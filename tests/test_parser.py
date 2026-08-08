from __future__ import annotations

from pathlib import Path

from tether.diff.parser import parse_diff
from tether.verdict.models import ChangeKind

CASE = (
    Path(__file__).resolve().parents[1] / "bench" / "cases" / "001-drop-orders-discount-pct" / "diff.patch"
)

DDL = """diff --git a/ddl/orders.sql b/ddl/orders.sql
--- a/ddl/orders.sql
+++ b/ddl/orders.sql
@@ -1,2 +1,3 @@
 -- migrations
+ALTER TABLE analytics.orders RENAME COLUMN discount_pct TO discount_rate;
+ALTER TABLE analytics.orders ALTER COLUMN quantity TYPE varchar(16);
"""


def test_dbt_drop_is_detected():
    changes = parse_diff(CASE.read_text(encoding="utf-8"))
    dropped = [c for c in changes if c.kind is ChangeKind.DROP]
    assert [c.column for c in dropped] == ["discount_pct"]


def test_dbt_drop_finds_exactly_one_change():
    changes = parse_diff(CASE.read_text(encoding="utf-8"))
    assert len(changes) == 1, [c.label() for c in changes]


def test_ddl_rename_and_retype():
    changes = parse_diff(DDL)
    kinds = {c.kind for c in changes}
    assert ChangeKind.RENAME in kinds
    assert ChangeKind.RETYPE in kinds
    rename = next(c for c in changes if c.kind is ChangeKind.RENAME)
    assert rename.column == "discount_pct" and rename.new_name == "discount_rate"


def test_non_sql_files_are_ignored():
    diff = "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@\n-old\n+new\n"
    assert parse_diff(diff) == []
