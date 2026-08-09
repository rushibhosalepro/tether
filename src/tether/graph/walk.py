"""Walk forward from a changed column, past the dashboards, into the ML layer.

This is the part of Tether that only exists because DataHub exists. Everyone else's impact
analysis terminates at the BI layer. This one keeps going: dataset -> mlFeature -> mlModel ->
mlModelDeployment, and returns the models that are actually serving.

How the walk actually works (verified against OSS quickstart, 2026-08-09):

DataHub models ML lineage as entity-level relationships, not column-level:

    dataset  <--DerivedFrom--  mlFeature  <--Consumes--  mlModel  --deployments-->  deployment

`searchAcrossLineage` does not traverse these edges when you start from the dataset, so the
walk uses the relationships API directly and deterministically:

    1. dataset  -> INCOMING DerivedFrom -> the features built from it
    2. feature  -> INCOMING Consumes    -> the models that use those features
    3. model    -> its deployments and their status

The graph edge is dataset-level. Which *column* a feature reads is not stored on the edge;
that precision is recorded evidence Tether itself adds (see writeback/lineage.py and the
repair module). `column_used_by` filters features to the changed column using that evidence
when it exists, and is conservative (assumes used) when it does not.
"""

from __future__ import annotations

from ..datahub_client import client
from ..verdict.models import Impact

FEATURES_FROM_DATASET = """
query featuresFrom($urn: String!, $count: Int!) {
  entity(urn: $urn) {
    relationships(input: {types: ["DerivedFrom"], direction: INCOMING, count: $count}) {
      relationships {
        entity {
          urn
          ... on MLFeature { name properties { description sources { urn } } }
        }
      }
    }
  }
}
"""

MODELS_FROM_FEATURE = """
query modelsFrom($urn: String!, $count: Int!) {
  entity(urn: $urn) {
    relationships(input: {types: ["Consumes"], direction: INCOMING, count: $count}) {
      relationships {
        entity {
          urn
          ... on MLModel {
            name
            properties { description customProperties { key value } }
            ownership { owners { owner { ... on CorpUser { urn username } } } }
          }
        }
      }
    }
  }
}
"""


def _props(entity: dict) -> dict[str, str]:
    kv = ((entity.get("properties") or {}).get("customProperties") or [])
    return {p["key"]: p["value"] for p in kv}


def _owners(entity: dict) -> list[str]:
    out = []
    for o in ((entity.get("ownership") or {}).get("owners") or []):
        owner = o.get("owner") or {}
        name = owner.get("username") or owner.get("urn", "")
        if name:
            out.append(f"@{name}" if not name.startswith("urn:") else name)
    return out


def features_of(dataset_urn: str, count: int = 50) -> list[dict]:
    """The mlFeature entities derived from a dataset. Empty when the edge was never declared."""
    data = client().graphql(FEATURES_FROM_DATASET, {"urn": dataset_urn, "count": count})
    rels = (((data or {}).get("entity") or {}).get("relationships") or {}).get("relationships") or []
    return [r["entity"] for r in rels]


def _column_used_by(feature: dict, column: str | None) -> bool:
    """Does this feature (found in the graph) read the changed column?

    The graph edge is dataset-level, so column precision comes from parsing the feature SQL
    (repair.infer). When the SQL proves it, use the exact answer. When there is no SQL to read
    (a Python feature whose edge was nonetheless declared), stay conservative and include it,
    because a false negative on a real declared dependency is the expensive error.
    """
    if not column:
        return True
    from ..repair.infer import infer

    name = feature.get("name")
    if not name:
        return True
    ev = infer(name)
    if not ev.provable:
        return True  # declared edge we cannot parse: do not silently drop it
    return column.lower() in ev.columns


def ml_impacts(dataset_urn: str, column: str | None = None, max_results: int = 50) -> list[Impact]:
    """Every serving model reachable from a dataset (optionally filtered to one column).

    Deduplicated by model: if two features feed the same model, the model appears once,
    attributed to the first feature that reached it.
    """
    impacts: dict[str, Impact] = {}
    for feat in features_of(dataset_urn, max_results):
        if not _column_used_by(feat, column):
            continue
        for imp in models_of_feature(feat["urn"], feat.get("name", ""), dataset_urn, max_results):
            impacts.setdefault(imp.model_urn, imp)
    return list(impacts.values())


def models_of_feature(feat_urn: str, feat_name: str, dataset_urn: str, max_results: int = 50) -> list[Impact]:
    """The serving models that consume one feature. Used by the walk and, after a repair, to
    build impacts from the just-repaired feature directly, without waiting for the freshly
    written dataset->feature edge to finish indexing."""
    data = client().graphql(MODELS_FROM_FEATURE, {"urn": feat_urn, "count": max_results})
    rels = (((data or {}).get("entity") or {}).get("relationships") or {}).get("relationships") or []
    out: list[Impact] = []
    for r in rels:
        m = r["entity"]
        props = _props(m)
        serving, assumed = _is_serving(props)
        out.append(
            Impact(
                model_urn=m["urn"],
                model_name=m.get("name") or m["urn"].split(",")[-2],
                feature_urn=feat_urn,
                feature_name=feat_name,
                deployment_urn=None,
                deployment_status="IN_SERVICE" if serving else None,
                owners=_owners(m),
                last_trained=props.get("last_trained"),
                hops=[dataset_urn, feat_urn, m["urn"]],
                serving_assumed=assumed,
            )
        )
    return out


def _is_serving(props: dict[str, str]) -> tuple[bool, bool]:
    """(is_serving, assumed). Conservative: if we cannot tell, assume live and flag it.

    OSS DataHub does not expose deployment entities over GraphQL, so serving state comes from a
    model property. We check, in order: a configurable property (TETHER_SERVING_PROPERTY,
    default `serving`), then mlflow's `stage`. If none is present we do NOT clear the block,
    because a false negative on a live model is the expensive error. Blocking is the whole verb;
    it must not switch itself off just because an instance labels deployment differently.
    """
    from ..config import settings

    key = settings.serving_property
    if key in props:
        return props[key].strip().lower() in ("true", "yes", "production", "serving", "in_service"), False
    stage = (props.get("stage") or props.get("mlflow.stage") or "").strip().lower()
    if stage:
        return stage in ("production", "serving", "staging_production"), False
    return True, True  # unknown deployment state -> treat as live, and say so in the reason
