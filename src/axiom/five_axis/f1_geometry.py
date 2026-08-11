from __future__ import annotations

import json
import math
from typing import Literal

import numpy as np
from pydantic import Field
from scipy.interpolate import BSpline

from ..models import AxiomModel
from .f1_models import (
    ArcPositionSegment,
    BezierPositionSegment,
    BSplinePositionSegment,
    ConstantOrientationSegment,
    CorrespondenceCertificate,
    CorrespondenceInterval,
    CorrespondencePolicy,
    HelixPositionSegment,
    LinePositionSegment,
    M1ReferencePath,
    M2CandidateTaskGeometry,
    MonotoneMinimaxPolicy,
    OrientationSegment,
    PathProgress,
    PositionSegment,
    ProvenanceProgressPolicy,
    SelectedNodeMapping,
    CanonicalNode,
    NumericTolerance,
    SlerpOrientationSegment,
    SourceSegmentAllowedTargetIntervals,
    SourceLineage,
)


_EPSILON = 1e-12
_GEOMETRY_TOLERANCE = 1e-9
_MINIMAX_GRID_SIZE = 33
_PROVENANCE_SOLVER_VERSION = "five-axis.correspondence.provenance-progress@1"
_MINIMAX_SOLVER_VERSION = "five-axis.correspondence.monotone-minimax.grid-dp@1"

GeometryPath = M1ReferencePath | M2CandidateTaskGeometry


class GeometryEvaluationError(ValueError):
    """Raised when an F1 continuous geometry cannot be evaluated deterministically."""


class UndefinedCorrespondenceError(ValueError):
    """Raised when a correspondence policy does not define a usable mapping."""


class ScalarSupBound(AxiomModel):
    level: Literal["Exact", "Certified", "Validated"]
    bound_semantics: Literal["rigorous-continuous", "observed-samples"] = Field(alias="boundSemantics")
    lower: float = Field(ge=0)
    upper: float = Field(ge=0)
    gap: float = Field(ge=0)
    evaluations: int = Field(ge=0)
    method: str = Field(min_length=1)


class ActualToReferenceContinuousErrorCertificate(AxiomModel):
    certificate_id: str = Field(alias="certificateId", min_length=1)
    source_geometry_id: str = Field(alias="sourceGeometryId", min_length=1)
    target_reference_path_id: str = Field(alias="targetReferencePathId", min_length=1)
    correspondence_certificate_id: str = Field(alias="correspondenceCertificateId", min_length=1)
    position: ScalarSupBound | None = None
    tool_axis_angle: ScalarSupBound | None = Field(default=None, alias="toolAxisAngle")


ContinuousErrorCertificate = ActualToReferenceContinuousErrorCertificate


def evaluate_position(path: GeometryPath, sigma: float) -> tuple[float, float, float]:
    if _position_segments(path):
        segment = _select_segment(_position_segments(path), sigma, start_attr="sigma_start", end_attr="sigma_end")
        local = _local_parameter(segment.sigma_start, segment.sigma_end, sigma)
        return _tuple3(_evaluate_position_segment(segment, local))
    if path.static_position is not None:
        _require_unit_interval(sigma)
        return path.static_position
    raise GeometryEvaluationError("position evaluation requires positionSegments or staticPosition")


def evaluate_tool_axis(path: GeometryPath, sigma: float) -> tuple[float, float, float]:
    segment = _select_segment(_orientation_segments(path), sigma, start_attr="sigma_start", end_attr="sigma_end")
    local = _local_parameter(segment.sigma_start, segment.sigma_end, sigma)
    return _tuple3(_evaluate_orientation_segment(segment, local))


def apply_correspondence(certificate: CorrespondenceCertificate, source_sigma: float) -> float:
    interval = _select_interval(certificate.intervals, source_sigma)
    return _map_sigma(interval, source_sigma)


def build_provenance_progress_correspondence(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    policy: ProvenanceProgressPolicy,
    *,
    certificate_id: str = "f1-provenance-progress-certificate",
) -> CorrespondenceCertificate:
    start, end = _non_empty_allowed_interval(policy.allowed_source_interval)
    _require_same_progress(actual_geometry.path_progress, reference_path.path_progress)
    _require_same_path_lineage(actual_geometry, reference_path, start, end)

    split_points = _partition_points_for_identity(actual_geometry, reference_path, start, end)
    intervals: list[CorrespondenceInterval] = []
    for index, (left, right) in enumerate(zip(split_points, split_points[1:])):
        midpoint = (left + right) * 0.5
        source_segment = _segment_at(_active_segments(actual_geometry), midpoint)
        target_segment = _segment_at(_active_segments(reference_path), midpoint)
        intervals.append(
            CorrespondenceInterval(
                intervalId=f"provenance-interval-{index:04d}",
                sourceSigmaStart=left,
                sourceSigmaEnd=right,
                targetSigmaStart=left,
                targetSigmaEnd=right,
                sourceSegmentId=source_segment.segment_id if source_segment is not None else None,
                targetSegmentId=target_segment.segment_id if target_segment is not None else None,
                correspondenceStatus="matched",
            )
        )

    return CorrespondenceCertificate(
        certificateId=certificate_id,
        sourceGeometryId=_geometry_id(actual_geometry),
        targetReferencePathId=reference_path.reference_path_id,
        policy=policy,
        canonicalNodes=_canonical_nodes_for_provenance(actual_geometry, reference_path, start, end),
        allowedSourceIntervals=_allowed_target_intervals_by_source_segment(actual_geometry, policy.allowed_target_interval),
        selectedNodeMapping=_selected_identity_node_mapping(actual_geometry, reference_path, start, end),
        intervals=tuple(intervals),
        primaryObjectiveLower=0.0,
        primaryObjectiveUpper=0.0,
        objectiveDomain="continuous",
        tieBreakObjective="identity-sigma",
        numericTolerance=policy.numeric_tolerance,
        solverVersion=_PROVENANCE_SOLVER_VERSION,
        evidenceLevel="machine-replayable",
    )


