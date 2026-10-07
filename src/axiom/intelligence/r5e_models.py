from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel
from .models import HASH_PATTERN, VERSIONED_ID_PATTERN, canonical_hash
from .r5c_models import (
    R5C_TARGETS,
    ConditionalEffectDatasetV2,
    ConditionalEffectEvaluation,
    ConditionalEffectModelBundleV2,
    ConditionalEffectParityReceiptV2,
    ConditionalEffectSplitManifestV2,
    ConditionalEffectTrainingReceiptV2,
)
from .r5d_models import (
    R5DExperimentPlanRequest,
    SimulationExperimentPlan,
)

R5E_RUNNER_ID = "axiom.physical.canonical-f3-f4-r4-replay@1"
R5E_APPROVAL_POLICY_ID = "axiom.intelligence.r5e-explicit-offline-approval@1"
R5E_CANDIDATE_GATE_POLICY_ID = (
    "axiom.intelligence.r5e-original-holdout-non-regression@1"
)
R5E_SAFETY_BANNER = (
    "SYNTHETIC SIL CAMPAIGN / NOT REALITY VALIDATED / NOT DEVICE SAFE / "
    "PROMOTION NOT PERFORMED"
)


def _finite(value: Any) -> Any:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("value must be a finite JSON number")
    return value


