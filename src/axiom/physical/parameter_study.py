from __future__ import annotations

from dataclasses import dataclass

from ..five_axis.f3_models import (
    ContinuousTrajectoryVerification,
    M4ContinuousTrajectory,
    MotionConstraintProfile,
)
from ..five_axis.f3_sampling import (
    M5DiscreteCommand,
    M5VerificationResult,
    POLYNOMIAL_POLICY_ID,
    verify_interval_reconstruction,
)
from ..five_axis.f3_timing import (
    plan_jerk_feasible_time_law,
    verify_continuous_trajectory,
)
from ..five_axis.f4_adapters import (
    SUT_ADAPTER_DESCRIPTOR,
    build_adapter_invocation,
    execute_adapter,
)
from ..five_axis.f4_collision import verify_m5_configuration_collision
from ..five_axis.f4_models import AdapterReceipt, M5CollisionVerification
from ..five_axis.f4_scenarios import load_f4_scenario
from .models import PhysicalModelDefinition, PhysicalResponseTrace
from .simulation import simulate_physical_response


@dataclass(frozen=True)
class CanonicalParameterPointEvaluation:
    motion_profile: MotionConstraintProfile
    continuous_trajectory: M4ContinuousTrajectory
    continuous_verification: ContinuousTrajectoryVerification
    adapter_receipt: AdapterReceipt
    command: M5DiscreteCommand
    interval_verification: M5VerificationResult
    collision_verification: M5CollisionVerification
    response: PhysicalResponseTrace
    linear_following_error_max_mm: float


def derate_motion_profile(
    base: MotionConstraintProfile,
    feed_override: float,
    *,
    profile_id: str,
    feed_source: str,
) -> MotionConstraintProfile:
    axis_constraints = tuple(
        constraint.model_copy(
            update={
                "maximum_velocity": constraint.maximum_velocity * feed_override,
                "maximum_acceleration": constraint.maximum_acceleration
                * feed_override**2,
                "maximum_jerk": (
                    constraint.maximum_jerk * feed_override**3
                    if constraint.maximum_jerk is not None
                    else None
                ),
            }
        )
        for constraint in base.axis_constraints
    )
    return base.model_copy(
        update={
            "profile_id": profile_id,
            "axis_constraints": axis_constraints,
            "maximum_path_velocity": (
                base.maximum_path_velocity * feed_override
                if base.maximum_path_velocity is not None
                else None
            ),
            "feed_source": feed_source,
        }
    )


def evaluate_canonical_parameter_point(
    physical_model: PhysicalModelDefinition,
    *,
    feed_override: float,
    sample_period: float,
    profile_id: str,
    feed_source: str,
    trajectory_id: str,
    invocation_id: str,
    response_trace_id: str,
) -> CanonicalParameterPointEvaluation:
    upstream = load_f4_scenario("canonical-head-table-solver")
    profile = derate_motion_profile(
        upstream.motionConstraintProfile,
        feed_override,
        profile_id=profile_id,
        feed_source=feed_source,
    )
    continuous = plan_jerk_feasible_time_law(
        upstream.axisPath,
        profile,
        trajectory_id=trajectory_id,
    )
    continuous_verification = verify_continuous_trajectory(continuous)
    invocation = build_adapter_invocation(
        SUT_ADAPTER_DESCRIPTOR,
        continuous,
        sample_period=sample_period,
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=False,
        invocation_id=invocation_id,
    )
    receipt, command = execute_adapter(invocation, continuous)
    if receipt.status != "Succeeded" or command is None:
        raise ValueError(f"parameter study adapter failed: {receipt.failure_code}")
    interval_verification = verify_interval_reconstruction(command)
    collision_verification = verify_m5_configuration_collision(
        command,
        collision_model=upstream.collisionModel,
    )
    response = simulate_physical_response(
        physical_model,
        command,
        response_trace_id=response_trace_id,
    )
    linear_error = max(
        abs(float(sample.command[axis]) - float(sample.simulated[axis]))
        for sample in response.samples
        for axis in range(3)
    )
    return CanonicalParameterPointEvaluation(
        motion_profile=profile,
        continuous_trajectory=continuous,
        continuous_verification=continuous_verification,
        adapter_receipt=receipt,
        command=command,
        interval_verification=interval_verification,
        collision_verification=collision_verification,
        response=response,
        linear_following_error_max_mm=linear_error,
    )


__all__ = [
    "CanonicalParameterPointEvaluation",
    "derate_motion_profile",
    "evaluate_canonical_parameter_point",
]
