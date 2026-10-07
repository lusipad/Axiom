from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np

from .models import EvaluationClaim, EvaluationEvidence, canonical_hash
from .r5c_interpreter import (
    conditional_effect_feature_vector,
    predict_conditional_effect,
    pure_python_conditional_effect_value,
)
from .r5c_models import (
    R5C_FEATURE_ORDER,
    R5C_TARGETS,
    ConditionalEffectDataset,
    ConditionalEffectDatasetV2,
    ConditionalEffectEvaluation,
    ConditionalEffectHead,
    ConditionalEffectHeadResult,
    ConditionalEffectModelBundle,
    ConditionalEffectModelBundleV2,
    ConditionalEffectParityReceipt,
    ConditionalEffectParityReceiptV2,
    ConditionalEffectPredictionRequest,
    ConditionalEffectResourceBudget,
    ConditionalEffectSample,
    ConditionalEffectSplitManifest,
    ConditionalEffectSplitManifestV2,
    ConditionalEffectTrainingReceipt,
    ConditionalEffectTrainingReceiptV2,
)

RIDGE_LAMBDA = 0.000001
CONFORMAL_COVERAGE = 0.80
TARGET_PARITY_TOLERANCE = 1e-12

DatasetLike = ConditionalEffectDataset | ConditionalEffectDatasetV2
SplitManifestLike = ConditionalEffectSplitManifest | ConditionalEffectSplitManifestV2
ModelBundleLike = ConditionalEffectModelBundle | ConditionalEffectModelBundleV2
TrainingReceiptLike = (
    ConditionalEffectTrainingReceipt | ConditionalEffectTrainingReceiptV2
)
ParityReceiptLike = ConditionalEffectParityReceipt | ConditionalEffectParityReceiptV2


def _samples_for_split(
    dataset: DatasetLike,
    split_manifest: SplitManifestLike,
    split_id: str,
) -> tuple[ConditionalEffectSample, ...]:
    sample_ids = next(
        partition.sample_ids
        for partition in split_manifest.partitions
        if partition.split_id == split_id
    )
    by_id = {sample.sample_id: sample for sample in dataset.samples}
    return tuple(by_id[sample_id] for sample_id in sample_ids)


def validate_conditional_effect_split_contract(
    dataset: DatasetLike,
    split_manifest: SplitManifestLike,
) -> None:
    if split_manifest.dataset_content_hash != dataset.content_hash:
        raise ValueError("split manifest datasetContentHash must identify dataset")
    by_id = {sample.sample_id: sample for sample in dataset.samples}
    assigned = {
        sample_id
        for partition in split_manifest.partitions
        for sample_id in partition.sample_ids
    }
    if assigned != set(by_id):
        raise ValueError("split manifest must assign every dataset sample exactly once")
    for partition in split_manifest.partitions:
        if any(
            by_id[sample_id].declared_split_id != partition.split_id
            for sample_id in partition.sample_ids
        ):
            raise ValueError("split manifest must respect each declared split")


def _target_value(sample: ConditionalEffectSample, target_id: str) -> float:
    if target_id == "cycleTimeSeconds":
        return float(sample.cycle_time_seconds)
    if target_id == "linearFollowingErrorMaxMm":
        return float(sample.linear_following_error_max_mm)
    raise KeyError(target_id)


def _feature_matrix(
    dataset: DatasetLike,
    samples: tuple[ConditionalEffectSample, ...],
) -> np.ndarray:
    return np.asarray(
        [
            conditional_effect_feature_vector(
                dataset.domain,
                feed_override=sample.feed_override,
                sample_period=sample.sample_period,
            )
            for sample in samples
        ],
        dtype=np.float64,
    )


