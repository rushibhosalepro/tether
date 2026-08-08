"""Unified diff -> ColumnChange[].

Two sources of truth in a data repo, so two paths:
  * `.sql` under models/ is dbt. Compare the selected column list before and after.
  * `.sql` containing ALTER/CREATE TABLE is DDL. Read the statement directly.

Renames are inferred, not declared: a column that disappears and one that appears in the
same file, with the same type, is a rename. That inference is one of the things the
benchmark measures, so it is deliberately conservative.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..verdict.models import ChangeKind, ColumnChange
from .sqlglot_ddl import columns_of, ddl_changes, is_ddl

FILE_RE = re.compile(r"^diff --git a/(?P<a>\S+) b/(?P<b>\S+)", re.M)
HUNK_RE = re.compile(r"^@@ .* @@", re.M)
# `-- tether: semantic <table>.<column> <note>` lets a PR author declare a meaning change
SEMANTIC_RE = re.compile(r"--\s*tether:\s*semantic\s+(\S+)\.(\S+)\s*(.*)", re.I)


def parse_diff(diff_text: str, repo_root: Path | None = None) -> list[ColumnChange]:
    changes: list[ColumnChange] = []
    for path, before, after in _files(diff_text):
        if not path.endswith(".sql"):
            continue
        table = _table_name(path, after or before)
        if is_ddl(after or before):
            changes.extend(ddl_changes(table, before, after, path))
        else:
            changes.extend(_dbt_changes(table, before, after, path))
        changes.extend(_declared_semantic(after, path))
    return _infer_renames(changes)


def _files(diff_text: str) -> list[tuple[str, str, str]]:
    """Split a unified diff into (path, before_content, after_content).

    Reconstructs both sides from the hunks. Good enough for whole-file dbt models, which is
    how dbt PRs actually look.
    """
    out = []
    blocks = re.split(r"(?m)^diff --git ", diff_text)
    for block in blocks:
        if not block.strip():
            continue
        m = re.match(r"a/(\S+) b/(\S+)", block)
        if not m:
            continue
        path = m.group(2)
        before_lines, after_lines = [], []
        for line in block.splitlines()[1:]:
            if line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
                continue
            if line.startswith("-"):
                before_lines.append(line[1:])
            elif line.startswith("+"):
                after_lines.append(line[1:])
            elif line.startswith(" "):
                before_lines.append(line[1:])
                after_lines.append(line[1:])
        out.append((path, "\n".join(before_lines), "\n".join(after_lines)))
    return out


def _table_name(path: str, sql: str) -> str:
    """dbt model file name is the table name unless the SQL says otherwise."""
    m = re.search(r"(?:CREATE|ALTER)\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"]+)", sql, re.I)
    if m:
        return m.group(1).replace('"', "")
    return Path(path).stem


def _dbt_changes(table: str, before: str, after: str, path: str) -> list[ColumnChange]:
    old = columns_of(before)
    new = columns_of(after)
    changes = []
    for col, typ in old.items():
        if col not in new:
            changes.append(
                ColumnChange(table, col, ChangeKind.DROP, old_type=typ, source_file=path)
            )
        elif typ and new[col] and typ != new[col]:
            changes.append(
                ColumnChange(
                    table, col, ChangeKind.RETYPE, old_type=typ, new_type=new[col], source_file=path
                )
            )
    return changes


def _declared_semantic(sql: str, path: str) -> list[ColumnChange]:
    out = []
    for m in SEMANTIC_RE.finditer(sql or ""):
        out.append(
            ColumnChange(m.group(1), m.group(2), ChangeKind.SEMANTIC, source_file=path)
        )
    return out


def _infer_renames(changes: list[ColumnChange]) -> list[ColumnChange]:
    """A DROP and an ADD of the same type in the same file is a rename, not a drop."""
    drops = [c for c in changes if c.kind is ChangeKind.DROP]
    adds = [c for c in changes if c.kind is ChangeKind.SEMANTIC and c.new_name]
    for d in drops:
        match = next(
            (a for a in adds if a.source_file == d.source_file and a.old_type == d.old_type), None
        )
        if match:
            d.kind = ChangeKind.RENAME
            d.new_name = match.column
            changes.remove(match)
    return changes
