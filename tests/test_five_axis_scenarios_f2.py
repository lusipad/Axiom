from __future__ import annotations

from axiom.five_axis.f2_collision import evaluate_configuration_path_collision
from axiom.five_axis.f2_scenarios import (
    F2ExamplePayload,
    f2_example_payload,
    list_f2_scenarios,
    load_f2_scenario,
    validate_f2_example_run_spec,
)
from axiom.five_axis.f2_runtime import (
    CONFIGURATION_COLLISION_FREE_CLAIM_ID,
    CONFIGURATION_COLLISION_FREE_METRIC_ID,
    KINEMATICALLY_FEASIBLE_CLAIM_ID,
    KINEMATICALLY_FEASIBLE_METRIC_ID,
)
from axiom.run import evaluate_run


def test_f2_scenario_catalog_freezes_three_topologies_and_interval_counterexample() -> None:
    summaries = list_f2_scenarios()

    assert {item.scenarioId for item in summaries} == {
        "canonical-head-head",
        "canonical-head-table",
        "canonical-table-table",
        "configuration-interior-collision",
    }
    assert {item.topology for item in summaries} == {"dual-head", "head-table", "dual-table"}


def test_f2_scenarios_execute_through_generic_core_runtime() -> None:
    for summary in list_f2_scenarios():
        spec = validate_f2_example_run_spec(summary.scenarioId)
        bundle = evaluate_run(spec)
        metrics = {item.metric_id: item for item in bundle.report.metric_results}
        claims = {item.claim_definition_id: item for item in bundle.claims}
        collision_expected = summary.scenarioId != "configuration-interior-collision"

        assert bundle.run.execution_status == "Succeeded"
        assert metrics[KINEMATICALLY_FEASIBLE_METRIC_ID].value is True
        assert metrics[CONFIGURATION_COLLISION_FREE_METRIC_ID].value is collision_expected
        assert claims[KINEMATICALLY_FEASIBLE_CLAIM_ID].status == "Supported"
        assert claims[CONFIGURATION_COLLISION_FREE_CLAIM_ID].status == (
            "Supported" if collision_expected else "Refuted"
        )


def test_f2_example_payload_is_typed_and_deterministic() -> None:
    first = F2ExamplePayload.model_validate(f2_example_payload("canonical-head-table"))
    second = F2ExamplePayload.model_validate(f2_example_payload("canonical-head-table"))

    assert first == second
    assert first.manifest.stage == "F2"
    assert first.artifacts.axis_path.machine_profile == first.artifacts.machine_profile
    assert first.run_spec.request.artifact == second.run_spec.request.artifact


def test_f2_interval_collision_is_not_reduced_to_endpoint_sampling() -> None:
    scenario = load_f2_scenario("configuration-interior-collision")
    evaluation = evaluate_configuration_path_collision(
        scenario.axisPath,
        collision_model=scenario.collisionModel,
    )

    assert evaluation.query_kind == "path"
    assert evaluation.status == "collision"
    assert evaluation.certificate_kind == "counterexample"
    witness = next(item.witness_sigma for item in evaluation.pair_results if item.status == "collision")
    assert witness is not None
    assert 0.0 < witness < 1.0
