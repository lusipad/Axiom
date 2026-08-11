from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Literal, Mapping

import numpy as np
from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel
from .f2_kinematics import forward_kinematics, normalize_numeric_identity
from .f3_models import M4ContinuousTrajectory

try:
    from .f3_timing import (
        evaluate_continuous_state as _F3_TIMING_EVALUATOR,
        verify_continuous_trajectory as _F3_TIMING_VERIFIER,
    )
except ImportError:  # pragma: no cover - timing lane may land after sampling lane
    _F3_TIMING_EVALUATOR = None
    _F3_TIMING_VERIFIER = None

_EPSILON = 1e-12
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_CONTENT_HASH_PATTERN = r"^[0-9a-f]{64}$"
_POLICY_ID_PATTERN = r"^five-axis\.reconstruction\.[a-z0-9-]+@[1-9][0-9]*$"

REFERENCE_M4_POLICY_ID = "five-axis.reconstruction.reference-m4@1"
POLYNOMIAL_POLICY_ID = "five-axis.reconstruction.polynomial@1"
FOH_POLICY_ID = "five-axis.reconstruction.foh@1"
ZOH_POLICY_ID = "five-axis.reconstruction.zoh@1"
_POLICY_ID_ALIASES = {
    "reference-m4": REFERENCE_M4_POLICY_ID,
    "polynomial": POLYNOMIAL_POLICY_ID,
    "foh": FOH_POLICY_ID,
    "zoh": ZOH_POLICY_ID,
}
ArtifactKind = Literal["auto", "sampled-trajectory", "discrete-command"]
_POLICY_DECLARED_CAPABILITIES = {
    REFERENCE_M4_POLICY_ID: ("position", "velocity", "acceleration", "jerk"),
    POLYNOMIAL_POLICY_ID: ("position", "velocity", "acceleration", "jerk"),
    FOH_POLICY_ID: ("position", "velocity"),
    ZOH_POLICY_ID: ("position",),
}


def _require_finite_json_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("value must be a finite JSON number")
    return value


def _require_finite_vector(value: Any, *, expected: int, field_name: str) -> Any:
    if isinstance(value, (list, tuple)):
        if len(value) != expected:
            raise ValueError(f"{field_name} must contain exactly {expected} numbers")
        for item in value:
            _require_finite_json_number(item)
    return value


def _canonical_content_id(model: Any, *, exclude: set[str] | None = None) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True, exclude=exclude or set())
    payload.pop("contentId", None)
    payload = normalize_numeric_identity(payload)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _coerce_policy_id(value: str) -> str:
    resolved = _POLICY_ID_ALIASES.get(value, value)
    if re.fullmatch(_POLICY_ID_PATTERN, resolved) is None:
        raise ValueError("policyId must be a versioned five-axis reconstruction policy")
    if resolved not in _POLICY_DECLARED_CAPABILITIES:
        raise ValueError("policyId must be one of reference-m4, polynomial, foh, zoh")
    return resolved


def _resolve_artifact_kind(policy_id: str, artifact_kind: ArtifactKind) -> Literal["sampled-trajectory", "discrete-command"]:
    if artifact_kind == "auto":
        if policy_id in {REFERENCE_M4_POLICY_ID, POLYNOMIAL_POLICY_ID}:
            return "sampled-trajectory"
        return "discrete-command"
    if artifact_kind in {"sampled-trajectory", "discrete-command"}:
        return artifact_kind
    raise ValueError("artifact_kind must be one of auto, sampled-trajectory, discrete-command")


