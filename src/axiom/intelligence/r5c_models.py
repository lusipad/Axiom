from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel, EvaluationCase, RunSpec
from .models import (
    HASH_PATTERN,
    VERSIONED_ID_PATTERN,
    EvaluationClaim,
    EvaluationEvidence,
    canonical_hash,
)

R5C_DOMAIN_PACK_ID = "intelligence.domain-pack@3"
R5C_EVALUATOR_ID = "intelligence-conditional-effect-evaluator@1"
R5C_RUNNER_ID = "intelligence-conditional-effect-validation@1"
R5C_TARGET_INTERPRETER_ID = "axiom.intelligence.conditional-effect-interpreter.python@1"
R5C_DEFAULT_SCENARIO_ID = "canonical-head-table-conditional-effect"

R5C_FEED_OVERRIDES = (0.65, 0.725, 0.80, 0.90, 1.00)
R5C_SAMPLE_PERIODS = (0.04, 0.05, 0.06, 0.07, 0.08)
R5C_SPLITS = ("train", "validation", "test")
R5C_TARGETS = ("cycleTimeSeconds", "linearFollowingErrorMaxMm")
R5C_FEATURE_ORDER = (
    "bias",
    "normalizedInverseFeed",
    "normalizedSamplePeriod",
    "interaction",
    "samplePeriodSquared",
    "inverseFeedSquared",
)


def _finite(value: Any) -> Any:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("value must be a finite JSON number")
    return value


class ConditionalEffectDomain(AxiomModel):
    domain_id: Literal["axiom.intelligence.r5c-parameter-domain@1"] = Field(
        alias="domainId"
    )
    feed_override_minimum: Literal[0.65] = Field(alias="feedOverrideMinimum")
    feed_override_maximum: Literal[1.0] = Field(alias="feedOverrideMaximum")
    sample_period_minimum: Literal[0.04] = Field(alias="samplePeriodMinimum")
    sample_period_maximum: Literal[0.08] = Field(alias="samplePeriodMaximum")
    feed_override_unit: Literal["ratio"] = Field(alias="feedOverrideUnit")
    sample_period_unit: Literal["s"] = Field(alias="samplePeriodUnit")

    def contains(self, feed_override: float, sample_period: float) -> bool:
        return (
            self.feed_override_minimum <= feed_override <= self.feed_override_maximum
            and self.sample_period_minimum
            <= sample_period
            <= self.sample_period_maximum
        )


class ConditionalEffectSample(AxiomModel):
    sample_id: str = Field(alias="sampleId", min_length=1)
    feed_override: float = Field(alias="feedOverride")
    sample_period: float = Field(alias="samplePeriod")
    declared_split_id: Literal["train", "validation", "test"] = Field(
        alias="declaredSplitId"
    )
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
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    source_scenario_id: Literal["canonical-head-table-solver"] = Field(
        alias="sourceScenarioId"
    )

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


