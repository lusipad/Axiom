from __future__ import annotations

import hashlib
import json
import math
import platform
from dataclasses import dataclass
from typing import Any, Callable, Literal, cast

import numpy as np

from .f2_kinematics import forward_kinematics, normalize_numeric_identity
from .f3_models import M4ContinuousTrajectory, NumericTolerance, ToleranceBinding
from .f3_sampling import (
    M5DiscreteCommand,
    M5IntervalRecord,
    M5KinematicLimits,
    M5ProvenanceRef,
    M5Sample,
    POLYNOMIAL_POLICY_ID,
    ReconstructionPolicy,
    sample_continuous_trajectory,
)
from .f3_timing import evaluate_continuous_state
from .f4_models import AdapterDescriptor, AdapterInvocation, AdapterReceipt, CrossValidationResult

_EPSILON = 1e-12
_SUCCESS_WORK_UNITS_BASE = 5
_REFERENCE_ADAPTER_ID = "five-axis.f4.reference-adapter"
_SUT_ADAPTER_ID = "five-axis.f4.sut-adapter"

_CrossValidationStatus = Literal["Supported", "Refuted", "Inconclusive"]
_JointVector = tuple[float, float, float, float, float]
_CertificateCoefficients = tuple[
    _JointVector,
    _JointVector,
    _JointVector,
    _JointVector,
    _JointVector,
    _JointVector,
    _JointVector,
    _JointVector,
]

REFERENCE_ADAPTER_DESCRIPTOR = AdapterDescriptor(
    adapterId=_REFERENCE_ADAPTER_ID,
    version="1.0.0",
    role="reference",
    subjectId="five-axis.reference-solver",
    subjectVersion="1.0.0",
    inputType="five-axis.m4-continuous-trajectory",
    outputType="five-axis.m5-discrete-command",
    transport="in-process",
)

SUT_ADAPTER_DESCRIPTOR = AdapterDescriptor(
    adapterId=_SUT_ADAPTER_ID,
    version="1.0.0",
    role="sut",
    subjectId="five-axis.sut-solver",
    subjectVersion="1.0.0",
    inputType="five-axis.m4-continuous-trajectory",
    outputType="five-axis.m5-discrete-command",
    transport="in-process",
)

FROZEN_CROSS_VALIDATION_TOLERANCES = (
    ToleranceBinding(
        toleranceId="f4.adapter.position-gap",
        target="position",
        tolerance=NumericTolerance(absolute=1e-12, unit="axis-unit"),
    ),
    ToleranceBinding(
        toleranceId="f4.adapter.velocity-gap",
        target="velocity",
        tolerance=NumericTolerance(absolute=1e-12, unit="axis-unit/s"),
    ),
    ToleranceBinding(
        toleranceId="f4.adapter.acceleration-gap",
        target="acceleration",
        tolerance=NumericTolerance(absolute=1e-12, unit="axis-unit/s^2"),
    ),
    ToleranceBinding(
        toleranceId="f4.adapter.jerk-gap",
        target="jerk",
        tolerance=NumericTolerance(absolute=1e-12, unit="axis-unit/s^3"),
    ),
)

FROZEN_COEFFICIENT_GAP_TOLERANCE = 1e-12


@dataclass(frozen=True)
class _AdapterBuildResult:
    command: M5DiscreteCommand
    deterministic_work_units: int


@dataclass(frozen=True)
class _RegisteredAdapter:
    descriptor: AdapterDescriptor
    builder: Callable[[AdapterInvocation, M4ContinuousTrajectory], _AdapterBuildResult]


def _canonical_content_hash(model: Any) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload = normalize_numeric_identity(payload)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_artifact_content_hash(model: Any) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload.pop("contentId", None)
    payload = normalize_numeric_identity(payload)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _numeric_environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
    }


def _deterministic_work_units_for_shape(sample_count: int, interval_count: int) -> int:
    return _SUCCESS_WORK_UNITS_BASE + sample_count * 5 + interval_count * 8


def _unsupported_receipt(
    invocation: AdapterInvocation,
    *,
    actual_input_hash: str,
    deterministic_work_units: int,
    failure_code: str,
    failure_message: str,
) -> AdapterReceipt:
    return AdapterReceipt(
        invocation=invocation,
        descriptor=invocation.descriptor,
        status="Unsupported",
        inputContentHash=actual_input_hash,
        deterministicWorkUnits=deterministic_work_units,
        failureCode=failure_code,
        failureMessage=failure_message,
        numericEnvironment=_numeric_environment(),
    )


