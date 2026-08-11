from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, cast

import numpy as np
from pydantic import Field, field_validator, model_validator

from ..evaluator import _content_hash
from ..models import AxiomModel
from .f1_collision import _box_distance
from .f1_models import AxisAlignedBoundingBox, NumericTolerance, ProvenanceRef, ToleranceBinding
from .f2_kinematics import normalize_numeric_identity
from .f2_models import JointPolynomialSegment, M3CandidateAxisPath, MachineAxis, MachineProfile


_EPSILON = 1e-12
_MIN_SIGMA_SPAN = 1e-5
_MAX_SUBDIVISION_DEPTH = 18
_SUPPORTED_INTERPOLATIONS = frozenset({"linear", "cubic-hermite"})
_SUPPORTED_POLYNOMIAL_ROWS = frozenset({2, 4, 8})
_SUPPORTED_CLAIM_ID = "five-axis.configuration-collision-free-claim@1"
_FORBIDDEN_CLAIM_IDS = (
    "five-axis.model-collision-free-claim@1",
    "five-axis.device-safe-claim@1",
)

Matrix3 = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
Vector3 = tuple[float, float, float]
Transform3 = tuple[Matrix3, Vector3]
_EvidenceLevel = Literal["Certified", "Validated", "Observed"]
_PairKind = Literal["machine-self", "environment"]
_PairStatus = Literal["safe", "collision", "unsupported", "not-applicable", "unresolved"]
_OverallStatus = Literal["safe", "collision", "unsupported", "not-applicable", "unresolved"]
_CertificateKind = Literal["proof", "counterexample", "point-check", "none"]


def _identity_matrix() -> Matrix3:
    return (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )


def _dot3(left: Vector3, right: Vector3) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _add3(left: Vector3, right: Vector3) -> Vector3:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def _sub3(left: Vector3, right: Vector3) -> Vector3:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _scale3(vector: Vector3, scalar: float) -> Vector3:
    return (vector[0] * scalar, vector[1] * scalar, vector[2] * scalar)


def _cross3(left: Vector3, right: Vector3) -> Vector3:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _norm3(vector: Vector3) -> float:
    return math.sqrt(_dot3(vector, vector))


def _normalize3(vector: Vector3) -> Vector3:
    norm = _norm3(vector)
    if math.isclose(norm, 0.0, abs_tol=_EPSILON):
        raise ValueError("zero vector cannot be normalized")
    return (vector[0] / norm, vector[1] / norm, vector[2] / norm)


def _mat_vec(matrix: Matrix3, vector: Vector3) -> Vector3:
    return (
        _dot3(matrix[0], vector),
        _dot3(matrix[1], vector),
        _dot3(matrix[2], vector),
    )


def _mat_mul(left: Matrix3, right: Matrix3) -> Matrix3:
    columns = tuple(zip(*right))
    return tuple(tuple(_dot3(row, column) for column in columns) for row in left)  # type: ignore[return-value]


def _compose(left: Transform3, right: Transform3) -> Transform3:
    left_rotation, left_translation = left
    right_rotation, right_translation = right
    return (
        _mat_mul(left_rotation, right_rotation),
        _add3(_mat_vec(left_rotation, right_translation), left_translation),
    )


def _apply_transform(transform: Transform3, point: Vector3) -> Vector3:
    rotation, translation = transform
    return _add3(_mat_vec(rotation, point), translation)


def _quaternion_to_matrix(quaternion: tuple[float, float, float, float]) -> Matrix3:
    x, y, z, w = quaternion
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z
    return (
        (1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)),
        (2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)),
        (2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)),
    )


def _rotation_about_axis(direction: Vector3, angle_rad: float) -> Matrix3:
    axis = _normalize3(direction)
    x, y, z = axis
    cosine = math.cos(angle_rad)
    sine = math.sin(angle_rad)
    one_minus_cos = 1.0 - cosine
    return (
        (
            cosine + x * x * one_minus_cos,
            x * y * one_minus_cos - z * sine,
            x * z * one_minus_cos + y * sine,
        ),
        (
            y * x * one_minus_cos + z * sine,
            cosine + y * y * one_minus_cos,
            y * z * one_minus_cos - x * sine,
        ),
        (
            z * x * one_minus_cos - y * sine,
            z * y * one_minus_cos + x * sine,
            cosine + z * z * one_minus_cos,
        ),
    )


def _transform_from_rotation_about_line(origin: Vector3, direction: Vector3, angle_rad: float) -> Transform3:
    rotation = _rotation_about_axis(direction, angle_rad)
    translation = _sub3(origin, _mat_vec(rotation, origin))
    return (rotation, translation)


def _transform_from_frame(frame: Any) -> Transform3:
    return (_quaternion_to_matrix(tuple(frame.rotation_quaternion)), tuple(frame.translation))


def _axis_displacement(axis: MachineAxis, joint_value: float) -> float:
    signed = joint_value - axis.zero_position
    if axis.sign == "negative":
        signed = -signed
    if axis.joint_type == "revolute" and axis.limits.unit == "deg":
        return math.radians(signed)
    return signed


def _canonical_aabb(box: AxisAlignedBoundingBox) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return (cast(Vector3, tuple(box.min_corner)), cast(Vector3, tuple(box.max_corner)))


def _union_boxes(boxes: Sequence[AxisAlignedBoundingBox]) -> AxisAlignedBoundingBox:
    min_corner = cast(Vector3, tuple(min(box.min_corner[index] for box in boxes) for index in range(3)))
    max_corner = cast(Vector3, tuple(max(box.max_corner[index] for box in boxes) for index in range(3)))
    return AxisAlignedBoundingBox(minCorner=min_corner, maxCorner=max_corner)


