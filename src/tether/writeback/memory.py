"""institutionalMemory on the column.

The incident lives on the model and gets resolved. This does not. It is a permanent record
on the column itself saying "a production model reads this, here is the PR where we found
out." That is the part that means nobody has to rediscover the dependency next quarter.
"""

from __future__ import annotations

import time

from ..datahub_client import client
from ..verdict.models import Impact, Verdict

ADD_LINK = """
mutation addLink($input: AddLinkInput!) {
  addLink(input: $input)
}
"""


def label_for(verdict: Verdict, impacts: list[Impact]) -> str:
    names = ", ".join(sorted({i.model_name for i in impacts})[:3])
    more = "" if len(impacts) <= 3 else f" +{len(impacts) - 3} more"
    return f"Tether: consumed by {names}{more}"


def record(verdict: Verdict, column_urn: str, pr_url: str) -> bool:
    """Attach the PR to the column so the dependency outlives the incident."""
    if not verdict.impacts:
        return False
    client().graphql(
        ADD_LINK,
        {
            "input": {
                "linkUrl": pr_url,
                "label": label_for(verdict, verdict.impacts),
                "resourceUrn": column_urn,
            }
        },
    )
    return True


def record_all(verdicts: list[Verdict], column_urns: dict[str, str], pr_url: str) -> int:
    """column_urns maps ColumnChange.label() -> schemaField urn."""
    n = 0
    for v in verdicts:
        urn = column_urns.get(v.change.label())
        if not urn or not v.impacts:
            continue
        try:
            if record(v, urn, pr_url):
                n += 1
        except Exception:
            # a failed link must not take the PR check down with it
            continue
        time.sleep(0.05)
    return n
