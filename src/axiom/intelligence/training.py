from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

import numpy as np

from .models import (
    FEATURE_ORDER,
    R5_DOMAIN_PACK_ID,
    R5_EVALUATOR_ID,
    R5_TARGET_INTERPRETER_ID,
    TARGET_PARITY_TOLERANCE,
    AxisDisposition,
    AxisResult,
    DatasetSnapshot,
    EvaluationClaim,
    EvaluationEvidence,
    FeatureEnvelope,
    IntelligenceSample,
    ModelBundle,
    R5Evaluation,
    ResourceBudget,
    SplitManifest,
    TargetParityReceipt,
    TrainingReceipt,
    XAxisHead,
    canonical_hash,
)
from .interpreter import pure_python_predict_observation, pure_python_predict_residual

RIDGE_LAMBDA = 0.1
OOD_MARGIN_FRACTION = 0.25
CONFORMAL_ALPHA = 0.1


def feature_vector(sample: IntelligenceSample) -> tuple[float, float, float, float, float, float]:
    t = float(sample.t)
    command_minus_simulation = float(sample.command - sample.simulation)
    return (
        1.0,
        t,
        t * t,
        t * t * t,
        t * t * t * t,
        command_minus_simulation,
    )


def target_residual(sample: IntelligenceSample) -> float:
    return float(sample.observation - sample.simulation)


def dataset_samples_for_split(
    dataset: DatasetSnapshot,
    split_manifest: SplitManifest,
    *,
    split_id: str,
    axis_id: str = "X",
    scenario_role: str | None = None,
) -> tuple[IntelligenceSample, ...]:
    sample_ids = next(partition.sample_ids for partition in split_manifest.partitions if partition.split_id == split_id)
    by_id = {sample.sample_id: sample for sample in dataset.samples}
    selected = []
    for sample_id in sample_ids:
        sample = by_id[sample_id]
        if sample.axis_id != axis_id:
            continue
        if scenario_role is not None and sample.scenario_role != scenario_role:
            continue
        selected.append(sample)
    return tuple(selected)


def validate_dataset_split_contract(dataset: DatasetSnapshot, split_manifest: SplitManifest) -> None:
    if split_manifest.dataset_content_hash != dataset.content_hash:
        raise ValueError("splitManifest datasetContentHash must identify dataset")
    samples_by_id = {sample.sample_id: sample for sample in dataset.samples}
    assigned_sample_ids = {
        sample_id for partition in split_manifest.partitions for sample_id in partition.sample_ids
    }
    if assigned_sample_ids != set(samples_by_id):
        raise ValueError("splitManifest must assign every dataset sample exactly once")
    group_identity_mismatch = False
    split_dimension_sets: dict[str, dict[str, set[str]]] = {
        partition.split_id: {
            "trajectoryFamily": set(),
            "taskId": set(),
            "deviceBatchId": set(),
            "pairId": set(),
        }
        for partition in split_manifest.partitions
    }
    for partition in split_manifest.partitions:
        partition_samples = [samples_by_id[sample_id] for sample_id in partition.sample_ids]
        groups = {sample.connected_group_id for sample in partition_samples}
        if groups != set(partition.connected_group_ids):
            group_identity_mismatch = True
        event_times = [sample.event_time for sample in partition_samples]
        if event_times:
            parsed_times = [datetime.fromisoformat(value) for value in event_times]
            if min(parsed_times) != datetime.fromisoformat(partition.start_time) or max(
                parsed_times
            ) != datetime.fromisoformat(partition.end_time):
                raise ValueError("splitManifest time windows do not match dataset eventTime values")
        for sample in partition_samples:
            split_dimension_sets[partition.split_id]["trajectoryFamily"].add(sample.trajectory_family)
            split_dimension_sets[partition.split_id]["taskId"].add(sample.task_id)
            split_dimension_sets[partition.split_id]["deviceBatchId"].add(sample.device_batch_id)
            split_dimension_sets[partition.split_id]["pairId"].add(sample.pair_id)
    train_groups, validation_groups, test_groups = (
        set(split_manifest.partitions[index].connected_group_ids) for index in range(3)
    )
    if train_groups & validation_groups or train_groups & test_groups or validation_groups & test_groups:
        raise ValueError("trajectory/task/device-batch/pair connected groups must be split-disjoint")
    for left_split, right_split in (("train", "validation"), ("train", "test"), ("validation", "test")):
        for dimension in ("trajectoryFamily", "taskId", "deviceBatchId", "pairId"):
            if split_dimension_sets[left_split][dimension] & split_dimension_sets[right_split][dimension]:
                raise ValueError(f"{dimension} identities must be split-disjoint")
    if group_identity_mismatch:
        raise ValueError("splitManifest connected groups do not match dataset identities")
    train_end = split_manifest.partitions[0].end_time
    validation_start = split_manifest.partitions[1].start_time
    validation_end = split_manifest.partitions[1].end_time
    test_start = split_manifest.partitions[2].start_time
    if not (train_end < validation_start and validation_end < test_start):
        raise ValueError("splitManifest must be forward-only in time")


