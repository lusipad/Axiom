from __future__ import annotations

import json

from axiom.five_axis.f1_collision import hash_state_geometry
from axiom.five_axis.f1_models import AxisAlignedBoundingBox
from axiom.five_axis.f1_runtime import (
    GEOMETRY_VALID_CLAIM_ID,
    GEOMETRY_VALID_METRIC_ID,
    TASK_COLLISION_FREE_CLAIM_ID,
    TASK_COLLISION_FREE_METRIC_ID,
)
from axiom.five_axis.f1_scenarios import (
    F1ExamplePayload,
    build_f1_manifest,
    f1_example_payload,
    f1_example_run_spec,
    list_f1_scenarios,
    load_f1_scenario,
)
from axiom.models import ClaimStatus, MetricStatus
from axiom.run import evaluate_run


def _claim_by_definition(bundle, claim_definition_id: str):
    return next(claim for claim in bundle.claims if claim.claim_definition_id == claim_definition_id)


def _snapshot_hash_from_payload(stock_state_geometries: dict[str, dict[str, list[dict[str, list[float]]]]], state_id: str) -> str:
    geometry = {
        stock_fixture_id: tuple(
            AxisAlignedBoundingBox.model_validate(box)
            for box in boxes
        )
        for stock_fixture_id, boxes in stock_state_geometries[state_id].items()
    }
    return hash_state_geometry(geometry)


def test_list_and_load_scenarios_are_stable_and_json_ready():
    summaries = list_f1_scenarios()

    assert [summary.scenarioId for summary in summaries] == [
        "fixture-collision",
        "geometry-tolerance-violation",
        "nominal-certified",
    ]

    nominal = load_f1_scenario("nominal-certified")
    payload_first = f1_example_payload()
    payload_second = f1_example_payload()

    assert payload_first == payload_second
    assert F1ExamplePayload.model_validate(payload_first).model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude_unset=True
    ) == payload_first
    assert json.loads(json.dumps(payload_first, sort_keys=True)) == payload_first
    assert build_f1_manifest().model_dump(mode="json", by_alias=True, exclude_none=True) == payload_first["manifest"]
    assert f1_example_run_spec() == nominal.runSpec

    interval = nominal.candidateGeometry.process_state_timeline.intervals[0]
    assert interval.input_stock_state.content_id == _snapshot_hash_from_payload(nominal.stockStateGeometries, interval.input_stock_state.state_id)
    assert interval.output_stock_state is not None
    assert interval.output_stock_state.content_id == _snapshot_hash_from_payload(nominal.stockStateGeometries, interval.output_stock_state.state_id)


def test_nominal_certified_scenario_supports_exact_geometry_and_certified_collision_claims():
    bundle = evaluate_run(f1_example_run_spec())

    geometry_metric = bundle.metric_result(GEOMETRY_VALID_METRIC_ID)
    collision_metric = bundle.metric_result(TASK_COLLISION_FREE_METRIC_ID)
    geometry_claim = _claim_by_definition(bundle, GEOMETRY_VALID_CLAIM_ID)
    collision_claim = _claim_by_definition(bundle, TASK_COLLISION_FREE_CLAIM_ID)

    assert bundle.run.case_outcome.value == "Passed"
    assert bundle.run.execution_status.value == "Succeeded"
    assert geometry_metric.status is MetricStatus.COMPUTED
    assert geometry_metric.value is True
    assert geometry_metric.evidence is not None and geometry_metric.evidence.level == "Exact"
    assert collision_metric.status is MetricStatus.COMPUTED
    assert collision_metric.value is True
    assert collision_metric.evidence is not None and collision_metric.evidence.level == "Certified"
    assert geometry_claim.status is ClaimStatus.SUPPORTED
    assert geometry_claim.evidence is not None and geometry_claim.evidence.level == "Exact"
    assert collision_claim.status is ClaimStatus.SUPPORTED
    assert collision_claim.evidence is not None and collision_claim.evidence.level == "Certified"


def test_geometry_tolerance_violation_refutes_geometry_claim_through_core_runtime():
    bundle = evaluate_run(f1_example_run_spec("geometry-tolerance-violation"))

    geometry_metric = bundle.metric_result(GEOMETRY_VALID_METRIC_ID)
    collision_metric = bundle.metric_result(TASK_COLLISION_FREE_METRIC_ID)
    geometry_claim = _claim_by_definition(bundle, GEOMETRY_VALID_CLAIM_ID)
    collision_claim = _claim_by_definition(bundle, TASK_COLLISION_FREE_CLAIM_ID)

    assert geometry_metric.status is MetricStatus.COMPUTED
    assert geometry_metric.value is False
    assert geometry_metric.reason_code == "GeometryToleranceExceeded"
    assert geometry_metric.evidence is not None and geometry_metric.evidence.level == "Observed"
    assert collision_metric.status is MetricStatus.COMPUTED
    assert collision_metric.value is True
    assert collision_metric.evidence is not None and collision_metric.evidence.level == "Certified"
    assert geometry_claim.status is ClaimStatus.REFUTED
    assert geometry_claim.evidence is not None and geometry_claim.evidence.level == "Observed"
    assert collision_claim.status is ClaimStatus.SUPPORTED
    assert collision_claim.evidence is not None and collision_claim.evidence.level == "Certified"


def test_fixture_collision_refutes_collision_free_claim_through_core_runtime():
    bundle = evaluate_run(f1_example_run_spec("fixture-collision"))

    geometry_metric = bundle.metric_result(GEOMETRY_VALID_METRIC_ID)
    collision_metric = bundle.metric_result(TASK_COLLISION_FREE_METRIC_ID)
    geometry_claim = _claim_by_definition(bundle, GEOMETRY_VALID_CLAIM_ID)
    collision_claim = _claim_by_definition(bundle, TASK_COLLISION_FREE_CLAIM_ID)

    assert geometry_metric.status is MetricStatus.COMPUTED
    assert geometry_metric.value is True
    assert geometry_metric.evidence is not None and geometry_metric.evidence.level == "Exact"
    assert collision_metric.status is MetricStatus.COMPUTED
    assert collision_metric.value is False
    assert collision_metric.reason_code == "ForbiddenContact"
    assert collision_metric.evidence is not None and collision_metric.evidence.level == "Observed"
    assert geometry_claim.status is ClaimStatus.SUPPORTED
    assert geometry_claim.evidence is not None and geometry_claim.evidence.level == "Exact"
    assert collision_claim.status is ClaimStatus.REFUTED
    assert collision_claim.evidence is not None and collision_claim.evidence.level == "Observed"


def test_rebuilding_same_scenario_preserves_hashes_and_ids():
    first = load_f1_scenario("fixture-collision")
    second = load_f1_scenario("fixture-collision")

    assert first.referencePath.model_dump(mode="json", by_alias=True, exclude_none=True) == second.referencePath.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    assert first.candidateGeometry.model_dump(mode="json", by_alias=True, exclude_none=True) == second.candidateGeometry.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    assert first.stockStateGeometries == second.stockStateGeometries
    assert first.manifest.model_dump(mode="json", by_alias=True, exclude_none=True) == second.manifest.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    assert first.runSpec == second.runSpec
