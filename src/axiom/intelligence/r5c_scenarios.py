from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from importlib.resources import files
from typing import Any

from ..models import RunSpec
from ..physical import (
    build_r4_multirate_physical_model,
    evaluate_canonical_parameter_point,
)
from .models import canonical_hash
from .r5c_interpreter import predict_conditional_effect
from .r5c_models import (
    R5C_DEFAULT_SCENARIO_ID,
    R5C_FEED_OVERRIDES,
    R5C_SAMPLE_PERIODS,
    ConditionalEffectDataset,
    ConditionalEffectDomain,
    ConditionalEffectEvaluationRequest,
    ConditionalEffectPartition,
    ConditionalEffectPredictionRequest,
    ConditionalEffectSplitManifest,
    R5CAcceptanceThresholds,
    R5CExamplePayload,
    R5CManifest,
    R5CScenario,
    R5CScenarioSummary,
)
from .r5c_training import train_r5c_bundle


def _feed_code(value: float) -> str:
    return f"{round(value * 1000):04d}"


def _period_code(value: float) -> str:
    return f"{round(value * 1000):03d}ms"


def _split_id(feed_index: int, period_index: int) -> str:
    bucket = (feed_index + period_index) % 5
    if bucket == 0:
        return "validation"
    if bucket == 1:
        return "test"
    return "train"


def _build_dataset() -> ConditionalEffectDataset:
    physical_model = build_r4_multirate_physical_model()
    samples: list[dict[str, Any]] = []
    for feed_index, feed_override in enumerate(R5C_FEED_OVERRIDES):
        for period_index, sample_period in enumerate(R5C_SAMPLE_PERIODS):
            feed_code = _feed_code(feed_override)
            period_code = _period_code(sample_period)
            point = evaluate_canonical_parameter_point(
                physical_model,
                feed_override=feed_override,
                sample_period=sample_period,
                profile_id=(
                    f"five-axis.r5c.motion-profile.feed-{feed_code}@1"
                ),
                feed_source="intelligence.r5c.feed-override-study@1",
                trajectory_id=f"five-axis.r5c.m4.feed-{feed_code}-v1",
                invocation_id=(
                    f"intelligence.r5c.feed-{feed_code}.period-{period_code}.invoke"
                ),
                response_trace_id=(
                    f"intelligence.r5c.feed-{feed_code}.period-{period_code}.response@1"
                ),
            )
            samples.append(
                {
                    "sampleId": f"r5c-feed-{feed_code}-period-{period_code}",
                    "feedOverride": feed_override,
                    "samplePeriod": sample_period,
                    "declaredSplitId": _split_id(feed_index, period_index),
                    "cycleTimeSeconds": point.continuous_verification.total_duration_seconds,
                    "linearFollowingErrorMaxMm": point.linear_following_error_max_mm,
                    "commandSampleCount": len(point.command.samples),
                    "m4ContentHash": canonical_hash(point.continuous_trajectory),
                    "m5ContentHash": point.command.content_id,
                    "physicalResponseContentHash": point.response.content_hash,
                    "sourceKind": "synthetic-sil",
                    "sourceScenarioId": "canonical-head-table-solver",
                }
            )
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.conditional-effect-dataset",
        "schemaId": "axiom.intelligence.conditional-effect-dataset@1",
        "schemaVersion": 1,
        "datasetId": "axiom.intelligence.r5c-canonical-head-table-grid@1",
        "domain": ConditionalEffectDomain(
            domainId="axiom.intelligence.r5c-parameter-domain@1",
            feedOverrideMinimum=0.65,
            feedOverrideMaximum=1.0,
            samplePeriodMinimum=0.04,
            samplePeriodMaximum=0.08,
            feedOverrideUnit="ratio",
            samplePeriodUnit="s",
        ).model_dump(mode="json", by_alias=True),
        "governance": {
            "governanceId": "axiom.intelligence.r5c-synthetic-governance@1",
            "sourceKind": "synthetic-sil",
            "syntheticConditionalEffectContractStatus": "Open",
            "realWorldGeneralizationStatus": "Open",
            "licenseId": "axiom-project-internal-synthetic@1",
            "allowedUses": [
                "conditional-effect-contract-validation",
                "deterministic-testing",
            ],
            "sensitivity": "synthetic",
            "retentionPolicyId": "axiom.synthetic-fixture-retention@1",
            "redistributionAllowed": False,
            "safetyBanner": "SYNTHETIC CONDITIONAL EFFECT / NOT REALITY VALIDATED / NOT DEVICE SAFE",
        },
        "selectionPolicyId": "axiom.intelligence.r5c-spatial-split-policy@1",
        "lineagePolicyId": "axiom.intelligence.r5c-m4-m5-physical-lineage@1",
        "sourceKind": "synthetic-sil",
        "knownBiases": [
            "All labels are deterministic R4 synthetic SIL responses.",
            "The first release covers one canonical head-table path and one physical model.",
        ],
        "coverageGaps": [
            "No independent real-device holdout is included.",
            "No thermal, cutting-force, backlash, wear, or controller-specific effects are represented.",
        ],
        "samples": samples,
    }
    payload["contentHash"] = canonical_hash(payload)
    return ConditionalEffectDataset.model_validate(payload)


