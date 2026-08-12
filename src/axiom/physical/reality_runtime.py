from __future__ import annotations

import platform
from importlib.metadata import version as package_version
from typing import Any, Literal

from ..domain import (
    CASE_OUTCOME_CLAIM_DEFINITION_ID,
    ArtifactTypeDescriptor,
    DomainPack,
    FailureMapping,
    MetricDefinition,
    NumericTolerance,
    register_domain_pack,
)
from ..evaluator import (
    _aggregate_outcome,
    _apply_threshold,
    _content_hash,
    _seal_evaluation_report,
)
from ..models import (
    CapabilityResolution,
    CaseOutcome,
    CoreEvaluationRequest,
    DomainFailure,
    EvaluationReport,
    Evidence,
    ExecutionStatus,
    MetricResult,
    MetricStatus,
    Provenance,
)
from ..runtime import DomainRuntimeBinding, register_domain_runtime_binding
from .reality_models import (
    FIVE_AXIS_REALITY_DOMAIN_PACK_ID,
    PHYSICAL_REALITY_EVALUATOR_ID,
    PHYSICAL_REALITY_RUNNER_ID,
    R41EvaluationRequest,
)
from .reality_scenarios import (
    R41_ALIGNMENT_METRIC_ID,
    R41_CALIBRATION_METRIC_ID,
    R41_CONTRACT_METRIC_ID,
    R41_DECOMPOSITION_METRIC_ID,
    R41_DEPLOYMENT_METRIC_ID,
    R41_FIT_METRIC_ID,
    R41_INDEPENDENT_METRIC_ID,
    R41_LINEAR_RMSE_METRIC_ID,
    R41_REALITY_METRIC_ID,
    R41_ROTARY_RMSE_METRIC_ID,
    assess_r41_reality,
)

R41_CONTRACT_CLAIM_ID = "five-axis.physical-reality-contract-claim@1"
R41_INDEPENDENT_CLAIM_ID = "five-axis.physical-independent-real-runs-claim@1"
R41_DEPLOYMENT_CLAIM_ID = "five-axis.physical-r7e-deployment-gates-claim@1"
R41_CALIBRATION_CLAIM_ID = "five-axis.physical-real-calibration-traceable-claim@1"
R41_ALIGNMENT_CLAIM_ID = "five-axis.physical-real-alignment-valid-claim@1"
R41_FIT_CLAIM_ID = "five-axis.physical-real-holdout-fit-claim@1"
R41_DECOMPOSITION_CLAIM_ID = (
    "five-axis.physical-real-residual-decomposition-closed-claim@1"
)
R41_REALITY_CLAIM_ID = "five-axis.physical-model-reality-validated-claim@2"

CAP_REALITY_ANALYSIS = "five-axis.physical.reality-analysis@1"
CAP_REAL_CALIBRATION = "five-axis.physical.real-calibration@1"
CAP_REAL_HOLDOUT = "five-axis.physical.real-holdout@1"
CAP_R7E_EVIDENCE = "control.beckhoff.shadow-run-evidence@1"
CAP_REALITY_EVALUATOR = "five-axis.physical.reality-evaluator@1"

_METRIC_IDS = (
    R41_CONTRACT_METRIC_ID,
    R41_INDEPENDENT_METRIC_ID,
    R41_DEPLOYMENT_METRIC_ID,
    R41_CALIBRATION_METRIC_ID,
    R41_ALIGNMENT_METRIC_ID,
    R41_FIT_METRIC_ID,
    R41_DECOMPOSITION_METRIC_ID,
    R41_REALITY_METRIC_ID,
    R41_LINEAR_RMSE_METRIC_ID,
    R41_ROTARY_RMSE_METRIC_ID,
)


def _definition(
    metric_id: str,
    *,
    requires: tuple[str, ...],
    claim_id: str | None = None,
    predicate: str | None = None,
    direction: Literal["lower-is-better", "higher-is-better"] | None = None,
    unit: str | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        metricId=metric_id,
        metricDefinitionId=metric_id,
        requires=requires,
        claimDefinitionId=claim_id,
        claimPredicate=predicate,
        direction=direction,
        numericTolerance=(
            NumericTolerance(absolute=1e-12, relative=1e-12, unit=unit)
            if direction
            else None
        ),
    )


