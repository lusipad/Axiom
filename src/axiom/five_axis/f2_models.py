from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel
from .f1_models import (
    ExpectedMetric,
    M2CandidateTaskGeometry,
    NodeEvent,
    PathProgress,
    ProvenanceRef,
    RegularityCertificate,
    StageDecision,
    ToleranceBinding,
)

_EPSILON = 1e-12
_CONTENT_HASH_PATTERN = r"^[0-9a-f]{64}$"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_VERSIONED_ID_PATTERN = r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+@[1-9][0-9]*$"
_QUATERNION_TOLERANCE = 1e-9
_VECTOR_TOLERANCE = 1e-9
_VERSION_SUFFIX_PATTERN = re.compile(r"@([1-9][0-9]*)$")


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


def _require_unique_ids(items: tuple[Any, ...], *, attr: str, field_name: str) -> tuple[Any, ...]:
    values = tuple(getattr(item, attr) for item in items)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicate IDs")
    return items


def _validate_unit_interval(start: float, end: float, *, field_name: str) -> None:
    if start < -_EPSILON or end > 1.0 + _EPSILON:
        raise ValueError(f"{field_name} must stay within [0, 1]")
    if end < start - _EPSILON:
        raise ValueError(f"{field_name} must be monotone nondecreasing")


def _validate_interval_coverage(
    items: tuple[Any, ...], *, start_attr: str, end_attr: str, field_name: str
) -> None:
    cursor = 0.0
    for item in items:
        start = getattr(item, start_attr)
        end = getattr(item, end_attr)
        if start < cursor - _EPSILON:
            raise ValueError(f"{field_name} must not overlap")
        if start > cursor + _EPSILON:
            raise ValueError(f"{field_name} must not contain gaps")
        if end < start - _EPSILON:
            raise ValueError(f"{field_name} must be monotone nondecreasing")
        cursor = max(cursor, end)
    if items:
        first = getattr(items[0], start_attr)
        last = getattr(items[-1], end_attr)
        if not math.isclose(first, 0.0, abs_tol=_EPSILON):
            raise ValueError(f"{field_name} must start at 0.0")
        if not math.isclose(last, 1.0, abs_tol=_EPSILON):
            raise ValueError(f"{field_name} must end at 1.0")


def _validate_unit_vector(vector: tuple[float, float, float], *, field_name: str) -> tuple[float, float, float]:
    norm = math.sqrt(sum(component * component for component in vector))
    if math.isclose(norm, 0.0, abs_tol=_EPSILON):
        raise ValueError(f"{field_name} must not be the zero vector")
    if not math.isclose(norm, 1.0, abs_tol=_VECTOR_TOLERANCE):
        raise ValueError(f"{field_name} must be unit length")
    return vector


def _validate_unit_quaternion(
    quaternion: tuple[float, float, float, float], *, field_name: str
) -> tuple[float, float, float, float]:
    norm = math.sqrt(sum(component * component for component in quaternion))
    if math.isclose(norm, 0.0, abs_tol=_EPSILON):
        raise ValueError(f"{field_name} must not be the zero quaternion")
    if not math.isclose(norm, 1.0, abs_tol=_QUATERNION_TOLERANCE):
        raise ValueError(f"{field_name} must be unit length")
    return quaternion


def _version_from_id(identifier: str, *, field_name: str) -> int:
    match = _VERSION_SUFFIX_PATTERN.search(identifier)
    if match is None:
        raise ValueError(f"{field_name} must be a versioned identifier")
    return int(match.group(1))


class RigidTransform(AxiomModel):
    transform_id: str = Field(alias="transformId", min_length=1, pattern=_ID_PATTERN)
    translation: tuple[float, float, float]
    rotation_quaternion: tuple[float, float, float, float] = Field(alias="rotationQuaternion")

    @field_validator("translation", mode="before")
    @classmethod
    def reject_invalid_translation(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="translation")

    @field_validator("rotation_quaternion", mode="before")
    @classmethod
    def reject_invalid_rotation_quaternion(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=4, field_name="rotationQuaternion")

    @model_validator(mode="after")
    def require_unit_quaternion(self) -> "RigidTransform":
        _validate_unit_quaternion(self.rotation_quaternion, field_name="rotationQuaternion")
        return self


