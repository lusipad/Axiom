from __future__ import annotations

import math
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib.resources import files
from typing import Any, Callable

from ..five_axis import validate_f4_example_run_spec
from ..models import RunSpec
from .models import (
    AXES,
    DatasetSnapshot,
    IntelligenceSample,
    R5_DOMAIN_PACK_ID,
    R5_EVALUATOR_ID,
    R5_RUNNER_ID,
    R5ExamplePayload,
    R5Manifest,
    R5Scenario,
    R5ScenarioSummary,
    SplitManifest,
    canonical_hash,
)
from .training import OOD_MARGIN_FRACTION, feature_vector, train_r5_bundle

DEFAULT_SCENARIO_ID = "synthetic-residual-contract"
LABEL_DERIVATION_ID = "axiom.intelligence.independent-two-stage-oracle@1"
_BASE_TIME = datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc)
_SOURCE_LAYOUT = (
    ("train", "canonical-dual-table-solver", "dual-table", 0, 0.0),
    ("validation", "canonical-head-table-solver", "head-table", 20, 0.35),
    ("test", "canonical-dual-head-solver", "dual-head", 40, 0.70),
)


def _iso(minutes: int) -> str:
    return (_BASE_TIME + timedelta(minutes=minutes)).isoformat()


def _first_order_response(command: tuple[float, ...], times: tuple[float, ...]) -> tuple[float, ...]:
    state = command[0]
    response = [state]
    for index in range(1, len(command)):
        dt = times[index] - times[index - 1]
        alpha = math.exp(-dt / 0.12)
        held_command = command[index - 1]
        state = held_command + (state - held_command) * alpha
        response.append(state)
    return tuple(response)


def _independent_oracle_response(
    command: tuple[float, ...],
    times: tuple[float, ...],
    *,
    phase: float,
) -> tuple[float, ...]:
    primary = command[0]
    secondary = command[0]
    response = [secondary + 0.001]
    duration = max(times[-1] - times[0], 1e-12)
    for index in range(1, len(command)):
        dt = times[index] - times[index - 1]
        held_command = command[index - 1]
        primary = held_command + (primary - held_command) * math.exp(-dt / 0.08)
        secondary = primary + (secondary - primary) * math.exp(-dt / 0.04)
        normalized_time = (times[index] - times[0]) / duration
        disturbance = 0.003 * (
            0.65 * math.sin(2.7 * times[index] + phase)
            + 0.25 * math.cos(5.1 * times[index] + 0.5 * phase)
            + 0.10 * normalized_time
        )
        response.append(secondary + 0.001 + disturbance)
    return tuple(response)


def _source_rows(
    split_id: str,
    scenario_id: str,
    topology: str,
    minute_offset: int,
    phase: float,
) -> list[dict[str, Any]]:
    source_spec = validate_f4_example_run_spec(scenario_id)
    command_artifact = source_spec.request.artifact.model_dump(mode="json", by_alias=True)
    source_samples = command_artifact["samples"]
    times = tuple(float(sample["t"]) for sample in source_samples)
    x_origin = float(source_samples[0]["q"][0])
    x_command = tuple(float(sample["q"][0] - x_origin) for sample in source_samples)
    simulation = _first_order_response(x_command, times)
    observation = _independent_oracle_response(x_command, times, phase=phase)
    duration = max(times[-1] - times[0], 1e-12)
    return [
        {
            "sampleId": f"{split_id}-{index}",
            "axisId": "X",
            "topology": topology,
            "trajectoryFamily": f"trajectory-{topology}",
            "taskId": f"task-{topology}",
            "deviceBatchId": f"synthetic-batch-{topology}",
            "pairId": f"synthetic-pair-{topology}",
            "declaredSplitId": split_id,
            "scenarioRole": "in-domain",
            "upstreamScenarioId": scenario_id,
            "sourceCommandContentId": command_artifact["contentId"],
            "sourceCommandSampleId": sample["sampleId"],
            "labelDerivationId": LABEL_DERIVATION_ID,
            "eventTime": _iso(minute_offset + index),
            "t": (times[index] - times[0]) / duration,
            "command": x_command[index],
            "simulation": simulation[index],
            "observation": observation[index],
        }
        for index, sample in enumerate(source_samples)
    ]


