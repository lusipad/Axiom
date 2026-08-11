from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from .domain import EXPERIMENT_COMPARISON_POLICY_ID, STRICT_COMPARISON_POLICY_ID, find_domain_pack
from .evaluator import _content_hash
from .models import (
    CaseOutcome,
    CompatibilityIssue,
    CompatibilityReport,
    ComparisonOperand,
    ComparisonReport,
    ComparisonSpec,
    ExecutionStatus,
    ExperimentSpec,
    MetricComparison,
    MetricResult,
    MetricStatus,
    RunBundle,
    RunSpec,
)
from .run import evaluate_run, validate_run_bundle_integrity

_COMPARISON_POLICY_ID = STRICT_COMPARISON_POLICY_ID
_SUPPORTED_COMPARISON_POLICIES = {_COMPARISON_POLICY_ID, EXPERIMENT_COMPARISON_POLICY_ID}
_TERMINAL_EXECUTION_STATUSES = {
    ExecutionStatus.SUCCEEDED,
    ExecutionStatus.EXECUTION_FAILED,
    ExecutionStatus.CANCELLED,
    ExecutionStatus.SKIPPED,
}


def compare_runs(
    left_payload: Mapping[str, Any] | RunBundle,
    right_payload: Mapping[str, Any] | RunBundle,
    *,
    policy_id: str = _COMPARISON_POLICY_ID,
    comparison_spec_hash: str | None = None,
    experiment_spec: Mapping[str, Any] | ExperimentSpec | None = None,
) -> ComparisonReport:
    left_bundle, left_issue = _normalize_bundle(left_payload, side="left")
    right_bundle, right_issue = _normalize_bundle(right_payload, side="right")
    errors = [issue for issue in (left_issue, right_issue) if issue is not None]
    if policy_id not in _SUPPORTED_COMPARISON_POLICIES:
        errors.append(
            CompatibilityIssue(
                code="UnknownComparisonPolicy",
                message="The requested comparison policy is not registered by this DomainPack.",
                path="policyId",
                left_value=policy_id,
                right_value=sorted(_SUPPORTED_COMPARISON_POLICIES),
            )
        )
    differences: list[CompatibilityIssue] = []
    expected_experiment: ExperimentSpec | None = None

    if policy_id == EXPERIMENT_COMPARISON_POLICY_ID:
        expected_experiment, experiment_issue = _normalize_experiment_spec(experiment_spec)
        if experiment_issue is not None:
            errors.append(experiment_issue)
        elif expected_experiment is not None:
            expected_hash = _content_hash(
                expected_experiment.model_dump(mode="json", by_alias=True, exclude_none=True)
            )
            if comparison_spec_hash is None:
                comparison_spec_hash = expected_hash
            elif comparison_spec_hash != expected_hash:
                errors.append(
                    CompatibilityIssue(
                        code="ExperimentSpecHashMismatch",
                        message="comparisonSpecHash does not identify the supplied ExperimentSpec.",
                        path="comparisonSpecHash",
                        left_value=comparison_spec_hash,
                        right_value=expected_hash,
                    )
                )

    if left_bundle is not None and right_bundle is not None:
        side_errors, differences = _compare_context(left_bundle, right_bundle)
        errors.extend(side_errors)
        if policy_id == EXPERIMENT_COMPARISON_POLICY_ID and expected_experiment is not None:
            errors.extend(_integrity_issues(left_bundle, "left"))
            errors.extend(_integrity_issues(right_bundle, "right"))
            errors.extend(_compare_experiment_lineage(left_bundle, right_bundle, expected_experiment))

    compatibility = _build_compatibility(errors)
    metric_comparisons: list[MetricComparison] = []
    score_comparison: MetricComparison | None = None
    if not errors and left_bundle is not None and right_bundle is not None:
        metric_comparisons = _build_metric_comparisons(left_bundle, right_bundle)
        score_comparison = _build_score_comparison(left_bundle, right_bundle)

    comparison_id = _comparison_id(comparison_spec_hash, left_bundle, right_bundle, policy_id)
    payload = {
        "comparisonId": comparison_id,
        "policyId": policy_id,
        "comparisonSpecHash": comparison_spec_hash,
        "leftRun": left_bundle.model_dump(mode="json", by_alias=True, exclude_none=True) if left_bundle else None,
        "rightRun": right_bundle.model_dump(mode="json", by_alias=True, exclude_none=True) if right_bundle else None,
        "compatibility": compatibility.model_dump(mode="json", by_alias=True, exclude_none=True),
        "differences": [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in differences],
        "metricComparisons": [
            item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in metric_comparisons
        ],
        "scoreComparison": score_comparison.model_dump(mode="json", by_alias=True, exclude_none=True)
        if score_comparison is not None
        else None,
    }
    return ComparisonReport(
        comparison_id=comparison_id,
        left_run=left_bundle,
        right_run=right_bundle,
        policy_id=policy_id,
        comparison_spec_hash=comparison_spec_hash,
        compatibility=compatibility,
        differences=differences,
        metric_comparisons=metric_comparisons,
        score_comparison=score_comparison,
        content_hash=_content_hash(payload),
    )