def _lookup(source: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(source, Mapping) and name in source:
            return source[name]
        if hasattr(source, name):
            return getattr(source, name)
    return default


def _require_lookup(source: Any, *names: str) -> Any:
    resolved = _lookup(source, *names, default=None)
    if resolved is None:
        joined = "/".join(names)
        raise ValueError(f"missing required field: {joined}")
    return resolved


def _tuple5(value: Any, *, field_name: str) -> tuple[float, float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 5:
        raise ValueError(f"{field_name} must contain exactly 5 numbers")
    return tuple(float(_require_finite_json_number(item)) for item in value)


def _tuple3(value: Any, *, field_name: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{field_name} must contain exactly 3 numbers")
    return tuple(float(_require_finite_json_number(item)) for item in value)


def _normalize_tool_axis(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = math.sqrt(sum(component * component for component in vector))
    if math.isclose(norm, 0.0, abs_tol=_EPSILON):
        raise ValueError("toolAxis must not be the zero vector")
    return tuple(component / norm for component in vector)


class ReconstructionPolicy(AxiomModel):
    policy_id: Literal[
        "five-axis.reconstruction.reference-m4@1",
        "five-axis.reconstruction.polynomial@1",
        "five-axis.reconstruction.foh@1",
        "five-axis.reconstruction.zoh@1",
    ] = Field(alias="policyId")

    @field_validator("policy_id", mode="before")
    @classmethod
    def normalize_policy_id(cls, value: Any) -> Any:
        if not isinstance(value, str):
            raise ValueError("policyId must be a string")
        return _coerce_policy_id(value)


class M5ProvenanceRef(AxiomModel):
    source_stage: str = Field(alias="sourceStage", min_length=1)
    source_id: str = Field(alias="sourceId", min_length=1, pattern=_ID_PATTERN)
    source_content_id: str | None = Field(default=None, alias="sourceContentId", pattern=_CONTENT_HASH_PATTERN)
    method: str | None = None


class M5TaskPose(AxiomModel):
    position: tuple[float, float, float]
    tool_axis: tuple[float, float, float] = Field(alias="toolAxis")

    @field_validator("position", mode="before")
    @classmethod
    def reject_invalid_position(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="position")

    @field_validator("tool_axis", mode="before")
    @classmethod
    def reject_invalid_tool_axis(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="toolAxis")

    @model_validator(mode="after")
    def require_nonzero_tool_axis(self) -> "M5TaskPose":
        self.tool_axis = _normalize_tool_axis(self.tool_axis)
        return self


class M5Sample(AxiomModel):
    sample_id: str = Field(alias="sampleId", min_length=1, pattern=_ID_PATTERN)
    sample_index: int = Field(alias="sampleIndex", ge=0)
    t: float
    cycle: int = Field(ge=0)
    sigma: float
    q: tuple[float, float, float, float, float]
    qdot: tuple[float, float, float, float, float]
    qddot: tuple[float, float, float, float, float]
    qjerk: tuple[float, float, float, float, float]
    task_pose: M5TaskPose = Field(alias="taskPose")
    provenance: tuple[M5ProvenanceRef, ...] = Field(default_factory=tuple)

    @field_validator("t", "sigma", mode="before")
    @classmethod
    def reject_invalid_scalars(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @field_validator("q", "qdot", "qddot", "qjerk", mode="before")
    @classmethod
    def reject_invalid_joint_vectors(cls, value: Any, info: Any) -> Any:
        return _require_finite_vector(value, expected=5, field_name=info.field_name)


class M5IntervalRecord(AxiomModel):
    interval_id: str = Field(alias="intervalId", min_length=1, pattern=_ID_PATTERN)
    interval_index: int = Field(alias="intervalIndex", ge=0)
    start_sample_index: int = Field(alias="startSampleIndex", ge=0)
    end_sample_index: int = Field(alias="endSampleIndex", ge=0)
    t_start: float = Field(alias="tStart")
    t_end: float = Field(alias="tEnd")
    interval_semantics: Literal["[t_k,t_k+1)"] = Field(default="[t_k,t_k+1)", alias="intervalSemantics")
    certificate_coefficients: tuple[
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
        tuple[float, float, float, float, float],
    ] = Field(alias="certificateCoefficients")

    @field_validator("t_start", "t_end", mode="before")
    @classmethod
    def reject_invalid_bounds(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @field_validator("certificate_coefficients", mode="before")
    @classmethod
    def reject_invalid_coefficients(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            if len(value) != 8:
                raise ValueError("certificateCoefficients must contain exactly 8 coefficient rows")
            for row in value:
                _require_finite_vector(row, expected=5, field_name="certificateCoefficients")
        return value

    @model_validator(mode="after")
    def require_forward_interval(self) -> "M5IntervalRecord":
        if self.end_sample_index <= self.start_sample_index:
            raise ValueError("endSampleIndex must be greater than startSampleIndex")
        if self.t_end <= self.t_start:
            raise ValueError("tEnd must be greater than tStart")
        return self


class M5KinematicLimits(AxiomModel):
    position_units: tuple[str, str, str, str, str] = Field(alias="positionUnits")
    velocity_limits: tuple[float, float, float, float, float] | None = Field(default=None, alias="velocityLimits")
    acceleration_limits: tuple[float, float, float, float, float] | None = Field(
        default=None, alias="accelerationLimits"
    )
    jerk_limits: tuple[float, float, float, float, float] | None = Field(default=None, alias="jerkLimits")

    @field_validator("position_units", mode="before")
    @classmethod
    def reject_invalid_units(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            if len(value) != 5:
                raise ValueError("positionUnits must contain exactly 5 units")
            if any(not isinstance(item, str) or not item for item in value):
                raise ValueError("positionUnits must not contain empty units")
        return value

    @field_validator("velocity_limits", "acceleration_limits", "jerk_limits", mode="before")
    @classmethod
    def reject_invalid_limit_vectors(cls, value: Any) -> Any:
        if value is None:
            return None
        return _require_finite_vector(value, expected=5, field_name="limits")


class M5ErrorLedgerEntry(AxiomModel):
    quantity: Literal[
        "sigma",
        "joint-position",
        "joint-velocity",
        "joint-acceleration",
        "joint-jerk",
        "position",
        "orientation",
    ]
    axis: int | None = Field(default=None, ge=0, le=4)
    unit: str = Field(min_length=1)
    source: str = Field(min_length=1)
    bound: float = Field(ge=0.0)
    method: str = Field(min_length=1)

    @field_validator("bound", mode="before")
    @classmethod
    def reject_invalid_bound(cls, value: Any) -> Any:
        return _require_finite_json_number(value)


class M5AxisVerification(AxiomModel):
    axis: int = Field(ge=0, le=4)
    unit: str = Field(min_length=1)
    status: Literal["Supported", "Refuted", "Unsupported"]
    observed_peak: float | None = Field(default=None, alias="observedPeak")
    limit: float | None = None
    interval_id: str | None = Field(default=None, alias="intervalId", pattern=_ID_PATTERN)
    reason_code: str | None = Field(default=None, alias="reasonCode")

    @field_validator("observed_peak", "limit", mode="before")
    @classmethod
    def reject_invalid_measurements(cls, value: Any) -> Any:
        if value is None:
            return None
        return _require_finite_json_number(value)


class M5QuantityVerification(AxiomModel):
    quantity: Literal["position", "velocity", "acceleration", "jerk", "interval-certified"]
    status: Literal["Supported", "Refuted", "Unsupported"]
    axis_results: tuple[M5AxisVerification, ...] = Field(default_factory=tuple, alias="axisResults")
    reason_code: str | None = Field(default=None, alias="reasonCode")


class M5VerificationResult(AxiomModel):
    status: Literal["Supported", "Refuted", "Unsupported"]
    evidence_level: Literal["Certified", "Validated", "Observed"] = Field(alias="evidenceLevel")
    method: str = Field(min_length=1)
    policy_id: str = Field(alias="policyId", pattern=_POLICY_ID_PATTERN)
    artifact_type: str = Field(alias="artifactType", min_length=1)
    artifact_id: str = Field(alias="artifactId", min_length=1, pattern=_ID_PATTERN)
    source_m4_content_id: str = Field(alias="sourceM4ContentId", pattern=_CONTENT_HASH_PATTERN)
    quantities: tuple[M5QuantityVerification, ...]
    error_ledger: tuple[M5ErrorLedgerEntry, ...] = Field(default_factory=tuple, alias="errorLedger")


class _M5ArtifactBase(AxiomModel):
    schema_id: Literal["five-axis.m5-sampled-trajectory@1", "five-axis.m5-discrete-command@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    content_id: str = Field(alias="contentId", pattern=_CONTENT_HASH_PATTERN)
    source_m4: M4ContinuousTrajectory = Field(alias="sourceM4")
    source_m4_id: str = Field(alias="sourceM4Id", min_length=1, pattern=_ID_PATTERN)
    source_m4_content_id: str = Field(alias="sourceM4ContentId", pattern=_CONTENT_HASH_PATTERN)
    sample_period: float = Field(alias="samplePeriod", gt=0.0)
    duration: float = Field(ge=0.0)
    remainder_duration: float = Field(alias="remainderDuration", ge=0.0)
    terminal_sample_included: Literal[True] = Field(default=True, alias="terminalSampleIncluded")
    final_hold: bool = Field(alias="finalHold")
    reconstruction_policy: ReconstructionPolicy = Field(alias="reconstructionPolicy")
    limits: M5KinematicLimits = Field(alias="limits")
    samples: tuple[M5Sample, ...] = Field(min_length=1)
    intervals: tuple[M5IntervalRecord, ...] = Field(default_factory=tuple)
    provenance: tuple[M5ProvenanceRef, ...] = Field(default_factory=tuple)

    @field_validator("sample_period", "duration", "remainder_duration", mode="before")
    @classmethod
    def reject_invalid_timing(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_interval_consistency(self) -> "_M5ArtifactBase":
        if len(self.samples) != len(self.intervals) + (0 if math.isclose(self.duration, 0.0, abs_tol=_EPSILON) else 1):
            if not (len(self.samples) == 1 and len(self.intervals) == 0 and math.isclose(self.duration, 0.0, abs_tol=_EPSILON)):
                raise ValueError("samples must contain exactly one more endpoint than intervals")
        for index, interval in enumerate(self.intervals):
            if interval.interval_index != index:
                raise ValueError("intervalIndex must be contiguous from zero")
            if interval.start_sample_index != index or interval.end_sample_index != index + 1:
                raise ValueError("interval sample indexes must follow adjacent samples")
            start_sample = self.samples[index]
            end_sample = self.samples[index + 1]
            if not math.isclose(interval.t_start, start_sample.t, abs_tol=_EPSILON):
                raise ValueError("interval tStart must match the adjacent sample time")
            if not math.isclose(interval.t_end, end_sample.t, abs_tol=_EPSILON):
                raise ValueError("interval tEnd must match the adjacent sample time")
        if self.source_m4_content_id != _canonical_content_id(self.source_m4):
            raise ValueError("sourceM4ContentId must equal the canonical content hash of sourceM4")
        if self.content_id != _canonical_content_id(self):
            raise ValueError("contentId must equal the canonical content hash of the artifact payload")
        return self

    def artifact_id_value(self) -> str:
        return str(_require_lookup(self, "sampled_trajectory_id", "discrete_command_id"))


class M5SampledTrajectory(_M5ArtifactBase):
    artifact_type: Literal["five-axis.m5-sampled-trajectory"] = Field(alias="artifactType")
    sampled_trajectory_id: str = Field(alias="sampledTrajectoryId", min_length=1, pattern=_ID_PATTERN)


class M5DiscreteCommand(_M5ArtifactBase):
    artifact_type: Literal["five-axis.m5-discrete-command"] = Field(alias="artifactType")
    discrete_command_id: str = Field(alias="discreteCommandId", min_length=1, pattern=_ID_PATTERN)


def _duration_of(m4: M4ContinuousTrajectory | Any) -> float:
    duration = _lookup(m4, "duration", "duration_seconds", "total_duration")
    if duration is None:
        verification = _lookup(m4, "verification")
        duration = _lookup(verification, "total_duration_seconds", "totalDurationSeconds")
    if duration is None:
        spans = _lookup(m4, "spans", default=())
        if isinstance(spans, (list, tuple)) and spans:
            duration = _lookup(spans[-1], "end_time_seconds", "endTimeSeconds")
    if duration is None:
        raise ValueError("M4 trajectory must expose duration")
    return float(_require_finite_json_number(duration))


def _source_m4_id(m4: Any) -> str:
    resolved = _lookup(m4, "trajectory_id", "timed_trajectory_id", "m4_id", "trajectoryId", "timedTrajectoryId")
    if isinstance(resolved, str) and resolved:
        return resolved
    return "m4.trajectory"


def _source_m4_content_id(m4: Any) -> str:
    declared = _lookup(m4, "content_id", "contentId")
    if isinstance(declared, str) and re.fullmatch(_CONTENT_HASH_PATTERN, declared) is not None:
        return declared
    if hasattr(m4, "model_dump"):
        return _canonical_content_id(m4)
    raise ValueError("M4 trajectory must expose contentId or model_dump()")


def _axis_units(m4: M4ContinuousTrajectory | Any) -> tuple[str, str, str, str, str]:
    units = _lookup(m4, "axis_units", "axisUnits")
    if isinstance(units, (list, tuple)) and len(units) == 5 and all(isinstance(item, str) and item for item in units):
        return tuple(units)  # type: ignore[return-value]
    constraint_profile = _lookup(m4, "motion_constraint_profile", "motionConstraintProfile")
    axis_constraints = _lookup(constraint_profile, "axis_constraints", "axisConstraints", default=())
    machine_profile = _machine_profile_for(m4)
    if isinstance(axis_constraints, (list, tuple)) and len(axis_constraints) == 5 and machine_profile is not None:
        ordered_axes = sorted(_lookup(machine_profile, "axes"), key=lambda axis: int(_lookup(axis, "axis_order", "axisOrder", default=0)))
        constraints_by_axis = {_lookup(item, "axis_id", "axisId"): item for item in axis_constraints}
        constraint_units: list[str] = []
        for axis in ordered_axes:
            axis_id = _lookup(axis, "axis_id", "axisId")
            constraint = constraints_by_axis.get(axis_id)
            unit = _lookup(constraint, "unit")
            if not isinstance(unit, str) or not unit:
                break
            constraint_units.append(unit)
        if len(constraint_units) == 5:
            return tuple(constraint_units)  # type: ignore[return-value]
    profile = _lookup(m4, "machine_profile", "machineProfile")
    axes = _lookup(profile, "axes", default=None)
    if isinstance(axes, (list, tuple)) and len(axes) == 5:
        resolved: list[str] = []
        for axis in axes:
            limits = _lookup(axis, "limits")
            unit = _lookup(limits, "unit")
            if not isinstance(unit, str) or not unit:
                break
            resolved.append(unit)
        if len(resolved) == 5:
            return tuple(resolved)  # type: ignore[return-value]
    return ("mm", "mm", "mm", "rad", "rad")


def _limit_vector(m4: Any, *names: str) -> tuple[float, float, float, float, float] | None:
    resolved = _lookup(m4, *names)
    if resolved is None:
        return None
    return _tuple5(resolved, field_name=names[0])


def _constraint_limit_vector(m4: M4ContinuousTrajectory | Any, *names: str) -> tuple[float, float, float, float, float] | None:
    constraint_profile = _lookup(m4, "motion_constraint_profile", "motionConstraintProfile")
    axis_constraints = _lookup(constraint_profile, "axis_constraints", "axisConstraints", default=())
    machine_profile = _machine_profile_for(m4)
    if not isinstance(axis_constraints, (list, tuple)) or len(axis_constraints) != 5 or machine_profile is None:
        return None
    ordered_axes = sorted(_lookup(machine_profile, "axes"), key=lambda axis: int(_lookup(axis, "axis_order", "axisOrder", default=0)))
    constraints_by_axis = {_lookup(item, "axis_id", "axisId"): item for item in axis_constraints}
    values: list[float] = []
    for axis in ordered_axes:
        axis_id = _lookup(axis, "axis_id", "axisId")
        constraint = constraints_by_axis.get(axis_id)
        value = _lookup(constraint, *names)
        if value is None:
            return None
        values.append(float(_require_finite_json_number(value)))
    return tuple(values)  # type: ignore[return-value]


def _limits_for(m4: M4ContinuousTrajectory | Any) -> M5KinematicLimits:
    return M5KinematicLimits(
        positionUnits=_axis_units(m4),
        velocityLimits=_limit_vector(m4, "axis_velocity_limits", "velocity_limits", "axisVelocityLimits")
        or _constraint_limit_vector(m4, "maximum_velocity", "maximumVelocity"),
        accelerationLimits=_limit_vector(m4, "axis_acceleration_limits", "acceleration_limits", "axisAccelerationLimits")
        or _constraint_limit_vector(m4, "maximum_acceleration", "maximumAcceleration"),
        jerkLimits=_limit_vector(m4, "axis_jerk_limits", "jerk_limits", "axisJerkLimits")
        or _constraint_limit_vector(m4, "maximum_jerk", "maximumJerk"),
    )


def _machine_profile_for(m4: M4ContinuousTrajectory | Any) -> Any | None:
    for candidate in (
        _lookup(m4, "machine_profile", "machineProfile"),
        _lookup(_lookup(m4, "source_axis_path", "sourceAxisPath"), "machine_profile", "machineProfile"),
    ):
        if candidate is not None:
            return candidate
    return None


def _joint_value_mapping(machine_profile: Any, q: tuple[float, float, float, float, float]) -> dict[str, float]:
    axes = _lookup(machine_profile, "axes")
    if not isinstance(axes, (list, tuple)) or len(axes) != 5:
        raise ValueError("machine_profile.axes must contain exactly 5 axes")
    ordered_axes = sorted(axes, key=lambda axis: int(_lookup(axis, "axis_order", "axisOrder", default=0)))
    result: dict[str, float] = {}
    for index, axis in enumerate(ordered_axes):
        axis_id = _lookup(axis, "axis_id", "axisId")
        if not isinstance(axis_id, str) or not axis_id:
            raise ValueError("machine_profile axes must expose axisId")
        result[axis_id] = q[index]
    return result


def _task_pose_for(m4: M4ContinuousTrajectory | Any, q: tuple[float, float, float, float, float], raw_state: Any | None = None) -> M5TaskPose:
    machine_profile = _machine_profile_for(m4)
    if machine_profile is not None:
        pose = forward_kinematics(machine_profile, _joint_value_mapping(machine_profile, q))
        return M5TaskPose(position=pose.position, toolAxis=pose.tool_axis)
    raw_pose = _lookup(raw_state, "task_pose", "taskPose")
    if raw_pose is None:
        raise ValueError("M4 trajectory must expose machineProfile or taskPose")
    return M5TaskPose(
        position=_tuple3(_require_lookup(raw_pose, "position"), field_name="taskPose.position"),
        toolAxis=_tuple3(_require_lookup(raw_pose, "tool_axis", "toolAxis"), field_name="taskPose.toolAxis"),
    )


def _evaluate_continuous_state(m4: M4ContinuousTrajectory | Any, t: float) -> Any:
    if _F3_TIMING_EVALUATOR is not None:
        return _F3_TIMING_EVALUATOR(m4, t)
    evaluator = _lookup(m4, "evaluate_continuous_state", "evaluateContinuousState")
    if callable(evaluator):
        return evaluator(t)
    raise ValueError("M4 trajectory must expose evaluate_continuous_state(t)")


def _normalized_source_state(m4: M4ContinuousTrajectory | Any, t: float) -> dict[str, Any]:
    raw = _evaluate_continuous_state(m4, t)
    q = _tuple5(_require_lookup(raw, "q", "joint_position", "jointPosition", "joint_values", "jointValues"), field_name="q")
    return {
        "t": float(t),
        "sigma": float(_require_finite_json_number(_require_lookup(raw, "sigma"))),
        "q": q,
        "qdot": _tuple5(
            _require_lookup(raw, "qdot", "joint_velocity", "jointVelocity", "joint_velocities", "jointVelocities"),
            field_name="qdot",
        ),
        "qddot": _tuple5(
            _require_lookup(
                raw, "qddot", "joint_acceleration", "jointAcceleration", "joint_accelerations", "jointAccelerations"
            ),
            field_name="qddot",
        ),
        "qjerk": _tuple5(_require_lookup(raw, "qjerk", "joint_jerk", "jointJerk", "joint_jerks", "jointJerks"), field_name="qjerk"),
        "task_pose": _task_pose_for(m4, q, raw),
    }


def _sample_times(duration: float, sample_period: float) -> tuple[list[float], float]:
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


def _interval_coefficients(start_state: Mapping[str, Any], end_state: Mapping[str, Any], dt: float) -> tuple[tuple[float, ...], ...]:
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
    powers: list[tuple[float, ...]] = []
    for power in range(8):
        powers.append(tuple(axis_coefficients[power] for axis_coefficients in solved))
    return tuple(powers)


def _interval_coefficients_array(interval: M5IntervalRecord) -> np.ndarray:
    return np.asarray(interval.certificate_coefficients, dtype=np.float64)


def _evaluate_axis_polynomial(interval: M5IntervalRecord, tau: float, axis: int, *, derivative: int = 0) -> float:
    coefficients = np.asarray(interval.certificate_coefficients, dtype=np.float64)[:, axis]
    derived = np.polynomial.polynomial.polyder(coefficients, m=derivative)
    return float(np.polynomial.polynomial.polyval(tau, derived))


def _find_interval(artifact: _M5ArtifactBase, t: float) -> M5IntervalRecord | None:
    for interval in artifact.intervals:
        if interval.t_start - _EPSILON <= t < interval.t_end - _EPSILON:
            return interval
    if math.isclose(t, artifact.duration, abs_tol=_EPSILON):
        return artifact.intervals[-1] if artifact.intervals else None
    return None


def _evaluate_policy_state(
    artifact: M5SampledTrajectory | M5DiscreteCommand,
    t: float,
) -> dict[str, Any]:
    if t < -_EPSILON:
        raise ValueError("t must be nonnegative")
    if t > artifact.duration + _EPSILON:
        if not artifact.final_hold:
            raise ValueError("t exceeds the sampled duration and finalHold is disabled")
        terminal = artifact.samples[-1]
        return {
            "t": float(t),
            "sigma": terminal.sigma,
            "q": terminal.q,
            "qdot": (0.0, 0.0, 0.0, 0.0, 0.0),
            "qddot": (0.0, 0.0, 0.0, 0.0, 0.0),
            "qjerk": (0.0, 0.0, 0.0, 0.0, 0.0),
            "task_pose": terminal.task_pose,
        }
    if math.isclose(t, artifact.duration, abs_tol=_EPSILON):
        terminal = artifact.samples[-1]
        return {
            "t": float(t),
            "sigma": terminal.sigma,
            "q": terminal.q,
            "qdot": terminal.qdot,
            "qddot": terminal.qddot,
            "qjerk": terminal.qjerk,
            "task_pose": terminal.task_pose,
        }
    interval = _find_interval(artifact, t)
    if interval is None:
        raise ValueError("failed to resolve reconstruction interval")
    start = artifact.samples[interval.start_sample_index]
    end = artifact.samples[interval.end_sample_index]
    tau = t - interval.t_start
    dt = interval.t_end - interval.t_start
    policy_id = artifact.reconstruction_policy.policy_id
    if policy_id == REFERENCE_M4_POLICY_ID:
        return _normalized_source_state(artifact.source_m4, t)
    if policy_id in {REFERENCE_M4_POLICY_ID, POLYNOMIAL_POLICY_ID}:
        q = tuple(_evaluate_axis_polynomial(interval, tau, axis, derivative=0) for axis in range(5))
        qdot = tuple(_evaluate_axis_polynomial(interval, tau, axis, derivative=1) for axis in range(5))
        qddot = tuple(_evaluate_axis_polynomial(interval, tau, axis, derivative=2) for axis in range(5))
        qjerk = tuple(_evaluate_axis_polynomial(interval, tau, axis, derivative=3) for axis in range(5))
    elif policy_id == FOH_POLICY_ID:
        alpha = 0.0 if math.isclose(dt, 0.0, abs_tol=_EPSILON) else tau / dt
        q = tuple((1.0 - alpha) * start.q[axis] + alpha * end.q[axis] for axis in range(5))
        qdot = tuple(0.0 if math.isclose(dt, 0.0, abs_tol=_EPSILON) else (end.q[axis] - start.q[axis]) / dt for axis in range(5))
        qddot = (0.0, 0.0, 0.0, 0.0, 0.0)
        qjerk = (0.0, 0.0, 0.0, 0.0, 0.0)
    else:
        q = start.q
        qdot = (0.0, 0.0, 0.0, 0.0, 0.0)
        qddot = (0.0, 0.0, 0.0, 0.0, 0.0)
        qjerk = (0.0, 0.0, 0.0, 0.0, 0.0)
    machine_profile = _machine_profile_for(artifact.source_m4)
    if machine_profile is not None:
        pose = forward_kinematics(machine_profile, _joint_value_mapping(machine_profile, q))
        task_pose = M5TaskPose(position=pose.position, toolAxis=pose.tool_axis)
    else:
        task_pose = start.task_pose
    sigma = start.sigma if math.isclose(dt, 0.0, abs_tol=_EPSILON) else start.sigma + (end.sigma - start.sigma) * (tau / dt)
    return {"t": float(t), "sigma": float(sigma), "q": q, "qdot": qdot, "qddot": qddot, "qjerk": qjerk, "task_pose": task_pose}


def _real_roots(coefficients: np.ndarray) -> tuple[float, ...]:
    if coefficients.size <= 1:
        return ()
    roots = np.polynomial.polynomial.polyroots(coefficients)
    resolved: list[float] = []
    for root in roots:
        if abs(root.imag) <= 1e-9:
            resolved.append(float(root.real))
    return tuple(resolved)


def _max_abs_polynomial(coefficients: np.ndarray, start: float, end: float) -> tuple[float, float]:
    derivative = np.polynomial.polynomial.polyder(coefficients)
    candidates = [start, end]
    for root in _real_roots(derivative):
        if start - _EPSILON <= root <= end + _EPSILON:
            candidates.append(min(end, max(start, root)))
    values = [float(np.polynomial.polynomial.polyval(candidate, coefficients)) for candidate in candidates]
    absolute = [abs(value) for value in values]
    index = int(np.argmax(absolute))
    return absolute[index], float(candidates[index])


def _certified_abs_bound(coefficients: np.ndarray, interval_length: float) -> float:
    total = 0.0
    for power, coefficient in enumerate(coefficients):
        total += abs(float(coefficient)) * interval_length**power
    return math.nextafter(float(total), math.inf)


def _position_peak_for_interval(
    artifact: M5SampledTrajectory | M5DiscreteCommand,
    interval: M5IntervalRecord,
    axis: int,
) -> tuple[float, str]:
    policy_id = artifact.reconstruction_policy.policy_id
    start = artifact.samples[interval.start_sample_index]
    end = artifact.samples[interval.end_sample_index]
    dt = interval.t_end - interval.t_start
    if policy_id in {REFERENCE_M4_POLICY_ID, POLYNOMIAL_POLICY_ID}:
        return _max_abs_polynomial(np.asarray(interval.certificate_coefficients, dtype=np.float64)[:, axis], 0.0, dt)[0], "analytic-extrema"
    if policy_id == FOH_POLICY_ID:
        return max(abs(start.q[axis]), abs(end.q[axis])), "endpoint-linear"
    return abs(start.q[axis]), "left-hold"


def _derivative_peak_for_interval(
    artifact: M5SampledTrajectory | M5DiscreteCommand,
    interval: M5IntervalRecord,
    axis: int,
    quantity: Literal["velocity", "acceleration", "jerk"],
) -> tuple[float, str]:
    order = {"velocity": 1, "acceleration": 2, "jerk": 3}[quantity]
    policy_id = artifact.reconstruction_policy.policy_id
    if policy_id in {REFERENCE_M4_POLICY_ID, POLYNOMIAL_POLICY_ID}:
        dt = interval.t_end - interval.t_start
        coefficients = np.polynomial.polynomial.polyder(np.asarray(interval.certificate_coefficients, dtype=np.float64)[:, axis], m=order)
        return _max_abs_polynomial(coefficients, 0.0, dt)[0], "analytic-extrema"
    if policy_id == FOH_POLICY_ID and quantity == "velocity":
        start = artifact.samples[interval.start_sample_index]
        end = artifact.samples[interval.end_sample_index]
        dt = interval.t_end - interval.t_start
        value = 0.0 if math.isclose(dt, 0.0, abs_tol=_EPSILON) else abs((end.q[axis] - start.q[axis]) / dt)
        return value, "piecewise-linear"
    raise ValueError("unsupported derivative capability")


def _certified_derivative_bound_for_interval(
    interval: M5IntervalRecord,
    axis: int,
    quantity: Literal["velocity", "acceleration", "jerk"],
) -> float:
    order = {"velocity": 1, "acceleration": 2, "jerk": 3}[quantity]
    dt = interval.t_end - interval.t_start
    coefficients = np.polynomial.polynomial.polyder(np.asarray(interval.certificate_coefficients, dtype=np.float64)[:, axis], m=order)
    return _certified_abs_bound(coefficients, dt)


def sample_continuous_trajectory(
    m4: Any,
    *,
    sample_period: float,
    policy: ReconstructionPolicy | str,
    final_hold: bool,
    artifact_kind: ArtifactKind = "auto",
) -> M5SampledTrajectory | M5DiscreteCommand:
    sample_period = float(_require_finite_json_number(sample_period))
    reconstruction_policy = policy if isinstance(policy, ReconstructionPolicy) else ReconstructionPolicy(policyId=policy)
    resolved_artifact_kind = _resolve_artifact_kind(reconstruction_policy.policy_id, artifact_kind)
    duration = _duration_of(m4)
    times, remainder = _sample_times(duration, sample_period)
    source_m4_id = _source_m4_id(m4)
    source_m4_content_id = _source_m4_content_id(m4)
    samples: list[M5Sample] = []
    states: list[dict[str, Any]] = []
    for index, t in enumerate(times):
        state = _normalized_source_state(m4, t)
        states.append(state)
        samples.append(
            M5Sample(
                sampleId=f"{source_m4_id}.sample.{index}",
                sampleIndex=index,
                t=t,
                cycle=int(min(index, math.floor(t / sample_period + _EPSILON))),
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
                        method="evaluate_continuous_state",
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
                intervalId=f"{source_m4_id}.interval.{index}",
                intervalIndex=index,
                startSampleIndex=index,
                endSampleIndex=index + 1,
                tStart=samples[index].t,
                tEnd=samples[index + 1].t,
                certificateCoefficients=_interval_coefficients(start_state, end_state, dt),
            )
        )
    common = dict(
        schema_id="five-axis.m5-sampled-trajectory@1"
        if resolved_artifact_kind == "sampled-trajectory"
        else "five-axis.m5-discrete-command@1",
        schema_version=1,
        content_id="0" * 64,
        source_m4=m4,
        source_m4_id=source_m4_id,
        source_m4_content_id=source_m4_content_id,
        sample_period=sample_period,
        duration=duration,
        remainder_duration=0.0 if math.isclose(remainder, sample_period, abs_tol=_EPSILON) else remainder,
        final_hold=final_hold,
        reconstruction_policy=reconstruction_policy,
        limits=_limits_for(m4),
        samples=tuple(samples),
        intervals=tuple(intervals),
        provenance=(
            M5ProvenanceRef(
                sourceStage="M4",
                sourceId=source_m4_id,
                sourceContentId=source_m4_content_id,
                method="fixed-period-sampling",
            ),
        ),
    )
    if resolved_artifact_kind == "sampled-trajectory":
        artifact = M5SampledTrajectory.model_construct(
            artifact_type="five-axis.m5-sampled-trajectory",
            sampled_trajectory_id=f"{source_m4_id}.m5-sampled",
            **common,
        )
    else:
        artifact = M5DiscreteCommand.model_construct(
            artifact_type="five-axis.m5-discrete-command",
            discrete_command_id=f"{source_m4_id}.m5-command",
            **common,
        )
    payload = artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["contentId"] = _canonical_content_id(artifact)
    return artifact.__class__.model_validate(payload)


def verify_interval_reconstruction(artifact: M5SampledTrajectory | M5DiscreteCommand) -> M5VerificationResult:
    policy_id = artifact.reconstruction_policy.policy_id
    declared = set(_POLICY_DECLARED_CAPABILITIES[policy_id])
    certifiable_policy = policy_id == POLYNOMIAL_POLICY_ID
    axis_units = artifact.limits.position_units
    quantities: list[M5QuantityVerification] = []
    error_ledger: list[M5ErrorLedgerEntry] = []
    consistency_reason: str | None = None
    source_verification = (
        _F3_TIMING_VERIFIER(artifact.source_m4)
        if policy_id == REFERENCE_M4_POLICY_ID and _F3_TIMING_VERIFIER is not None
        else None
    )
    source_usage_by_axis: dict[int, Any] = {}
    if source_verification is not None:
        machine_profile = _machine_profile_for(artifact.source_m4)
        if machine_profile is not None:
            usage_by_id = {item.axis_id: item for item in source_verification.axis_constraint_usage}
            ordered_axes = sorted(machine_profile.axes, key=lambda item: item.axis_order)
            source_usage_by_axis = {
                index: usage_by_id[axis.axis_id]
                for index, axis in enumerate(ordered_axes)
                if axis.axis_id in usage_by_id
            }

    def derivative_units(power: int) -> tuple[str, str, str, str, str]:
        suffix = {1: "/s", 2: "/s^2", 3: "/s^3"}[power]
        return tuple(f"{unit}{suffix}" for unit in axis_units)

    for sample in artifact.samples:
        source_state = _normalized_source_state(artifact.source_m4, sample.t)
        sigma_error = abs(source_state["sigma"] - sample.sigma)
        if sigma_error > 1e-9:
            consistency_reason = consistency_reason or "SampleReplayMismatch"
            error_ledger.append(
                M5ErrorLedgerEntry(
                    quantity="sigma",
                    unit="dimensionless",
                    source=f"{policy_id}:{sample.sample_id}",
                    bound=sigma_error,
                    method="source-replay-consistency",
                )
            )
        for quantity, key, units in (
            ("joint-position", "q", axis_units),
            ("joint-velocity", "qdot", derivative_units(1)),
            ("joint-acceleration", "qddot", derivative_units(2)),
            ("joint-jerk", "qjerk", derivative_units(3)),
        ):
            observed = getattr(sample, key)
            for axis in range(5):
                mismatch = abs(source_state[key][axis] - observed[axis])
                if mismatch > 1e-9:
                    consistency_reason = consistency_reason or "SampleReplayMismatch"
                    error_ledger.append(
                        M5ErrorLedgerEntry(
                            quantity=quantity,
                            axis=axis,
                            unit=units[axis],
                            source=f"{policy_id}:{sample.sample_id}",
                            bound=mismatch,
                            method="source-replay-consistency",
                        )
                    )
    for interval in artifact.intervals:
        start_sample = artifact.samples[interval.start_sample_index]
        end_sample = artifact.samples[interval.end_sample_index]
        dt = interval.t_end - interval.t_start
        for axis in range(5):
            for quantity, derivative_order, units in (
                ("joint-position", 0, axis_units),
                ("joint-velocity", 1, derivative_units(1)),
                ("joint-acceleration", 2, derivative_units(2)),
                ("joint-jerk", 3, derivative_units(3)),
            ):
                start_mismatch = abs(
                    _evaluate_axis_polynomial(interval, 0.0, axis, derivative=derivative_order)
                    - getattr(start_sample, {0: "q", 1: "qdot", 2: "qddot", 3: "qjerk"}[derivative_order])[axis]
                )
                end_mismatch = abs(
                    _evaluate_axis_polynomial(interval, dt, axis, derivative=derivative_order)
                    - getattr(end_sample, {0: "q", 1: "qdot", 2: "qddot", 3: "qjerk"}[derivative_order])[axis]
                )
                mismatch = max(start_mismatch, end_mismatch)
                if mismatch > 1e-9:
                    consistency_reason = consistency_reason or "CoefficientEndpointMismatch"
                    error_ledger.append(
                        M5ErrorLedgerEntry(
                            quantity=quantity,
                            axis=axis,
                            unit=units[axis],
                            source=f"{policy_id}:{interval.interval_id}",
                            bound=mismatch,
                            method="certificate-endpoint-replay",
                        )
                    )

    for quantity in ("position", "velocity", "acceleration", "jerk"):
        if quantity not in declared:
            axis_results = tuple(
                M5AxisVerification(axis=axis, unit=derivative_units(1)[axis] if quantity == "velocity" else derivative_units(2)[axis] if quantity == "acceleration" else derivative_units(3)[axis] if quantity == "jerk" else axis_units[axis], status="Unsupported", reasonCode="PolicyCapabilityUnsupported")
                for axis in range(5)
            )
            quantities.append(M5QuantityVerification(quantity=quantity, status="Unsupported", axisResults=axis_results, reasonCode="PolicyCapabilityUnsupported"))
            continue
        if quantity == "position":
            axis_results = []
            for axis in range(5):
                peaks = [_position_peak_for_interval(artifact, interval, axis)[0] for interval in artifact.intervals] or [abs(artifact.samples[0].q[axis])]
                axis_results.append(
                    M5AxisVerification(
                        axis=axis,
                        unit=axis_units[axis],
                        status="Supported",
                        observedPeak=max(peaks),
                    )
                )
            quantities.append(M5QuantityVerification(quantity="position", status="Supported", axisResults=tuple(axis_results)))
            continue
        limits = {
            "velocity": artifact.limits.velocity_limits,
            "acceleration": artifact.limits.acceleration_limits,
            "jerk": artifact.limits.jerk_limits,
        }[quantity]
        if limits is None:
            axis_results = tuple(
                M5AxisVerification(
                    axis=axis,
                    unit=derivative_units({"velocity": 1, "acceleration": 2, "jerk": 3}[quantity])[axis],
                    status="Unsupported",
                    reasonCode="MissingLimits",
                )
                for axis in range(5)
            )
            quantities.append(M5QuantityVerification(quantity=quantity, status="Unsupported", axisResults=axis_results, reasonCode="MissingLimits"))
            continue
        axis_results = []
        quantity_status = "Supported"
        units = derivative_units({"velocity": 1, "acceleration": 2, "jerk": 3}[quantity])
        for axis in range(5):
            if policy_id == REFERENCE_M4_POLICY_ID:
                if source_verification is None:
                    if quantity_status != "Refuted":
                        quantity_status = "Unsupported"
                    axis_results.append(
                        M5AxisVerification(
                            axis=axis,
                            unit=units[axis],
                            status="Unsupported",
                            limit=limits[axis],
                            reasonCode="SourceContinuousVerifierUnavailable",
                        )
                    )
                    continue
                if source_verification.overall_status != "Supported":
                    source_status = (
                        "Refuted" if source_verification.overall_status == "Refuted" else "Unsupported"
                    )
                    if source_status == "Refuted":
                        quantity_status = "Refuted"
                    elif quantity_status != "Refuted":
                        quantity_status = "Unsupported"
                    axis_results.append(
                        M5AxisVerification(
                            axis=axis,
                            unit=units[axis],
                            status=source_status,
                            limit=limits[axis],
                            reasonCode=f"SourceContinuousTrajectory{source_verification.overall_status}",
                        )
                    )
                    continue
                usage = source_usage_by_axis.get(axis)
                if usage is None:
                    if quantity_status != "Refuted":
                        quantity_status = "Unsupported"
                    axis_results.append(
                        M5AxisVerification(
                            axis=axis,
                            unit=units[axis],
                            status="Unsupported",
                            limit=limits[axis],
                            reasonCode="SourceAxisConstraintUsageMissing",
                        )
                    )
                    continue
                observed = {
                    "velocity": usage.maximum_velocity,
                    "acceleration": usage.maximum_acceleration,
                    "jerk": usage.maximum_jerk,
                }[quantity]
                if observed is None:
                    if quantity_status != "Refuted":
                        quantity_status = "Unsupported"
                    axis_results.append(
                        M5AxisVerification(
                            axis=axis,
                            unit=units[axis],
                            status="Unsupported",
                            limit=limits[axis],
                            reasonCode="SourceAxisConstraintUsageMissing",
                        )
                    )
                    continue
                limit = limits[axis]
                if observed > limit + _EPSILON:
                    quantity_status = "Refuted"
                    axis_results.append(
                        M5AxisVerification(
                            axis=axis,
                            unit=units[axis],
                            status="Refuted",
                            observedPeak=observed,
                            limit=limit,
                            reasonCode="SourceContinuousLimitExceeded",
                        )
                    )
                else:
                    axis_results.append(
                        M5AxisVerification(
                            axis=axis,
                            unit=units[axis],
                            status="Supported",
                            observedPeak=observed,
                            limit=limit,
                        )
                    )
                continue
            worst_peak = 0.0
            certified_bound = 0.0
            worst_interval_id: str | None = None
            worst_method = "analytic-extrema"
            for interval in artifact.intervals:
                peak, method = _derivative_peak_for_interval(artifact, interval, axis, quantity)
                if peak >= worst_peak:
                    worst_peak = peak
                    worst_interval_id = interval.interval_id
                    worst_method = method
                if certifiable_policy:
                    certified_bound = max(
                        certified_bound,
                        _certified_derivative_bound_for_interval(interval, axis, quantity),
                    )
            limit = limits[axis]
            if worst_peak > limit + _EPSILON:
                quantity_status = "Refuted"
                axis_results.append(
                    M5AxisVerification(
                        axis=axis,
                        unit=units[axis],
                        status="Refuted",
                        observedPeak=worst_peak,
                        limit=limit,
                        intervalId=worst_interval_id,
                        reasonCode="IntervalInteriorLimitExceeded",
                    )
                )
                error_ledger.append(
                    M5ErrorLedgerEntry(
                        quantity=f"joint-{quantity}",
                        axis=axis,
                        unit=units[axis],
                        source=f"{policy_id}:{worst_interval_id or 'terminal'}",
                        bound=worst_peak - limit,
                        method=worst_method,
                    )
                )
            elif certifiable_policy and certified_bound > limit + _EPSILON:
                if quantity_status != "Refuted":
                    quantity_status = "Unsupported"
                axis_results.append(
                    M5AxisVerification(
                        axis=axis,
                        unit=units[axis],
                        status="Unsupported",
                        observedPeak=certified_bound,
                        limit=limit,
                        intervalId=worst_interval_id,
                        reasonCode="CertifiedBoundExceedsLimit",
                    )
                )
            else:
                axis_results.append(
                    M5AxisVerification(
                        axis=axis,
                        unit=units[axis],
                        status="Supported",
                        observedPeak=certified_bound if certifiable_policy else worst_peak,
                        limit=limit,
                        intervalId=worst_interval_id,
                    )
                )
        quantities.append(M5QuantityVerification(quantity=quantity, status=quantity_status, axisResults=tuple(axis_results)))

    if artifact.intervals:
        machine_profile = _machine_profile_for(artifact.source_m4)
        midpoint_times = tuple((interval.t_start + interval.t_end) * 0.5 for interval in artifact.intervals)
        for quantity, key, units in (
            ("joint-position", "q", axis_units),
            ("joint-velocity", "qdot", derivative_units(1)),
            ("joint-acceleration", "qddot", derivative_units(2)),
            ("joint-jerk", "qjerk", derivative_units(3)),
        ):
            maxima = [0.0] * 5
            for t in midpoint_times:
                source_state = _normalized_source_state(artifact.source_m4, t)
                reconstructed = _evaluate_policy_state(artifact, t)
                for axis in range(5):
                    maxima[axis] = max(maxima[axis], abs(source_state[key][axis] - reconstructed[key][axis]))
            for axis in range(5):
                error_ledger.append(
                    M5ErrorLedgerEntry(
                        quantity=quantity,
                        axis=axis,
                        unit=units[axis],
                        source=policy_id,
                        bound=maxima[axis],
                        method="midpoint-replay",
                    )
                )
        if machine_profile is not None:
            position_error = 0.0
            orientation_error = 0.0
            for t in midpoint_times:
                source_state = _normalized_source_state(artifact.source_m4, t)
                reconstructed = _evaluate_policy_state(artifact, t)
                source_pose = source_state["task_pose"]
                reconstructed_pose = reconstructed["task_pose"]
                position_error = max(
                    position_error,
                    math.dist(source_pose.position, reconstructed_pose.position),
                )
                dot = sum(a * b for a, b in zip(source_pose.tool_axis, reconstructed_pose.tool_axis, strict=True))
                dot = min(1.0, max(-1.0, dot))
                orientation_error = max(orientation_error, math.acos(dot))
            error_ledger.append(
                M5ErrorLedgerEntry(
                    quantity="position",
                    unit="mm",
                    source=policy_id,
                    bound=position_error,
                    method="forward-kinematics-midpoint-replay",
                )
            )
            error_ledger.append(
                M5ErrorLedgerEntry(
                    quantity="orientation",
                    unit="rad",
                    source=policy_id,
                    bound=orientation_error,
                    method="forward-kinematics-midpoint-replay",
                )
            )

    non_interval_results = [item for item in quantities if item.quantity != "interval-certified"]
    if consistency_reason is not None:
        overall_status = "Refuted"
        interval_reason = consistency_reason
    elif source_verification is not None and source_verification.overall_status == "Refuted":
        overall_status = "Refuted"
        interval_reason = "SourceContinuousTrajectoryRefuted"
    elif policy_id == REFERENCE_M4_POLICY_ID and (
        source_verification is None or source_verification.overall_status != "Supported"
    ):
        overall_status = "Unsupported"
        interval_reason = "SourceContinuousTrajectoryUnsupported"
    elif policy_id in {FOH_POLICY_ID, ZOH_POLICY_ID}:
        overall_status = "Unsupported"
        interval_reason = "FullDerivativeClosureUnsupportedByPolicy"
    elif any(item.status == "Refuted" for item in non_interval_results if item.quantity in declared):
        overall_status = "Refuted"
        interval_reason = "DeclaredCapabilityRefuted"
    elif any(item.status == "Unsupported" for item in non_interval_results if item.quantity in declared):
        overall_status = "Unsupported"
        interval_reason = "DeclaredCapabilityUnsupported"
    else:
        overall_status = "Supported"
        interval_reason = None
    evidence_level = "Certified" if overall_status == "Supported" else "Validated"
    method = {
        REFERENCE_M4_POLICY_ID: "five-axis.m5.reference-m4.replay-certified-power-bound@1",
        POLYNOMIAL_POLICY_ID: "five-axis.m5.polynomial.certified-power-bound@1",
        FOH_POLICY_ID: "five-axis.m5.foh.segment-check@1",
        ZOH_POLICY_ID: "five-axis.m5.zoh.segment-check@1",
    }[policy_id]
    quantities.append(
        M5QuantityVerification(
            quantity="interval-certified",
            status=overall_status,
            axisResults=tuple(),
            reasonCode=interval_reason,
        )
    )
    return M5VerificationResult(
        status=overall_status,
        evidenceLevel=evidence_level,
        method=method,
        policyId=policy_id,
        artifactType=artifact.artifact_type,
        artifactId=artifact.artifact_id_value(),
        sourceM4ContentId=artifact.source_m4_content_id,
        quantities=tuple(quantities),
        errorLedger=tuple(error_ledger),
    )


__all__ = [
    "FOH_POLICY_ID",
    "POLYNOMIAL_POLICY_ID",
    "REFERENCE_M4_POLICY_ID",
    "ZOH_POLICY_ID",
    "M5DiscreteCommand",
    "M5ErrorLedgerEntry",
    "M5QuantityVerification",
    "M5Sample",
    "M5SampledTrajectory",
    "M5VerificationResult",
    "ReconstructionPolicy",
    "sample_continuous_trajectory",
    "verify_interval_reconstruction",
]