def _mark_test_ood(rows: list[dict[str, Any]]) -> None:
    train_samples = tuple(IntelligenceSample.model_validate(row) for row in rows if row["declaredSplitId"] == "train")
    train_features = tuple(feature_vector(sample) for sample in train_samples)
    columns = tuple(zip(*train_features, strict=True))
    lower = tuple(min(column) for column in columns)
    upper = tuple(max(column) for column in columns)
    for row in rows:
        if row["declaredSplitId"] != "test":
            continue
        features = feature_vector(IntelligenceSample.model_validate(row))
        outside = any(
            value < minimum - OOD_MARGIN_FRACTION * (maximum - minimum)
            or value > maximum + OOD_MARGIN_FRACTION * (maximum - minimum)
            for value, minimum, maximum in zip(features, lower, upper, strict=True)
        )
        row["scenarioRole"] = "ood-probe" if outside else "in-domain"


def _dataset_snapshot(rows: list[dict[str, Any]]) -> DatasetSnapshot:
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.dataset-snapshot",
        "schemaId": "axiom.intelligence.dataset-snapshot@1",
        "schemaVersion": 1,
        "datasetId": "axiom.intelligence.f4-synthetic-residual-dataset@1",
        "axisIds": list(AXES),
        "allowedSplitIds": ["train", "validation", "test"],
        "selectionPolicyId": "axiom.intelligence.f4-canonical-topology-split@1",
        "labelDerivationId": LABEL_DERIVATION_ID,
        "knownBiases": [
            "All labels are generated by a deterministic synthetic SIL oracle.",
            "Only the X residual head is eligible for validation in this slice.",
        ],
        "coverageGaps": [
            "No real-device paired holdout is included.",
            "Y and Z have no validated improvement; B and C have insufficient excitation.",
        ],
        "governance": {
            "governanceId": "axiom.intelligence.synthetic-governance@1",
            "sourceKind": "synthetic-sil",
            "syntheticLearningContractStatus": "Open",
            "realWorldGeneralizationStatus": "Open",
            "safetyBanner": "SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE",
            "licenseId": "axiom-project-internal-synthetic@1",
            "allowedUses": ["contract-validation", "deterministic-testing"],
            "sensitivity": "synthetic",
            "retentionPolicyId": "axiom.synthetic-fixture-retention@1",
            "redistributionAllowed": False,
        },
        "samples": rows,
    }
    payload["contentHash"] = canonical_hash(payload)
    return DatasetSnapshot.model_validate(payload)


def _split_manifest(dataset: DatasetSnapshot) -> SplitManifest:
    partitions = []
    for split_id in ("train", "validation", "test"):
        samples = tuple(sample for sample in dataset.samples if sample.declared_split_id == split_id)
        partitions.append(
            {
                "splitId": split_id,
                "sampleIds": [sample.sample_id for sample in samples],
                "connectedGroupIds": sorted({sample.connected_group_id for sample in samples}),
                "startTime": min(sample.event_time for sample in samples),
                "endTime": max(sample.event_time for sample in samples),
            }
        )
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.split-manifest",
        "schemaId": "axiom.intelligence.split-manifest@1",
        "schemaVersion": 1,
        "manifestId": "axiom.intelligence.f4-topology-split@1",
        "datasetContentHash": dataset.content_hash,
        "partitions": partitions,
    }
    payload["contentHash"] = canonical_hash(payload)
    return SplitManifest.model_validate(payload)