def compare(payload: Mapping[str, Any] | ComparisonSpec) -> ComparisonReport:
    if isinstance(payload, ComparisonSpec):
        spec = payload
    else:
        try:
            spec = ComparisonSpec.model_validate(payload)
        except ValidationError as exc:
            issue = CompatibilityIssue(
                code="MalformedComparisonSpec",
                message="ComparisonSpec does not satisfy the compare API contract.",
                path=_validation_path(exc),
            )
            compatibility = _build_compatibility([issue])
            payload_hash = _content_hash(payload)
            return ComparisonReport(
                comparison_id=f"comparison:{payload_hash}",
                left_run=None,
                right_run=None,
                policy_id=_COMPARISON_POLICY_ID,
                comparison_spec_hash=None,
                compatibility=compatibility,
                differences=[],
                metric_comparisons=[],
                score_comparison=None,
                content_hash=_content_hash(
                    {
                        "comparisonId": f"comparison:{payload_hash}",
                        "compatibility": compatibility.model_dump(mode="json", by_alias=True, exclude_none=True),
                    }
                ),
            )

    left_run = evaluate_run(RunSpec(subject_id=spec.left.subject_id, request=spec.left.request))
    right_run = evaluate_run(RunSpec(subject_id=spec.right.subject_id, request=spec.right.request))
    return compare_runs(
        left_run,
        right_run,
        policy_id=spec.policy_id,
        comparison_spec_hash=_comparison_spec_hash_from_spec(spec),
    )


def _normalize_bundle(
    payload: Mapping[str, Any] | RunBundle, *, side: str
) -> tuple[RunBundle | None, CompatibilityIssue | None]:
    if isinstance(payload, RunBundle):
        return payload, None
    try:
        return RunBundle.model_validate(payload), None
    except ValidationError as exc:
        return None, CompatibilityIssue(
            code="MalformedRunBundle",
            message=f"{side} payload does not satisfy the serialized run contract.",
            path=f"{side}.{_validation_path(exc) or ''}".rstrip("."),
        )


def _normalize_experiment_spec(
    payload: Mapping[str, Any] | ExperimentSpec | None,
) -> tuple[ExperimentSpec | None, CompatibilityIssue | None]:
    if payload is None:
        return None, CompatibilityIssue(
            code="ExperimentSpecRequired",
            message="The experiment comparison policy requires the complete frozen ExperimentSpec.",
            path="experimentSpec",
        )
    if isinstance(payload, ExperimentSpec):
        return payload, None
    try:
        return ExperimentSpec.model_validate(payload), None
    except ValidationError as exc:
        return None, CompatibilityIssue(
            code="MalformedExperimentSpec",
            message="experimentSpec does not satisfy the executable experiment contract.",
            path=f"experimentSpec.{_validation_path(exc) or ''}".rstrip("."),
        )


