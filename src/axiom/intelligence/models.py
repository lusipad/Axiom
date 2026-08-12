from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel, EvaluationCase, RunSpec

HASH_PATTERN = r"^[0-9a-f]{64}$"
VERSIONED_ID_PATTERN = r"^.+@[0-9]+$"
AXES: tuple[str, ...] = ("X", "Y", "Z", "B", "C")
SPLITS: tuple[str, ...] = ("train", "validation", "test")
R5_DOMAIN_PACK_ID = "intelligence.domain-pack@1"
R5_EVALUATOR_ID = "intelligence-evaluator@1"
R5_RUNNER_ID = "intelligence-model-validation@1"
R5_TARGET_INTERPRETER_ID = "axiom.intelligence.target-interpreter.python@1"
TARGET_PARITY_TOLERANCE = 1e-12
FEATURE_ORDER: tuple[str, ...] = (
    "bias",
    "t",
    "t2",
    "t3",
    "t4",
    "command_minus_simulation",
)


def _finite(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be a finite JSON number")
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("value must be a finite JSON number")
    return value


def _aware_timestamp(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


def canonical_hash(payload: Any, *, exclude: set[str] | None = None) -> str:
    if hasattr(payload, "model_dump"):
        serializable = payload.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
            exclude=exclude or set(),
        )
    else:
        serializable = payload
    encoded = json.dumps(
        serializable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class DatasetGovernance(AxiomModel):
    governance_id: str = Field(alias="governanceId", pattern=VERSIONED_ID_PATTERN)
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    synthetic_learning_contract_status: Literal["Open", "Passed", "Failed"] = Field(
        alias="syntheticLearningContractStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(alias="realWorldGeneralizationStatus")
    safety_banner: Literal["SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE"] = Field(alias="safetyBanner")
    license_id: str = Field(alias="licenseId", min_length=1)
    allowed_uses: tuple[str, ...] = Field(alias="allowedUses", min_length=1)
    sensitivity: Literal["synthetic"]
    retention_policy_id: str = Field(alias="retentionPolicyId", pattern=VERSIONED_ID_PATTERN)
    redistribution_allowed: Literal[False] = Field(default=False, alias="redistributionAllowed")


class IntelligenceSample(AxiomModel):
    sample_id: str = Field(alias="sampleId", min_length=1)
    axis_id: Literal["X", "Y", "Z", "B", "C"] = Field(alias="axisId")
    topology: Literal["dual-table", "head-table", "dual-head"]
    trajectory_family: str = Field(alias="trajectoryFamily", min_length=1)
    task_id: str = Field(alias="taskId", min_length=1)
    device_batch_id: str = Field(alias="deviceBatchId", min_length=1)
    pair_id: str = Field(alias="pairId", min_length=1)
    declared_split_id: Literal["train", "validation", "test"] = Field(alias="declaredSplitId")
    scenario_role: Literal["in-domain", "ood-probe"] = Field(alias="scenarioRole")
    upstream_scenario_id: str = Field(alias="upstreamScenarioId", min_length=1)
    source_command_content_id: str = Field(alias="sourceCommandContentId", pattern=HASH_PATTERN)
    source_command_sample_id: str = Field(alias="sourceCommandSampleId", min_length=1)
    label_derivation_id: str = Field(alias="labelDerivationId", pattern=VERSIONED_ID_PATTERN)
    event_time: str = Field(alias="eventTime", min_length=1)
    t: float = Field(ge=0.0, le=1.0)
    command: float
    simulation: float
    observation: float

    @field_validator("t", "command", "simulation", "observation", mode="before")
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)

    @field_validator("event_time")
    @classmethod
    def require_aware_time(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="eventTime")

    @property
    def connected_group_id(self) -> str:
        return "|".join((self.trajectory_family, self.task_id, self.device_batch_id, self.pair_id))


class DatasetSnapshot(AxiomModel):
    artifact_type: Literal["axiom.intelligence.dataset-snapshot"] = Field(alias="artifactType")
    schema_id: Literal["axiom.intelligence.dataset-snapshot@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    dataset_id: str = Field(alias="datasetId", pattern=VERSIONED_ID_PATTERN)
    axis_ids: tuple[Literal["X", "Y", "Z", "B", "C"], ...] = Field(alias="axisIds", min_length=5, max_length=5)
    allowed_split_ids: tuple[Literal["train", "validation", "test"], ...] = Field(
        alias="allowedSplitIds",
        min_length=3,
        max_length=3,
    )
    governance: DatasetGovernance
    selection_policy_id: str = Field(alias="selectionPolicyId", pattern=VERSIONED_ID_PATTERN)
    label_derivation_id: str = Field(alias="labelDerivationId", pattern=VERSIONED_ID_PATTERN)
    known_biases: tuple[str, ...] = Field(alias="knownBiases", min_length=1)
    coverage_gaps: tuple[str, ...] = Field(alias="coverageGaps", min_length=1)
    samples: tuple[IntelligenceSample, ...] = Field(min_length=1)
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "DatasetSnapshot":
        if self.axis_ids != AXES:
            raise ValueError("axisIds must freeze X/Y/Z/B/C in order")
        if self.allowed_split_ids != SPLITS:
            raise ValueError("allowedSplitIds must freeze train/validation/test in order")
        ids = [sample.sample_id for sample in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("DatasetSnapshot must not contain duplicate sampleId values")
        declared_axes = set(self.axis_ids)
        undeclared = {sample.axis_id for sample in self.samples if sample.axis_id not in declared_axes}
        if undeclared:
            raise ValueError("DatasetSnapshot samples reference undeclared axes")
        allowed_splits = set(self.allowed_split_ids)
        if any(sample.declared_split_id not in allowed_splits for sample in self.samples):
            raise ValueError("DatasetSnapshot samples reference invalid declaredSplitId values")
        if any(sample.label_derivation_id != self.label_derivation_id for sample in self.samples):
            raise ValueError("DatasetSnapshot samples must use the frozen labelDerivationId")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match DatasetSnapshot content")
        return self


class SplitPartition(AxiomModel):
    split_id: Literal["train", "validation", "test"] = Field(alias="splitId")
    sample_ids: tuple[str, ...] = Field(alias="sampleIds", min_length=1)
    connected_group_ids: tuple[str, ...] = Field(alias="connectedGroupIds", min_length=1)
    start_time: str = Field(alias="startTime", min_length=1)
    end_time: str = Field(alias="endTime", min_length=1)

    @field_validator("start_time", "end_time")
    @classmethod
    def require_aware_times(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @model_validator(mode="after")
    def require_forward_window(self) -> "SplitPartition":
        if datetime.fromisoformat(self.end_time) <= datetime.fromisoformat(self.start_time):
            raise ValueError("SplitPartition endTime must be greater than startTime")
        return self


class SplitManifest(AxiomModel):
    artifact_type: Literal["axiom.intelligence.split-manifest"] = Field(alias="artifactType")
    schema_id: Literal["axiom.intelligence.split-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    manifest_id: str = Field(alias="manifestId", pattern=VERSIONED_ID_PATTERN)
    dataset_content_hash: str = Field(alias="datasetContentHash", pattern=HASH_PATTERN)
    partitions: tuple[SplitPartition, ...] = Field(min_length=3, max_length=3)
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "SplitManifest":
        if tuple(partition.split_id for partition in self.partitions) != SPLITS:
            raise ValueError("SplitManifest partitions must freeze train/validation/test in order")
        sample_ids = [sample_id for partition in self.partitions for sample_id in partition.sample_ids]
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("SplitManifest must not assign the same sampleId to multiple splits")
        group_ids = [group_id for partition in self.partitions for group_id in partition.connected_group_ids]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("SplitManifest connected identity components must be split-disjoint")
        train, validation, test = self.partitions
        if not (
            datetime.fromisoformat(train.end_time) < datetime.fromisoformat(validation.start_time)
            and datetime.fromisoformat(validation.end_time) < datetime.fromisoformat(test.start_time)
        ):
            raise ValueError("SplitManifest must enforce forward-only split time")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match SplitManifest content")
        return self


class AxisDisposition(AxiomModel):
    axis_id: Literal["X", "Y", "Z", "B", "C"] = Field(alias="axisId")
    status: Literal["Validated", "NoValidatedImprovement", "InsufficientExcitation", "Failed"]


class FeatureEnvelope(AxiomModel):
    minimums: tuple[float, float, float, float, float, float] = Field(alias="minimums")
    maximums: tuple[float, float, float, float, float, float] = Field(alias="maximums")
    margin_fraction: Literal[0.25] = Field(alias="marginFraction")

    @field_validator("minimums", "maximums", mode="before")
    @classmethod
    def reject_non_finite_vectors(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)) and len(value) == 6:
            for item in value:
                _finite(item)
        return value

    @field_validator("margin_fraction", mode="before")
    @classmethod
    def reject_non_finite_margin(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def require_ordered_bounds(self) -> "FeatureEnvelope":
        if any(lower > upper for lower, upper in zip(self.minimums, self.maximums, strict=True)):
            raise ValueError("FeatureEnvelope minimums must not exceed maximums")
        return self


class XAxisHead(AxiomModel):
    axis_id: Literal["X"] = Field(alias="axisId")
    lambda_value: Literal[0.1] = Field(alias="lambdaValue")
    feature_order: tuple[
        Literal["bias"],
        Literal["t"],
        Literal["t2"],
        Literal["t3"],
        Literal["t4"],
        Literal["command_minus_simulation"],
    ] = Field(alias="featureOrder")
    weights: tuple[float, float, float, float, float, float]
    conformal_radius: float = Field(alias="conformalRadius", ge=0.0)
    feature_envelope: FeatureEnvelope = Field(alias="featureEnvelope")

    @field_validator("weights", mode="before")
    @classmethod
    def reject_non_finite_weights(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)) and len(value) == 6:
            for item in value:
                _finite(item)
        return value

    @field_validator("conformal_radius", mode="before")
    @classmethod
    def reject_non_finite_radius(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def freeze_feature_order(self) -> "XAxisHead":
        if self.feature_order != FEATURE_ORDER:
            raise ValueError("XAxisHead featureOrder must match the frozen residual contract")
        return self


class ResourceBudget(AxiomModel):
    target_runtime: Literal["pure-python"] = Field(alias="targetRuntime")
    feature_count: Literal[6] = Field(alias="featureCount")
    deterministic_numeric_type: Literal["float64"] = Field(alias="deterministicNumericType")
    weight_decimal_places: Literal[15] = Field(alias="weightDecimalPlaces")


class ModelBundle(AxiomModel):
    artifact_type: Literal["axiom.intelligence.model-bundle"] = Field(alias="artifactType")
    schema_id: Literal["axiom.intelligence.model-bundle@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    bundle_id: str = Field(alias="bundleId", pattern=VERSIONED_ID_PATTERN)
    domain_pack_id: Literal["intelligence.domain-pack@1"] = Field(alias="domainPackId")
    evaluator_version: Literal["intelligence-evaluator@1"] = Field(alias="evaluatorVersion")
    target_interpreter_id: Literal["axiom.intelligence.target-interpreter.python@1"] = Field(
        alias="targetInterpreterId"
    )
    input_contract_id: Literal["axiom.intelligence.x-residual-input@1"] = Field(alias="inputContractId")
    preprocessor_id: Literal["axiom.intelligence.polynomial-feature-map@1"] = Field(alias="preprocessorId")
    output_contract_id: Literal["axiom.intelligence.residual-with-abstention@1"] = Field(
        alias="outputContractId"
    )
    dataset_content_hash: str = Field(alias="datasetContentHash", pattern=HASH_PATTERN)
    split_manifest_hash: str = Field(alias="splitManifestHash", pattern=HASH_PATTERN)
    training_receipt_hash: str = Field(alias="trainingReceiptHash", pattern=HASH_PATTERN)
    synthetic_learning_contract_status: Literal["Passed", "Failed"] = Field(
        alias="syntheticLearningContractStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(alias="realWorldGeneralizationStatus")
    axis_dispositions: tuple[AxisDisposition, ...] = Field(alias="axisDispositions", min_length=5, max_length=5)
    x_axis_head: XAxisHead = Field(alias="xAxisHead")
    resource_budget: ResourceBudget = Field(alias="resourceBudget")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "ModelBundle":
        if tuple(item.axis_id for item in self.axis_dispositions) != AXES:
            raise ValueError("ModelBundle axisDispositions must freeze X/Y/Z/B/C in order")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match ModelBundle content")
        return self


class TrainingReceipt(AxiomModel):
    artifact_type: Literal["axiom.intelligence.training-receipt"] = Field(alias="artifactType")
    schema_id: Literal["axiom.intelligence.training-receipt@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    receipt_id: str = Field(alias="receiptId", pattern=VERSIONED_ID_PATTERN)
    method_id: Literal["axiom.intelligence.x-residual-ridge@1"] = Field(alias="methodId")
    dataset_content_hash: str = Field(alias="datasetContentHash", pattern=HASH_PATTERN)
    split_manifest_hash: str = Field(alias="splitManifestHash", pattern=HASH_PATTERN)
    lambda_value: Literal[0.1] = Field(alias="lambdaValue")
    feature_order: tuple[str, ...] = Field(alias="featureOrder", min_length=6, max_length=6)
    train_sample_count: int = Field(alias="trainSampleCount", ge=1)
    validation_sample_count: int = Field(alias="validationSampleCount", ge=1)
    test_sample_count: int = Field(alias="testSampleCount", ge=1)
    axis_dispositions: tuple[AxisDisposition, ...] = Field(alias="axisDispositions", min_length=5, max_length=5)
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "TrainingReceipt":
        if tuple(item.axis_id for item in self.axis_dispositions) != AXES:
            raise ValueError("TrainingReceipt axisDispositions must freeze X/Y/Z/B/C in order")
        if tuple(self.feature_order) != FEATURE_ORDER:
            raise ValueError("TrainingReceipt featureOrder must match the frozen residual contract")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match TrainingReceipt content")
        return self


class TargetParityReceipt(AxiomModel):
    artifact_type: Literal["axiom.intelligence.target-parity-receipt"] = Field(alias="artifactType")
    schema_id: Literal["axiom.intelligence.target-parity-receipt@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    receipt_id: str = Field(alias="receiptId", pattern=VERSIONED_ID_PATTERN)
    model_bundle_hash: str = Field(alias="modelBundleHash", pattern=HASH_PATTERN)
    dataset_content_hash: str = Field(alias="datasetContentHash", pattern=HASH_PATTERN)
    max_abs_gap: float = Field(alias="maxAbsGap", ge=0.0)
    sample_count: int = Field(alias="sampleCount", ge=1)
    status: Literal["Passed", "Failed"]
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @field_validator("max_abs_gap", mode="before")
    @classmethod
    def reject_non_finite_gap(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def validate_contract(self) -> "TargetParityReceipt":
        expected_status = "Passed" if self.max_abs_gap <= TARGET_PARITY_TOLERANCE else "Failed"
        if self.status != expected_status:
            raise ValueError("TargetParityReceipt status must match maxAbsGap tolerance")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match TargetParityReceipt content")
        return self


class IntelligenceEvaluationRequest(AxiomModel):
    artifact: ModelBundle
    dataset: DatasetSnapshot
    split_manifest: SplitManifest = Field(alias="splitManifest")
    training_receipt: TrainingReceipt = Field(alias="trainingReceipt")
    parity_receipt: TargetParityReceipt = Field(alias="parityReceipt")
    case: EvaluationCase

    @model_validator(mode="after")
    def validate_cross_object_contract(self) -> "IntelligenceEvaluationRequest":
        if self.artifact.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("ModelBundle datasetContentHash must identify dataset")
        if self.artifact.split_manifest_hash != self.split_manifest.content_hash:
            raise ValueError("ModelBundle splitManifestHash must identify splitManifest")
        if self.artifact.training_receipt_hash != self.training_receipt.content_hash:
            raise ValueError("ModelBundle trainingReceiptHash must identify trainingReceipt")
        if self.split_manifest.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("SplitManifest datasetContentHash must identify dataset")
        if self.training_receipt.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("TrainingReceipt datasetContentHash must identify dataset")
        if self.training_receipt.split_manifest_hash != self.split_manifest.content_hash:
            raise ValueError("TrainingReceipt splitManifestHash must identify splitManifest")
        if self.parity_receipt.model_bundle_hash != self.artifact.content_hash:
            raise ValueError("TargetParityReceipt modelBundleHash must identify ModelBundle")
        if self.parity_receipt.dataset_content_hash != self.dataset.content_hash:
            raise ValueError("TargetParityReceipt datasetContentHash must identify dataset")
        known_sample_ids = {sample.sample_id for sample in self.dataset.samples}
        assigned_sample_ids = {
            sample_id for partition in self.split_manifest.partitions for sample_id in partition.sample_ids
        }
        if assigned_sample_ids != known_sample_ids:
            raise ValueError("SplitManifest must assign every DatasetSnapshot sample exactly once")
        for partition in self.split_manifest.partitions:
            if any(sample_id not in known_sample_ids for sample_id in partition.sample_ids):
                raise ValueError("SplitManifest references unknown sampleId values")
        samples_by_id = {sample.sample_id: sample for sample in self.dataset.samples}
        split_dimension_sets: dict[str, dict[str, set[str]]] = {
            partition.split_id: {
                "trajectoryFamily": set(),
                "taskId": set(),
                "deviceBatchId": set(),
                "pairId": set(),
            }
            for partition in self.split_manifest.partitions
        }
        for partition in self.split_manifest.partitions:
            observed_groups = {samples_by_id[sample_id].connected_group_id for sample_id in partition.sample_ids}
            if observed_groups != set(partition.connected_group_ids):
                raise ValueError("SplitManifest connectedGroupIds must match dataset lineage")
            if any(samples_by_id[sample_id].declared_split_id != partition.split_id for sample_id in partition.sample_ids):
                raise ValueError("SplitManifest sampleIds must respect DatasetSnapshot declaredSplitId")
            sample_times = [datetime.fromisoformat(samples_by_id[sample_id].event_time) for sample_id in partition.sample_ids]
            if min(sample_times) != datetime.fromisoformat(partition.start_time) or max(sample_times) != datetime.fromisoformat(
                partition.end_time
            ):
                raise ValueError("SplitManifest time windows must match assigned sample eventTime values")
            for sample_id in partition.sample_ids:
                sample = samples_by_id[sample_id]
                split_dimension_sets[partition.split_id]["trajectoryFamily"].add(sample.trajectory_family)
                split_dimension_sets[partition.split_id]["taskId"].add(sample.task_id)
                split_dimension_sets[partition.split_id]["deviceBatchId"].add(sample.device_batch_id)
                split_dimension_sets[partition.split_id]["pairId"].add(sample.pair_id)
        for left_split, right_split in (("train", "validation"), ("train", "test"), ("validation", "test")):
            left_dimensions = split_dimension_sets[left_split]
            right_dimensions = split_dimension_sets[right_split]
            for dimension in ("trajectoryFamily", "taskId", "deviceBatchId", "pairId"):
                if left_dimensions[dimension] & right_dimensions[dimension]:
                    raise ValueError(f"SplitManifest must isolate {dimension} identities across splits")
        sample_counts = {
            partition.split_id: sum(
                samples_by_id[sample_id].axis_id == "X" and samples_by_id[sample_id].scenario_role == "in-domain"
                for sample_id in partition.sample_ids
            )
            for partition in self.split_manifest.partitions
        }
        if (
            self.training_receipt.train_sample_count != sample_counts["train"]
            or self.training_receipt.validation_sample_count != sample_counts["validation"]
            or self.training_receipt.test_sample_count != sample_counts["test"]
        ):
            raise ValueError("TrainingReceipt sample counts must match split-declared X in-domain samples")
        test_sample_count = sum(
            samples_by_id[sample_id].axis_id == "X"
            for sample_id in next(
                partition.sample_ids for partition in self.split_manifest.partitions if partition.split_id == "test"
            )
        )
        if self.parity_receipt.sample_count != test_sample_count:
            raise ValueError("TargetParityReceipt sampleCount must cover the full test split")
        if self.artifact.axis_dispositions != self.training_receipt.axis_dispositions:
            raise ValueError("ModelBundle and TrainingReceipt axisDispositions must match")
        return self


class AxisResult(AxiomModel):
    axis_id: Literal["X", "Y", "Z", "B", "C"] = Field(alias="axisId")
    status: Literal["Validated", "NoValidatedImprovement", "InsufficientExcitation", "Failed"]
    baseline_rmse: float | None = Field(default=None, alias="baselineRmse", ge=0.0)
    model_rmse: float | None = Field(default=None, alias="modelRmse", ge=0.0)
    improvement_ratio: float | None = Field(default=None, alias="improvementRatio")
    conformal_coverage: float | None = Field(default=None, alias="conformalCoverage", ge=0.0, le=1.0)
    ood_detection_rate: float | None = Field(default=None, alias="oodDetectionRate", ge=0.0, le=1.0)

    @field_validator(
        "baseline_rmse",
        "model_rmse",
        "improvement_ratio",
        "conformal_coverage",
        "ood_detection_rate",
        mode="before",
    )
    @classmethod
    def reject_non_finite_optional_numbers(cls, value: Any) -> Any:
        if value is None:
            return None
        return _finite(value)


class EvaluationClaim(AxiomModel):
    claim_id: str = Field(alias="claimId", min_length=1)
    title: str = Field(min_length=1)
    status: Literal["Supported", "Refuted", "Inconclusive"]
    statement: str = Field(min_length=1)
    reason_code: str | None = Field(default=None, alias="reasonCode")
    evidence_level: Literal["Observed", "Validated"] | None = Field(default=None, alias="evidenceLevel")


class EvaluationEvidence(AxiomModel):
    evidence_id: str = Field(alias="evidenceId", min_length=1)
    title: str = Field(min_length=1)
    content_hash: str | None = Field(default=None, alias="contentHash", pattern=HASH_PATTERN)
    summary: str = Field(min_length=1)


class R5Evaluation(AxiomModel):
    synthetic_learning_contract_status: Literal["Passed", "Failed", "Open"] = Field(
        alias="syntheticLearningContractStatus"
    )
    real_world_generalization_status: Literal["Open"] = Field(alias="realWorldGeneralizationStatus")
    axis_results: tuple[AxisResult, ...] = Field(alias="axisResults", min_length=5, max_length=5)
    ood_detection_rate: float = Field(alias="oodDetectionRate", ge=0.0, le=1.0)
    conformal_coverage: float = Field(alias="conformalCoverage", ge=0.0, le=1.0)
    target_parity_max_abs_gap: float = Field(alias="targetParityMaxAbsGap", ge=0.0)
    baseline_test_rmse: float = Field(alias="baselineTestRmse", ge=0.0)
    model_test_rmse: float = Field(alias="modelTestRmse", ge=0.0)
    claims: tuple[EvaluationClaim, ...] = Field(min_length=1)
    evidence: tuple[EvaluationEvidence, ...] = Field(min_length=1)

    @field_validator(
        "ood_detection_rate",
        "conformal_coverage",
        "target_parity_max_abs_gap",
        "baseline_test_rmse",
        "model_test_rmse",
        mode="before",
    )
    @classmethod
    def reject_non_finite_numbers(cls, value: Any) -> Any:
        return _finite(value)


class R5Manifest(AxiomModel):
    manifest_id: Literal["axiom.intelligence.r5-manifest@1"] = Field(alias="manifestId")
    schema_id: Literal["axiom.intelligence.r5-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["R5-A"]
    domain_pack_id: Literal["intelligence.domain-pack@1"] = Field(alias="domainPackId")
    platform: Literal["windows"] = Field(alias="platform")
    default_scenario_id: str = Field(alias="defaultScenarioId", min_length=1)
    safety_banner: Literal["SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE"] = Field(alias="safetyBanner")
    synthetic_learning_contract_status: Literal["Passed"] = Field(alias="syntheticLearningContractStatus")
    real_world_generalization_status: Literal["Open"] = Field(alias="realWorldGeneralizationStatus")


class R5ScenarioSummary(AxiomModel):
    scenario_id: str = Field(alias="scenarioId", min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expected_outcome: Literal["Passed", "Invalid"] = Field(alias="expectedOutcome")
    expected_execution_status: Literal["Succeeded", "Skipped"] = Field(alias="expectedExecutionStatus")


class R5ExamplePayload(AxiomModel):
    manifest: R5Manifest
    scenario: R5ScenarioSummary
    dataset: DatasetSnapshot
    split_manifest: SplitManifest = Field(alias="splitManifest")
    model_bundle: ModelBundle = Field(alias="modelBundle")
    evaluation: R5Evaluation | None = None
    run_spec: RunSpec = Field(alias="runSpec")


@dataclass(frozen=True, slots=True)
class R5Scenario:
    summary: R5ScenarioSummary
    dataset: DatasetSnapshot
    split_manifest: SplitManifest
    model_bundle: ModelBundle
    training_receipt: TrainingReceipt
    parity_receipt: TargetParityReceipt
    evaluation: R5Evaluation
    run_spec: dict[str, Any]
