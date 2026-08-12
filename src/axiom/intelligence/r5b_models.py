from __future__ import annotations

from datetime import datetime
from itertools import pairwise
from math import isfinite
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..machine.models import MachineObservationRequest
from ..models import AxiomModel, EvaluationCase, RunSpec
from ..physical.models import PhysicalResponseTrace
from .models import (
    HASH_PATTERN,
    VERSIONED_ID_PATTERN,
    DatasetSnapshot,
    IntelligenceEvaluationRequest,
    ModelBundle,
    SplitManifest,
    TargetParityReceipt,
    TrainingReceipt,
    canonical_hash,
)

R5B_DOMAIN_PACK_ID = "intelligence.domain-pack@2"
R5B_EVALUATOR_ID = "intelligence-real-holdout-evaluator@1"
R5B_RUNNER_ID = "intelligence-real-holdout-validation@1"
R5B_REQUIRED_EVIDENCE: tuple[str, ...] = (
    "model-bundle@1",
    "dataset-snapshot@1",
    "split-manifest@1",
    "training-receipt@1",
    "target-parity-receipt@1",
    "real-paired-holdout-set@1",
)
R5B_LEAKAGE_DIMENSIONS: tuple[str, ...] = (
    "device",
    "condition",
    "task",
    "batch",
    "time",
)