def _matrix(samples: tuple[IntelligenceSample, ...]) -> tuple[np.ndarray, np.ndarray]:
    features = np.asarray([feature_vector(sample) for sample in samples], dtype=np.float64)
    targets = np.asarray([target_residual(sample) for sample in samples], dtype=np.float64)
    return features, targets


def _ridge_weights(samples: tuple[IntelligenceSample, ...]) -> tuple[float, float, float, float, float, float]:
    features, targets = _matrix(samples)
    gram = features.T @ features
    regularized = gram + RIDGE_LAMBDA * np.eye(features.shape[1], dtype=np.float64)
    solution = np.linalg.solve(regularized, features.T @ targets)
    return tuple(round(float(value), 15) for value in solution)


def _residuals(weights: tuple[float, ...], samples: tuple[IntelligenceSample, ...]) -> tuple[float, ...]:
    values = []
    for sample in samples:
        prediction = pure_python_predict_residual(weights, feature_vector(sample))
        values.append(float(target_residual(sample) - prediction))
    return tuple(values)


def _rmse(values: tuple[float, ...]) -> float:
    if not values:
        raise ValueError("RMSE requires at least one residual")
    return math.sqrt(sum(value * value for value in values) / len(values))


def _coverage(bundle: ModelBundle, samples: tuple[IntelligenceSample, ...]) -> float:
    covered = 0
    observed = 0
    for sample in samples:
        abstained, prediction = pure_python_predict_observation(bundle, sample)
        if abstained or prediction is None:
            continue
        observed += 1
        if abs(float(sample.observation) - prediction) <= bundle.x_axis_head.conformal_radius:
            covered += 1
    return float(covered / observed) if observed else 0.0


def _ood_detection_rate(bundle: ModelBundle, samples: tuple[IntelligenceSample, ...]) -> float:
    if not samples:
        return 0.0
    detected = 0
    for sample in samples:
        abstained, _ = pure_python_predict_observation(bundle, sample)
        if abstained:
            detected += 1
    return float(detected / len(samples))


def _baseline_rmse(samples: tuple[IntelligenceSample, ...]) -> float:
    baseline = tuple(float(sample.observation - sample.simulation) for sample in samples)
    return _rmse(baseline)


def _model_rmse(bundle: ModelBundle, samples: tuple[IntelligenceSample, ...]) -> float:
    residuals = []
    for sample in samples:
        abstained, prediction = pure_python_predict_observation(bundle, sample)
        if abstained or prediction is None:
            raise ValueError("in-domain evaluation samples must not be OOD")
        residuals.append(float(sample.observation - prediction))
    return _rmse(tuple(residuals))