_DEFINITIONS = (
    _definition(
        R41_CONTRACT_METRIC_ID,
        requires=(CAP_REALITY_ANALYSIS, CAP_REALITY_EVALUATOR),
        claim_id=R41_CONTRACT_CLAIM_ID,
        predicate="the two-run Windows physical reality contract is valid",
    ),
    _definition(
        R41_INDEPENDENT_METRIC_ID,
        requires=(CAP_REAL_CALIBRATION, CAP_REAL_HOLDOUT),
        claim_id=R41_INDEPENDENT_CLAIM_ID,
        predicate="calibration and validation controller captures are disjoint",
    ),
    _definition(
        R41_DEPLOYMENT_METRIC_ID,
        requires=(CAP_R7E_EVIDENCE,),
        claim_id=R41_DEPLOYMENT_CLAIM_ID,
        predicate="both inputs passed deterministic R7-E deployment Shadow replay",
    ),
    _definition(
        R41_CALIBRATION_METRIC_ID,
        requires=(CAP_REAL_CALIBRATION, CAP_REALITY_EVALUATOR),
        claim_id=R41_CALIBRATION_CLAIM_ID,
        predicate="five-axis parameters are traceable to the calibration capture",
    ),
    _definition(
        R41_ALIGNMENT_METRIC_ID,
        requires=(CAP_R7E_EVIDENCE, CAP_REALITY_EVALUATOR),
        claim_id=R41_ALIGNMENT_CLAIM_ID,
        predicate="both real runs have exact complete sample-index alignment",
    ),
    _definition(
        R41_FIT_METRIC_ID,
        requires=(CAP_REAL_HOLDOUT, CAP_REALITY_EVALUATOR),
        claim_id=R41_FIT_CLAIM_ID,
        predicate="the disjoint real holdout fit meets both unit-family tolerances",
    ),
    _definition(
        R41_DECOMPOSITION_METRIC_ID,
        requires=(CAP_REAL_HOLDOUT, CAP_REALITY_EVALUATOR),
        claim_id=R41_DECOMPOSITION_CLAIM_ID,
        predicate="command, model and observation residual decomposition closes",
    ),
    _definition(
        R41_REALITY_METRIC_ID,
        requires=(
            CAP_REAL_CALIBRATION,
            CAP_REAL_HOLDOUT,
            CAP_R7E_EVIDENCE,
            CAP_REALITY_EVALUATOR,
        ),
        claim_id=R41_REALITY_CLAIM_ID,
        predicate=(
            "the physical model passed a disjoint real holdout for one selected "
            "device and case"
        ),
    ),
    _definition(
        R41_LINEAR_RMSE_METRIC_ID,
        requires=(CAP_REAL_HOLDOUT, CAP_REALITY_EVALUATOR),
        direction="lower-is-better",
        unit="mm",
    ),
    _definition(
        R41_ROTARY_RMSE_METRIC_ID,
        requires=(CAP_REAL_HOLDOUT, CAP_REALITY_EVALUATOR),
        direction="lower-is-better",
        unit="rad",
    ),
)

FIVE_AXIS_REALITY_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=FIVE_AXIS_REALITY_DOMAIN_PACK_ID,
        artifactType="five-axis.physical-reality-analysis",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="five-axis.physical-reality-analysis",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.physical-model-definition",
                schemaVersion=2,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.control.beckhoff-shadow-run-evidence",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=PHYSICAL_REALITY_EVALUATOR_ID,
        runnerId=PHYSICAL_REALITY_RUNNER_ID,
        runnerIds=(PHYSICAL_REALITY_RUNNER_ID,),
        importRunnerIds=(PHYSICAL_REALITY_RUNNER_ID,),
        capabilityIds=(
            CAP_REALITY_ANALYSIS,
            CAP_REAL_CALIBRATION,
            CAP_REAL_HOLDOUT,
            CAP_R7E_EVIDENCE,
            CAP_REALITY_EVALUATOR,
        ),
        metricDefinitions=_DEFINITIONS,
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            R41_CONTRACT_CLAIM_ID,
            R41_INDEPENDENT_CLAIM_ID,
            R41_DEPLOYMENT_CLAIM_ID,
            R41_CALIBRATION_CLAIM_ID,
            R41_ALIGNMENT_CLAIM_ID,
            R41_FIT_CLAIM_ID,
            R41_DECOMPOSITION_CLAIM_ID,
            R41_REALITY_CLAIM_ID,
        ),
        failureMappings=(
            FailureMapping(
                code="MalformedEvaluationRequest",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
            FailureMapping(
                code="PhysicalRealityAnalysisMismatch",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
        ),
    )
)