def _ridge_weights(
    dataset: DatasetLike,
    samples: tuple[ConditionalEffectSample, ...],
    target_id: str,
) -> tuple[float, float, float, float, float, float]:
    features = _feature_matrix(dataset, samples)
    targets = np.asarray(
        [_target_value(sample, target_id) for sample in samples], dtype=np.float64
    )
    gram = features.T @ features
    regularized = gram + RIDGE_LAMBDA * np.eye(features.shape[1], dtype=np.float64)
    weights = np.linalg.solve(regularized, features.T @ targets)
    return tuple(round(float(value), 15) for value in weights)  # type: ignore[return-value]


def _absolute_errors(
    dataset: DatasetLike,
    samples: tuple[ConditionalEffectSample, ...],
    *,
    target_id: str,
    weights: tuple[float, float, float, float, float, float],
) -> tuple[float, ...]:
    return tuple(
        abs(
            _target_value(sample, target_id)
            - sum(
                weight * feature
                for weight, feature in zip(
                    weights,
                    conditional_effect_feature_vector(
                        dataset.domain,
                        feed_override=sample.feed_override,
                        sample_period=sample.sample_period,
                    ),
                    strict=True,
                )
            )
        )
        for sample in samples
    )


def _conformal_radius(errors: tuple[float, ...]) -> float:
    ordered = sorted(errors)
    rank = max(1, math.ceil((len(ordered) + 1) * CONFORMAL_COVERAGE))
    return float(ordered[min(rank - 1, len(ordered) - 1)])


def _training_receipt(
    dataset: DatasetLike,
    split_manifest: SplitManifestLike,
    *,
    parent_model_bundle_hash: str | None,
) -> TrainingReceiptLike:
    is_v2 = isinstance(dataset, ConditionalEffectDatasetV2)
    if is_v2 != isinstance(split_manifest, ConditionalEffectSplitManifestV2):
        raise ValueError("dataset and split manifest schema versions must match")
    if is_v2 and parent_model_bundle_hash is None:
        raise ValueError("R5-E training requires parentModelBundleHash")
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.conditional-effect-training-receipt",
        "schemaId": "axiom.intelligence.conditional-effect-training-receipt@1",
        "schemaVersion": 1,
        "receiptId": "axiom.intelligence.r5c-training-receipt.synthetic@1",
        "methodId": "axiom.intelligence.r5c-ridge-regression@1",
        "datasetContentHash": dataset.content_hash,
        "splitManifestHash": split_manifest.content_hash,
        "featureOrder": list(R5C_FEATURE_ORDER),
        "targetIds": list(R5C_TARGETS),
        "lambdaValue": RIDGE_LAMBDA,
        "trainSampleCount": 15,
        "validationSampleCount": 5,
        "testSampleCount": 5,
    }
    receipt_type: (
        type[ConditionalEffectTrainingReceipt]
        | type[ConditionalEffectTrainingReceiptV2]
    ) = ConditionalEffectTrainingReceipt
    if is_v2:
        assert isinstance(dataset, ConditionalEffectDatasetV2)
        payload.update(
            {
                "schemaId": "axiom.intelligence.conditional-effect-training-receipt@2",
                "schemaVersion": 2,
                "receiptId": "axiom.intelligence.r5e-training-receipt.synthetic@2",
                "trainSampleCount": 20,
                "parentModelBundleHash": parent_model_bundle_hash,
                "acquisitionReceiptHash": dataset.acquisition_receipt_hash,
            }
        )
        receipt_type = ConditionalEffectTrainingReceiptV2
    payload["contentHash"] = canonical_hash(payload)
    return receipt_type.model_validate(payload)