def _conformal_radius(weights: tuple[float, ...], validation_samples: tuple[IntelligenceSample, ...]) -> float:
    absolute_errors = sorted(abs(value) for value in _residuals(weights, validation_samples))
    rank = max(1, math.ceil((len(absolute_errors) + 1) * (1.0 - CONFORMAL_ALPHA)))
    index = min(rank - 1, len(absolute_errors) - 1)
    return float(absolute_errors[index])


def _feature_envelope(samples: tuple[IntelligenceSample, ...]) -> FeatureEnvelope:
    features = [feature_vector(sample) for sample in samples]
    columns = list(zip(*features, strict=True))
    minimums = tuple(float(min(column)) for column in columns)
    maximums = tuple(float(max(column)) for column in columns)
    return FeatureEnvelope(minimums=minimums, maximums=maximums, marginFraction=OOD_MARGIN_FRACTION)


def _axis_dispositions(passed: bool) -> tuple[AxisDisposition, ...]:
    return (
        AxisDisposition(axisId="X", status="Validated" if passed else "Failed"),
        AxisDisposition(axisId="Y", status="NoValidatedImprovement"),
        AxisDisposition(axisId="Z", status="NoValidatedImprovement"),
        AxisDisposition(axisId="B", status="InsufficientExcitation"),
        AxisDisposition(axisId="C", status="InsufficientExcitation"),
    )


def _build_training_receipt(
    dataset: DatasetSnapshot,
    split_manifest: SplitManifest,
    *,
    train_count: int,
    validation_count: int,
    test_count: int,
    axis_dispositions: tuple[AxisDisposition, ...],
) -> TrainingReceipt:
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.training-receipt",
        "schemaId": "axiom.intelligence.training-receipt@1",
        "schemaVersion": 1,
        "receiptId": "axiom.intelligence.training-receipt.synthetic@1",
        "methodId": "axiom.intelligence.x-residual-ridge@1",
        "datasetContentHash": dataset.content_hash,
        "splitManifestHash": split_manifest.content_hash,
        "lambdaValue": RIDGE_LAMBDA,
        "featureOrder": list(FEATURE_ORDER),
        "trainSampleCount": train_count,
        "validationSampleCount": validation_count,
        "testSampleCount": test_count,
        "axisDispositions": [item.model_dump(mode="json", by_alias=True) for item in axis_dispositions],
    }
    payload["contentHash"] = canonical_hash(payload)
    return TrainingReceipt.model_validate(payload)


def _build_model_bundle(
    dataset: DatasetSnapshot,
    split_manifest: SplitManifest,
    training_receipt: TrainingReceipt,
    x_axis_head: XAxisHead,
    *,
    synthetic_status: Literal["Passed", "Failed"],
    axis_dispositions: tuple[AxisDisposition, ...],
) -> ModelBundle:
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.model-bundle",
        "schemaId": "axiom.intelligence.model-bundle@1",
        "schemaVersion": 1,
        "bundleId": "axiom.intelligence.model-bundle.synthetic@1",
        "domainPackId": R5_DOMAIN_PACK_ID,
        "evaluatorVersion": R5_EVALUATOR_ID,
        "targetInterpreterId": R5_TARGET_INTERPRETER_ID,
        "inputContractId": "axiom.intelligence.x-residual-input@1",
        "preprocessorId": "axiom.intelligence.polynomial-feature-map@1",
        "outputContractId": "axiom.intelligence.residual-with-abstention@1",
        "datasetContentHash": dataset.content_hash,
        "splitManifestHash": split_manifest.content_hash,
        "trainingReceiptHash": training_receipt.content_hash,
        "syntheticLearningContractStatus": synthetic_status,
        "realWorldGeneralizationStatus": "Open",
        "axisDispositions": [item.model_dump(mode="json", by_alias=True) for item in axis_dispositions],
        "xAxisHead": x_axis_head.model_dump(mode="json", by_alias=True),
        "resourceBudget": ResourceBudget(
            targetRuntime="pure-python",
            featureCount=6,
            deterministicNumericType="float64",
            weightDecimalPlaces=15,
        ).model_dump(mode="json", by_alias=True),
    }
    payload["contentHash"] = canonical_hash(payload)
    return ModelBundle.model_validate(payload)