class AxisLimits(AxiomModel):
    lower: float
    upper: float
    unit: Literal["mm", "rad"]

    @field_validator("lower", "upper", mode="before")
    @classmethod
    def reject_invalid_bounds(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_ordered_interval(self) -> "AxisLimits":
        if self.upper <= self.lower:
            raise ValueError("AxisLimits upper must be greater than lower")
        return self


class MachineAxis(AxiomModel):
    axis_id: str = Field(alias="axisId", min_length=1, pattern=_ID_PATTERN)
    axis_order: int = Field(alias="axisOrder", ge=0, le=4)
    joint_type: Literal["prismatic", "revolute"] = Field(alias="jointType")
    axis_symbol: Literal["X", "Y", "Z", "A", "B", "C"] = Field(alias="axisSymbol")
    semantic_role: Literal[
        "linear-x",
        "linear-y",
        "linear-z",
        "workpiece-rotary-primary",
        "workpiece-rotary-secondary",
        "tool-rotary-primary",
        "tool-rotary-secondary",
    ] = Field(alias="semanticRole")
    parent_axis_id: str | None = Field(default=None, alias="parentAxisId", pattern=_ID_PATTERN)
    origin: tuple[float, float, float]
    direction: tuple[float, float, float]
    installation_side: Literal["workpiece", "tool"] = Field(alias="installationSide")
    sign: Literal["positive", "negative"]
    zero_position: float = Field(alias="zeroPosition")
    periodic: bool
    limits: AxisLimits

    @field_validator("origin", "direction", mode="before")
    @classmethod
    def reject_invalid_vectors(cls, value: Any, info: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name=info.field_name)

    @field_validator("zero_position", mode="before")
    @classmethod
    def reject_invalid_zero_position(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_joint_consistency(self) -> "MachineAxis":
        _validate_unit_vector(self.direction, field_name="direction")
        if self.joint_type == "prismatic":
            if self.axis_symbol not in {"X", "Y", "Z"}:
                raise ValueError("prismatic joints must use X/Y/Z axisSymbol")
            if self.semantic_role != f"linear-{self.axis_symbol.lower()}":
                raise ValueError("prismatic semanticRole must match axisSymbol")
            if self.periodic:
                raise ValueError("prismatic joints must not be periodic")
            if self.limits.unit != "mm":
                raise ValueError("prismatic joint limits must use mm")
        else:
            if self.axis_symbol not in {"A", "B", "C"}:
                raise ValueError("revolute joints must use A/B/C axisSymbol")
            if self.semantic_role.startswith("linear-"):
                raise ValueError("revolute joints must not use linear semanticRole")
            if self.limits.unit != "rad":
                raise ValueError("revolute joint limits must use rad")
            expected_side = "workpiece" if self.semantic_role.startswith("workpiece-") else "tool"
            if self.installation_side != expected_side:
                raise ValueError("revolute semanticRole must match installationSide")
        return self


class MachineProfile(AxiomModel):
    artifact_type: Literal["five-axis.machine-profile"] = Field(alias="artifactType")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    profile_id: str = Field(alias="profileId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    profile_version: int = Field(alias="profileVersion", ge=1)
    topology: Literal["dual-table", "head-table", "dual-head"]
    axes: tuple[MachineAxis, ...] = Field(min_length=5, max_length=5)
    workpiece_frame: RigidTransform = Field(alias="workpieceFrame")
    tool_mount_frame: RigidTransform = Field(alias="toolMountFrame")

    @model_validator(mode="after")
    def require_five_axis_topology(self) -> "MachineProfile":
        if _version_from_id(self.profile_id, field_name="profileId") != self.profile_version:
            raise ValueError("profileVersion must match the @version suffix in profileId")
        _require_unique_ids(self.axes, attr="axis_id", field_name="axes")
        _require_unique_ids(self.axes, attr="axis_symbol", field_name="axes")
        _require_unique_ids(self.axes, attr="semantic_role", field_name="axes")
        orders = tuple(axis.axis_order for axis in self.axes)
        if orders != (0, 1, 2, 3, 4):
            raise ValueError("MachineProfile axes must be serialized in axisOrder 0..4")
        axes_by_id = {axis.axis_id: axis for axis in self.axes}
        for side in ("workpiece", "tool"):
            side_axes = sorted(
                (axis for axis in self.axes if axis.installation_side == side),
                key=lambda item: item.axis_order,
            )
            if not side_axes:
                continue
            if side_axes[0].parent_axis_id is not None:
                raise ValueError("the first axis on each installationSide must be a root axis")
            for parent, axis in zip(side_axes[:-1], side_axes[1:], strict=True):
                if axis.parent_axis_id != parent.axis_id:
                    raise ValueError(
                        "parentAxisId must reference the immediately preceding axis on the same installationSide"
                    )
            for axis in side_axes:
                if axis.parent_axis_id is None:
                    continue
                resolved_parent = axes_by_id.get(axis.parent_axis_id)
                if resolved_parent is None or resolved_parent.installation_side != side:
                    raise ValueError("parentAxisId must reference an axis on the same installationSide")
        prismatic_axes = tuple(axis for axis in self.axes if axis.joint_type == "prismatic")
        revolute_axes = tuple(axis for axis in self.axes if axis.joint_type == "revolute")
        if len(prismatic_axes) != 3 or len(revolute_axes) != 2:
            raise ValueError("MachineProfile must contain exactly 3 prismatic and 2 revolute joints")
        if {axis.axis_symbol for axis in prismatic_axes} != {"X", "Y", "Z"}:
            raise ValueError("MachineProfile prismatic joints must cover X/Y/Z exactly once")
        expected_rotary_side_counts = {
            "dual-table": (2, 0),
            "head-table": (1, 1),
            "dual-head": (0, 2),
        }[self.topology]
        workpiece_count = sum(axis.installation_side == "workpiece" for axis in revolute_axes)
        tool_count = sum(axis.installation_side == "tool" for axis in revolute_axes)
        if (workpiece_count, tool_count) != expected_rotary_side_counts:
            raise ValueError("MachineProfile revolute installationSide counts must match topology")
        if len({self.workpiece_frame.transform_id, self.tool_mount_frame.transform_id}) != 2:
            raise ValueError("workpieceFrame and toolMountFrame must use distinct transformId values")
        return self


class AxisWrapState(AxiomModel):
    axis_id: str = Field(alias="axisId", min_length=1, pattern=_ID_PATTERN)
    turns: int


class FreeAxisParameter(AxiomModel):
    axis_id: str = Field(alias="axisId", min_length=1, pattern=_ID_PATTERN)
    lower: float
    upper: float
    unit: Literal["rad"]
    semantics: Literal["continuous-singular-family@1"]

    @field_validator("lower", "upper", mode="before")
    @classmethod
    def reject_invalid_bounds(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_ordered_bounds(self) -> "FreeAxisParameter":
        if self.upper <= self.lower:
            raise ValueError("FreeAxisParameter upper must be greater than lower")
        return self


class AxisLimitObservation(AxiomModel):
    axis_id: str = Field(alias="axisId", min_length=1, pattern=_ID_PATTERN)
    status: Literal["within", "at-lower", "at-upper", "violated-lower", "violated-upper"]
    distance_to_lower: float = Field(alias="distanceToLower")
    distance_to_upper: float = Field(alias="distanceToUpper")

    @field_validator("distance_to_lower", "distance_to_upper", mode="before")
    @classmethod
    def reject_invalid_distances(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_consistent_status(self) -> "AxisLimitObservation":
        lower_nonnegative = self.distance_to_lower >= -_EPSILON
        upper_nonnegative = self.distance_to_upper >= -_EPSILON
        if self.status in {"within", "at-lower", "at-upper"} and not (lower_nonnegative and upper_nonnegative):
            raise ValueError("non-violated axisLimitState distances must be nonnegative")
        if self.status == "at-lower" and not math.isclose(self.distance_to_lower, 0.0, abs_tol=_EPSILON):
            raise ValueError("at-lower requires distanceToLower=0")
        if self.status == "at-upper" and not math.isclose(self.distance_to_upper, 0.0, abs_tol=_EPSILON):
            raise ValueError("at-upper requires distanceToUpper=0")
        if self.status == "violated-lower" and self.distance_to_lower >= 0.0:
            raise ValueError("violated-lower requires a negative distanceToLower")
        if self.status == "violated-upper" and self.distance_to_upper >= 0.0:
            raise ValueError("violated-upper requires a negative distanceToUpper")
        return self


class KinematicResidual(AxiomModel):
    metric_id: str = Field(alias="metricId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    value: float = Field(ge=0.0)
    unit: str = Field(min_length=1)

    @field_validator("value", mode="before")
    @classmethod
    def reject_invalid_value(cls, value: Any) -> Any:
        return _require_finite_json_number(value)


class SingularityIndicator(AxiomModel):
    status: Literal["regular", "near-singular", "singular", "unknown"]
    conditioning_metric: float | None = Field(default=None, alias="conditioningMetric", ge=0.0)
    minimum_singular_value: float | None = Field(default=None, alias="minimumSingularValue", ge=0.0)

    @field_validator("conditioning_metric", "minimum_singular_value", mode="before")
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_json_number(value)


class IKSolution(AxiomModel):
    solution_id: str = Field(alias="solutionId", min_length=1, pattern=_ID_PATTERN)
    sigma: float
    branch_id: str = Field(alias="branchId", min_length=1, pattern=_ID_PATTERN)
    joint_values: tuple[float, ...] = Field(alias="jointValues", min_length=5, max_length=5)
    wrap_state: tuple[AxisWrapState, ...] = Field(alias="wrapState", default_factory=tuple)
    free_parameters: tuple[FreeAxisParameter, ...] = Field(alias="freeParameters", default_factory=tuple)
    axis_limit_state: tuple[AxisLimitObservation, ...] = Field(alias="axisLimitState", min_length=1)
    residuals: tuple[KinematicResidual, ...] = Field(min_length=1)
    singularity: SingularityIndicator
    within_limits: bool = Field(alias="withinLimits")

    @field_validator("sigma", mode="before")
    @classmethod
    def reject_invalid_sigma(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @field_validator("joint_values", mode="before")
    @classmethod
    def reject_invalid_joint_values(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=5, field_name="jointValues")

    @model_validator(mode="after")
    def require_consistent_solution(self) -> "IKSolution":
        _validate_unit_interval(self.sigma, self.sigma, field_name="sigma")
        _require_unique_ids(self.wrap_state, attr="axis_id", field_name="wrapState")
        _require_unique_ids(self.free_parameters, attr="axis_id", field_name="freeParameters")
        _require_unique_ids(self.axis_limit_state, attr="axis_id", field_name="axisLimitState")
        _require_unique_ids(self.residuals, attr="metric_id", field_name="residuals")
        has_violation = any(item.status.startswith("violated") for item in self.axis_limit_state)
        if self.within_limits and has_violation:
            raise ValueError("withinLimits cannot be true when axisLimitState reports a violation")
        return self


class BranchNode(AxiomModel):
    branch_id: str = Field(alias="branchId", min_length=1, pattern=_ID_PATTERN)
    sigma_start: float = Field(alias="sigmaStart")
    sigma_end: float = Field(alias="sigmaEnd")
    solution_ids: tuple[str, ...] = Field(alias="solutionIds", min_length=1)
    status: Literal["active", "terminated", "unknown"]

    @field_validator("sigma_start", "sigma_end", mode="before")
    @classmethod
    def reject_invalid_sigma(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @field_validator("solution_ids")
    @classmethod
    def require_unique_solution_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("solutionIds must not contain duplicates")
        return value

    @model_validator(mode="after")
    def require_valid_interval(self) -> "BranchNode":
        _validate_unit_interval(self.sigma_start, self.sigma_end, field_name="branch sigma")
        return self


class BranchTransition(AxiomModel):
    edge_id: str = Field(alias="edgeId", min_length=1, pattern=_ID_PATTERN)
    from_branch_id: str = Field(alias="fromBranchId", min_length=1, pattern=_ID_PATTERN)
    to_branch_id: str = Field(alias="toBranchId", min_length=1, pattern=_ID_PATTERN)
    sigma: float
    transition_type: Literal[
        "continuous",
        "branch-change",
        "wrap",
        "merge",
        "limit-hit",
        "collision-boundary",
        "singularity-boundary",
    ] = Field(alias="transitionType")

    @field_validator("sigma", mode="before")
    @classmethod
    def reject_invalid_sigma(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_unit_sigma(self) -> "BranchTransition":
        _validate_unit_interval(self.sigma, self.sigma, field_name="sigma")
        return self


class BranchGraph(AxiomModel):
    graph_id: str = Field(alias="graphId", min_length=1, pattern=_ID_PATTERN)
    root_branch_ids: tuple[str, ...] = Field(alias="rootBranchIds", min_length=1)
    branches: tuple[BranchNode, ...] = Field(min_length=1)
    transitions: tuple[BranchTransition, ...] = Field(default_factory=tuple)

    @field_validator("root_branch_ids")
    @classmethod
    def require_unique_root_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("rootBranchIds must not contain duplicates")
        return value

    @model_validator(mode="after")
    def require_consistent_references(self) -> "BranchGraph":
        _require_unique_ids(self.branches, attr="branch_id", field_name="branches")
        _require_unique_ids(self.transitions, attr="edge_id", field_name="transitions")
        branch_ids = {branch.branch_id for branch in self.branches}
        if any(branch_id not in branch_ids for branch_id in self.root_branch_ids):
            raise ValueError("rootBranchIds must reference actual branches")
        expected_root_ids = {branch.branch_id for branch in self.branches if math.isclose(branch.sigma_start, 0.0, abs_tol=_EPSILON)}
        if set(self.root_branch_ids) != expected_root_ids:
            raise ValueError("rootBranchIds must list every branch that starts at sigma 0")
        if any(transition.from_branch_id not in branch_ids or transition.to_branch_id not in branch_ids for transition in self.transitions):
            raise ValueError("transitions must reference actual branches")
        branches_by_id = {branch.branch_id: branch for branch in self.branches}
        for transition in self.transitions:
            source = branches_by_id[transition.from_branch_id]
            target = branches_by_id[transition.to_branch_id]
            if not (
                source.sigma_start - _EPSILON <= transition.sigma <= source.sigma_end + _EPSILON
                and target.sigma_start - _EPSILON <= transition.sigma <= target.sigma_end + _EPSILON
            ):
                raise ValueError("transition sigma must lie in both referenced branch intervals")
        return self


class JointPolynomialSegment(AxiomModel):
    segment_id: str = Field(alias="segmentId", min_length=1, pattern=_ID_PATTERN)
    branch_id: str = Field(alias="branchId", min_length=1, pattern=_ID_PATTERN)
    sigma_start: float = Field(alias="sigmaStart")
    sigma_end: float = Field(alias="sigmaEnd")
    start_solution_id: str = Field(alias="startSolutionId", min_length=1, pattern=_ID_PATTERN)
    end_solution_id: str = Field(alias="endSolutionId", min_length=1, pattern=_ID_PATTERN)
    continuity_class: Literal["C0", "C1", "C2", "C3"] = Field(alias="continuityClass")
    interpolation: Literal["linear", "cubic-hermite"]
    coefficient_basis: Literal["local-power@1"] = Field(alias="coefficientBasis")
    coefficients: tuple[tuple[float, ...], ...] = Field(min_length=1)

    @field_validator("sigma_start", "sigma_end", mode="before")
    @classmethod
    def reject_invalid_sigma(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @field_validator("coefficients", mode="before")
    @classmethod
    def reject_invalid_coefficients(cls, value: Any) -> Any:
        if isinstance(value, list):
            for index, coefficient_vector in enumerate(value):
                _require_finite_vector(coefficient_vector, expected=5, field_name=f"coefficients[{index}]")
        return value

    @model_validator(mode="after")
    def require_valid_sigma(self) -> "JointPolynomialSegment":
        _validate_unit_interval(self.sigma_start, self.sigma_end, field_name="segment sigma")
        expected_count = 2 if self.interpolation == "linear" else 4
        if len(self.coefficients) != expected_count:
            raise ValueError(f"{self.interpolation} must contain exactly {expected_count} local-power coefficients")
        return self

    def evaluate(self, sigma: float) -> tuple[float, ...]:
        _require_finite_json_number(sigma)
        if sigma < self.sigma_start - _EPSILON or sigma > self.sigma_end + _EPSILON:
            raise ValueError("sigma must stay within the joint segment interval")
        duration = self.sigma_end - self.sigma_start
        local = 0.0 if math.isclose(duration, 0.0, abs_tol=_EPSILON) else (sigma - self.sigma_start) / duration
        return tuple(
            sum(coefficient[axis_index] * local**power for power, coefficient in enumerate(self.coefficients))
            for axis_index in range(5)
        )


class KinematicsCertificate(AxiomModel):
    certificate_id: str = Field(alias="certificateId", min_length=1, pattern=_ID_PATTERN)
    machine_profile_id: str = Field(alias="machineProfileId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    machine_profile_content_id: str = Field(alias="machineProfileContentId", pattern=_CONTENT_HASH_PATTERN)
    source_candidate_geometry_id: str = Field(alias="sourceCandidateGeometryId", min_length=1, pattern=_ID_PATTERN)
    source_candidate_geometry_content_id: str = Field(alias="sourceCandidateGeometryContentId", pattern=_CONTENT_HASH_PATTERN)
    branch_graph_id: str = Field(alias="branchGraphId", min_length=1, pattern=_ID_PATTERN)
    solver_id: str = Field(alias="solverId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    solver_version: str = Field(alias="solverVersion", min_length=1)
    evidence_level: Literal["Exact", "Certified", "Validated", "Observed"] = Field(alias="evidenceLevel")
    continuous_method: str = Field(alias="continuousMethod", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    claim_scope: Literal["selected-continuous-lift"] = Field(alias="claimScope")
    selected_branch_id: str = Field(alias="selectedBranchId", min_length=1, pattern=_ID_PATTERN)
    interval_count: int = Field(alias="intervalCount", ge=1)
    position_residual_upper_bound: float = Field(alias="positionResidualUpperBound", ge=0.0)
    orientation_residual_upper_bound: float = Field(alias="orientationResidualUpperBound", ge=0.0)
    axis_limit_normalized_margin_lower_bound: float = Field(
        alias="axisLimitNormalizedMarginLowerBound",
        ge=0.0,
        le=0.5,
    )
    minimum_singular_value_lower_bound: float = Field(alias="minimumSingularValueLowerBound", ge=0.0)
    singularity_handling: Literal["regular-only", "explicit-free-family"] = Field(alias="singularityHandling")
    policy_ids: tuple[str, ...] = Field(alias="policyIds", min_length=1)
    numeric_environment: dict[str, str] = Field(alias="numericEnvironment", min_length=1)
    position_tolerance: ToleranceBinding = Field(alias="positionTolerance")
    orientation_tolerance: ToleranceBinding = Field(alias="orientationTolerance")
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_expected_targets(self) -> "KinematicsCertificate":
        if self.position_tolerance.target != "position":
            raise ValueError("positionTolerance must target position")
        if self.orientation_tolerance.target != "orientation":
            raise ValueError("orientationTolerance must target orientation")
        if self.position_residual_upper_bound > self.position_tolerance.tolerance.absolute + _EPSILON:
            raise ValueError("positionResidualUpperBound must satisfy positionTolerance")
        if self.orientation_residual_upper_bound > self.orientation_tolerance.tolerance.absolute + _EPSILON:
            raise ValueError("orientationResidualUpperBound must satisfy orientationTolerance")
        if len(self.policy_ids) != len(set(self.policy_ids)):
            raise ValueError("policyIds must not contain duplicates")
        if any(re.fullmatch(_VERSIONED_ID_PATTERN, policy_id) is None for policy_id in self.policy_ids):
            raise ValueError("policyIds must contain versioned identifiers")
        return self


class ArtifactDescriptor(AxiomModel):
    stage: Literal["M0", "M1", "M2", "M3"]
    artifact_type: str = Field(alias="artifactType", min_length=1)
    schema_id: str = Field(alias="schemaId", min_length=1, pattern=_VERSIONED_ID_PATTERN)

    @model_validator(mode="after")
    def require_frozen_descriptor(self) -> "ArtifactDescriptor":
        expected = {
            "M0": ("five-axis.normalized-program", "five-axis.normalized-program@1"),
            "M1": ("five-axis.m1-reference-path", "five-axis.m1-reference-path@1"),
            "M2": ("five-axis.m2-candidate-task-geometry", "five-axis.m2-candidate-task-geometry@1"),
            "M3": ("five-axis.m3-candidate-axis-path", "five-axis.m3-candidate-axis-path@1"),
        }[self.stage]
        if (self.artifact_type, self.schema_id) != expected:
            raise ValueError("ArtifactDescriptor must use the frozen F2 artifact/schema mapping")
        return self


class ExpectedClaim(AxiomModel):
    claim_id: str = Field(alias="claimId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    claim_class: Literal["M0", "M1", "M2", "M3", "M4", "M5", "DeviceSafe"] = Field(alias="claimClass")
    expected_status: Literal["Supported", "Refuted", "Inconclusive", "Unsupported", "Insufficient"] = Field(
        alias="expectedStatus"
    )
    evidence_level: str | None = Field(default=None, alias="evidenceLevel")

    @model_validator(mode="after")
    def reject_forbidden_positive_claim(self) -> "ExpectedClaim":
        if self.expected_status == "Supported":
            if self.claim_class in {"M4", "M5", "DeviceSafe"}:
                raise ValueError("F2MathStageManifest must not publish positive M4/M5/DeviceSafe claims")
            if self.claim_class == "M3" and self.claim_id not in {
                "five-axis.kinematically-feasible-claim@1",
                "five-axis.configuration-collision-free-claim@1",
            }:
                raise ValueError("F2 positive M3 claims must use the frozen whitelist IDs")
        return self


class ExpectedEvidence(AxiomModel):
    evidence_id: str = Field(alias="evidenceId", min_length=1, pattern=_ID_PATTERN)
    evidence_kind: Literal[
        "lineage",
        "regularity",
        "correspondence",
        "ik-branch",
        "wrap",
        "kinematics",
        "configuration-collision",
        "singularity",
    ] = Field(alias="evidenceKind")
    required: bool


class M3CandidateAxisPath(AxiomModel):
    artifact_type: Literal["five-axis.m3-candidate-axis-path"] = Field(alias="artifactType")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    axis_path_id: str = Field(alias="axisPathId", min_length=1, pattern=_ID_PATTERN)
    source_candidate_geometry: M2CandidateTaskGeometry = Field(alias="sourceCandidateGeometry")
    source_candidate_geometry_content_id: str = Field(alias="sourceCandidateGeometryContentId", pattern=_CONTENT_HASH_PATTERN)
    machine_profile: MachineProfile = Field(alias="machineProfile")
    machine_profile_content_id: str = Field(alias="machineProfileContentId", pattern=_CONTENT_HASH_PATTERN)
    path_progress: PathProgress = Field(alias="pathProgress")
    ik_solutions: tuple[IKSolution, ...] = Field(alias="ikSolutions", min_length=1)
    branch_graph: BranchGraph = Field(alias="branchGraph")
    joint_segments: tuple[JointPolynomialSegment, ...] = Field(alias="jointSegments", min_length=1)
    node_events: tuple[NodeEvent, ...] = Field(alias="nodeEvents", default_factory=tuple)
    regularity_certificate: RegularityCertificate = Field(alias="regularityCertificate")
    kinematics_certificate: KinematicsCertificate = Field(alias="kinematicsCertificate")
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_bound_kinematics(self) -> "M3CandidateAxisPath":
        _require_unique_ids(self.ik_solutions, attr="solution_id", field_name="ikSolutions")
        _require_unique_ids(self.joint_segments, attr="segment_id", field_name="jointSegments")
        _require_unique_ids(self.node_events, attr="node_id", field_name="nodeEvents")
        _validate_interval_coverage(self.joint_segments, start_attr="sigma_start", end_attr="sigma_end", field_name="jointSegments")
        segment_ids = {segment.segment_id for segment in self.joint_segments}
        branch_ids = {branch.branch_id for branch in self.branch_graph.branches}
        if any(mapping.source_segment_id not in segment_ids for mapping in self.path_progress.mappings):
            raise ValueError("pathProgress mappings must target actual jointSegments")
        if {mapping.source_segment_id for mapping in self.path_progress.mappings} != segment_ids:
            raise ValueError("pathProgress mappings must cover every jointSegment")
        if any(segment.branch_id not in branch_ids for segment in self.joint_segments):
            raise ValueError("jointSegments branchId must reference branchGraph branches")
        if any(solution.branch_id not in branch_ids for solution in self.ik_solutions):
            raise ValueError("ikSolutions branchId must reference branchGraph branches")
        if any(event.left_segment_id is not None and event.left_segment_id not in segment_ids for event in self.node_events):
            raise ValueError("nodeEvents leftSegmentId must target actual jointSegments")
        if any(event.right_segment_id is not None and event.right_segment_id not in segment_ids for event in self.node_events):
            raise ValueError("nodeEvents rightSegmentId must target actual jointSegments")
        solution_by_id = {solution.solution_id: solution for solution in self.ik_solutions}
        axis_ids = {axis.axis_id for axis in self.machine_profile.axes}
        rotary_axis_ids = {axis.axis_id for axis in self.machine_profile.axes if axis.joint_type == "revolute"}
        expected_axis_count = len(self.machine_profile.axes)
        for solution in self.ik_solutions:
            if len(solution.joint_values) != expected_axis_count:
                raise ValueError("ikSolutions jointValues must match the MachineProfile axis count")
            wrap_axis_ids = {item.axis_id for item in solution.wrap_state}
            if not wrap_axis_ids.issubset(rotary_axis_ids):
                raise ValueError("wrapState may only reference revolute MachineProfile axes")
            periodic_axis_ids = {axis.axis_id for axis in self.machine_profile.axes if axis.periodic}
            if not wrap_axis_ids.issubset(periodic_axis_ids):
                raise ValueError("wrapState may only reference periodic MachineProfile axes")
            free_axis_ids = {item.axis_id for item in solution.free_parameters}
            if not free_axis_ids.issubset(rotary_axis_ids):
                raise ValueError("freeParameters may only reference revolute MachineProfile axes")
            observed_axis_ids = {item.axis_id for item in solution.axis_limit_state}
            if observed_axis_ids != axis_ids:
                raise ValueError("axisLimitState must cover every MachineProfile axis exactly once")
        for segment in self.joint_segments:
            start_solution = solution_by_id.get(segment.start_solution_id)
            end_solution = solution_by_id.get(segment.end_solution_id)
            if start_solution is None or end_solution is None:
                raise ValueError("jointSegments must reference actual ikSolutions")
            if start_solution.branch_id != segment.branch_id or end_solution.branch_id != segment.branch_id:
                raise ValueError("jointSegments and their endpoint ikSolutions must stay on one branchId")
            if not math.isclose(start_solution.sigma, segment.sigma_start, abs_tol=_EPSILON):
                raise ValueError("startSolutionId sigma must match jointSegment sigmaStart")
            if not math.isclose(end_solution.sigma, segment.sigma_end, abs_tol=_EPSILON):
                raise ValueError("endSolutionId sigma must match jointSegment sigmaEnd")
            if any(
                not math.isclose(actual, expected, abs_tol=_EPSILON)
                for actual, expected in zip(segment.evaluate(segment.sigma_start), start_solution.joint_values, strict=True)
            ):
                raise ValueError("jointSegment coefficients must reproduce startSolutionId jointValues")
            if any(
                not math.isclose(actual, expected, abs_tol=_EPSILON)
                for actual, expected in zip(segment.evaluate(segment.sigma_end), end_solution.joint_values, strict=True)
            ):
                raise ValueError("jointSegment coefficients must reproduce endSolutionId jointValues")
        for branch in self.branch_graph.branches:
            branch_solutions: list[IKSolution] = []
            for solution_id in branch.solution_ids:
                resolved_solution = solution_by_id.get(solution_id)
                if resolved_solution is None:
                    raise ValueError("branchGraph solutionIds must reference actual ikSolutions")
                if resolved_solution.branch_id != branch.branch_id:
                    raise ValueError("branchGraph solutionIds must stay within their branchId")
                if not (branch.sigma_start - _EPSILON <= resolved_solution.sigma <= branch.sigma_end + _EPSILON):
                    raise ValueError("branchGraph solutions must stay within the branch sigma interval")
                branch_solutions.append(resolved_solution)
            if not any(math.isclose(item.sigma, branch.sigma_start, abs_tol=_EPSILON) for item in branch_solutions):
                raise ValueError("each branch must contain an IK solution at sigmaStart")
            if not any(math.isclose(item.sigma, branch.sigma_end, abs_tol=_EPSILON) for item in branch_solutions):
                raise ValueError("each branch must contain an IK solution at sigmaEnd")
        regularity_segment_ids = {item.segment_id for item in self.regularity_certificate.segment_evidence}
        if regularity_segment_ids != segment_ids:
            raise ValueError("regularityCertificate segmentEvidence must cover every jointSegment")
        node_ids = {event.node_id for event in self.node_events}
        regularity_node_ids = {item.node_id for item in self.regularity_certificate.node_evidence}
        if regularity_node_ids != node_ids:
            raise ValueError("regularityCertificate nodeEvidence must cover every nodeEvent")
        if self.kinematics_certificate.machine_profile_id != self.machine_profile.profile_id:
            raise ValueError("kinematicsCertificate machineProfileId must match machineProfile profileId")
        if self.kinematics_certificate.machine_profile_content_id != self.machine_profile_content_id:
            raise ValueError("kinematicsCertificate machineProfileContentId must match M3 machineProfileContentId")
        if self.kinematics_certificate.source_candidate_geometry_id != self.source_candidate_geometry.candidate_geometry_id:
            raise ValueError("kinematicsCertificate sourceCandidateGeometryId must match sourceCandidateGeometry candidateGeometryId")
        if self.kinematics_certificate.source_candidate_geometry_content_id != self.source_candidate_geometry_content_id:
            raise ValueError(
                "kinematicsCertificate sourceCandidateGeometryContentId must match M3 sourceCandidateGeometryContentId"
            )
        if self.kinematics_certificate.branch_graph_id != self.branch_graph.graph_id:
            raise ValueError("kinematicsCertificate branchGraphId must match branchGraph graphId")
        if self.kinematics_certificate.selected_branch_id not in branch_ids:
            raise ValueError("kinematicsCertificate selectedBranchId must reference branchGraph")
        selected_segment_ids = {
            segment.segment_id
            for segment in self.joint_segments
            if segment.branch_id == self.kinematics_certificate.selected_branch_id
        }
        if selected_segment_ids != segment_ids:
            raise ValueError("all jointSegments must belong to the kinematicsCertificate selectedBranchId")
        if self.kinematics_certificate.interval_count != len(self.joint_segments):
            raise ValueError("kinematicsCertificate intervalCount must match jointSegments")
        return self


class F2MathStageManifest(AxiomModel):
    manifest_id: Literal["five-axis.f2-math-stage-manifest@1"] = Field(alias="manifestId")
    schema_id: Literal["five-axis.f2-math-stage-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["F2"]
    artifact_descriptors: tuple[ArtifactDescriptor, ...] = Field(alias="artifactDescriptors", min_length=4)
    machine_profile_schema_id: Literal["five-axis.machine-profile@1"] = Field(alias="machineProfileSchemaId")
    machine_profile_id: str = Field(alias="machineProfileId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    machine_profile_content_id: str = Field(alias="machineProfileContentId", pattern=_CONTENT_HASH_PATTERN)
    capability_ids: tuple[str, ...] = Field(alias="capabilityIds", min_length=1)
    fixture_content_ids: tuple[str, ...] = Field(alias="fixtureContentIds", min_length=1)
    policy_ids: tuple[str, ...] = Field(alias="policyIds", min_length=1)
    numeric_environment: dict[str, str] = Field(alias="numericEnvironment", min_length=1)
    expected_metrics: tuple[ExpectedMetric, ...] = Field(alias="expectedMetrics", min_length=1)
    expected_claims: tuple[ExpectedClaim, ...] = Field(alias="expectedClaims", min_length=1)
    expected_evidence: tuple[ExpectedEvidence, ...] = Field(alias="expectedEvidence", min_length=1)
    tolerances: tuple[ToleranceBinding, ...] = Field(min_length=1)
    decisions: tuple[StageDecision, ...] = Field(min_length=1)

    @field_validator("capability_ids", "policy_ids")
    @classmethod
    def require_unique_versioned_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("IDs must not contain duplicates")
        for item in value:
            if re.fullmatch(_VERSIONED_ID_PATTERN, item) is None:
                raise ValueError("IDs must be versioned identifiers")
        return value

    @field_validator("fixture_content_ids")
    @classmethod
    def require_unique_fixture_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("fixtureContentIds must not contain duplicates")
        for item in value:
            if re.fullmatch(_CONTENT_HASH_PATTERN, item) is None:
                raise ValueError("fixtureContentIds must contain content hashes")
        return value

    @model_validator(mode="after")
    def require_frozen_manifest_sets(self) -> "F2MathStageManifest":
        _require_unique_ids(self.artifact_descriptors, attr="stage", field_name="artifactDescriptors")
        _require_unique_ids(self.expected_metrics, attr="metric_id", field_name="expectedMetrics")
        _require_unique_ids(self.expected_claims, attr="claim_id", field_name="expectedClaims")
        _require_unique_ids(self.expected_evidence, attr="evidence_id", field_name="expectedEvidence")
        _require_unique_ids(self.tolerances, attr="tolerance_id", field_name="tolerances")
        _require_unique_ids(self.decisions, attr="decision_id", field_name="decisions")
        if tuple(descriptor.stage for descriptor in self.artifact_descriptors) != ("M0", "M1", "M2", "M3"):
            raise ValueError("artifactDescriptors must freeze M0, M1, M2, M3 in order")
        return self


__all__ = [
    "ArtifactDescriptor",
    "AxisLimitObservation",
    "AxisLimits",
    "AxisWrapState",
    "BranchGraph",
    "BranchNode",
    "BranchTransition",
    "ContinuousJointSegment",
    "ExpectedClaim",
    "ExpectedEvidence",
    "F2MathStageManifest",
    "FreeAxisParameter",
    "IKSolution",
    "JointPolynomialSegment",
    "KinematicResidual",
    "KinematicsCertificate",
    "M3CandidateAxisPath",
    "MachineAxis",
    "MachineProfile",
    "RigidTransform",
    "SingularityIndicator",
]

ContinuousJointSegment = JointPolynomialSegment
