from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from .domain import (
    ARTIFACT_IMPORT_RUNNER_ID,
    CASE_OUTCOME_CLAIM_DEFINITION_ID,
    METRIC_THRESHOLD_CLAIM_DEFINITION_ID,
    ORDERED_POINT_DOMAIN_PACK,
    ORDERED_POINT_DOMAIN_PACK_ID,
    ORDERED_POINT_EVALUATOR_ID,
    find_domain_pack,
)
from .evaluator import _content_hash, _evaluation_report_hash, _seal_evaluation_report, evaluate
from .models import (
    CaseOutcome,
    Claim,
    ClaimStatus,
    CoreEvaluationRequest,
    DomainFailure,
    Evidence,
    EvaluationReport,
    EvaluationRequest,
    ExecutionStatus,
    MetricResult,
    MetricStatus,
    Observation,
    Run,
    RunBundle,
    RunSpec,
)
from .runtime import find_domain_runtime_binding, get_domain_runtime_binding


def evaluate_run(payload: Mapping[str, Any] | EvaluationRequest | RunSpec) -> RunBundle:
    raw_hash = _content_hash(payload)
    try:
        spec = _coerce_run_spec(payload)
    except ValidationError as exc:
        report = _seal_evaluation_report(
            EvaluationReport(
                execution_status=ExecutionStatus.SKIPPED,
                case_outcome=CaseOutcome.INVALID,
                domain_failures=[
                    DomainFailure(
                        code="MalformedRunSpec",
                        message="RunSpec does not satisfy the import-run contract.",
                        path=_validation_path(exc),
                    )
                ],
                content_hash=raw_hash,
            )
        )
        run = _build_run(
            subject_id=None,
            domain_pack_id=ORDERED_POINT_DOMAIN_PACK_ID,
            runner_id=ARTIFACT_IMPORT_RUNNER_ID,
            run_spec_hash=None,
            report=report,
        )
        return _build_bundle(None, run, None, report, [])

    preflight = _preflight_report(spec)
    if preflight is not None:
        report = preflight
    else:
        binding = get_domain_runtime_binding(spec.domain_pack_id)
        try:
            parsed_request = binding.parse_request(spec.request)
        except ValidationError as exc:
            report = _malformed_request_report(spec, exc)
        except ValueError:
            report = _request_failure_report(
                spec,
                message="RunSpec request failed domain-specific validation.",
                path="request",
            )
        else:
            try:
                report = binding.evaluate(parsed_request)
            except Exception:
                report = _evaluator_failure_report(spec)
    report = _bind_run_provenance(spec, report)
    observation = _build_observation(spec)
    claims = _build_claims(spec, report)
    run = _build_run(
        subject_id=spec.subject_id,
        domain_pack_id=spec.domain_pack_id,
        runner_id=spec.runner_id,
        run_spec_hash=_run_spec_hash(spec),
        report=report,
    )
    return _build_bundle(spec, run, observation, report, claims)