def parity_gap(bundle: ModelBundle, samples: tuple[IntelligenceSample, ...]) -> float:
    features = np.asarray([feature_vector(sample) for sample in samples], dtype=np.float64)
    weights = np.asarray(bundle.x_axis_head.weights, dtype=np.float64)
    numpy_predictions = features @ weights
    maximum = 0.0
    for index, sample in enumerate(samples):
        python_prediction = pure_python_predict_residual(bundle.x_axis_head.weights, feature_vector(sample))
        maximum = max(maximum, abs(float(numpy_predictions[index]) - python_prediction))
    return float(maximum)


def build_parity_receipt(
    dataset: DatasetSnapshot,
    bundle: ModelBundle,
    samples: tuple[IntelligenceSample, ...],
) -> TargetParityReceipt:
    maximum_gap = parity_gap(bundle, samples)
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.target-parity-receipt",
        "schemaId": "axiom.intelligence.target-parity-receipt@1",
        "schemaVersion": 1,
        "receiptId": "axiom.intelligence.target-parity-receipt.synthetic@1",
        "modelBundleHash": bundle.content_hash,
        "datasetContentHash": dataset.content_hash,
        "maxAbsGap": maximum_gap,
        "sampleCount": len(samples),
        "status": "Passed" if maximum_gap <= TARGET_PARITY_TOLERANCE else "Failed",
    }
    payload["contentHash"] = canonical_hash(payload)
    return TargetParityReceipt.model_validate(payload)


def build_evaluation(
    bundle: ModelBundle,
    dataset: DatasetSnapshot,
    split_manifest: SplitManifest,
) -> R5Evaluation:
    in_domain_test = dataset_samples_for_split(dataset, split_manifest, split_id="test", scenario_role="in-domain")
    ood_test = dataset_samples_for_split(dataset, split_manifest, split_id="test", scenario_role="ood-probe")
    baseline_rmse = _baseline_rmse(in_domain_test)
    model_rmse = _model_rmse(bundle, in_domain_test)
    improvement_ratio = float(1.0 - (model_rmse / baseline_rmse))
    coverage = _coverage(bundle, in_domain_test)
    ood_detection = _ood_detection_rate(bundle, ood_test)
    x_status = "Validated" if (
        improvement_ratio >= 0.20 and coverage >= 0.80 and ood_detection == 1.0 and parity_gap(bundle, in_domain_test + ood_test) <= 1e-12
    ) else "Failed"
    axis_results = (
        AxisResult(
            axisId="X",
            status=x_status,
            baselineRmse=baseline_rmse,
            modelRmse=model_rmse,
            improvementRatio=improvement_ratio,
            conformalCoverage=coverage,
            oodDetectionRate=ood_detection,
        ),
        AxisResult(axisId="Y", status="NoValidatedImprovement"),
        AxisResult(axisId="Z", status="NoValidatedImprovement"),
        AxisResult(axisId="B", status="InsufficientExcitation"),
        AxisResult(axisId="C", status="InsufficientExcitation"),
    )
    synthetic_status: Literal["Passed", "Failed", "Open"] = "Passed" if x_status == "Validated" else "Failed"
    claims = (
        EvaluationClaim(
            claimId="claim.synthetic-learning-contract",
            title="Synthetic learning contract",
            status="Supported" if synthetic_status == "Passed" else "Refuted",
            statement="Synthetic residual-learning contract is evaluated only for X and remains synthetic-only.",
            evidenceLevel="Observed",
        ),
        EvaluationClaim(
            claimId="claim.real-world-generalization-open",
            title="Real-world generalization",
            status="Inconclusive",
            statement="Real-world generalization remains Open and is not claimed by this synthetic contract.",
            reasonCode="RealPairedHoldoutMissing",
            evidenceLevel="Observed",
        ),
    )
    evidence = (
        EvaluationEvidence(
            evidenceId="dataset-snapshot",
            title="Dataset snapshot",
            contentHash=dataset.content_hash,
            summary="Immutable synthetic dataset snapshot with split-declared sample lineage.",
        ),
        EvaluationEvidence(
            evidenceId="split-manifest",
            title="Split manifest",
            contentHash=split_manifest.content_hash,
            summary="Forward-only train/validation/test split with connected-group isolation.",
        ),
        EvaluationEvidence(
            evidenceId="model-bundle",
            title="Model bundle",
            contentHash=bundle.content_hash,
            summary="Single primary artifact containing the X-axis residual model and abstention policy.",
        ),
    )
    return R5Evaluation(
        syntheticLearningContractStatus=synthetic_status,
        realWorldGeneralizationStatus="Open",
        axisResults=axis_results,
        oodDetectionRate=ood_detection,
        conformalCoverage=coverage,
        targetParityMaxAbsGap=parity_gap(bundle, in_domain_test + ood_test),
        baselineTestRmse=baseline_rmse,
        modelTestRmse=model_rmse,
        claims=claims,
        evidence=evidence,
    )