def _model_bundle(
    dataset: DatasetLike,
    split_manifest: SplitManifestLike,
    training_receipt: TrainingReceiptLike,
    heads: tuple[ConditionalEffectHead, ConditionalEffectHead],
    *,
    status: Literal["Passed", "Failed"],
) -> ModelBundleLike:
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.conditional-effect-model-bundle",
        "schemaId": "axiom.intelligence.conditional-effect-model-bundle@1",
        "schemaVersion": 1,
        "bundleId": "axiom.intelligence.r5c-conditional-effect-bundle.synthetic@1",
        "domainPackId": "intelligence.domain-pack@3",
        "evaluatorVersion": "intelligence-conditional-effect-evaluator@1",
        "targetInterpreterId": "axiom.intelligence.conditional-effect-interpreter.python@1",
        "inputContractId": "axiom.intelligence.conditional-effect-input@1",
        "outputContractId": "axiom.intelligence.conditional-effect-intervals-with-abstention@1",
        "datasetContentHash": dataset.content_hash,
        "splitManifestHash": split_manifest.content_hash,
        "trainingReceiptHash": training_receipt.content_hash,
        "domain": dataset.domain.model_dump(mode="json", by_alias=True),
        "featureOrder": list(R5C_FEATURE_ORDER),
        "heads": [
            head.model_dump(mode="json", by_alias=True, exclude_none=True)
            for head in heads
        ],
        "resourceBudget": ConditionalEffectResourceBudget(
            targetRuntime="pure-python",
            featureCount=6,
            outputCount=2,
            deterministicNumericType="float64",
            weightDecimalPlaces=15,
        ).model_dump(mode="json", by_alias=True),
        "syntheticConditionalEffectContractStatus": status,
        "realWorldGeneralizationStatus": "Open",
        "permissionLevel": "Offline",
        "deviceWriteAllowed": False,
        "safetyBanner": "SYNTHETIC CONDITIONAL EFFECT / NOT REALITY VALIDATED / NOT DEVICE SAFE",
    }
    bundle_type: (
        type[ConditionalEffectModelBundle] | type[ConditionalEffectModelBundleV2]
    ) = ConditionalEffectModelBundle
    if isinstance(dataset, ConditionalEffectDatasetV2):
        if not isinstance(training_receipt, ConditionalEffectTrainingReceiptV2):
            raise ValueError("R5-E model bundle requires a v2 training receipt")
        payload.update(
            {
                "schemaId": "axiom.intelligence.conditional-effect-model-bundle@2",
                "schemaVersion": 2,
                "bundleId": "axiom.intelligence.r5e-conditional-effect-bundle.synthetic@2",
                "parentModelBundleHash": training_receipt.parent_model_bundle_hash,
                "acquisitionReceiptHash": dataset.acquisition_receipt_hash,
            }
        )
        bundle_type = ConditionalEffectModelBundleV2
    payload["contentHash"] = canonical_hash(payload)
    return bundle_type.model_validate(payload)


def conditional_effect_parity_gap(
    bundle: ModelBundleLike,
    samples: tuple[ConditionalEffectSample, ...],
) -> float:
    features = np.asarray(
        [
            conditional_effect_feature_vector(
                bundle.domain,
                feed_override=sample.feed_override,
                sample_period=sample.sample_period,
            )
            for sample in samples
        ],
        dtype=np.float64,
    )
    maximum = 0.0
    for head in bundle.heads:
        numpy_values = features @ np.asarray(head.weights, dtype=np.float64)
        for index, row in enumerate(features):
            python_value = pure_python_conditional_effect_value(
                head,
                tuple(float(value) for value in row),  # type: ignore[arg-type]
            )
            maximum = max(maximum, abs(float(numpy_values[index]) - python_value))
    return float(maximum)


def _parity_receipt(
    dataset: DatasetLike,
    bundle: ModelBundleLike,
) -> ParityReceiptLike:
    gap = conditional_effect_parity_gap(bundle, dataset.samples)
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.conditional-effect-parity-receipt",
        "schemaId": "axiom.intelligence.conditional-effect-parity-receipt@1",
        "schemaVersion": 1,
        "receiptId": "axiom.intelligence.r5c-parity-receipt.synthetic@1",
        "modelBundleHash": bundle.content_hash,
        "datasetContentHash": dataset.content_hash,
        "maxAbsGap": gap,
        "sampleCount": 25,
        "targetCount": 2,
        "status": "Passed" if gap <= TARGET_PARITY_TOLERANCE else "Failed",
    }
    receipt_type: (
        type[ConditionalEffectParityReceipt] | type[ConditionalEffectParityReceiptV2]
    ) = ConditionalEffectParityReceipt
    if isinstance(dataset, ConditionalEffectDatasetV2):
        payload.update(
            {
                "schemaId": "axiom.intelligence.conditional-effect-parity-receipt@2",
                "schemaVersion": 2,
                "receiptId": "axiom.intelligence.r5e-parity-receipt.synthetic@2",
                "sampleCount": 30,
                "acquisitionReceiptHash": dataset.acquisition_receipt_hash,
            }
        )
        receipt_type = ConditionalEffectParityReceiptV2
    payload["contentHash"] = canonical_hash(payload)
    return receipt_type.model_validate(payload)