def _build_split_manifest(
    dataset: ConditionalEffectDataset,
) -> ConditionalEffectSplitManifest:
    partitions = tuple(
        ConditionalEffectPartition(
            splitId=split_id,
            sampleIds=tuple(
                sample.sample_id
                for sample in dataset.samples
                if sample.declared_split_id == split_id
            ),
        )
        for split_id in ("train", "validation", "test")
    )
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.conditional-effect-split-manifest",
        "schemaId": "axiom.intelligence.conditional-effect-split-manifest@1",
        "schemaVersion": 1,
        "manifestId": "axiom.intelligence.r5c-spatial-split@1",
        "datasetContentHash": dataset.content_hash,
        "partitions": [
            partition.model_dump(mode="json", by_alias=True)
            for partition in partitions
        ],
    }
    payload["contentHash"] = canonical_hash(payload)
    return ConditionalEffectSplitManifest.model_validate(payload)


def build_r5c_manifest() -> R5CManifest:
    return R5CManifest(
        manifestId="axiom.intelligence.r5c-manifest@1",
        schemaId="axiom.intelligence.r5c-manifest@1",
        schemaVersion=1,
        stage="R5-C",
        domainPackId="intelligence.domain-pack@3",
        platform="windows",
        defaultScenarioId=R5C_DEFAULT_SCENARIO_ID,
        parameterDomain=ConditionalEffectDomain(
            domainId="axiom.intelligence.r5c-parameter-domain@1",
            feedOverrideMinimum=0.65,
            feedOverrideMaximum=1.0,
            samplePeriodMinimum=0.04,
            samplePeriodMaximum=0.08,
            feedOverrideUnit="ratio",
            samplePeriodUnit="s",
        ),
        outputTargets=("cycleTimeSeconds", "linearFollowingErrorMaxMm"),
        acceptanceThresholds=R5CAcceptanceThresholds(
            maximumCycleTimeNormalizedRmse=0.02,
            maximumLinearErrorNormalizedRmse=0.05,
            minimumConformalCoverage=0.8,
            requiredOodAbstentionRate=1.0,
            maximumTargetParityGap=1e-12,
        ),
        syntheticConditionalEffectContractStatus="Passed",
        realWorldGeneralizationStatus="Open",
        permissionLevel="Offline",
        deviceWriteAllowed=False,
        safetyBanner=(
            "SYNTHETIC CONDITIONAL EFFECT / NOT REALITY VALIDATED / NOT DEVICE SAFE"
        ),
    )