def _finite(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be a finite JSON number")  # noqa: TRY004 - Pydantic validator contract
    if not isfinite(value):
        raise ValueError("value must be a finite JSON number")
    return value


def _aware_timestamp(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


class RealHoldoutGovernance(AxiomModel):
    governance_id: str = Field(alias="governanceId", pattern=VERSIONED_ID_PATTERN)
    license_id: str = Field(alias="licenseId", min_length=1)
    allowed_uses: tuple[str, ...] = Field(alias="allowedUses", min_length=1)
    retention_policy_id: str = Field(
        alias="retentionPolicyId", pattern=VERSIONED_ID_PATTERN
    )
    owner_id: str = Field(alias="ownerId", min_length=1)
    authorization_id: str = Field(alias="authorizationId", pattern=VERSIONED_ID_PATTERN)
    authenticity_basis: Literal["data-owner-attestation"] = Field(
        alias="authenticityBasis"
    )
    attested_at: str = Field(alias="attestedAt", min_length=1)
    sensitivity: Literal["internal", "restricted", "confidential"]
    redistribution_allowed: Literal[False] = Field(
        default=False, alias="redistributionAllowed"
    )
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("attested_at")
    @classmethod
    def require_attested_at(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="attestedAt")

    @model_validator(mode="after")
    def validate_contract(self) -> RealHoldoutGovernance:
        if "real-holdout-evaluation" not in self.allowed_uses:
            raise ValueError(
                "RealHoldoutGovernance allowedUses must include real-holdout-evaluation"
            )
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match RealHoldoutGovernance content")
        return self


class RealHoldoutSelectionReceipt(AxiomModel):
    selection_id: str = Field(alias="selectionId", pattern=VERSIONED_ID_PATTERN)
    model_bundle_hash: str = Field(alias="modelBundleHash", pattern=HASH_PATTERN)
    training_dataset_hash: str = Field(
        alias="trainingDatasetHash", pattern=HASH_PATTERN
    )
    selected_before_evaluation: Literal[True] = Field(alias="selectedBeforeEvaluation")
    leakage_dimensions: tuple[
        Literal["device"],
        Literal["condition"],
        Literal["task"],
        Literal["batch"],
        Literal["time"],
    ] = Field(alias="leakageDimensions", min_length=5, max_length=5)
    case_ids: tuple[str, ...] = Field(alias="caseIds", min_length=1)
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> RealHoldoutSelectionReceipt:
        if tuple(self.leakage_dimensions) != R5B_LEAKAGE_DIMENSIONS:
            raise ValueError(
                "RealHoldoutSelectionReceipt leakageDimensions must freeze device/condition/task/batch/time"
            )
        if len(self.case_ids) != len(set(self.case_ids)):
            raise ValueError("RealHoldoutSelectionReceipt caseIds must be unique")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError(
                "contentHash must match RealHoldoutSelectionReceipt content"
            )
        return self


class RealHoldoutCaseEvidence(AxiomModel):
    case_id: str = Field(alias="caseId", min_length=1)
    role: Literal["in-domain", "ood-probe"]
    topology: Literal["dual-table", "head-table", "dual-head"]
    trajectory_family: str = Field(alias="trajectoryFamily", min_length=1)
    task_id: str = Field(alias="taskId", min_length=1)
    condition_id: str = Field(alias="conditionId", min_length=1)
    batch_id: str = Field(alias="batchId", min_length=1)
    pair_id: str = Field(alias="pairId", min_length=1)
    source_kind: Literal["controller-export", "device-read"] = Field(alias="sourceKind")
    observation: MachineObservationRequest
    response_trace: PhysicalResponseTrace = Field(alias="responseTrace")
    scalar_channel_id: str = Field(alias="scalarChannelId", min_length=1)
    scalar_unit: Literal["mm"] = Field(alias="scalarUnit")
    capture_start_time: str = Field(alias="captureStartTime", min_length=1)
    capture_end_time: str = Field(alias="captureEndTime", min_length=1)
    device_time_anchor: str = Field(alias="deviceTimeAnchor", min_length=1)
    maximum_time_error_seconds: float = Field(alias="maximumTimeErrorSeconds", ge=0.0)
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("capture_start_time", "capture_end_time", "device_time_anchor")
    @classmethod
    def require_aware_anchor(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @field_validator("maximum_time_error_seconds", mode="before")
    @classmethod
    def reject_non_finite_error(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_contract(self) -> RealHoldoutCaseEvidence:
        if datetime.fromisoformat(self.capture_end_time) <= datetime.fromisoformat(
            self.capture_start_time
        ):
            raise ValueError(
                "RealHoldoutCaseEvidence captureEndTime must be greater than captureStartTime"
            )
        if self.observation.artifact.source_kind != self.source_kind:
            raise ValueError(
                "RealHoldoutCaseEvidence sourceKind must match observation artifact sourceKind"
            )
        if self.observation.lineage.pairing_status != "paired":
            raise ValueError(
                "RealHoldoutCaseEvidence observation lineage must be paired"
            )
        if self.observation.clock_mapping is None:
            raise ValueError("RealHoldoutCaseEvidence requires clockMapping")
        if self.observation.coordinate_alignment is None:
            raise ValueError("RealHoldoutCaseEvidence requires coordinateAlignment")
        if self.observation.coordinate_alignment.calibration_status != "calibrated":
            raise ValueError(
                "RealHoldoutCaseEvidence coordinateAlignment must be calibrated"
            )
        if self.observation.coordinate_alignment.source_kind == "synthetic-reference":
            raise ValueError(
                "RealHoldoutCaseEvidence coordinateAlignment must not be synthetic-reference"
            )
        if (
            self.observation.lineage.source_command_content_hash
            != self.response_trace.source_command_content_id
        ):
            raise ValueError(
                "RealHoldoutCaseEvidence responseTrace source command hash must match observation lineage"
            )
        channels = {
            channel.channel_id: channel
            for channel in self.observation.device_profile.channels
        }
        scalar_channel = channels.get(self.scalar_channel_id)
        if scalar_channel is None:
            raise ValueError(
                "RealHoldoutCaseEvidence scalarChannelId must be declared by deviceProfile"
            )
        if scalar_channel.unit != self.scalar_unit:
            raise ValueError(
                "RealHoldoutCaseEvidence scalarChannelId must use mm units"
            )
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match RealHoldoutCaseEvidence content")
        return self


class RealPairedHoldoutSet(AxiomModel):
    artifact_type: Literal["axiom.intelligence.real-paired-holdout-set"] = Field(
        alias="artifactType"
    )
    schema_id: Literal["axiom.intelligence.real-paired-holdout-set@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    holdout_set_id: str = Field(alias="holdoutSetId", pattern=VERSIONED_ID_PATTERN)
    model_bundle_hash: str = Field(alias="modelBundleHash", pattern=HASH_PATTERN)
    training_dataset_hash: str = Field(
        alias="trainingDatasetHash", pattern=HASH_PATTERN
    )
    governance: RealHoldoutGovernance
    selection: RealHoldoutSelectionReceipt
    cases: tuple[RealHoldoutCaseEvidence, ...] = Field(min_length=3)
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> RealPairedHoldoutSet:
        if self.selection.model_bundle_hash != self.model_bundle_hash:
            raise ValueError(
                "RealPairedHoldoutSet selection must identify modelBundleHash"
            )
        if self.selection.training_dataset_hash != self.training_dataset_hash:
            raise ValueError(
                "RealPairedHoldoutSet selection must identify trainingDatasetHash"
            )
        case_ids = tuple(case.case_id for case in self.cases)
        if tuple(self.selection.case_ids) != case_ids:
            raise ValueError(
                "RealPairedHoldoutSet selection caseIds must exactly match case order"
            )
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("RealPairedHoldoutSet caseId values must be unique")
        trace_hashes = [
            case.observation.artifact.capture_receipt.trace_content_hash
            for case in self.cases
        ]
        if len(set(trace_hashes)) != len(trace_hashes):
            raise ValueError(
                "RealPairedHoldoutSet traceContentHash values must be unique"
            )
        response_hashes = [case.response_trace.content_hash for case in self.cases]
        if len(set(response_hashes)) != len(response_hashes):
            raise ValueError(
                "RealPairedHoldoutSet responseTrace contentHash values must be unique"
            )
        task_ids = [case.task_id for case in self.cases]
        if len(set(task_ids)) != len(task_ids):
            raise ValueError("RealPairedHoldoutSet taskId values must be unique")
        batch_ids = [case.batch_id for case in self.cases]
        if len(set(batch_ids)) != len(batch_ids):
            raise ValueError("RealPairedHoldoutSet batchId values must be unique")
        pair_ids = [case.pair_id for case in self.cases]
        if len(set(pair_ids)) != len(pair_ids):
            raise ValueError("RealPairedHoldoutSet pairId values must be unique")
        windows = sorted(
            (
                datetime.fromisoformat(case.capture_start_time),
                datetime.fromisoformat(case.capture_end_time),
                case.case_id,
            )
            for case in self.cases
        )
        for left, right in pairwise(windows):
            if left[1] >= right[0]:
                raise ValueError(
                    "RealPairedHoldoutSet capture windows must not overlap"
                )
        in_domain = tuple(case for case in self.cases if case.role == "in-domain")
        if len(in_domain) < 2:
            raise ValueError(
                "RealPairedHoldoutSet requires at least two in-domain cases"
            )
        if sum(case.role == "ood-probe" for case in self.cases) < 1:
            raise ValueError(
                "RealPairedHoldoutSet requires at least one ood-probe case"
            )
        device_ids = {
            case.observation.artifact.device_identity.device_id for case in in_domain
        }
        if len(device_ids) < 2:
            raise ValueError(
                "RealPairedHoldoutSet in-domain cases must span at least two devices"
            )
        condition_ids = {case.condition_id for case in in_domain}
        if len(condition_ids) < 2:
            raise ValueError(
                "RealPairedHoldoutSet in-domain cases must span at least two conditions"
            )
        latest_capture_end = max(
            datetime.fromisoformat(case.capture_end_time) for case in self.cases
        )
        if datetime.fromisoformat(self.governance.attested_at) < latest_capture_end:
            raise ValueError(
                "RealPairedHoldoutSet governance attestedAt must not precede capture completion"
            )
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match RealPairedHoldoutSet content")
        return self


class R5BIntelligenceEvaluationRequest(AxiomModel):
    artifact: ModelBundle
    dataset: DatasetSnapshot
    split_manifest: SplitManifest = Field(alias="splitManifest")
    training_receipt: TrainingReceipt = Field(alias="trainingReceipt")
    parity_receipt: TargetParityReceipt = Field(alias="parityReceipt")
    real_holdout_set: RealPairedHoldoutSet | None = Field(
        default=None, alias="realHoldoutSet"
    )
    case: EvaluationCase

    @model_validator(mode="after")
    def validate_cross_object_contract(self) -> R5BIntelligenceEvaluationRequest:
        IntelligenceEvaluationRequest.model_validate(
            {
                "artifact": self.artifact.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
                "dataset": self.dataset.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
                "splitManifest": self.split_manifest.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
                "trainingReceipt": self.training_receipt.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
                "parityReceipt": self.parity_receipt.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
                "case": self.case.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ),
            }
        )
        if self.real_holdout_set is None:
            return self
        if self.artifact.synthetic_learning_contract_status != "Passed":
            raise ValueError(
                "R5-B requires a ModelBundle that passed the R5-A synthetic learning contract"
            )
        if (
            self.parity_receipt.status != "Passed"
            or self.parity_receipt.max_abs_gap > 1e-12
        ):
            raise ValueError("R5-B requires target parity at or below 1e-12")
        if self.real_holdout_set.model_bundle_hash != self.artifact.content_hash:
            raise ValueError(
                "RealPairedHoldoutSet modelBundleHash must identify ModelBundle"
            )
        if self.real_holdout_set.training_dataset_hash != self.dataset.content_hash:
            raise ValueError(
                "RealPairedHoldoutSet trainingDatasetHash must identify DatasetSnapshot"
            )
        latest_training_time = max(
            datetime.fromisoformat(sample.event_time) for sample in self.dataset.samples
        )
        dataset_task_ids = {sample.task_id for sample in self.dataset.samples}
        dataset_batch_ids = {sample.device_batch_id for sample in self.dataset.samples}
        dataset_pair_ids = {sample.pair_id for sample in self.dataset.samples}
        for case in self.real_holdout_set.cases:
            if datetime.fromisoformat(case.capture_start_time) <= latest_training_time:
                raise ValueError(
                    "RealPairedHoldoutSet captureStartTime must be later than the training dataset window"
                )
            if case.task_id in dataset_task_ids:
                raise ValueError(
                    "RealPairedHoldoutSet taskId identities must be disjoint from training dataset"
                )
            if case.batch_id in dataset_batch_ids:
                raise ValueError(
                    "RealPairedHoldoutSet batchId identities must be disjoint from training dataset"
                )
            if case.pair_id in dataset_pair_ids:
                raise ValueError(
                    "RealPairedHoldoutSet pairId identities must be disjoint from training dataset"
                )
        return self


class R5BAcceptanceThresholds(AxiomModel):
    minimum_in_domain_cases: Literal[2] = Field(alias="minimumInDomainCases")
    minimum_total_cases: Literal[3] = Field(alias="minimumTotalCases")
    minimum_distinct_devices: Literal[2] = Field(alias="minimumDistinctDevices")
    minimum_distinct_conditions: Literal[2] = Field(alias="minimumDistinctConditions")
    required_alignment_coverage: Literal[1.0] = Field(alias="requiredAlignmentCoverage")
    minimum_improvement_ratio: Literal[0.2] = Field(alias="minimumImprovementRatio")
    minimum_conformal_coverage: Literal[0.8] = Field(alias="minimumConformalCoverage")
    required_ood_abstention_rate: Literal[1.0] = Field(
        alias="requiredOodAbstentionRate"
    )
    maximum_target_parity_gap: Literal[1e-12] = Field(alias="maximumTargetParityGap")


class R5BManifest(AxiomModel):
    manifest_id: Literal["axiom.intelligence.r5b-manifest@1"] = Field(
        alias="manifestId"
    )
    schema_id: Literal["axiom.intelligence.r5b-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["R5-B"]
    domain_pack_id: Literal["intelligence.domain-pack@2"] = Field(alias="domainPackId")
    platform: Literal["windows"] = Field(alias="platform")
    default_scenario_id: str = Field(alias="defaultScenarioId", min_length=1)
    contract_readiness_status: Literal["Passed"] = Field(
        alias="contractReadinessStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    safety_banner: Literal["REAL HOLDOUT VALIDATION / NOT DEVICE SAFE"] = Field(
        alias="safetyBanner"
    )
    reality_banner: Literal[
        "NO BUNDLED REAL CAPTURE / CASE-SCOPED EVIDENCE REQUIRED"
    ] = Field(alias="realityBanner")
    required_evidence: tuple[str, ...] = Field(
        alias="requiredEvidence", min_length=len(R5B_REQUIRED_EVIDENCE)
    )
    acceptance_thresholds: R5BAcceptanceThresholds = Field(alias="acceptanceThresholds")

    @model_validator(mode="after")
    def validate_contract(self) -> R5BManifest:
        if tuple(self.required_evidence) != R5B_REQUIRED_EVIDENCE:
            raise ValueError(
                "R5BManifest requiredEvidence must freeze the published R5-B evidence contract"
            )
        return self


class R5BScenarioSummary(AxiomModel):
    scenario_id: str = Field(alias="scenarioId", min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expected_outcome: Literal["Passed", "Inconclusive", "Invalid", "Unsupported"] = (
        Field(alias="expectedOutcome")
    )
    expected_execution_status: Literal["Succeeded", "Skipped"] = Field(
        alias="expectedExecutionStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )


class R5BReadinessCheck(AxiomModel):
    check_id: str = Field(alias="checkId", min_length=1)
    title: str = Field(min_length=1)
    status: Literal["Passed", "Open", "Failed", "Invalid"]
    detail: str = Field(min_length=1)


class R5BExamplePayload(AxiomModel):
    manifest: R5BManifest
    scenario: R5BScenarioSummary
    readiness_checks: tuple[R5BReadinessCheck, ...] = Field(
        alias="readinessChecks", min_length=1
    )
    model_bundle: ModelBundle = Field(alias="modelBundle")
    dataset: DatasetSnapshot
    split_manifest: SplitManifest = Field(alias="splitManifest")
    training_receipt: TrainingReceipt = Field(alias="trainingReceipt")
    parity_receipt: TargetParityReceipt = Field(alias="parityReceipt")
    real_holdout_set: RealPairedHoldoutSet | None = Field(
        default=None, alias="realHoldoutSet"
    )
    run_spec: RunSpec = Field(alias="runSpec")


__all__ = [
    "R5B_DOMAIN_PACK_ID",
    "R5B_EVALUATOR_ID",
    "R5B_REQUIRED_EVIDENCE",
    "R5B_RUNNER_ID",
    "R5BAcceptanceThresholds",
    "R5BExamplePayload",
    "R5BIntelligenceEvaluationRequest",
    "R5BManifest",
    "R5BReadinessCheck",
    "R5BScenarioSummary",
    "RealHoldoutCaseEvidence",
    "RealHoldoutGovernance",
    "RealHoldoutSelectionReceipt",
    "RealPairedHoldoutSet",
]