def _rmse(values: tuple[float, ...]) -> float:
    return math.sqrt(sum(value * value for value in values) / len(values))


def _head_result(
    bundle: ModelBundleLike,
    dataset: DatasetLike,
    split_manifest: SplitManifestLike,
    target_id: str,
) -> ConditionalEffectHeadResult:
    train = _samples_for_split(dataset, split_manifest, "train")
    test = _samples_for_split(dataset, split_manifest, "test")
    target_values = tuple(_target_value(sample, target_id) for sample in train)
    baseline = sum(target_values) / len(target_values)
    baseline_rmse = _rmse(
        tuple(_target_value(sample, target_id) - baseline for sample in test)
    )
    residuals = []
    covered = 0
    for sample in test:
        prediction = predict_conditional_effect(
            ConditionalEffectPredictionRequest(
                modelBundle=bundle,
                feedOverride=sample.feed_override,
                samplePeriod=sample.sample_period,
            )
        )
        interval = next(
            item for item in prediction.predictions if item.target_id == target_id
        )
        observed = _target_value(sample, target_id)
        residuals.append(observed - interval.value)
        covered += interval.lower <= observed <= interval.upper
    model_rmse = _rmse(tuple(residuals))
    all_values = tuple(_target_value(sample, target_id) for sample in dataset.samples)
    target_range = max(all_values) - min(all_values)
    normalized_rmse = model_rmse / target_range
    unit = "s" if target_id == "cycleTimeSeconds" else "mm"
    return ConditionalEffectHeadResult(
        targetId=target_id,
        unit=unit,
        baselineRmse=baseline_rmse,
        modelRmse=model_rmse,
        normalizedRmse=normalized_rmse,
        improvementRatio=1.0 - model_rmse / baseline_rmse,
        conformalCoverage=covered / len(test),
    )