def _build_scenario() -> R5CScenario:
    dataset = _build_dataset()
    split_manifest = _build_split_manifest(dataset)
    model_bundle, training_receipt, parity_receipt, evaluation = train_r5c_bundle(
        dataset, split_manifest
    )
    run_spec: dict[str, Any] = {
        "subjectId": "axiom.intelligence.r5c-conditional-effect-model@1",
        "domainPackId": "intelligence.domain-pack@3",
        "runnerId": "intelligence-conditional-effect-validation@1",
        "evaluatorVersion": "intelligence-conditional-effect-evaluator@1",
        "request": {
            "artifact": model_bundle.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "dataset": dataset.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "splitManifest": split_manifest.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "trainingReceipt": training_receipt.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "parityReceipt": parity_receipt.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "case": {
                "caseId": "axiom.intelligence.r5c-conditional-effect.case@1",
                "requiredMetrics": [
                    "intelligence.r5c.integrity-valid@1",
                    "intelligence.r5c.synthetic-contract@1",
                    {
                        "metricId": "intelligence.r5c.cycle-time-normalized-rmse@1",
                        "threshold": {"operator": "<=", "value": 0.02},
                    },
                    {
                        "metricId": "intelligence.r5c.linear-error-normalized-rmse@1",
                        "threshold": {"operator": "<=", "value": 0.05},
                    },
                    {
                        "metricId": "intelligence.r5c.minimum-conformal-coverage@1",
                        "threshold": {"operator": ">=", "value": 0.8},
                    },
                    {
                        "metricId": "intelligence.r5c.ood-abstention-rate@1",
                        "threshold": {"operator": ">=", "value": 1.0},
                    },
                    {
                        "metricId": "intelligence.r5c.target-parity-max-abs-gap@1",
                        "threshold": {"operator": "<=", "value": 1e-12},
                    },
                ],
                "optionalMetrics": [
                    "intelligence.r5c.real-world-generalization@1"
                ],
            },
        },
    }
    parsed_run_spec = RunSpec.model_validate(run_spec)
    evaluation_request = ConditionalEffectEvaluationRequest.model_validate(
        parsed_run_spec.request.model_dump(
            mode="json", by_alias=True, exclude_unset=True
        )
    )
    return R5CScenario(
        summary=R5CScenarioSummary(
            scenarioId=R5C_DEFAULT_SCENARIO_ID,
            title="Canonical head-table conditional-effect surrogate",
            description=(
                "A deterministic 5x5 R4 SIL study validates separate cycle-time and "
                "linear-following-error heads with spatial holdout points."
            ),
            expectedOutcome="Passed",
            expectedExecutionStatus="Succeeded",
            realWorldGeneralizationStatus="Open",
        ),
        dataset=dataset,
        split_manifest=split_manifest,
        model_bundle=model_bundle,
        training_receipt=training_receipt,
        parity_receipt=parity_receipt,
        evaluation=evaluation,
        evaluation_request=evaluation_request,
        run_spec=run_spec,
    )


@lru_cache(maxsize=1)
def _scenario() -> R5CScenario:
    return _build_scenario()


def list_r5c_scenarios() -> tuple[R5CScenarioSummary, ...]:
    return (_scenario().summary,)


def load_r5c_fixture_manifest() -> dict[str, Any]:
    resource = files("axiom.intelligence").joinpath(
        "fixtures", "r5c-manifest.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def load_r5c_scenario(
    scenario_id: str = R5C_DEFAULT_SCENARIO_ID,
) -> R5CScenario:
    if scenario_id != R5C_DEFAULT_SCENARIO_ID:
        raise KeyError(
            f"unknown R5-C scenario '{scenario_id}'; expected: {R5C_DEFAULT_SCENARIO_ID}"
        )
    return _scenario()


def r5c_example_payload(
    scenario_id: str = R5C_DEFAULT_SCENARIO_ID,
) -> R5CExamplePayload:
    scenario = load_r5c_scenario(scenario_id)
    prediction = predict_conditional_effect(
        ConditionalEffectPredictionRequest(
            modelBundle=scenario.model_bundle,
            feedOverride=0.82,
            samplePeriod=0.055,
        )
    )
    return R5CExamplePayload(
        manifest=build_r5c_manifest(),
        scenario=scenario.summary,
        dataset=scenario.dataset,
        splitManifest=scenario.split_manifest,
        modelBundle=scenario.model_bundle,
        trainingReceipt=scenario.training_receipt,
        parityReceipt=scenario.parity_receipt,
        evaluation=scenario.evaluation,
        predictionExample=prediction,
        runSpec=RunSpec.model_validate(scenario.run_spec),
    )


def r5c_example_run_spec(
    scenario_id: str = R5C_DEFAULT_SCENARIO_ID,
) -> dict[str, Any]:
    return deepcopy(load_r5c_scenario(scenario_id).run_spec)


def validate_r5c_example_run_spec(
    scenario_id: str = R5C_DEFAULT_SCENARIO_ID,
) -> RunSpec:
    return RunSpec.model_validate(r5c_example_run_spec(scenario_id))


__all__ = [
    "R5C_DEFAULT_SCENARIO_ID",
    "build_r5c_manifest",
    "list_r5c_scenarios",
    "load_r5c_fixture_manifest",
    "load_r5c_scenario",
    "r5c_example_payload",
    "r5c_example_run_spec",
    "validate_r5c_example_run_spec",
]
