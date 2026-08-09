"""Repair the gaps diagnose found: write the proven edges, refuse and log the rest.

The gate is the whole point. Tether writes a lineage edge only when it can point at a SQL
expression for it. A feature computed in Python, with no SQL to cite, is refused, and the
refusal is recorded and published rather than hidden. That refusal is Tether's honest failure
number, framed as a virtue: it does not guess at the graph.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import settings
from ..writeback.lineage import write_source_edge
from .diagnose import LineageGap

# runtime output belongs next to the ledger (repo root / configurable), never in the package dir
REFUSALS = settings.ledger_path.with_name("refusals.jsonl")


@dataclass
class RepairResult:
    repaired: list[str]   # "feature <- dataset (evidence)"
    refused: list[str]    # "feature: reason"


def repair(gaps: list[LineageGap], dry_run: bool = False) -> RepairResult:
    repaired: list[str] = []
    refused: list[str] = []

    for gap in gaps:
        if not gap.provable:
            reason = f"{gap.feature}: no SQL expression to prove the {gap.column} dependency"
            refused.append(reason)
            _log_refusal(gap, reason)
            continue
        if not dry_run:
            write_source_edge(gap.feature_urn, gap.dataset_urn, gap.evidence)
        repaired.append(f"{gap.feature} <- {gap.dataset_urn.split(',')[-2]} ({gap.evidence})")

    return RepairResult(repaired=repaired, refused=refused)


def _log_refusal(gap: LineageGap, reason: str) -> None:
    with REFUSALS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**asdict(gap), "reason": reason}) + "\n")