class ConditionalEffectGovernance(AxiomModel):
    governance_id: str = Field(alias="governanceId", pattern=VERSIONED_ID_PATTERN)
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    synthetic_conditional_effect_contract_status: Literal["Open"] = Field(
        alias="syntheticConditionalEffectContractStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    license_id: str = Field(alias="licenseId", min_length=1)
    allowed_uses: tuple[str, ...] = Field(alias="allowedUses", min_length=1)
    sensitivity: Literal["synthetic"]
    retention_policy_id: str = Field(
        alias="retentionPolicyId", pattern=VERSIONED_ID_PATTERN
    )
    redistribution_allowed: Literal[False] = Field(alias="redistributionAllowed")
    safety_banner: Literal[
        "SYNTHETIC CONDITIONAL EFFECT / NOT REALITY VALIDATED / NOT DEVICE SAFE"
    ] = Field(alias="safetyBanner")


class ConditionalEffectDataset(AxiomModel):
    artifact_type: Literal["axiom.intelligence.conditional-effect-dataset"] = Field(
        alias="artifactType"
    )
    schema_id: Literal["axiom.intelligence.conditional-effect-dataset@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    dataset_id: str = Field(alias="datasetId", pattern=VERSIONED_ID_PATTERN)
    domain: ConditionalEffectDomain
    governance: ConditionalEffectGovernance
    selection_policy_id: Literal["axiom.intelligence.r5c-spatial-split-policy@1"] = (
        Field(alias="selectionPolicyId")
    )
    lineage_policy_id: Literal["axiom.intelligence.r5c-m4-m5-physical-lineage@1"] = (
        Field(alias="lineagePolicyId")
    )
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    known_biases: tuple[str, ...] = Field(alias="knownBiases", min_length=1)
    coverage_gaps: tuple[str, ...] = Field(alias="coverageGaps", min_length=1)
    samples: tuple[ConditionalEffectSample, ...] = Field(min_length=25, max_length=25)
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectDataset":
        sample_ids = tuple(sample.sample_id for sample in self.samples)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("ConditionalEffectDataset sampleId values must be unique")
        points = tuple(
            (sample.feed_override, sample.sample_period) for sample in self.samples
        )
        expected_points = tuple(
            (feed, period)
            for feed in R5C_FEED_OVERRIDES
            for period in R5C_SAMPLE_PERIODS
        )
        if points != expected_points:
            raise ValueError(
                "ConditionalEffectDataset must freeze the ordered 5x5 parameter grid"
            )
        if any(
            not self.domain.contains(sample.feed_override, sample.sample_period)
            for sample in self.samples
        ):
            raise ValueError("ConditionalEffectDataset samples must stay inside domain")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match ConditionalEffectDataset content")
        return self


class ConditionalEffectDatasetV2(ConditionalEffectDataset):
    schema_id: Literal["axiom.intelligence.conditional-effect-dataset@2"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[2] = Field(alias="schemaVersion")
    selection_policy_id: Literal[
        "axiom.intelligence.r5e-append-train-only-policy@1"
    ] = Field(alias="selectionPolicyId")
    lineage_policy_id: Literal["axiom.intelligence.r5e-campaign-lineage@1"] = Field(
        alias="lineagePolicyId"
    )
    samples: tuple[ConditionalEffectSample, ...] = Field(min_length=30, max_length=30)
    base_dataset_content_hash: str = Field(
        alias="baseDatasetContentHash", pattern=HASH_PATTERN
    )
    acquisition_receipt_hash: str = Field(
        alias="acquisitionReceiptHash", pattern=HASH_PATTERN
    )

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectDatasetV2":
        sample_ids = tuple(sample.sample_id for sample in self.samples)
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError(
                "ConditionalEffectDatasetV2 sampleId values must be unique"
            )
        points = tuple(
            (sample.feed_override, sample.sample_period) for sample in self.samples
        )
        if len(points) != len(set(points)):
            raise ValueError(
                "ConditionalEffectDatasetV2 parameter points must be unique"
            )
        expected_base_points = tuple(
            (feed, period)
            for feed in R5C_FEED_OVERRIDES
            for period in R5C_SAMPLE_PERIODS
        )
        if points[:25] != expected_base_points:
            raise ValueError(
                "ConditionalEffectDatasetV2 must preserve the ordered R5-C base grid"
            )
        if any(sample.declared_split_id != "train" for sample in self.samples[25:]):
            raise ValueError("R5-E acquired samples must only enter the train split")
        if any(
            not self.domain.contains(sample.feed_override, sample.sample_period)
            for sample in self.samples
        ):
            raise ValueError(
                "ConditionalEffectDatasetV2 samples must stay inside domain"
            )
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError(
                "contentHash must match ConditionalEffectDatasetV2 content"
            )
        return self


class ConditionalEffectPartition(AxiomModel):
    split_id: Literal["train", "validation", "test"] = Field(alias="splitId")
    sample_ids: tuple[str, ...] = Field(alias="sampleIds", min_length=1)


class ConditionalEffectSplitManifest(AxiomModel):
    artifact_type: Literal["axiom.intelligence.conditional-effect-split-manifest"] = (
        Field(alias="artifactType")
    )
    schema_id: Literal["axiom.intelligence.conditional-effect-split-manifest@1"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    manifest_id: str = Field(alias="manifestId", pattern=VERSIONED_ID_PATTERN)
    dataset_content_hash: str = Field(alias="datasetContentHash", pattern=HASH_PATTERN)
    partitions: tuple[
        ConditionalEffectPartition,
        ConditionalEffectPartition,
        ConditionalEffectPartition,
    ]
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectSplitManifest":
        if tuple(partition.split_id for partition in self.partitions) != R5C_SPLITS:
            raise ValueError("partitions must freeze train/validation/test in order")
        assigned = tuple(
            sample_id
            for partition in self.partitions
            for sample_id in partition.sample_ids
        )
        if len(assigned) != len(set(assigned)):
            raise ValueError("split partitions must be sample-disjoint")
        if tuple(len(partition.sample_ids) for partition in self.partitions) != (
            15,
            5,
            5,
        ):
            raise ValueError("split partitions must freeze 15/5/5 samples")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match split manifest content")
        return self


class ConditionalEffectSplitManifestV2(ConditionalEffectSplitManifest):
    schema_id: Literal["axiom.intelligence.conditional-effect-split-manifest@2"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[2] = Field(alias="schemaVersion")
    base_split_manifest_hash: str = Field(
        alias="baseSplitManifestHash", pattern=HASH_PATTERN
    )
    acquisition_receipt_hash: str = Field(
        alias="acquisitionReceiptHash", pattern=HASH_PATTERN
    )

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectSplitManifestV2":
        if tuple(partition.split_id for partition in self.partitions) != R5C_SPLITS:
            raise ValueError("partitions must freeze train/validation/test in order")
        assigned = tuple(
            sample_id
            for partition in self.partitions
            for sample_id in partition.sample_ids
        )
        if len(assigned) != len(set(assigned)):
            raise ValueError("split partitions must be sample-disjoint")
        if tuple(len(partition.sample_ids) for partition in self.partitions) != (
            20,
            5,
            5,
        ):
            raise ValueError("R5-E split partitions must freeze 20/5/5 samples")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match R5-E split manifest content")
        return self


class ConditionalEffectResourceBudget(AxiomModel):
    target_runtime: Literal["pure-python"] = Field(alias="targetRuntime")
    feature_count: Literal[6] = Field(alias="featureCount")
    output_count: Literal[2] = Field(alias="outputCount")
    deterministic_numeric_type: Literal["float64"] = Field(
        alias="deterministicNumericType"
    )
    weight_decimal_places: Literal[15] = Field(alias="weightDecimalPlaces")


class ConditionalEffectTrainingReceipt(AxiomModel):
    artifact_type: Literal["axiom.intelligence.conditional-effect-training-receipt"] = (
        Field(alias="artifactType")
    )
    schema_id: Literal["axiom.intelligence.conditional-effect-training-receipt@1"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    receipt_id: str = Field(alias="receiptId", pattern=VERSIONED_ID_PATTERN)
    method_id: Literal["axiom.intelligence.r5c-ridge-regression@1"] = Field(
        alias="methodId"
    )
    dataset_content_hash: str = Field(alias="datasetContentHash", pattern=HASH_PATTERN)
    split_manifest_hash: str = Field(alias="splitManifestHash", pattern=HASH_PATTERN)
    feature_order: tuple[str, str, str, str, str, str] = Field(alias="featureOrder")
    target_ids: tuple[str, str] = Field(alias="targetIds")
    lambda_value: Literal[0.000001] = Field(alias="lambdaValue")
    train_sample_count: Literal[15] = Field(alias="trainSampleCount")
    validation_sample_count: Literal[5] = Field(alias="validationSampleCount")
    test_sample_count: Literal[5] = Field(alias="testSampleCount")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectTrainingReceipt":
        if self.feature_order != R5C_FEATURE_ORDER:
            raise ValueError("featureOrder must match the frozen R5-C feature map")
        if self.target_ids != R5C_TARGETS:
            raise ValueError("targetIds must keep seconds and millimetres separate")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match training receipt content")
        return self


class ConditionalEffectTrainingReceiptV2(ConditionalEffectTrainingReceipt):
    schema_id: Literal["axiom.intelligence.conditional-effect-training-receipt@2"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[2] = Field(alias="schemaVersion")
    train_sample_count: Literal[20] = Field(alias="trainSampleCount")
    parent_model_bundle_hash: str = Field(
        alias="parentModelBundleHash", pattern=HASH_PATTERN
    )
    acquisition_receipt_hash: str = Field(
        alias="acquisitionReceiptHash", pattern=HASH_PATTERN
    )

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectTrainingReceiptV2":
        if self.feature_order != R5C_FEATURE_ORDER:
            raise ValueError("featureOrder must match the frozen R5-C feature map")
        if self.target_ids != R5C_TARGETS:
            raise ValueError("targetIds must keep seconds and millimetres separate")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match R5-E training receipt content")
        return self


class ConditionalEffectHead(AxiomModel):
    target_id: Literal["cycleTimeSeconds", "linearFollowingErrorMaxMm"] = Field(
        alias="targetId"
    )
    unit: Literal["s", "mm"]
    weights: tuple[float, float, float, float, float, float]
    conformal_radius: float = Field(alias="conformalRadius", ge=0.0)

    @field_validator("weights", mode="before")
    @classmethod
    def reject_non_finite_weights(cls, value: Any) -> Any:
        if isinstance(value, (tuple, list)):
            for item in value:
                _finite(item)
        return value

    @field_validator("conformal_radius", mode="before")
    @classmethod
    def reject_non_finite_radius(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def require_target_unit(self) -> "ConditionalEffectHead":
        expected = {"cycleTimeSeconds": "s", "linearFollowingErrorMaxMm": "mm"}
        if self.unit != expected[self.target_id]:
            raise ValueError("head unit must match targetId")
        return self


class ConditionalEffectModelBundle(AxiomModel):
    artifact_type: Literal["axiom.intelligence.conditional-effect-model-bundle"] = (
        Field(alias="artifactType")
    )
    schema_id: Literal["axiom.intelligence.conditional-effect-model-bundle@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    bundle_id: str = Field(alias="bundleId", pattern=VERSIONED_ID_PATTERN)
    domain_pack_id: Literal["intelligence.domain-pack@3"] = Field(alias="domainPackId")
    evaluator_version: Literal["intelligence-conditional-effect-evaluator@1"] = Field(
        alias="evaluatorVersion"
    )
    target_interpreter_id: Literal[
        "axiom.intelligence.conditional-effect-interpreter.python@1"
    ] = Field(alias="targetInterpreterId")
    input_contract_id: Literal["axiom.intelligence.conditional-effect-input@1"] = Field(
        alias="inputContractId"
    )
    output_contract_id: Literal[
        "axiom.intelligence.conditional-effect-intervals-with-abstention@1"
    ] = Field(alias="outputContractId")
    dataset_content_hash: str = Field(alias="datasetContentHash", pattern=HASH_PATTERN)
    split_manifest_hash: str = Field(alias="splitManifestHash", pattern=HASH_PATTERN)
    training_receipt_hash: str = Field(
        alias="trainingReceiptHash", pattern=HASH_PATTERN
    )
    domain: ConditionalEffectDomain
    feature_order: tuple[str, str, str, str, str, str] = Field(alias="featureOrder")
    heads: tuple[ConditionalEffectHead, ConditionalEffectHead]
    resource_budget: ConditionalEffectResourceBudget = Field(alias="resourceBudget")
    synthetic_conditional_effect_contract_status: Literal["Passed", "Failed"] = Field(
        alias="syntheticConditionalEffectContractStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    safety_banner: Literal[
        "SYNTHETIC CONDITIONAL EFFECT / NOT REALITY VALIDATED / NOT DEVICE SAFE"
    ] = Field(alias="safetyBanner")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectModelBundle":
        if self.feature_order != R5C_FEATURE_ORDER:
            raise ValueError("featureOrder must match the frozen R5-C feature map")
        if tuple(head.target_id for head in self.heads) != R5C_TARGETS:
            raise ValueError("heads must keep cycle time and linear error separate")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError(
                "contentHash must match ConditionalEffectModelBundle content"
            )
        return self


class ConditionalEffectModelBundleV2(ConditionalEffectModelBundle):
    schema_id: Literal["axiom.intelligence.conditional-effect-model-bundle@2"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[2] = Field(alias="schemaVersion")
    parent_model_bundle_hash: str = Field(
        alias="parentModelBundleHash", pattern=HASH_PATTERN
    )
    acquisition_receipt_hash: str = Field(
        alias="acquisitionReceiptHash", pattern=HASH_PATTERN
    )

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectModelBundleV2":
        if self.feature_order != R5C_FEATURE_ORDER:
            raise ValueError("featureOrder must match the frozen R5-C feature map")
        if tuple(head.target_id for head in self.heads) != R5C_TARGETS:
            raise ValueError("heads must keep cycle time and linear error separate")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match R5-E model bundle content")
        return self


class ConditionalEffectParityReceipt(AxiomModel):
    artifact_type: Literal["axiom.intelligence.conditional-effect-parity-receipt"] = (
        Field(alias="artifactType")
    )
    schema_id: Literal["axiom.intelligence.conditional-effect-parity-receipt@1"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    receipt_id: str = Field(alias="receiptId", pattern=VERSIONED_ID_PATTERN)
    model_bundle_hash: str = Field(alias="modelBundleHash", pattern=HASH_PATTERN)
    dataset_content_hash: str = Field(alias="datasetContentHash", pattern=HASH_PATTERN)
    max_abs_gap: float = Field(alias="maxAbsGap", ge=0.0)
    sample_count: Literal[25] = Field(alias="sampleCount")
    target_count: Literal[2] = Field(alias="targetCount")
    status: Literal["Passed", "Failed"]
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("max_abs_gap", mode="before")
    @classmethod
    def reject_non_finite_gap(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectParityReceipt":
        expected = "Passed" if self.max_abs_gap <= 1e-12 else "Failed"
        if self.status != expected:
            raise ValueError("status must match the 1e-12 parity tolerance")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match parity receipt content")
        return self


class ConditionalEffectParityReceiptV2(ConditionalEffectParityReceipt):
    schema_id: Literal["axiom.intelligence.conditional-effect-parity-receipt@2"] = (
        Field(alias="schemaId")
    )
    schema_version: Literal[2] = Field(alias="schemaVersion")
    sample_count: Literal[30] = Field(alias="sampleCount")
    acquisition_receipt_hash: str = Field(
        alias="acquisitionReceiptHash", pattern=HASH_PATTERN
    )

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectParityReceiptV2":
        expected = "Passed" if self.max_abs_gap <= 1e-12 else "Failed"
        if self.status != expected:
            raise ValueError("status must match the 1e-12 parity tolerance")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match R5-E parity receipt content")
        return self


class ConditionalEffectPredictionRequest(AxiomModel):
    model_bundle: ConditionalEffectModelBundle | ConditionalEffectModelBundleV2 = Field(
        alias="modelBundle"
    )
    feed_override: float = Field(alias="feedOverride")
    sample_period: float = Field(alias="samplePeriod")

    @field_validator("feed_override", "sample_period", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)


class ConditionalEffectPredictionInterval(AxiomModel):
    target_id: Literal["cycleTimeSeconds", "linearFollowingErrorMaxMm"] = Field(
        alias="targetId"
    )
    unit: Literal["s", "mm"]
    value: float
    lower: float
    upper: float

    @field_validator("value", "lower", "upper", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def require_ordered_interval(self) -> "ConditionalEffectPredictionInterval":
        if not self.lower <= self.value <= self.upper:
            raise ValueError("prediction interval must contain value")
        expected = {"cycleTimeSeconds": "s", "linearFollowingErrorMaxMm": "mm"}
        if self.unit != expected[self.target_id]:
            raise ValueError("prediction unit must match targetId")
        return self


class ConditionalEffectPrediction(AxiomModel):
    schema_id: Literal["axiom.intelligence.conditional-effect-prediction@1"] = Field(
        alias="schemaId"
    )
    model_bundle_hash: str = Field(alias="modelBundleHash", pattern=HASH_PATTERN)
    feed_override: float = Field(alias="feedOverride")
    sample_period: float = Field(alias="samplePeriod")
    status: Literal["Predicted", "Abstained"]
    predictions: tuple[ConditionalEffectPredictionInterval, ...]
    reason_code: Literal["OutsideDeclaredDomain"] | None = Field(
        default=None, alias="reasonCode"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("feed_override", "sample_period", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_contract(self) -> "ConditionalEffectPrediction":
        if self.status == "Predicted":
            if tuple(item.target_id for item in self.predictions) != R5C_TARGETS:
                raise ValueError("Predicted response must contain both frozen targets")
            if self.reason_code is not None:
                raise ValueError("Predicted response must not contain reasonCode")
        elif self.predictions or self.reason_code != "OutsideDeclaredDomain":
            raise ValueError(
                "Abstained response must contain only OutsideDeclaredDomain reason"
            )
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match prediction content")
        return self


class ConditionalEffectHeadResult(AxiomModel):
    target_id: Literal["cycleTimeSeconds", "linearFollowingErrorMaxMm"] = Field(
        alias="targetId"
    )
    unit: Literal["s", "mm"]
    baseline_rmse: float = Field(alias="baselineRmse", ge=0.0)
    model_rmse: float = Field(alias="modelRmse", ge=0.0)
    normalized_rmse: float = Field(alias="normalizedRmse", ge=0.0)
    improvement_ratio: float = Field(alias="improvementRatio")
    conformal_coverage: float = Field(alias="conformalCoverage", ge=0.0, le=1.0)

    @field_validator(
        "baseline_rmse",
        "model_rmse",
        "normalized_rmse",
        "improvement_ratio",
        "conformal_coverage",
        mode="before",
    )
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)


class ConditionalEffectEvaluation(AxiomModel):
    synthetic_conditional_effect_contract_status: Literal["Passed", "Failed"] = Field(
        alias="syntheticConditionalEffectContractStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    head_results: tuple[ConditionalEffectHeadResult, ConditionalEffectHeadResult] = (
        Field(alias="headResults")
    )
    ood_abstention_rate: float = Field(alias="oodAbstentionRate", ge=0.0, le=1.0)
    target_parity_max_abs_gap: float = Field(alias="targetParityMaxAbsGap", ge=0.0)
    claims: tuple[EvaluationClaim, ...] = Field(min_length=2)
    evidence: tuple[EvaluationEvidence, ...] = Field(min_length=3)

    @field_validator("ood_abstention_rate", "target_parity_max_abs_gap", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def freeze_target_order(self) -> "ConditionalEffectEvaluation":
        if tuple(item.target_id for item in self.head_results) != R5C_TARGETS:
            raise ValueError("headResults must keep the frozen target order")
        return self


class ConditionalEffectEvaluationRequest(AxiomModel):
    artifact: ConditionalEffectModelBundle | ConditionalEffectModelBundleV2
    dataset: ConditionalEffectDataset | ConditionalEffectDatasetV2
    split_manifest: (
        ConditionalEffectSplitManifest | ConditionalEffectSplitManifestV2
    ) = Field(alias="splitManifest")
    training_receipt: (
        ConditionalEffectTrainingReceipt | ConditionalEffectTrainingReceiptV2
    ) = Field(alias="trainingReceipt")
    parity_receipt: (
        ConditionalEffectParityReceipt | ConditionalEffectParityReceiptV2
    ) = Field(alias="parityReceipt")
    case: EvaluationCase

    @model_validator(mode="after")
    def validate_cross_object_contract(self) -> "ConditionalEffectEvaluationRequest":
        samples = {sample.sample_id: sample for sample in self.dataset.samples}
        assigned = {
            sample_id
            for partition in self.split_manifest.partitions
            for sample_id in partition.sample_ids
        }
        if assigned != set(samples):
            raise ValueError("split manifest must assign every dataset sample once")
        for partition in self.split_manifest.partitions:
            if any(
                samples[sample_id].declared_split_id != partition.split_id
                for sample_id in partition.sample_ids
            ):
                raise ValueError(
                    "split manifest sampleIds must respect dataset declared split"
                )
        if self.artifact.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("model bundle must identify dataset")
        if self.artifact.split_manifest_hash != self.split_manifest.content_hash:
            raise ValueError("model bundle must identify split manifest")
        if self.artifact.training_receipt_hash != self.training_receipt.content_hash:
            raise ValueError("model bundle must identify training receipt")
        if self.split_manifest.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("split manifest must identify dataset")
        if self.training_receipt.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("training receipt must identify dataset")
        if (
            self.training_receipt.split_manifest_hash
            != self.split_manifest.content_hash
        ):
            raise ValueError("training receipt must identify split manifest")
        if self.parity_receipt.model_bundle_hash != self.artifact.content_hash:
            raise ValueError("parity receipt must identify model bundle")
        if self.parity_receipt.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("parity receipt must identify dataset")
        return self


class R5CAcceptanceThresholds(AxiomModel):
    maximum_cycle_time_normalized_rmse: Literal[0.02] = Field(
        alias="maximumCycleTimeNormalizedRmse"
    )
    maximum_linear_error_normalized_rmse: Literal[0.05] = Field(
        alias="maximumLinearErrorNormalizedRmse"
    )
    minimum_conformal_coverage: Literal[0.8] = Field(alias="minimumConformalCoverage")
    required_ood_abstention_rate: Literal[1.0] = Field(
        alias="requiredOodAbstentionRate"
    )
    maximum_target_parity_gap: Literal[1e-12] = Field(alias="maximumTargetParityGap")


class R5CManifest(AxiomModel):
    manifest_id: Literal["axiom.intelligence.r5c-manifest@1"] = Field(
        alias="manifestId"
    )
    schema_id: Literal["axiom.intelligence.r5c-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["R5-C"]
    domain_pack_id: Literal["intelligence.domain-pack@3"] = Field(alias="domainPackId")
    platform: Literal["windows"]
    default_scenario_id: Literal["canonical-head-table-conditional-effect"] = Field(
        alias="defaultScenarioId"
    )
    parameter_domain: ConditionalEffectDomain = Field(alias="parameterDomain")
    output_targets: tuple[str, str] = Field(alias="outputTargets")
    acceptance_thresholds: R5CAcceptanceThresholds = Field(alias="acceptanceThresholds")
    synthetic_conditional_effect_contract_status: Literal["Passed"] = Field(
        alias="syntheticConditionalEffectContractStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    safety_banner: Literal[
        "SYNTHETIC CONDITIONAL EFFECT / NOT REALITY VALIDATED / NOT DEVICE SAFE"
    ] = Field(alias="safetyBanner")

    @model_validator(mode="after")
    def freeze_outputs(self) -> "R5CManifest":
        if self.output_targets != R5C_TARGETS:
            raise ValueError("outputTargets must keep seconds and millimetres separate")
        return self


class R5CScenarioSummary(AxiomModel):
    scenario_id: Literal["canonical-head-table-conditional-effect"] = Field(
        alias="scenarioId"
    )
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expected_outcome: Literal["Passed"] = Field(alias="expectedOutcome")
    expected_execution_status: Literal["Succeeded"] = Field(
        alias="expectedExecutionStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(
        alias="realWorldGeneralizationStatus"
    )


class R5CExamplePayload(AxiomModel):
    manifest: R5CManifest
    scenario: R5CScenarioSummary
    dataset: ConditionalEffectDataset
    split_manifest: ConditionalEffectSplitManifest = Field(alias="splitManifest")
    model_bundle: ConditionalEffectModelBundle = Field(alias="modelBundle")
    training_receipt: ConditionalEffectTrainingReceipt = Field(alias="trainingReceipt")
    parity_receipt: ConditionalEffectParityReceipt = Field(alias="parityReceipt")
    evaluation: ConditionalEffectEvaluation
    prediction_example: ConditionalEffectPrediction = Field(alias="predictionExample")
    run_spec: RunSpec = Field(alias="runSpec")


@dataclass(frozen=True, slots=True)
class R5CScenario:
    summary: R5CScenarioSummary
    dataset: ConditionalEffectDataset
    split_manifest: ConditionalEffectSplitManifest
    model_bundle: ConditionalEffectModelBundle
    training_receipt: ConditionalEffectTrainingReceipt
    parity_receipt: ConditionalEffectParityReceipt
    evaluation: ConditionalEffectEvaluation
    evaluation_request: ConditionalEffectEvaluationRequest
    run_spec: dict[str, Any]


__all__ = [
    "R5C_DEFAULT_SCENARIO_ID",
    "R5C_DOMAIN_PACK_ID",
    "R5C_EVALUATOR_ID",
    "R5C_FEATURE_ORDER",
    "R5C_FEED_OVERRIDES",
    "R5C_RUNNER_ID",
    "R5C_SAMPLE_PERIODS",
    "R5C_TARGETS",
    "ConditionalEffectDataset",
    "ConditionalEffectDatasetV2",
    "ConditionalEffectDomain",
    "ConditionalEffectEvaluation",
    "ConditionalEffectEvaluationRequest",
    "ConditionalEffectGovernance",
    "ConditionalEffectHead",
    "ConditionalEffectHeadResult",
    "ConditionalEffectModelBundle",
    "ConditionalEffectModelBundleV2",
    "ConditionalEffectParityReceipt",
    "ConditionalEffectParityReceiptV2",
    "ConditionalEffectPartition",
    "ConditionalEffectPrediction",
    "ConditionalEffectPredictionInterval",
    "ConditionalEffectPredictionRequest",
    "ConditionalEffectResourceBudget",
    "ConditionalEffectSample",
    "ConditionalEffectSplitManifest",
    "ConditionalEffectSplitManifestV2",
    "ConditionalEffectTrainingReceipt",
    "ConditionalEffectTrainingReceiptV2",
    "R5CAcceptanceThresholds",
    "R5CExamplePayload",
    "R5CManifest",
    "R5CScenario",
    "R5CScenarioSummary",
]