def build_monotone_minimax_correspondence(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    policy: MonotoneMinimaxPolicy,
    *,
    certificate_id: str = "f1-monotone-minimax-certificate",
    grid_size: int = _MINIMAX_GRID_SIZE,
) -> CorrespondenceCertificate:
    source_start, source_end = _non_empty_allowed_interval(policy.allowed_source_interval)
    target_start, target_end = _non_empty_allowed_interval(policy.allowed_target_interval)
    source_sigmas = _canonical_grid(actual_geometry, source_start, source_end, grid_size)
    target_sigmas = _canonical_grid(reference_path, target_start, target_end, grid_size)
    source_points = np.asarray([evaluate_position(actual_geometry, sigma) for sigma in source_sigmas], dtype=np.float64)
    target_points = np.asarray([evaluate_position(reference_path, sigma) for sigma in target_sigmas], dtype=np.float64)
    distances = np.linalg.norm(source_points[:, np.newaxis, :] - target_points[np.newaxis, :, :], axis=2)

    objective = _monotone_minimax_objective(distances)
    assignments = _lexicographic_monotone_assignment(distances, objective)

    intervals: list[CorrespondenceInterval] = []
    for index, (source_left, source_right, target_left_index, target_right_index) in enumerate(
        zip(source_sigmas, source_sigmas[1:], assignments, assignments[1:])
    ):
        target_left = target_sigmas[target_left_index]
        target_right = target_sigmas[target_right_index]
        midpoint = (source_left + source_right) * 0.5
        target_midpoint = target_left if math.isclose(target_left, target_right, abs_tol=_EPSILON) else (
            target_left + target_right
        ) * 0.5
        source_segment = _segment_at(_active_segments(actual_geometry), midpoint)
        target_segment = _segment_at(_active_segments(reference_path), target_midpoint)
        status = "collapsed" if math.isclose(target_left, target_right, abs_tol=_EPSILON) else "matched"
        intervals.append(
            CorrespondenceInterval(
                intervalId=f"minimax-interval-{index:04d}",
                sourceSigmaStart=source_left,
                sourceSigmaEnd=source_right,
                targetSigmaStart=target_left,
                targetSigmaEnd=target_right,
                sourceSegmentId=source_segment.segment_id if source_segment is not None else None,
                targetSegmentId=target_segment.segment_id if target_segment is not None else None,
                correspondenceStatus=status,
            )
        )

    canonical_nodes = _canonical_nodes_for_grid(actual_geometry, reference_path, source_sigmas, target_sigmas)
    selected_node_mapping = _selected_grid_node_mapping(actual_geometry, reference_path, source_sigmas, target_sigmas, assignments)

    return CorrespondenceCertificate(
        certificateId=certificate_id,
        sourceGeometryId=_geometry_id(actual_geometry),
        targetReferencePathId=reference_path.reference_path_id,
        policy=policy,
        canonicalNodes=canonical_nodes,
        allowedSourceIntervals=_allowed_target_intervals_by_source_segment(actual_geometry, policy.allowed_target_interval),
        selectedNodeMapping=selected_node_mapping,
        intervals=tuple(intervals),
        primaryObjectiveLower=objective,
        primaryObjectiveUpper=objective,
        objectiveDomain="canonical-grid",
        tieBreakObjective=policy.deterministic_tie_break,
        numericTolerance=policy.numeric_tolerance,
        solverVersion=_MINIMAX_SOLVER_VERSION,
        evidenceLevel="certificate-summary",
    )


def compute_actual_to_reference_continuous_error_certificate(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    correspondence: CorrespondenceCertificate,
    *,
    certificate_id: str = "f1-continuous-error-certificate",
    certified_gap_tolerance: float = 1e-6,
    max_depth: int = 14,
    validated_samples: int = 257,
) -> ActualToReferenceContinuousErrorCertificate:
    _require_correspondence_matches(actual_geometry, reference_path, correspondence)
    position_bound = None
    tool_axis_bound = None
    if _has_position(actual_geometry) and _has_position(reference_path):
        position_bound = _compute_scalar_bound(
            actual_geometry,
            reference_path,
            correspondence,
            quantity="position",
            certified_gap_tolerance=certified_gap_tolerance,
            max_depth=max_depth,
            validated_samples=validated_samples,
        )
    if _orientation_segments(actual_geometry) and _orientation_segments(reference_path):
        tool_axis_bound = _compute_scalar_bound(
            actual_geometry,
            reference_path,
            correspondence,
            quantity="orientation",
            certified_gap_tolerance=certified_gap_tolerance,
            max_depth=max_depth,
            validated_samples=validated_samples,
        )
    return ActualToReferenceContinuousErrorCertificate(
        certificateId=certificate_id,
        sourceGeometryId=_geometry_id(actual_geometry),
        targetReferencePathId=reference_path.reference_path_id,
        correspondenceCertificateId=correspondence.certificate_id,
        position=position_bound,
        toolAxisAngle=tool_axis_bound,
    )


def compute_continuous_error_certificate(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    correspondence: CorrespondenceCertificate,
    *,
    certificate_id: str = "f1-continuous-error-certificate",
    certified_gap_tolerance: float = 1e-6,
    max_depth: int = 14,
    validated_samples: int = 257,
) -> ActualToReferenceContinuousErrorCertificate:
    return compute_actual_to_reference_continuous_error_certificate(
        actual_geometry,
        reference_path,
        correspondence,
        certificate_id=certificate_id,
        certified_gap_tolerance=certified_gap_tolerance,
        max_depth=max_depth,
        validated_samples=validated_samples,
    )


