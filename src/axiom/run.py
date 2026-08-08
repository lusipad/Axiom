from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from .domain import (
    ARTIFACT_IMPORT_RUNNER_ID,
    CASE_OUTCOME_CLAIM_DEFINITION_ID,
    METRIC_THRESHOLD_CLAIM_DEFINITION_ID,
    ORDERED_POINT_DOMAIN_PACK_ID,
    ORDERED_POINT_EVALUATOR_ID,
    find_domain_pack,
)
from .evaluator import _content_hash, evaluate
from .models import (
    CaseOutcome,
    Claim,
    ClaimStatus,
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


def evaluate_run(payload: Mapping[str, Any] | EvaluationRequest | RunSpec) -> RunBundle:
    raw_hash = _content_hash(payload)
    try:
        spec = _coerce_run_spec(payload)
    except ValidationError as exc:
        report = EvaluationReport(
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
        run = _build_run(
            subject_id=None,
            domain_pack_id=ORDERED_POINT_DOMAIN_PACK_ID,
            runner_id=ARTIFACT_IMPORT_RUNNER_ID,
            run_spec_hash=None,
            report=report,
        )
        return _build_bundle(None, run, None, report, [])

    preflight = _preflight_report(spec)
    report = preflight if preflight is not None else evaluate(spec.request)
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
        if pack.domain_pack_id != ORDERED_POINT_DOMAIN_PACK_ID:
            failures.append(
                DomainFailure(
                    code="DomainPackEvaluatorUnavailable",
                    message="The registered DomainPack has no evaluator binding in v0.2.",
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
        if spec.runner_id != pack.runner_id:
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


def _coerce_run_spec(payload: Mapping[str, Any] | EvaluationRequest | RunSpec) -> RunSpec:
    if isinstance(payload, RunSpec):
        return payload
    if isinstance(payload, EvaluationRequest):
        return RunSpec(subject_id="imported-artifact@1", request=payload)
    if _looks_like_run_spec(payload):
        return RunSpec.model_validate(payload)
    request = EvaluationRequest.model_validate(payload)
    return RunSpec(subject_id="imported-artifact@1", request=request)


def _looks_like_run_spec(payload: Mapping[str, Any]) -> bool:
    return any(key in payload for key in ("subjectId", "request", "domainPackId", "runnerId", "evaluatorVersion"))


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
    payload = {
        "subjectId": spec.subject_id,
        "artifact": spec.request.artifact.model_dump(mode="json", by_alias=True, exclude_unset=True),
        "artifactHash": artifact_hash,
        "source": "ImportedArtifact",
    }
    observation_hash = _content_hash(payload)
    return Observation(
        observation_id=f"observation:{observation_hash}",
        subject_id=spec.subject_id,
        artifact=spec.request.artifact,
        artifact_hash=artifact_hash,
        observation_hash=observation_hash,
        source="ImportedArtifact",
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
    payload = {
        "claimDefinitionId": CASE_OUTCOME_CLAIM_DEFINITION_ID,
        "subjectId": subject_id,
        "status": ClaimStatus.SUPPORTED.value,
        "predicate": predicate,
        "reportContentHash": report_hash,
        "evidence": evidence.model_dump(mode="json", by_alias=True),
        "details": {
            "caseOutcome": report.case_outcome.value,
            "aggregationMethod": "axiom.case-outcome.aggregate@1",
        },
    }
    content_hash = _content_hash(payload)
    return Claim(
        claim_id=f"claim:{content_hash}",
        claim_definition_id=CASE_OUTCOME_CLAIM_DEFINITION_ID,
        subject_id=subject_id,
        status=ClaimStatus.SUPPORTED,
        predicate=predicate,
        report_content_hash=report_hash,
        evidence=evidence,
        details={
            "caseOutcome": report.case_outcome.value,
            "aggregationMethod": "axiom.case-outcome.aggregate@1",
        },
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
    payload = {
        "claimDefinitionId": METRIC_THRESHOLD_CLAIM_DEFINITION_ID,
        "subjectId": subject_id,
        "metricId": result.metric_id,
        "status": status.value,
        "predicate": predicate,
        "reportContentHash": report_hash,
        "evidence": (
            result.evidence.model_dump(mode="json", by_alias=True)
            if result.evidence is not None
            else None
        ),
        "details": details,
    }
    content_hash = _content_hash(payload)
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
    payload = {
        "subjectId": subject_id,
        "domainPackId": domain_pack_id,
        "runnerId": runner_id,
        "runSpecHash": run_spec_hash,
        "reportContentHash": report_hash,
        "executionStatus": report.execution_status.value,
        "caseOutcome": report.case_outcome.value,
        "evaluatorVersion": report.evaluator_version,
        "numericEnvironment": provenance.numeric_environment if provenance is not None else {},
    }
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


def _build_bundle(
    run_spec: RunSpec | None,
    run: Run,
    observation: Observation | None,
    report: EvaluationReport,
    claims: list[Claim],
) -> RunBundle:
    payload = {
        "runSpec": run_spec.model_dump(mode="json", by_alias=True, exclude_none=True) if run_spec is not None else None,
        "run": run.model_dump(mode="json", by_alias=True, exclude_none=True),
        "observation": observation.model_dump(mode="json", by_alias=True, exclude_none=True)
        if observation is not None
        else None,
        "report": report.model_dump(mode="json", by_alias=True, exclude_none=True),
        "claims": [claim.model_dump(mode="json", by_alias=True, exclude_none=True) for claim in claims],
    }
    bundle_hash = _content_hash(payload)
    return RunBundle(
        run_spec=run_spec,
        run=run,
        observation=observation,
        report=report,
        claims=claims,
        bundle_hash=bundle_hash,
    )


def _run_spec_hash(spec: RunSpec) -> str:
    return _content_hash(
        {
            "subjectId": spec.subject_id,
            "request": spec.request.model_dump(mode="json", by_alias=True, exclude_unset=True),
            "domainPackId": spec.domain_pack_id,
            "runnerId": spec.runner_id,
            "evaluatorVersion": spec.evaluator_version,
        }
    )


def _evaluation_report_hash(report: EvaluationReport) -> str:
    return _content_hash(report.model_dump(mode="json", by_alias=True, exclude_none=True))


def _validation_path(exc: ValidationError) -> str | None:
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    if not errors:
        return None
    return ".".join(str(part) for part in errors[0]["loc"])
