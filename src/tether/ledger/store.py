"""Append-only prediction ledger.

Every verdict Tether has ever issued, with enough context to score it later against what
actually happened. This is what makes the number a measurement of the system's judgment
rather than a count of tests written.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..config import settings
from ..verdict.models import Report


def append(report: Report, case_id: str = "", arm: str = "datahub", path: Path | None = None) -> None:
    path = path or settings.ledger_path
    with path.open("a", encoding="utf-8") as fh:
        for v in report.verdicts:
            fh.write(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "case_id": case_id,
                        "arm": arm,
                        "pr_url": report.pr_url,
                        "column": v.change.label(),
                        "kind": v.change.kind.value,
                        "predicted": v.level.value,
                        "rule_id": v.rule_id,
                        "decided_by": v.decided_by.value,
                        "models": [i.model_urn for i in v.impacts],
                    }
                )
                + "\n"
            )


def read(path: Path | None = None) -> Iterator[dict]:
    path = path or settings.ledger_path
    if not path.exists():
        return iter(())
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)