def build_conditional_effect_evaluation(
    bundle: ModelBundleLike,
    dataset: DatasetLike,
    split_manifest: SplitManifestLike,
    parity_receipt: ParityReceiptLike,
) -> ConditionalEffectEvaluation:
    results = tuple(
        _head_result(bundle, dataset, split_manifest, target_id)
        for target_id in R5C_TARGETS
    )
    ood_requests = (
        (0.64, 0.06),
        (1.01, 0.06),
        (0.80, 0.039),
        (0.80, 0.081),
    )
    abstention_rate = sum(
        predict_conditional_effect(
            ConditionalEffectPredictionRequest(
                modelBundle=bundle,
                feedOverride=feed_override,
                samplePeriod=sample_period,
            )
        ).status
        == "Abstained"
        for feed_override, sample_period in ood_requests
    ) / len(ood_requests)
    cycle, linear_error = results
    passed = (
        cycle.normalized_rmse <= 0.02
        and linear_error.normalized_rmse <= 0.05
        and all(item.conformal_coverage >= 0.80 for item in results)
        and abstention_rate == 1.0
        and parity_receipt.max_abs_gap <= TARGET_PARITY_TOLERANCE
    )
    status: Literal["Passed", "Failed"] = "Passed" if passed else "Failed"
    return ConditionalEffectEvaluation(
        syntheticConditionalEffectContractStatus=status,
        realWorldGeneralizationStatus="Open",
        headResults=results,
        oodAbstentionRate=abstention_rate,
        targetParityMaxAbsGap=parity_receipt.max_abs_gap,
        claims=(
            EvaluationClaim(
                claimId="intelligence.synthetic-conditional-effect-claim@1",
                title="Synthetic conditional effect",
                status="Supported" if passed else "Refuted",
                statement=(
                    "The declared synthetic SIL parameter domain meets the separate cycle-time "
                    "and linear-error validation gates."
                ),
                evidenceLevel="Observed",
            ),
            EvaluationClaim(
                claimId="intelligence.real-world-generalization-claim@1",
                title="Real-world generalization",
                status="Inconclusive",
                statement=(
                    "Synthetic SIL evidence does not establish real-device generalization."
                ),
                reasonCode="RealPairedHoldoutMissing",
                evidenceLevel="Observed",
            ),
        ),
        evidence=(
            EvaluationEvidence(
                evidenceId="r5c-dataset",
                title="Conditional-effect dataset",
                contentHash=dataset.content_hash,
                summary="Immutable 5x5 synthetic SIL parameter study with spatial split labels.",
            ),
            EvaluationEvidence(
                evidenceId="r5c-split",
                title="Spatial split manifest",
                contentHash=split_manifest.content_hash,
                summary="Train, validation, and test parameter points are sample-disjoint.",
            ),
            EvaluationEvidence(
                evidenceId="r5c-model",
                title="Two-head model bundle",
                contentHash=bundle.content_hash,
                summary="Cycle time in seconds and linear error in millimetres remain separate outputs.",
            ),
        ),
    )


def train_r5c_bundle(
    dataset: DatasetLike,
    split_manifest: SplitManifestLike,
    *,
    parent_model_bundle_hash: str | None = None,
) -> tuple[
    ModelBundleLike,
    TrainingReceiptLike,
    ParityReceiptLike,
    ConditionalEffectEvaluation,
]:
    validate_conditional_effect_split_contract(dataset, split_manifest)
    train = _samples_for_split(dataset, split_manifest, "train")
    validation = _samples_for_split(dataset, split_manifest, "validation")
    heads = []
    for target_id in R5C_TARGETS:
        weights = _ridge_weights(dataset, train, target_id)
        radius = _conformal_radius(
            _absolute_errors(
                dataset,
                validation,
                target_id=target_id,
                weights=weights,
            )
        )
        heads.append(
            ConditionalEffectHead(
                targetId=target_id,
                unit="s" if target_id == "cycleTimeSeconds" else "mm",
                weights=weights,
                conformalRadius=radius,
            )
        )
    frozen_heads = tuple(heads)
    if len(frozen_heads) != 2:
        raise AssertionError("R5-C must train exactly two output heads")
    typed_heads = (frozen_heads[0], frozen_heads[1])
    receipt = _training_receipt(
        dataset,
        split_manifest,
        parent_model_bundle_hash=parent_model_bundle_hash,
    )
    provisional = _model_bundle(
        dataset, split_manifest, receipt, typed_heads, status="Passed"
    )
    parity = _parity_receipt(dataset, provisional)
    evaluation = build_conditional_effect_evaluation(
        provisional, dataset, split_manifest, parity
    )
    if evaluation.synthetic_conditional_effect_contract_status == "Passed":
        return provisional, receipt, parity, evaluation
    bundle = _model_bundle(
        dataset, split_manifest, receipt, typed_heads, status="Failed"
    )
    parity = _parity_receipt(dataset, bundle)
    evaluation = build_conditional_effect_evaluation(
        bundle, dataset, split_manifest, parity
    )
    return bundle, receipt, parity, evaluation


__all__ = [
    "CONFORMAL_COVERAGE",
    "RIDGE_LAMBDA",
    "TARGET_PARITY_TOLERANCE",
    "build_conditional_effect_evaluation",
    "conditional_effect_parity_gap",
    "train_r5c_bundle",
    "validate_conditional_effect_split_contract",
]
