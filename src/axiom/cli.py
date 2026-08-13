from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from .comparison import compare
from .control import (
    BeckhoffWitnessDeploymentRequest,
    R7EAssessmentRequest,
    assess_beckhoff_witness_deployment,
)
from .evaluator import evaluate
from .experiment import run_experiment
from .field_evidence import FieldEvidenceAssessmentRequest, assess_field_evidence
from .models import CaseOutcome, ExecutionStatus
from .run import evaluate_run


MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_COMPARISON_BYTES = 2 * MAX_REQUEST_BYTES
MAX_EXPERIMENT_BYTES = 2 * MAX_REQUEST_BYTES
MAX_FIELD_EVIDENCE_BYTES = 2 * MAX_REQUEST_BYTES


class _CliInputError(Exception):
    def __init__(self, payload: dict[str, object]) -> None:
        super().__init__(str(payload.get("code", "MalformedInput")))
        self.payload = payload


def _validation_path(exc: ValidationError) -> str | None:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    return ".".join(str(part) for part in errors[0]["loc"]) if errors else None


def _load_r7e_assessment(path: Path, role: str) -> R7EAssessmentRequest:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise _CliInputError(
                {"code": "R7EAssessmentRequestTooLarge", "role": role}
            )
        payload = json.loads(raw.decode("utf-8"))
    except _CliInputError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _CliInputError(
            {
                "code": "UnreadableR7EAssessmentRequest",
                "role": role,
                "message": str(exc),
            }
        ) from exc
    try:
        return R7EAssessmentRequest.model_validate(payload)
    except ValidationError as exc:
        raise _CliInputError(
            {
                "code": "MalformedR7EAssessmentRequest",
                "role": role,
                "path": _validation_path(exc),
            }
        ) from exc


