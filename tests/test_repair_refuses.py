"""The second determinism boundary: Tether never writes an edge it cannot prove from SQL.

The README claims "Tether never writes a lineage edge it cannot point at a SQL expression
for." These tests make that claim checkable, the same way test_llm_cannot_block does for the
verdict side. No DataHub needed: repair runs in dry_run.
"""

from __future__ import annotations

from tether.repair import infer
from tether.repair.diagnose import LineageGap
from tether.repair.emit import repair


def test_sql_feature_is_provable():
    ev = infer.infer("discount_sensitivity")
    assert ev.provable
    assert "discount_pct" in ev.columns
    assert "total_amount" in ev.columns
    assert ev.cite().endswith(".sql:5") or ".sql:" in ev.cite()


def test_python_feature_is_not_provable():
    ev = infer.infer("support_sentiment")
    assert not ev.provable
    assert ev.columns == set()


def test_repair_writes_a_provable_edge():
    gap = LineageGap(
        column="orders.discount_pct",
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.public.orders,PROD)",
        feature="discount_sensitivity",
        feature_urn="urn:li:mlFeature:(customer_churn_features,discount_sensitivity)",
        evidence="features/discount_sensitivity.sql:5",
        provable=True,
    )
    res = repair([gap], dry_run=True)
    assert res.repaired and not res.refused


def test_repair_refuses_an_unprovable_edge():
    gap = LineageGap(
        column="customers.support_tickets",
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.public.customers,PROD)",
        feature="support_sentiment",
        feature_urn="urn:li:mlFeature:(customer_churn_features,support_sentiment)",
        evidence="support_sentiment.py (no SQL)",
        provable=False,
    )
    res = repair([gap], dry_run=True)
    assert res.refused and not res.repaired
    assert "support_sentiment" in res.refused[0]
