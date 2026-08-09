"""Report roll-up and the SQL inference across every seeded feature."""

from __future__ import annotations

import pytest

from tether.repair import infer
from tether.verdict.models import ChangeKind, ColumnChange, Impact, Level, Report, Verdict


def _v(level: Level, model="m", change_col="c") -> Verdict:
    imp = Impact(model_urn=f"urn:{model}", model_name=model, deployment_status="IN_SERVICE")
    return Verdict(
        change=ColumnChange("t", change_col, ChangeKind.DROP),
        level=level,
        impacts=[imp] if level is not Level.PASS else [],
    )


def test_report_level_is_the_worst_verdict():
    assert Report("pr", [_v(Level.PASS), _v(Level.WARN)]).level is Level.WARN
    assert Report("pr", [_v(Level.PASS), _v(Level.BLOCK), _v(Level.WARN)]).level is Level.BLOCK
    assert Report("pr", [_v(Level.PASS)]).level is Level.PASS


def test_blocked_models_dedupe_across_verdicts():
    r = Report("pr", [_v(Level.BLOCK, "churn"), _v(Level.BLOCK, "churn"), _v(Level.BLOCK, "pricing")])
    names = sorted(i.model_name for i in r.blocked_models)
    assert names == ["churn", "pricing"]


# every SQL feature must be recoverable; the Python one must not be
@pytest.mark.parametrize(
    "feature,expected",
    [
        ("discount_sensitivity", {"discount_pct", "total_amount"}),
        ("avg_basket_value", {"total_amount"}),
        ("order_frequency_90d", {"order_id"}),
        ("margin_band", {"unit_cost", "list_price"}),
        ("demand_index_7d", {"quantity"}),
    ],
)
def test_sql_features_are_provable(feature, expected):
    ev = infer.infer(feature)
    assert ev.provable
    assert expected.issubset(ev.columns)


def test_python_feature_is_never_provable():
    assert not infer.infer("support_sentiment").provable