def _failed_receipt(
    invocation: AdapterInvocation,
    *,
    actual_input_hash: str,
    deterministic_work_units: int,
    failure_code: str,
    failure_message: str,
) -> AdapterReceipt:
    return AdapterReceipt(
        invocation=invocation,
        descriptor=invocation.descriptor,
        status="Failed",
        inputContentHash=actual_input_hash,
        deterministicWorkUnits=deterministic_work_units,
        failureCode=failure_code,
        failureMessage=failure_message,
        numericEnvironment=_numeric_environment(),
    )


def _succeeded_receipt(
    invocation: AdapterInvocation,
    *,
    actual_input_hash: str,
    command: M5DiscreteCommand,
    deterministic_work_units: int,
) -> AdapterReceipt:
    return AdapterReceipt(
        invocation=invocation,
        descriptor=invocation.descriptor,
        status="Succeeded",
        inputContentHash=actual_input_hash,
        outputContentHash=command.content_id,
        deterministicWorkUnits=deterministic_work_units,
        numericEnvironment=_numeric_environment(),
    )


def list_registered_adapters() -> tuple[AdapterDescriptor, ...]:
    return tuple(item.descriptor for item in _ADAPTER_REGISTRY.values())


def build_adapter_invocation(
    adapter: str | AdapterDescriptor,
    m4: M4ContinuousTrajectory,
    *,
    sample_period: float,
    policy: str | ReconstructionPolicy,
    final_hold: bool,
    invocation_id: str | None = None,
) -> AdapterInvocation:
    descriptor = _resolve_descriptor(adapter)
    resolved_policy = (
        policy
        if isinstance(policy, ReconstructionPolicy)
        else ReconstructionPolicy.model_validate({"policyId": policy})
    )
    source_m4_id = _m4_identity(m4)
    return AdapterInvocation(
        invocationId=invocation_id or f"{descriptor.adapter_id}.{source_m4_id}.invoke",
        descriptor=descriptor,
        inputM4Id=source_m4_id,
        inputM4ContentHash=_canonical_content_hash(m4),
        policyId=resolved_policy.policy_id,
        samplePeriod=sample_period,
        finalHold=final_hold,
    )


def execute_adapter(
    invocation: AdapterInvocation,
    m4: M4ContinuousTrajectory,
) -> tuple[AdapterReceipt, M5DiscreteCommand | None]:
    actual_input_hash = _canonical_content_hash(m4)
    actual_m4_id = _m4_identity(m4)
    registered = _ADAPTER_REGISTRY.get(invocation.descriptor.adapter_id)
    if registered is None:
        return (
            _unsupported_receipt(
                invocation,
                actual_input_hash=actual_input_hash,
                deterministic_work_units=1,
                failure_code="AdapterNotRegistered",
                failure_message="adapterId is not registered for the in-process F4 transport",
            ),
            None,
        )
    if invocation.descriptor != registered.descriptor:
        return (
            _unsupported_receipt(
                invocation,
                actual_input_hash=actual_input_hash,
                deterministic_work_units=1,
                failure_code="AdapterIdentityMismatch",
                failure_message="adapter descriptor role/identity does not match the registered adapter",
            ),
            None,
        )
    if invocation.input_m4_id != actual_m4_id:
        return (
            _failed_receipt(
                invocation,
                actual_input_hash=actual_input_hash,
                deterministic_work_units=1,
                failure_code="InputIdentityMismatch",
                failure_message="inputM4Id does not match the supplied M4 trajectory identity",
            ),
            None,
        )
    if invocation.input_m4_content_hash != actual_input_hash:
        return (
            _failed_receipt(
                invocation,
                actual_input_hash=actual_input_hash,
                deterministic_work_units=1,
                failure_code="InputContentHashMismatch",
                failure_message="inputM4ContentHash does not match the supplied M4 trajectory payload",
            ),
            None,
        )
    if invocation.policy_id != POLYNOMIAL_POLICY_ID:
        return (
            _unsupported_receipt(
                invocation,
                actual_input_hash=actual_input_hash,
                deterministic_work_units=1,
                failure_code="UnsupportedPolicy",
                failure_message="F4 in-process adapters currently support only five-axis.reconstruction.polynomial@1",
            ),
            None,
        )
    try:
        result = registered.builder(invocation, m4)
    except Exception as exc:
        return (
            _failed_receipt(
                invocation,
                actual_input_hash=actual_input_hash,
                deterministic_work_units=2,
                failure_code="AdapterExecutionFailed",
                failure_message=str(exc),
            ),
            None,
        )
    command = result.command
    if command.source_m4_id != actual_m4_id:
        return (
            _failed_receipt(
                invocation,
                actual_input_hash=actual_input_hash,
                deterministic_work_units=result.deterministic_work_units,
                failure_code="OutputIdentityMismatch",
                failure_message="adapter output sourceM4Id does not match the supplied M4 trajectory",
            ),
            None,
        )
    if command.source_m4_content_id != actual_input_hash:
        return (
            _failed_receipt(
                invocation,
                actual_input_hash=actual_input_hash,
                deterministic_work_units=result.deterministic_work_units,
                failure_code="OutputContentHashMismatch",
                failure_message="adapter output sourceM4ContentId does not match the supplied M4 trajectory",
            ),
            None,
        )
    if command.reconstruction_policy.policy_id != POLYNOMIAL_POLICY_ID:
        return (
            _failed_receipt(
                invocation,
                actual_input_hash=actual_input_hash,
                deterministic_work_units=result.deterministic_work_units,
                failure_code="OutputPolicyMismatch",
                failure_message="adapter output reconstructionPolicy must stay polynomial",
            ),
            None,
        )
    return (
        _succeeded_receipt(
            invocation,
            actual_input_hash=actual_input_hash,
            command=command,
            deterministic_work_units=result.deterministic_work_units,
        ),
        command,
    )