def _compare_experiment_lineage(
    left: RunBundle,
    right: RunBundle,
    experiment_spec: ExperimentSpec,
) -> list[CompatibilityIssue]:
    errors: list[CompatibilityIssue] = []
    expected_spec_hash = _content_hash(
        experiment_spec.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    expected_input_hash = _content_hash(experiment_spec.shared_input)
    expected_parameter_hash = _content_hash(experiment_spec.parameter_set)
    for side, bundle, arm in zip(
        ("left", "right"),
        (left, right),
        experiment_spec.arms,
        strict=True,
    ):
        run_spec = bundle.run_spec
        provenance = bundle.report.provenance
        checks = [
            ("ExperimentArmSubjectMismatch", "runSpec.subjectId", run_spec.subject_id if run_spec else None, arm.subject_id),
            ("ExperimentArmSubjectVersionMismatch", "runSpec.subjectVersion", run_spec.subject_version if run_spec else None, arm.subject_version),
            ("ExperimentArmRunnerMismatch", "runSpec.runnerId", run_spec.runner_id if run_spec else None, arm.runner_id),
            ("ExperimentDomainPackMismatch", "runSpec.domainPackId", run_spec.domain_pack_id if run_spec else None, experiment_spec.domain_pack_id),
            ("ExperimentEvaluatorMismatch", "runSpec.evaluatorVersion", run_spec.evaluator_version if run_spec else None, experiment_spec.evaluator_version),
            ("InputArtifactMismatch", "runSpec.inputArtifactHash", run_spec.input_artifact_hash if run_spec else None, expected_input_hash),
            ("ParameterSetMismatch", "runSpec.parameterSetHash", run_spec.parameter_set_hash if run_spec else None, expected_parameter_hash),
            ("ExperimentSpecMismatch", "runSpec.experimentSpecHash", run_spec.experiment_spec_hash if run_spec else None, expected_spec_hash),
            ("ExperimentRunSubjectMismatch", "run.subjectId", bundle.run.subject_id, arm.subject_id),
            ("ExperimentRunRunnerMismatch", "run.runnerId", bundle.run.runner_id, arm.runner_id),
            (
                "ExperimentObservationSubjectMismatch",
                "observation.subjectId",
                bundle.observation.subject_id if bundle.observation else None,
                arm.subject_id,
            ),
            (
                "ExperimentObservationSourceMismatch",
                "observation.source",
                bundle.observation.source if bundle.observation else None,
                "ExecutedSubject",
            ),
            (
                "ExperimentProvenanceRunnerMismatch",
                "report.provenance.runnerId",
                provenance.runner_id if provenance else None,
                arm.runner_id,
            ),
            (
                "ExperimentProvenanceSubjectVersionMismatch",
                "report.provenance.subjectVersion",
                provenance.subject_version if provenance else None,
                arm.subject_version,
            ),
            (
                "ExperimentProvenanceInputMismatch",
                "report.provenance.inputArtifactHash",
                provenance.input_artifact_hash if provenance else None,
                expected_input_hash,
            ),
            (
                "ExperimentProvenanceParameterMismatch",
                "report.provenance.parameterSetHash",
                provenance.parameter_set_hash if provenance else None,
                expected_parameter_hash,
            ),
            (
                "ExperimentProvenanceSpecMismatch",
                "report.provenance.experimentSpecHash",
                provenance.experiment_spec_hash if provenance else None,
                expected_spec_hash,
            ),
        ]
        for code, path, actual, expected in checks:
            _require_equal(
                errors,
                code,
                f"{side}.{path}",
                actual,
                expected,
                f"{side} run lineage must match the frozen ExperimentSpec arm.",
                require_present=True,
            )
    return errors


def _integrity_issues(bundle: RunBundle, side: str) -> list[CompatibilityIssue]:
    return [
        CompatibilityIssue(
            code=failure.code,
            message=failure.message,
            path=f"{side}.{failure.path}" if failure.path else side,
        )
        for failure in validate_run_bundle_integrity(bundle)
    ]


def _compare_context(
    left: RunBundle, right: RunBundle
) -> tuple[list[CompatibilityIssue], list[CompatibilityIssue]]:
    errors: list[CompatibilityIssue] = []
    differences: list[CompatibilityIssue] = []

    _require_equal(
        errors,
        "DomainPackMismatch",
        "run.domainPackId",
        left.run.domain_pack_id,
        right.run.domain_pack_id,
        "Compared runs must use the same domainPackId.",
    )
    for side, bundle in (("left", left), ("right", right)):
        if find_domain_pack(bundle.run.domain_pack_id) is None:
            errors.append(
                CompatibilityIssue(
                    code="UnknownDomainPack",
                    message=f"{side} run references an unregistered DomainPack.",
                    path=f"{side}.run.domainPackId",
                    left_value=bundle.run.domain_pack_id,
                )
            )
        if bundle.run.execution_status not in _TERMINAL_EXECUTION_STATUSES:
            errors.append(
                CompatibilityIssue(
                    code="RunNotTerminal",
                    message=f"{side} run must have a terminal executionStatus.",
                    path=f"{side}.run.executionStatus",
                    left_value=bundle.run.execution_status.value,
                )
            )
        if (
            bundle.run.execution_status is not bundle.report.execution_status
            or bundle.run.case_outcome is not bundle.report.case_outcome
        ):
            errors.append(
                CompatibilityIssue(
                    code="RunReportStateMismatch",
                    message=f"{side} Run state must match its EvaluationReport state.",
                    path=f"{side}.run",
                )
            )
        if bundle.observation is None:
            errors.append(
                CompatibilityIssue(
                    code="ObservationMissing",
                    message=f"{side} run must retain its original Observation.",
                    path=f"{side}.observation",
                )
            )

    _require_equal(
        errors,
        "RunnerMismatch",
        "run.runnerId",
        left.run.runner_id,
        right.run.runner_id,
        "Compared runs must use the same runner contract.",
    )
    _require_equal(
        errors,
        "ArtifactTypeMismatch",
        "runSpec.request.artifact.artifactType",
        _run_spec_value(left, "request.artifact.artifactType"),
        _run_spec_value(right, "request.artifact.artifactType"),
        "Compared runs must use the same artifactType.",
    )
    _require_equal(
        errors,
        "SchemaMismatch",
        "runSpec.request.artifact.schemaVersion",
        _run_spec_value(left, "request.artifact.schemaVersion"),
        _run_spec_value(right, "request.artifact.schemaVersion"),
        "Compared runs must use the same artifact schemaVersion.",
    )
    _require_equal(
        errors,
        "CoordinateDimensionMismatch",
        "observation.artifact.points.dimension",
        _artifact_dimension(left),
        _artifact_dimension(right),
        "Compared runs must use the same coordinate dimension.",
    )
    _require_equal(
        errors,
        "FrameMismatch",
        "runSpec.request.artifact.semantics.coordinateFrame",
        _run_spec_value(left, "request.artifact.semantics.coordinateFrame"),
        _run_spec_value(right, "request.artifact.semantics.coordinateFrame"),
        "Compared runs must use the same observation coordinateFrame.",
    )
    _require_equal(
        errors,
        "ArtifactUnitMismatch",
        "runSpec.request.artifact.semantics.unit",
        _run_spec_value(left, "request.artifact.semantics.unit"),
        _run_spec_value(right, "request.artifact.semantics.unit"),
        "Compared runs must use the same observation unit in the strict v0.2 policy.",
    )
    _require_equal(
        errors,
        "ClosedSemanticsMismatch",
        "runSpec.request.artifact.semantics.closed",
        _run_spec_value(left, "request.artifact.semantics.closed"),
        _run_spec_value(right, "request.artifact.semantics.closed"),
        "Compared runs must use the same closed-sequence semantics.",
    )
    _require_equal(
        errors,
        "ParameterKindMismatch",
        "runSpec.request.artifact.parameter.kind",
        _run_spec_value(left, "request.artifact.parameter.kind"),
        _run_spec_value(right, "request.artifact.parameter.kind"),
        "Compared runs must use the same sequence parameter kind.",
    )
    _require_equal(
        errors,
        "ParameterUnitMismatch",
        "runSpec.request.artifact.parameter.unit",
        _run_spec_value(left, "request.artifact.parameter.unit"),
        _run_spec_value(right, "request.artifact.parameter.unit"),
        "Compared runs must use the same sequence parameter unit.",
    )

    if (
        left.report.case_outcome is CaseOutcome.INVALID
        or right.report.case_outcome is CaseOutcome.INVALID
        or left.run.case_outcome is CaseOutcome.INVALID
        or right.run.case_outcome is CaseOutcome.INVALID
    ):
        errors.append(
            CompatibilityIssue(
                code="InvalidRunState",
                message="Strict comparison requires both runs to have non-Invalid caseOutcome.",
                path="report.caseOutcome",
                left_value=left.report.case_outcome.value,
                right_value=right.report.case_outcome.value,
            )
        )

    if left.report.provenance is None or right.report.provenance is None:
        errors.append(
            CompatibilityIssue(
                code="ProvenanceMissing",
                message="Strict comparison requires provenance on both runs.",
                path="report.provenance",
            )
        )
    else:
        _require_equal(
            errors,
            "CaseMismatch",
            "report.provenance.caseHash",
            left.report.provenance.case_hash,
            right.report.provenance.case_hash,
            "Compared runs must share the same caseHash.",
        )
        _require_equal(
            errors,
            "ProfileMismatch",
            "report.provenance.scoreProfileHash",
            left.report.provenance.score_profile_hash,
            right.report.provenance.score_profile_hash,
            "Compared runs must share the same scoreProfileHash.",
        )
        _require_equal(
            errors,
            "ReferenceBindingMismatch",
            "report.provenance.referenceBindingHash",
            left.report.provenance.reference_binding_hash,
            right.report.provenance.reference_binding_hash,
            "Compared runs must share the same referenceBindingHash.",
        )
        _require_equal(
            errors,
            "ExecutionPolicyMismatch",
            "report.provenance.executionOutcomePolicy",
            left.report.provenance.execution_outcome_policy,
            right.report.provenance.execution_outcome_policy,
            "Compared runs must share the same executionOutcomePolicy.",
        )

    left_results = {result.metric_id: result for result in left.report.metric_results}
    right_results = {result.metric_id: result for result in right.report.metric_results}
    if set(left_results) != set(right_results):
        errors.append(
            CompatibilityIssue(
                code="MetricSetMismatch",
                message="Compared runs must expose the same metric result set.",
                path="report.metricResults",
                left_value=sorted(left_results),
                right_value=sorted(right_results),
            )
        )
    for metric_id in sorted(set(left_results) & set(right_results)):
        left_result = left_results[metric_id]
        right_result = right_results[metric_id]
        if left_result.metric_definition_id != right_result.metric_definition_id:
            errors.append(
                CompatibilityIssue(
                    code="MetricDefinitionMismatch",
                    message="Compared runs must expose the same metricDefinitionId.",
                    path=f"report.metricResults[{metric_id}].metricDefinitionId",
                    left_value=left_result.metric_definition_id,
                    right_value=right_result.metric_definition_id,
                )
            )
        if left_result.unit != right_result.unit:
            errors.append(
                CompatibilityIssue(
                    code="UnitMismatch",
                    message="Compared runs must expose the same result unit.",
                    path=f"report.metricResults[{metric_id}].unit",
                    left_value=left_result.unit,
                    right_value=right_result.unit,
                )
            )

    _record_difference(
        differences,
        "report.evaluatorVersion",
        left.report.evaluator_version,
        right.report.evaluator_version,
        "Evaluator versions differ across runs.",
    )
    _record_difference(
        differences,
        "report.provenance.numericType",
        _provenance_value(left, "numeric_type"),
        _provenance_value(right, "numeric_type"),
        "Numeric precision declarations differ across runs.",
    )

    left_env = left.run.numeric_environment or (_provenance_value(left, "numeric_environment") or {})
    right_env = right.run.numeric_environment or (_provenance_value(right, "numeric_environment") or {})
    for key in sorted(set(left_env) | set(right_env)):
        _record_difference(
            differences,
            f"run.numericEnvironment.{key}",
            left_env.get(key),
            right_env.get(key),
            "Numeric environment values differ across runs.",
        )

    return errors, differences


def _build_metric_comparisons(left: RunBundle, right: RunBundle) -> list[MetricComparison]:
    directions = _metric_directions(left, right)
    left_results = {result.metric_id: result for result in left.report.metric_results}
    right_results = {result.metric_id: result for result in right.report.metric_results}
    return [
        _build_metric_comparison(
            left,
            right,
            metric_id,
            left_results.get(metric_id),
            right_results.get(metric_id),
            directions.get(metric_id),
        )
        for metric_id in sorted(set(left_results) | set(right_results))
    ]


def _build_metric_comparison(
    left: RunBundle,
    right: RunBundle,
    metric_id: str,
    left_result: MetricResult | None,
    right_result: MetricResult | None,
    direction: str | None,
) -> MetricComparison:
    if left_result is None or right_result is None:
        return MetricComparison(
            metric_id=metric_id,
            metric_definition_id=(left_result or right_result).metric_definition_id,
            left_status=left_result.status if left_result else None,
            right_status=right_result.status if right_result else None,
            left_value=left_result.value if left_result else None,
            right_value=right_result.value if right_result else None,
            unit=(left_result or right_result).unit,
            comparable=False,
            reason_code="MetricMissingFromRun",
            direction=direction,
        )

    if left_result.status is not MetricStatus.COMPUTED or right_result.status is not MetricStatus.COMPUTED:
        return MetricComparison(
            metric_id=metric_id,
            metric_definition_id=left_result.metric_definition_id,
            left_status=left_result.status,
            right_status=right_result.status,
            left_value=left_result.value,
            right_value=right_result.value,
            unit=left_result.unit,
            comparable=False,
            reason_code="MetricStatusNotComputed",
            direction=direction,
        )

    if not _is_scalar_number(left_result.value) or not _is_scalar_number(right_result.value):
        return MetricComparison(
            metric_id=metric_id,
            metric_definition_id=left_result.metric_definition_id,
            left_status=left_result.status,
            right_status=right_result.status,
            left_value=left_result.value,
            right_value=right_result.value,
            unit=left_result.unit,
            comparable=False,
            reason_code="MetricValueNotScalar",
            direction=direction,
        )

    preferred = _preferred_subject_id(
        left.run.subject_id,
        right.run.subject_id,
        float(left_result.value),
        float(right_result.value),
        direction,
    )
    return MetricComparison(
        metric_id=metric_id,
        metric_definition_id=left_result.metric_definition_id,
        left_status=left_result.status,
        right_status=right_result.status,
        left_value=left_result.value,
        right_value=right_result.value,
        unit=left_result.unit,
        comparable=True,
        direction=direction,
        preferred_subject_id=preferred,
        delta=float(right_result.value) - float(left_result.value),
    )


def _build_score_comparison(left: RunBundle, right: RunBundle) -> MetricComparison | None:
    if left.report.score is None or right.report.score is None:
        if left.report.score is None and right.report.score is None:
            return None
        available = left.report.score or right.report.score
        assert available is not None
        return MetricComparison(
            metric_id="score",
            metric_definition_id=available.profile_id,
            left_status=left.report.score.status if left.report.score else None,
            right_status=right.report.score.status if right.report.score else None,
            left_value=left.report.score.value if left.report.score else None,
            right_value=right.report.score.value if right.report.score else None,
            unit="score-point",
            comparable=False,
            reason_code="ScoreMissingFromRun",
            direction="higher-is-better",
        )
    left_score = left.report.score
    right_score = right.report.score
    if left_score.status is not MetricStatus.COMPUTED or right_score.status is not MetricStatus.COMPUTED:
        return MetricComparison(
            metric_id="score",
            metric_definition_id=left_score.profile_id,
            left_status=left_score.status,
            right_status=right_score.status,
            left_value=left_score.value,
            right_value=right_score.value,
            unit="score-point",
            comparable=False,
            reason_code="ScoreStatusNotComputed",
            direction="higher-is-better",
        )
    if left_score.value is None or right_score.value is None:
        return None
    preferred = _preferred_subject_id(
        left.run.subject_id,
        right.run.subject_id,
        left_score.value,
        right_score.value,
        "higher-is-better",
    )
    return MetricComparison(
        metric_id="score",
        metric_definition_id=left_score.profile_id,
        left_status=left_score.status,
        right_status=right_score.status,
        left_value=left_score.value,
        right_value=right_score.value,
        unit="score-point",
        comparable=True,
        direction="higher-is-better",
        preferred_subject_id=preferred,
        delta=right_score.value - left_score.value,
    )


def _metric_directions(left: RunBundle, right: RunBundle) -> dict[str, str]:
    directions: dict[str, str] = {}
    if left.run_spec is None or right.run_spec is None:
        return directions

    left_profile = left.run_spec.request.case.score_profile
    right_profile = right.run_spec.request.case.score_profile
    if left_profile is not None and right_profile is not None and left_profile.profile_id == right_profile.profile_id:
        right_rule_map = {rule.metric_id: rule.direction for rule in right_profile.rules}
        for rule in left_profile.rules:
            if right_rule_map.get(rule.metric_id) == rule.direction:
                directions[rule.metric_id] = rule.direction

    pack = find_domain_pack(left.run.domain_pack_id)
    if pack is not None:
        for definition in pack.metric_definitions:
            if definition.direction is not None and definition.metric_id not in directions:
                directions[definition.metric_id] = definition.direction
    return directions


def _build_compatibility(errors: list[CompatibilityIssue]) -> CompatibilityReport:
    payload = [issue.model_dump(mode="json", by_alias=True, exclude_none=True) for issue in errors]
    return CompatibilityReport(compatible=not errors, issues=errors, content_hash=_content_hash(payload))


def _comparison_id(
    comparison_spec_hash: str | None,
    left: RunBundle | None,
    right: RunBundle | None,
    policy_id: str,
) -> str:
    if comparison_spec_hash is not None:
        return f"comparison:{comparison_spec_hash}"
    return f"comparison:{_content_hash({'policyId': policy_id, 'left': left.bundle_hash if left else None, 'right': right.bundle_hash if right else None})}"


def _comparison_spec_hash_from_spec(spec: ComparisonSpec) -> str:
    return _content_hash(
        {
            "policyId": spec.policy_id,
            "left": _comparison_operand_payload(spec.left),
            "right": _comparison_operand_payload(spec.right),
        }
    )


def _comparison_operand_payload(operand: ComparisonOperand) -> dict[str, Any]:
    return {
        "subjectId": operand.subject_id,
        "request": operand.request.model_dump(mode="json", by_alias=True, exclude_unset=True),
    }


def _run_spec_value(bundle: RunBundle, path: str) -> Any:
    if bundle.run_spec is None:
        return None
    current: Any = bundle.run_spec.model_dump(mode="json", by_alias=True, exclude_none=True)
    for part in path.split("."):
        if current is None:
            return None
        current = current.get(part) if isinstance(current, dict) else None
    return current


def _provenance_value(bundle: RunBundle, attr: str) -> Any:
    if bundle.report.provenance is None:
        return None
    return getattr(bundle.report.provenance, attr)


def _artifact_dimension(bundle: RunBundle) -> int | None:
    if bundle.observation is None or not bundle.observation.artifact.points:
        return None
    return len(bundle.observation.artifact.points[0])


def _record_difference(
    differences: list[CompatibilityIssue],
    field: str,
    left_value: Any,
    right_value: Any,
    message: str,
) -> None:
    if left_value == right_value:
        return
    differences.append(
        CompatibilityIssue(
            code="ContextDifference",
            message=message,
            path=field,
            severity="finding",
            left_value=left_value,
            right_value=right_value,
        )
    )


def _require_equal(
    errors: list[CompatibilityIssue],
    code: str,
    field: str,
    left_value: Any,
    right_value: Any,
    message: str,
    *,
    require_present: bool = False,
) -> None:
    if left_value == right_value and (not require_present or left_value is not None):
        return
    errors.append(
        CompatibilityIssue(
            code=code,
            message=message,
            path=field,
            left_value=left_value,
            right_value=right_value,
        )
    )


def _preferred_subject_id(
    left_subject_id: str | None,
    right_subject_id: str | None,
    left_value: float,
    right_value: float,
    direction: str | None,
) -> str | None:
    if direction is None or left_subject_id is None or right_subject_id is None or left_value == right_value:
        return None
    if direction == "lower-is-better":
        return left_subject_id if left_value < right_value else right_subject_id
    return left_subject_id if left_value > right_value else right_subject_id


def _is_scalar_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validation_path(exc: ValidationError) -> str | None:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    if not errors:
        return None
    return ".".join(str(part) for part in errors[0]["loc"])
