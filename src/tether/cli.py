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
    report, column_urns = run(diff_text, args.pr_url, arm=args.arm, use_llm=not args.no_llm)

    result = {"incidents": [], "check_url": None}
    if not args.dry_run:
        result = write_back(report, column_urns, args.pr_url)
        store.append(report, case_id=args.case_id, arm=args.arm)

    if args.json:
        print(json.dumps({**report.to_dict(), **result}, indent=2))
    else:
        print(f"tether: {report.level.value}")
        print(summary_markdown(report, result.get("incidents") or []))

    return EXIT_BLOCK if report.level is Level.BLOCK else 0


def cmd_seed(args) -> int:
    from seed.emit_ml_layer import main as emit  # noqa: PLC0415

    return emit(dry_run=args.dry_run)


def cmd_bench(args) -> int:
    from bench.run_bench import main as bench  # noqa: PLC0415

    return bench()


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

    b = sub.add_parser("bench", help="run the cold->repair->warm benchmark")
    b.set_defaults(func=cmd_bench)

    d = sub.add_parser("doctor", help="check the local setup")
    d.set_defaults(func=cmd_doctor)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
