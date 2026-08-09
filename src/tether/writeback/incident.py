"""raiseIncident for a schema change that threatens a production model.

The incident is filed on the affected **dataset** (the table being changed), not the model,
and this is deliberate: OSS DataHub exposes `incidents` on `Dataset` but not on `MLModel`, so
an incident raised on a model is created but never rendered in the UI. Filing it on the table
means the next engineer who opens that table sees it, and the model it endangers is named in
the incident title and body. The finding is inherited by whoever touches the column next.

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


def _cache_path():
    from ..config import settings

    return settings.ledger_path.with_name(".incidents_raised.json")


def already_open(model_urn: str, title: str) -> str | None:
    """OSS GraphQL does not expose an entity's incidents, so idempotency is tracked locally.

    Keyed on model + title, so re-running Tether on the same PR does not spam the model page.
    """
    import json

    path = _cache_path()
    if not path.exists():
        return None
    cache = json.loads(path.read_text(encoding="utf-8"))
    return cache.get(f"{model_urn}|{title}")


def _remember(model_urn: str, title: str, incident_urn: str) -> None:
    import json

    path = _cache_path()
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    cache[f"{model_urn}|{title}"] = incident_urn
    path.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _dataset_of(schema_field_urn: str) -> str:
    """schemaField urn embeds its dataset: urn:li:schemaField:(<dataset_urn>,<col>)."""
    inner = schema_field_urn[len("urn:li:schemaField:("):]
    return inner[: inner.rfind(",")]


def raise_for(verdict: Verdict, impact: Impact, pr_url: str, dataset_urn: str) -> str:
    """File the incident on the dataset (where OSS renders it). Idempotent on dataset + title."""
    title = title_for(verdict, impact)
    existing = already_open(dataset_urn, title)
    if existing:
        return existing

    data = client().graphql(
        RAISE,
        {
            "input": {
                "type": "DATA_SCHEMA",
                "title": title,
                "description": description_for(verdict, impact, pr_url),
                "resourceUrns": [dataset_urn],
                "priority": "CRITICAL" if impact.is_live else "MEDIUM",
            }
        },
    )
    incident_urn = data["raiseIncident"]
    _remember(dataset_urn, title, incident_urn)
    return incident_urn


def raise_all(verdicts: list[Verdict], pr_url: str, column_urns: dict[str, str]) -> list[str]:
    from ..verdict.models import Level

    urns = []
    for v in verdicts:
        if v.level is not Level.BLOCK:
            continue
        schema_field = column_urns.get(v.change.label())
        if not schema_field:
            continue
        dataset_urn = _dataset_of(schema_field)
        for impact in v.impacts:
            urns.append(raise_for(v, impact, pr_url, dataset_urn))
    return urns


def incident_link_for_dataset(dataset_urn: str) -> str:
    """Datasets render their incidents in the OSS UI; link there, not to a bare incident URN."""
    return f"{settings.frontend_url}/dataset/{dataset_urn}/Incidents"