def _build_positive_scenario() -> R5Scenario:
    rows = [row for source in _SOURCE_LAYOUT for row in _source_rows(*source)]
    _mark_test_ood(rows)
    dataset = _dataset_snapshot(rows)
    split_manifest = _split_manifest(dataset)
    model_bundle, training_receipt, parity_receipt, evaluation = train_r5_bundle(dataset, split_manifest)
    summary = R5ScenarioSummary(
        scenarioId=DEFAULT_SCENARIO_ID,
        title="F4 topology-isolated synthetic residual contract",
        description=(
            "F4 dual-table, head-table and dual-head commands are isolated across train, validation and test; "
            "only the X residual head can pass."
        ),
        expectedOutcome="Passed",
        expectedExecutionStatus="Succeeded",
    )
    run_spec = {
        "subjectId": "axiom.intelligence.x-residual-model@1",
        "domainPackId": R5_DOMAIN_PACK_ID,
        "runnerId": R5_RUNNER_ID,
        "evaluatorVersion": R5_EVALUATOR_ID,
        "request": {
            "artifact": model_bundle.model_dump(mode="json", by_alias=True, exclude_none=True),
            "dataset": dataset.model_dump(mode="json", by_alias=True, exclude_none=True),
            "splitManifest": split_manifest.model_dump(mode="json", by_alias=True, exclude_none=True),
            "trainingReceipt": training_receipt.model_dump(mode="json", by_alias=True, exclude_none=True),
            "parityReceipt": parity_receipt.model_dump(mode="json", by_alias=True, exclude_none=True),
            "case": {
                "caseId": "axiom.intelligence.synthetic-residual-contract.case@1",
                "requiredMetrics": [
                    "intelligence.integrity-valid@1",
                    "intelligence.synthetic-learning-contract@1",
                    {"metricId": "intelligence.x.in-domain-improvement-ratio@1", "threshold": {"operator": ">=", "value": 0.20}},
                    {"metricId": "intelligence.x.conformal-coverage@1", "threshold": {"operator": ">=", "value": 0.80}},
                    {"metricId": "intelligence.x.ood-detection-rate@1", "threshold": {"operator": ">=", "value": 1.0}},
                    {"metricId": "intelligence.x.target-parity-max-abs-gap@1", "threshold": {"operator": "<=", "value": 1e-12}},
                ],
                "optionalMetrics": ["intelligence.real-world-generalization@1"],
            },
        },
    }
    RunSpec.model_validate(run_spec)
    return R5Scenario(
        summary=summary,
        dataset=dataset,
        split_manifest=split_manifest,
        model_bundle=model_bundle,
        training_receipt=training_receipt,
        parity_receipt=parity_receipt,
        evaluation=evaluation,
        run_spec=run_spec,
    )


def _invalid_scenario(
    *,
    scenario_id: str,
    title: str,
    description: str,
    mutate: Callable[[dict[str, Any]], None],
) -> R5Scenario:
    base = _build_positive_scenario()
    run_spec = deepcopy(base.run_spec)
    mutate(run_spec)
    return R5Scenario(
        summary=R5ScenarioSummary(
            scenarioId=scenario_id,
            title=title,
            description=description,
            expectedOutcome="Invalid",
            expectedExecutionStatus="Skipped",
        ),
        dataset=base.dataset,
        split_manifest=base.split_manifest,
        model_bundle=base.model_bundle,
        training_receipt=base.training_receipt,
        parity_receipt=base.parity_receipt,
        evaluation=base.evaluation,
        run_spec=run_spec,
    )