def _compute_scalar_bound(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    correspondence: CorrespondenceCertificate,
    *,
    quantity: Literal["position", "orientation"],
    certified_gap_tolerance: float,
    max_depth: int,
    validated_samples: int,
) -> ScalarSupBound:
    source_start, source_end = correspondence.policy.allowed_source_interval
    if _is_exact_identity(actual_geometry, reference_path, correspondence, quantity=quantity):
        return ScalarSupBound(
            level="Exact",
            boundSemantics="rigorous-continuous",
            lower=0.0,
            upper=0.0,
            gap=0.0,
            evaluations=0,
            method="analytic-identity",
        )

    if quantity == "position":
        unsupported = _contains_nurbs(_position_segments(actual_geometry)) or _contains_nurbs(_position_segments(reference_path))
    else:
        unsupported = False
    if unsupported:
        return _validated_sampling_bound(
            actual_geometry,
            reference_path,
            correspondence,
            quantity=quantity,
            samples=validated_samples,
            method="validated-sampling-no-rigorous-derivative",
        )

    partitions = _smooth_partitions(actual_geometry, reference_path, correspondence, quantity=quantity)
    evaluator_cache: dict[float, float] = {}

    def evaluate_scalar(sigma: float) -> float:
        key = round(sigma, 15)
        if key not in evaluator_cache:
            reference_sigma = apply_correspondence(correspondence, sigma)
            if quantity == "position":
                left = np.asarray(evaluate_position(actual_geometry, sigma), dtype=np.float64)
                right = np.asarray(evaluate_position(reference_path, reference_sigma), dtype=np.float64)
                evaluator_cache[key] = float(np.linalg.norm(left - right))
            else:
                left = np.asarray(evaluate_tool_axis(actual_geometry, sigma), dtype=np.float64)
                right = np.asarray(evaluate_tool_axis(reference_path, reference_sigma), dtype=np.float64)
                evaluator_cache[key] = _angular_distance(left, right)
        return evaluator_cache[key]

    lower = 0.0
    upper = 0.0
    conservative = True
    for left, right in zip(partitions, partitions[1:]):
        lipschitz = _scalar_lipschitz_bound(
            actual_geometry,
            reference_path,
            correspondence,
            quantity=quantity,
            start=left,
            end=right,
        )
        if lipschitz is None:
            conservative = False
            break
        piece_lower, piece_upper = _adaptive_lipschitz_bound(
            evaluate_scalar,
            start=left,
            end=right,
            lipschitz=lipschitz,
            target_gap=certified_gap_tolerance,
            depth=max_depth,
        )
        lower = max(lower, piece_lower)
        upper = max(upper, piece_upper)

    if conservative and upper - lower <= certified_gap_tolerance:
        return ScalarSupBound(
            level="Certified",
            boundSemantics="rigorous-continuous",
            lower=lower,
            upper=upper,
            gap=upper - lower,
            evaluations=len(evaluator_cache),
            method=f"adaptive-lipschitz-{quantity}",
        )

    validated = _validated_sampling_bound(
        actual_geometry,
        reference_path,
        correspondence,
        quantity=quantity,
        samples=max(validated_samples, len(evaluator_cache) or 0),
        method=f"validated-sampling-fallback-{quantity}",
    )
    if conservative:
        return ScalarSupBound(
            level="Validated",
            boundSemantics="rigorous-continuous",
            lower=max(lower, validated.lower),
            upper=max(upper, validated.upper),
            gap=max(upper, validated.upper) - max(lower, validated.lower),
            evaluations=validated.evaluations,
            method=f"validated-after-conservative-gap-{quantity}",
        )
    return validated


def _validated_sampling_bound(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    correspondence: CorrespondenceCertificate,
    *,
    quantity: Literal["position", "orientation"],
    samples: int,
    method: str,
) -> ScalarSupBound:
    start, end = correspondence.policy.allowed_source_interval
    sigma_values = np.linspace(start, end, num=max(samples, 2), dtype=np.float64)
    values: list[float] = []
    for sigma in sigma_values:
        reference_sigma = apply_correspondence(correspondence, float(sigma))
        if quantity == "position":
            left = np.asarray(evaluate_position(actual_geometry, float(sigma)), dtype=np.float64)
            right = np.asarray(evaluate_position(reference_path, reference_sigma), dtype=np.float64)
            values.append(float(np.linalg.norm(left - right)))
        else:
            left = np.asarray(evaluate_tool_axis(actual_geometry, float(sigma)), dtype=np.float64)
            right = np.asarray(evaluate_tool_axis(reference_path, reference_sigma), dtype=np.float64)
            values.append(_angular_distance(left, right))
    observed = max(values, default=0.0)
    return ScalarSupBound(
        level="Validated",
        boundSemantics="observed-samples",
        lower=observed,
        upper=observed,
        gap=0.0,
        evaluations=len(values),
        method=method,
    )


def _adaptive_lipschitz_bound(
    evaluator,
    *,
    start: float,
    end: float,
    lipschitz: float,
    target_gap: float,
    depth: int,
) -> tuple[float, float]:
    left_value = evaluator(start)
    right_value = evaluator(end)
    if math.isclose(start, end, abs_tol=_EPSILON):
        value = max(left_value, right_value)
        return value, value
    lower = max(left_value, right_value)
    upper = lower + lipschitz * (end - start) * 0.5
    if depth <= 0 or upper - lower <= target_gap:
        return lower, upper
    midpoint = (start + end) * 0.5
    left_lower, left_upper = _adaptive_lipschitz_bound(
        evaluator,
        start=start,
        end=midpoint,
        lipschitz=lipschitz,
        target_gap=target_gap,
        depth=depth - 1,
    )
    right_lower, right_upper = _adaptive_lipschitz_bound(
        evaluator,
        start=midpoint,
        end=end,
        lipschitz=lipschitz,
        target_gap=target_gap,
        depth=depth - 1,
    )
    return max(left_lower, right_lower), max(left_upper, right_upper)


