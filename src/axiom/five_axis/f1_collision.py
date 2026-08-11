from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from scipy.optimize import minimize_scalar

from ..models import AxiomModel
from .f1_geometry import GeometryEvaluationError, evaluate_position as _evaluate_geometry_position
from .f1_geometry import evaluate_tool_axis as _evaluate_geometry_tool_axis
from .f1_models import AxisAlignedBoundingBox, M2CandidateTaskGeometry


_EPSILON = 1e-12
_MAX_SUBDIVISION_DEPTH = 18
_MIN_SIGMA_SPAN = 1e-5
_MAX_REGULARIZED_DIFFERENCE_FRAGMENTS = 256

_EvidenceLevel = Literal["Certified", "Validated", "Observed"]
_FindingKind = Literal[
    "allowed-removal-contact",
    "forbidden-contact",
    "overcut",
    "insufficient-context",
    "invalid-snapshot",
    "unsupported",
    "upstream-process-state-invalid",
]
_TransitionStatus = Literal["Succeeded", "Failed", "Blocked"]


def _dot3(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _sub3(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _add3(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return (left[0] + right[0], left[1] + right[1], left[2] + right[2])


def _scale3(vector: tuple[float, float, float], scalar: float) -> tuple[float, float, float]:
    return (vector[0] * scalar, vector[1] * scalar, vector[2] * scalar)


def _cross3(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _norm3(vector: tuple[float, float, float]) -> float:
    return math.sqrt(_dot3(vector, vector))


def _normalize3(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = _norm3(vector)
    if math.isclose(norm, 0.0, abs_tol=_EPSILON):
        raise ValueError("zero vector cannot be normalized")
    return (vector[0] / norm, vector[1] / norm, vector[2] / norm)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _canonical_box(box: AxisAlignedBoundingBox) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return (tuple(box.min_corner), tuple(box.max_corner))


def _make_box(min_corner: tuple[float, float, float], max_corner: tuple[float, float, float]) -> AxisAlignedBoundingBox | None:
    if any(high <= low + _EPSILON for low, high in zip(min_corner, max_corner)):
        return None
    return AxisAlignedBoundingBox(min_corner=min_corner, max_corner=max_corner)


def _intersect_boxes(left: AxisAlignedBoundingBox, right: AxisAlignedBoundingBox) -> AxisAlignedBoundingBox | None:
    min_corner = tuple(max(a, b) for a, b in zip(left.min_corner, right.min_corner))
    max_corner = tuple(min(a, b) for a, b in zip(left.max_corner, right.max_corner))
    return _make_box(min_corner, max_corner)


def _box_distance(left: AxisAlignedBoundingBox, right: AxisAlignedBoundingBox) -> float:
    distance_sq = 0.0
    for left_min, left_max, right_min, right_max in zip(
        left.min_corner,
        left.max_corner,
        right.min_corner,
        right.max_corner,
    ):
        if left_max < right_min:
            gap = right_min - left_max
        elif right_max < left_min:
            gap = left_min - right_max
        else:
            gap = 0.0
        distance_sq += gap * gap
    return math.sqrt(distance_sq)


def _subtract_box(source: AxisAlignedBoundingBox, cutter: AxisAlignedBoundingBox) -> tuple[AxisAlignedBoundingBox, ...]:
    overlap = _intersect_boxes(source, cutter)
    if overlap is None:
        return (source,)
    sx0, sy0, sz0 = source.min_corner
    sx1, sy1, sz1 = source.max_corner
    ox0, oy0, oz0 = overlap.min_corner
    ox1, oy1, oz1 = overlap.max_corner
    candidates = (
        _make_box((sx0, sy0, sz0), (ox0, sy1, sz1)),
        _make_box((ox1, sy0, sz0), (sx1, sy1, sz1)),
        _make_box((ox0, sy0, sz0), (ox1, oy0, sz1)),
        _make_box((ox0, oy1, sz0), (ox1, sy1, sz1)),
        _make_box((ox0, oy0, sz0), (ox1, oy1, oz0)),
        _make_box((ox0, oy0, oz1), (ox1, oy1, sz1)),
    )
    return tuple(box for box in candidates if box is not None)


def _subtract_union(
    source_boxes: Sequence[AxisAlignedBoundingBox],
    cutters: Sequence[AxisAlignedBoundingBox],
) -> tuple[AxisAlignedBoundingBox, ...]:
    remaining = tuple(source_boxes)
    for cutter in cutters:
        next_remaining: list[AxisAlignedBoundingBox] = []
        for box in remaining:
            next_remaining.extend(_subtract_box(box, cutter))
        remaining = tuple(next_remaining)
    return tuple(sorted(remaining, key=_canonical_box))


def _boxes_subset_of(boxes: Sequence[AxisAlignedBoundingBox], allowed: Sequence[AxisAlignedBoundingBox]) -> bool:
    for box in boxes:
        uncovered = (box,)
        for allowed_box in allowed:
            uncovered = _subtract_union(uncovered, (allowed_box,))
            if not uncovered:
                break
        if uncovered:
            return False
    return True


def _hash_state_geometry(geometry: Mapping[str, Sequence[AxisAlignedBoundingBox]]) -> str:
    payload = {
        stock_fixture_id: [
            {"minCorner": list(box.min_corner), "maxCorner": list(box.max_corner)}
            for box in sorted(boxes, key=_canonical_box)
        ]
        for stock_fixture_id, boxes in sorted(geometry.items())
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


hash_state_geometry = _hash_state_geometry


def _segment_point_distance_to_aabb_sq(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    box: AxisAlignedBoundingBox,
) -> float:
    direction = _sub3(end, start)

    def objective(parameter: float) -> float:
        point = _add3(start, _scale3(direction, parameter))
        distance_sq = 0.0
        for coordinate, lower, upper in zip(point, box.min_corner, box.max_corner):
            if coordinate < lower:
                delta = lower - coordinate
            elif coordinate > upper:
                delta = coordinate - upper
            else:
                delta = 0.0
            distance_sq += delta * delta
        return distance_sq

    optimum = minimize_scalar(objective, bounds=(0.0, 1.0), method="bounded")
    return max(0.0, float(optimum.fun))


def _rotation_from_to(
    source: tuple[float, float, float],
    target: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    source_axis = _normalize3(source)
    target_axis = _normalize3(target)
    cosine = _clamp(_dot3(source_axis, target_axis), -1.0, 1.0)
    if math.isclose(cosine, 1.0, abs_tol=1e-9):
        return (
            (1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0),
        )
    if math.isclose(cosine, -1.0, abs_tol=1e-9):
        helper = (1.0, 0.0, 0.0) if abs(source_axis[0]) < 0.9 else (0.0, 1.0, 0.0)
        axis = _normalize3(_cross3(source_axis, helper))
        x, y, z = axis
        return (
            (-1.0 + 2.0 * x * x, 2.0 * x * y, 2.0 * x * z),
            (2.0 * x * y, -1.0 + 2.0 * y * y, 2.0 * y * z),
            (2.0 * x * z, 2.0 * y * z, -1.0 + 2.0 * z * z),
        )
    axis = _normalize3(_cross3(source_axis, target_axis))
    x, y, z = axis
    sine = math.sqrt(max(0.0, 1.0 - cosine * cosine))
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


def _rotate_vector(
    matrix: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        _dot3(matrix[0], vector),
        _dot3(matrix[1], vector),
        _dot3(matrix[2], vector),
    )


@dataclass(frozen=True)
class _ToolPrimitive:
    kind: Literal["aabb", "capsule"]
    component_id: str
    component_kind: str
    tool_axis: tuple[float, float, float]
    aabb: AxisAlignedBoundingBox | None = None
    radius: float | None = None
    axis_start_offset: float | None = None
    axis_end_offset: float | None = None


@dataclass(frozen=True)
class _SubIntervalKinematics:
    sigma_start: float
    sigma_end: float
    start_position: tuple[float, float, float]
    end_position: tuple[float, float, float]
    axis: tuple[float, float, float]
    position_segment_id: str
    orientation_segment_id: str


@dataclass(frozen=True)
class _PairResolution:
    status: Literal["safe", "refuted", "validated"]
    evidence_level: _EvidenceLevel
    minimum_clearance_lower_bound: float
    subdivisions: int
    evaluations: int
    sample_sigma: float | None = None


@dataclass(frozen=True)
class _StockStateSnapshot:
    actual_content_id: str
    declared_content_id: str | None
    stock_boxes: dict[str, tuple[AxisAlignedBoundingBox, ...]]


class TaskCollisionFinding(AxiomModel):
    interval_id: str
    finding_kind: _FindingKind
    evidence_level: _EvidenceLevel
    reason_code: str = "None"
    component_id: str | None = None
    stock_fixture_id: str | None = None
    sigma_start: float
    sigma_end: float
    minimum_clearance_lower_bound: float | None = None
    sample_sigma: float | None = None


class TaskCollisionStateTransition(AxiomModel):
    interval_id: str
    status: _TransitionStatus
    reason_code: str
    input_state_id: str
    output_state_id: str | None = None
    produced_content_id: str | None = None
    evidence_level: _EvidenceLevel


class TaskCollisionEvaluation(AxiomModel):
    collision_free: bool | None
    overcut_free: bool | None
    minimum_clearance_lower_bound: float | None
    clearance_unit: str
    continuous_method: str
    subdivision_count: int
    evaluation_count: int
    evidence_level: _EvidenceLevel
    reason_code: str | None = None
    findings: tuple[TaskCollisionFinding, ...]
    state_transitions: tuple[TaskCollisionStateTransition, ...]
    supported_segment_types: tuple[str, ...] = ("line", "constant-orientation")


class UnsupportedCollisionGeometry(ValueError):
    """Raised when F1 collision cannot certify the requested analytic geometry subset."""


class UnsupportedRegularizedDifference(ValueError):
    """Raised when nominal-sweep AABB subtraction exceeds the supported deterministic subset."""


def _get_attr(value: Any, *names: str) -> Any:
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return None


def _normalize_tool_component(component: Any) -> _ToolPrimitive:
    component_id = _get_attr(component, "component_id", "componentId")
    component_kind = _get_attr(component, "component_kind", "componentKind")
    tool_axis = _get_attr(component, "tool_axis", "toolAxis") or (0.0, 0.0, 1.0)
    radius = _get_attr(component, "radius")
    axis_start_offset = _get_attr(component, "axis_start_offset", "axisStartOffset")
    axis_end_offset = _get_attr(component, "axis_end_offset", "axisEndOffset")
    if radius is not None and axis_start_offset is not None and axis_end_offset is not None:
        return _ToolPrimitive(
            kind="capsule",
            component_id=component_id,
            component_kind=component_kind,
            tool_axis=tuple(tool_axis),
            radius=float(radius),
            axis_start_offset=float(axis_start_offset),
            axis_end_offset=float(axis_end_offset),
        )
    if hasattr(component, "aabb"):
        return _ToolPrimitive(
            kind="aabb",
            component_id=component_id,
            component_kind=component_kind,
            tool_axis=tuple(tool_axis),
            aabb=component.aabb,
        )
    raise UnsupportedCollisionGeometry("UnsupportedToolComponentPrimitive")


def _normalize_state_geometry(
    seeded_geometry: Mapping[str, Mapping[str, Sequence[Any]]] | None,
) -> dict[str, _StockStateSnapshot]:
    normalized: dict[str, _StockStateSnapshot] = {}
    if seeded_geometry is None:
        return normalized
    for state_id, state_payload in seeded_geometry.items():
        declared_content_id: str | None = None
        stock_mapping: Mapping[str, Sequence[Any]]
        if isinstance(state_payload, Mapping) and ("stockFixtures" in state_payload or "contentId" in state_payload):
            declared_content_id = state_payload.get("contentId")
            stock_mapping = state_payload.get("stockFixtures", {})
        else:
            stock_mapping = state_payload
        materialized_mapping: dict[str, tuple[AxisAlignedBoundingBox, ...]] = {}
        for stock_fixture_id, boxes in stock_mapping.items():
            materialized: list[AxisAlignedBoundingBox] = []
            for box in boxes:
                if isinstance(box, AxisAlignedBoundingBox):
                    materialized.append(box)
                    continue
                if isinstance(box, Mapping):
                    materialized.append(
                        AxisAlignedBoundingBox(
                            min_corner=tuple(box["minCorner"]),
                            max_corner=tuple(box["maxCorner"]),
                        )
                    )
                    continue
                min_corner, max_corner = box
                materialized.append(AxisAlignedBoundingBox(min_corner=tuple(min_corner), max_corner=tuple(max_corner)))
            materialized_mapping[stock_fixture_id] = tuple(sorted(materialized, key=_canonical_box))
        normalized[state_id] = _StockStateSnapshot(
            actual_content_id=hash_state_geometry(materialized_mapping),
            declared_content_id=declared_content_id,
            stock_boxes=materialized_mapping,
        )
    return normalized


def _contact_policy_lookup(task: M2CandidateTaskGeometry, left: str, right: str) -> Literal["allowed", "forbidden"]:
    explicit_allowed = False
    for rule in task.collision_context.contact_policy.rules:
        if {rule.left_category, rule.right_category} != {left, right}:
            continue
        if rule.contact_policy == "forbidden":
            return "forbidden"
        explicit_allowed = True
    return "allowed" if explicit_allowed else "forbidden"


def _point_on_line_segment(
    start_point: tuple[float, float, float],
    end_point: tuple[float, float, float],
    local_parameter: float,
) -> tuple[float, float, float]:
    return _add3(start_point, _scale3(_sub3(end_point, start_point), local_parameter))


def _position_at_sigma(task: M2CandidateTaskGeometry, sigma: float) -> tuple[float, float, float]:
    try:
        return tuple(_evaluate_geometry_position(task, sigma))
    except GeometryEvaluationError as exc:
        raise UnsupportedCollisionGeometry(str(exc)) from exc


def _axis_at_sigma(task: M2CandidateTaskGeometry, sigma: float) -> tuple[float, float, float]:
    try:
        return tuple(_evaluate_geometry_tool_axis(task, sigma))
    except GeometryEvaluationError as exc:
        raise UnsupportedCollisionGeometry(str(exc)) from exc


def _kinematic_subintervals(task: M2CandidateTaskGeometry, sigma_start: float, sigma_end: float) -> tuple[_SubIntervalKinematics, ...]:
    if not task.position_segments or not task.orientation_segments:
        raise UnsupportedCollisionGeometry("ContinuousPositionAndOrientationRequired")
    breakpoints = {sigma_start, sigma_end}
    for segment in task.position_segments:
        if sigma_start < segment.sigma_start < sigma_end:
            breakpoints.add(segment.sigma_start)
        if sigma_start < segment.sigma_end < sigma_end:
            breakpoints.add(segment.sigma_end)
    for segment in task.orientation_segments:
        if sigma_start < segment.sigma_start < sigma_end:
            breakpoints.add(segment.sigma_start)
        if sigma_start < segment.sigma_end < sigma_end:
            breakpoints.add(segment.sigma_end)
    ordered = sorted(breakpoints)
    subintervals: list[_SubIntervalKinematics] = []
    for left, right in zip(ordered, ordered[1:]):
        midpoint = (left + right) * 0.5
        position_segment = next(
            (segment for segment in task.position_segments if segment.sigma_start - _EPSILON <= midpoint <= segment.sigma_end + _EPSILON),
            None,
        )
        orientation_segment = next(
            (segment for segment in task.orientation_segments if segment.sigma_start - _EPSILON <= midpoint <= segment.sigma_end + _EPSILON),
            None,
        )
        if position_segment is None or orientation_segment is None:
            raise UnsupportedCollisionGeometry("MissingSegmentCoverage")
        if position_segment.segment_type != "line":
            raise UnsupportedCollisionGeometry(f"UnsupportedPositionSegment:{position_segment.segment_type}")
        if orientation_segment.segment_type != "constant":
            raise UnsupportedCollisionGeometry(f"UnsupportedOrientationSegment:{orientation_segment.segment_type}")
        position_start = _position_at_sigma(task, left)
        position_end = _position_at_sigma(task, right)
        subintervals.append(
            _SubIntervalKinematics(
                sigma_start=left,
                sigma_end=right,
                start_position=position_start,
                end_position=position_end,
                axis=_axis_at_sigma(task, (left + right) * 0.5),
                position_segment_id=position_segment.segment_id,
                orientation_segment_id=orientation_segment.segment_id,
            )
        )
    return tuple(subintervals)


def _world_aabb_for_box(
    primitive: _ToolPrimitive,
    position: tuple[float, float, float],
    axis: tuple[float, float, float],
) -> AxisAlignedBoundingBox:
    assert primitive.aabb is not None
    rotation = _rotation_from_to(primitive.tool_axis, axis)
    x0, y0, z0 = primitive.aabb.min_corner
    x1, y1, z1 = primitive.aabb.max_corner
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
    world_corners = [_add3(position, _rotate_vector(rotation, corner)) for corner in corners]
    min_corner = tuple(min(point[index] for point in world_corners) for index in range(3))
    max_corner = tuple(max(point[index] for point in world_corners) for index in range(3))
    return AxisAlignedBoundingBox(min_corner=min_corner, max_corner=max_corner)


def _world_capsule_endpoints(
    primitive: _ToolPrimitive,
    position: tuple[float, float, float],
    axis: tuple[float, float, float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    assert primitive.axis_start_offset is not None
    assert primitive.axis_end_offset is not None
    start = _add3(position, _scale3(axis, primitive.axis_start_offset))
    end = _add3(position, _scale3(axis, primitive.axis_end_offset))
    return start, end


def _world_aabb_for_capsule(
    primitive: _ToolPrimitive,
    position: tuple[float, float, float],
    axis: tuple[float, float, float],
) -> AxisAlignedBoundingBox:
    assert primitive.radius is not None
    start, end = _world_capsule_endpoints(primitive, position, axis)
    min_corner = tuple(min(start[index], end[index]) - primitive.radius for index in range(3))
    max_corner = tuple(max(start[index], end[index]) + primitive.radius for index in range(3))
    return AxisAlignedBoundingBox(min_corner=min_corner, max_corner=max_corner)


def _primitive_aabb_at_pose(
    primitive: _ToolPrimitive,
    position: tuple[float, float, float],
    axis: tuple[float, float, float],
) -> AxisAlignedBoundingBox:
    if primitive.kind == "aabb":
        return _world_aabb_for_box(primitive, position, axis)
    return _world_aabb_for_capsule(primitive, position, axis)


def _primitive_clearance_to_box_at_pose(
    primitive: _ToolPrimitive,
    position: tuple[float, float, float],
    axis: tuple[float, float, float],
    obstacle: AxisAlignedBoundingBox,
) -> float:
    if primitive.kind == "aabb":
        return _box_distance(_world_aabb_for_box(primitive, position, axis), obstacle)
    capsule_box = _world_aabb_for_capsule(primitive, position, axis)
    broad_phase = _box_distance(capsule_box, obstacle)
    if broad_phase > (primitive.radius or 0.0):
        return broad_phase - (primitive.radius or 0.0)
    start, end = _world_capsule_endpoints(primitive, position, axis)
    distance_sq = _segment_point_distance_to_aabb_sq(start, end, obstacle)
    return max(0.0, math.sqrt(distance_sq) - float(primitive.radius))


def _swept_aabb_for_translation(
    primitive: _ToolPrimitive,
    kinematics: _SubIntervalKinematics,
) -> AxisAlignedBoundingBox:
    start_box = _primitive_aabb_at_pose(primitive, kinematics.start_position, kinematics.axis)
    end_box = _primitive_aabb_at_pose(primitive, kinematics.end_position, kinematics.axis)
    min_corner = tuple(min(start_box.min_corner[index], end_box.min_corner[index]) for index in range(3))
    max_corner = tuple(max(start_box.max_corner[index], end_box.max_corner[index]) for index in range(3))
    return AxisAlignedBoundingBox(min_corner=min_corner, max_corner=max_corner)


def _refine_forbidden_pair(
    primitive: _ToolPrimitive,
    obstacle: AxisAlignedBoundingBox,
    kinematics: _SubIntervalKinematics,
    threshold: float,
    *,
    max_depth: int = _MAX_SUBDIVISION_DEPTH,
    depth: int = 0,
) -> _PairResolution:
    swept_box = _swept_aabb_for_translation(primitive, kinematics)
    clearance_lower_bound = _box_distance(swept_box, obstacle)
    if clearance_lower_bound > threshold + _EPSILON:
        return _PairResolution(
            status="safe",
            evidence_level="Certified",
            minimum_clearance_lower_bound=clearance_lower_bound,
            subdivisions=0,
            evaluations=0,
        )
    sample_points = (
        (kinematics.sigma_start, kinematics.start_position),
        ((kinematics.sigma_start + kinematics.sigma_end) * 0.5, _point_on_line_segment(kinematics.start_position, kinematics.end_position, 0.5)),
        (kinematics.sigma_end, kinematics.end_position),
    )
    evaluations = 0
    for sigma, position in sample_points:
        evaluations += 1
        actual_clearance = _primitive_clearance_to_box_at_pose(primitive, position, kinematics.axis, obstacle)
        if actual_clearance <= threshold + _EPSILON:
            return _PairResolution(
                status="refuted",
                evidence_level="Observed",
                minimum_clearance_lower_bound=min(clearance_lower_bound, actual_clearance),
                subdivisions=0,
                evaluations=evaluations,
                sample_sigma=sigma,
            )
    span = kinematics.sigma_end - kinematics.sigma_start
    if depth >= max_depth or span <= _MIN_SIGMA_SPAN:
        return _PairResolution(
            status="validated",
            evidence_level="Validated",
            minimum_clearance_lower_bound=0.0,
            subdivisions=0,
            evaluations=evaluations,
        )
    midpoint_sigma = (kinematics.sigma_start + kinematics.sigma_end) * 0.5
    midpoint_position = _point_on_line_segment(kinematics.start_position, kinematics.end_position, 0.5)
    left = _refine_forbidden_pair(
        primitive,
        obstacle,
        _SubIntervalKinematics(
            sigma_start=kinematics.sigma_start,
            sigma_end=midpoint_sigma,
            start_position=kinematics.start_position,
            end_position=midpoint_position,
            axis=kinematics.axis,
            position_segment_id=kinematics.position_segment_id,
            orientation_segment_id=kinematics.orientation_segment_id,
        ),
        threshold,
        max_depth=max_depth,
        depth=depth + 1,
    )
    right = _refine_forbidden_pair(
        primitive,
        obstacle,
        _SubIntervalKinematics(
            sigma_start=midpoint_sigma,
            sigma_end=kinematics.sigma_end,
            start_position=midpoint_position,
            end_position=kinematics.end_position,
            axis=kinematics.axis,
            position_segment_id=kinematics.position_segment_id,
            orientation_segment_id=kinematics.orientation_segment_id,
        ),
        threshold,
        max_depth=max_depth,
        depth=depth + 1,
    )
    status = "safe"
    evidence_level: _EvidenceLevel = "Certified"
    sample_sigma = None
    if left.status == "refuted" or right.status == "refuted":
        status = "refuted"
        evidence_level = "Observed"
        sample_sigma = left.sample_sigma if left.status == "refuted" else right.sample_sigma
    elif left.status == "validated" or right.status == "validated":
        status = "validated"
        evidence_level = "Validated"
    return _PairResolution(
        status=status,
        evidence_level=evidence_level,
        minimum_clearance_lower_bound=min(left.minimum_clearance_lower_bound, right.minimum_clearance_lower_bound),
        subdivisions=left.subdivisions + right.subdivisions + 1,
        evaluations=evaluations + left.evaluations + right.evaluations,
        sample_sigma=sample_sigma,
    )


def _allowed_regions_for_interval(task: M2CandidateTaskGeometry, interval: Any) -> dict[str, tuple[AxisAlignedBoundingBox, ...]]:
    if interval.tool_component_id is None:
        return {}
    regions: dict[str, list[AxisAlignedBoundingBox]] = {}
    for removal in task.collision_context.allowed_removal:
        if removal.tool_component_id != interval.tool_component_id:
            continue
        region = removal.region
        if region is None:
            stock_box = next(
                stock_fixture.aabb
                for stock_fixture in task.collision_context.stock_fixtures
                if stock_fixture.stock_fixture_id == removal.stock_fixture_id
            )
            region = stock_box
        regions.setdefault(removal.stock_fixture_id, []).append(region)
    return {stock_fixture_id: tuple(sorted(boxes, key=_canonical_box)) for stock_fixture_id, boxes in regions.items()}


def _result_level(findings: Sequence[TaskCollisionFinding], default: _EvidenceLevel) -> _EvidenceLevel:
    safety_relevant_findings = tuple(
        finding for finding in findings if finding.finding_kind != "allowed-removal-contact"
    )
    if any(finding.evidence_level == "Observed" for finding in safety_relevant_findings):
        return "Observed"
    if any(finding.evidence_level == "Validated" for finding in safety_relevant_findings):
        return "Validated"
    return default


def _subtract_union_bounded(
    source_boxes: Sequence[AxisAlignedBoundingBox],
    cutters: Sequence[AxisAlignedBoundingBox],
    *,
    max_fragments: int,
) -> tuple[AxisAlignedBoundingBox, ...]:
    remaining = tuple(source_boxes)
    for cutter in cutters:
        next_remaining: list[AxisAlignedBoundingBox] = []
        for box in remaining:
            next_remaining.extend(_subtract_box(box, cutter))
            if len(next_remaining) > max_fragments:
                raise UnsupportedRegularizedDifference("UnsupportedRegularizedDifference")
        remaining = tuple(next_remaining)
    return tuple(sorted(remaining, key=_canonical_box))


def _snapshot_validation_reason(
    snapshot: _StockStateSnapshot | None,
    expected_content_id: str,
    *,
    role: Literal["Input", "Output"],
) -> str | None:
    if snapshot is None:
        return f"Missing{role}Snapshot"
    if snapshot.declared_content_id is not None and snapshot.declared_content_id != snapshot.actual_content_id:
        return f"Provided{role}SnapshotHashMismatch"
    if snapshot.actual_content_id != expected_content_id:
        return f"{role}SnapshotHashMismatch"
    return None


def evaluate_task_collision(
    task: M2CandidateTaskGeometry,
    *,
    stock_state_geometries: Mapping[str, Mapping[str, Sequence[Any]]] | None = None,
    max_subdivision_depth: int = _MAX_SUBDIVISION_DEPTH,
    max_regularized_difference_fragments: int = _MAX_REGULARIZED_DIFFERENCE_FRAGMENTS,
) -> TaskCollisionEvaluation:
    if getattr(task, "collision_context", None) is None:
        return TaskCollisionEvaluation(
            collision_free=None,
            overcut_free=None,
            minimum_clearance_lower_bound=None,
            clearance_unit="mm",
            continuous_method="continuous-envelope-recursive",
            subdivision_count=0,
            evaluation_count=0,
            evidence_level="Validated",
            reason_code="CollisionContextRequired",
            findings=(
                TaskCollisionFinding(
                    interval_id="task",
                    finding_kind="insufficient-context",
                    evidence_level="Validated",
                    reason_code="CollisionContextRequired",
                    sigma_start=0.0,
                    sigma_end=1.0,
                ),
            ),
            state_transitions=tuple(),
        )
    state_store = _normalize_state_geometry(stock_state_geometries)
    invalid_state_ids: set[str] = set()

    primitives = {component.component_id: _normalize_tool_component(component) for component in task.collision_context.tool_components}
    threshold = (
        task.collision_context.minimum_clearance.absolute
        + task.collision_context.solver_tolerance.absolute
        + task.collision_context.envelope_tolerance.absolute
    )

    findings: list[TaskCollisionFinding] = []
    transitions: list[TaskCollisionStateTransition] = []
    evaluation_count = 0
    subdivision_count = 0
    clearance_lower_bounds: list[float] = []
    collision_free: bool | None = True
    overcut_free: bool | None = True
    overall_reason: str | None = None

    for interval in task.process_state_timeline.intervals:
        input_state_id = interval.input_stock_state.state_id
        output_state_id = interval.output_stock_state.state_id if interval.output_stock_state is not None else None
        snapshot_policy_id = task.process_state_timeline.stock_update_policy.policy_id
        if input_state_id in invalid_state_ids:
            findings.append(
                TaskCollisionFinding(
                    interval_id=interval.interval_id,
                    finding_kind="upstream-process-state-invalid",
                    evidence_level="Validated",
                    reason_code="UpstreamProcessStateInvalid",
                    sigma_start=interval.sigma_start,
                    sigma_end=interval.sigma_end,
                )
            )
            transitions.append(
                TaskCollisionStateTransition(
                    interval_id=interval.interval_id,
                    status="Blocked",
                    reason_code="UpstreamProcessStateInvalid",
                    input_state_id=input_state_id,
                    output_state_id=output_state_id,
                    evidence_level="Validated",
                )
            )
            collision_free = None
            overcut_free = None
            overall_reason = overall_reason or "UpstreamProcessStateInvalid"
            continue
        input_snapshot = state_store.get(input_state_id)
        input_snapshot_reason = _snapshot_validation_reason(
            input_snapshot,
            interval.input_stock_state.content_id,
            role="Input",
        )
        if input_snapshot_reason is not None:
            findings.append(
                TaskCollisionFinding(
                    interval_id=interval.interval_id,
                    finding_kind="insufficient-context"
                    if input_snapshot_reason == "MissingInputSnapshot"
                    else "invalid-snapshot",
                    evidence_level="Validated",
                    reason_code=input_snapshot_reason,
                    sigma_start=interval.sigma_start,
                    sigma_end=interval.sigma_end,
                )
            )
            transitions.append(
                TaskCollisionStateTransition(
                    interval_id=interval.interval_id,
                    status="Blocked",
                    reason_code=input_snapshot_reason,
                    input_state_id=input_state_id,
                    output_state_id=output_state_id,
                    evidence_level="Validated",
                )
            )
            collision_free = None
            overcut_free = None
            overall_reason = overall_reason or input_snapshot_reason
            continue
        current_state = {
            stock_fixture_id: tuple(sorted(boxes, key=_canonical_box))
            for stock_fixture_id, boxes in input_snapshot.stock_boxes.items()
        }
        explicit_output_snapshot: _StockStateSnapshot | None = None
        if snapshot_policy_id == "five-axis.stock-update.explicit-snapshot@1" and interval.output_stock_state is not None:
            explicit_output_snapshot = state_store.get(interval.output_stock_state.state_id)
            output_snapshot_reason = _snapshot_validation_reason(
                explicit_output_snapshot,
                interval.output_stock_state.content_id,
                role="Output",
            )
            if output_snapshot_reason is not None:
                findings.append(
                    TaskCollisionFinding(
                        interval_id=interval.interval_id,
                        finding_kind="insufficient-context"
                        if output_snapshot_reason == "MissingOutputSnapshot"
                        else "invalid-snapshot",
                        evidence_level="Validated",
                        reason_code=output_snapshot_reason,
                        sigma_start=interval.sigma_start,
                        sigma_end=interval.sigma_end,
                    )
                )
                transitions.append(
                    TaskCollisionStateTransition(
                        interval_id=interval.interval_id,
                        status="Failed",
                        reason_code=output_snapshot_reason,
                        input_state_id=input_state_id,
                        output_state_id=output_state_id,
                        evidence_level="Validated",
                    )
                )
                if output_state_id is not None:
                    invalid_state_ids.add(output_state_id)
                collision_free = None
                overcut_free = None
                overall_reason = overall_reason or output_snapshot_reason
                continue
        try:
            subintervals = _kinematic_subintervals(task, interval.sigma_start, interval.sigma_end)
        except UnsupportedCollisionGeometry as exc:
            reason_code = str(exc)
            findings.append(
                TaskCollisionFinding(
                    interval_id=interval.interval_id,
                    finding_kind="unsupported",
                    evidence_level="Validated",
                    reason_code=reason_code,
                    sigma_start=interval.sigma_start,
                    sigma_end=interval.sigma_end,
                )
            )
            transitions.append(
                TaskCollisionStateTransition(
                    interval_id=interval.interval_id,
                    status="Failed",
                    reason_code=reason_code,
                    input_state_id=input_state_id,
                    output_state_id=output_state_id,
                    evidence_level="Validated",
                )
            )
            if output_state_id is not None:
                invalid_state_ids.add(output_state_id)
            collision_free = None
            overcut_free = None
            overall_reason = overall_reason or reason_code
            continue

        interval_failed = False
        interval_reason: str | None = None
        allowed_regions = _allowed_regions_for_interval(task, interval)
        active_component_id = interval.tool_component_id

        for subinterval in subintervals:
            for component_id, primitive in primitives.items():
                for stock_fixture in task.collision_context.stock_fixtures:
                    if stock_fixture.category == "stock":
                        boxes = current_state.get(stock_fixture.stock_fixture_id, ())
                    else:
                        boxes = (stock_fixture.aabb,)
                    relation = _contact_policy_lookup(task, primitive.component_kind, stock_fixture.category)
                    if stock_fixture.category == "stock" and component_id == active_component_id and relation == "allowed":
                        forbidden_boxes = _subtract_union(boxes, allowed_regions.get(stock_fixture.stock_fixture_id, ()))
                        if not allowed_regions.get(stock_fixture.stock_fixture_id):
                            for stock_box in boxes:
                                result = _refine_forbidden_pair(
                                    primitive,
                                    stock_box,
                                    subinterval,
                                    threshold,
                                    max_depth=max_subdivision_depth,
                                )
                                evaluation_count += result.evaluations
                                subdivision_count += result.subdivisions
                                clearance_lower_bounds.append(result.minimum_clearance_lower_bound)
                                if result.status == "refuted":
                                    findings.append(
                                        TaskCollisionFinding(
                                            interval_id=interval.interval_id,
                                            finding_kind="insufficient-context",
                                            evidence_level="Observed",
                                            reason_code="AllowedRemovalRequired",
                                            component_id=component_id,
                                            stock_fixture_id=stock_fixture.stock_fixture_id,
                                            sigma_start=subinterval.sigma_start,
                                            sigma_end=subinterval.sigma_end,
                                            minimum_clearance_lower_bound=result.minimum_clearance_lower_bound,
                                            sample_sigma=result.sample_sigma,
                                        )
                                    )
                                    interval_failed = True
                                    interval_reason = "AllowedRemovalRequired"
                                    collision_free = None
                                    overcut_free = None
                                    break
                                if result.status == "validated":
                                    findings.append(
                                        TaskCollisionFinding(
                                            interval_id=interval.interval_id,
                                            finding_kind="insufficient-context",
                                            evidence_level="Validated",
                                            reason_code="AllowedRemovalContactUnresolved",
                                            component_id=component_id,
                                            stock_fixture_id=stock_fixture.stock_fixture_id,
                                            sigma_start=subinterval.sigma_start,
                                            sigma_end=subinterval.sigma_end,
                                            minimum_clearance_lower_bound=result.minimum_clearance_lower_bound,
                                        )
                                    )
                                    interval_failed = True
                                    interval_reason = "AllowedRemovalContactUnresolved"
                                    collision_free = None
                                    overcut_free = None
                                    break
                            if interval_failed:
                                break
                        for forbidden_box in forbidden_boxes:
                            result = _refine_forbidden_pair(
                                primitive,
                                forbidden_box,
                                subinterval,
                                threshold,
                                max_depth=max_subdivision_depth,
                            )
                            evaluation_count += result.evaluations
                            subdivision_count += result.subdivisions
                            clearance_lower_bounds.append(result.minimum_clearance_lower_bound)
                            if result.status == "refuted":
                                findings.append(
                                    TaskCollisionFinding(
                                        interval_id=interval.interval_id,
                                        finding_kind="overcut",
                                        evidence_level="Observed",
                                        reason_code="NominalOvercut",
                                        component_id=component_id,
                                        stock_fixture_id=stock_fixture.stock_fixture_id,
                                        sigma_start=subinterval.sigma_start,
                                        sigma_end=subinterval.sigma_end,
                                        minimum_clearance_lower_bound=result.minimum_clearance_lower_bound,
                                        sample_sigma=result.sample_sigma,
                                    )
                                )
                                interval_failed = True
                                interval_reason = "NominalOvercut"
                                collision_free = False if collision_free is not None else None
                                overcut_free = False if overcut_free is not None else None
                                break
                            if result.status == "validated":
                                findings.append(
                                    TaskCollisionFinding(
                                        interval_id=interval.interval_id,
                                        finding_kind="overcut",
                                        evidence_level="Validated",
                                        reason_code="NominalOvercutUnresolved",
                                        component_id=component_id,
                                        stock_fixture_id=stock_fixture.stock_fixture_id,
                                        sigma_start=subinterval.sigma_start,
                                        sigma_end=subinterval.sigma_end,
                                        minimum_clearance_lower_bound=result.minimum_clearance_lower_bound,
                                    )
                                )
                                interval_failed = True
                                interval_reason = "NominalOvercutUnresolved"
                                collision_free = None
                                overcut_free = None
                                break
                        if interval_failed:
                            break
                        if boxes:
                            for stock_box in boxes:
                                result = _refine_forbidden_pair(
                                    primitive,
                                    stock_box,
                                    subinterval,
                                    threshold,
                                    max_depth=max_subdivision_depth,
                                )
                                evaluation_count += result.evaluations
                                subdivision_count += result.subdivisions
                                clearance_lower_bounds.append(result.minimum_clearance_lower_bound)
                                if result.status == "refuted":
                                    findings.append(
                                        TaskCollisionFinding(
                                            interval_id=interval.interval_id,
                                            finding_kind="allowed-removal-contact",
                                            evidence_level=result.evidence_level,
                                            reason_code="AllowedRemovalContact",
                                            component_id=component_id,
                                            stock_fixture_id=stock_fixture.stock_fixture_id,
                                            sigma_start=subinterval.sigma_start,
                                            sigma_end=subinterval.sigma_end,
                                            minimum_clearance_lower_bound=result.minimum_clearance_lower_bound,
                                            sample_sigma=result.sample_sigma,
                                        )
                                    )
                                    break
                                if result.status == "validated":
                                    findings.append(
                                        TaskCollisionFinding(
                                            interval_id=interval.interval_id,
                                            finding_kind="allowed-removal-contact",
                                            evidence_level="Validated",
                                            reason_code="AllowedRemovalContactUnresolved",
                                            component_id=component_id,
                                            stock_fixture_id=stock_fixture.stock_fixture_id,
                                            sigma_start=subinterval.sigma_start,
                                            sigma_end=subinterval.sigma_end,
                                            minimum_clearance_lower_bound=result.minimum_clearance_lower_bound,
                                        )
                                    )
                                    interval_failed = True
                                    interval_reason = "AllowedRemovalContactUnresolved"
                                    collision_free = None
                                    overcut_free = None
                                    break
                        continue
                    if relation != "forbidden":
                        continue
                    for obstacle_box in boxes:
                        result = _refine_forbidden_pair(
                            primitive,
                            obstacle_box,
                            subinterval,
                            threshold,
                            max_depth=max_subdivision_depth,
                        )
                        evaluation_count += result.evaluations
                        subdivision_count += result.subdivisions
                        clearance_lower_bounds.append(result.minimum_clearance_lower_bound)
                        if result.status == "refuted":
                            findings.append(
                                TaskCollisionFinding(
                                    interval_id=interval.interval_id,
                                    finding_kind="forbidden-contact",
                                    evidence_level="Observed",
                                    reason_code="ForbiddenContact",
                                    component_id=component_id,
                                    stock_fixture_id=stock_fixture.stock_fixture_id,
                                    sigma_start=subinterval.sigma_start,
                                    sigma_end=subinterval.sigma_end,
                                    minimum_clearance_lower_bound=result.minimum_clearance_lower_bound,
                                    sample_sigma=result.sample_sigma,
                                )
                            )
                            interval_failed = True
                            interval_reason = "ForbiddenContact"
                            collision_free = False if collision_free is not None else None
                            break
                        if result.status == "validated":
                            findings.append(
                                TaskCollisionFinding(
                                    interval_id=interval.interval_id,
                                    finding_kind="forbidden-contact",
                                    evidence_level="Validated",
                                    reason_code="ForbiddenContactUnresolved",
                                    component_id=component_id,
                                    stock_fixture_id=stock_fixture.stock_fixture_id,
                                    sigma_start=subinterval.sigma_start,
                                    sigma_end=subinterval.sigma_end,
                                    minimum_clearance_lower_bound=result.minimum_clearance_lower_bound,
                                )
                            )
                            interval_failed = True
                            interval_reason = "ForbiddenContactUnresolved"
                            collision_free = None
                            overcut_free = None
                            break
                    if interval_failed:
                        break
                if interval_failed:
                    break
            if interval_failed:
                break

        if interval_failed:
            transitions.append(
                TaskCollisionStateTransition(
                    interval_id=interval.interval_id,
                    status="Failed",
                    reason_code=interval_reason or "CollisionEvaluationFailed",
                    input_state_id=input_state_id,
                    output_state_id=output_state_id,
                    evidence_level="Observed" if interval_reason in {"ForbiddenContact", "NominalOvercut"} else "Validated",
                )
            )
            if output_state_id is not None:
                invalid_state_ids.add(output_state_id)
            overall_reason = overall_reason or interval_reason
            continue

        next_state = current_state
        produced_content_id: str | None
        if snapshot_policy_id == "five-axis.stock-update.nominal-sweep@1":
            if active_component_id is not None and active_component_id in primitives:
                active_primitive = primitives[active_component_id]
                stock_contact_logged = any(
                    finding.interval_id == interval.interval_id and finding.finding_kind == "allowed-removal-contact"
                    for finding in findings
                )
                if stock_contact_logged:
                    if active_primitive.kind != "aabb":
                        interval_reason = "UnsupportedRegularizedDifference"
                        if output_state_id is not None:
                            invalid_state_ids.add(output_state_id)
                        transitions.append(
                            TaskCollisionStateTransition(
                                interval_id=interval.interval_id,
                                status="Failed",
                                reason_code=interval_reason,
                                input_state_id=input_state_id,
                                output_state_id=output_state_id,
                                evidence_level="Validated",
                            )
                        )
                        collision_free = None
                        overcut_free = None
                        overall_reason = overall_reason or interval_reason
                        continue
                    removal_boxes: list[AxisAlignedBoundingBox] = []
                    for subinterval in subintervals:
                        removal_box = _swept_aabb_for_translation(active_primitive, subinterval)
                        removal_boxes.append(removal_box)
                    exact_allowed = [
                        box
                        for boxes in allowed_regions.values()
                        for box in boxes
                    ]
                    if not exact_allowed or not _boxes_subset_of(removal_boxes, exact_allowed):
                        interval_reason = "UnsupportedRegularizedDifference"
                        if output_state_id is not None:
                            invalid_state_ids.add(output_state_id)
                        transitions.append(
                            TaskCollisionStateTransition(
                                interval_id=interval.interval_id,
                                status="Failed",
                                reason_code=interval_reason,
                                input_state_id=input_state_id,
                                output_state_id=output_state_id,
                                evidence_level="Validated",
                            )
                        )
                        collision_free = None
                        overcut_free = None
                        overall_reason = overall_reason or interval_reason
                        continue
                    try:
                        next_state = {
                            stock_fixture_id: _subtract_union_bounded(
                                boxes,
                                removal_boxes,
                                max_fragments=max_regularized_difference_fragments,
                            )
                            for stock_fixture_id, boxes in current_state.items()
                        }
                    except UnsupportedRegularizedDifference as exc:
                        interval_reason = str(exc)
                        if output_state_id is not None:
                            invalid_state_ids.add(output_state_id)
                        transitions.append(
                            TaskCollisionStateTransition(
                                interval_id=interval.interval_id,
                                status="Failed",
                                reason_code=interval_reason,
                                input_state_id=input_state_id,
                                output_state_id=output_state_id,
                                evidence_level="Validated",
                            )
                        )
                        collision_free = None
                        overcut_free = None
                        overall_reason = overall_reason or interval_reason
                        continue
            produced_content_id = hash_state_geometry(next_state)
            if interval.output_stock_state is not None and produced_content_id != interval.output_stock_state.content_id:
                interval_reason = "OutputSnapshotHashMismatch"
                transitions.append(
                    TaskCollisionStateTransition(
                        interval_id=interval.interval_id,
                        status="Failed",
                        reason_code=interval_reason,
                        input_state_id=input_state_id,
                        output_state_id=output_state_id,
                        produced_content_id=produced_content_id,
                        evidence_level="Validated",
                    )
                )
                findings.append(
                    TaskCollisionFinding(
                        interval_id=interval.interval_id,
                        finding_kind="invalid-snapshot",
                        evidence_level="Validated",
                        reason_code=interval_reason,
                        sigma_start=interval.sigma_start,
                        sigma_end=interval.sigma_end,
                    )
                )
                if output_state_id is not None:
                    invalid_state_ids.add(output_state_id)
                collision_free = None
                overcut_free = None
                overall_reason = overall_reason or interval_reason
                continue
            if output_state_id is not None:
                state_store[output_state_id] = _StockStateSnapshot(
                    actual_content_id=produced_content_id,
                    declared_content_id=interval.output_stock_state.content_id if interval.output_stock_state is not None else None,
                    stock_boxes={
                        stock_fixture_id: tuple(sorted(boxes, key=_canonical_box))
                        for stock_fixture_id, boxes in next_state.items()
                    },
                )
        else:
            produced_content_id = explicit_output_snapshot.actual_content_id if explicit_output_snapshot is not None else None
        transitions.append(
            TaskCollisionStateTransition(
                interval_id=interval.interval_id,
                status="Succeeded",
                reason_code="CollisionCertified" if not any(
                    finding.interval_id == interval.interval_id and finding.evidence_level == "Validated"
                    for finding in findings
                ) else "CollisionValidated",
                input_state_id=input_state_id,
                output_state_id=output_state_id,
                produced_content_id=produced_content_id,
                evidence_level="Certified"
                if not any(finding.interval_id == interval.interval_id and finding.evidence_level == "Validated" for finding in findings)
                else "Validated",
            )
        )

    if overall_reason is None:
        if collision_free is False:
            overall_reason = "ForbiddenContact"
        elif overcut_free is False:
            overall_reason = "NominalOvercut"
        else:
            overall_reason = "CollisionCertified" if not findings or _result_level(findings, "Certified") == "Certified" else "CollisionValidated"
    minimum_clearance_lower_bound = min(clearance_lower_bounds) if clearance_lower_bounds else None
    return TaskCollisionEvaluation(
        collision_free=collision_free,
        overcut_free=overcut_free,
        minimum_clearance_lower_bound=minimum_clearance_lower_bound,
        clearance_unit=task.collision_context.minimum_clearance.unit,
        continuous_method="continuous-envelope-recursive",
        subdivision_count=subdivision_count,
        evaluation_count=evaluation_count,
        evidence_level=_result_level(findings, "Certified"),
        reason_code=overall_reason,
        findings=tuple(findings),
        state_transitions=tuple(transitions),
    )


__all__ = [
    "TaskCollisionEvaluation",
    "TaskCollisionFinding",
    "TaskCollisionStateTransition",
    "UnsupportedCollisionGeometry",
    "UnsupportedRegularizedDifference",
    "evaluate_task_collision",
    "hash_state_geometry",
]
