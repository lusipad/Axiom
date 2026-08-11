from __future__ import annotations

from typing import Any, Mapping

from .comparison import compare_runs
from .evaluator import _content_hash
from .models import (
    CaseOutcome,
    DomainFailure,
    EvaluationRequest,
    ExecutionStatus,
    ExperimentArm,
    ExperimentArmResult,
    ExperimentReport,
    ExperimentSpec,
    RunSpec,
)
from .run import evaluate_run
from .subjects import SubjectExecutionError, execute_subject


def run_experiment(payload: Mapping[str, Any] | ExperimentSpec) -> ExperimentReport:
    spec = payload if isinstance(payload, ExperimentSpec) else ExperimentSpec.model_validate(payload)
    spec_hash = _content_hash(spec.model_dump(mode="json", by_alias=True, exclude_none=True))
    shared_input_hash = _content_hash(spec.shared_input)
    parameter_set_hash = _content_hash(spec.parameter_set)
    arm_results = [
        _run_arm(spec, arm, spec_hash, shared_input_hash, parameter_set_hash, index)
        for index, arm in enumerate(spec.arms)
    ]
    failures = [result.failure for result in arm_results if result.failure is not None]
    comparison = None

    if not failures:
        left = arm_results[0].run_bundle
        right = arm_results[1].run_bundle
        if left is not None and right is not None:
            comparison = compare_runs(
                left,
                right,
                policy_id=spec.comparison_policy_id,
                comparison_spec_hash=spec_hash,
                experiment_spec=spec,
            )
            if not comparison.compatibility.compatible:
                failures.append(
                    DomainFailure(
                        code="ExperimentRunsIncompatible",
                        message="Executed arms did not satisfy the experiment comparison contract.",
                        path="comparison",
                    )
                )

    if any(result.execution_status is ExecutionStatus.EXECUTION_FAILED for result in arm_results):
        execution_status = ExecutionStatus.EXECUTION_FAILED
        case_outcome = CaseOutcome.INCONCLUSIVE
    else:
        execution_status = ExecutionStatus.SUCCEEDED
        case_outcome = _aggregate_experiment_outcome(arm_results) if not failures else CaseOutcome.INCONCLUSIVE

    return _build_experiment_report(
        spec=spec,
        spec_hash=spec_hash,
        shared_input_hash=shared_input_hash,
        parameter_set_hash=parameter_set_hash,
        execution_status=execution_status,
        case_outcome=case_outcome,
        arm_results=arm_results,
        comparison=comparison,
        failures=failures,
    )


def _run_arm(
    spec: ExperimentSpec,
    arm: ExperimentArm,
    spec_hash: str,
    shared_input_hash: str,
    parameter_set_hash: str,
    index: int,
) -> ExperimentArmResult:
    try:
        output = execute_subject(
            arm.subject_id,
            arm.subject_version,
            spec.shared_input,
            spec.parameter_set,
        )
    except SubjectExecutionError as exc:
        failure = DomainFailure(code=exc.code, message=exc.message, path=f"arms.{index}")
        return ExperimentArmResult(
            arm_id=arm.arm_id,
            subject_id=arm.subject_id,
            subject_version=arm.subject_version,
            execution_status=ExecutionStatus.EXECUTION_FAILED,
            case_outcome=CaseOutcome.INCONCLUSIVE,
            failure=failure,
        )

    request = EvaluationRequest(
        artifact=output,
        case=spec.evaluation.case,
        reference_binding=spec.evaluation.reference_binding,
    )
    run_spec = RunSpec(
        subject_id=arm.subject_id,
        subject_version=arm.subject_version,
        request=request,
        domain_pack_id=spec.domain_pack_id,
        runner_id=arm.runner_id,
        evaluator_version=spec.evaluator_version,
        input_artifact_hash=shared_input_hash,
        parameter_set_hash=parameter_set_hash,
        experiment_spec_hash=spec_hash,
    )
    bundle = evaluate_run(run_spec)
    return ExperimentArmResult(
        arm_id=arm.arm_id,
        subject_id=arm.subject_id,
        subject_version=arm.subject_version,
        execution_status=bundle.run.execution_status,
        case_outcome=bundle.run.case_outcome,
        output_artifact_hash=bundle.observation.artifact_hash if bundle.observation is not None else None,
        run_bundle=bundle,
    )


