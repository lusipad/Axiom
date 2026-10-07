from __future__ import annotations

import json
import math
import platform
from importlib.resources import files
from typing import Any

from .models import canonical_hash
from .r5c_interpreter import (
    conditional_effect_feature_vector,
    predict_conditional_effect,
)
from .r5c_models import ConditionalEffectPredictionRequest
from .r5c_scenarios import load_r5c_scenario
from .r5c_training import RIDGE_LAMBDA
from .r5d_models import (
    R5D_CANDIDATE_FEED_OVERRIDES,
    R5D_CANDIDATE_POOL_ID,
    R5D_CANDIDATE_POOL_SIZE,
    R5D_CANDIDATE_SAMPLE_PERIODS,
    R5D_DEFAULT_AVAILABLE_CANDIDATE_COUNT,
    R5D_DEFAULT_BATCH_SIZE,
    R5D_MAXIMUM_BATCH_SIZE,
    R5D_PLANNER_ID,
    R5D_SAFETY_BANNER,
    R5DExamplePayload,
    R5DExperimentPlanRequest,
    R5DManifest,
    SimulationExperimentPlan,
    SimulationExperimentProposal,
)


def _freeze(value: float) -> float:
    return float(f"{value:.15g}")


def _features(
    request: R5DExperimentPlanRequest, point: tuple[float, float]
) -> tuple[float, float, float, float, float, float]:
    return conditional_effect_feature_vector(
        request.dataset.domain,
        feed_override=point[0],
        sample_period=point[1],
    )


def _information_matrix(request: R5DExperimentPlanRequest) -> list[list[float]]:
    train_ids = set(request.split_manifest.partitions[0].sample_ids)
    design = [
        _features(request, (sample.feed_override, sample.sample_period))
        for sample in request.dataset.samples
        if sample.sample_id in train_ids
    ]
    size = len(design[0])
    return [
        [
            sum(row[left] * row[right] for row in design)
            + (RIDGE_LAMBDA if left == right else 0.0)
            for right in range(size)
        ]
        for left in range(size)
    ]


def _solve_linear_system(
    matrix: list[list[float]], right_hand_side: tuple[float, ...]
) -> tuple[float, ...]:
    size = len(matrix)
    augmented = [[*matrix[row], right_hand_side[row]] for row in range(size)]
    for column in range(size):
        pivot = max(
            range(column, size),
            key=lambda row: (abs(augmented[row][column]), -row),
        )
        if abs(augmented[pivot][column]) <= 1e-15:
            raise ValueError("R5-D information matrix is singular")
        if pivot != column:
            augmented[column], augmented[pivot] = (
                augmented[pivot],
                augmented[column],
            )
        pivot_value = augmented[column][column]
        for row in range(column + 1, size):
            factor = augmented[row][column] / pivot_value
            augmented[row][column] = 0.0
            for index in range(column + 1, size + 1):
                augmented[row][index] -= factor * augmented[column][index]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        remainder = augmented[row][size] - sum(
            augmented[row][column] * solution[column] for column in range(row + 1, size)
        )
        solution[row] = remainder / augmented[row][row]
    return tuple(solution)


def _design_leverage(
    information: list[list[float]], features: tuple[float, ...]
) -> float:
    solved = _solve_linear_system(information, features)
    value = sum(left * right for left, right in zip(features, solved, strict=True))
    if value < 0.0 and abs(value) <= 1e-12:
        return 0.0
    if value < 0.0:
        raise ValueError("R5-D design leverage cannot be negative")
    return value


def _add_outer_product(
    information: list[list[float]], features: tuple[float, ...]
) -> None:
    for row in range(len(information)):
        for column in range(len(information)):
            information[row][column] += features[row] * features[column]


def _available_candidates(
    request: R5DExperimentPlanRequest,
) -> list[tuple[float, float]]:
    observed = {
        (sample.feed_override, sample.sample_period)
        for sample in request.dataset.samples
    }
    return [
        (feed, period)
        for feed in R5D_CANDIDATE_FEED_OVERRIDES
        for period in R5D_CANDIDATE_SAMPLE_PERIODS
        if (feed, period) not in observed
    ]