def _scalar_lipschitz_bound(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    correspondence: CorrespondenceCertificate,
    *,
    quantity: Literal["position", "orientation"],
    start: float,
    end: float,
) -> float | None:
    midpoint = (start + end) * 0.5
    source_interval = _select_interval(correspondence.intervals, midpoint)
    phi_slope = _phi_slope(source_interval)
    reference_start = _map_sigma(source_interval, start)
    reference_end = _map_sigma(source_interval, end)
    if quantity == "position":
        source_speed = _position_speed_bound_at(actual_geometry, midpoint)
        target_speed = _position_speed_bound_at(reference_path, (reference_start + reference_end) * 0.5)
    else:
        source_segment = _segment_at(_orientation_segments(actual_geometry), midpoint)
        target_segment = _segment_at(_orientation_segments(reference_path), (reference_start + reference_end) * 0.5)
        if source_segment is None or target_segment is None:
            raise GeometryEvaluationError("orientation segments are required for orientation bounds")
        source_speed = _orientation_speed_bound(source_segment)
        target_speed = _orientation_speed_bound(target_segment)
    if source_speed is None or target_speed is None:
        return None
    return source_speed + abs(phi_slope) * target_speed


def _position_speed_bound(segment: PositionSegment) -> float | None:
    width = segment.sigma_end - segment.sigma_start
    if math.isclose(width, 0.0, abs_tol=_EPSILON):
        return 0.0
    if isinstance(segment, LinePositionSegment):
        return float(np.linalg.norm(_to_array(segment.end_point) - _to_array(segment.start_point)) / width)
    if isinstance(segment, ArcPositionSegment):
        _validate_arc_geometry(segment)
        return abs(segment.sweep_radians) * segment.radius / width
    if isinstance(segment, HelixPositionSegment):
        angular = 2.0 * math.pi * segment.turns * segment.radius
        axial = segment.pitch_per_turn * segment.turns
        return math.hypot(angular, axial) / width
    if isinstance(segment, BezierPositionSegment):
        degree = len(segment.control_points) - 1
        diffs = [_to_array(right) - _to_array(left) for left, right in zip(segment.control_points, segment.control_points[1:])]
        return degree * max((float(np.linalg.norm(diff)) for diff in diffs), default=0.0) / width
    if isinstance(segment, BSplinePositionSegment):
        if segment.weights is not None:
            return None
        derivative_control = _bspline_derivative_controls(segment)
        return max((float(np.linalg.norm(item)) for item in derivative_control), default=0.0) / width
    raise GeometryEvaluationError(f"unsupported position segment type: {segment.segment_type}")


def _position_speed_bound_at(path: GeometryPath, sigma: float) -> float | None:
    if _position_segments(path):
        segment = _segment_at(_position_segments(path), sigma)
        if segment is None:
            raise GeometryEvaluationError("position bounds require a valid segment or staticPosition")
        return _position_speed_bound(segment)
    if path.static_position is not None:
        return 0.0
    raise GeometryEvaluationError("position bounds require positionSegments or staticPosition")


def _orientation_speed_bound(segment: OrientationSegment) -> float | None:
    width = segment.sigma_end - segment.sigma_start
    if isinstance(segment, ConstantOrientationSegment):
        return 0.0
    if isinstance(segment, SlerpOrientationSegment):
        dot = _clamp(float(np.dot(_to_array(segment.start_axis), _to_array(segment.end_axis))), -1.0, 1.0)
        angle = math.acos(dot)
        return angle / width
    raise GeometryEvaluationError(f"unsupported orientation segment type: {segment.segment_type}")


def _evaluate_position_segment(segment: PositionSegment, local: float) -> np.ndarray:
    _require_unit_interval(local)
    if isinstance(segment, LinePositionSegment):
        start = _to_array(segment.start_point)
        end = _to_array(segment.end_point)
        return start + (end - start) * local
    if isinstance(segment, ArcPositionSegment):
        return _evaluate_arc(segment, local)
    if isinstance(segment, HelixPositionSegment):
        return _evaluate_helix(segment, local)
    if isinstance(segment, BezierPositionSegment):
        return _evaluate_bezier(segment.control_points, local)
    if isinstance(segment, BSplinePositionSegment):
        return _evaluate_bspline(segment, local)
    raise GeometryEvaluationError(f"unsupported position segment type: {segment.segment_type}")


def _evaluate_orientation_segment(segment: OrientationSegment, local: float) -> np.ndarray:
    _require_unit_interval(local)
    if isinstance(segment, ConstantOrientationSegment):
        return _unit(_to_array(segment.axis))
    if isinstance(segment, SlerpOrientationSegment):
        start = _unit(_to_array(segment.start_axis))
        end = _unit(_to_array(segment.end_axis))
        dot = _clamp(float(np.dot(start, end)), -1.0, 1.0)
        if math.isclose(dot, -1.0, abs_tol=1e-9):
            raise GeometryEvaluationError("antipodal tool-axis interpolation is rejected")
        if math.isclose(dot, 1.0, abs_tol=1e-12):
            return _unit((1.0 - local) * start + local * end)
        angle = math.acos(dot)
        sine = math.sin(angle)
        return _unit((math.sin((1.0 - local) * angle) / sine) * start + (math.sin(local * angle) / sine) * end)
    raise GeometryEvaluationError(f"unsupported orientation segment type: {segment.segment_type}")


