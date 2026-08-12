from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib.metadata import version as package_version
from typing import Any

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
from ..machine.runtime import (
    CLOCK_ALIGNED_METRIC_ID,
    COORDINATE_CONTEXT_METRIC_ID,
    LINEAGE_COMPLETE_METRIC_ID,
    RAW_INTEGRITY_METRIC_ID,
    READ_ONLY_CAPTURE_METRIC_ID,
    evaluate_machine_observation,
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
from .interpreter import pure_python_predict_observation
from .models import IntelligenceSample
from .r5b_models import (
    R5B_DOMAIN_PACK_ID,
    R5B_EVALUATOR_ID,
    R5B_RUNNER_ID,
    R5BIntelligenceEvaluationRequest,
)
from .training import train_r5_bundle

R5B_MODEL_INTEGRITY_METRIC_ID = "intelligence.r5b.model-integrity@1"
R5B_SOURCE_DECLARED_REAL_METRIC_ID = "intelligence.r5b.source-declared-real@1"
R5B_GOVERNANCE_VALID_METRIC_ID = "intelligence.r5b.governance-valid@1"
R5B_HOLDOUT_ISOLATION_METRIC_ID = "intelligence.r5b.holdout-isolation@1"
R5B_ALIGNMENT_COVERAGE_METRIC_ID = "intelligence.r5b.alignment-coverage@1"
R5B_OBSERVED_IMPROVEMENT_METRIC_ID = "intelligence.r5b.x.observed-improvement-ratio@1"
R5B_CONFORMAL_COVERAGE_METRIC_ID = "intelligence.r5b.x.conformal-coverage@1"
R5B_OOD_ABSTENTION_METRIC_ID = "intelligence.r5b.x.ood-abstention-rate@1"
R5B_REAL_WORLD_GENERALIZATION_METRIC_ID = "intelligence.real-world-generalization@1"
R5B_REAL_WORLD_GENERALIZATION_CLAIM_ID = (
    "intelligence.real-world-generalization-claim@1"
)

R5B_DATASET_CAPABILITY_ID = "intelligence.synthetic-dataset@1"
R5B_SPLIT_CONTRACT_CAPABILITY_ID = "intelligence.split-contract@1"
R5B_TRAINING_RECEIPT_CAPABILITY_ID = "intelligence.training-receipt@1"
R5B_MODEL_BUNDLE_CAPABILITY_ID = "intelligence.model-bundle@1"
R5B_TARGET_PARITY_CAPABILITY_ID = "intelligence.target-parity@1"
R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID = "intelligence.real-paired-holdout@1"

_R3_REQUIRED_METRICS = (
    RAW_INTEGRITY_METRIC_ID,
    READ_ONLY_CAPTURE_METRIC_ID,
    LINEAGE_COMPLETE_METRIC_ID,
    CLOCK_ALIGNED_METRIC_ID,
    COORDINATE_CONTEXT_METRIC_ID,
)
_REAL_METRIC_IDS = (
    R5B_SOURCE_DECLARED_REAL_METRIC_ID,
    R5B_GOVERNANCE_VALID_METRIC_ID,
    R5B_HOLDOUT_ISOLATION_METRIC_ID,
    R5B_ALIGNMENT_COVERAGE_METRIC_ID,
    R5B_OBSERVED_IMPROVEMENT_METRIC_ID,
    R5B_CONFORMAL_COVERAGE_METRIC_ID,
    R5B_OOD_ABSTENTION_METRIC_ID,
    R5B_REAL_WORLD_GENERALIZATION_METRIC_ID,
)


def _metric(
    metric_id: str,
    *,
    requires: tuple[str, ...],
    claim_id: str | None = None,
    predicate: str | None = None,
    direction: str | None = None,
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
            if direction is not None
            else None
        ),
    )