class SyntheticSimulationCampaignApproval(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.synthetic-simulation-campaign-approval@1"
    ] = Field(alias="schemaId")
    approval_id: str = Field(alias="approvalId", pattern=VERSIONED_ID_PATTERN)
    approval_policy_id: Literal[
        "axiom.intelligence.r5e-explicit-offline-approval@1"
    ] = Field(alias="approvalPolicyId")
    plan_content_hash: str = Field(alias="planContentHash", pattern=HASH_PATTERN)
    approved_experiment_ids: tuple[str, ...] = Field(
        alias="approvedExperimentIds", min_length=1
    )
    accountable_party_id: str = Field(alias="accountablePartyId", min_length=1)
    approval_mode: Literal["explicit-offline-user-approval"] = Field(
        alias="approvalMode"
    )
    human_approval_present: Literal[True] = Field(alias="humanApprovalPresent")
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    automatic_execution_allowed: Literal[False] = Field(
        alias="automaticExecutionAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("accountable_party_id")
    @classmethod
    def reject_blank_party(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("accountablePartyId must not be blank")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> "SyntheticSimulationCampaignApproval":
        if len(self.approved_experiment_ids) != len(set(self.approved_experiment_ids)):
            raise ValueError("approvedExperimentIds must be unique")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match campaign approval content")
        return self


class R5ESyntheticCampaignRequest(AxiomModel):
    schema_id: Literal["axiom.intelligence.synthetic-simulation-campaign-request@1"] = (
        Field(alias="schemaId")
    )
    plan_request: R5DExperimentPlanRequest = Field(alias="planRequest")
    plan: SimulationExperimentPlan
    approval: SyntheticSimulationCampaignApproval
    execution_mode: Literal["local-windows-synthetic-sil"] = Field(
        alias="executionMode"
    )
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "R5ESyntheticCampaignRequest":
        if self.plan_request.dataset.schema_version != 1:
            raise ValueError("R5-E v1 campaign requires the immutable R5-C v1 source")
        if self.plan.status != "Planned" or len(self.plan.proposals) != 5:
            raise ValueError("R5-E v1 campaign requires a complete five-proposal plan")
        if self.plan.requested_batch_size != 5:
            raise ValueError("R5-E v1 campaign freezes batchSize=5")
        source_identities = (
            (self.plan.model_bundle_hash, self.plan_request.model_bundle.content_hash),
            (self.plan.dataset_content_hash, self.plan_request.dataset.content_hash),
            (
                self.plan.split_manifest_content_hash,
                self.plan_request.split_manifest.content_hash,
            ),
        )
        if any(actual != expected for actual, expected in source_identities):
            raise ValueError("plan must identify every campaign source object")
        if self.approval.plan_content_hash != self.plan.content_hash:
            raise ValueError("approval must identify the exact plan content")
        proposal_ids = tuple(item.experiment_id for item in self.plan.proposals)
        if self.approval.approved_experiment_ids != proposal_ids:
            raise ValueError("approval must cover all proposals in plan order")
        if any(item.planned_runner_id != R5E_RUNNER_ID for item in self.plan.proposals):
            raise ValueError("all proposals must use the frozen local SIL runner")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match campaign request content")
        return self


class R5ECampaignApprovalCommand(AxiomModel):
    plan_request: R5DExperimentPlanRequest = Field(alias="planRequest")
    plan: SimulationExperimentPlan
    accountable_party_id: str = Field(alias="accountablePartyId", min_length=1)
    synthetic_only_acknowledged: Literal[True] = Field(
        alias="syntheticOnlyAcknowledged"
    )

    @field_validator("accountable_party_id")
    @classmethod
    def reject_blank_party(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("accountablePartyId must not be blank")
        return value


class SyntheticSimulationExperimentResult(AxiomModel):
    result_id: str = Field(alias="resultId", pattern=VERSIONED_ID_PATTERN)
    rank: int = Field(ge=1, le=5)
    experiment_id: str = Field(alias="experimentId", pattern=VERSIONED_ID_PATTERN)
    feed_override: float = Field(alias="feedOverride")
    sample_period: float = Field(alias="samplePeriod")
    cycle_time_seconds: float = Field(alias="cycleTimeSeconds", gt=0.0)
    linear_following_error_max_mm: float = Field(
        alias="linearFollowingErrorMaxMm", ge=0.0
    )
    command_sample_count: int = Field(alias="commandSampleCount", ge=2)
    m4_content_hash: str = Field(alias="m4ContentHash", pattern=HASH_PATTERN)
    m5_content_hash: str = Field(alias="m5ContentHash", pattern=HASH_PATTERN)
    physical_response_content_hash: str = Field(
        alias="physicalResponseContentHash", pattern=HASH_PATTERN
    )
    continuous_feasibility_status: Literal["Supported"] = Field(
        alias="continuousFeasibilityStatus"
    )
    adapter_status: Literal["Succeeded"] = Field(alias="adapterStatus")
    interval_verification_status: Literal["Supported"] = Field(
        alias="intervalVerificationStatus"
    )
    collision_verification_status: Literal["safe"] = Field(
        alias="collisionVerificationStatus"
    )
    execution_status: Literal["Succeeded"] = Field(alias="executionStatus")
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator(
        "feed_override",
        "sample_period",
        "cycle_time_seconds",
        "linear_following_error_max_mm",
        mode="before",
    )
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_contract(self) -> "SyntheticSimulationExperimentResult":
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match experiment result content")
        return self


class SyntheticSimulationAcquisitionReceipt(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.synthetic-simulation-acquisition-receipt@1"
    ] = Field(alias="schemaId")
    receipt_id: str = Field(alias="receiptId", pattern=VERSIONED_ID_PATTERN)
    campaign_request_hash: str = Field(
        alias="campaignRequestHash", pattern=HASH_PATTERN
    )
    approval_content_hash: str = Field(
        alias="approvalContentHash", pattern=HASH_PATTERN
    )
    source_plan_content_hash: str = Field(
        alias="sourcePlanContentHash", pattern=HASH_PATTERN
    )
    source_model_bundle_hash: str = Field(
        alias="sourceModelBundleHash", pattern=HASH_PATTERN
    )
    source_dataset_content_hash: str = Field(
        alias="sourceDatasetContentHash", pattern=HASH_PATTERN
    )
    source_split_manifest_hash: str = Field(
        alias="sourceSplitManifestHash", pattern=HASH_PATTERN
    )
    runner_id: Literal["axiom.physical.canonical-f3-f4-r4-replay@1"] = Field(
        alias="runnerId"
    )
    physical_model_content_hash: str = Field(
        alias="physicalModelContentHash", pattern=HASH_PATTERN
    )
    execution_status: Literal["Succeeded"] = Field(alias="executionStatus")
    result_count: Literal[5] = Field(alias="resultCount")
    results: tuple[
        SyntheticSimulationExperimentResult,
        SyntheticSimulationExperimentResult,
        SyntheticSimulationExperimentResult,
        SyntheticSimulationExperimentResult,
        SyntheticSimulationExperimentResult,
    ]
    numeric_environment: dict[str, str] = Field(
        alias="numericEnvironment", min_length=1
    )
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    automatic_execution_allowed: Literal[False] = Field(
        alias="automaticExecutionAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "SyntheticSimulationAcquisitionReceipt":
        if tuple(item.rank for item in self.results) != (1, 2, 3, 4, 5):
            raise ValueError("acquisition results must preserve proposal rank order")
        result_ids = tuple(item.experiment_id for item in self.results)
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("acquisition experimentId values must be unique")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match acquisition receipt content")
        return self


class ConditionalEffectMetricDelta(AxiomModel):
    target_id: Literal["cycleTimeSeconds", "linearFollowingErrorMaxMm"] = Field(
        alias="targetId"
    )
    unit: Literal["s", "mm"]
    baseline_model_rmse: float = Field(alias="baselineModelRmse", ge=0.0)
    candidate_model_rmse: float = Field(alias="candidateModelRmse", ge=0.0)
    absolute_change: float = Field(alias="absoluteChange")
    relative_improvement: float = Field(alias="relativeImprovement")
    status: Literal["Improved", "Unchanged", "Regressed"]

    @field_validator(
        "baseline_model_rmse",
        "candidate_model_rmse",
        "absolute_change",
        "relative_improvement",
        mode="before",
    )
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectMetricDelta":
        expected_unit = "s" if self.target_id == "cycleTimeSeconds" else "mm"
        if self.unit != expected_unit:
            raise ValueError("metric delta unit must match targetId")
        expected_change = self.candidate_model_rmse - self.baseline_model_rmse
        if not math.isclose(
            self.absolute_change, expected_change, rel_tol=0.0, abs_tol=1e-15
        ):
            raise ValueError("absoluteChange must equal candidate minus baseline")
        if self.baseline_model_rmse <= 0.0:
            raise ValueError("baselineModelRmse must be positive")
        expected_improvement = 1.0 - (
            self.candidate_model_rmse / self.baseline_model_rmse
        )
        if not math.isclose(
            self.relative_improvement,
            expected_improvement,
            rel_tol=0.0,
            abs_tol=1e-14,
        ):
            raise ValueError("relativeImprovement must match the reported RMSE values")
        expected_status = (
            "Improved"
            if self.absolute_change < -1e-15
            else "Regressed"
            if self.absolute_change > 1e-15
            else "Unchanged"
        )
        if self.status != expected_status:
            raise ValueError("status must match the RMSE change")
        return self


class R5EModelCandidateAssessment(AxiomModel):
    assessment_id: str = Field(alias="assessmentId", pattern=VERSIONED_ID_PATTERN)
    policy_id: Literal["axiom.intelligence.r5e-original-holdout-non-regression@1"] = (
        Field(alias="policyId")
    )
    source_model_bundle_hash: str = Field(
        alias="sourceModelBundleHash", pattern=HASH_PATTERN
    )
    candidate_model_bundle_hash: str = Field(
        alias="candidateModelBundleHash", pattern=HASH_PATTERN
    )
    metric_deltas: tuple[ConditionalEffectMetricDelta, ConditionalEffectMetricDelta] = (
        Field(alias="metricDeltas")
    )
    candidate_gate_status: Literal["Passed", "Failed"] = Field(
        alias="candidateGateStatus"
    )
    eligible_for_manual_promotion: bool = Field(alias="eligibleForManualPromotion")
    model_promotion_status: Literal["NotPerformed"] = Field(
        alias="modelPromotionStatus"
    )
    general_improvement_guarantee: Literal["NotClaimed"] = Field(
        alias="generalImprovementGuarantee"
    )
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "R5EModelCandidateAssessment":
        if tuple(item.target_id for item in self.metric_deltas) != R5C_TARGETS:
            raise ValueError("metricDeltas must keep the frozen target order")
        if self.eligible_for_manual_promotion != (
            self.candidate_gate_status == "Passed"
        ):
            raise ValueError("manual promotion eligibility must match candidate gate")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match candidate assessment content")
        return self


class R5ESyntheticCampaignReport(AxiomModel):
    schema_id: Literal["axiom.intelligence.synthetic-simulation-campaign-report@1"] = (
        Field(alias="schemaId")
    )
    report_id: str = Field(alias="reportId", pattern=VERSIONED_ID_PATTERN)
    campaign_request: R5ESyntheticCampaignRequest = Field(alias="campaignRequest")
    acquisition_receipt: SyntheticSimulationAcquisitionReceipt = Field(
        alias="acquisitionReceipt"
    )
    dataset: ConditionalEffectDatasetV2
    split_manifest: ConditionalEffectSplitManifestV2 = Field(alias="splitManifest")
    model_bundle: ConditionalEffectModelBundleV2 = Field(alias="modelBundle")
    training_receipt: ConditionalEffectTrainingReceiptV2 = Field(
        alias="trainingReceipt"
    )
    parity_receipt: ConditionalEffectParityReceiptV2 = Field(alias="parityReceipt")
    baseline_evaluation: ConditionalEffectEvaluation = Field(alias="baselineEvaluation")
    candidate_evaluation: ConditionalEffectEvaluation = Field(
        alias="candidateEvaluation"
    )
    candidate_assessment: R5EModelCandidateAssessment = Field(
        alias="candidateAssessment"
    )
    next_plan_request: R5DExperimentPlanRequest = Field(alias="nextPlanRequest")
    next_plan: SimulationExperimentPlan = Field(alias="nextPlan")
    campaign_execution_status: Literal["Succeeded"] = Field(
        alias="campaignExecutionStatus"
    )
    model_promotion_status: Literal["NotPerformed"] = Field(
        alias="modelPromotionStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    automatic_execution_allowed: Literal[False] = Field(
        alias="automaticExecutionAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    safety_banner: Literal[
        "SYNTHETIC SIL CAMPAIGN / NOT REALITY VALIDATED / NOT DEVICE SAFE / PROMOTION NOT PERFORMED"
    ] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "R5ESyntheticCampaignReport":
        request = self.campaign_request
        receipt = self.acquisition_receipt
        if receipt.campaign_request_hash != request.content_hash:
            raise ValueError("acquisition receipt must identify campaign request")
        if receipt.approval_content_hash != request.approval.content_hash:
            raise ValueError("acquisition receipt must identify approval")
        source_receipt_identities = (
            (receipt.source_plan_content_hash, request.plan.content_hash),
            (receipt.source_model_bundle_hash, request.plan.model_bundle_hash),
            (receipt.source_dataset_content_hash, request.plan.dataset_content_hash),
            (
                receipt.source_split_manifest_hash,
                request.plan.split_manifest_content_hash,
            ),
        )
        if any(actual != expected for actual, expected in source_receipt_identities):
            raise ValueError("acquisition receipt must identify every campaign source")
        expected_results = tuple(
            (
                proposal.rank,
                proposal.experiment_id,
                proposal.feed_override,
                proposal.sample_period,
            )
            for proposal in request.plan.proposals
        )
        actual_results = tuple(
            (
                result.rank,
                result.experiment_id,
                result.feed_override,
                result.sample_period,
            )
            for result in receipt.results
        )
        if actual_results != expected_results:
            raise ValueError("acquisition results must match proposals in order")
        source_samples = request.plan_request.dataset.samples
        if self.dataset.samples[:25] != source_samples:
            raise ValueError("R5-E dataset must preserve all source samples exactly")
        acquired_ids = tuple(item.sample_id for item in self.dataset.samples[25:])
        expected_acquired_ids = tuple(
            f"r5e-{item.experiment_id.split('@', 1)[0].split('r5d.', 1)[-1]}"
            for item in request.plan.proposals
        )
        if acquired_ids != expected_acquired_ids:
            raise ValueError("R5-E dataset must append samples in proposal order")
        for sample, result in zip(
            self.dataset.samples[25:], receipt.results, strict=True
        ):
            if (
                sample.feed_override,
                sample.sample_period,
                sample.cycle_time_seconds,
                sample.linear_following_error_max_mm,
                sample.command_sample_count,
                sample.m4_content_hash,
                sample.m5_content_hash,
                sample.physical_response_content_hash,
            ) != (
                result.feed_override,
                result.sample_period,
                result.cycle_time_seconds,
                result.linear_following_error_max_mm,
                result.command_sample_count,
                result.m4_content_hash,
                result.m5_content_hash,
                result.physical_response_content_hash,
            ):
                raise ValueError(
                    "R5-E acquired samples must reproduce acquisition results exactly"
                )
        if self.dataset.base_dataset_content_hash != request.plan.dataset_content_hash:
            raise ValueError("R5-E dataset must identify the source dataset")
        if self.dataset.acquisition_receipt_hash != receipt.content_hash:
            raise ValueError("R5-E dataset must identify the acquisition receipt")
        if self.split_manifest.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("R5-E split manifest must identify the dataset")
        if (
            self.split_manifest.base_split_manifest_hash
            != request.plan.split_manifest_content_hash
            or self.split_manifest.acquisition_receipt_hash != receipt.content_hash
        ):
            raise ValueError("R5-E split manifest must identify its source lineage")
        source_partitions = request.plan_request.split_manifest.partitions
        if self.split_manifest.partitions[1:] != source_partitions[1:]:
            raise ValueError("R5-E validation and test partitions must remain frozen")
        if self.split_manifest.partitions[0].sample_ids != (
            source_partitions[0].sample_ids + acquired_ids
        ):
            raise ValueError(
                "R5-E train partition must append acquired samples in proposal order"
            )
        if self.model_bundle.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("candidate bundle must identify R5-E dataset")
        if self.model_bundle.split_manifest_hash != self.split_manifest.content_hash:
            raise ValueError("candidate bundle must identify R5-E split manifest")
        if (
            self.model_bundle.training_receipt_hash
            != self.training_receipt.content_hash
        ):
            raise ValueError("candidate bundle must identify R5-E training receipt")
        training_identities = (
            (self.training_receipt.dataset_content_hash, self.dataset.content_hash),
            (
                self.training_receipt.split_manifest_hash,
                self.split_manifest.content_hash,
            ),
            (
                self.training_receipt.parent_model_bundle_hash,
                request.plan.model_bundle_hash,
            ),
            (
                self.training_receipt.acquisition_receipt_hash,
                receipt.content_hash,
            ),
        )
        if any(actual != expected for actual, expected in training_identities):
            raise ValueError("training receipt must identify candidate training inputs")
        if self.model_bundle.parent_model_bundle_hash != request.plan.model_bundle_hash:
            raise ValueError("candidate bundle must identify its parent model")
        if self.model_bundle.acquisition_receipt_hash != receipt.content_hash:
            raise ValueError("candidate bundle must identify acquisition receipt")
        if self.parity_receipt.model_bundle_hash != self.model_bundle.content_hash:
            raise ValueError("parity receipt must identify candidate model")
        if (
            self.parity_receipt.dataset_content_hash != self.dataset.content_hash
            or self.parity_receipt.acquisition_receipt_hash != receipt.content_hash
        ):
            raise ValueError("parity receipt must identify candidate inputs")
        if (
            self.candidate_assessment.source_model_bundle_hash
            != request.plan.model_bundle_hash
            or self.candidate_assessment.candidate_model_bundle_hash
            != self.model_bundle.content_hash
        ):
            raise ValueError("candidate assessment must identify both compared models")
        expected_metrics = tuple(
            (
                baseline.target_id,
                baseline.unit,
                baseline.model_rmse,
                candidate.model_rmse,
            )
            for baseline, candidate in zip(
                self.baseline_evaluation.head_results,
                self.candidate_evaluation.head_results,
                strict=True,
            )
        )
        actual_metrics = tuple(
            (
                delta.target_id,
                delta.unit,
                delta.baseline_model_rmse,
                delta.candidate_model_rmse,
            )
            for delta in self.candidate_assessment.metric_deltas
        )
        if actual_metrics != expected_metrics:
            raise ValueError("candidate assessment metrics must match both evaluations")
        expected_candidate_gate = (
            self.candidate_evaluation.synthetic_conditional_effect_contract_status
            == "Passed"
            and self.parity_receipt.status == "Passed"
            and all(
                delta.absolute_change <= 1e-15
                for delta in self.candidate_assessment.metric_deltas
            )
        )
        if (self.candidate_assessment.candidate_gate_status == "Passed") != (
            expected_candidate_gate
        ):
            raise ValueError("candidate gate must match evaluation and parity evidence")
        if (
            self.next_plan_request.model_bundle.content_hash
            != self.model_bundle.content_hash
        ):
            raise ValueError("next plan request must use the candidate model")
        next_request_identities = (
            (self.next_plan_request.dataset.content_hash, self.dataset.content_hash),
            (
                self.next_plan_request.split_manifest.content_hash,
                self.split_manifest.content_hash,
            ),
        )
        if any(actual != expected for actual, expected in next_request_identities):
            raise ValueError("next plan request must use all candidate inputs")
        next_plan_identities = (
            (self.next_plan.model_bundle_hash, self.model_bundle.content_hash),
            (self.next_plan.dataset_content_hash, self.dataset.content_hash),
            (
                self.next_plan.split_manifest_content_hash,
                self.split_manifest.content_hash,
            ),
            (self.next_plan.requested_batch_size, self.next_plan_request.batch_size),
        )
        if any(actual != expected for actual, expected in next_plan_identities):
            raise ValueError("next plan must identify the complete next plan request")
        if self.next_plan.experiment_execution_status != "NotExecuted":
            raise ValueError("R5-E must not recursively execute the next plan")
        if (
            self.candidate_assessment.model_promotion_status
            != self.model_promotion_status
        ):
            raise ValueError("report promotion status must match assessment")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match R5-E campaign report content")
        return self


class R5EManifest(AxiomModel):
    manifest_id: Literal["axiom.intelligence.r5e-manifest@1"] = Field(
        alias="manifestId"
    )
    schema_id: Literal["axiom.intelligence.r5e-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["R5-E"]
    platform: Literal["windows"]
    runner_id: Literal["axiom.physical.canonical-f3-f4-r4-replay@1"] = Field(
        alias="runnerId"
    )
    approval_policy_id: Literal[
        "axiom.intelligence.r5e-explicit-offline-approval@1"
    ] = Field(alias="approvalPolicyId")
    fixed_batch_size: Literal[5] = Field(alias="fixedBatchSize")
    base_sample_count: Literal[25] = Field(alias="baseSampleCount")
    acquired_sample_count: Literal[5] = Field(alias="acquiredSampleCount")
    candidate_sample_count: Literal[30] = Field(alias="candidateSampleCount")
    validation_and_test_frozen: Literal[True] = Field(alias="validationAndTestFrozen")
    automatic_model_promotion_allowed: Literal[False] = Field(
        alias="automaticModelPromotionAllowed"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    automatic_execution_allowed: Literal[False] = Field(
        alias="automaticExecutionAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    safety_banner: Literal[
        "SYNTHETIC SIL CAMPAIGN / NOT REALITY VALIDATED / NOT DEVICE SAFE / PROMOTION NOT PERFORMED"
    ] = Field(alias="safetyBanner")


class R5EApprovalRequirements(AxiomModel):
    approval_required: Literal[True] = Field(alias="approvalRequired")
    accountable_party_required: Literal[True] = Field(alias="accountablePartyRequired")
    full_batch_only: Literal[True] = Field(alias="fullBatchOnly")
    synthetic_only_acknowledgement_required: Literal[True] = Field(
        alias="syntheticOnlyAcknowledgementRequired"
    )
    device_authority_granted: Literal[False] = Field(alias="deviceAuthorityGranted")


class R5EExamplePayload(AxiomModel):
    manifest: R5EManifest
    plan_request: R5DExperimentPlanRequest = Field(alias="planRequest")
    plan: SimulationExperimentPlan
    approval_requirements: R5EApprovalRequirements = Field(alias="approvalRequirements")


__all__ = [
    "R5E_APPROVAL_POLICY_ID",
    "R5E_CANDIDATE_GATE_POLICY_ID",
    "R5E_RUNNER_ID",
    "R5E_SAFETY_BANNER",
    "ConditionalEffectMetricDelta",
    "R5EApprovalRequirements",
    "R5ECampaignApprovalCommand",
    "R5EExamplePayload",
    "R5EManifest",
    "R5EModelCandidateAssessment",
    "R5ESyntheticCampaignReport",
    "R5ESyntheticCampaignRequest",
    "SyntheticSimulationAcquisitionReceipt",
    "SyntheticSimulationCampaignApproval",
    "SyntheticSimulationExperimentResult",
]