def _evaluate_arc(segment: ArcPositionSegment, local: float) -> np.ndarray:
    _validate_arc_geometry(segment)
    return _evaluate_arc_unchecked(segment, local)


def _evaluate_arc_unchecked(segment: ArcPositionSegment, local: float) -> np.ndarray:
    center = _to_array(segment.center)
    start_vector = _to_array(segment.start_point) - center
    normal = _unit(_to_array(segment.normal))
    basis_v = np.cross(normal, start_vector / segment.radius)
    theta = segment.sweep_radians * local
    return center + math.cos(theta) * start_vector + math.sin(theta) * segment.radius * basis_v


def _evaluate_helix(segment: HelixPositionSegment, local: float) -> np.ndarray:
    axis = _unit(_to_array(segment.axis))
    center = _to_array(segment.center)
    radial = _to_array(segment.start_point) - center
    radial = _unit(radial) * segment.radius
    tangential = np.cross(axis, radial / segment.radius)
    theta = 2.0 * math.pi * segment.turns * local
    axial = axis * (segment.pitch_per_turn * segment.turns * local)
    return center + math.cos(theta) * radial + math.sin(theta) * segment.radius * tangential + axial


def _evaluate_bezier(control_points: tuple[tuple[float, float, float], ...], local: float) -> np.ndarray:
    points = np.asarray(control_points, dtype=np.float64)
    while len(points) > 1:
        points = (1.0 - local) * points[:-1] + local * points[1:]
    return points[0]


def _evaluate_bspline(segment: BSplinePositionSegment, local: float) -> np.ndarray:
    spline, domain_scale = _bspline_curve(segment)
    u_min = segment.knots[segment.degree]
    u_max = segment.knots[-segment.degree - 1]
    if not u_max > u_min:
        raise GeometryEvaluationError("B-spline domain must have positive extent")
    u_value = u_min + local * (u_max - u_min)
    evaluated = spline(u_value)
    if np.any(~np.isfinite(evaluated)):
        raise GeometryEvaluationError("B-spline evaluation rejected extrapolation outside the knot domain")
    if segment.weights is None:
        return np.asarray(evaluated, dtype=np.float64)
    numerator = np.asarray(evaluated[:3], dtype=np.float64)
    denominator = float(evaluated[3])
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise GeometryEvaluationError("NURBS denominator must stay positive on the knot domain")
    return numerator / denominator


def _bspline_curve(segment: BSplinePositionSegment) -> tuple[BSpline, float]:
    knots = np.asarray(segment.knots, dtype=np.float64)
    control_points = np.asarray(segment.control_points, dtype=np.float64)
    if segment.weights is None:
        return BSpline(knots, control_points, segment.degree, axis=0, extrapolate=False), knots[-segment.degree - 1] - knots[segment.degree]
    weights = np.asarray(segment.weights, dtype=np.float64)
    homogeneous = np.concatenate([control_points * weights[:, np.newaxis], weights[:, np.newaxis]], axis=1)
    return BSpline(knots, homogeneous, segment.degree, axis=0, extrapolate=False), knots[-segment.degree - 1] - knots[segment.degree]


def _bspline_derivative_controls(segment: BSplinePositionSegment) -> list[np.ndarray]:
    knots = np.asarray(segment.knots, dtype=np.float64)
    points = np.asarray(segment.control_points, dtype=np.float64)
    degree = segment.degree
    controls: list[np.ndarray] = []
    for index in range(len(points) - 1):
        denominator = knots[index + degree + 1] - knots[index + 1]
        if denominator <= 0.0:
            continue
        controls.append((degree / denominator) * (points[index + 1] - points[index]))
    domain_scale = knots[-degree - 1] - knots[degree]
    return [domain_scale * item for item in controls]


def _validate_arc_geometry(segment: ArcPositionSegment) -> None:
    center = _to_array(segment.center)
    start = _to_array(segment.start_point)
    end = _to_array(segment.end_point)
    normal = _unit(_to_array(segment.normal))
    start_vector = start - center
    if not math.isclose(float(np.linalg.norm(start_vector)), segment.radius, rel_tol=0.0, abs_tol=_GEOMETRY_TOLERANCE):
        raise GeometryEvaluationError("arc start point is inconsistent with the declared radius")
    if not math.isclose(float(np.dot(start_vector, normal)), 0.0, abs_tol=_GEOMETRY_TOLERANCE):
        raise GeometryEvaluationError("arc start point must lie in the declared plane")
    predicted_end = _evaluate_arc_unchecked(segment, 1.0)
    if not np.allclose(predicted_end, end, atol=_GEOMETRY_TOLERANCE, rtol=0.0):
        raise GeometryEvaluationError("arc sweep is inconsistent with the declared end point")


def _is_exact_identity(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    correspondence: CorrespondenceCertificate,
    *,
    quantity: Literal["position", "orientation"],
) -> bool:
    if not all(
        math.isclose(interval.source_sigma_start, interval.target_sigma_start, abs_tol=_EPSILON)
        and math.isclose(interval.source_sigma_end, interval.target_sigma_end, abs_tol=_EPSILON)
        for interval in correspondence.intervals
    ):
        return False
    if quantity == "position":
        if bool(_position_segments(actual_geometry)) != bool(_position_segments(reference_path)):
            return False
        if _position_segments(actual_geometry):
            return tuple(
                _exact_segment_signature(segment) for segment in _position_segments(actual_geometry)
            ) == tuple(_exact_segment_signature(segment) for segment in _position_segments(reference_path))
        return actual_geometry.static_position == reference_path.static_position
    return tuple(
        _exact_segment_signature(segment) for segment in _orientation_segments(actual_geometry)
    ) == tuple(_exact_segment_signature(segment) for segment in _orientation_segments(reference_path))