_DEFINITION_BY_ID = {
    definition.metric_id: definition
    for definition in FIVE_AXIS_REALITY_DOMAIN_PACK.metric_definitions
}


def _parse_request(request: CoreEvaluationRequest) -> R41EvaluationRequest:
    return R41EvaluationRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _result(
    metric_id: str,
    *,
    status: MetricStatus,
    value: Any = None,
    unit: str | None = None,
    reason_code: str | None = None,
    details: dict[str, Any] | None = None,
    evidence: Evidence | None = None,
) -> MetricResult:
    definition = _DEFINITION_BY_ID[metric_id]
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=status,
        value=value,
        unit=unit,
        reasonCode=reason_code,
        details=details or {},
        evidence=evidence,
    )


def _check_result(
    metric_id: str,
    check: Any,
    *,
    evidence_level: str = "Observed",
    evidence_method: str = "real-controller-holdout@1",
) -> MetricResult:
    if check.status == "Passed":
        return _result(
            metric_id,
            status=MetricStatus.COMPUTED,
            value=True,
            details=check.details,
            evidence=Evidence(
                level=evidence_level, method=f"{metric_id}.{evidence_method}"
            ),
        )
    if check.status in {"Refuted", "Blocked"}:
        return _result(
            metric_id,
            status=MetricStatus.COMPUTED,
            value=False,
            reason_code=check.reason_code,
            details=check.details,
            evidence=Evidence(
                level=evidence_level, method=f"{metric_id}.{evidence_method}"
            ),
        )
    return _result(
        metric_id,
        status=MetricStatus.INSUFFICIENT_CONTEXT,
        reason_code=check.reason_code,
        details=check.details,
    )


def _numeric_result(
    metric_id: str, value: float | None, *, unit: str
) -> MetricResult:
    if value is None:
        return _result(
            metric_id,
            status=MetricStatus.INSUFFICIENT_CONTEXT,
            reason_code="RealHoldoutAnalysisUnavailable",
        )
    return _result(
        metric_id,
        status=MetricStatus.COMPUTED,
        value=value,
        unit=unit,
        evidence=Evidence(
            level="Observed", method=f"{metric_id}.real-controller-holdout@1"
        ),
    )


def _bind_boolean_gate(result: MetricResult) -> MetricResult:
    if result.status is MetricStatus.COMPUTED and isinstance(result.value, bool):
        return result.model_copy(update={"threshold_passed": result.value})
    return result


def _provenance(request: R41EvaluationRequest) -> Provenance:
    context_hashes: dict[str, str] = {}
    for role, pair in (
        ("calibration", request.calibration_pair),
        ("validation", request.validation_pair),
    ):
        if pair is not None:
            context_hashes[f"{role}Pair"] = pair.pair_content_hash
            context_hashes[f"{role}Command"] = pair.command_content_hash
            context_hashes[f"{role}ShadowEvidence"] = (
                pair.shadow_evidence_content_hash
            )
    if request.artifact.model is not None:
        context_hashes["physicalModel"] = request.artifact.model.content_hash
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=PHYSICAL_REALITY_RUNNER_ID,
        evaluatorVersion=PHYSICAL_REALITY_EVALUATOR_ID,
        executionOutcomePolicy=request.case.execution_outcome_policy,
        numericEnvironment={
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "pydantic": package_version("pydantic"),
        },
        contextHashes=context_hashes or None,
    )


def _invalid_report(request: R41EvaluationRequest) -> EvaluationReport:
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SKIPPED,
            caseOutcome=CaseOutcome.INVALID,
            metricResults=[
                _result(
                    metric_id,
                    status=MetricStatus.INVALID_OBSERVATION,
                    reason_code="PhysicalRealityAnalysisMismatch",
                )
                for metric_id in _METRIC_IDS
            ],
            domainFailures=[
                DomainFailure(
                    code="PhysicalRealityAnalysisMismatch",
                    message=(
                        "Submitted physical reality analysis does not match "
                        "deterministic two-run replay."
                    ),
                    path="request.artifact",
                )
            ],
            contentHash="",
            evaluatorVersion=PHYSICAL_REALITY_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


