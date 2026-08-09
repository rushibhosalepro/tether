"""The benchmark: cold -> repair -> warm, on the live graph, one command.

Three passes over the same cases:
  1. COLD   reseed the partial graph, classify every case, score it
  2. REPAIR diagnose each miss and write back the edges Tether can prove from SQL
  3. WARM   classify every case again against the repaired graph, score it

The delta between pass 1 and pass 3 is the whole submission. Delete the repair pass and warm
equals cold. Writes bench/results/REPORT.md and examples/report.html.

Run: `python bench/run_bench.py`  (needs a live DataHub with the seed loaded)
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tether.graph.resolve import resolve_dataset  # noqa: E402
from tether.pipeline import run  # noqa: E402
from tether.repair.diagnose import diagnose  # noqa: E402
from tether.repair.emit import repair  # noqa: E402
from tether.verdict.models import Level  # noqa: E402

CASES = yaml.safe_load((ROOT / "bench" / "cases.yaml").read_text(encoding="utf-8"))["cases"]
RESULTS = ROOT / "bench" / "results"
INDEX_WAIT = 9  # seconds for DataHub to index after a reseed / repair


@dataclass
class CaseResult:
    table: str
    column: str
    expected: str
    cold: str = ""
    warm: str = ""
    provable: bool = True

    @property
    def label(self) -> str:
        return f"{self.table.split('.')[-1]}.{self.column}"

    def correct(self, phase: str) -> bool:
        return getattr(self, phase) == self.expected


@dataclass
class Score:
    phase: str
    results: list[CaseResult] = field(default_factory=list)

    @property
    def breakages(self) -> list[CaseResult]:
        return [r for r in self.results if r.expected == "BLOCK"]

    @property
    def caught(self) -> int:
        return sum(1 for r in self.breakages if getattr(r, self.phase) == "BLOCK")

    @property
    def missed(self) -> int:
        return len(self.breakages) - self.caught

    @property
    def correct(self) -> int:
        return sum(1 for r in self.results if r.correct(self.phase))


def _diff_for(table: str, column: str) -> str:
    """Synthesize the unified diff that drops one column from its model file."""
    model = table.split(".")[-1]
    return (
        f"diff --git a/demo/warehouse/models/{model}.sql b/demo/warehouse/models/{model}.sql\n"
        f"--- a/demo/warehouse/models/{model}.sql\n"
        f"+++ b/demo/warehouse/models/{model}.sql\n"
        f"@@ -1,4 +1,3 @@\n"
        f" select\n"
        f"-    {column},\n"
        f"     other_col\n"
        f" from {table}\n"
    )


def classify_case(c: dict) -> str:
    diff = _diff_for(c["table"], c["column"])
    report, _ = run(diff, pr_url="bench", arm="datahub", use_llm=False)
    return report.level.value


def reseed_partial() -> None:
    subprocess.run([sys.executable, "-m", "seed.emit_ml_layer", "--partial"], cwd=ROOT, check=True,
                   capture_output=True)
    time.sleep(INDEX_WAIT)


def main() -> int:
    results = [
        CaseResult(c["table"], c["column"], c["expected"], provable=c.get("provable", True))
        for c in CASES
    ]

    print("PASS 1 (cold): reseeding partial graph...")
    reseed_partial()
    from tether.graph.resolve import resolve_dataset as _r  # bust lru cache across reseeds
    _r.cache_clear()
    for r in results:
        r.cold = classify_case({"table": r.table, "column": r.column})
        print(f"  {r.label:24} expected={r.expected:5} cold={r.cold}")

    print("\nPASS 2 (repair): diagnosing and repairing misses...")
    repaired, refused = [], []
    for r in results:
        if r.cold == "BLOCK" or r.expected != "BLOCK":
            continue
        gaps = diagnose(r.table, r.column)
        res = repair(gaps)
        repaired += res.repaired
        refused += res.refused
    for line in repaired:
        print(f"  repaired: {line}")
    for line in refused:
        print(f"  refused:  {line}")
    time.sleep(INDEX_WAIT)

    print("\nPASS 3 (warm): reclassifying against the repaired graph...")
    _r.cache_clear()
    for r in results:
        r.warm = classify_case({"table": r.table, "column": r.column})
        print(f"  {r.label:24} expected={r.expected:5} warm={r.warm}")

    cold, warm = Score("cold", results), Score("warm", results)
    _write_report(cold, warm, repaired, refused)
    _render_html(cold, warm)

    print("\n=== RESULT ===")
    print(f"breakages caught: cold {cold.caught}/{len(cold.breakages)}  ->  warm {warm.caught}/{len(warm.breakages)}")
    print(f"correct verdicts: cold {cold.correct}/{len(results)}  ->  warm {warm.correct}/{len(results)}")
    print(f"edges repaired: {len(repaired)}   refused: {len(refused)}")
    return 0


def _write_report(cold: Score, warm: Score, repaired: list[str], refused: list[str]) -> None:
    RESULTS.mkdir(exist_ok=True)
    lines = [
        "# Benchmark: detection before vs after the repair loop",
        "",
        "Same cases, same code, live graph. The only difference between the two columns is whether",
        "Tether repaired the lineage edges it found missing.",
        "",
        f"**Breakages caught: cold {cold.caught}/{len(cold.breakages)} -> warm {warm.caught}/{len(warm.breakages)}.** "
        f"Repaired {len(repaired)} edges, refused {len(refused)}.",
        "",
        "| Column | Expected | Cold | After repair |",
        "|---|---|---|---|",
    ]
    for r in warm.results:
        cold_ok = "✅" if r.correct("cold") else "❌"
        warm_ok = "✅" if r.correct("warm") else "❌"
        note = "" if r.provable else " (Python, refused)"
        lines.append(f"| `{r.label}`{note} | {r.expected} | {r.cold} {cold_ok} | {r.warm} {warm_ok} |")
    lines += ["", "## Edges repaired", ""]
    lines += [f"- {r}" for r in repaired] or ["- none"]
    lines += ["", "## Refused (no SQL to prove the edge)", ""]
    lines += [f"- {r}" for r in refused] or ["- none"]
    (RESULTS / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nwrote {RESULTS / 'REPORT.md'}")


def _render_html(cold: Score, warm: Score) -> None:
    try:
        from render_report import render

        render(cold, warm, RESULTS)
    except Exception as exc:
        print(f"(html report skipped: {exc})")


if __name__ == "__main__":
    raise SystemExit(main())