def _paired_field_evidence_request(
    args: argparse.Namespace,
) -> FieldEvidenceAssessmentRequest | None:
    required_pair_values = (
        args.calibration,
        args.validation,
        args.assessment_id,
        args.calibration_pair_id,
        args.validation_pair_id,
    )
    pair_values = required_pair_values + (
        args.fit_improvement_minimum,
        args.excitation_span_minimum,
        args.decomposition_tolerance,
    )
    if args.request is not None:
        if any(value is not None for value in pair_values):
            raise _CliInputError({"code": "AmbiguousFieldEvidenceInput"})
        return None
    if any(value is None for value in required_pair_values):
        raise _CliInputError({"code": "IncompleteFieldEvidencePairInput"})

    calibration = _load_r7e_assessment(args.calibration, "calibration")
    validation = _load_r7e_assessment(args.validation, "validation")
    try:
        return FieldEvidenceAssessmentRequest(
            schemaId="axiom.field-evidence-assessment-request@1",
            schemaVersion=1,
            assessmentId=args.assessment_id,
            calibrationPairId=args.calibration_pair_id,
            validationPairId=args.validation_pair_id,
            calibration=calibration,
            validation=validation,
            fitImprovementMinimum=(
                args.fit_improvement_minimum
                if args.fit_improvement_minimum is not None
                else 0.2
            ),
            excitationSpanMinimum=(
                args.excitation_span_minimum
                if args.excitation_span_minimum is not None
                else 1e-6
            ),
            decompositionTolerance=(
                args.decomposition_tolerance
                if args.decomposition_tolerance is not None
                else 1e-12
            ),
        )
    except ValidationError as exc:
        raise _CliInputError(
            {
                "code": "MalformedFieldEvidenceAssessmentRequest",
                "path": _validation_path(exc),
            }
        ) from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axiom",
        description="Evaluate domain artifacts and run reproducible Axiom experiments.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    evaluate_command = commands.add_parser("evaluate", help="evaluate one JSON request")
    evaluate_command.add_argument("request", type=Path, help="path to an evaluation-request@1 JSON file")
    run_command = commands.add_parser("run", help="execute a DomainPack RunSpec")
    run_command.add_argument("run_spec", type=Path, help="path to a run-spec@1 JSON file")
    compare_command = commands.add_parser("compare", help="compare two imported runs from one JSON spec")
    compare_command.add_argument("comparison", type=Path, help="path to a comparison-spec@1 JSON file")
    experiment_command = commands.add_parser("experiment", help="execute and compare two local Subjects")
    experiment_command.add_argument("experiment", type=Path, help="path to an experiment-spec@1 JSON file")
    field_evidence_command = commands.add_parser(
        "field-evidence",
        help="assess two Windows R7-E captures as one case-scoped R4.1 evidence set",
    )
    field_evidence_command.add_argument(
        "request",
        nargs="?",
        type=Path,
        help="path to an axiom.field-evidence-assessment-request@1 JSON file",
    )
    field_evidence_command.add_argument(
        "--calibration",
        type=Path,
        help="path to a ready R7-E calibration assessment JSON file",
    )
    field_evidence_command.add_argument(
        "--validation",
        type=Path,
        help="path to a ready R7-E validation assessment JSON file",
    )
    field_evidence_command.add_argument("--assessment-id")
    field_evidence_command.add_argument("--calibration-pair-id")
    field_evidence_command.add_argument("--validation-pair-id")
    field_evidence_command.add_argument(
        "--fit-improvement-minimum", type=float
    )
    field_evidence_command.add_argument(
        "--excitation-span-minimum", type=float
    )
    field_evidence_command.add_argument(
        "--decomposition-tolerance", type=float
    )
    deployment_command = commands.add_parser(
        "beckhoff-witness-deployment",
        help="validate a Windows TwinCAT read-only witness deployment request",
    )
    deployment_command.add_argument(
        "request",
        type=Path,
        help=(
            "path to an axiom.control.beckhoff-shadow-witness-"
            "deployment-request@1 JSON file"
        ),
    )
    serve_command = commands.add_parser("serve", help="serve the local Axiom web workbench")
    serve_command.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    serve_command.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        import uvicorn

        from .web import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port)
        return 0

    if args.command == "field-evidence":
        try:
            paired_field_request = _paired_field_evidence_request(args)
        except _CliInputError as exc:
            print(json.dumps(exc.payload, ensure_ascii=False), file=sys.stderr)
            return 2
        if paired_field_request is not None:
            report = assess_field_evidence(paired_field_request)
            print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
            return 0 if report.overall_status == "Passed" else 1

    if args.command == "evaluate":
        path, label, limit = args.request, "评估请求", MAX_REQUEST_BYTES
    elif args.command == "run":
        path, label, limit = args.run_spec, "运行请求", MAX_REQUEST_BYTES
    elif args.command == "compare":
        path, label, limit = args.comparison, "比较请求", MAX_COMPARISON_BYTES
    elif args.command == "field-evidence":
        path, label, limit = args.request, "现场证据请求", MAX_FIELD_EVIDENCE_BYTES
    elif args.command == "beckhoff-witness-deployment":
        path, label, limit = args.request, "Beckhoff 见证部署请求", MAX_REQUEST_BYTES
    else:
        path, label, limit = args.experiment, "实验请求", MAX_EXPERIMENT_BYTES
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

    if args.command == "beckhoff-witness-deployment":
        try:
            request = BeckhoffWitnessDeploymentRequest.model_validate(payload)
        except ValidationError as exc:
            errors = exc.errors(
                include_url=False, include_context=False, include_input=False
            )
            print(
                json.dumps(
                    {
                        "code": "MalformedBeckhoffWitnessDeploymentRequest",
                        "path": (
                            ".".join(str(part) for part in errors[0]["loc"])
                            if errors
                            else None
                        ),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        report = assess_beckhoff_witness_deployment(request)
        print(
            report.model_dump_json(
                indent=2, by_alias=True, exclude_none=True
            )
        )
        return 0 if report.capture_preparation_status == "Passed" else 1

    if args.command == "field-evidence":
        try:
            request = FieldEvidenceAssessmentRequest.model_validate(payload)
        except ValidationError as exc:
            print(
                json.dumps(
                    {
                        "code": "MalformedFieldEvidenceAssessmentRequest",
                        "path": _validation_path(exc),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        report = assess_field_evidence(request)
        print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
        return 0 if report.overall_status == "Passed" else 1

    if args.command == "experiment":
        try:
            report = run_experiment(payload)
        except ValidationError as exc:
            errors = exc.errors(include_url=False, include_context=False, include_input=False)
            print(
                json.dumps(
                    {
                        "code": "MalformedExperimentSpec",
                        "path": ".".join(str(part) for part in errors[0]["loc"]) if errors else None,
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
        if report.execution_status is not ExecutionStatus.SUCCEEDED:
            return 1
        if report.comparison is None or not report.comparison.compatibility.compatible:
            return 1
        return 0 if report.case_outcome is CaseOutcome.PASSED else 1

    if args.command == "run":
        bundle = evaluate_run(payload)
        print(bundle.model_dump_json(indent=2, by_alias=True, exclude_none=True))
        if bundle.report.case_outcome is CaseOutcome.INVALID:
            return 2
        return 0 if bundle.report.case_outcome is CaseOutcome.PASSED else 1

    report = evaluate(payload)
    print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
    if report.case_outcome is CaseOutcome.INVALID:
        return 2
    if report.case_outcome is not CaseOutcome.PASSED:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