def evaluate_physical_reality(request: R41EvaluationRequest) -> EvaluationReport:
    current_platform = platform.system()
    if current_platform != "Windows":
        requested = request.case.required_metrics + request.case.optional_metrics
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.UNSUPPORTED,
                metricResults=[
                    _result(
                        item.metric_id,
                        status=MetricStatus.UNSUPPORTED_CAPABILITY,
                        reason_code="UnsupportedRuntimePlatform",
                        details={
                            "currentPlatform": current_platform,
                            "supportedPlatforms": ["Windows"],
                        },
                    )
                    for item in requested
                ],
                contentHash="",
                evaluatorVersion=PHYSICAL_REALITY_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    replay = assess_r41_reality(
        request.calibration_pair,
        request.validation_pair,
        fit_improvement_minimum=request.fit_improvement_minimum,
        excitation_span_minimum=request.excitation_span_minimum,
        decomposition_tolerance=request.decomposition_tolerance,
    )
    if replay != request.artifact or replay.content_hash != request.artifact.content_hash:
        return _invalid_report(request)

    checks = {check.check_id: check for check in replay.checks}
    evaluated = {
        R41_CONTRACT_METRIC_ID: _check_result(
            R41_CONTRACT_METRIC_ID,
            checks["r41.contract"],
            evidence_level="Validated",
            evidence_method="typed-contract-check@1",
        ),
        R41_INDEPENDENT_METRIC_ID: _check_result(
            R41_INDEPENDENT_METRIC_ID, checks["r41.independent-evidence"]
        ),
        R41_DEPLOYMENT_METRIC_ID: _check_result(
            R41_DEPLOYMENT_METRIC_ID, checks["r41.r7e-deployment-gates"]
        ),
        R41_CALIBRATION_METRIC_ID: _check_result(
            R41_CALIBRATION_METRIC_ID, checks["r41.calibration"]
        ),
        R41_ALIGNMENT_METRIC_ID: _check_result(
            R41_ALIGNMENT_METRIC_ID, checks["r41.alignment"]
        ),
        R41_FIT_METRIC_ID: _check_result(
            R41_FIT_METRIC_ID, checks["r41.holdout-fit"]
        ),
        R41_DECOMPOSITION_METRIC_ID: _check_result(
            R41_DECOMPOSITION_METRIC_ID, checks["r41.residual-decomposition"]
        ),
        R41_REALITY_METRIC_ID: _check_result(
            R41_REALITY_METRIC_ID, checks["r41.reality-gate"]
        ),
        R41_LINEAR_RMSE_METRIC_ID: _numeric_result(
            R41_LINEAR_RMSE_METRIC_ID,
            replay.linear_simulation_observation_rmse,
            unit="mm",
        ),
        R41_ROTARY_RMSE_METRIC_ID: _numeric_result(
            R41_ROTARY_RMSE_METRIC_ID,
            replay.rotary_simulation_observation_rmse,
            unit="rad",
        ),
    }
    requested = request.case.required_metrics + request.case.optional_metrics
    results = [
        _bind_boolean_gate(
            _apply_threshold(evaluated[item.metric_id], item.threshold)
        )
        for item in requested
    ]
    required_count = len(request.case.required_metrics)
    capabilities = [
        CapabilityResolution(capabilityId=CAP_REALITY_ANALYSIS, source="Artifact"),
        CapabilityResolution(capabilityId=CAP_REALITY_EVALUATOR, source="Evaluator"),
    ]
    if request.calibration_pair is not None:
        capabilities.extend(
            (
                CapabilityResolution(
                    capabilityId=CAP_REAL_CALIBRATION, source="Artifact"
                ),
                CapabilityResolution(capabilityId=CAP_R7E_EVIDENCE, source="Adapter"),
            )
        )
    if request.validation_pair is not None:
        capabilities.append(
            CapabilityResolution(capabilityId=CAP_REAL_HOLDOUT, source="Artifact")
        )
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=_aggregate_outcome(results[:required_count]),
            metricResults=results,
            capabilities=capabilities,
            contentHash="",
            evaluatorVersion=PHYSICAL_REALITY_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


FIVE_AXIS_REALITY_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=FIVE_AXIS_REALITY_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_physical_reality,
    )
)


__all__ = [
    "FIVE_AXIS_REALITY_DOMAIN_PACK",
    "FIVE_AXIS_REALITY_RUNTIME_BINDING",
    "R41_REALITY_CLAIM_ID",
    "evaluate_physical_reality",
]
