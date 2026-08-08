"""Walk forward from a changed column, past the dashboards, into the ML layer.

This is the part of Tether that only exists because DataHub exists. Everyone else's impact
analysis terminates at the BI layer. This one keeps going: dataset -> mlFeature ->
mlFeatureTable -> mlModel -> mlModelDeployment, and returns the models that are actually
serving.
"""

from __future__ import annotations

from ..datahub_client import client
from ..verdict.models import Impact

ML_TYPES = ["MLFEATURE", "MLPRIMARY_KEY", "MLMODEL", "MLMODEL_GROUP", "MLFEATURE_TABLE"]

DOWNSTREAM = """
query downstream($urn: String!, $types: [EntityType!], $count: Int!) {
  searchAcrossLineage(
    input: {urn: $urn, direction: DOWNSTREAM, types: $types, query: "*", start: 0, count: $count}
  ) {
    total
    searchResults {
      degree
      paths { path { urn type } }
      entity {
        urn
        type
        ... on MLFeature { name featureNamespace }
        ... on MLModel {
          name
          properties { description lastModified { time } deployments { urn } }
          ownership { owners { owner { ... on CorpUser { urn username } } } }
        }
      }
    }
  }
}
"""

DEPLOYMENT = """
query deployment($urn: String!) {
  mlModelDeployment(urn: $urn) {
    urn
    properties { status createdAt }
  }
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


def ml_impacts(column_urn: str, max_results: int = 50) -> list[Impact]:
    """Every ML model reachable downstream of one column, with its deployment status."""
    data = client().graphql(
        DOWNSTREAM, {"urn": column_urn, "types": ML_TYPES, "count": max_results}
    )
    results = data["searchAcrossLineage"]["searchResults"]

    features: dict[str, str] = {}  # urn -> name, for attribution on the model
    impacts: list[Impact] = []

    for r in results:
        e = r["entity"]
        if e["type"] == "MLFEATURE":
            features[e["urn"]] = e.get("name", "")

    for r in results:
        e = r["entity"]
        if e["type"] != "MLMODEL":
            continue
        props = e.get("properties") or {}
        path = [p["urn"] for p in (r.get("paths") or [{}])[0].get("path", [])]
        feat_urn = next((u for u in path if ":mlFeature:" in u), None)

        dep_urns = [d["urn"] for d in (props.get("deployments") or [])]
        status, dep_urn = _deployment_status(dep_urns)

        impacts.append(
            Impact(
                model_urn=e["urn"],
                model_name=e.get("name") or e["urn"].split(",")[-2],
                feature_urn=feat_urn,
                feature_name=features.get(feat_urn or "", None),
                deployment_urn=dep_urn,
                deployment_status=status,
                owners=_owners(e),
                last_trained=_iso(((props.get("lastModified") or {}).get("time"))),
                hops=path,
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