def cross_validate_discrete_commands(
    reference: M5DiscreteCommand,
    sut: M5DiscreteCommand,
    *,
    tolerances: tuple[ToleranceBinding, ...] = FROZEN_CROSS_VALIDATION_TOLERANCES,
) -> CrossValidationResult:
    if reference.reconstruction_policy.policy_id != POLYNOMIAL_POLICY_ID:
        return _cross_validation_result(reference, sut, tolerances=tolerances, status="Inconclusive")
    if sut.reconstruction_policy.policy_id != POLYNOMIAL_POLICY_ID:
        return _cross_validation_result(reference, sut, tolerances=tolerances, status="Inconclusive")
    if not _commands_are_shape_compatible(reference, sut):
        return _cross_validation_result(reference, sut, tolerances=tolerances, status="Inconclusive")
    max_position_gap, max_velocity_gap, max_acceleration_gap, max_jerk_gap = _max_state_gaps(reference, sut)
    absolute_limits = {item.target: item.tolerance.absolute for item in tolerances}
    status: _CrossValidationStatus = (
        "Supported"
        if max_position_gap <= absolute_limits["position"] + _EPSILON
        and max_velocity_gap <= absolute_limits["velocity"] + _EPSILON
        and max_acceleration_gap <= absolute_limits["acceleration"] + _EPSILON
        and max_jerk_gap <= absolute_limits["jerk"] + _EPSILON
        else "Refuted"
    )
    return CrossValidationResult(
        referenceContentHash=reference.content_id,
        sutContentHash=sut.content_id,
        status=status,
        maxPositionGap=max_position_gap,
        maxVelocityGap=max_velocity_gap,
        maxAccelerationGap=max_acceleration_gap,
        maxJerkGap=max_jerk_gap,
        tolerances=tolerances,
        evidenceLevel="Validated",
        method="five-axis.f4.adapter-cross-validation.polynomial@1",
    )


def _cross_validation_result(
    reference: M5DiscreteCommand,
    sut: M5DiscreteCommand,
    *,
    tolerances: tuple[ToleranceBinding, ...],
    status: _CrossValidationStatus,
) -> CrossValidationResult:
    return CrossValidationResult(
        referenceContentHash=reference.content_id,
        sutContentHash=sut.content_id,
        status=status,
        maxPositionGap=0.0,
        maxVelocityGap=0.0,
        maxAccelerationGap=0.0,
        maxJerkGap=0.0,
        tolerances=tolerances,
        evidenceLevel="Validated",
        method="five-axis.f4.adapter-cross-validation.polynomial@1",
    )


def _resolve_descriptor(adapter: str | AdapterDescriptor) -> AdapterDescriptor:
    if isinstance(adapter, AdapterDescriptor):
        return adapter
    registered = _ADAPTER_REGISTRY.get(adapter)
    if registered is None:
        raise ValueError(f"unknown adapterId: {adapter}")
    return registered.descriptor