class CollisionTolerance(AxiomModel):
    absolute: float = Field(ge=0.0)
    unit: Literal["mm"]

    @field_validator("absolute", mode="before")
    @classmethod
    def require_finite_value(cls, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("absolute must be a finite JSON number")
        return value


class CollisionEntity(AxiomModel):
    entity_id: str = Field(alias="entityId", min_length=1)
    entity_kind: Literal["machine-component", "environment"] = Field(alias="entityKind")
    anchor_type: Literal["base", "axis", "tool-mount-frame", "workpiece-frame"] = Field(alias="anchorType")
    anchor_axis_id: str | None = Field(default=None, alias="anchorAxisId")
    local_aabb: AxisAlignedBoundingBox = Field(alias="localAabb")
    active_branch_ids: tuple[str, ...] = Field(default_factory=tuple, alias="activeBranchIds")

    @model_validator(mode="after")
    def require_axis_anchor(self) -> "CollisionEntity":
        if self.anchor_type == "axis" and self.anchor_axis_id is None:
            raise ValueError("anchorAxisId is required when anchorType=axis")
        if self.anchor_type != "axis" and self.anchor_axis_id is not None:
            raise ValueError("anchorAxisId is only allowed when anchorType=axis")
        return self


class CollisionPair(AxiomModel):
    pair_id: str = Field(alias="pairId", min_length=1)
    pair_kind: _PairKind = Field(alias="pairKind")
    left_entity_id: str = Field(alias="leftEntityId", min_length=1)
    right_entity_id: str = Field(alias="rightEntityId", min_length=1)
    active_branch_ids: tuple[str, ...] = Field(default_factory=tuple, alias="activeBranchIds")
    minimum_clearance: CollisionTolerance | None = Field(default=None, alias="minimumClearance")


class ConfigurationCollisionModel(AxiomModel):
    model_id: str = Field(alias="modelId", min_length=1)
    content_id: str | None = Field(default=None, alias="contentId")
    machine_profile_id: str = Field(alias="machineProfileId", min_length=1)
    machine_profile_content_id: str = Field(alias="machineProfileContentId", pattern=r"^[0-9a-f]{64}$")
    policy_id: str = Field(default="five-axis.configuration-collision.explicit-pairs@1", alias="policyId", min_length=1)
    coverage_status: Literal["complete", "partial"] = Field(alias="coverageStatus")
    covered_pair_kinds: tuple[_PairKind, ...] = Field(alias="coveredPairKinds", min_length=1)
    minimum_clearance: CollisionTolerance = Field(alias="minimumClearance")
    solver_tolerance: CollisionTolerance = Field(alias="solverTolerance")
    entities: tuple[CollisionEntity, ...] = Field(min_length=1)
    pairs: tuple[CollisionPair, ...] = Field(min_length=1)
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_matching_entity_references(self) -> "ConfigurationCollisionModel":
        entity_ids = {entity.entity_id for entity in self.entities}
        if len(entity_ids) != len(self.entities):
            raise ValueError("entities must not contain duplicate entityId")
        pair_ids = {pair.pair_id for pair in self.pairs}
        if len(pair_ids) != len(self.pairs):
            raise ValueError("pairs must not contain duplicate pairId")
        entities_by_id = {entity.entity_id: entity for entity in self.entities}
        if len(self.covered_pair_kinds) != len(set(self.covered_pair_kinds)):
            raise ValueError("coveredPairKinds must not contain duplicates")
        actual_pair_kinds = {pair.pair_kind for pair in self.pairs}
        if not actual_pair_kinds.issubset(set(self.covered_pair_kinds)):
            raise ValueError("every collision pair kind must be declared in coveredPairKinds")
        if self.coverage_status == "complete" and set(self.covered_pair_kinds) != {"machine-self", "environment"}:
            raise ValueError("complete collision coverage requires machine-self and environment pair kinds")
        if self.coverage_status == "complete" and actual_pair_kinds != set(self.covered_pair_kinds):
            raise ValueError("complete collision coverage requires at least one pair for every coveredPairKind")
        for pair in self.pairs:
            if pair.left_entity_id not in entity_ids or pair.right_entity_id not in entity_ids:
                raise ValueError("pairs must reference declared entities")
            if pair.left_entity_id == pair.right_entity_id:
                raise ValueError("collision pairs must reference two distinct entities")
            kinds = {entities_by_id[pair.left_entity_id].entity_kind, entities_by_id[pair.right_entity_id].entity_kind}
            if pair.pair_kind == "machine-self" and kinds != {"machine-component"}:
                raise ValueError("machine-self pairs require two machine-component entities")
            if pair.pair_kind == "environment" and "environment" not in kinds:
                raise ValueError("environment pairs require an environment entity")
        return self


class ConfigurationCollisionPairResult(AxiomModel):
    pair_id: str = Field(alias="pairId")
    pair_kind: _PairKind = Field(alias="pairKind")
    status: _PairStatus
    reason_code: str = Field(alias="reasonCode")
    left_entity_id: str = Field(alias="leftEntityId")
    right_entity_id: str = Field(alias="rightEntityId")
    minimum_clearance_lower_bound: float | None = Field(default=None, alias="minimumClearanceLowerBound")
    witness_sigma: float | None = Field(default=None, alias="witnessSigma")


class ConfigurationCollisionEvaluation(AxiomModel):
    query_kind: Literal["point", "segment", "path"] = Field(alias="queryKind")
    status: _OverallStatus
    collision_free: bool | None = Field(alias="collisionFree")
    certificate_kind: _CertificateKind = Field(alias="certificateKind")
    claim_id: str | None = Field(default=None, alias="claimId")
    forbidden_claim_ids: tuple[str, ...] = Field(alias="forbiddenClaimIds")
    reason_code: str = Field(alias="reasonCode")
    evidence_level: _EvidenceLevel = Field(alias="evidenceLevel")
    machine_profile_id: str = Field(alias="machineProfileId")
    machine_profile_content_id: str = Field(alias="machineProfileContentId")
    axis_path_id: str = Field(alias="axisPathId")
    axis_path_content_id: str = Field(alias="axisPathContentId", pattern=r"^[0-9a-f]{64}$")
    collision_model_id: str = Field(alias="collisionModelId")
    collision_model_content_id: str = Field(alias="collisionModelContentId")
    branch_id: str | None = Field(default=None, alias="branchId")
    segment_id: str | None = Field(default=None, alias="segmentId")
    sigma_start: float = Field(alias="sigmaStart")
    sigma_end: float = Field(alias="sigmaEnd")
    minimum_clearance_lower_bound: float | None = Field(default=None, alias="minimumClearanceLowerBound")
    clearance_unit: str = Field(alias="clearanceUnit")
    policy_id: str = Field(alias="policyId")
    tolerance: ToleranceBinding = Field(alias="tolerance")
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)
    continuous_method: str = Field(alias="continuousMethod")
    evaluation_count: int = Field(alias="evaluationCount")
    subdivision_count: int = Field(alias="subdivisionCount")
    pair_results: tuple[ConfigurationCollisionPairResult, ...] = Field(alias="pairResults")


class PolynomialCollisionPairResult(AxiomModel):
    pair_id: str = Field(alias="pairId")
    pair_kind: _PairKind = Field(alias="pairKind")
    status: _PairStatus
    reason_code: str = Field(alias="reasonCode")
    left_entity_id: str = Field(alias="leftEntityId")
    right_entity_id: str = Field(alias="rightEntityId")
    minimum_clearance_lower_bound: float | None = Field(default=None, alias="minimumClearanceLowerBound")
    witness_parameter: float | None = Field(default=None, alias="witnessParameter")