def _preflight_report(spec: RunSpec) -> EvaluationReport | None:
    pack = find_domain_pack(spec.domain_pack_id)
    failures: list[DomainFailure] = []
    case_outcome = CaseOutcome.UNSUPPORTED
    metric_status = MetricStatus.UNSUPPORTED_CAPABILITY

    if pack is None:
        failures.append(
            DomainFailure(
                code="UnknownDomainPack",
                message="RunSpec references an unregistered DomainPack.",
                path="domainPackId",
            )
        )
    else:
        if find_domain_runtime_binding(pack.domain_pack_id) is None:
            failures.append(
                DomainFailure(
                    code="DomainPackEvaluatorUnavailable",
                    message="The registered DomainPack has no executable runtime binding.",
                    path="domainPackId",
                )
            )
        if spec.request.artifact.artifact_type != pack.artifact_type:
            failures.append(
                DomainFailure(
                    code="ArtifactTypeMismatch",
                    message="RunSpec request artifactType does not match the registered DomainPack.",
                    path="request.artifact.artifactType",
                )
            )
            case_outcome = CaseOutcome.INVALID
            metric_status = MetricStatus.INVALID_OBSERVATION
        if spec.request.artifact.schema_version not in pack.artifact_schema_versions:
            failures.append(
                DomainFailure(
                    code="ArtifactSchemaVersionMismatch",
                    message="RunSpec request schemaVersion is not supported by the registered DomainPack.",
                    path="request.artifact.schemaVersion",
                )
            )
            case_outcome = CaseOutcome.INVALID
            metric_status = MetricStatus.INVALID_OBSERVATION
        if not pack.supports_runner(spec.runner_id):
            failures.append(
                DomainFailure(
                    code="RunnerMismatch",
                    message="RunSpec runnerId does not match the registered DomainPack.",
                    path="runnerId",
                )
            )
        if spec.evaluator_version != pack.evaluator_version:
            failures.append(
                DomainFailure(
                    code="EvaluatorVersionMismatch",
                    message="RunSpec evaluatorVersion does not match the registered DomainPack.",
                    path="evaluatorVersion",
                )
            )

    if not failures:
        return None

    metric_results = [
        _preflight_metric_result(metric.metric_id, metric_status, pack)
        for metric in spec.request.case.required_metrics + spec.request.case.optional_metrics
    ]
    return EvaluationReport(
        execution_status=ExecutionStatus.SKIPPED,
        case_outcome=case_outcome,
        metric_results=metric_results,
        domain_failures=failures,
        content_hash=_content_hash(spec.request),
        evaluator_version=pack.evaluator_version if pack is not None else ORDERED_POINT_EVALUATOR_ID,
    )


def _malformed_request_report(spec: RunSpec, exc: ValidationError) -> EvaluationReport:
    return _request_failure_report(
        spec,
        message="RunSpec request does not satisfy the registered DomainPack runtime binding.",
        path=_validation_path(exc, prefix="request"),
    )


def _request_failure_report(spec: RunSpec, *, message: str, path: str | None) -> EvaluationReport:
    pack = find_domain_pack(spec.domain_pack_id) or ORDERED_POINT_DOMAIN_PACK
    mapping = pack.failure_mapping("MalformedEvaluationRequest")
    metric_status = MetricStatus.INVALID_OBSERVATION
    case_outcome = CaseOutcome.INVALID
    execution_status = ExecutionStatus.SKIPPED
    if mapping is not None:
        metric_status = MetricStatus(mapping.metric_status)
        case_outcome = CaseOutcome(mapping.case_outcome)
        execution_status = ExecutionStatus(mapping.execution_status)
    metric_results = [
        _preflight_metric_result(metric.metric_id, metric_status, pack)
        for metric in spec.request.case.required_metrics + spec.request.case.optional_metrics
    ]
    return EvaluationReport(
        execution_status=execution_status,
        case_outcome=case_outcome,
        metric_results=metric_results,
        domain_failures=[
            DomainFailure(
                code="MalformedEvaluationRequest",
                message=message,
                path=path,
            )
        ],
        content_hash=_content_hash(spec.request),
        evaluator_version=pack.evaluator_version,
    )


def _evaluator_failure_report(spec: RunSpec) -> EvaluationReport:
    pack = find_domain_pack(spec.domain_pack_id) or ORDERED_POINT_DOMAIN_PACK
    mapping = pack.failure_mapping("DomainEvaluatorFailed")
    execution_status = (
        mapping.execution_status if mapping is not None else ExecutionStatus.EXECUTION_FAILED
    )
    metric_status = mapping.metric_status if mapping is not None else MetricStatus.NUMERICAL_FAILURE
    case_outcome = mapping.case_outcome if mapping is not None else CaseOutcome.INCONCLUSIVE
    metric_results = [
        _preflight_metric_result(metric.metric_id, metric_status, pack)
        for metric in spec.request.case.required_metrics + spec.request.case.optional_metrics
    ]
    return EvaluationReport(
        execution_status=execution_status,
        case_outcome=case_outcome,
        metric_results=metric_results,
        domain_failures=[
            DomainFailure(
                code="DomainEvaluatorFailed",
                message="The registered DomainPack evaluator failed during execution.",
                path="domainPackId",
            )
        ],
        content_hash=_content_hash(spec.request),
        evaluator_version=pack.evaluator_version,
    )