def train_r5_bundle(
    dataset: DatasetSnapshot,
    split_manifest: SplitManifest,
) -> tuple[ModelBundle, TrainingReceipt, TargetParityReceipt, R5Evaluation]:
    validate_dataset_split_contract(dataset, split_manifest)
    train_samples = dataset_samples_for_split(dataset, split_manifest, split_id="train", scenario_role="in-domain")
    validation_samples = dataset_samples_for_split(
        dataset,
        split_manifest,
        split_id="validation",
        scenario_role="in-domain",
    )
    test_samples = dataset_samples_for_split(dataset, split_manifest, split_id="test", scenario_role="in-domain")
    parity_samples = test_samples + dataset_samples_for_split(
        dataset,
        split_manifest,
        split_id="test",
        scenario_role="ood-probe",
    )
    weights = _ridge_weights(train_samples)
    x_axis_head = XAxisHead(
        axisId="X",
        lambdaValue=RIDGE_LAMBDA,
        featureOrder=FEATURE_ORDER,
        weights=weights,
        conformalRadius=_conformal_radius(weights, validation_samples),
        featureEnvelope=_feature_envelope(train_samples),
    )
    provisional_axis_dispositions = _axis_dispositions(passed=False)
    training_receipt = _build_training_receipt(
        dataset,
        split_manifest,
        train_count=len(train_samples),
        validation_count=len(validation_samples),
        test_count=len(test_samples),
        axis_dispositions=provisional_axis_dispositions,
    )
    provisional_bundle = _build_model_bundle(
        dataset,
        split_manifest,
        training_receipt,
        x_axis_head,
        synthetic_status="Failed",
        axis_dispositions=provisional_axis_dispositions,
    )
    provisional_evaluation = build_evaluation(provisional_bundle, dataset, split_manifest)
    passed = provisional_evaluation.synthetic_learning_contract_status == "Passed"
    final_dispositions = _axis_dispositions(passed=passed)
    training_receipt = _build_training_receipt(
        dataset,
        split_manifest,
        train_count=len(train_samples),
        validation_count=len(validation_samples),
        test_count=len(test_samples),
        axis_dispositions=final_dispositions,
    )
    final_bundle = _build_model_bundle(
        dataset,
        split_manifest,
        training_receipt,
        x_axis_head,
        synthetic_status="Passed" if passed else "Failed",
        axis_dispositions=final_dispositions,
    )
    final_parity = build_parity_receipt(dataset, final_bundle, parity_samples)
    final_evaluation = build_evaluation(final_bundle, dataset, split_manifest)
    return final_bundle, training_receipt, final_parity, final_evaluation
