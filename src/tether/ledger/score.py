"""Score predictions against ground truth. Misses are first-class output, not a footnote.

Positive class = "this change breaks a production model" = predicted BLOCK.
A false negative is the expensive one: the PR merges and the model silently rots.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any


@dataclass
class Scores:
    arm: str
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    misses: list[dict[str, Any]] = field(default_factory=list)
    false_alarms: list[dict[str, Any]] = field(default_factory=list)

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def f1(self) -> float:
        d = self.precision + self.recall
        return 2 * self.precision * self.recall / d if d else 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update(
            precision=round(self.precision, 3),
            recall=round(self.recall, 3),
            f1=round(self.f1, 3),
            n=self.tp + self.fp + self.tn + self.fn,
        )
        return d


def score(predictions: list[dict], truth: dict[str, str], arm: str) -> Scores:
    """truth maps "case_id::column" -> expected level ("BLOCK" or "PASS")."""
    s = Scores(arm=arm)
    for p in predictions:
        key = f"{p['case_id']}::{p['column']}"
        expected = truth.get(key)
        if expected is None:
            continue
        predicted_block = p["predicted"] == "BLOCK"
        expected_block = expected == "BLOCK"

        if predicted_block and expected_block:
            s.tp += 1
        elif predicted_block and not expected_block:
            s.fp += 1
            s.false_alarms.append(p)
        elif not predicted_block and expected_block:
            s.fn += 1
            s.misses.append(p)
        else:
            s.tn += 1
    return s


def markdown_table(rows: list[Scores]) -> str:
    out = ["| Arm | n | Precision | Recall | F1 | Missed breakages |", "|---|---|---|---|---|---|"]
    for s in rows:
        d = s.to_dict()
        out.append(
            f"| {s.arm} | {d['n']} | {d['precision']:.0%} | {d['recall']:.0%} | "
            f"{d['f1']:.2f} | {s.fn} |"
        )
    return "\n".join(out)