R5B_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=R5B_DOMAIN_PACK_ID,
        artifactType="axiom.intelligence.model-bundle",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.model-bundle",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.dataset-snapshot",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.split-manifest",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.training-receipt",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.target-parity-receipt",
                schemaVersion=1,
                role="context",
            ),
            ArtifactTypeDescriptor(
                artifactType="axiom.intelligence.real-paired-holdout-set",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=R5B_EVALUATOR_ID,
        runnerId=R5B_RUNNER_ID,
        runnerIds=(R5B_RUNNER_ID,),
        capabilityIds=(
            R5B_DATASET_CAPABILITY_ID,
            R5B_SPLIT_CONTRACT_CAPABILITY_ID,
            R5B_TRAINING_RECEIPT_CAPABILITY_ID,
            R5B_MODEL_BUNDLE_CAPABILITY_ID,
            R5B_TARGET_PARITY_CAPABILITY_ID,
            R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID,
        ),
        metricDefinitions=(
            _metric(
                R5B_MODEL_INTEGRITY_METRIC_ID,
                requires=(
                    R5B_DATASET_CAPABILITY_ID,
                    R5B_SPLIT_CONTRACT_CAPABILITY_ID,
                    R5B_TRAINING_RECEIPT_CAPABILITY_ID,
                    R5B_MODEL_BUNDLE_CAPABILITY_ID,
                    R5B_TARGET_PARITY_CAPABILITY_ID,
                ),
            ),
            _metric(
                R5B_SOURCE_DECLARED_REAL_METRIC_ID,
                requires=(R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID,),
            ),
            _metric(
                R5B_GOVERNANCE_VALID_METRIC_ID,
                requires=(R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID,),
            ),
            _metric(
                R5B_HOLDOUT_ISOLATION_METRIC_ID,
                requires=(R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID,),
            ),
            _metric(
                R5B_ALIGNMENT_COVERAGE_METRIC_ID,
                requires=(R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID,),
            ),
            _metric(
                R5B_OBSERVED_IMPROVEMENT_METRIC_ID,
                requires=(R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID,),
                direction="higher-is-better",
                unit="ratio",
            ),
            _metric(
                R5B_CONFORMAL_COVERAGE_METRIC_ID,
                requires=(R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID,),
                direction="higher-is-better",
                unit="ratio",
            ),
            _metric(
                R5B_OOD_ABSTENTION_METRIC_ID,
                requires=(R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID,),
                direction="higher-is-better",
                unit="ratio",
            ),
            _metric(
                R5B_REAL_WORLD_GENERALIZATION_METRIC_ID,
                requires=(R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID,),
                claim_id=R5B_REAL_WORLD_GENERALIZATION_CLAIM_ID,
                predicate="Real-world generalization is supported only for the submitted Windows read-only holdout cases.",
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            R5B_REAL_WORLD_GENERALIZATION_CLAIM_ID,
        ),
        comparisonPolicyIds=(),
        failureMappings=(
            FailureMapping(
                code="MalformedEvaluationRequest",
                executionStatus=ExecutionStatus.SKIPPED,
                metricStatus=MetricStatus.INVALID_OBSERVATION,
                caseOutcome=CaseOutcome.INVALID,
            ),
            FailureMapping(
                code="DomainEvaluatorFailed",
                executionStatus=ExecutionStatus.EXECUTION_FAILED,
                metricStatus=MetricStatus.NUMERICAL_FAILURE,
                caseOutcome=CaseOutcome.INCONCLUSIVE,
            ),
        ),
    )
)


@dataclass(frozen=True, slots=True)
class _AlignedCase:
    case_id: str
    role: str
    coverage: float
    maximum_time_error_seconds: float
    device_id: str
    condition_id: str
    sample_count: int
    aligned_samples: tuple[IntelligenceSample, ...]


def _parse_request(request: CoreEvaluationRequest) -> R5BIntelligenceEvaluationRequest:
    return R5BIntelligenceEvaluationRequest.model_validate(
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
    method: str | None = None,
) -> MetricResult:
    definition = R5B_DOMAIN_PACK.metric_definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=definition.requires,
        status=status,
        value=value,
        unit=unit,
        reasonCode=reason_code,
        details=details or {},
        evidence=Evidence(level="Observed", method=method or f"{metric_id}.audit@1"),
    )


def _unsupported(metric_id: str, *, current_platform: str) -> MetricResult:
    return _result(
        metric_id,
        status=MetricStatus.UNSUPPORTED_CAPABILITY,
        reason_code="UnsupportedRuntimePlatform",
        details={
            "currentPlatform": current_platform,
            "supportedPlatforms": ["Windows"],
        },
        method=f"{metric_id}.runtime-gate@1",
    )


