from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import settings
from .verdict.models import Level

EXIT_BLOCK = 1


def cmd_check(args) -> int:
    from .ledger import store
    from .pipeline import run, write_back
    from .writeback.github_check import summary_markdown

    diff_text = Path(args.diff).read_text(encoding="utf-8") if args.diff else sys.stdin.read()
    # a real run (not dry) repairs on a miss: that is the loop, in the product not just the bench
    report, column_urns = run(
        diff_text, args.pr_url, arm=args.arm, use_llm=not args.no_llm, repair=not args.dry_run
    )

    result = {"incidents": [], "incident_links": [], "check_url": None}
    if not args.dry_run:
        result = write_back(report, column_urns, args.pr_url)
        store.append(report, case_id=args.case_id, arm=args.arm)

    if args.json:
        print(json.dumps({**report.to_dict(), **result}, indent=2))
    else:
        print(f"tether: {report.level.value}")
        print(summary_markdown(report, result.get("incident_links") or []))

    # fail closed: red on a real block AND when Tether could not verify
    return EXIT_BLOCK if report.fails_check else 0


def cmd_seed(args) -> int:
    from seed.emit_ml_layer import main as emit  # noqa: PLC0415

    return emit(dry_run=args.dry_run)


def cmd_bench(args) -> int:
    from bench.run_bench import main as bench  # noqa: PLC0415

    return bench()


def cmd_demo(args) -> int:
    """Play the whole loop offline, no DataHub: cold PASS -> repair -> warm BLOCK.

    Runs the same `tether check` twice against recorded fixtures, once against the cold graph
    (the edge nobody declared) and once against the warm graph (after Tether wrote it back).
    """
    import os
    import subprocess

    diff = "bench/cases/001-drop-orders-discount-pct/diff.patch"
    root = Path(__file__).resolve().parents[2]

    def check(fixture_set: str) -> str:
        env = {**os.environ, "DEMO_MODE": "1", "TETHER_FIXTURE_SET": fixture_set,
               "TETHER_NO_LLM": "1", "PYTHONPATH": str(root / "src")}
        out = subprocess.run(
            [sys.executable, "-m", "tether.cli", "check", "--diff", diff, "--pr-url", "demo", "--dry-run"],
            cwd=root, env=env, capture_output=True, text=True,
        ).stdout
        return "BLOCK" if "BLOCK" in out.split("\n")[0] else "PASS"

    print("Tether loop, replayed offline (no DataHub needed)\n")
    print("The same PR, dropping orders.discount_pct, judged twice.\n")

    cold = check("cold")
    print(f"  COLD    drop orders.discount_pct   ->  {cold}   (no one declared the edge, so the walk misses)")
    print("  REPAIR  discount_sensitivity <- orders   proven from features/discount_sensitivity.sql:5")
    warm = check("warm")
    print(f"  WARM    drop orders.discount_pct   ->  {warm}  churn_propensity_v4, owner @aman\n")

    ok = cold == "PASS" and warm == "BLOCK"
    print("The write-back is what flipped the verdict. That is the loop." if ok else "(unexpected: check fixtures)")
    return 0 if ok else 1


def cmd_doctor(args) -> int:
    from .datahub_client import client

    ok = client().health()
    print(f"GMS       {settings.gms_url}  {'up' if ok else 'UNREACHABLE'}")
    print(f"frontend  {settings.frontend_url}")
    print(f"demo mode {'on' if settings.demo_mode else 'off'}")
    print(f"token     {'set' if settings.token else 'missing (fine on quickstart)'}")
    return 0 if ok or settings.demo_mode else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("tether", description="Block the PR that breaks the model.")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="run against a diff and write back")
    c.add_argument("--diff", help="path to a unified diff, or stdin")
    c.add_argument("--pr-url", default="local")
    c.add_argument("--arm", default="datahub", choices=["datahub", "dbt-only"])
    c.add_argument("--case-id", default="")
    c.add_argument("--dry-run", action="store_true", help="classify but write nothing")
    c.add_argument("--no-llm", action="store_true")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("seed", help="emit the ML layer onto showcase-ecommerce")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_seed)

    b = sub.add_parser("bench", help="run the cold->repair->warm benchmark (needs live DataHub)")
    b.set_defaults(func=cmd_bench)

    dm = sub.add_parser("demo", help="play the loop offline from fixtures, no DataHub needed")
    dm.set_defaults(func=cmd_demo)

    d = sub.add_parser("doctor", help="check the local setup")
    d.set_defaults(func=cmd_doctor)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