def _build_scenarios() -> dict[str, R5Scenario]:
    positive = _build_positive_scenario()
    return {
        DEFAULT_SCENARIO_ID: positive,
        "group-leak": _invalid_scenario(
            scenario_id="group-leak",
            title="Group leak",
            description="Validation illegally reuses the train trajectory family without rebinding identities.",
            mutate=lambda spec: spec["request"]["dataset"]["samples"][10].__setitem__(
                "trajectoryFamily", "trajectory-dual-table"
            ),
        ),
        "time-order-reversal": _invalid_scenario(
            scenario_id="time-order-reversal",
            title="Time order reversal",
            description="Validation starts before the train time window ends.",
            mutate=lambda spec: spec["request"]["splitManifest"]["partitions"][1].__setitem__(
                "startTime", spec["request"]["splitManifest"]["partitions"][0]["startTime"]
            ),
        ),
        "bundle-tamper": _invalid_scenario(
            scenario_id="bundle-tamper",
            title="Bundle tamper",
            description="A sealed X-head weight is modified.",
            mutate=lambda spec: spec["request"]["artifact"]["xAxisHead"]["weights"].__setitem__(0, 999.0),
        ),
        "parity-tamper": _invalid_scenario(
            scenario_id="parity-tamper",
            title="Parity tamper",
            description="The parity receipt is modified after sealing.",
            mutate=lambda spec: spec["request"]["parityReceipt"].__setitem__("maxAbsGap", 1e-3),
        ),
    }


@lru_cache(maxsize=1)
def _scenarios() -> dict[str, R5Scenario]:
    return _build_scenarios()


def build_r5_manifest() -> dict[str, Any]:
    return R5Manifest(
        manifestId="axiom.intelligence.r5-manifest@1",
        schemaId="axiom.intelligence.r5-manifest@1",
        schemaVersion=1,
        stage="R5-A",
        domainPackId=R5_DOMAIN_PACK_ID,
        platform="windows",
        defaultScenarioId=DEFAULT_SCENARIO_ID,
        safetyBanner="SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE",
        syntheticLearningContractStatus="Passed",
        realWorldGeneralizationStatus="Open",
    ).model_dump(mode="json", by_alias=True, exclude_none=True)


def load_r5_fixture_manifest() -> dict[str, Any]:
    resource = files("axiom.intelligence").joinpath("fixtures", "manifest.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def list_r5_scenarios() -> tuple[R5ScenarioSummary, ...]:
    order = (DEFAULT_SCENARIO_ID, "group-leak", "time-order-reversal", "bundle-tamper", "parity-tamper")
    return tuple(_scenarios()[scenario_id].summary for scenario_id in order)


def load_r5_scenario(scenario_id: str = DEFAULT_SCENARIO_ID) -> R5Scenario:
    try:
        return _scenarios()[scenario_id]
    except KeyError as exc:
        available = ", ".join(item.scenario_id for item in list_r5_scenarios())
        raise KeyError(f"unknown R5 scenario '{scenario_id}'; expected one of: {available}") from exc


def r5_example_payload(scenario_id: str = DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    scenario = load_r5_scenario(scenario_id)
    payload = R5ExamplePayload(
        manifest=R5Manifest.model_validate(build_r5_manifest()),
        scenario=scenario.summary,
        dataset=scenario.dataset,
        splitManifest=scenario.split_manifest,
        modelBundle=scenario.model_bundle,
        evaluation=(scenario.evaluation if scenario.summary.expected_execution_status == "Succeeded" else None),
        runSpec=RunSpec.model_validate(scenario.run_spec),
    )
    return payload.model_dump(mode="json", by_alias=True, exclude_none=True)


def r5_example_run_spec(scenario_id: str = DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    return deepcopy(load_r5_scenario(scenario_id).run_spec)


def validate_r5_example_run_spec(scenario_id: str = DEFAULT_SCENARIO_ID) -> RunSpec:
    return RunSpec.model_validate(r5_example_run_spec(scenario_id))


__all__ = [
    "DEFAULT_SCENARIO_ID",
    "build_r5_manifest",
    "list_r5_scenarios",
    "load_r5_scenario",
    "load_r5_fixture_manifest",
    "r5_example_payload",
    "r5_example_run_spec",
    "validate_r5_example_run_spec",
]
