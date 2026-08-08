from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .comparison import compare
from .evaluator import evaluate
from .models import CaseOutcome


MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_COMPARISON_BYTES = 2 * MAX_REQUEST_BYTES


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axiom",
        description="Evaluate and compare ordered discrete point sequences.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    evaluate_command = commands.add_parser("evaluate", help="evaluate one JSON request")
    evaluate_command.add_argument("request", type=Path, help="path to an evaluation-request@1 JSON file")
    compare_command = commands.add_parser("compare", help="compare two imported runs from one JSON spec")
    compare_command.add_argument("comparison", type=Path, help="path to a comparison-spec@1 JSON file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    path = args.request if args.command == "evaluate" else args.comparison
    label = "评估请求" if args.command == "evaluate" else "比较请求"
    limit = MAX_REQUEST_BYTES if args.command == "evaluate" else MAX_COMPARISON_BYTES
    try:
        with path.open("rb") as stream:
            raw_request = stream.read(limit + 1)
        if len(raw_request) > limit:
            print(f"{label}超过 {limit} 字节限制", file=sys.stderr)
            return 2
        payload = json.loads(raw_request.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"无法读取{label}：{exc}", file=sys.stderr)
        return 2

    if args.command == "compare":
        report = compare(payload)
        print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
        if any(issue.code == "MalformedComparisonSpec" for issue in report.compatibility.issues):
            return 2
        return 0 if report.compatibility.compatible else 1

    report = evaluate(payload)
    print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
    if report.case_outcome is CaseOutcome.INVALID:
        return 2
    if report.case_outcome is not CaseOutcome.PASSED:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