def _coerce_run_spec(payload: Mapping[str, Any] | EvaluationRequest | RunSpec) -> RunSpec:
    if isinstance(payload, RunSpec):
        return payload
    if isinstance(payload, EvaluationRequest):
        return RunSpec(subject_id="imported-artifact@1", request=_core_request_from_ordered(payload))
    if _looks_like_run_spec(payload):
        spec = RunSpec.model_validate(payload)
        return _apply_domain_pack_defaults(spec, payload)
    request = EvaluationRequest.model_validate(payload)
    return RunSpec(subject_id="imported-artifact@1", request=_core_request_from_ordered(request))


def _looks_like_run_spec(payload: Mapping[str, Any]) -> bool:
    return any(key in payload for key in ("subjectId", "request", "domainPackId", "runnerId", "evaluatorVersion"))


def _core_request_from_ordered(request: EvaluationRequest) -> CoreEvaluationRequest:
    return CoreEvaluationRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _apply_domain_pack_defaults(spec: RunSpec, payload: Mapping[str, Any]) -> RunSpec:
    if "domainPackId" not in payload and "domain_pack_id" not in payload:
        return spec
    pack = find_domain_pack(spec.domain_pack_id)
    if pack is None:
        return spec
    updates: dict[str, Any] = {}
    if "runnerId" not in payload and "runner_id" not in payload:
        updates["runner_id"] = pack.runner_id
    if "evaluatorVersion" not in payload and "evaluator_version" not in payload:
        updates["evaluator_version"] = pack.evaluator_version
    if not updates:
        return spec
    return spec.model_copy(update=updates)


def _preflight_metric_result(metric_id: str, status: MetricStatus, pack: Any) -> MetricResult:
    metric_definition_id = f"ordered-point.{metric_id}@1"
    requires: list[str] = []
    if pack is not None:
        try:
            definition = pack.metric_definition(metric_id)
        except KeyError:
            pass
        else:
            metric_definition_id = definition.metric_definition_id
            requires = definition.requires
    return MetricResult(
        metric_id=metric_id,
        metric_definition_id=metric_definition_id,
        requires=requires,
        status=status,
        reason_code="RunSpecIncompatible",
    )


def _build_observation(spec: RunSpec) -> Observation:
    artifact_hash = _content_hash(spec.request.artifact)
    source = "ImportedArtifact" if spec.runner_id == ARTIFACT_IMPORT_RUNNER_ID else "ExecutedSubject"
    payload = {
        "subjectId": spec.subject_id,
        "artifact": spec.request.artifact.model_dump(mode="json", by_alias=True, exclude_unset=True),
        "artifactHash": artifact_hash,
        "source": source,
    }
    observation_hash = _content_hash(payload)
    return Observation(
        observation_id=f"observation:{observation_hash}",
        subject_id=spec.subject_id,
        artifact=spec.request.artifact,
        artifact_hash=artifact_hash,
        observation_hash=observation_hash,
        source=source,
    )


def _build_claims(spec: RunSpec, report: EvaluationReport) -> list[Claim]:
    claims = [_build_case_outcome_claim(spec.subject_id, report)]
    thresholds = {
        metric.metric_id: metric.threshold
        for metric in spec.request.case.required_metrics + spec.request.case.optional_metrics
        if metric.threshold is not None
    }
    for result in report.metric_results:
        if result.threshold_passed is None:
            continue
        claims.append(_build_threshold_claim(spec.subject_id, report, result, thresholds.get(result.metric_id)))
    return claims


