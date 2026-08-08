from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .evaluator import evaluate
from .models import CaseOutcome


MAX_REQUEST_BYTES = 8 * 1024 * 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="axiom", description="Evaluate ordered discrete point sequences.")
    commands = parser.add_subparsers(dest="command", required=True)
    evaluate_command = commands.add_parser("evaluate", help="evaluate one JSON request")
    evaluate_command.add_argument("request", type=Path, help="path to an evaluation-request@1 JSON file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        with args.request.open("rb") as stream:
            raw_request = stream.read(MAX_REQUEST_BYTES + 1)
        if len(raw_request) > MAX_REQUEST_BYTES:
            print(f"评估请求超过 {MAX_REQUEST_BYTES} 字节限制", file=sys.stderr)
            return 2
        payload = json.loads(raw_request.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"无法读取评估请求：{exc}", file=sys.stderr)
        return 2

    report = evaluate(payload)
    print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
    if report.case_outcome is CaseOutcome.INVALID:
        return 2
    if report.case_outcome is not CaseOutcome.PASSED:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