class PolynomialCollisionIntervalEvaluation(AxiomModel):
    interval_id: str = Field(alias="intervalId")
    parameter_name: Literal["normalized-local", "time"] = Field(alias="parameterName")
    parameter_start: float = Field(alias="parameterStart")
    parameter_end: float = Field(alias="parameterEnd")
    status: _OverallStatus
    collision_free: bool | None = Field(alias="collisionFree")
    certificate_kind: _CertificateKind = Field(alias="certificateKind")
    reason_code: str = Field(alias="reasonCode")
    evidence_level: _EvidenceLevel = Field(alias="evidenceLevel")
    machine_profile_id: str = Field(alias="machineProfileId")
    machine_profile_content_id: str = Field(alias="machineProfileContentId")
    source_axis_path_id: str = Field(alias="sourceAxisPathId")
    source_axis_path_content_id: str = Field(alias="sourceAxisPathContentId", pattern=r"^[0-9a-f]{64}$")
    collision_model_id: str = Field(alias="collisionModelId")
    collision_model_content_id: str = Field(alias="collisionModelContentId")
    branch_id: str = Field(alias="branchId")
    minimum_clearance_lower_bound: float | None = Field(default=None, alias="minimumClearanceLowerBound")
    clearance_unit: str = Field(alias="clearanceUnit")
    policy_id: str = Field(alias="policyId")
    continuous_method: Literal["five-axis.configuration-polynomial-envelope-recursive@1"] = Field(
        alias="continuousMethod"
    )
    evaluation_count: int = Field(alias="evaluationCount")
    subdivision_count: int = Field(alias="subdivisionCount")
    pair_results: tuple[PolynomialCollisionPairResult, ...] = Field(alias="pairResults")


@dataclass(frozen=True)
class _PairResolution:
    status: _PairStatus
    minimum_clearance_lower_bound: float | None
    reason_code: str
    witness_sigma: float | None = None
    evaluations: int = 0
    subdivisions: int = 0


@dataclass(frozen=True)
class _PolynomialJointInterval:
    segment_id: str
    branch_id: str
    sigma_start: float
    sigma_end: float
    coefficients: tuple[tuple[float, ...], ...]
    coefficient_basis: str = "local-power@1"


