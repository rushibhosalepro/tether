"""Replay benchmark, both arms, misses included.

Each case is a directory with a `diff.patch` and an `expected.json`. Ground truth says, per
column, whether a change actually breaks a production model. Both arms see identical input.

The point of the control arm is not that it is bad. It is that dbt's graph has no ML
entities in it, so an arm restricted to the manifest cannot find a model dependency no
matter how good its traversal is. The gap between the two columns is the finding.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tether.ledger.score import Scores, markdown_table, score  # noqa: E402
from tether.pipeline import run  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = Path(__file__).with_name("results")


def load_cases(cases_dir: Path) -> list[tuple[str, str, dict]]:
    out = []
    for d in sorted(p for p in cases_dir.iterdir() if p.is_dir()):
        diff = d / "diff.patch"
        expected = d / "expected.json"
        if diff.exists() and expected.exists():
            out.append(
                (d.name, diff.read_text(encoding="utf-8"), json.loads(expected.read_text("utf-8")))
            )
    return out


def main(arms: list[str] | None = None, cases_dir: Path | None = None) -> int:
    arms = arms or ["datahub", "dbt-only"]
    cases_dir = cases_dir or (ROOT / "bench" / "cases")
    cases = load_cases(cases_dir)
    if not cases:
        print(f"no cases in {cases_dir}")
        return 1

    truth: dict[str, str] = {}
    for case_id, _, expected in cases:
        for col, level in expected["columns"].items():
            truth[f"{case_id}::{col}"] = level

    RESULTS.mkdir(exist_ok=True)
    all_scores: list[Scores] = []

    for arm in arms:
        predictions: list[dict] = []
        for case_id, diff_text, expected in cases:
            report, _ = run(diff_text, expected.get("pr_url", case_id), arm=arm, use_llm=False)
            for v in report.verdicts:
                predictions.append(
                    {
                        "case_id": case_id,
                        "column": v.change.label(),
                        "predicted": v.level.value,
                        "rule_id": v.rule_id,
                        "models": [i.model_name for i in v.impacts],
                    }
                )
            print(f"  [{arm}] {case_id}: {report.level.value}")

        s = score(predictions, truth, arm)
        all_scores.append(s)
        (RESULTS / f"arm-{arm}.json").write_text(
            json.dumps({"scores": s.to_dict(), "predictions": predictions}, indent=2),
            encoding="utf-8",
        )

    report_md = _write_report(all_scores, len(cases))
    print("\n" + markdown_table(all_scores))
    print(f"\nwrote {report_md}")

    from render_report import render  # noqa: PLC0415

    render(all_scores, RESULTS)
    return 0


def _write_report(scores: list[Scores], n_cases: int) -> Path:
    lines = [
        "# Benchmark: predicted breakage on replayed schema changes",
        "",
        f"{n_cases} real schema changes replayed against the seeded graph. Identical input to "
        "both arms. Positive class is \"this change breaks a model that is currently serving\".",
        "",
        markdown_table(scores),
        "",
    ]
    for s in scores:
        lines.append(f"## Arm: {s.arm}")
        lines.append("")
        if s.misses:
            lines.append(f"**Missed {len(s.misses)} real breakage(s):**")
            lines += [f"- `{m['column']}` in {m['case_id']} (predicted {m['predicted']})" for m in s.misses]
        else:
            lines.append("No missed breakages.")
        lines.append("")
        if s.false_alarms:
            lines.append(f"**{len(s.false_alarms)} false alarm(s):**")
            lines += [f"- `{m['column']}` in {m['case_id']}" for m in s.false_alarms]
            lines.append("")
    path = RESULTS / "REPORT.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
