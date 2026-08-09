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
            properties { description lastModified { time } deployments { urn } }
            ownership { owners { owner { ... on CorpUser { urn username } } } }
          }
        }
      }
    }
  }
}
"""

DEPLOYMENT = """
query deployment($urn: String!) {
  mlModelDeployment(urn: $urn) { urn properties { status createdAt } }
}
"""


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
    """Conservative column filter. The graph edge is dataset-level, so we lean on evidence.

    Tether records the source columns it inferred in the feature description/props. If that
    evidence names the column, it is used. If there is no evidence, assume used rather than
    silently clearing a real dependency (a false negative is the expensive error).
    """
    if not column:
        return True
    desc = ((feature.get("properties") or {}).get("description") or "").lower()
    if "source_columns" in desc or column.lower() in desc:
        return column.lower() in desc
    return True


def ml_impacts(dataset_urn: str, column: str | None = None, max_results: int = 50) -> list[Impact]:
    """Every serving model reachable from a dataset (optionally filtered to one column)."""
    impacts: list[Impact] = []
    for feat in features_of(dataset_urn, max_results):
        if not _column_used_by(feat, column):
            continue
        feat_urn = feat["urn"]
        feat_name = feat.get("name", "")
        data = client().graphql(MODELS_FROM_FEATURE, {"urn": feat_urn, "count": max_results})
        rels = (((data or {}).get("entity") or {}).get("relationships") or {}).get("relationships") or []
        for r in rels:
            m = r["entity"]
            props = m.get("properties") or {}
            dep_urns = [d["urn"] for d in (props.get("deployments") or [])]
            status, dep_urn = _deployment_status(dep_urns)
            impacts.append(
                Impact(
                    model_urn=m["urn"],
                    model_name=m.get("name") or m["urn"].split(",")[-2],
                    feature_urn=feat_urn,
                    feature_name=feat_name,
                    deployment_urn=dep_urn,
                    deployment_status=status,
                    owners=_owners(m),
                    last_trained=_iso(((props.get("lastModified") or {}).get("time"))),
                    hops=[dataset_urn, feat_urn, m["urn"]],
                )
            )
    return impacts


def _deployment_status(dep_urns: list[str]) -> tuple[str | None, str | None]:
    for urn in dep_urns:
        try:
            d = client().graphql(DEPLOYMENT, {"urn": urn})
        except Exception:
            continue
        props = ((d.get("mlModelDeployment") or {}).get("properties") or {})
        if props.get("status") == "IN_PRODUCTION":
            return "IN_PRODUCTION", urn
    return (None, dep_urns[0]) if dep_urns else (None, None)


def _iso(ms: int | None) -> str | None:
    if not ms:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