def _hash_collision_model(model: ConfigurationCollisionModel) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude={"content_id"})
    payload = normalize_numeric_identity(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


hash_configuration_collision_model = _hash_collision_model


def _ordered_axes(profile: MachineProfile) -> tuple[MachineAxis, ...]:
    return tuple(sorted(profile.axes, key=lambda axis: axis.axis_order))


def _axis_index_map(profile: MachineProfile) -> dict[str, int]:
    return {axis.axis_id: index for index, axis in enumerate(_ordered_axes(profile))}


def _axis_chain_ids(profile: MachineProfile, axis_id: str) -> tuple[str, ...]:
    axes_by_id = {axis.axis_id: axis for axis in profile.axes}
    chain: list[str] = []
    cursor = axes_by_id[axis_id]
    while True:
        chain.append(cursor.axis_id)
        if cursor.parent_axis_id is None:
            break
        cursor = axes_by_id[cursor.parent_axis_id]
    chain.reverse()
    return tuple(chain)


def _terminal_axis_id(profile: MachineProfile, side: Literal["tool", "workpiece"]) -> str:
    candidates = [axis for axis in _ordered_axes(profile) if axis.installation_side == side]
    if not candidates:
        raise ValueError(f"MachineProfile does not define a {side} anchor chain")
    return candidates[-1].axis_id


def _entity_chain_ids(profile: MachineProfile, entity: CollisionEntity) -> tuple[str, ...]:
    if entity.anchor_type == "base":
        return tuple()
    if entity.anchor_type == "axis":
        assert entity.anchor_axis_id is not None
        return _axis_chain_ids(profile, entity.anchor_axis_id)
    if entity.anchor_type == "tool-mount-frame":
        return _axis_chain_ids(profile, _terminal_axis_id(profile, "tool"))
    return _axis_chain_ids(profile, _terminal_axis_id(profile, "workpiece"))


def _axis_transform(axis: MachineAxis, joint_values: Sequence[float], axis_index: int) -> Transform3:
    origin = cast(Vector3, tuple(axis.origin))
    direction = cast(Vector3, tuple(axis.direction))
    displacement = _axis_displacement(axis, float(joint_values[axis_index]))
    if axis.joint_type == "prismatic":
        return (_identity_matrix(), _scale3(direction, displacement))
    return _transform_from_rotation_about_line(origin, direction, displacement)


def _entity_transform(profile: MachineProfile, entity: CollisionEntity, joint_values: Sequence[float]) -> Transform3:
    axis_indices = _axis_index_map(profile)
    chain_ids = _entity_chain_ids(profile, entity)
    axes_by_id = {axis.axis_id: axis for axis in profile.axes}
    if chain_ids and axes_by_id[chain_ids[0]].installation_side == "workpiece":
        transform = _transform_from_frame(profile.workpiece_frame)
    else:
        transform = (_identity_matrix(), (0.0, 0.0, 0.0))
    for axis_id in chain_ids:
        axis = next(axis for axis in profile.axes if axis.axis_id == axis_id)
        transform = _compose(transform, _axis_transform(axis, joint_values, axis_indices[axis_id]))
    if entity.anchor_type == "tool-mount-frame":
        transform = _compose(transform, _transform_from_frame(profile.tool_mount_frame))
    return transform


def _transform_aabb(box: AxisAlignedBoundingBox, transform: Transform3) -> AxisAlignedBoundingBox:
    x0, y0, z0 = box.min_corner
    x1, y1, z1 = box.max_corner
    corners = (
        (x0, y0, z0),
        (x0, y0, z1),
        (x0, y1, z0),
        (x0, y1, z1),
        (x1, y0, z0),
        (x1, y0, z1),
        (x1, y1, z0),
        (x1, y1, z1),
    )
    transformed = [_apply_transform(transform, corner) for corner in corners]
    min_corner = cast(Vector3, tuple(min(point[index] for point in transformed) for index in range(3)))
    max_corner = cast(Vector3, tuple(max(point[index] for point in transformed) for index in range(3)))
    return AxisAlignedBoundingBox(minCorner=min_corner, maxCorner=max_corner)


def _entity_box_at_q(profile: MachineProfile, entity: CollisionEntity, joint_values: Sequence[float]) -> AxisAlignedBoundingBox:
    return _transform_aabb(entity.local_aabb, _entity_transform(profile, entity, joint_values))


def _segment_coefficients(segment: JointPolynomialSegment | _PolynomialJointInterval) -> np.ndarray:
    coefficient_basis = getattr(segment, "coefficient_basis", None) or getattr(segment, "coefficientBasis", None) or "local-power@1"
    if coefficient_basis != "local-power@1":
        raise ValueError(f"UnsupportedCoefficientBasis:{coefficient_basis}")
    rows = np.asarray(segment.coefficients, dtype=float)
    if isinstance(segment, _PolynomialJointInterval):
        if rows.ndim != 2 or rows.shape[0] not in _SUPPORTED_POLYNOMIAL_ROWS or rows.shape[1] != 5:
            raise ValueError("InvalidCoefficientShape:local-power")
        if not np.isfinite(rows).all():
            raise ValueError("NonFinitePolynomialCoefficient")
        return rows
    expected_rows = 2 if segment.interpolation == "linear" else 4 if segment.interpolation == "cubic-hermite" else None
    if segment.interpolation not in _SUPPORTED_INTERPOLATIONS or expected_rows is None:
        raise ValueError(f"UnsupportedInterpolation:{segment.interpolation}")
    if rows.shape != (expected_rows, 5):
        raise ValueError(f"InvalidCoefficientShape:{segment.interpolation}")
    return rows


def _local_tau(segment: JointPolynomialSegment | _PolynomialJointInterval, sigma: float) -> float:
    span = segment.sigma_end - segment.sigma_start
    if span <= _EPSILON:
        return 0.0
    return (sigma - segment.sigma_start) / span


def _evaluate_segment(segment: JointPolynomialSegment | _PolynomialJointInterval, sigma: float) -> tuple[float, ...]:
    if hasattr(segment, "evaluate"):
        evaluated = segment.evaluate(sigma)
        return tuple(float(value) for value in evaluated)
    tau = _local_tau(segment, sigma)
    coefficients = _segment_coefficients(segment)
    values = np.zeros(5, dtype=float)
    power = 1.0
    for coefficient in coefficients:
        values += coefficient * power
        power *= tau
    return tuple(float(value) for value in values)


def _polynomial_extrema(coefficients: np.ndarray, tau_start: float, tau_end: float) -> tuple[float, float]:
    candidates = [tau_start, tau_end]
    derivative = np.polynomial.polynomial.polyder(coefficients)
    if derivative.size > 1 or not math.isclose(float(derivative[0]), 0.0, abs_tol=_EPSILON):
        for root in np.polynomial.polynomial.polyroots(derivative):
            if abs(root.imag) > 1e-9:
                continue
            tau = float(root.real)
            if tau_start - _EPSILON <= tau <= tau_end + _EPSILON:
                candidates.append(min(tau_end, max(tau_start, tau)))
    values = [float(np.polynomial.polynomial.polyval(tau, coefficients)) for tau in candidates]
    return (min(values), max(values))


def _joint_bounds(
    segment: JointPolynomialSegment | _PolynomialJointInterval,
    sigma_start: float,
    sigma_end: float,
) -> tuple[tuple[float, float], ...]:
    tau_start = _local_tau(segment, sigma_start)
    tau_end = _local_tau(segment, sigma_end)
    local_start, local_end = sorted((tau_start, tau_end))
    coefficients = _segment_coefficients(segment)
    bounds: list[tuple[float, float]] = []
    for axis_index in range(coefficients.shape[1]):
        bounds.append(_polynomial_extrema(coefficients[:, axis_index], local_start, local_end))
    return tuple(bounds)


def _branch_segment(
    axis_path: M3CandidateAxisPath,
    *,
    segment_id: str | None = None,
    sigma: float | None = None,
    branch_id: str | None = None,
) -> JointPolynomialSegment:
    segments = list(axis_path.joint_segments)
    if segment_id is not None:
        matches = [segment for segment in segments if segment.segment_id == segment_id]
    elif sigma is not None:
        matches = [
            segment
            for segment in segments
            if segment.sigma_start - _EPSILON <= sigma <= segment.sigma_end + _EPSILON
            and (branch_id is None or segment.branch_id == branch_id)
        ]
    else:
        raise ValueError("segmentId or sigma is required")
    if not matches:
        raise ValueError("NoMatchingJointSegment")
    if len(matches) > 1:
        ordered = sorted(matches, key=lambda item: (item.branch_id, item.segment_id))
        if segment_id is None and branch_id is None and len({item.branch_id for item in ordered}) > 1:
            raise ValueError("BranchSelectionRequired")
        return ordered[0]
    return matches[0]


def _pair_threshold(model: ConfigurationCollisionModel, pair: CollisionPair) -> float:
    pair_clearance = pair.minimum_clearance.absolute if pair.minimum_clearance is not None else model.minimum_clearance.absolute
    return pair_clearance + model.solver_tolerance.absolute


def _pair_applicable(pair: CollisionPair, entities: Mapping[str, CollisionEntity], branch_id: str | None) -> bool:
    if branch_id is not None and pair.active_branch_ids and branch_id not in pair.active_branch_ids:
        return False
    left = entities[pair.left_entity_id]
    right = entities[pair.right_entity_id]
    if branch_id is not None and left.active_branch_ids and branch_id not in left.active_branch_ids:
        return False
    if branch_id is not None and right.active_branch_ids and branch_id not in right.active_branch_ids:
        return False
    return True


def _entity_envelope(
    profile: MachineProfile,
    entity: CollisionEntity,
    midpoint_q: Sequence[float],
    joint_bounds: Sequence[tuple[float, float]],
) -> tuple[AxisAlignedBoundingBox | None, str | None]:
    chain_ids = _entity_chain_ids(profile, entity)
    if not chain_ids:
        return (_entity_box_at_q(profile, entity, midpoint_q), None)
    axes_by_id = {axis.axis_id: axis for axis in profile.axes}
    index_map = _axis_index_map(profile)
    variable_prismatic_indices: list[int] = []
    for axis_id in chain_ids:
        axis = axes_by_id[axis_id]
        axis_index = index_map[axis_id]
        lower, upper = joint_bounds[axis_index]
        if axis.joint_type == "revolute" and upper - lower > _EPSILON:
            return (None, "UnsupportedRotaryIntervalMotion")
        if axis.joint_type == "prismatic" and upper - lower > _EPSILON:
            variable_prismatic_indices.append(axis_index)
    boxes: list[AxisAlignedBoundingBox] = []
    corners = tuple(itertools.product((0, 1), repeat=len(variable_prismatic_indices))) or (tuple(),)
    for selector in corners:
        q_values = list(midpoint_q)
        for choice, axis_index in zip(selector, variable_prismatic_indices):
            q_values[axis_index] = joint_bounds[axis_index][choice]
        boxes.append(_entity_box_at_q(profile, entity, q_values))
    return (_union_boxes(boxes), None)


def _pair_clearance_at_q(
    profile: MachineProfile,
    left: CollisionEntity,
    right: CollisionEntity,
    joint_values: Sequence[float],
) -> float:
    return _box_distance(_entity_box_at_q(profile, left, joint_values), _entity_box_at_q(profile, right, joint_values))


def _refine_segment_pair(
    axis_path: M3CandidateAxisPath,
    model: ConfigurationCollisionModel,
    pair: CollisionPair,
    left: CollisionEntity,
    right: CollisionEntity,
    segment: JointPolynomialSegment | _PolynomialJointInterval,
    sigma_start: float,
    sigma_end: float,
    *,
    max_depth: int,
    depth: int = 0,
) -> _PairResolution:
    midpoint_sigma = (sigma_start + sigma_end) * 0.5
    midpoint_q = _evaluate_segment(segment, midpoint_sigma)
    bounds = _joint_bounds(segment, sigma_start, sigma_end)
    left_box, left_reason = _entity_envelope(axis_path.machine_profile, left, midpoint_q, bounds)
    if left_reason is not None:
        return _PairResolution(
            status="unsupported",
            minimum_clearance_lower_bound=None,
            reason_code=left_reason,
        )
    right_box, right_reason = _entity_envelope(axis_path.machine_profile, right, midpoint_q, bounds)
    if right_reason is not None:
        return _PairResolution(
            status="unsupported",
            minimum_clearance_lower_bound=None,
            reason_code=right_reason,
        )
    assert left_box is not None and right_box is not None
    threshold = _pair_threshold(model, pair)
    clearance_lower_bound = _box_distance(left_box, right_box)
    if clearance_lower_bound > threshold + _EPSILON:
        return _PairResolution(
            status="safe",
            minimum_clearance_lower_bound=clearance_lower_bound,
            reason_code="ConfigurationCollisionCertified",
        )
    actual_clearance = _pair_clearance_at_q(axis_path.machine_profile, left, right, midpoint_q)
    if actual_clearance <= threshold + _EPSILON:
        return _PairResolution(
            status="collision",
            minimum_clearance_lower_bound=min(clearance_lower_bound, actual_clearance),
            reason_code="CollisionWitnessFound",
            witness_sigma=midpoint_sigma,
            evaluations=1,
        )
    span = sigma_end - sigma_start
    if depth >= max_depth or span <= _MIN_SIGMA_SPAN:
        return _PairResolution(
            status="unresolved",
            minimum_clearance_lower_bound=max(0.0, clearance_lower_bound),
            reason_code="ClearanceIntervalUnresolved",
            evaluations=1,
        )
    left_result = _refine_segment_pair(
        axis_path,
        model,
        pair,
        left,
        right,
        segment,
        sigma_start,
        midpoint_sigma,
        max_depth=max_depth,
        depth=depth + 1,
    )
    right_result = _refine_segment_pair(
        axis_path,
        model,
        pair,
        left,
        right,
        segment,
        midpoint_sigma,
        sigma_end,
        max_depth=max_depth,
        depth=depth + 1,
    )
    if left_result.status == "collision" or right_result.status == "collision":
        witness_sigma = left_result.witness_sigma if left_result.status == "collision" else right_result.witness_sigma
        minimum = min(
            value
            for value in (left_result.minimum_clearance_lower_bound, right_result.minimum_clearance_lower_bound)
            if value is not None
        )
        return _PairResolution(
            status="collision",
            minimum_clearance_lower_bound=minimum,
            reason_code="CollisionWitnessFound",
            witness_sigma=witness_sigma,
            evaluations=1 + left_result.evaluations + right_result.evaluations,
            subdivisions=1 + left_result.subdivisions + right_result.subdivisions,
        )
    if left_result.status == "unsupported" or right_result.status == "unsupported":
        return _PairResolution(
            status="unsupported",
            minimum_clearance_lower_bound=None,
            reason_code=left_result.reason_code if left_result.status == "unsupported" else right_result.reason_code,
            evaluations=1 + left_result.evaluations + right_result.evaluations,
            subdivisions=1 + left_result.subdivisions + right_result.subdivisions,
        )
    if left_result.status == "unresolved" or right_result.status == "unresolved":
        minima = [
            value
            for value in (left_result.minimum_clearance_lower_bound, right_result.minimum_clearance_lower_bound)
            if value is not None
        ]
        return _PairResolution(
            status="unresolved",
            minimum_clearance_lower_bound=min(minima) if minima else None,
            reason_code="ClearanceIntervalUnresolved",
            evaluations=1 + left_result.evaluations + right_result.evaluations,
            subdivisions=1 + left_result.subdivisions + right_result.subdivisions,
        )
    minima = [
        value
        for value in (left_result.minimum_clearance_lower_bound, right_result.minimum_clearance_lower_bound)
        if value is not None
    ]
    return _PairResolution(
        status="safe",
        minimum_clearance_lower_bound=min(minima) if minima else clearance_lower_bound,
        reason_code="ConfigurationCollisionCertified",
        evaluations=1 + left_result.evaluations + right_result.evaluations,
        subdivisions=1 + left_result.subdivisions + right_result.subdivisions,
    )


def _normalize_collision_model(collision_model: ConfigurationCollisionModel | Mapping[str, Any]) -> ConfigurationCollisionModel:
    if isinstance(collision_model, ConfigurationCollisionModel):
        return collision_model
    return ConfigurationCollisionModel.model_validate(collision_model)


def _artifact_content_hash(artifact: AxiomModel) -> str:
    payload = artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    return _content_hash(normalize_numeric_identity(payload))


def _content_binding_error(
    model: ConfigurationCollisionModel,
    axis_path: M3CandidateAxisPath,
) -> str | None:
    actual_content_id = _hash_collision_model(model)
    if model.content_id is not None and model.content_id != actual_content_id:
        return "CollisionModelContentHashMismatch"
    if model.machine_profile_id != axis_path.machine_profile.profile_id:
        return "CollisionModelMachineProfileIdentityMismatch"
    if model.machine_profile_content_id != axis_path.machine_profile_content_id:
        return "CollisionModelMachineProfileContentIdentityMismatch"
    if _artifact_content_hash(axis_path.machine_profile) != axis_path.machine_profile_content_id:
        return "MachineProfileContentHashMismatch"
    if _artifact_content_hash(axis_path.source_candidate_geometry) != axis_path.source_candidate_geometry_content_id:
        return "SourceCandidateGeometryContentHashMismatch"
    axis_ids = {axis.axis_id for axis in axis_path.machine_profile.axes}
    if any(
        entity.anchor_axis_id is not None and entity.anchor_axis_id not in axis_ids
        for entity in model.entities
    ):
        return "CollisionEntityAnchorAxisUnknown"
    return None


def _result_provenance(axis_path: M3CandidateAxisPath, model: ConfigurationCollisionModel) -> tuple[ProvenanceRef, ...]:
    return tuple(axis_path.provenance) + tuple(axis_path.kinematics_certificate.provenance) + tuple(model.provenance)


def _clearance_tolerance(axis_path: M3CandidateAxisPath, model: ConfigurationCollisionModel) -> ToleranceBinding:
    matched = next(
        (binding for binding in axis_path.source_candidate_geometry.tolerances if binding.target == "collision-clearance"),
        None,
    )
    if matched is not None:
        return matched
    return ToleranceBinding(
        toleranceId="five-axis.configuration-collision.clearance",
        target="collision-clearance",
        tolerance=NumericTolerance(absolute=model.minimum_clearance.absolute, unit=model.minimum_clearance.unit),
    )


def _overall_result(
    *,
    query_kind: Literal["point", "segment", "path"],
    axis_path: M3CandidateAxisPath,
    model: ConfigurationCollisionModel,
    branch_id: str | None,
    segment_id: str | None,
    sigma_start: float,
    sigma_end: float,
    pair_results: Sequence[ConfigurationCollisionPairResult],
    minimum_clearance_lower_bound: float | None,
    evaluation_count: int,
    subdivision_count: int,
) -> ConfigurationCollisionEvaluation:
    statuses = [pair.status for pair in pair_results if pair.status != "not-applicable"]
    if not statuses:
        status: _OverallStatus = "not-applicable"
        collision_free = None
        certificate_kind: _CertificateKind = "none"
        reason_code = "NoApplicableCollisionPairs"
        evidence_level: _EvidenceLevel = "Validated"
    elif any(item == "collision" for item in statuses):
        status = "collision"
        collision_free = False
        certificate_kind = "counterexample"
        reason_code = "CollisionWitnessFound"
        evidence_level = "Observed"
    elif any(item == "unsupported" for item in statuses):
        status = "unsupported"
        collision_free = None
        certificate_kind = "none"
        reason_code = next(pair.reason_code for pair in pair_results if pair.status == "unsupported")
        evidence_level = "Validated"
    elif any(item == "unresolved" for item in statuses):
        status = "unresolved"
        collision_free = None
        certificate_kind = "none"
        reason_code = "ClearanceIntervalUnresolved"
        evidence_level = "Validated"
    else:
        status = "safe"
        collision_free = True
        certificate_kind = "proof"
        reason_code = "ConfigurationCollisionCertified"
        evidence_level = "Certified"
    claim_id = (
        _SUPPORTED_CLAIM_ID
        if query_kind == "path" and model.coverage_status == "complete"
        else None
    )
    if query_kind == "point":
        certificate_kind = "point-check"
        evidence_level = "Validated"
    return ConfigurationCollisionEvaluation(
        queryKind=query_kind,
        status=status,
        collisionFree=collision_free,
        certificateKind=certificate_kind,
        claimId=claim_id,
        forbiddenClaimIds=_FORBIDDEN_CLAIM_IDS,
        reasonCode=reason_code,
        evidenceLevel=evidence_level,
        machineProfileId=axis_path.machine_profile.profile_id,
        machineProfileContentId=axis_path.machine_profile_content_id,
        axisPathId=axis_path.axis_path_id,
        axisPathContentId=_artifact_content_hash(axis_path),
        collisionModelId=model.model_id,
        collisionModelContentId=_hash_collision_model(model),
        branchId=branch_id,
        segmentId=segment_id,
        sigmaStart=sigma_start,
        sigmaEnd=sigma_end,
        minimumClearanceLowerBound=minimum_clearance_lower_bound,
        clearanceUnit=model.minimum_clearance.unit,
        policyId=model.policy_id,
        tolerance=_clearance_tolerance(axis_path, model),
        provenance=_result_provenance(axis_path, model),
        continuousMethod={
            "point": "five-axis.configuration-q-point-query@1",
            "segment": "five-axis.configuration-aabb-envelope-recursive@1",
            "path": "five-axis.configuration-path-envelope-aggregate@1",
        }[query_kind],
        evaluationCount=evaluation_count,
        subdivisionCount=subdivision_count,
        pairResults=tuple(pair_results),
    )


def evaluate_configuration_q_free(
    axis_path: M3CandidateAxisPath,
    *,
    collision_model: ConfigurationCollisionModel | Mapping[str, Any],
    sigma: float,
    branch_id: str | None = None,
) -> ConfigurationCollisionEvaluation:
    model = _normalize_collision_model(collision_model)
    content_reason = _content_binding_error(model, axis_path)
    if content_reason is not None:
        return _overall_result(
            query_kind="point",
            axis_path=axis_path,
            model=model,
            branch_id=branch_id,
            segment_id=None,
            sigma_start=sigma,
            sigma_end=sigma,
            pair_results=(
                ConfigurationCollisionPairResult(
                    pairId="model",
                    pairKind="environment",
                    status="unsupported",
                    reasonCode=content_reason,
                    leftEntityId="model",
                    rightEntityId="model",
                ),
            ),
            minimum_clearance_lower_bound=None,
            evaluation_count=0,
            subdivision_count=0,
        )
    segment = _branch_segment(axis_path, sigma=sigma, branch_id=branch_id)
    q_values = _evaluate_segment(segment, sigma)
    entities = {entity.entity_id: entity for entity in model.entities}
    pair_results: list[ConfigurationCollisionPairResult] = []
    lower_bounds: list[float] = []
    for pair in model.pairs:
        if not _pair_applicable(pair, entities, segment.branch_id):
            pair_results.append(
                ConfigurationCollisionPairResult(
                    pairId=pair.pair_id,
                    pairKind=pair.pair_kind,
                    status="not-applicable",
                    reasonCode="PairInactiveOnBranch",
                    leftEntityId=pair.left_entity_id,
                    rightEntityId=pair.right_entity_id,
                )
            )
            continue
        clearance = _pair_clearance_at_q(axis_path.machine_profile, entities[pair.left_entity_id], entities[pair.right_entity_id], q_values)
        lower_bounds.append(clearance)
        threshold = _pair_threshold(model, pair)
        status: _PairStatus = "collision" if clearance <= threshold + _EPSILON else "safe"
        pair_results.append(
            ConfigurationCollisionPairResult(
                pairId=pair.pair_id,
                pairKind=pair.pair_kind,
                status=status,
                reasonCode="CollisionWitnessFound" if status == "collision" else "ConfigurationCollisionCertified",
                leftEntityId=pair.left_entity_id,
                rightEntityId=pair.right_entity_id,
                minimumClearanceLowerBound=max(0.0, clearance),
                witnessSigma=sigma if status == "collision" else None,
            )
        )
    return _overall_result(
        query_kind="point",
        axis_path=axis_path,
        model=model,
        branch_id=segment.branch_id,
        segment_id=segment.segment_id,
        sigma_start=sigma,
        sigma_end=sigma,
        pair_results=pair_results,
        minimum_clearance_lower_bound=min(lower_bounds) if lower_bounds else None,
        evaluation_count=len([pair for pair in pair_results if pair.status != "not-applicable"]),
        subdivision_count=0,
    )


def _resolve_configuration_interval_pairs(
    axis_path: M3CandidateAxisPath,
    *,
    model: ConfigurationCollisionModel,
    segment: JointPolynomialSegment | _PolynomialJointInterval,
    interval_start: float,
    interval_end: float,
    max_subdivision_depth: int,
) -> tuple[tuple[tuple[CollisionPair, _PairResolution], ...], float | None, int, int]:
    entities = {entity.entity_id: entity for entity in model.entities}
    resolutions: list[tuple[CollisionPair, _PairResolution]] = []
    lower_bounds: list[float] = []
    evaluation_count = 0
    subdivision_count = 0
    for pair in model.pairs:
        if not _pair_applicable(pair, entities, segment.branch_id):
            resolutions.append(
                (
                    pair,
                    _PairResolution(
                        status="not-applicable",
                        minimum_clearance_lower_bound=None,
                        reason_code="PairInactiveOnBranch",
                    ),
                )
            )
            continue
        resolution = _refine_segment_pair(
            axis_path,
            model,
            pair,
            entities[pair.left_entity_id],
            entities[pair.right_entity_id],
            segment,
            interval_start,
            interval_end,
            max_depth=max_subdivision_depth,
        )
        evaluation_count += resolution.evaluations
        subdivision_count += resolution.subdivisions
        if resolution.minimum_clearance_lower_bound is not None:
            lower_bounds.append(resolution.minimum_clearance_lower_bound)
        resolutions.append((pair, resolution))
    return (
        tuple(resolutions),
        min(lower_bounds) if lower_bounds else None,
        evaluation_count,
        subdivision_count,
    )


def _evaluate_configuration_interval_collision(
    axis_path: M3CandidateAxisPath,
    *,
    model: ConfigurationCollisionModel,
    segment: JointPolynomialSegment | _PolynomialJointInterval,
    interval_start: float,
    interval_end: float,
    max_subdivision_depth: int,
) -> ConfigurationCollisionEvaluation:
    content_reason = _content_binding_error(model, axis_path)
    if content_reason is not None:
        pair_results = (
            ConfigurationCollisionPairResult(
                pairId="model",
                pairKind="environment",
                status="unsupported",
                reasonCode=content_reason,
                leftEntityId="model",
                rightEntityId="model",
            ),
        )
        minimum_clearance_lower_bound = None
        evaluation_count = 0
        subdivision_count = 0
    else:
        resolutions, minimum_clearance_lower_bound, evaluation_count, subdivision_count = (
            _resolve_configuration_interval_pairs(
                axis_path,
                model=model,
                segment=segment,
                interval_start=interval_start,
                interval_end=interval_end,
                max_subdivision_depth=max_subdivision_depth,
            )
        )
        pair_results = tuple(
            ConfigurationCollisionPairResult(
                pairId=pair.pair_id,
                pairKind=pair.pair_kind,
                status=resolution.status,
                reasonCode=resolution.reason_code,
                leftEntityId=pair.left_entity_id,
                rightEntityId=pair.right_entity_id,
                minimumClearanceLowerBound=resolution.minimum_clearance_lower_bound,
                witnessSigma=resolution.witness_sigma,
            )
            for pair, resolution in resolutions
        )
    return _overall_result(
        query_kind="segment",
        axis_path=axis_path,
        model=model,
        branch_id=segment.branch_id,
        segment_id=segment.segment_id,
        sigma_start=interval_start,
        sigma_end=interval_end,
        pair_results=pair_results,
        minimum_clearance_lower_bound=minimum_clearance_lower_bound,
        evaluation_count=evaluation_count,
        subdivision_count=subdivision_count,
    )


def evaluate_configuration_segment_collision(
    axis_path: M3CandidateAxisPath,
    *,
    collision_model: ConfigurationCollisionModel | Mapping[str, Any],
    segment_id: str,
    sigma_start: float | None = None,
    sigma_end: float | None = None,
    max_subdivision_depth: int = _MAX_SUBDIVISION_DEPTH,
) -> ConfigurationCollisionEvaluation:
    model = _normalize_collision_model(collision_model)
    segment = _branch_segment(axis_path, segment_id=segment_id)
    interval_start = segment.sigma_start if sigma_start is None else sigma_start
    interval_end = segment.sigma_end if sigma_end is None else sigma_end
    if interval_start < segment.sigma_start - _EPSILON or interval_end > segment.sigma_end + _EPSILON or interval_end < interval_start:
        raise ValueError("SegmentIntervalOutOfBounds")
    return _evaluate_configuration_interval_collision(
        axis_path,
        model=model,
        segment=segment,
        interval_start=interval_start,
        interval_end=interval_end,
        max_subdivision_depth=max_subdivision_depth,
    )


def evaluate_configuration_polynomial_interval_collision(
    axis_path: M3CandidateAxisPath,
    *,
    collision_model: ConfigurationCollisionModel | Mapping[str, Any],
    interval_id: str,
    parameter_start: float,
    parameter_end: float,
    branch_id: str,
    coefficients: Sequence[Sequence[float]],
    coefficient_basis: str = "local-power@1",
    parameter_name: Literal["normalized-local", "time"] = "normalized-local",
    max_subdivision_depth: int = _MAX_SUBDIVISION_DEPTH,
) -> PolynomialCollisionIntervalEvaluation:
    """Validate a normalized local-power joint interval against the F2 collision model.

    Coefficients are ordered by ascending power over local parameter ``u`` in
    ``[0, 1]``.  The result remains a segment-level diagnostic and therefore
    cannot publish a path-level collision claim.
    """

    if not interval_id:
        raise ValueError("intervalId is required")
    if not branch_id:
        raise ValueError("branchId is required")
    if not math.isfinite(parameter_start) or not math.isfinite(parameter_end):
        raise ValueError("PolynomialIntervalBoundsMustBeFinite")
    if parameter_end <= parameter_start:
        raise ValueError("PolynomialIntervalBoundsInvalid")
    interval = _PolynomialJointInterval(
        segment_id=interval_id,
        branch_id=branch_id,
        sigma_start=float(parameter_start),
        sigma_end=float(parameter_end),
        coefficients=tuple(tuple(float(value) for value in row) for row in coefficients),
        coefficient_basis=coefficient_basis,
    )
    _segment_coefficients(interval)
    model = _normalize_collision_model(collision_model)
    content_reason = _content_binding_error(model, axis_path)
    if content_reason is not None:
        pair_results = (
            PolynomialCollisionPairResult(
                pairId="model",
                pairKind="environment",
                status="unsupported",
                reasonCode=content_reason,
                leftEntityId="model",
                rightEntityId="model",
            ),
        )
        minimum_clearance_lower_bound = None
        evaluation_count = 0
        subdivision_count = 0
    else:
        resolutions, minimum_clearance_lower_bound, evaluation_count, subdivision_count = (
            _resolve_configuration_interval_pairs(
                axis_path,
                model=model,
                segment=interval,
                interval_start=interval.sigma_start,
                interval_end=interval.sigma_end,
                max_subdivision_depth=max_subdivision_depth,
            )
        )
        pair_results = tuple(
            PolynomialCollisionPairResult(
                pairId=pair.pair_id,
                pairKind=pair.pair_kind,
                status=resolution.status,
                reasonCode=resolution.reason_code,
                leftEntityId=pair.left_entity_id,
                rightEntityId=pair.right_entity_id,
                minimumClearanceLowerBound=resolution.minimum_clearance_lower_bound,
                witnessParameter=resolution.witness_sigma,
            )
            for pair, resolution in resolutions
        )
    statuses = [pair.status for pair in pair_results if pair.status != "not-applicable"]
    if not statuses:
        status: _OverallStatus = "not-applicable"
        collision_free = None
        certificate_kind: _CertificateKind = "none"
        reason_code = "NoApplicableCollisionPairs"
        evidence_level: _EvidenceLevel = "Validated"
    elif any(item == "collision" for item in statuses):
        status = "collision"
        collision_free = False
        certificate_kind = "counterexample"
        reason_code = "CollisionWitnessFound"
        evidence_level = "Observed"
    elif any(item == "unsupported" for item in statuses):
        status = "unsupported"
        collision_free = None
        certificate_kind = "none"
        reason_code = next(pair.reason_code for pair in pair_results if pair.status == "unsupported")
        evidence_level = "Validated"
    elif any(item == "unresolved" for item in statuses):
        status = "unresolved"
        collision_free = None
        certificate_kind = "none"
        reason_code = "ClearanceIntervalUnresolved"
        evidence_level = "Validated"
    else:
        status = "safe"
        collision_free = True
        certificate_kind = "proof"
        reason_code = "ConfigurationCollisionCertified"
        evidence_level = "Certified"
    return PolynomialCollisionIntervalEvaluation(
        intervalId=interval.segment_id,
        parameterName=parameter_name,
        parameterStart=interval.sigma_start,
        parameterEnd=interval.sigma_end,
        status=status,
        collisionFree=collision_free,
        certificateKind=certificate_kind,
        reasonCode=reason_code,
        evidenceLevel=evidence_level,
        machineProfileId=axis_path.machine_profile.profile_id,
        machineProfileContentId=axis_path.machine_profile_content_id,
        sourceAxisPathId=axis_path.axis_path_id,
        sourceAxisPathContentId=_artifact_content_hash(axis_path),
        collisionModelId=model.model_id,
        collisionModelContentId=_hash_collision_model(model),
        branchId=interval.branch_id,
        minimumClearanceLowerBound=minimum_clearance_lower_bound,
        clearanceUnit=model.minimum_clearance.unit,
        policyId=model.policy_id,
        continuousMethod="five-axis.configuration-polynomial-envelope-recursive@1",
        evaluationCount=evaluation_count,
        subdivisionCount=subdivision_count,
        pairResults=pair_results,
    )


def evaluate_configuration_path_collision(
    axis_path: M3CandidateAxisPath,
    *,
    collision_model: ConfigurationCollisionModel | Mapping[str, Any],
    max_subdivision_depth: int = _MAX_SUBDIVISION_DEPTH,
) -> ConfigurationCollisionEvaluation:
    model = _normalize_collision_model(collision_model)
    segment_results = tuple(
        evaluate_configuration_segment_collision(
            axis_path,
            collision_model=model,
            segment_id=segment.segment_id,
            max_subdivision_depth=max_subdivision_depth,
        )
        for segment in axis_path.joint_segments
    )
    pair_results = tuple(pair for result in segment_results for pair in result.pair_results)
    lower_bounds = tuple(
        result.minimum_clearance_lower_bound
        for result in segment_results
        if result.minimum_clearance_lower_bound is not None
    )
    return _overall_result(
        query_kind="path",
        axis_path=axis_path,
        model=model,
        branch_id=axis_path.kinematics_certificate.selected_branch_id,
        segment_id=None,
        sigma_start=0.0,
        sigma_end=1.0,
        pair_results=pair_results,
        minimum_clearance_lower_bound=min(lower_bounds) if lower_bounds else None,
        evaluation_count=sum(result.evaluation_count for result in segment_results),
        subdivision_count=sum(result.subdivision_count for result in segment_results),
    )


__all__ = [
    "CollisionEntity",
    "CollisionPair",
    "CollisionTolerance",
    "ConfigurationCollisionEvaluation",
    "ConfigurationCollisionModel",
    "ConfigurationCollisionPairResult",
    "PolynomialCollisionIntervalEvaluation",
    "PolynomialCollisionPairResult",
    "evaluate_configuration_q_free",
    "evaluate_configuration_path_collision",
    "evaluate_configuration_polynomial_interval_collision",
    "evaluate_configuration_segment_collision",
    "hash_configuration_collision_model",
]
