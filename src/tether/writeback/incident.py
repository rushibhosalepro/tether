"""raiseIncident on the ML model.

This is the write-back that matters most. After Tether runs, the model's own page in
DataHub carries an open incident that names the PR, the column, and the owner. The next
person to look at that model inherits the finding without ever having seen the PR.

Incidents are OSS-available over GraphQL. There is no Python SDK for them yet (the docs say
"coming soon"), which is why this module exists and why it is worth offering upstream.
"""

from __future__ import annotations

from ..config import settings
from ..datahub_client import client
from ..verdict.models import Impact, Verdict

RAISE = """
mutation raise($input: RaiseIncidentInput!) {
  raiseIncident(input: $input)
}
"""

EXISTING = """
query openIncidents($urn: String!) {
  entity(urn: $urn) {
    ... on MLModel {
      incidents(start: 0, count: 50) {
        incidents { urn title status { state } }
      }
    }
  }
}
"""


def title_for(verdict: Verdict, impact: Impact) -> str:
    return f"Schema change blocks {impact.model_name}: {verdict.change.label()}"


def description_for(verdict: Verdict, impact: Impact, pr_url: str) -> str:
    owners = ", ".join(impact.owners) or "no owner recorded"
    return "\n".join(
        [
            f"**{verdict.change.kind.value}** on `{verdict.change.label()}` proposed in {pr_url}.",
            "",
            f"{verdict.reason}",
            "",
            f"- Model: `{impact.model_urn}`",
            f"- Feature: `{impact.feature_urn or 'direct dataset dependency'}`",
            f"- Deployment: `{impact.deployment_urn or 'none'}` ({impact.deployment_status or 'not deployed'})",
            f"- Last trained: {impact.last_trained or 'unknown'}",
            f"- Owners: {owners}",
            f"- Rule: `{verdict.rule_id}`, decided by `{verdict.decided_by.value}`",
            "",
            "Raised automatically by Tether. Resolve this incident once the model has been "
            "retrained without the column, or the change has been withdrawn.",
        ]
    )


def already_open(model_urn: str, title: str) -> str | None:
    try:
        data = client().graphql(EXISTING, {"urn": model_urn})
    except Exception:
        return None
    entity = data.get("entity") or {}
    for inc in ((entity.get("incidents") or {}).get("incidents") or []):
        if inc.get("title") == title and (inc.get("status") or {}).get("state") == "ACTIVE":
            return inc["urn"]
    return None


def raise_for(verdict: Verdict, impact: Impact, pr_url: str) -> str:
    """Idempotent: re-running on the same PR does not spam the model page."""
    title = title_for(verdict, impact)
    existing = already_open(impact.model_urn, title)
    if existing:
        return existing

    data = client().graphql(
        RAISE,
        {
            "input": {
                "type": "DATA_SCHEMA",
                "title": title,
                "description": description_for(verdict, impact, pr_url),
                "resourceUrns": [impact.model_urn],
                "priority": 0 if impact.is_live else 2,
                "source": {"type": "MANUAL"},
            }
        },
    )
    return data["raiseIncident"]


def raise_all(verdicts: list[Verdict], pr_url: str) -> list[str]:
    from ..verdict.models import Level

    urns = []
    for v in verdicts:
        if v.level is not Level.BLOCK:
            continue
        for impact in v.impacts:
            urns.append(raise_for(v, impact, pr_url))
    return urns


def incident_link(urn: str) -> str:
    return f"{settings.frontend_url}/incident/{urn}"