def _partition_points_for_identity(source: GeometryPath, target: GeometryPath, start: float, end: float) -> tuple[float, ...]:
    values = {start, end}
    for segment in _active_segments(source):
        if start < segment.sigma_start < end:
            values.add(segment.sigma_start)
        if start < segment.sigma_end < end:
            values.add(segment.sigma_end)
    for segment in _active_segments(target):
        if start < segment.sigma_start < end:
            values.add(segment.sigma_start)
        if start < segment.sigma_end < end:
            values.add(segment.sigma_end)
    return tuple(sorted(values))


def _canonical_nodes_for_provenance(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    start: float,
    end: float,
) -> tuple[CanonicalNode, ...]:
    return tuple(
        [
            *_canonical_nodes_from_path(actual_geometry, role="source", extra_sigmas=(start, end)),
            *_canonical_nodes_from_path(reference_path, role="target", extra_sigmas=(start, end)),
        ]
    )


def _selected_identity_node_mapping(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    start: float,
    end: float,
) -> tuple[SelectedNodeMapping, ...]:
    source_nodes = _canonical_nodes_from_path(actual_geometry, role="source", extra_sigmas=(start, end))
    target_nodes_by_sigma = {
        _rounded_sigma(node.sigma): node.node_id
        for node in _canonical_nodes_from_path(reference_path, role="target", extra_sigmas=(start, end))
    }
    mappings = [
        SelectedNodeMapping(sourceNodeId=node.node_id, targetNodeId=target_nodes_by_sigma[_rounded_sigma(node.sigma)])
        for node in source_nodes
        if _rounded_sigma(node.sigma) in target_nodes_by_sigma
    ]
    if not mappings:
        raise UndefinedCorrespondenceError("provenance correspondence requires at least one shared canonical sigma")
    return tuple(mappings)


def _canonical_nodes_for_grid(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    source_sigmas: tuple[float, ...],
    target_sigmas: tuple[float, ...],
) -> tuple[CanonicalNode, ...]:
    return tuple(
        [
            *_canonical_nodes_from_path(actual_geometry, role="source", extra_sigmas=source_sigmas),
            *_canonical_nodes_from_path(reference_path, role="target", extra_sigmas=target_sigmas),
        ]
    )


def _selected_grid_node_mapping(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    source_sigmas: tuple[float, ...],
    target_sigmas: tuple[float, ...],
    assignments: tuple[int, ...],
) -> tuple[SelectedNodeMapping, ...]:
    source_nodes = _canonical_nodes_from_path(actual_geometry, role="source", extra_sigmas=(source_sigmas[0], source_sigmas[-1]))
    target_nodes = _canonical_nodes_from_path(reference_path, role="target", extra_sigmas=target_sigmas)
    target_nodes_by_sigma = { _rounded_sigma(node.sigma): node.node_id for node in target_nodes }
    source_grid_index = { _rounded_sigma(sigma): index for index, sigma in enumerate(source_sigmas) }
    used_targets: set[str] = set()
    mappings: list[SelectedNodeMapping] = []
    for node in source_nodes:
        index = source_grid_index.get(_rounded_sigma(node.sigma))
        if index is None:
            continue
        target_sigma = target_sigmas[assignments[index]]
        target_node_id = target_nodes_by_sigma.get(_rounded_sigma(target_sigma))
        if target_node_id is None or target_node_id in used_targets:
            continue
        used_targets.add(target_node_id)
        mappings.append(SelectedNodeMapping(sourceNodeId=node.node_id, targetNodeId=target_node_id))
    if not mappings:
        mappings.append(SelectedNodeMapping(sourceNodeId="source-boundary-start", targetNodeId="target-boundary-start"))
    return tuple(mappings)


def _canonical_nodes_from_path(
    path: GeometryPath,
    *,
    role: Literal["source", "target"],
    extra_sigmas: tuple[float, ...],
) -> tuple[CanonicalNode, ...]:
    items: list[CanonicalNode] = []
    seen: set[tuple[str, float]] = set()
    boundaries = (
        (f"{role}-boundary-start", 0.0),
        (f"{role}-boundary-end", 1.0),
    )
    for node_id, sigma in boundaries:
        items.append(_canonical_node(role=role, node_id=node_id, sigma=sigma, path=path, seen=seen))
    for event in path.node_events:
        items.append(_canonical_node(role=role, node_id=event.node_id, sigma=event.sigma, path=path, seen=seen))
    for index, sigma in enumerate(extra_sigmas):
        node_id = f"{role}-grid-{index:04d}"
        node = _canonical_node(role=role, node_id=node_id, sigma=sigma, path=path, seen=seen, allow_skip=True)
        if node is not None:
            items.append(node)
    return tuple(items)


def _canonical_node(
    *,
    role: Literal["source", "target"],
    node_id: str,
    sigma: float,
    path: GeometryPath,
    seen: set[tuple[str, float]],
    allow_skip: bool = False,
) -> CanonicalNode | None:
    key = (role, _rounded_sigma(sigma))
    if key in seen:
        return None if allow_skip else CanonicalNode(
            pathRole=role,
            nodeId=node_id,
            sigma=sigma,
            segmentId=_segment_at(_active_segments(path), sigma).segment_id,
        )
    seen.add(key)
    return CanonicalNode(
        pathRole=role,
        nodeId=node_id,
        sigma=sigma,
        segmentId=_segment_at(_active_segments(path), sigma).segment_id,
    )


