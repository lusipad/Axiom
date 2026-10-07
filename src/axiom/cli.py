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
from .intelligence import (
    PreregisteredRealHoldoutIntakeRequest,
    R5IMonitoringWindowRequest,
    R5IPromotionPreflightRequest,
    R5IRollbackRequest,
    RealHoldoutCampaignRegistrationRequest,
    RealHoldoutIntakeRequest,
    apply_r5i_promotion_transaction,
    apply_r5i_rollback_transaction,
    assess_r5i_monitoring_window,
    assess_preregistered_real_holdout_intake,
    assess_real_holdout_intake,
    predict_r5i_active_model,
    preflight_r5i_model_promotion,
    read_r5i_registry_status,
    register_real_holdout_campaign,
)
from .models import CaseOutcome, ExecutionStatus
from .run import evaluate_run


MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_COMPARISON_BYTES = 2 * MAX_REQUEST_BYTES
MAX_EXPERIMENT_BYTES = 2 * MAX_REQUEST_BYTES
MAX_FIELD_EVIDENCE_BYTES = 2 * MAX_REQUEST_BYTES
MAX_REAL_HOLDOUT_INTAKE_BYTES = 8 * MAX_REQUEST_BYTES
MAX_R5I_LIFECYCLE_BYTES = 8 * MAX_REQUEST_BYTES
MAX_AUTHORITY_KEY_BYTES = 4096


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


def _read_json_file(path: Path, *, limit: int, label: str) -> object:
    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise _CliInputError({"code": f"{label}TooLarge"})
        return json.loads(raw.decode("utf-8"))
    except _CliInputError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _CliInputError(
            {"code": f"Unreadable{label}", "message": str(exc)}
        ) from exc