def _bind_boolean_gate(result: MetricResult) -> MetricResult:
    if result.threshold_passed is not None:
        return result
    if result.status is MetricStatus.COMPUTED and isinstance(result.value, bool):
        return result.model_copy(update={"threshold_passed": result.value})
    return result


def _invalid_results(reason_code: str) -> list[MetricResult]:
    return [
        _result(
            metric_id, status=MetricStatus.INVALID_OBSERVATION, reason_code=reason_code
        )
        for metric_id in (
            R5B_MODEL_INTEGRITY_METRIC_ID,
            *_REAL_METRIC_IDS,
        )
    ]


def _insufficient(
    metric_id: str, *, reason_code: str, details: dict[str, Any] | None = None
) -> MetricResult:
    return _result(
        metric_id,
        status=MetricStatus.INSUFFICIENT_CONTEXT,
        reason_code=reason_code,
        details=details,
        method=f"{metric_id}.boundary@1",
    )


def _r3_context_valid(case: Any) -> bool:
    report = evaluate_machine_observation(case.observation)
    results = {result.metric_id: result for result in report.metric_results}
    return all(
        metric_id in results
        and results[metric_id].status is MetricStatus.COMPUTED
        and results[metric_id].value is True
        for metric_id in _R3_REQUIRED_METRICS
    )


def _aligned_case(case: Any, *, label_derivation_id: str) -> _AlignedCase:
    anchor = datetime.fromisoformat(case.device_time_anchor)
    parsed_frames = tuple(
        (datetime.fromisoformat(frame.device_timestamp), frame)
        for frame in case.observation.artifact.frames
    )
    used_sequences: set[int] = set()
    aligned_samples: list[IntelligenceSample] = []
    maximum_error = 0.0
    matched = 0
    response_samples = case.response_trace.samples
    total = len(response_samples)
    min_t = (
        min(float(sample.t) for sample in response_samples) if response_samples else 0.0
    )
    max_t = (
        max(float(sample.t) for sample in response_samples) if response_samples else 1.0
    )
    duration = max(max_t - min_t, 1e-12)

    for index, response_sample in enumerate(response_samples):
        target = anchor + timedelta(seconds=float(response_sample.t))
        closest_timestamp, closest_frame = min(
            parsed_frames,
            key=lambda item: abs((item[0] - target).total_seconds()),
        )
        error = abs((closest_timestamp - target).total_seconds())
        if (
            error > float(case.maximum_time_error_seconds)
            or closest_frame.sequence_id in used_sequences
        ):
            continue
        frame_samples = {sample.channel_id: sample for sample in closest_frame.samples}
        observed = frame_samples.get(case.scalar_channel_id)
        if (
            observed is None
            or not isinstance(observed.value, (int, float))
            or observed.unit != "mm"
        ):
            continue
        used_sequences.add(closest_frame.sequence_id)
        matched += 1
        maximum_error = max(maximum_error, error)
        aligned = IntelligenceSample(
            sampleId=f"{case.case_id}:x:{index}",
            axisId="X",
            topology=case.topology,
            trajectoryFamily=case.trajectory_family,
            taskId=case.task_id,
            deviceBatchId=case.batch_id,
            pairId=case.pair_id,
            declaredSplitId="test",
            scenarioRole=case.role,
            upstreamScenarioId=case.case_id,
            sourceCommandContentId=case.observation.lineage.source_command_content_hash,
            sourceCommandSampleId=case.response_trace.source_command_id,
            labelDerivationId=label_derivation_id,
            eventTime=closest_timestamp.isoformat(),
            t=min(max((float(response_sample.t) - min_t) / duration, 0.0), 1.0),
            command=float(response_sample.command[0]),
            simulation=float(response_sample.simulated[0]),
            observation=float(observed.value),
        )
        aligned_samples.append(aligned)

    coverage = matched / total if total else 0.0
    return _AlignedCase(
        case_id=case.case_id,
        role=case.role,
        coverage=coverage,
        maximum_time_error_seconds=maximum_error,
        device_id=case.observation.artifact.device_identity.device_id,
        condition_id=case.condition_id,
        sample_count=len(aligned_samples),
        aligned_samples=tuple(aligned_samples),
    )