def _allowed_target_intervals_by_source_segment(
    path: GeometryPath,
    target_interval: tuple[float, float],
) -> tuple[SourceSegmentAllowedTargetIntervals, ...]:
    clipped: list[SourceSegmentAllowedTargetIntervals] = []
    target_start, target_end = target_interval
    for segment in _active_segments(path):
        if segment.sigma_end > segment.sigma_start + _EPSILON:
            clipped.append(
                SourceSegmentAllowedTargetIntervals(
                    sourceSegmentId=segment.segment_id,
                    allowedTargetIntervals=((target_start, target_end),),
                )
            )
    if not clipped:
        raise UndefinedCorrespondenceError("allowed source interval does not intersect any active source segment")
    return tuple(clipped)


def _canonical_grid(path: GeometryPath, start: float, end: float, grid_size: int) -> tuple[float, ...]:
    values = {start, end}
    for segment in _active_segments(path):
        if start < segment.sigma_start < end:
            values.add(segment.sigma_start)
        if start < segment.sigma_end < end:
            values.add(segment.sigma_end)
    for event in path.node_events:
        if start < event.sigma < end:
            values.add(event.sigma)
    for index in range(max(grid_size, 2)):
        values.add(start + (end - start) * index / (max(grid_size, 2) - 1))
    return tuple(sorted(values))


def _monotone_minimax_objective(distances: np.ndarray) -> float:
    rows, columns = distances.shape
    dp = np.full((rows, columns), np.inf, dtype=np.float64)
    dp[0, 0] = distances[0, 0]
    for row in range(1, rows):
        prefix = np.minimum.accumulate(dp[row - 1])
        for column in range(columns):
            dp[row, column] = max(distances[row, column], prefix[column])
    return float(dp[-1, -1])


def _lexicographic_monotone_assignment(distances: np.ndarray, objective: float) -> tuple[int, ...]:
    rows, columns = distances.shape
    feasible = np.zeros((rows, columns), dtype=bool)
    feasible[-1, -1] = distances[-1, -1] <= objective + _EPSILON
    suffix = np.zeros(columns, dtype=bool)
    suffix[-1] = feasible[-1, -1]
    for row in range(rows - 2, -1, -1):
        next_suffix = np.zeros(columns, dtype=bool)
        running = False
        for column in range(columns - 1, -1, -1):
            running = running or suffix[column]
            next_suffix[column] = running and distances[row, column] <= objective + _EPSILON
        feasible[row] = next_suffix
        suffix = next_suffix
    if not feasible[0, 0]:
        raise UndefinedCorrespondenceError("monotone minimax grid produced no feasible assignment")
    assignment = [0]
    previous = 0
    for row in range(1, rows - 1):
        chosen = None
        for column in range(previous, columns):
            if feasible[row, column] and distances[row, column] <= objective + _EPSILON:
                chosen = column
                break
        if chosen is None:
            raise UndefinedCorrespondenceError("monotone minimax tie-break reconstruction failed")
        assignment.append(chosen)
        previous = chosen
    assignment.append(columns - 1)
    return tuple(assignment)


def _smooth_partitions(
    source: GeometryPath,
    target: GeometryPath,
    correspondence: CorrespondenceCertificate,
    *,
    quantity: Literal["position", "orientation"],
) -> tuple[float, ...]:
    start, end = correspondence.policy.allowed_source_interval
    values = {start, end}
    source_segments = _position_segments(source) if quantity == "position" else _orientation_segments(source)
    target_segments = _position_segments(target) if quantity == "position" else _orientation_segments(target)
    for interval in correspondence.intervals:
        values.add(interval.source_sigma_start)
        values.add(interval.source_sigma_end)
        for segment in source_segments:
            if interval.source_sigma_start < segment.sigma_start < interval.source_sigma_end:
                values.add(segment.sigma_start)
            if interval.source_sigma_start < segment.sigma_end < interval.source_sigma_end:
                values.add(segment.sigma_end)
        slope = _phi_slope(interval)
        if math.isclose(slope, 0.0, abs_tol=_EPSILON):
            continue
        for segment in target_segments:
            for boundary in (segment.sigma_start, segment.sigma_end):
                if interval.target_sigma_start < boundary < interval.target_sigma_end or interval.target_sigma_end < boundary < interval.target_sigma_start:
                    sigma = interval.source_sigma_start + (boundary - interval.target_sigma_start) / slope
                    if start < sigma < end:
                        values.add(sigma)
    return tuple(sorted(values))


def _contains_nurbs(segments: tuple[PositionSegment, ...]) -> bool:
    return any(isinstance(segment, BSplinePositionSegment) and segment.weights is not None for segment in segments)


def _position_segments(path: GeometryPath) -> tuple[PositionSegment, ...]:
    return path.position_segments


def _orientation_segments(path: GeometryPath) -> tuple[OrientationSegment, ...]:
    return path.orientation_segments


def _active_segments(path: GeometryPath) -> tuple[PositionSegment | OrientationSegment, ...]:
    return path.position_segments if path.position_segments else path.orientation_segments


def _geometry_id(path: GeometryPath) -> str:
    if isinstance(path, M1ReferencePath):
        return path.reference_path_id
    return path.candidate_geometry_id


def _has_position(path: GeometryPath) -> bool:
    return bool(path.position_segments) or path.static_position is not None


def _require_correspondence_matches(
    actual_geometry: GeometryPath,
    reference_path: M1ReferencePath,
    correspondence: CorrespondenceCertificate,
) -> None:
    expected_geometry_id = _geometry_id(actual_geometry)
    if correspondence.source_geometry_id != expected_geometry_id:
        raise UndefinedCorrespondenceError("correspondence sourceGeometryId does not match the actual geometry")
    if correspondence.target_reference_path_id != reference_path.reference_path_id:
        raise UndefinedCorrespondenceError("correspondence targetReferencePathId does not match the reference path")


