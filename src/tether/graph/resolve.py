"""Turn a table name as written in SQL into a DataHub URN.

dbt writes `analytics.public.orders`, or just `orders` in a ref(). The graph holds
`urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.public.orders,PROD)`. This module
is the only place that gap is bridged, and it caches, because the diff parser will ask for
the same table many times.
"""

from __future__ import annotations

from functools import lru_cache

from ..datahub_client import client

SEARCH = """
query resolve($q: String!) {
  search(input: {type: DATASET, query: $q, start: 0, count: 10}) {
    searchResults {
      entity {
        urn
        ... on Dataset {
          name
          platform { name }
          properties { qualifiedName }
        }
      }
    }
  }
}
"""


def schema_field_urn(dataset_urn: str, column: str) -> str:
    return f"urn:li:schemaField:({dataset_urn},{column})"


@lru_cache(maxsize=512)
def resolve_dataset(table: str, platform: str = "snowflake") -> str | None:
    """Best match for a table reference. Exact qualifiedName wins, then suffix match."""
    leaf = table.split(".")[-1]
    data = client().graphql(SEARCH, {"q": leaf})
    results = [r["entity"] for r in data["search"]["searchResults"]]
    if not results:
        return None

    wanted = table.lower()
    exact = [
        e
        for e in results
        if ((e.get("properties") or {}).get("qualifiedName") or "").lower() == wanted
        or (e.get("name") or "").lower() == wanted
    ]
    if exact:
        return exact[0]["urn"]

    same_platform = [
        e for e in results if ((e.get("platform") or {}).get("name") or "").lower() == platform
    ]
    pool = same_platform or results
    suffix = [e for e in pool if (e.get("name") or "").lower().endswith(leaf.lower())]
    return (suffix or pool)[0]["urn"]


FEATURE_SEARCH = """
query resolveFeature($q: String!) {
  search(input: {type: MLFEATURE, query: $q, start: 0, count: 20}) {
    searchResults { entity { urn ... on MLFeature { name } } }
  }
}
"""


@lru_cache(maxsize=512)
def resolve_feature_urn(name: str) -> str | None:
    """Find an mlFeature's URN in DataHub by its name. Works on any DataHub, no local files.

    The feature already exists in the user's graph (their ML platform emitted it); Tether just
    needs its URN to attach a repaired source edge. Matched on exact name.
    """
    data = client().graphql(FEATURE_SEARCH, {"q": name})
    for r in data["search"]["searchResults"]:
        e = r["entity"]
        if (e.get("name") or "").lower() == name.lower():
            return e["urn"]
    return None


def resolve_column(table: str, column: str) -> str | None:
    ds = resolve_dataset(table)
    return schema_field_urn(ds, column) if ds else None
