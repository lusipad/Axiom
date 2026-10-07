from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from pydantic import ValidationError

from .comparison import compare
from .benchmark import CncBenchmarkCase, benchmark_case_hash, cnc_benchmark_example, compare_cnc_exports, render_report_table
from .benchmark_standard import STANDARD_CASE_NAMES, StandardCaseSettings, render_nc_program, standard_cases
from .benchmark_trace import TraceColumns, TraceImportOptions, import_controller_trace
from .control import (
    BeckhoffWitnessDeploymentRequest,
    R7EAssessmentRequest,
    assess_beckhoff_witness_deployment,
)
from .evaluator import evaluate
from .experiment import run_experiment
from .field_evidence import FieldEvidenceAssessmentRequest, assess_field_evidence
from .intelligence import (
    RealHoldoutIntakeRequest,
    assess_real_holdout_intake,
)
from .models import CaseOutcome, ExecutionStatus
from .run import evaluate_run


MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_COMPARISON_BYTES = 2 * MAX_REQUEST_BYTES
MAX_EXPERIMENT_BYTES = 2 * MAX_REQUEST_BYTES
MAX_FIELD_EVIDENCE_BYTES = 2 * MAX_REQUEST_BYTES
MAX_REAL_HOLDOUT_INTAKE_BYTES = 8 * MAX_REQUEST_BYTES


class _CliInputError(Exception):
    def __init__(self, payload: dict[str, object]) -> None:
        super().__init__(str(payload.get("code", "MalformedInput")))
        self.payload = payload


def _benchmark_json(path: Path) -> object:
    with path.open("rb") as stream:
        raw = stream.read(MAX_EXPERIMENT_BYTES + 1)
    if len(raw) > MAX_EXPERIMENT_BYTES:
        raise ValueError(f"{path.name} exceeds the {MAX_EXPERIMENT_BYTES} byte limit")
    return json.loads(raw.decode("utf-8-sig"))


def _benchmark_command(args: argparse.Namespace) -> int:
    try:
        if args.command == "benchmark-example":
            print(cnc_benchmark_example().model_dump_json(indent=2, by_alias=True, exclude_none=True))
            return 0
        if args.command == "benchmark-case-hash":
            print(benchmark_case_hash(_benchmark_json(args.case)))
            return 0
        if args.command == "benchmark-standard-cases":
            return _write_standard_cases(args)
        if args.command == "benchmark-import-trace":
            return _import_trace(args)
        paths = (args.case, args.baseline, args.candidate)
        if args.request is not None:
            if any(path is not None for path in paths):
                raise ValueError("use a request file or --case/--baseline/--candidate, not both")
            payload = _benchmark_json(args.request)
        else:
            if any(path is None for path in paths):
                raise ValueError("--case, --baseline and --candidate are all required")
            payload = {role: _benchmark_json(path) for role, path in zip(("case", "baseline", "candidate"), paths, strict=True)}
        report = compare_cnc_exports(payload)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        message = str(exc) if not isinstance(exc, ValidationError) else str(exc.errors(include_url=False, include_context=False, include_input=False))
        print(json.dumps({"code": "MalformedCncBenchmark", "message": message}, ensure_ascii=False), file=sys.stderr)
        return 2
    if args.format == "table":
        print(render_report_table(report), end="")
    else:
        print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
    return 0 if report.outcome in {"Improved", "WithinTolerance"} else 1