def _build_case_outcome_claim(subject_id: str, report: EvaluationReport) -> Claim:
    predicate = f"case.outcome == {report.case_outcome.value}"
    evidence = Evidence(level="Observed", method="axiom.case-outcome.aggregate@1")
    report_hash = _evaluation_report_hash(report)
    details = {
        "caseOutcome": report.case_outcome.value,
        "aggregationMethod": "axiom.case-outcome.aggregate@1",
    }
    content_hash = _content_hash(
        _claim_identity_payload(
            claim_definition_id=CASE_OUTCOME_CLAIM_DEFINITION_ID,
            subject_id=subject_id,
            status=ClaimStatus.SUPPORTED,
            predicate=predicate,
            report_content_hash=report_hash,
            reason_code=None,
            evidence=evidence,
            details=details,
        )
    )
    return Claim(
        claim_id=f"claim:{content_hash}",
        claim_definition_id=CASE_OUTCOME_CLAIM_DEFINITION_ID,
        subject_id=subject_id,
        status=ClaimStatus.SUPPORTED,
        predicate=predicate,
        report_content_hash=report_hash,
        evidence=evidence,
        details=details,
        content_hash=content_hash,
    )


def _build_threshold_claim(
    subject_id: str,
    report: EvaluationReport,
    result: MetricResult,
    threshold: Any,
) -> Claim:
    status = ClaimStatus.SUPPORTED if result.threshold_passed else ClaimStatus.REFUTED
    details = {
        "metricId": result.metric_id,
        "operator": threshold.operator if threshold is not None else None,
        "thresholdValue": threshold.value if threshold is not None else None,
        "thresholdUnit": threshold.unit if threshold is not None else None,
        "metricValue": result.value,
        "resultUnit": result.unit,
    }
    predicate = (
        f"{result.metric_id} {threshold.operator} {threshold.value}"
        if threshold is not None
        else "metric.threshold"
    )
    report_hash = _evaluation_report_hash(report)
    content_hash = _content_hash(
        _claim_identity_payload(
            claim_definition_id=METRIC_THRESHOLD_CLAIM_DEFINITION_ID,
            subject_id=subject_id,
            metric_id=result.metric_id,
            status=status,
            predicate=predicate,
            report_content_hash=report_hash,
            reason_code=result.reason_code,
            evidence=result.evidence,
            details=details,
        )
    )
    return Claim(
        claim_id=f"claim:{content_hash}",
        claim_definition_id=METRIC_THRESHOLD_CLAIM_DEFINITION_ID,
        subject_id=subject_id,
        status=status,
        predicate=predicate,
        metric_id=result.metric_id,
        report_content_hash=report_hash,
        reason_code=result.reason_code,
        evidence=result.evidence,
        details=details,
        content_hash=content_hash,
    )


def _build_run(
    *,
    subject_id: str | None,
    domain_pack_id: str,
    runner_id: str,
    run_spec_hash: str | None,
    report: EvaluationReport,
) -> Run:
    provenance = report.provenance
    report_hash = _evaluation_report_hash(report)
    payload = _run_identity_payload(
        subject_id=subject_id,
        domain_pack_id=domain_pack_id,
        runner_id=runner_id,
        run_spec_hash=run_spec_hash,
        report_content_hash=report_hash,
        execution_status=report.execution_status,
        case_outcome=report.case_outcome,
        evaluator_version=report.evaluator_version,
        numeric_environment=provenance.numeric_environment if provenance is not None else {},
    )
    content_hash = _content_hash(payload)
    return Run(
        run_id=f"run:{content_hash}",
        subject_id=subject_id,
        domain_pack_id=domain_pack_id,
        runner_id=runner_id,
        run_spec_hash=run_spec_hash,
        report_content_hash=report_hash,
        execution_status=report.execution_status,
        case_outcome=report.case_outcome,
        evaluator_version=report.evaluator_version,
        numeric_environment=provenance.numeric_environment if provenance is not None else {},
        provenance=provenance,
        content_hash=content_hash,
    )