def _aggregate_experiment_outcome(arm_results: list[ExperimentArmResult]) -> CaseOutcome:
    outcomes = {result.case_outcome for result in arm_results}
    for outcome in (
        CaseOutcome.INVALID,
        CaseOutcome.FAILED,
        CaseOutcome.UNSUPPORTED,
        CaseOutcome.INCONCLUSIVE,
    ):
        if outcome in outcomes:
            return outcome
    return CaseOutcome.PASSED


def _build_experiment_report(
    *,
    spec: ExperimentSpec,
    spec_hash: str,
    shared_input_hash: str,
    parameter_set_hash: str,
    execution_status: ExecutionStatus,
    case_outcome: CaseOutcome,
    arm_results: list[ExperimentArmResult],
    comparison: Any,
    failures: list[DomainFailure],
) -> ExperimentReport:
    payload = {
        "experimentSpec": spec.model_dump(mode="json", by_alias=True, exclude_none=True),
        "experimentSpecHash": spec_hash,
        "sharedInputHash": shared_input_hash,
        "parameterSetHash": parameter_set_hash,
        "executionStatus": execution_status.value,
        "caseOutcome": case_outcome.value,
        "armResults": [
            result.model_dump(mode="json", by_alias=True, exclude_none=True) for result in arm_results
        ],
        "comparison": comparison.model_dump(mode="json", by_alias=True, exclude_none=True)
        if comparison is not None
        else None,
        "failures": [failure.model_dump(mode="json", by_alias=True) for failure in failures],
    }
    return ExperimentReport(
        experiment_spec=spec,
        experiment_spec_hash=spec_hash,
        shared_input_hash=shared_input_hash,
        parameter_set_hash=parameter_set_hash,
        execution_status=execution_status,
        case_outcome=case_outcome,
        arm_results=arm_results,
        comparison=comparison,
        failures=failures,
        content_hash=_content_hash(payload),
    )


def contour_ab_example() -> ExperimentSpec:
    points = [[0.0, 0.0], [10.0, 0.0], [20.0, 0.0], [30.0, 0.0], [40.0, 0.0], [50.0, 0.0]]
    semantics = {"unit": "mm", "coordinateFrame": "G54-workpiece", "closed": False}
    reference = {
        "artifactType": "ordered-point-sequence",
        "schemaVersion": 1,
        "points": points,
        "semantics": semantics,
    }
    return ExperimentSpec.model_validate(
        {
            "experimentId": "cnc-contour-true-ab@1",
            "sharedInput": reference,
            "parameterSet": {
                "parameterSetId": "finish-pass-offset@1",
                "parameterSchemaId": "ordered-point.offset-error-parameters@1",
                "schemaVersion": 1,
                "values": {"errorVector": [0.0, 0.08], "compensationGain": 0.75},
                "units": {"errorVector": "mm", "compensationGain": "ratio"},
            },
            "arms": [
                {
                    "armId": "baseline",
                    "subjectId": "ordered-point.offset-baseline",
                    "subjectVersion": "1",
                },
                {
                    "armId": "candidate",
                    "subjectId": "ordered-point.offset-compensated",
                    "subjectVersion": "1",
                },
            ],
            "evaluation": {
                "case": {
                    "caseId": "cnc-contour-true-ab-evaluation@1",
                    "requiredMetrics": [
                        "paired.euclidean.rms",
                        {
                            "metricId": "paired.euclidean.max",
                            "threshold": {"operator": "<=", "value": 0.03, "unit": "mm"},
                        },
                    ],
                    "scoreProfile": {
                        "profileId": "cnc-contour-score@1",
                        "applicableContext": "true Case D contour experiment",
                        "rules": [
                            {
                                "metricId": "paired.euclidean.max",
                                "direction": "lower-is-better",
                                "best": 0.0,
                                "worst": 0.1,
                                "weight": 1.0,
                                "unit": "mm",
                            }
                        ],
                        "missingValuePolicy": "reject",
                    },
                },
                "referenceBinding": {
                    "reference": reference,
                    "alignment": "ordered-point.alignment.identity@1",
                    "strategyId": "ordered-point.correspondence.index-paired@1",
                    "distanceId": "ordered-point.distance.euclidean@1",
                    "tolerance": {
                        "policyId": "ordered-point.tolerance.absolute@1",
                        "value": 0.001,
                        "unit": "mm",
                    },
                    "boundaryPolicy": "ordered-point.boundary.finite-sequence@1",
                },
            },
        }
    )