def _ranked_candidates(
    request: R5DExperimentPlanRequest,
    information: list[list[float]],
    candidates: list[tuple[float, float]],
) -> list[tuple[float, tuple[float, float]]]:
    scored = [
        (_design_leverage(information, _features(request, point)), point)
        for point in candidates
    ]
    return sorted(scored, key=lambda item: (-_freeze(item[0]), item[1]))


def _sample_count(duration: float, sample_period: float) -> int:
    count = math.floor((duration + 1e-12) / sample_period) + 1
    if not math.isclose(
        (count - 1) * sample_period,
        duration,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        count += 1
    return count


def _point_code(point: tuple[float, float]) -> tuple[str, str]:
    return f"{round(point[0] * 1000):04d}", f"{round(point[1] * 1000):03d}ms"


def _sealed_plan(payload: dict[str, Any]) -> SimulationExperimentPlan:
    payload["contentHash"] = canonical_hash(payload)
    return SimulationExperimentPlan.model_validate(payload)


def build_r5d_manifest() -> R5DManifest:
    return R5DManifest(
        manifestId="axiom.intelligence.r5d-manifest@1",
        schemaId="axiom.intelligence.r5d-manifest@1",
        schemaVersion=1,
        stage="R5-D",
        platform="windows",
        plannerId=R5D_PLANNER_ID,
        candidatePoolId=R5D_CANDIDATE_POOL_ID,
        candidatePoolSize=R5D_CANDIDATE_POOL_SIZE,
        defaultAvailableCandidateCount=R5D_DEFAULT_AVAILABLE_CANDIDATE_COUNT,
        defaultBatchSize=R5D_DEFAULT_BATCH_SIZE,
        maximumBatchSize=R5D_MAXIMUM_BATCH_SIZE,
        designFeatureCount=6,
        designPartition="train",
        selectionObjective="maximum-design-leverage",
        globalOptimalityStatus="NotClaimed",
        realWorldGeneralizationStatus="Open",
        permissionLevel="Offline",
        automaticExecutionAllowed=False,
        deviceWriteAllowed=False,
        safetyBanner=R5D_SAFETY_BANNER,
    )


def build_r5d_experiment_plan_request(
    *, batch_size: int = R5D_DEFAULT_BATCH_SIZE
) -> R5DExperimentPlanRequest:
    scenario = load_r5c_scenario()
    return R5DExperimentPlanRequest(
        modelBundle=scenario.model_bundle,
        dataset=scenario.dataset,
        splitManifest=scenario.split_manifest,
        batchSize=batch_size,
    )


def plan_r5d_simulation_experiments(
    request: R5DExperimentPlanRequest,
    *,
    current_platform: str | None = None,
) -> SimulationExperimentPlan:
    runtime_platform = current_platform or platform.system()
    observed_count = len(request.dataset.samples)
    design_count = len(request.split_manifest.partitions[0].sample_ids)
    available_count = R5D_CANDIDATE_POOL_SIZE - observed_count
    plan_prefix = "r5d-simulation-plan"
    if request.dataset.schema_version == 2:
        plan_prefix = "r5e-next-simulation-plan"
    common: dict[str, Any] = {
        "schemaId": "axiom.intelligence.simulation-experiment-plan@1",
        "planId": (
            f"axiom.intelligence.{plan_prefix}.batch-{request.batch_size:02d}@1"
        ),
        "plannerId": R5D_PLANNER_ID,
        "candidatePoolId": R5D_CANDIDATE_POOL_ID,
        "modelBundleHash": request.model_bundle.content_hash,
        "datasetContentHash": request.dataset.content_hash,
        "splitManifestContentHash": request.split_manifest.content_hash,
        "candidatePoolSize": R5D_CANDIDATE_POOL_SIZE,
        "availableCandidateCount": available_count,
        "designSampleCount": design_count,
        "excludedObservedPointCount": observed_count,
        "requestedBatchSize": request.batch_size,
        "uncertaintyScope": "linear-design-epistemic-proxy",
        "globalOptimalityStatus": "NotClaimed",
        "experimentExecutionStatus": "NotExecuted",
        "modelUpdateStatus": "NotPerformed",
        "realWorldGeneralizationStatus": "Open",
        "permissionLevel": "Offline",
        "automaticExecutionAllowed": False,
        "deviceWriteAllowed": False,
        "knownLimitations": [
            "Design leverage is a linear-model epistemic proxy, not a calibrated error probability.",
            "The first planner treats all synthetic SIL candidates as equal acquisition cost.",
            "A new label must create a new DatasetSnapshot and model version before replanning.",
        ],
        "safetyBanner": R5D_SAFETY_BANNER,
    }
    if runtime_platform.casefold() != "windows":
        return _sealed_plan(
            {
                **common,
                "status": "Blocked",
                "reasonCodes": ["UnsupportedRuntimePlatform"],
                "proposals": [],
            }
        )

    information = _information_matrix(request)
    candidates = _available_candidates(request)
    initial_ranked = _ranked_candidates(request, information, candidates)
    maximum_before = initial_ranked[0][0]
    proposals: list[SimulationExperimentProposal] = []
    for rank in range(1, request.batch_size + 1):
        score, point = _ranked_candidates(request, information, candidates)[0]
        prediction = predict_conditional_effect(
            ConditionalEffectPredictionRequest(
                modelBundle=request.model_bundle,
                feedOverride=point[0],
                samplePeriod=point[1],
            )
        )
        if prediction.status != "Predicted" or len(prediction.predictions) != 2:
            raise ValueError("R5-D candidate must have two in-domain predictions")
        cycle = prediction.predictions[0]
        feed_code, period_code = _point_code(point)
        proposals.append(
            SimulationExperimentProposal(
                rank=rank,
                experimentId=(
                    f"axiom.intelligence.r5d.feed-{feed_code}.period-{period_code}@1"
                ),
                feedOverride=point[0],
                samplePeriod=point[1],
                feedOverrideUnit="ratio",
                samplePeriodUnit="s",
                designLeverage=_freeze(score),
                predictedOutcomes=prediction.predictions,
                estimatedCommandSampleCount=_sample_count(cycle.value, point[1]),
                plannedRunnerId="axiom.physical.canonical-f3-f4-r4-replay@1",
                sourceKind="synthetic-sil",
                labelStatus="NotAcquired",
                automaticExecutionAllowed=False,
                deviceWriteAllowed=False,
            )
        )
        features = _features(request, point)
        _add_outer_product(information, features)
        candidates.remove(point)
    maximum_after = _ranked_candidates(request, information, candidates)[0][0]
    frozen_before = _freeze(maximum_before)
    frozen_after = _freeze(maximum_after)
    reduction = _freeze(1.0 - frozen_after / frozen_before)
    return _sealed_plan(
        {
            **common,
            "status": "Planned",
            "reasonCodes": [],
            "proposals": [
                proposal.model_dump(mode="json", by_alias=True)
                for proposal in proposals
            ],
            "maximumCandidateLeverageBefore": frozen_before,
            "maximumCandidateLeverageAfter": frozen_after,
            "relativeMaximumLeverageReduction": reduction,
        }
    )


def r5d_example_payload() -> R5DExamplePayload:
    request = build_r5d_experiment_plan_request()
    return R5DExamplePayload(
        manifest=build_r5d_manifest(),
        request=request,
        plan=plan_r5d_simulation_experiments(request),
    )


def load_r5d_fixture_manifest() -> dict[str, Any]:
    resource = files("axiom.intelligence").joinpath("fixtures", "r5d-manifest.json")
    return json.loads(resource.read_text(encoding="utf-8"))


__all__ = [
    "build_r5d_experiment_plan_request",
    "build_r5d_manifest",
    "load_r5d_fixture_manifest",
    "plan_r5d_simulation_experiments",
    "r5d_example_payload",
]