def _write_standard_cases(args: argparse.Namespace) -> int:
    settings = StandardCaseSettings(
        feed_mm_min=args.feed,
        sample_period_seconds=args.period,
        maximum_velocity_mm_s=args.max_velocity,
        maximum_acceleration_mm_s2=args.max_acceleration,
        maximum_jerk_mm_s3=args.max_jerk,
        maximum_path_deviation_mm=args.max_deviation,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for case in standard_cases(settings):
        if args.only and case.case_id.rsplit(".", 1)[-1] not in args.only:
            continue
        stem = case.case_id.rsplit(".", 1)[-1]
        (args.out_dir / f"{stem}.case.json").write_text(case.model_dump_json(indent=2, by_alias=True, exclude_none=True) + "\n", encoding="utf-8")
        (args.out_dir / f"{stem}.nc").write_text(render_nc_program(case, arc_format=args.arc_format, line_numbers=args.line_numbers), encoding="utf-8")
        print(f"{stem}: {stem}.case.json {stem}.nc caseContentHash={benchmark_case_hash(case)}")
    return 0


def _import_trace(args: argparse.Namespace) -> int:
    case = CncBenchmarkCase.model_validate(_benchmark_json(args.case))
    if args.trace.stat().st_size > MAX_EXPERIMENT_BYTES * 4:
        raise ValueError(f"{args.trace.name} exceeds the {MAX_EXPERIMENT_BYTES * 4} byte limit")
    options = TraceImportOptions(
        columns=TraceColumns(x=args.x, y=args.y, z=args.z, cycle=args.cycle_column, time=args.time_column, time_scale=args.time_scale),
        position_scale=args.position_scale,
        offset_mm=tuple(args.offset) if args.offset else (0.0, 0.0, 0.0),
        align_start_to_case=args.align_start,
        trim_stationary=not args.no_trim,
    )
    export = import_controller_trace(
        args.trace.read_text(encoding="utf-8-sig"),
        case,
        algorithm_id=args.algorithm_id,
        algorithm_version=args.algorithm_version,
        options=options,
    )
    text = export.model_dump_json(indent=2, by_alias=True, exclude_none=True) + "\n"
    if args.out is None:
        print(text, end="")
    else:
        args.out.write_text(text, encoding="utf-8")
        print(f"{args.out}: {len(export.samples)} samples, {export.samples[-1].t:.6g} s", file=sys.stderr)
    return 0


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


def _assembled_real_holdout_intake_request(
    args: argparse.Namespace,
) -> RealHoldoutIntakeRequest | None:
    assembled_values = (
        args.base_run_spec,
        args.governance,
        *(args.cases or ()),
        args.intake_id,
        args.holdout_set_id,
        args.selection_id,
    )
    if args.request is not None:
        if any(value is not None for value in assembled_values):
            raise _CliInputError({"code": "AmbiguousRealHoldoutIntakeInput"})
        return None
    if args.base_run_spec is None or args.governance is None or not args.cases:
        raise _CliInputError({"code": "IncompleteRealHoldoutIntakeInput"})

    paths = (
        ("baseRunSpec", args.base_run_spec, MAX_REQUEST_BYTES),
        ("governance", args.governance, MAX_REQUEST_BYTES),
        *(
            (f"cases[{index}]", path, MAX_FIELD_EVIDENCE_BYTES)
            for index, path in enumerate(args.cases)
        ),
    )
    payloads: dict[str, object] = {}
    case_payloads: list[object] = []
    total_size = 0
    for role, path, limit in paths:
        try:
            with path.open("rb") as stream:
                raw = stream.read(limit + 1)
            if len(raw) > limit:
                raise _CliInputError(
                    {"code": "RealHoldoutIntakeInputTooLarge", "role": role}
                )
            total_size += len(raw)
            if total_size > MAX_REAL_HOLDOUT_INTAKE_BYTES:
                raise _CliInputError(
                    {"code": "RealHoldoutIntakeInputTooLarge", "role": "combined"}
                )
            payload = json.loads(raw.decode("utf-8"))
        except _CliInputError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _CliInputError(
                {
                    "code": "UnreadableRealHoldoutIntakeInput",
                    "role": role,
                    "message": str(exc),
                }
            ) from exc
        if role.startswith("cases["):
            case_payloads.append(payload)
        else:
            payloads[role] = payload

    try:
        return RealHoldoutIntakeRequest.model_validate(
            {
                "schemaId": "axiom.intelligence.real-holdout-intake-request@1",
                "schemaVersion": 1,
                "intakeId": args.intake_id or "field.real-holdout-intake@1",
                "holdoutSetId": args.holdout_set_id or "field.real-holdout-set@1",
                "selectionId": args.selection_id or "field.real-holdout-selection@1",
                "selectedBeforeEvaluation": True,
                "baseRunSpec": payloads["baseRunSpec"],
                "governance": payloads["governance"],
                "cases": case_payloads,
            }
        )
    except ValidationError as exc:
        raise _CliInputError(
            {
                "code": "MalformedRealHoldoutIntakeRequest",
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
    intake_command = commands.add_parser(
        "real-holdout-intake",
        help="project Windows field evidence into one R5-B real holdout RunSpec",
    )
    intake_command.add_argument(
        "request",
        nargs="?",
        type=Path,
        help=(
            "path to an axiom.intelligence.real-holdout-intake-request@1 JSON file"
        ),
    )
    intake_command.add_argument("--base-run-spec", type=Path)
    intake_command.add_argument("--governance", type=Path)
    intake_command.add_argument("--case", action="append", dest="cases", type=Path)
    intake_command.add_argument("--intake-id")
    intake_command.add_argument("--holdout-set-id")
    intake_command.add_argument("--selection-id")
    benchmark_command = commands.add_parser("benchmark", help="compare two exported XYZ command traces under one frozen case")
    benchmark_command.add_argument("request", nargs="?", type=Path)
    benchmark_command.add_argument("--case", type=Path)
    benchmark_command.add_argument("--baseline", type=Path)
    benchmark_command.add_argument("--candidate", type=Path)
    benchmark_command.add_argument("--format", choices=("json", "table"), default="json", help="json report (default) or a readable A/B table")
    standard_command = commands.add_parser("benchmark-standard-cases", help="write the five V1 standard cases and their NC programs")
    standard_command.add_argument("--out-dir", type=Path, required=True)
    standard_command.add_argument("--only", nargs="+", choices=STANDARD_CASE_NAMES)
    standard_command.add_argument("--feed", type=float, default=3000.0, help="programmed feed in mm/min (default: 3000)")
    standard_command.add_argument("--period", type=float, default=0.001, help="trace sample period in seconds (default: 0.001)")
    standard_command.add_argument("--arc-format", choices=("IJK", "R"), default="IJK")
    standard_command.add_argument("--line-numbers", action="store_true")
    standard_command.add_argument("--max-velocity", type=float, default=500.0, help="axis velocity limit in mm/s")
    standard_command.add_argument("--max-acceleration", type=float, default=5000.0, help="axis acceleration limit in mm/s^2")
    standard_command.add_argument("--max-jerk", type=float, default=500000.0, help="axis jerk limit in mm/s^3")
    standard_command.add_argument("--max-deviation", type=float, default=0.05, help="allowed contour deviation in mm")
    import_command = commands.add_parser("benchmark-import-trace", help="convert a controller trace CSV into a benchmark export")
    import_command.add_argument("trace", type=Path)
    import_command.add_argument("--case", type=Path, required=True)
    import_command.add_argument("--algorithm-id", required=True)
    import_command.add_argument("--algorithm-version", required=True)
    import_command.add_argument("--x", default="X", help="X position column (default: X)")
    import_command.add_argument("--y", default="Y", help="Y position column (default: Y)")
    import_command.add_argument("--z", default="Z", help="Z position column (default: Z)")
    clock = import_command.add_mutually_exclusive_group(required=True)
    clock.add_argument("--cycle-column", help="interpolation cycle counter column")
    clock.add_argument("--time-column", help="timestamp column")
    import_command.add_argument("--time-scale", type=float, default=1.0, help="seconds per time unit, e.g. 0.001 for ms")
    import_command.add_argument("--position-scale", type=float, default=1.0, help="mm per position unit, e.g. 0.001 for um")
    import_command.add_argument("--offset", type=float, nargs=3, metavar=("X", "Y", "Z"), help="subtract this offset (mm) to reach the case frame")
    import_command.add_argument("--align-start", action="store_true", help="shift the trace so its first sample is the case start")
    import_command.add_argument("--no-trim", action="store_true", help="keep stationary samples before and after motion")
    import_command.add_argument("--out", type=Path)
    hash_command = commands.add_parser("benchmark-case-hash", help="print the canonical case hash to bind algorithm exports")
    hash_command.add_argument("case", type=Path)
    commands.add_parser("benchmark-example", help="print an explicitly synthetic CNC comparison request")
    serve_command = commands.add_parser("serve", help="serve the local Axiom web workbench")
    serve_command.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    serve_command.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in {"benchmark", "benchmark-case-hash", "benchmark-example", "benchmark-standard-cases", "benchmark-import-trace"}:
        return _benchmark_command(args)
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

    if args.command == "real-holdout-intake":
        try:
            assembled_intake_request = _assembled_real_holdout_intake_request(args)
        except _CliInputError as exc:
            print(json.dumps(exc.payload, ensure_ascii=False), file=sys.stderr)
            return 2
        if assembled_intake_request is not None:
            report = assess_real_holdout_intake(assembled_intake_request)
            print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
            return 0 if report.intake_status == "Passed" else 1

    if args.command == "evaluate":
        path, label, limit = args.request, "评估请求", MAX_REQUEST_BYTES
    elif args.command == "run":
        path, label, limit = args.run_spec, "运行请求", MAX_REQUEST_BYTES
    elif args.command == "compare":
        path, label, limit = args.comparison, "比较请求", MAX_COMPARISON_BYTES
    elif args.command == "field-evidence":
        path, label, limit = args.request, "现场证据请求", MAX_FIELD_EVIDENCE_BYTES
    elif args.command == "real-holdout-intake":
        path, label, limit = (
            args.request,
            "真实 holdout intake 请求",
            MAX_REAL_HOLDOUT_INTAKE_BYTES,
        )
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

    if args.command == "real-holdout-intake":
        try:
            request = RealHoldoutIntakeRequest.model_validate(payload)
        except ValidationError as exc:
            print(
                json.dumps(
                    {
                        "code": "MalformedRealHoldoutIntakeRequest",
                        "path": _validation_path(exc),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        report = assess_real_holdout_intake(request)
        print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
        return 0 if report.intake_status == "Passed" else 1

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
