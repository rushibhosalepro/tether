"""The last-mile verb: a failing required check that greys out the merge button.

Detection without action puts the load back on the reviewer. This module is the difference
between Tether being a report and Tether being a gate.
"""

from __future__ import annotations

import os

import requests

from ..config import settings
from ..verdict.models import Level, Report

API = "https://api.github.com"


def summary_markdown(report: Report, incident_urns: list[str]) -> str:
    from .incident import incident_link

    if report.level is Level.PASS:
        return "No production ML model consumes any column changed in this PR."

    lines = ["| Column | Change | Model | Deployment | Owner | Last trained |", "|---|---|---|---|---|---|"]
    for v in report.verdicts:
        if v.level is Level.PASS:
            continue
        for i in v.impacts:
            lines.append(
                f"| `{v.change.label()}` | {v.change.kind.value} | **{i.model_name}** | "
                f"{i.deployment_status or 'not deployed'} | {', '.join(i.owners) or 'unowned'} | "
                f"{i.last_trained or 'unknown'} |"
            )

    body = ["\n".join(lines), ""]
    for v in report.verdicts:
        if v.level is Level.BLOCK:
            body.append(f"- **{v.change.label()}** ({v.rule_id}): {v.reason}")
        elif v.level is Level.WARN and v.llm_note:
            body.append(f"- {v.change.label()} downgraded to WARN: {v.llm_note}")

    if incident_urns:
        body += ["", "Filed in DataHub:"]
        body += [f"- {incident_link(u)}" for u in incident_urns]

    body += [
        "",
        "---",
        "Every BLOCK above was decided by the deterministic classifier. The LLM can only "
        "downgrade a verdict, never raise one.",
    ]
    return "\n".join(body)


def post_check(report: Report, incident_urns: list[str], sha: str | None = None) -> str | None:
    """Create a check run on the PR head. Returns the check URL, or None when not in CI."""
    token = settings.gh_token
    repo = settings.gh_repo
    sha = sha or os.getenv("GITHUB_SHA", "")
    if not (token and repo and sha):
        return None

    conclusion = {"BLOCK": "failure", "WARN": "neutral", "PASS": "success"}[report.level.value]
    n = len(report.blocked_models)
    title = {
        "BLOCK": f"{n} production model(s) still read a column this PR changes",
        "WARN": "Schema change touches ML lineage, review before merge",
        "PASS": "No production ML impact",
    }[report.level.value]

    resp = requests.post(
        f"{API}/repos/{repo}/check-runs",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "name": "tether",
            "head_sha": sha,
            "status": "completed",
            "conclusion": conclusion,
            "output": {
                "title": title,
                "summary": summary_markdown(report, incident_urns),
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("html_url")
