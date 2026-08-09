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
    """Set a commit status on the PR head and post the detail as a PR comment.

    A commit status (not a check run) is used deliberately: the GitHub Checks API only accepts
    check runs from GitHub Apps, while a status works with a normal token and, when marked
    required, greys out the merge button exactly the same way. That is the last-mile verb.
    Returns the status target URL, or None when the token/repo/sha are not set.
    """
    token = settings.gh_token
    repo = settings.gh_repo
    sha = sha or os.getenv("GITHUB_SHA", "")
    if not (token and repo and sha):
        return None

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    state = {"BLOCK": "failure", "WARN": "success", "PASS": "success"}[report.level.value]
    n = len(report.blocked_models)
    desc = {
        "BLOCK": f"{n} production model(s) still read a column this PR changes",
        "WARN": "Schema change touches ML lineage, review before merge",
        "PASS": "No production ML impact",
    }[report.level.value][:140]

    resp = requests.post(
        f"{API}/repos/{repo}/statuses/{sha}",
        headers=headers,
        json={
            "state": state,
            "context": "tether",
            "description": desc,
            "target_url": report.pr_url,
        },
        timeout=30,
    )
    resp.raise_for_status()

    _upsert_comment(repo, report, incident_urns, headers)
    return resp.json().get("url")


def _upsert_comment(repo: str, report: Report, incident_urns: list[str], headers: dict) -> None:
    """Post (or update) one Tether comment on the PR, so re-runs don't spam it."""
    pr_number = report.pr_url.rstrip("/").split("/")[-1]
    if not pr_number.isdigit():
        return
    marker = "<!-- tether -->"
    icon = {"BLOCK": "🔴", "WARN": "🟡", "PASS": "🟢"}[report.level.value]
    body = f"{marker}\n## {icon} Tether: {report.level.value}\n\n" + summary_markdown(report, incident_urns)

    listing = requests.get(f"{API}/repos/{repo}/issues/{pr_number}/comments", headers=headers, timeout=30)
    existing = None
    if listing.ok:
        existing = next((c for c in listing.json() if marker in (c.get("body") or "")), None)
    if existing:
        requests.patch(f"{API}/repos/{repo}/issues/comments/{existing['id']}", headers=headers, json={"body": body}, timeout=30)
    else:
        requests.post(f"{API}/repos/{repo}/issues/{pr_number}/comments", headers=headers, json={"body": body}, timeout=30)
