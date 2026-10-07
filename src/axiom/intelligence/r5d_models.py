from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel
from .models import HASH_PATTERN, VERSIONED_ID_PATTERN, canonical_hash
from .r5c_models import (
    R5C_FEATURE_ORDER,
    ConditionalEffectDataset,
    ConditionalEffectDatasetV2,
    ConditionalEffectModelBundle,
    ConditionalEffectModelBundleV2,
    ConditionalEffectPredictionInterval,
    ConditionalEffectSplitManifest,
    ConditionalEffectSplitManifestV2,
)

R5D_PLANNER_ID = "axiom.intelligence.greedy-g-optimal-linear-design@1"
R5D_CANDIDATE_POOL_ID = "axiom.optimization.r6v2-grid@1"
R5D_DEFAULT_BATCH_SIZE = 5
R5D_MAXIMUM_BATCH_SIZE = 10
R5D_CANDIDATE_FEED_OVERRIDES = tuple(
    round(0.65 + 0.025 * index, 3) for index in range(15)
)
R5D_CANDIDATE_SAMPLE_PERIODS = tuple(
    round(0.04 + 0.005 * index, 3) for index in range(9)
)
R5D_CANDIDATE_POOL_SIZE = 135
R5D_DEFAULT_AVAILABLE_CANDIDATE_COUNT = 110
R5D_SAFETY_BANNER = (
    "SYNTHETIC EXPERIMENT PLAN / NOT EXECUTED / NOT REALITY VALIDATED / NOT DEVICE SAFE"
)


def _finite(value: Any) -> Any:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("value must be a finite JSON number")
    return value


class R5DExperimentPlanRequest(AxiomModel):
    schema_id: Literal["axiom.intelligence.simulation-experiment-plan-request@1"] = (
        Field(
            default="axiom.intelligence.simulation-experiment-plan-request@1",
            alias="schemaId",
        )
    )
    model_bundle: ConditionalEffectModelBundle | ConditionalEffectModelBundleV2 = Field(
        alias="modelBundle"
    )
    dataset: ConditionalEffectDataset | ConditionalEffectDatasetV2
    split_manifest: (
        ConditionalEffectSplitManifest | ConditionalEffectSplitManifestV2
    ) = Field(alias="splitManifest")
    batch_size: int = Field(
        default=R5D_DEFAULT_BATCH_SIZE,
        alias="batchSize",
        ge=1,
        le=R5D_MAXIMUM_BATCH_SIZE,
    )

    @model_validator(mode="after")
    def validate_source_contract(self) -> "R5DExperimentPlanRequest":
        if (
            len(
                {
                    self.model_bundle.schema_version,
                    self.dataset.schema_version,
                    self.split_manifest.schema_version,
                }
            )
            != 1
        ):
            raise ValueError("R5-D source schema versions must match")
        if self.model_bundle.synthetic_conditional_effect_contract_status != "Passed":
            raise ValueError("R5-D requires a Passed R5-C model bundle")
        if self.model_bundle.feature_order != R5C_FEATURE_ORDER:
            raise ValueError("R5-D requires the frozen R5-C feature order")
        if self.model_bundle.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("model bundle must identify the request dataset")
        if self.model_bundle.split_manifest_hash != self.split_manifest.content_hash:
            raise ValueError("model bundle must identify the request split manifest")
        if self.split_manifest.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("split manifest must identify the request dataset")
        sample_by_id = {sample.sample_id: sample for sample in self.dataset.samples}
        for partition in self.split_manifest.partitions:
            for sample_id in partition.sample_ids:
                sample = sample_by_id.get(sample_id)
                if sample is None:
                    raise ValueError("split manifest references an unknown sample")
                if sample.declared_split_id != partition.split_id:
                    raise ValueError(
                        "split partition must match each sample declared split"
                    )
        assigned = {
            sample_id
            for partition in self.split_manifest.partitions
            for sample_id in partition.sample_ids
        }
        if assigned != set(sample_by_id):
            raise ValueError(
                "split manifest must cover every dataset sample exactly once"
            )
        candidate_points = {
            (feed, period)
            for feed in R5D_CANDIDATE_FEED_OVERRIDES
            for period in R5D_CANDIDATE_SAMPLE_PERIODS
        }
        observed_points = {
            (sample.feed_override, sample.sample_period)
            for sample in self.dataset.samples
        }
        if not observed_points.issubset(candidate_points):
            raise ValueError("dataset points must belong to the frozen candidate pool")
        if self.batch_size > len(candidate_points - observed_points):
            raise ValueError("batchSize exceeds available unobserved candidates")
        return self


