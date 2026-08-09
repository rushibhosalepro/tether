"""Recover which source columns a feature reads, by parsing its SQL. Never the answer key.

This is the heart of the honesty story. DataHub's ML lineage is dataset-level: it knows a
feature came from `orders`, not which columns. Tether gets column precision the only correct
way, by reading the actual feature-engineering SQL the same way an engineer would.

Used in two places:
  * the walk, to filter a dataset's features down to the changed column
  * the repair, to prove a missing edge before writing it back

It reads only the SQL files under `settings.features_dir`. It never reads entities.yaml or
ground_truth.yaml. If a feature is computed in Python (no SQL), it recovers nothing and the
caller must refuse to act rather than guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ..config import settings


@dataclass
class Evidence:
    feature: str
    columns: set[str]
    sql_file: str
    expression_line: int  # 1-indexed line in the SQL where the column first appears
    provable: bool        # False when there is no SQL to point at

    def cite(self) -> str:
        return f"{self.sql_file}:{self.expression_line}"


def _sql_path(feature: str):
    p = settings.features_dir / f"{feature}.sql"
    return p if p.exists() else None


@lru_cache(maxsize=256)
def infer(feature: str) -> Evidence:
    """Recover source columns for one feature from its SQL. Empty + provable=False if no SQL."""
    path = _sql_path(feature)
    if path is None:
        return Evidence(feature, set(), "", 0, provable=False)

    sql = path.read_text(encoding="utf-8")
    cols = _columns_from_sql(sql, feature)
    line = _first_line(sql, cols)
    return Evidence(feature, cols, str(path.relative_to(settings.features_dir.parents[2])), line, provable=bool(cols))


def _columns_from_sql(sql: str, feature: str) -> set[str]:
    from sqlglot.lineage import lineage

    try:
        node = lineage(feature, sql)
    except Exception:
        return set()
    cols: set[str] = set()

    def walk(n) -> None:
        if not n.downstream and "." in str(n.name):
            cols.add(str(n.name).split(".")[-1].lower())
        for d in n.downstream:
            walk(d)

    walk(node)
    return cols


def _first_line(sql: str, cols: set[str]) -> int:
    for i, line in enumerate(sql.splitlines(), start=1):
        low = line.lower()
        if any(c in low for c in cols):
            return i
    return 1


def uses_column(feature: str, column: str) -> bool:
    """Does this feature read this column, per its SQL? Conservative only when unprovable."""
    ev = infer(feature)
    if not ev.provable:
        return False  # no SQL to prove it; do not claim a column dependency we cannot show
    return column.lower() in ev.columns