def _run_identity_payload(
    *,
    subject_id: str | None,
    domain_pack_id: str,
    runner_id: str,
    run_spec_hash: str | None,
    report_content_hash: str,
    execution_status: ExecutionStatus,
    case_outcome: CaseOutcome,
    evaluator_version: str,
    numeric_environment: dict[str, str],
) -> dict[str, Any]:
    return {
        "subjectId": subject_id,
        "domainPackId": domain_pack_id,
        "runnerId": runner_id,
        "runSpecHash": run_spec_hash,
        "reportContentHash": report_content_hash,
        "executionStatus": execution_status.value,
        "caseOutcome": case_outcome.value,
        "evaluatorVersion": evaluator_version,
        "numericEnvironment": numeric_environment,
    }


def _claim_identity_payload(
    *,
    claim_definition_id: str,
    subject_id: str | None,
    status: ClaimStatus,
    predicate: str,
    report_content_hash: str | None,
    reason_code: str | None,
    evidence: Evidence | None,
    details: dict[str, Any],
    metric_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "claimDefinitionId": claim_definition_id,
        "subjectId": subject_id,
        "status": status.value,
        "predicate": predicate,
        "reportContentHash": report_content_hash,
        "evidence": (
            evidence.model_dump(mode="json", by_alias=True)
            if evidence is not None
            else None
        ),
        "details": details,
    }
    if metric_id is not None:
        payload["metricId"] = metric_id
    if reason_code is not None:
        payload["reasonCode"] = reason_code
    return payload


def _claim_content_hash(claim: Claim) -> str:
    return _content_hash(
        _claim_identity_payload(
            claim_definition_id=claim.claim_definition_id,
            subject_id=claim.subject_id,
            metric_id=claim.metric_id,
            status=claim.status,
            predicate=claim.predicate,
            report_content_hash=claim.report_content_hash,
            reason_code=claim.reason_code,
            evidence=claim.evidence,
            details=claim.details,
        )
    )


def _build_bundle(
    run_spec: RunSpec | None,
    run: Run,
    observation: Observation | None,
    report: EvaluationReport,
    claims: list[Claim],
) -> RunBundle:
    payload = _bundle_identity_payload(run_spec, run, observation, report, claims)
    bundle_hash = _content_hash(payload)
    return RunBundle(
        run_spec=run_spec,
        run=run,
        observation=observation,
        report=report,
        claims=claims,
        bundle_hash=bundle_hash,
    )


def _bundle_identity_payload(
    run_spec: RunSpec | None,
    run: Run,
    observation: Observation | None,
    report: EvaluationReport,
    claims: list[Claim],
) -> dict[str, Any]:
    return {
        "runSpec": run_spec.model_dump(mode="json", by_alias=True, exclude_none=True) if run_spec is not None else None,
        "run": run.model_dump(mode="json", by_alias=True, exclude_none=True),
        "observation": observation.model_dump(mode="json", by_alias=True, exclude_none=True)
        if observation is not None
        else None,
        "report": report.model_dump(mode="json", by_alias=True, exclude_none=True),
        "claims": [claim.model_dump(mode="json", by_alias=True, exclude_none=True) for claim in claims],
    }