def _read_authority_key(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            key = stream.read(MAX_AUTHORITY_KEY_BYTES + 1)
    except OSError as exc:
        raise _CliInputError(
            {"code": "UnreadableR5IAuthorityKey", "message": str(exc)}
        ) from exc
    if not 16 <= len(key) <= MAX_AUTHORITY_KEY_BYTES:
        raise _CliInputError({"code": "InvalidR5IAuthorityKeyLength"})
    return key


def _r5i_authority_keys(request: object, key_file: Path) -> dict[str, bytes]:
    key_id = getattr(
        getattr(request, "promotion_decision", request),
        "authority_key_id",
        None,
    )
    if not isinstance(key_id, str):
        raise _CliInputError({"code": "MissingR5IAuthorityKeyId"})
    return {key_id: _read_authority_key(key_file)}


def _handle_r5i_lifecycle(args: argparse.Namespace) -> int:
    action = args.lifecycle_action
    try:
        if action == "status":
            result = read_r5i_registry_status(args.registry)
            print(result.model_dump_json(indent=2, by_alias=True, exclude_none=True))
            return 0
        if action == "predict":
            result = predict_r5i_active_model(
                args.registry,
                feed_override=args.feed_override,
                sample_period=args.sample_period,
            )
            print(result.model_dump_json(indent=2, by_alias=True, exclude_none=True))
            return 0 if result.status == "Predicted" else 1

        payload = _read_json_file(
            args.request,
            limit=MAX_R5I_LIFECYCLE_BYTES,
            label="R5ILifecycleRequest",
        )
        if action in {"preflight", "promote"}:
            request = R5IPromotionPreflightRequest.model_validate(payload)
            keys = _r5i_authority_keys(request, args.authority_key_file)
            if action == "preflight":
                result = preflight_r5i_model_promotion(
                    request,
                    authority_keys=keys,
                )
                print(
                    result.model_dump_json(
                        indent=2, by_alias=True, exclude_none=True
                    )
                )
                return 0 if result.overall_status == "Passed" else 1
            result = apply_r5i_promotion_transaction(
                args.registry,
                request,
                authority_keys=keys,
                event_id=args.event_id,
                activated_at=args.activated_at,
                expected_generation=args.expected_generation,
            )
        elif action == "monitor":
            request = R5IMonitoringWindowRequest.model_validate(payload)
            result = assess_r5i_monitoring_window(args.registry, request)
        else:
            request = R5IRollbackRequest.model_validate(payload)
            result = apply_r5i_rollback_transaction(
                args.registry,
                request,
                authority_keys=_r5i_authority_keys(
                    request,
                    args.authority_key_file,
                ),
                event_id=args.event_id,
            )
        print(result.model_dump_json(indent=2, by_alias=True, exclude_none=True))
        if action == "monitor":
            return 0 if result.monitoring_status == "Healthy" else 1
        return 0
    except ValidationError as exc:
        print(
            json.dumps(
                {
                    "code": "MalformedR5ILifecycleRequest",
                    "path": _validation_path(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except _CliInputError as exc:
        print(json.dumps(exc.payload, ensure_ascii=False), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(
            json.dumps(
                {"code": "R5ILifecycleBlocked", "message": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


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
    campaign_command = commands.add_parser(
        "real-holdout-campaign",
        help="freeze and externally register an R5-B field campaign before capture",
    )
    campaign_command.add_argument(
        "request",
        type=Path,
        help=(
            "path to an axiom.intelligence.real-holdout-campaign-"
            "registration-request@1 JSON file"
        ),
    )
    lifecycle_command = commands.add_parser(
        "model-lifecycle",
        help="inspect or mutate the local Windows R5-I model registry",
    )
    lifecycle_actions = lifecycle_command.add_subparsers(
        dest="lifecycle_action",
        required=True,
    )
    lifecycle_status = lifecycle_actions.add_parser(
        "status",
        help="read the local registry status without creating it",
    )
    lifecycle_status.add_argument("--registry", required=True, type=Path)
    lifecycle_predict = lifecycle_actions.add_parser(
        "predict",
        help="run read-only inference with the active local model",
    )
    lifecycle_predict.add_argument("--registry", required=True, type=Path)
    lifecycle_predict.add_argument("--feed-override", required=True, type=float)
    lifecycle_predict.add_argument("--sample-period", required=True, type=float)
    lifecycle_preflight = lifecycle_actions.add_parser(
        "preflight",
        help="verify a signed promotion request without writing the registry",
    )
    lifecycle_preflight.add_argument("request", type=Path)
    lifecycle_preflight.add_argument(
        "--authority-key-file",
        required=True,
        type=Path,
    )
    lifecycle_promote = lifecycle_actions.add_parser(
        "promote",
        help="atomically activate a preflight-approved candidate model",
    )
    lifecycle_promote.add_argument("request", type=Path)
    lifecycle_promote.add_argument("--registry", required=True, type=Path)
    lifecycle_promote.add_argument(
        "--authority-key-file",
        required=True,
        type=Path,
    )
    lifecycle_promote.add_argument("--event-id", required=True)
    lifecycle_promote.add_argument("--activated-at", required=True)
    lifecycle_promote.add_argument(
        "--expected-generation",
        required=True,
        type=int,
    )
    lifecycle_monitor = lifecycle_actions.add_parser(
        "monitor",
        help="evaluate and persist one active-model monitoring window",
    )
    lifecycle_monitor.add_argument("request", type=Path)
    lifecycle_monitor.add_argument("--registry", required=True, type=Path)
    lifecycle_rollback = lifecycle_actions.add_parser(
        "rollback",
        help="explicitly roll back after a persisted RollbackRequired window",
    )
    lifecycle_rollback.add_argument("request", type=Path)
    lifecycle_rollback.add_argument("--registry", required=True, type=Path)
    lifecycle_rollback.add_argument(
        "--authority-key-file",
        required=True,
        type=Path,
    )
    lifecycle_rollback.add_argument("--event-id", required=True)
    serve_command = commands.add_parser("serve", help="serve the local Axiom web workbench")
    serve_command.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    serve_command.add_argument("--port", type=int, default=8000, help="bind port (default: 8000)")
    serve_command.add_argument(
        "--r5i-registry",
        type=Path,
        help="optional local R5-I SQLite registry exposed read-only to the web UI",
    )
    serve_command.add_argument("--r5i-authority-key-id")
    serve_command.add_argument("--r5i-authority-key-file", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "serve":
        import uvicorn

        from .web import create_app

        key_options = (
            args.r5i_authority_key_id,
            args.r5i_authority_key_file,
        )
        if any(key_options) and not all(key_options):
            print(
                "--r5i-authority-key-id 与 --r5i-authority-key-file 必须同时提供",
                file=sys.stderr,
            )
            return 2
        try:
            authority_keys = (
                {
                    args.r5i_authority_key_id: _read_authority_key(
                        args.r5i_authority_key_file
                    )
                }
                if all(key_options)
                else {}
            )
        except _CliInputError as exc:
            print(json.dumps(exc.payload, ensure_ascii=False), file=sys.stderr)
            return 2
        uvicorn.run(
            create_app(
                r5i_registry_path=args.r5i_registry,
                r5i_authority_keys=authority_keys,
            ),
            host=args.host,
            port=args.port,
        )
        return 0

    if args.command == "model-lifecycle":
        return _handle_r5i_lifecycle(args)

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
    elif args.command == "real-holdout-campaign":
        path, label, limit = (
            args.request,
            "真实 holdout campaign 登记请求",
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
        if payload.get("schemaId") == (
            "axiom.intelligence.preregistered-real-holdout-intake-request@1"
        ):
            try:
                request = PreregisteredRealHoldoutIntakeRequest.model_validate(payload)
            except ValidationError as exc:
                print(
                    json.dumps(
                        {
                            "code": "MalformedPreregisteredRealHoldoutIntakeRequest",
                            "path": _validation_path(exc),
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
                return 2
            report = assess_preregistered_real_holdout_intake(request)
            print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
            return 0 if report.intake_status == "Passed" else 1
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

    if args.command == "real-holdout-campaign":
        try:
            request = RealHoldoutCampaignRegistrationRequest.model_validate(payload)
        except ValidationError as exc:
            print(
                json.dumps(
                    {
                        "code": "MalformedRealHoldoutCampaignRegistrationRequest",
                        "path": _validation_path(exc),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            return 2
        report = register_real_holdout_campaign(request)
        print(report.model_dump_json(indent=2, by_alias=True, exclude_none=True))
        return 0

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
