from __future__ import annotations

import pytest

from axiom.five_axis.f1_scenarios import load_f1_scenario
from axiom.five_axis.f2_collision import evaluate_configuration_q_free
from axiom.five_axis.f2_scenarios import load_f2_scenario
from axiom.five_axis.f4_runtime import (
    F4_EVALUATOR_ID,
    F4_RUNNER_ID,
    FIVE_AXIS_F4_DOMAIN_PACK_ID,
)
from axiom.five_axis.f4_scenarios import (
    F4ExamplePayload,
    build_f4_manifest,
    build_f4_stage_acceptance_report,
    f4_example_payload,
    validate_f4_example_run_spec,
    list_f4_scenarios,
    load_f4_scenario,
)
from axiom.run import evaluate_run


def test_f4_scenario_catalog_freezes_three_topologies_and_two_counterexamples() -> None:
    summaries = list_f4_scenarios()

    assert [item.scenarioId for item in summaries] == [
        "canonical-dual-table-solver",
        "canonical-head-table-solver",
        "canonical-dual-head-solver",
        "adapter-input-hash-mismatch",
        "interval-interior-collision",
    ]
    assert {item.topology for item in summaries if item.countsTowardClosure} == {
        "dual-head",
        "dual-table",
        "head-table",
    }
    assert [item.scenarioId for item in summaries if not item.countsTowardClosure] == [
        "adapter-input-hash-mismatch",
        "interval-interior-collision",
    ]


@pytest.mark.parametrize(
    ("scenario_id", "base_f2_scenario_id", "topology"),
    [
        ("canonical-dual-table-solver", "canonical-table-table", "dual-table"),
        ("canonical-head-table-solver", "canonical-head-table", "head-table"),
        ("canonical-dual-head-solver", "canonical-head-head", "dual-head"),
    ],
)
def test_positive_solver_scenarios_rebuild_from_f1_safety_context_and_pass(
    scenario_id: str,
    base_f2_scenario_id: str,
    topology: str,
) -> None:
    scenario = load_f4_scenario(scenario_id)
    nominal_f1 = load_f1_scenario("nominal-certified")
    canonical_f2 = load_f2_scenario(base_f2_scenario_id)

    assert scenario.summary.topology == topology
    assert canonical_f2.candidateGeometry.collision_context is None
    assert canonical_f2.candidateGeometry.process_state_timeline is None
    assert scenario.candidateGeometry.collision_context == nominal_f1.candidateGeometry.collision_context
    assert scenario.candidateGeometry.process_state_timeline == nominal_f1.candidateGeometry.process_state_timeline
    assert scenario.axisPath.source_candidate_geometry.collision_context == nominal_f1.candidateGeometry.collision_context
    assert (
        scenario.axisPath.source_candidate_geometry.process_state_timeline
        == nominal_f1.candidateGeometry.process_state_timeline
    )
    assert scenario.stockStateGeometries == nominal_f1.stockStateGeometries
    assert scenario.referenceInvocation.descriptor.subject_id != scenario.sutInvocation.descriptor.subject_id
    assert scenario.referenceReceipt.status == "Succeeded"
    assert scenario.sutReceipt.status == "Succeeded"
    assert scenario.referenceCommand is not None
    assert scenario.sutCommand is not None
    assert scenario.crossValidation is not None
    assert scenario.crossValidation.status == "Supported"
    assert scenario.collisionVerification is not None
    assert scenario.collisionVerification.status == "safe"
    assert scenario.collisionVerification.supports_model_collision_aggregation is True
    assert scenario.scenarioResult.outcome == "Passed"
    assert scenario.scenarioResult.sut_mode == "solver"
    assert scenario.scenarioResult.counts_toward_closure is True
    assert scenario.runSpec is not None
    assert scenario.runSpec["domainPackId"] == FIVE_AXIS_F4_DOMAIN_PACK_ID
    assert scenario.runSpec["request"]["artifact"]["contentId"] == scenario.sutCommand.content_id
    assert scenario.runSpec["request"]["referenceArtifact"]["contentId"] == scenario.referenceCommand.content_id
    assert build_f4_manifest(scenario_id) == scenario.manifest


