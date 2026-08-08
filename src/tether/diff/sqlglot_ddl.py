"""Column extraction, via sqlglot when it parses and regex when it does not.

dbt models in the wild have Jinja in them, which sqlglot will refuse. Falling back rather
than failing is the right call: a missed column shows up in the benchmark as a miss, and a
crash shows up as a broken demo.
"""

from __future__ import annotations

import re

from ..verdict.models import ChangeKind, ColumnChange

DDL_RE = re.compile(r"\b(ALTER|CREATE)\s+TABLE\b", re.I)
DROP_COL_RE = re.compile(r"ALTER\s+TABLE\s+([\w.\"]+)\s+DROP\s+(?:COLUMN\s+)?([\w\"]+)", re.I)
RENAME_COL_RE = re.compile(
    r"ALTER\s+TABLE\s+([\w.\"]+)\s+RENAME\s+(?:COLUMN\s+)?([\w\"]+)\s+TO\s+([\w\"]+)", re.I
)
ALTER_TYPE_RE = re.compile(
    r"ALTER\s+TABLE\s+([\w.\"]+)\s+ALTER\s+(?:COLUMN\s+)?([\w\"]+)\s+(?:SET\s+DATA\s+)?TYPE\s+([\w()]+)",
    re.I,
)
SELECT_ALIAS_RE = re.compile(r"(?:^|,)\s*(?:[\w.\"]+|\([^)]*\))\s+as\s+([\w\"]+)", re.I | re.M)
BARE_COL_RE = re.compile(r"(?:^|,)\s*([a-z_][\w]*)\s*(?=,|$)", re.I | re.M)


def _clean(s: str) -> str:
    return s.replace('"', "").strip().lower()


def is_ddl(sql: str) -> bool:
    return bool(DDL_RE.search(sql or ""))


def columns_of(sql: str) -> dict[str, str | None]:
    """Column name -> declared type, for whatever this SQL produces."""
    if not sql:
        return {}
    try:
        import sqlglot
        from sqlglot import exp

        tree = sqlglot.parse_one(sql, error_level=None)
        if tree is None:
            raise ValueError
        cols: dict[str, str | None] = {}
        for cd in tree.find_all(exp.ColumnDef):
            cols[_clean(cd.alias_or_name)] = str(cd.args.get("kind") or "").lower() or None
        if cols:
            return cols
        select = tree.find(exp.Select)
        if select:
            for p in select.expressions:
                name = p.alias_or_name
                if name and name != "*":
                    cols[_clean(name)] = None
            return cols
    except Exception:
        pass
    return _regex_columns(sql)


def _regex_columns(sql: str) -> dict[str, str | None]:
    body = sql
    m = re.search(r"select(.*?)\bfrom\b", sql, re.I | re.S)
    if m:
        body = m.group(1)
    cols: dict[str, str | None] = {}
    for name in SELECT_ALIAS_RE.findall(body):
        cols[_clean(name)] = None
    for name in BARE_COL_RE.findall(body):
        cols.setdefault(_clean(name), None)
    cols.pop("", None)
    return cols


def ddl_changes(table: str, before: str, after: str, path: str) -> list[ColumnChange]:
    """DDL states its intent, so read it rather than diffing column sets."""
    out: list[ColumnChange] = []
    added = "\n".join(
        line for line in (after or "").splitlines() if line.strip() and line not in (before or "")
    )
    for tbl, col in DROP_COL_RE.findall(added):
        out.append(ColumnChange(_clean(tbl) or table, _clean(col), ChangeKind.DROP, source_file=path))
    for tbl, old, new in RENAME_COL_RE.findall(added):
        out.append(
            ColumnChange(
                _clean(tbl) or table,
                _clean(old),
                ChangeKind.RENAME,
                new_name=_clean(new),
                source_file=path,
            )
        )
    for tbl, col, typ in ALTER_TYPE_RE.findall(added):
        out.append(
            ColumnChange(
                _clean(tbl) or table, _clean(col), ChangeKind.RETYPE, new_type=_clean(typ), source_file=path
            )
        )
    return out