def _require_same_progress(source: PathProgress, target: PathProgress) -> None:
    if source.schema_version != target.schema_version:
        raise UndefinedCorrespondenceError("PathProgress schemaVersion must match for exact provenance-progress construction")
    if source.progress_id != target.progress_id:
        raise UndefinedCorrespondenceError("PathProgress progressId must match for exact provenance-progress construction")
    if source.model_dump(mode="json", by_alias=True, exclude_none=True) != target.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    ):
        raise UndefinedCorrespondenceError("PathProgress mappings and provenance must match exactly")


def _require_same_path_lineage(source: GeometryPath, target: GeometryPath, start: float, end: float) -> None:
    split_points = _partition_points_for_identity(source, target, start, end)
    for left, right in zip(split_points, split_points[1:]):
        midpoint = (left + right) * 0.5
        source_segment = _segment_at(_active_segments(source), midpoint)
        target_segment = _segment_at(_active_segments(target), midpoint)
        if source_segment is None or target_segment is None:
            raise UndefinedCorrespondenceError("exact provenance-progress construction requires active segments on both paths")
        if _lineage_signature(source_segment.lineage) != _lineage_signature(target_segment.lineage):
            raise UndefinedCorrespondenceError("segment lineage must match for exact provenance-progress construction")


def _lineage_signature(lineage: tuple[SourceLineage, ...]) -> tuple[str, ...]:
    return tuple(
        json.dumps(item.model_dump(mode="json", by_alias=True, exclude_none=True), sort_keys=True, separators=(",", ":"))
        for item in lineage
    )


def _non_empty_allowed_interval(interval: tuple[float, float]) -> tuple[float, float]:
    start, end = interval
    if end - start <= _EPSILON:
        raise UndefinedCorrespondenceError("allowed interval must have positive extent")
    return start, end


def _select_interval(intervals: tuple[CorrespondenceInterval, ...], sigma: float) -> CorrespondenceInterval:
    return _select_segment(intervals, sigma, start_attr="source_sigma_start", end_attr="source_sigma_end")


def _segment_at(
    segments: tuple[PositionSegment | OrientationSegment, ...],
    sigma: float,
) -> PositionSegment | OrientationSegment | None:
    if not segments:
        return None
    return _select_segment(segments, sigma, start_attr="sigma_start", end_attr="sigma_end")


def _select_segment(segments, sigma: float, *, start_attr: str, end_attr: str):
    _require_unit_interval(sigma)
    candidates = []
    for item in segments:
        start = getattr(item, start_attr)
        end = getattr(item, end_attr)
        if start - _EPSILON <= sigma <= end + _EPSILON:
            candidates.append(item)
    if not candidates:
        raise GeometryEvaluationError("sigma is outside the closed segment domain")
    if math.isclose(sigma, 1.0, abs_tol=_EPSILON):
        return candidates[-1]
    for item in candidates:
        if getattr(item, end_attr) > sigma + _EPSILON:
            return item
    return candidates[-1]


def _local_parameter(start: float, end: float, sigma: float) -> float:
    if math.isclose(start, end, abs_tol=_EPSILON):
        return 0.0
    local = (sigma - start) / (end - start)
    return _clamp(local, 0.0, 1.0)


def _map_sigma(interval: CorrespondenceInterval, sigma: float) -> float:
    if math.isclose(interval.source_sigma_start, interval.source_sigma_end, abs_tol=_EPSILON):
        return interval.target_sigma_start
    local = (sigma - interval.source_sigma_start) / (interval.source_sigma_end - interval.source_sigma_start)
    return interval.target_sigma_start + local * (interval.target_sigma_end - interval.target_sigma_start)


def _phi_slope(interval: CorrespondenceInterval) -> float:
    denominator = interval.source_sigma_end - interval.source_sigma_start
    if math.isclose(denominator, 0.0, abs_tol=_EPSILON):
        return 0.0
    return (interval.target_sigma_end - interval.target_sigma_start) / denominator


def _angular_distance(left: np.ndarray, right: np.ndarray) -> float:
    left_unit = _unit(left)
    right_unit = _unit(right)
    return math.acos(_clamp(float(np.dot(left_unit, right_unit)), -1.0, 1.0))


def _require_unit_interval(value: float) -> None:
    if value < -_EPSILON or value > 1.0 + _EPSILON:
        raise GeometryEvaluationError("evaluation sigma must stay within [0, 1]")


def _to_array(value: tuple[float, float, float]) -> np.ndarray:
    return np.asarray(value, dtype=np.float64)


def _tuple3(value: np.ndarray) -> tuple[float, float, float]:
    return tuple(float(item) for item in value.tolist())


def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or math.isclose(norm, 0.0, abs_tol=_EPSILON):
        raise GeometryEvaluationError("vector must be non-zero and finite")
    return vector / norm


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _rounded_sigma(value: float) -> float:
    return round(value, 15)


def _exact_segment_signature(segment: PositionSegment | OrientationSegment) -> str:
    payload = segment.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload.pop("segmentId", None)
    payload.pop("lineage", None)
    payload.pop("provenance", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


__all__ = [
    "ActualToReferenceContinuousErrorCertificate",
    "ContinuousErrorCertificate",
    "GeometryEvaluationError",
    "ScalarSupBound",
    "UndefinedCorrespondenceError",
    "apply_correspondence",
    "build_monotone_minimax_correspondence",
    "build_provenance_progress_correspondence",
    "compute_actual_to_reference_continuous_error_certificate",
    "compute_continuous_error_certificate",
    "evaluate_position",
    "evaluate_tool_axis",
]
