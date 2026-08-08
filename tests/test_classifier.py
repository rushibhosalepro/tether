from __future__ import annotations

import pytest

from tether.verdict.classifier import classify
from tether.verdict.models import ChangeKind, ColumnChange, Impact, Level


def live(name="churn_propensity_v4"):
    return Impact(
        model_urn=f"urn:li:mlModel:(urn:li:dataPlatform:mlflow,{name},PROD)",
        model_name=name,
        deployment_status="IN_PRODUCTION",
        owners=["@aman"],
        last_trained="2026-03-14",
    )


def shelved(name="churn_propensity_v3"):
    return Impact(model_urn=f"urn:li:mlModel:x,{name}", model_name=name, deployment_status=None)


def change(kind, old=None, new=None, new_name=None):
    return ColumnChange("analytics.orders", "discount_pct", kind, old, new, new_name)


def test_no_ml_consumer_passes():
    v = classify(change(ChangeKind.DROP), [])
    assert v.level is Level.PASS and v.rule_id == "R0"


def test_drop_under_live_model_blocks():
    v = classify(change(ChangeKind.DROP), [live()])
    assert v.level is Level.BLOCK and v.rule_id == "R1"
    assert "churn_propensity_v4" in v.reason


def test_rename_blocks_like_a_drop():
    v = classify(change(ChangeKind.RENAME, new_name="discount_rate"), [live()])
    assert v.level is Level.BLOCK and v.rule_id == "R2"


def test_semantic_change_blocks_because_nothing_throws():
    v = classify(change(ChangeKind.SEMANTIC), [live()])
    assert v.level is Level.BLOCK and v.rule_id == "R4"


@pytest.mark.parametrize("old,new", [("int", "bigint"), ("float", "double"), ("date", "timestamp")])
def test_widening_warns_not_blocks(old, new):
    v = classify(change(ChangeKind.RETYPE, old, new), [live()])
    assert v.level is Level.WARN and v.rule_id == "R3a"


def test_type_class_change_blocks():
    v = classify(change(ChangeKind.RETYPE, "int", "varchar(32)"), [live()])
    assert v.level is Level.BLOCK and v.rule_id == "R3b"


def test_model_with_no_deployment_warns():
    v = classify(change(ChangeKind.DROP), [shelved()])
    assert v.level is Level.WARN and v.rule_id == "R5"
