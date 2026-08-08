"""Control arm: the same agent, same diffs, with a dbt manifest instead of DataHub.

This is not a strawman. It does real impact analysis: it parses `manifest.json`, walks the
full `child_map`, and reports every downstream dbt model and exposure the column feeds. It
is the analysis most data teams actually have today.

It returns zero ML impacts, always, and not because it is badly written. dbt has no concept
of a feature or a model or a deployment, so the entities cannot appear in its graph. That
structural blindness is the finding, and it is why the two-arm number is worth publishing.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..verdict.models import Impact


@lru_cache(maxsize=4)
def _manifest(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def downstream_nodes(table: str, manifest_path: str) -> list[str]:
    """Every dbt node downstream of this table. The best this arm can do."""
    m = _manifest(manifest_path)
    child_map = m.get("child_map", {})
    start = next(
        (
            uid
            for uid, node in m.get("nodes", {}).items()
            if node.get("name", "").lower() == table.split(".")[-1].lower()
        ),
        None,
    )
    if not start:
        return []

    seen: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        for child in child_map.get(cur, []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return sorted(seen)


def ml_impacts(column_urn: str, manifest_path: str = "demo/warehouse/target/manifest.json") -> list[Impact]:
    """Always empty. dbt's graph contains no mlFeature, mlModel or mlModelDeployment."""
    return []