class SimulationExperimentProposal(AxiomModel):
    rank: int = Field(ge=1, le=R5D_MAXIMUM_BATCH_SIZE)
    experiment_id: str = Field(alias="experimentId", pattern=VERSIONED_ID_PATTERN)
    feed_override: float = Field(alias="feedOverride")
    sample_period: float = Field(alias="samplePeriod")
    feed_override_unit: Literal["ratio"] = Field(alias="feedOverrideUnit")
    sample_period_unit: Literal["s"] = Field(alias="samplePeriodUnit")
    design_leverage: float = Field(alias="designLeverage", ge=0.0)
    predicted_outcomes: tuple[
        ConditionalEffectPredictionInterval,
        ConditionalEffectPredictionInterval,
    ] = Field(alias="predictedOutcomes")
    estimated_command_sample_count: int = Field(
        alias="estimatedCommandSampleCount", ge=2
    )
    planned_runner_id: Literal["axiom.physical.canonical-f3-f4-r4-replay@1"] = Field(
        alias="plannedRunnerId"
    )
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    label_status: Literal["NotAcquired"] = Field(alias="labelStatus")
    automatic_execution_allowed: Literal[False] = Field(
        alias="automaticExecutionAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")

    @field_validator("feed_override", "sample_period", "design_leverage", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_contract(self) -> "SimulationExperimentProposal":
        if self.feed_override not in R5D_CANDIDATE_FEED_OVERRIDES:
            raise ValueError("feedOverride must belong to the frozen candidate pool")
        if self.sample_period not in R5D_CANDIDATE_SAMPLE_PERIODS:
            raise ValueError("samplePeriod must belong to the frozen candidate pool")
        if tuple(item.target_id for item in self.predicted_outcomes) != (
            "cycleTimeSeconds",
            "linearFollowingErrorMaxMm",
        ):
            raise ValueError(
                "predicted outcomes must keep the two R5-C targets ordered"
            )
        return self


class SimulationExperimentPlan(AxiomModel):
    schema_id: Literal["axiom.intelligence.simulation-experiment-plan@1"] = Field(
        alias="schemaId"
    )
    plan_id: str = Field(alias="planId", pattern=VERSIONED_ID_PATTERN)
    planner_id: Literal["axiom.intelligence.greedy-g-optimal-linear-design@1"] = Field(
        alias="plannerId"
    )
    candidate_pool_id: Literal["axiom.optimization.r6v2-grid@1"] = Field(
        alias="candidatePoolId"
    )
    model_bundle_hash: str = Field(alias="modelBundleHash", pattern=HASH_PATTERN)
    dataset_content_hash: str = Field(alias="datasetContentHash", pattern=HASH_PATTERN)
    split_manifest_content_hash: str = Field(
        alias="splitManifestContentHash", pattern=HASH_PATTERN
    )
    status: Literal["Planned", "Blocked"]
    reason_codes: tuple[str, ...] = Field(default=(), alias="reasonCodes")
    candidate_pool_size: Literal[135] = Field(alias="candidatePoolSize")
    available_candidate_count: int = Field(alias="availableCandidateCount", ge=0)
    design_sample_count: int = Field(alias="designSampleCount", ge=1)
    excluded_observed_point_count: int = Field(alias="excludedObservedPointCount", ge=1)
    requested_batch_size: int = Field(
        alias="requestedBatchSize", ge=1, le=R5D_MAXIMUM_BATCH_SIZE
    )
    proposals: tuple[SimulationExperimentProposal, ...]
    maximum_candidate_leverage_before: float | None = Field(
        default=None, alias="maximumCandidateLeverageBefore", ge=0.0
    )
    maximum_candidate_leverage_after: float | None = Field(
        default=None, alias="maximumCandidateLeverageAfter", ge=0.0
    )
    relative_maximum_leverage_reduction: float | None = Field(
        default=None,
        alias="relativeMaximumLeverageReduction",
        ge=0.0,
        le=1.0,
    )
    uncertainty_scope: Literal["linear-design-epistemic-proxy"] = Field(
        alias="uncertaintyScope"
    )
    global_optimality_status: Literal["NotClaimed"] = Field(
        alias="globalOptimalityStatus"
    )
    experiment_execution_status: Literal["NotExecuted"] = Field(
        alias="experimentExecutionStatus"
    )
    model_update_status: Literal["NotPerformed"] = Field(alias="modelUpdateStatus")
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    automatic_execution_allowed: Literal[False] = Field(
        alias="automaticExecutionAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    known_limitations: tuple[str, ...] = Field(alias="knownLimitations", min_length=1)
    safety_banner: Literal[
        "SYNTHETIC EXPERIMENT PLAN / NOT EXECUTED / NOT REALITY VALIDATED / NOT DEVICE SAFE"
    ] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator(
        "maximum_candidate_leverage_before",
        "maximum_candidate_leverage_after",
        "relative_maximum_leverage_reduction",
        mode="before",
    )
    @classmethod
    def reject_non_finite_optional(cls, value: Any) -> Any:
        if value is not None:
            _finite(value)
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> "SimulationExperimentPlan":
        if (
            self.available_candidate_count + self.excluded_observed_point_count
            != self.candidate_pool_size
        ):
            raise ValueError(
                "available and excluded candidate counts must cover the candidate pool"
            )
        if self.design_sample_count > self.excluded_observed_point_count:
            raise ValueError("designSampleCount cannot exceed observed point count")
        if self.status == "Blocked":
            if not self.reason_codes:
                raise ValueError("Blocked plan must provide reasonCodes")
            if self.proposals:
                raise ValueError("Blocked plan cannot contain proposals")
            if any(
                value is not None
                for value in (
                    self.maximum_candidate_leverage_before,
                    self.maximum_candidate_leverage_after,
                    self.relative_maximum_leverage_reduction,
                )
            ):
                raise ValueError("Blocked plan cannot report leverage results")
        else:
            if self.reason_codes:
                raise ValueError("Planned plan cannot provide reasonCodes")
            if len(self.proposals) != self.requested_batch_size:
                raise ValueError("proposal count must match requestedBatchSize")
            if self.requested_batch_size > self.available_candidate_count:
                raise ValueError("requestedBatchSize exceeds available candidates")
            if tuple(item.rank for item in self.proposals) != tuple(
                range(1, self.requested_batch_size + 1)
            ):
                raise ValueError("proposal ranks must be contiguous and ordered")
            proposal_points = tuple(
                (item.feed_override, item.sample_period) for item in self.proposals
            )
            if len(proposal_points) != len(set(proposal_points)):
                raise ValueError("proposal parameter points must be unique")
            if any(
                value is None
                for value in (
                    self.maximum_candidate_leverage_before,
                    self.maximum_candidate_leverage_after,
                    self.relative_maximum_leverage_reduction,
                )
            ):
                raise ValueError("Planned plan must report leverage results")
            before = self.maximum_candidate_leverage_before
            after = self.maximum_candidate_leverage_after
            reduction = self.relative_maximum_leverage_reduction
            assert before is not None and after is not None and reduction is not None
            if not after < before:
                raise ValueError("planned batch must reduce maximum candidate leverage")
            expected = 1.0 - after / before
            if not math.isclose(reduction, expected, rel_tol=0.0, abs_tol=1e-14):
                raise ValueError("relative leverage reduction must match before/after")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match SimulationExperimentPlan content")
        return self


class R5DManifest(AxiomModel):
    manifest_id: Literal["axiom.intelligence.r5d-manifest@1"] = Field(
        alias="manifestId"
    )
    schema_id: Literal["axiom.intelligence.r5d-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["R5-D"]
    platform: Literal["windows"]
    planner_id: Literal["axiom.intelligence.greedy-g-optimal-linear-design@1"] = Field(
        alias="plannerId"
    )
    candidate_pool_id: Literal["axiom.optimization.r6v2-grid@1"] = Field(
        alias="candidatePoolId"
    )
    candidate_pool_size: Literal[135] = Field(alias="candidatePoolSize")
    default_available_candidate_count: Literal[110] = Field(
        alias="defaultAvailableCandidateCount"
    )
    default_batch_size: Literal[5] = Field(alias="defaultBatchSize")
    maximum_batch_size: Literal[10] = Field(alias="maximumBatchSize")
    design_feature_count: Literal[6] = Field(alias="designFeatureCount")
    design_partition: Literal["train"] = Field(alias="designPartition")
    selection_objective: Literal["maximum-design-leverage"] = Field(
        alias="selectionObjective"
    )
    global_optimality_status: Literal["NotClaimed"] = Field(
        alias="globalOptimalityStatus"
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
        "SYNTHETIC EXPERIMENT PLAN / NOT EXECUTED / NOT REALITY VALIDATED / NOT DEVICE SAFE"
    ] = Field(alias="safetyBanner")


class R5DExamplePayload(AxiomModel):
    manifest: R5DManifest
    request: R5DExperimentPlanRequest
    plan: SimulationExperimentPlan


__all__ = [
    "R5D_CANDIDATE_FEED_OVERRIDES",
    "R5D_CANDIDATE_POOL_ID",
    "R5D_CANDIDATE_POOL_SIZE",
    "R5D_CANDIDATE_SAMPLE_PERIODS",
    "R5D_DEFAULT_AVAILABLE_CANDIDATE_COUNT",
    "R5D_DEFAULT_BATCH_SIZE",
    "R5D_MAXIMUM_BATCH_SIZE",
    "R5D_PLANNER_ID",
    "R5D_SAFETY_BANNER",
    "R5DExamplePayload",
    "R5DExperimentPlanRequest",
    "R5DManifest",
    "SimulationExperimentPlan",
    "SimulationExperimentProposal",
]
