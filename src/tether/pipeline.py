"""diff -> changes -> URNs -> ML impacts -> verdicts -> write-back.

The whole product in one readable function, deliberately. A judge should be able to read
`run()` top to bottom and see every claim the README makes.
"""

from __future__ import annotations

from typing import Callable

from .arms import datahub_arm, dbt_manifest_arm
from .diff.parser import parse_diff
from .graph.resolve import resolve_dataset, schema_field_urn
from .verdict import llm_assist
from .verdict.classifier import assert_deterministic, classify
from .verdict.models import Impact, Level, Report

ARMS: dict[str, Callable[..., list[Impact]]] = {
    "datahub": datahub_arm.ml_impacts,
    "dbt-only": dbt_manifest_arm.ml_impacts,
}


def run(
    diff_text: str,
    pr_url: str,
    arm: str = "datahub",
    use_llm: bool = True,
) -> tuple[Report, dict[str, str]]:
    """Returns the report and a map of column label -> schemaField URN for write-back."""
    impacts_for = ARMS[arm]
    changes = parse_diff(diff_text)
    report = Report(pr_url=pr_url)
    column_urns: dict[str, str] = {}

    for change in changes:
        impacts: list[Impact] = []
        try:
            dataset_urn = resolve_dataset(change.table)
            if dataset_urn:
                column_urns[change.label()] = schema_field_urn(dataset_urn, change.column)
                impacts = impacts_for(dataset_urn, change.column)
        except Exception as exc:  # unresolvable table is a finding, not a crash
            verdict = classify(change, [])
            verdict.reason = f"Could not resolve {change.label()} in DataHub: {exc}"
            verdict.rule_id = "R-unresolved"
            report.verdicts.append(verdict)
            continue

        verdict = classify(change, impacts)
        if use_llm and verdict.level is Level.BLOCK:
            verdict = llm_assist.soften(verdict, diff_text)
        report.verdicts.append(assert_deterministic(verdict))

    return report, column_urns


def write_back(report: Report, column_urns: dict[str, str], pr_url: str) -> dict:
    """The three artifacts. Each one is independently allowed to fail."""
    from .writeback import github_check, incident, memory

    out: dict = {"incidents": [], "links": 0, "check_url": None, "errors": []}
    try:
        out["incidents"] = incident.raise_all(report.verdicts, pr_url)
    except Exception as exc:
        out["errors"].append(f"incident: {exc}")
    try:
        out["links"] = memory.record_all(report.verdicts, column_urns, pr_url)
    except Exception as exc:
        out["errors"].append(f"memory: {exc}")
    try:
        out["check_url"] = github_check.post_check(report, out["incidents"])
    except Exception as exc:
        out["errors"].append(f"check: {exc}")
    return out