def _build_reference_command(invocation: AdapterInvocation, m4: M4ContinuousTrajectory) -> _AdapterBuildResult:
    command = sample_continuous_trajectory(
        m4,
        sample_period=invocation.sample_period,
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=invocation.final_hold,
        artifact_kind="discrete-command",
    )
    if not isinstance(command, M5DiscreteCommand):
        raise ValueError("reference adapter did not emit a discrete command")
    return _AdapterBuildResult(
        command=command,
        deterministic_work_units=_deterministic_work_units_for_shape(len(command.samples), len(command.intervals)),
    )


def _build_sut_command(invocation: AdapterInvocation, m4: M4ContinuousTrajectory) -> _AdapterBuildResult:
    duration = _m4_duration_seconds(m4)
    times, remainder = _build_sample_schedule(duration, invocation.sample_period)
    source_m4_id = _m4_identity(m4)
    source_m4_content_id = _canonical_content_hash(m4)
    samples: list[M5Sample] = []
    states: list[dict[str, Any]] = []
    for index, t in enumerate(times):
        state = _evaluate_public_m4_state(m4, t)
        states.append(state)
        samples.append(
            M5Sample(
                sampleId=f"{source_m4_id}.sut.sample.{index}",
                sampleIndex=index,
                t=t,
                cycle=int(min(index, math.floor(t / invocation.sample_period + _EPSILON))),
                sigma=state["sigma"],
                q=state["q"],
                qdot=state["qdot"],
                qddot=state["qddot"],
                qjerk=state["qjerk"],
                taskPose=state["task_pose"],
                provenance=(
                    M5ProvenanceRef(
                        sourceStage="M4",
                        sourceId=source_m4_id,
                        sourceContentId=source_m4_content_id,
                        method="sut-evaluate-continuous-state",
                    ),
                ),
            )
        )
    intervals: list[M5IntervalRecord] = []
    for index in range(max(0, len(samples) - 1)):
        start_state = states[index]
        end_state = states[index + 1]
        dt = samples[index + 1].t - samples[index].t
        intervals.append(
            M5IntervalRecord(
                intervalId=f"{source_m4_id}.sut.interval.{index}",
                intervalIndex=index,
                startSampleIndex=index,
                endSampleIndex=index + 1,
                tStart=samples[index].t,
                tEnd=samples[index + 1].t,
                certificateCoefficients=_solve_septic_coefficients(start_state, end_state, dt),
            )
        )
    artifact = M5DiscreteCommand.model_construct(
        schema_id="five-axis.m5-discrete-command@1",
        schema_version=1,
        content_id="0" * 64,
        artifact_type="five-axis.m5-discrete-command",
        discrete_command_id=f"{source_m4_id}.m5-command.sut",
        source_m4=m4,
        source_m4_id=source_m4_id,
        source_m4_content_id=source_m4_content_id,
        sample_period=invocation.sample_period,
        duration=duration,
        remainder_duration=0.0
        if math.isclose(remainder, invocation.sample_period, abs_tol=_EPSILON)
        else remainder,
        terminal_sample_included=True,
        final_hold=invocation.final_hold,
        reconstruction_policy=ReconstructionPolicy.model_validate({"policyId": POLYNOMIAL_POLICY_ID}),
        limits=M5KinematicLimits.model_validate(_limits_from_profile(m4)),
        samples=tuple(samples),
        intervals=tuple(intervals),
        provenance=(
            M5ProvenanceRef(
                sourceStage="M4",
                sourceId=source_m4_id,
                sourceContentId=source_m4_content_id,
                method="sut-fixed-period-sampling",
            ),
        ),
    )
    payload = artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["contentId"] = _canonical_artifact_content_hash(artifact)
    command = M5DiscreteCommand.model_validate(payload)
    return _AdapterBuildResult(
        command=command,
        deterministic_work_units=_deterministic_work_units_for_shape(len(command.samples), len(command.intervals)),
    )


def _commands_are_shape_compatible(reference: M5DiscreteCommand, sut: M5DiscreteCommand) -> bool:
    if len(reference.samples) != len(sut.samples):
        return False
    if len(reference.intervals) != len(sut.intervals):
        return False
    if not math.isclose(reference.sample_period, sut.sample_period, rel_tol=0.0, abs_tol=_EPSILON):
        return False
    for reference_sample, sut_sample in zip(reference.samples, sut.samples, strict=True):
        if not math.isclose(reference_sample.t, sut_sample.t, rel_tol=0.0, abs_tol=_EPSILON):
            return False
    for reference_interval, sut_interval in zip(reference.intervals, sut.intervals, strict=True):
        if not math.isclose(reference_interval.t_start, sut_interval.t_start, rel_tol=0.0, abs_tol=_EPSILON):
            return False
        if not math.isclose(reference_interval.t_end, sut_interval.t_end, rel_tol=0.0, abs_tol=_EPSILON):
            return False
    return True