def validate_run_bundle_integrity(bundle: RunBundle) -> list[DomainFailure]:
    failures: list[DomainFailure] = []
    expected_report_hash = _evaluation_report_hash(bundle.report)
    if bundle.run_spec is not None:
        _record_hash_failure(
            failures,
            code="RunSpecHashMismatch",
            path="run.runSpecHash",
            actual=bundle.run.run_spec_hash,
            expected=_run_spec_hash(bundle.run_spec),
        )
    _record_hash_failure(
        failures,
        code="ReportContentHashMismatch",
        path="report.contentHash",
        actual=bundle.report.content_hash,
        expected=expected_report_hash,
    )
    _record_hash_failure(
        failures,
        code="ReportHashMismatch",
        path="run.reportContentHash",
        actual=bundle.run.report_content_hash,
        expected=expected_report_hash,
    )
    if bundle.observation is not None:
        artifact_hash = _content_hash(bundle.observation.artifact)
        _record_hash_failure(
            failures,
            code="ObservationArtifactHashMismatch",
            path="observation.artifactHash",
            actual=bundle.observation.artifact_hash,
            expected=artifact_hash,
        )
        observation_payload = {
            "subjectId": bundle.observation.subject_id,
            "artifact": bundle.observation.artifact.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            ),
            "artifactHash": artifact_hash,
            "source": bundle.observation.source,
        }
        _record_hash_failure(
            failures,
            code="ObservationHashMismatch",
            path="observation.observationHash",
            actual=bundle.observation.observation_hash,
            expected=_content_hash(observation_payload),
        )
    for index, claim in enumerate(bundle.claims):
        _record_hash_failure(
            failures,
            code="ClaimReportHashMismatch",
            path=f"claims[{index}].reportContentHash",
            actual=claim.report_content_hash,
            expected=expected_report_hash,
        )
        _record_hash_failure(
            failures,
            code="ClaimHashMismatch",
            path=f"claims[{index}].contentHash",
            actual=claim.content_hash,
            expected=_claim_content_hash(claim),
        )
    run_payload = _run_identity_payload(
        subject_id=bundle.run.subject_id,
        domain_pack_id=bundle.run.domain_pack_id,
        runner_id=bundle.run.runner_id,
        run_spec_hash=bundle.run.run_spec_hash,
        report_content_hash=bundle.run.report_content_hash,
        execution_status=bundle.run.execution_status,
        case_outcome=bundle.run.case_outcome,
        evaluator_version=bundle.run.evaluator_version,
        numeric_environment=bundle.run.numeric_environment,
    )
    _record_hash_failure(
        failures,
        code="RunHashMismatch",
        path="run.contentHash",
        actual=bundle.run.content_hash,
        expected=_content_hash(run_payload),
    )
    _record_hash_failure(
        failures,
        code="BundleHashMismatch",
        path="bundleHash",
        actual=bundle.bundle_hash,
        expected=_content_hash(
            _bundle_identity_payload(
                bundle.run_spec,
                bundle.run,
                bundle.observation,
                bundle.report,
                bundle.claims,
            )
        ),
    )
    return failures


def _record_hash_failure(
    failures: list[DomainFailure],
    *,
    code: str,
    path: str,
    actual: str | None,
    expected: str,
) -> None:
    if actual == expected:
        return
    failures.append(
        DomainFailure(
            code=code,
            message=f"Stored content identity does not match the serialized {path} payload.",
            path=path,
        )
    )


def _run_spec_hash(spec: RunSpec) -> str:
    return _content_hash(
        {
            "subjectId": spec.subject_id,
            "request": spec.request.model_dump(mode="json", by_alias=True, exclude_unset=True),
            "domainPackId": spec.domain_pack_id,
            "runnerId": spec.runner_id,
            "evaluatorVersion": spec.evaluator_version,
            "subjectVersion": spec.subject_version,
            "inputArtifactHash": spec.input_artifact_hash,
            "parameterSetHash": spec.parameter_set_hash,
            "experimentSpecHash": spec.experiment_spec_hash,
        }
    )


def _bind_run_provenance(spec: RunSpec, report: EvaluationReport) -> EvaluationReport:
    provenance = report.provenance
    if provenance is None:
        return _seal_evaluation_report(report)
    updated = report.model_copy(
        update={
            "provenance": provenance.model_copy(
                update={
                    "runner_id": spec.runner_id,
                    "subject_version": spec.subject_version,
                    "input_artifact_hash": spec.input_artifact_hash,
                    "parameter_set_hash": spec.parameter_set_hash,
                    "experiment_spec_hash": spec.experiment_spec_hash,
                }
            )
        }
    )
    return _seal_evaluation_report(updated)


def _validation_path(exc: ValidationError, *, prefix: str | None = None) -> str | None:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    if not errors:
        return prefix
    path = ".".join(str(part) for part in errors[0]["loc"])
    if prefix is None:
        return path or None
    if not path:
        return prefix
    return f"{prefix}.{path}"
