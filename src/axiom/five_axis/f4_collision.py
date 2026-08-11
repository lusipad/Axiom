from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from .f2_collision import (
    ConfigurationCollisionModel,
    PolynomialCollisionIntervalEvaluation,
    evaluate_configuration_polynomial_interval_collision,
    hash_configuration_collision_model,
)
from .f3_sampling import M5DiscreteCommand, POLYNOMIAL_POLICY_ID
from .f4_models import M5CollisionIntervalResult, M5CollisionVerification


_METHOD_ID = "five-axis.f4.m5-polynomial-collision-envelope@1"


def _normalized_coefficients(
    coefficients: Sequence[Sequence[float]],
    duration: float,
) -> tuple[tuple[float, ...], ...]:
    return tuple(
        tuple(float(value) * duration**power for value in row)
        for power, row in enumerate(coefficients)
    )


def _interval_result(
    evaluation: PolynomialCollisionIntervalEvaluation,
) -> M5CollisionIntervalResult:
    status: Literal["safe", "collision", "unsupported", "unresolved"]
    status = "unsupported" if evaluation.status == "not-applicable" else evaluation.status
    witnesses = tuple(
        pair.witness_parameter
        for pair in evaluation.pair_results
        if pair.witness_parameter is not None
    )
    reason_code = None if status == "safe" else evaluation.reason_code
    return M5CollisionIntervalResult(
        intervalId=evaluation.interval_id,
        tStart=evaluation.parameter_start,
        tEnd=evaluation.parameter_end,
        status=status,
        witnessTime=min(witnesses) if witnesses else None,
        minimumClearanceLowerBound=evaluation.minimum_clearance_lower_bound,
        reasonCode=reason_code,
    )


def verify_m5_configuration_collision(
    command: M5DiscreteCommand,
    *,
    collision_model: ConfigurationCollisionModel,
) -> M5CollisionVerification:
    if not command.intervals:
        raise ValueError("F4 collision verification requires at least one M5 reconstruction interval")
    axis_path = command.source_m4.source_axis_path
    branch_id = axis_path.kinematics_certificate.selected_branch_id
    interval_results: list[M5CollisionIntervalResult] = []
    if command.reconstruction_policy.policy_id != POLYNOMIAL_POLICY_ID:
        interval_results.extend(
            M5CollisionIntervalResult(
                intervalId=interval.interval_id,
                tStart=interval.t_start,
                tEnd=interval.t_end,
                status="unsupported",
                reasonCode="ReconstructionPolicyUnsupportedForCertifiedCollision",
            )
            for interval in command.intervals
        )
    else:
        for interval in command.intervals:
            duration = interval.t_end - interval.t_start
            evaluation = evaluate_configuration_polynomial_interval_collision(
                axis_path,
                collision_model=collision_model,
                interval_id=interval.interval_id,
                parameter_start=interval.t_start,
                parameter_end=interval.t_end,
                parameter_name="time",
                branch_id=branch_id,
                coefficients=_normalized_coefficients(
                    interval.certificate_coefficients,
                    duration,
                ),
            )
            interval_results.append(_interval_result(evaluation))
    statuses = {item.status for item in interval_results}
    status: Literal["safe", "collision", "unsupported", "unresolved"]
    evidence_level: Literal["Certified", "Validated", "Observed"]
    if "collision" in statuses:
        status = "collision"
        evidence_level = "Observed"
    elif "unresolved" in statuses:
        status = "unresolved"
        evidence_level = "Validated"
    elif "unsupported" in statuses:
        status = "unsupported"
        evidence_level = "Validated"
    else:
        status = "safe"
        evidence_level = "Certified"
    return M5CollisionVerification(
        commandId=command.discrete_command_id,
        commandContentHash=command.content_id,
        sourceM3Id=axis_path.axis_path_id,
        sourceM3ContentHash=command.source_m4.source_axis_path_content_id,
        collisionModelId=collision_model.model_id,
        collisionModelContentHash=hash_configuration_collision_model(collision_model),
        reconstructionPolicyId=command.reconstruction_policy.policy_id,
        status=status,
        coverageStatus=collision_model.coverage_status,
        supportsModelCollisionAggregation=(
            status == "safe" and collision_model.coverage_status == "complete"
        ),
        evidenceLevel=evidence_level,
        method=_METHOD_ID,
        intervalEvaluations=tuple(interval_results),
    )


__all__ = ["verify_m5_configuration_collision"]
