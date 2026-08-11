from __future__ import annotations

from axiom.five_axis.f2_collision import evaluate_configuration_q_free
from axiom.five_axis.f2_scenarios import load_f2_scenario
from axiom.five_axis.f3_sampling import (
    FOH_POLICY_ID,
    POLYNOMIAL_POLICY_ID,
    M5DiscreteCommand,
    sample_continuous_trajectory,
)
from axiom.five_axis.f3_scenarios import load_f3_scenario
from axiom.five_axis.f4_collision import verify_m5_configuration_collision


def _command(*, policy_id: str = POLYNOMIAL_POLICY_ID) -> M5DiscreteCommand:
    continuous = load_f3_scenario("canonical-table-table-jerk").continuousTrajectory
    command = sample_continuous_trajectory(
        continuous,
        sample_period=0.25,
        policy=policy_id,
        final_hold=False,
        artifact_kind="discrete-command",
    )
    assert isinstance(command, M5DiscreteCommand)
    return command


def test_polynomial_command_receives_complete_m5_collision_certificate() -> None:
    result = verify_m5_configuration_collision(
        _command(),
        collision_model=load_f2_scenario("canonical-table-table").collisionModel,
    )

    assert result.status == "safe"
    assert result.coverage_status == "complete"
    assert result.supports_model_collision_aggregation is True
    assert result.evidence_level == "Certified"
    assert result.interval_evaluations
    assert all(item.status == "safe" for item in result.interval_evaluations)


def test_polynomial_command_refutes_collision_inside_reconstruction_interval() -> None:
    command = _command()
    collision_model = load_f2_scenario("configuration-interior-collision").collisionModel
    result = verify_m5_configuration_collision(
        command,
        collision_model=collision_model,
    )

    witnesses = tuple(
        item.witness_time
        for item in result.interval_evaluations
        if item.witness_time is not None
    )
    assert result.status == "collision"
    assert result.supports_model_collision_aggregation is False
    assert result.evidence_level == "Observed"
    assert witnesses
    collision_interval = next(item for item in result.interval_evaluations if item.status == "collision")
    source_axis_path = command.source_m4.source_axis_path
    start_sample = next(sample for sample in command.samples if sample.t == collision_interval.t_start)
    end_sample = next(sample for sample in command.samples if sample.t == collision_interval.t_end)
    assert evaluate_configuration_q_free(
        source_axis_path,
        collision_model=collision_model,
        sigma=start_sample.sigma,
    ).status == "safe"
    assert evaluate_configuration_q_free(
        source_axis_path,
        collision_model=collision_model,
        sigma=end_sample.sigma,
    ).status == "safe"


def test_non_polynomial_command_cannot_publish_m5_collision_support() -> None:
    result = verify_m5_configuration_collision(
        _command(policy_id=FOH_POLICY_ID),
        collision_model=load_f2_scenario("canonical-table-table").collisionModel,
    )

    assert result.status == "unsupported"
    assert result.supports_model_collision_aggregation is False
    assert all(
        item.reason_code == "ReconstructionPolicyUnsupportedForCertifiedCollision"
        for item in result.interval_evaluations
    )