def test_hash_mismatch_counterexample_fails_without_command_and_stays_out_of_closure() -> None:
    scenario = load_f4_scenario("adapter-input-hash-mismatch")

    assert scenario.referenceReceipt.status == "Succeeded"
    assert scenario.referenceCommand is not None
    assert scenario.sutReceipt.status == "Failed"
    assert scenario.sutReceipt.failure_code == "InputContentHashMismatch"
    assert scenario.sutCommand is None
    assert scenario.crossValidation is None
    assert scenario.collisionVerification is None
    assert scenario.scenarioResult.outcome == "Passed"
    assert scenario.scenarioResult.cross_validation_status == "Inconclusive"
    assert scenario.scenarioResult.collision_status == "unsupported"
    assert scenario.scenarioResult.counts_toward_closure is False
    assert scenario.runSpec is None


def test_interval_collision_counterexample_is_safe_at_endpoints_but_collides_inside_interval() -> None:
    scenario = load_f4_scenario("interval-interior-collision")

    assert scenario.referenceReceipt.status == "Succeeded"
    assert scenario.sutReceipt.status == "Succeeded"
    assert scenario.referenceCommand is not None
    assert scenario.sutCommand is not None
    assert scenario.crossValidation is not None
    assert scenario.crossValidation.status == "Supported"
    assert scenario.collisionVerification is not None
    assert scenario.collisionVerification.status == "collision"
    assert scenario.collisionVerification.supports_model_collision_aggregation is False
    assert scenario.scenarioResult.outcome == "Passed"
    assert scenario.scenarioResult.counts_toward_closure is False
    assert scenario.runSpec is None

    collision_interval = next(
        item
        for item in scenario.collisionVerification.interval_evaluations
        if item.status == "collision"
    )
    start_sample = next(sample for sample in scenario.sutCommand.samples if sample.t == collision_interval.t_start)
    end_sample = next(sample for sample in scenario.sutCommand.samples if sample.t == collision_interval.t_end)
    source_axis_path = scenario.sutCommand.source_m4.source_axis_path

    assert evaluate_configuration_q_free(
        source_axis_path,
        collision_model=scenario.collisionModel,
        sigma=start_sample.sigma,
    ).status == "safe"
    assert evaluate_configuration_q_free(
        source_axis_path,
        collision_model=scenario.collisionModel,
        sigma=end_sample.sigma,
    ).status == "safe"


def test_f4_example_payload_is_typed_and_contains_stage_acceptance_report() -> None:
    payload = f4_example_payload("canonical-head-table-solver")
    validated = F4ExamplePayload.model_validate(payload)
    acceptance_report = build_f4_stage_acceptance_report()
    bundle = evaluate_run(validate_f4_example_run_spec("canonical-head-table-solver"))

    assert validated.manifest.stage == "F4"
    assert validated.run_spec is not None
    assert validated.run_spec.domain_pack_id == FIVE_AXIS_F4_DOMAIN_PACK_ID
    assert validated.run_spec.runner_id == F4_RUNNER_ID
    assert validated.run_spec.evaluator_version == F4_EVALUATOR_ID
    assert validated.evidence.reference_receipt.status == "Succeeded"
    assert validated.evidence.sut_receipt.status == "Succeeded"
    assert validated.evidence.cross_validation is not None
    assert validated.evidence.cross_validation.status == "Supported"
    assert validated.evidence.collision_verification is not None
    assert validated.evidence.collision_verification.status == "safe"
    assert payload["acceptanceReport"]["status"] == "Passed"
    assert acceptance_report.status == "Passed"
    assert all(item.covered for item in acceptance_report.topology_coverage)
    assert all(item.covered for item in acceptance_report.counterexample_coverage)
    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Passed"