def _vector_gap(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return max(abs(a - b) for a, b in zip(left, right, strict=True))


def _max_state_gaps(reference: M5DiscreteCommand, sut: M5DiscreteCommand) -> tuple[float, float, float, float]:
    position_gap = 0.0
    velocity_gap = 0.0
    acceleration_gap = 0.0
    jerk_gap = 0.0
    for reference_sample, sut_sample in zip(reference.samples, sut.samples, strict=True):
        position_gap = max(position_gap, _vector_gap(reference_sample.q, sut_sample.q))
        velocity_gap = max(velocity_gap, _vector_gap(reference_sample.qdot, sut_sample.qdot))
        acceleration_gap = max(acceleration_gap, _vector_gap(reference_sample.qddot, sut_sample.qddot))
        jerk_gap = max(jerk_gap, _vector_gap(reference_sample.qjerk, sut_sample.qjerk))
    for reference_interval, sut_interval in zip(reference.intervals, sut.intervals, strict=True):
        for u in (0.25, 0.5, 0.75):
            left_state = _evaluate_interval_state(reference, reference_interval, u)
            right_state = _evaluate_interval_state(sut, sut_interval, u)
            position_gap = max(position_gap, _vector_gap(left_state["q"], right_state["q"]))
            velocity_gap = max(velocity_gap, _vector_gap(left_state["qdot"], right_state["qdot"]))
            acceleration_gap = max(acceleration_gap, _vector_gap(left_state["qddot"], right_state["qddot"]))
            jerk_gap = max(jerk_gap, _vector_gap(left_state["qjerk"], right_state["qjerk"]))
    return position_gap, velocity_gap, acceleration_gap, jerk_gap


def _m4_identity(m4: M4ContinuousTrajectory) -> str:
    return m4.trajectory_id


def _m4_duration_seconds(m4: M4ContinuousTrajectory) -> float:
    return float(m4.verification.total_duration_seconds)


def _build_sample_schedule(duration: float, sample_period: float) -> tuple[list[float], float]:
    if math.isclose(duration, 0.0, abs_tol=_EPSILON):
        return [0.0], 0.0
    count = int(math.floor((duration + _EPSILON) / sample_period))
    times = [round(index * sample_period, 15) for index in range(count + 1) if index * sample_period <= duration + _EPSILON]
    if not math.isclose(times[-1], duration, abs_tol=_EPSILON):
        times.append(float(duration))
    else:
        times[-1] = float(duration)
    remainder = duration - sample_period * int(math.floor(duration / sample_period))
    if math.isclose(remainder, sample_period, abs_tol=_EPSILON):
        remainder = 0.0
    return times, max(0.0, float(remainder))


def _ordered_axes(m4: M4ContinuousTrajectory) -> tuple[Any, ...]:
    return tuple(sorted(m4.source_axis_path.machine_profile.axes, key=lambda axis: axis.axis_order))


def _joint_value_mapping(m4: M4ContinuousTrajectory, q: tuple[float, float, float, float, float]) -> dict[str, float]:
    return {axis.axis_id: q[index] for index, axis in enumerate(_ordered_axes(m4))}


def _evaluate_public_m4_state(m4: M4ContinuousTrajectory, t: float) -> dict[str, Any]:
    state = evaluate_continuous_state(m4, t)
    q = cast(_JointVector, tuple(float(value) for value in state.joint_position))
    pose = forward_kinematics(m4.source_axis_path.machine_profile, _joint_value_mapping(m4, q))
    return {
        "sigma": float(state.sigma),
        "q": q,
        "qdot": tuple(float(value) for value in state.joint_velocity),
        "qddot": tuple(float(value) for value in state.joint_acceleration),
        "qjerk": tuple(float(value) for value in state.joint_jerk),
        "task_pose": {
            "position": pose.position,
            "toolAxis": pose.tool_axis,
        },
    }


def _limits_from_profile(m4: M4ContinuousTrajectory) -> dict[str, Any]:
    constraints_by_axis = {constraint.axis_id: constraint for constraint in m4.motion_constraint_profile.axis_constraints}
    ordered_axes = _ordered_axes(m4)
    velocity_limits: list[float] = []
    acceleration_limits: list[float] = []
    jerk_limits: list[float] = []
    has_complete_jerk_limits = True
    for axis in ordered_axes:
        constraint = constraints_by_axis[axis.axis_id]
        velocity_limits.append(float(constraint.maximum_velocity))
        acceleration_limits.append(float(constraint.maximum_acceleration))
        if constraint.maximum_jerk is None:
            has_complete_jerk_limits = False
        else:
            jerk_limits.append(float(constraint.maximum_jerk))
    return {
        "positionUnits": tuple(axis.limits.unit for axis in ordered_axes),
        "velocityLimits": tuple(velocity_limits),
        "accelerationLimits": tuple(acceleration_limits),
        "jerkLimits": tuple(jerk_limits) if has_complete_jerk_limits else None,
    }


def _boundary_matrix(dt: float) -> np.ndarray:
    return np.array(
        [
            [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 6.0, 0.0, 0.0, 0.0, 0.0],
            [1.0, dt, dt**2, dt**3, dt**4, dt**5, dt**6, dt**7],
            [0.0, 1.0, 2.0 * dt, 3.0 * dt**2, 4.0 * dt**3, 5.0 * dt**4, 6.0 * dt**5, 7.0 * dt**6],
            [0.0, 0.0, 2.0, 6.0 * dt, 12.0 * dt**2, 20.0 * dt**3, 30.0 * dt**4, 42.0 * dt**5],
            [0.0, 0.0, 0.0, 6.0, 24.0 * dt, 60.0 * dt**2, 120.0 * dt**3, 210.0 * dt**4],
        ],
        dtype=np.float64,
    )


def _solve_septic_coefficients(
    start_state: dict[str, Any],
    end_state: dict[str, Any],
    dt: float,
) -> _CertificateCoefficients:
    system = _boundary_matrix(dt)
    solved: list[tuple[float, ...]] = []
    for axis in range(5):
        rhs = np.array(
            [
                start_state["q"][axis],
                start_state["qdot"][axis],
                start_state["qddot"][axis],
                start_state["qjerk"][axis],
                end_state["q"][axis],
                end_state["qdot"][axis],
                end_state["qddot"][axis],
                end_state["qjerk"][axis],
            ],
            dtype=np.float64,
        )
        solved.append(tuple(float(value) for value in np.linalg.solve(system, rhs)))
    rows = tuple(tuple(axis_coefficients[power] for axis_coefficients in solved) for power in range(8))
    return cast(_CertificateCoefficients, rows)


def _evaluate_interval_state(artifact: M5DiscreteCommand, interval: M5IntervalRecord, u: float) -> dict[str, tuple[float, ...]]:
    tau = (interval.t_end - interval.t_start) * u
    return {
        "q": tuple(_evaluate_axis_polynomial(interval, tau, axis, derivative=0) for axis in range(5)),
        "qdot": tuple(_evaluate_axis_polynomial(interval, tau, axis, derivative=1) for axis in range(5)),
        "qddot": tuple(_evaluate_axis_polynomial(interval, tau, axis, derivative=2) for axis in range(5)),
        "qjerk": tuple(_evaluate_axis_polynomial(interval, tau, axis, derivative=3) for axis in range(5)),
    }


def _evaluate_axis_polynomial(interval: M5IntervalRecord, tau: float, axis: int, *, derivative: int) -> float:
    coefficients = np.asarray(interval.certificate_coefficients, dtype=np.float64)[:, axis]
    derived = np.polynomial.polynomial.polyder(coefficients, m=derivative)
    return float(np.polynomial.polynomial.polyval(tau, derived))


_ADAPTER_REGISTRY: dict[str, _RegisteredAdapter] = {
    REFERENCE_ADAPTER_DESCRIPTOR.adapter_id: _RegisteredAdapter(
        descriptor=REFERENCE_ADAPTER_DESCRIPTOR,
        builder=_build_reference_command,
    ),
    SUT_ADAPTER_DESCRIPTOR.adapter_id: _RegisteredAdapter(
        descriptor=SUT_ADAPTER_DESCRIPTOR,
        builder=_build_sut_command,
    ),
}


__all__ = [
    "FROZEN_COEFFICIENT_GAP_TOLERANCE",
    "FROZEN_CROSS_VALIDATION_TOLERANCES",
    "REFERENCE_ADAPTER_DESCRIPTOR",
    "SUT_ADAPTER_DESCRIPTOR",
    "build_adapter_invocation",
    "cross_validate_discrete_commands",
    "execute_adapter",
    "list_registered_adapters",
]
