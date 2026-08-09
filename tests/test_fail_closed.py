"""Tether must fail closed: when it cannot verify a change, it never shows green.

These guard the correctness bug where an unreachable DataHub, a parse failure, or a transient
error used to return PASS on a PR that breaks a model.
"""

from __future__ import annotations

import tether.pipeline as pipeline
from tether.graph.walk import _is_serving
from tether.verdict.models import ChangeKind, ColumnChange, Impact, Level, Report, Verdict

DIFF = (
    "diff --git a/models/orders.sql b/models/orders.sql\n"
    "--- a/models/orders.sql\n+++ b/models/orders.sql\n"
    "@@ -1,4 +1,3 @@\n select\n-    discount_pct,\n     other_col\n from analytics.public.orders\n"
)


def test_unreachable_datahub_errors_not_passes(monkeypatch):
    def boom(_table):
        raise ConnectionError("DataHub unreachable")

    monkeypatch.setattr(pipeline, "resolve_dataset", boom)
    report, _ = pipeline.run(DIFF, "pr", use_llm=False)
    assert report.level is Level.ERROR
    assert report.fails_check


def test_walk_failure_errors_not_passes(monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_dataset", lambda t: "urn:li:dataset:x")

    def boom(*a, **k):
        raise RuntimeError("500 from GMS")

    monkeypatch.setitem(pipeline.ARMS, "datahub", boom)
    report, _ = pipeline.run(DIFF, "pr", use_llm=False)
    assert report.level is Level.ERROR
    assert report.fails_check


def test_error_and_block_both_fail_the_check():
    err = Verdict(change=ColumnChange("t", "c", ChangeKind.DROP), level=Level.ERROR)
    assert Report("pr", [err]).fails_check
    blk = Verdict(
        change=ColumnChange("t", "c", ChangeKind.DROP),
        level=Level.BLOCK,
        impacts=[Impact(model_urn="m", model_name="m", deployment_status="IN_SERVICE")],
    )
    assert Report("pr", [blk]).fails_check
    warn = Verdict(change=ColumnChange("t", "c", ChangeKind.DROP), level=Level.WARN)
    assert not Report("pr", [warn]).fails_check


def test_serving_defaults_to_live_when_unknown():
    # a real DataHub without our seeded 'serving' property must still block, not silently WARN
    serving, assumed = _is_serving({})
    assert serving and assumed


def test_serving_reads_mlflow_stage():
    assert _is_serving({"stage": "Production"}) == (True, False)
    assert _is_serving({"stage": "Archived"}) == (False, False)


def test_serving_explicit_property_wins():
    assert _is_serving({"serving": "false"}) == (False, False)
    assert _is_serving({"serving": "true"}) == (True, False)