def _provenance(request: R5BIntelligenceEvaluationRequest) -> Provenance:
    context_hashes = {
        "dataset": request.dataset.content_hash,
        "splitManifest": request.split_manifest.content_hash,
        "trainingReceipt": request.training_receipt.content_hash,
        "parityReceipt": request.parity_receipt.content_hash,
    }
    if request.real_holdout_set is not None:
        context_hashes["realHoldoutSet"] = request.real_holdout_set.content_hash
    return Provenance(
        requestHash=_content_hash(request),
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=R5B_RUNNER_ID,
        evaluatorVersion=R5B_EVALUATOR_ID,
        executionOutcomePolicy=request.case.execution_outcome_policy,
        numericEnvironment={
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "numpy": package_version("numpy"),
            "pydantic": package_version("pydantic"),
        },
        contextHashes=context_hashes,
    )


def evaluate_r5b_intelligence(
    request: R5BIntelligenceEvaluationRequest,
) -> EvaluationReport:
    current_platform = platform.system()
    metric_ids = (R5B_MODEL_INTEGRITY_METRIC_ID, *_REAL_METRIC_IDS)
    if current_platform != "Windows":
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.UNSUPPORTED,
                metricResults=[
                    _unsupported(metric_id, current_platform=current_platform)
                    for metric_id in metric_ids
                ],
                contentHash="",
                evaluatorVersion=R5B_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    replay_bundle, replay_training_receipt, replay_parity_receipt, _ = train_r5_bundle(
        request.dataset,
        request.split_manifest,
    )
    if (
        replay_bundle.content_hash != request.artifact.content_hash
        or replay_training_receipt.content_hash != request.training_receipt.content_hash
        or replay_parity_receipt.content_hash != request.parity_receipt.content_hash
    ):
        return _seal_evaluation_report(
            EvaluationReport(
                executionStatus=ExecutionStatus.SKIPPED,
                caseOutcome=CaseOutcome.INVALID,
                metricResults=_invalid_results("IntegrityReplayMismatch"),
                domainFailures=[
                    DomainFailure(
                        code="IntegrityReplayMismatch",
                        message="ModelBundle, DatasetSnapshot, SplitManifest, TrainingReceipt or ParityReceipt failed deterministic replay.",
                        path="request",
                    )
                ],
                contentHash="",
                evaluatorVersion=R5B_EVALUATOR_ID,
                provenance=_provenance(request),
            )
        )

    evaluated: dict[str, MetricResult] = {
        R5B_MODEL_INTEGRITY_METRIC_ID: _result(
            R5B_MODEL_INTEGRITY_METRIC_ID,
            status=MetricStatus.COMPUTED,
            value=True,
            details={
                "bundleHash": replay_bundle.content_hash,
                "parityReceiptHash": replay_parity_receipt.content_hash,
            },
            method=f"{R5B_MODEL_INTEGRITY_METRIC_ID}.synthetic-replay@1",
        )
    }

    if request.real_holdout_set is None:
        for metric_id in _REAL_METRIC_IDS:
            evaluated[metric_id] = _insufficient(
                metric_id,
                reason_code="RealPairedHoldoutMissing",
                details={"realWorldGeneralizationStatus": "Open"},
            )
    else:
        holdout_set = request.real_holdout_set
        governance_valid = True
        source_declared_real = all(
            case.source_kind in {"controller-export", "device-read"}
            for case in holdout_set.cases
        )
        holdout_isolation = True
        aligned_cases: list[_AlignedCase] = []
        alignment_coverage_ok = True
        r3_gate_ok = True
        for case in holdout_set.cases:
            if not _r3_context_valid(case):
                r3_gate_ok = False
            aligned = _aligned_case(
                case, label_derivation_id=request.dataset.label_derivation_id
            )
            if aligned.coverage != 1.0:
                alignment_coverage_ok = False
            aligned_cases.append(aligned)

        in_domain_samples: list[IntelligenceSample] = []
        ood_samples: list[IntelligenceSample] = []
        in_domain_abstain = 0
        ood_abstain = 0
        for aligned in aligned_cases:
            for sample in aligned.aligned_samples:
                abstained, _ = pure_python_predict_observation(request.artifact, sample)
                if aligned.role == "in-domain":
                    in_domain_samples.append(sample)
                    if abstained:
                        in_domain_abstain += 1
                else:
                    ood_samples.append(sample)
                    if abstained:
                        ood_abstain += 1

        baseline_sq = sum(
            (sample.simulation - sample.observation) ** 2
            for sample in in_domain_samples
        )
        model_sq = 0.0
        conformal_hits = 0
        evaluated_count = 0
        for sample in in_domain_samples:
            abstained, prediction = pure_python_predict_observation(
                request.artifact, sample
            )
            if abstained or prediction is None:
                continue
            evaluated_count += 1
            model_sq += (prediction - sample.observation) ** 2
            if (
                abs(prediction - sample.observation)
                <= request.artifact.x_axis_head.conformal_radius
            ):
                conformal_hits += 1
        baseline_rmse = (
            (baseline_sq / len(in_domain_samples)) ** 0.5 if in_domain_samples else 0.0
        )
        model_rmse = (
            (model_sq / evaluated_count) ** 0.5 if evaluated_count else float("inf")
        )
        improvement_ratio = (
            0.0
            if baseline_rmse <= 0 or model_rmse == float("inf")
            else (baseline_rmse - model_rmse) / baseline_rmse
        )
        conformal_coverage = (
            conformal_hits / evaluated_count if evaluated_count else 0.0
        )
        ood_abstention_rate = ood_abstain / len(ood_samples) if ood_samples else 0.0

        alignment_details = {
            "caseCoverage": {case.case_id: case.coverage for case in aligned_cases},
            "maximumTimeErrorSeconds": {
                case.case_id: case.maximum_time_error_seconds for case in aligned_cases
            },
            "r3ContextValidated": r3_gate_ok,
        }
        isolation_details = {
            "caseIds": [case.case_id for case in holdout_set.cases],
            "deviceIds": sorted(
                {
                    case.observation.artifact.device_identity.device_id
                    for case in holdout_set.cases
                }
            ),
            "conditionIds": sorted({case.condition_id for case in holdout_set.cases}),
            "selectionId": holdout_set.selection.selection_id,
        }
        source_details = {
            "sourceKinds": {
                case.case_id: case.source_kind for case in holdout_set.cases
            },
            "traceHashes": {
                case.case_id: case.observation.artifact.capture_receipt.trace_content_hash
                for case in holdout_set.cases
            },
        }
        performance_gate = (
            in_domain_abstain == 0
            and improvement_ratio >= 0.20
            and conformal_coverage >= 0.80
            and ood_abstention_rate == 1.0
        )
        final_gate = all(
            (
                governance_valid,
                source_declared_real,
                holdout_isolation,
                alignment_coverage_ok,
                r3_gate_ok,
                performance_gate,
            )
        )

        evaluated.update(
            {
                R5B_SOURCE_DECLARED_REAL_METRIC_ID: _result(
                    R5B_SOURCE_DECLARED_REAL_METRIC_ID,
                    status=MetricStatus.COMPUTED,
                    value=source_declared_real,
                    reason_code=None
                    if source_declared_real
                    else "SourceDeclaredRealFalse",
                    details=source_details,
                ),
                R5B_GOVERNANCE_VALID_METRIC_ID: _result(
                    R5B_GOVERNANCE_VALID_METRIC_ID,
                    status=MetricStatus.COMPUTED,
                    value=governance_valid,
                    reason_code=None
                    if governance_valid
                    else "GovernanceContractFailed",
                    details={
                        "governanceId": holdout_set.governance.governance_id,
                        "licenseId": holdout_set.governance.license_id,
                        "allowedUses": list(holdout_set.governance.allowed_uses),
                    },
                ),
                R5B_HOLDOUT_ISOLATION_METRIC_ID: _result(
                    R5B_HOLDOUT_ISOLATION_METRIC_ID,
                    status=MetricStatus.COMPUTED,
                    value=holdout_isolation,
                    reason_code=None if holdout_isolation else "HoldoutIsolationFailed",
                    details=isolation_details,
                ),
                R5B_ALIGNMENT_COVERAGE_METRIC_ID: _result(
                    R5B_ALIGNMENT_COVERAGE_METRIC_ID,
                    status=MetricStatus.COMPUTED,
                    value=alignment_coverage_ok and r3_gate_ok,
                    reason_code=None
                    if alignment_coverage_ok and r3_gate_ok
                    else "AlignmentCoverageFailed",
                    details=alignment_details,
                ),
                R5B_OBSERVED_IMPROVEMENT_METRIC_ID: _result(
                    R5B_OBSERVED_IMPROVEMENT_METRIC_ID,
                    status=MetricStatus.COMPUTED,
                    value=improvement_ratio,
                    unit="ratio",
                    details={
                        "baselineRmse": baseline_rmse,
                        "modelRmse": model_rmse,
                        "inDomainSampleCount": len(in_domain_samples),
                    },
                ),
                R5B_CONFORMAL_COVERAGE_METRIC_ID: _result(
                    R5B_CONFORMAL_COVERAGE_METRIC_ID,
                    status=MetricStatus.COMPUTED,
                    value=conformal_coverage,
                    unit="ratio",
                    details={
                        "evaluatedSampleCount": evaluated_count,
                        "radius": request.artifact.x_axis_head.conformal_radius,
                    },
                ),
                R5B_OOD_ABSTENTION_METRIC_ID: _result(
                    R5B_OOD_ABSTENTION_METRIC_ID,
                    status=MetricStatus.COMPUTED,
                    value=ood_abstention_rate,
                    unit="ratio",
                    details={
                        "oodSampleCount": len(ood_samples),
                        "abstainedCount": ood_abstain,
                    },
                ),
                R5B_REAL_WORLD_GENERALIZATION_METRIC_ID: _result(
                    R5B_REAL_WORLD_GENERALIZATION_METRIC_ID,
                    status=MetricStatus.COMPUTED,
                    value=final_gate,
                    reason_code=None if final_gate else "CaseScopedGateFailed",
                    details={
                        "status": "CaseScopedPassed" if final_gate else "Open",
                        "scopeCaseIds": [case.case_id for case in holdout_set.cases],
                        "inDomainAbstainedCount": in_domain_abstain,
                        "improvementRatio": improvement_ratio,
                        "conformalCoverage": conformal_coverage,
                        "oodAbstentionRate": ood_abstention_rate,
                        "submittedCasesOnly": True,
                    },
                    method=f"{R5B_REAL_WORLD_GENERALIZATION_METRIC_ID}.case-scoped@1",
                ),
            }
        )

    requested = request.case.required_metrics + request.case.optional_metrics
    results = [
        _bind_boolean_gate(_apply_threshold(evaluated[item.metric_id], item.threshold))
        for item in requested
    ]
    required = results[: len(request.case.required_metrics)]
    capabilities = [
        CapabilityResolution(capabilityId=R5B_DATASET_CAPABILITY_ID, source="Artifact"),
        CapabilityResolution(
            capabilityId=R5B_SPLIT_CONTRACT_CAPABILITY_ID, source="Artifact"
        ),
        CapabilityResolution(
            capabilityId=R5B_TRAINING_RECEIPT_CAPABILITY_ID, source="Artifact"
        ),
        CapabilityResolution(
            capabilityId=R5B_MODEL_BUNDLE_CAPABILITY_ID, source="Artifact"
        ),
        CapabilityResolution(
            capabilityId=R5B_TARGET_PARITY_CAPABILITY_ID, source="Artifact"
        ),
    ]
    if request.real_holdout_set is not None:
        capabilities.append(
            CapabilityResolution(
                capabilityId=R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID, source="Artifact"
            )
        )
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=_aggregate_outcome(required),
            metricResults=results,
            capabilities=tuple(capabilities),
            contentHash="",
            evaluatorVersion=R5B_EVALUATOR_ID,
            provenance=_provenance(request),
        )
    )


R5B_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=R5B_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_r5b_intelligence,
    )
)


__all__ = [
    "R5B_ALIGNMENT_COVERAGE_METRIC_ID",
    "R5B_CONFORMAL_COVERAGE_METRIC_ID",
    "R5B_DOMAIN_PACK",
    "R5B_GOVERNANCE_VALID_METRIC_ID",
    "R5B_HOLDOUT_ISOLATION_METRIC_ID",
    "R5B_MODEL_INTEGRITY_METRIC_ID",
    "R5B_OBSERVED_IMPROVEMENT_METRIC_ID",
    "R5B_OOD_ABSTENTION_METRIC_ID",
    "R5B_REAL_PAIRED_HOLDOUT_CAPABILITY_ID",
    "R5B_REAL_WORLD_GENERALIZATION_CLAIM_ID",
    "R5B_REAL_WORLD_GENERALIZATION_METRIC_ID",
    "R5B_RUNTIME_BINDING",
    "R5B_SOURCE_DECLARED_REAL_METRIC_ID",
    "evaluate_r5b_intelligence",
]
