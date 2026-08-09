"""Parser coverage for the shapes real PRs actually take.

These complement test_parser.py with multi-column diffs, retypes, and the exact synthesized
form the benchmark uses, so a change to the parser that breaks the benchmark fails here first.
"""

from __future__ import annotations

from tether.diff.parser import parse_diff
from tether.verdict.models import ChangeKind


def _drop_diff(table: str, column: str) -> str:
    model = table.split(".")[-1]
    return (
        f"diff --git a/models/{model}.sql b/models/{model}.sql\n"
        f"--- a/models/{model}.sql\n+++ b/models/{model}.sql\n"
        f"@@ -1,4 +1,3 @@\n select\n-    {column},\n     other_col\n from {table}\n"
    )


def test_benchmark_style_diff_parses_one_drop():
    changes = parse_diff(_drop_diff("analytics.public.orders", "discount_pct"))
    assert len(changes) == 1
    assert changes[0].kind is ChangeKind.DROP
    assert changes[0].column == "discount_pct"


def test_multiple_dropped_columns_in_one_file():
    diff = (
        "diff --git a/models/orders.sql b/models/orders.sql\n"
        "--- a/models/orders.sql\n+++ b/models/orders.sql\n"
        "@@ -1,5 +1,3 @@\n select\n-    discount_pct,\n-    quantity,\n     total_amount\n from orders\n"
    )
    cols = sorted(c.column for c in parse_diff(diff))
    assert cols == ["discount_pct", "quantity"]


def test_added_column_is_not_a_drop():
    diff = (
        "diff --git a/models/orders.sql b/models/orders.sql\n"
        "--- a/models/orders.sql\n+++ b/models/orders.sql\n"
        "@@ -1,3 +1,4 @@\n select\n     total_amount,\n+    new_col\n from orders\n"
    )
    drops = [c for c in parse_diff(diff) if c.kind is ChangeKind.DROP]
    assert drops == []


def test_status_column_drop_is_detected_but_harmless_downstream():
    # the parser still reports it; the classifier is what makes it PASS (no consumer)
    changes = parse_diff(_drop_diff("analytics.public.orders", "status"))
    assert [c.column for c in changes] == ["status"]
