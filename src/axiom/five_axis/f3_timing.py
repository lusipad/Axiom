from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .f1_models import NodeEvent
from .f2_kinematics import normalize_numeric_identity
from .f2_models import JointPolynomialSegment, M3CandidateAxisPath
from .f3_models import (
    AxisConstraintUsage,
    ContinuousTrajectorySpan,
    ContinuousTrajectoryState,
    ContinuousTrajectoryVerification,
    M4ContinuousTrajectory,
    MotionConstraintProfile,
    RealizedNodeContract,
    TimeLawDefinition,
    TrajectoryErrorLedgerEntry,
    TrajectoryOptimality,
)


_EPSILON = 1e-12
_SMOOTHSTEP7_VELOCITY_MAX = 35.0 / 16.0
_SMOOTHSTEP7_ACCELERATION_BOUND = 26.25
_SMOOTHSTEP7_JERK_MAX = 210.0
_CONTINUOUSLY_FEASIBLE_CLAIM_ID = "five-axis.continuously-feasible-claim@1"
_SECOND_ORDER_SOLVER_ID = "five-axis.f3.second-order-optimal@1"
_JERK_SOLVER_ID = "five-axis.f3.smoothstep7-feasible@1"
_VERIFIER_ID = "five-axis.f3.continuous-trajectory-verifier@1"


@dataclass(frozen=True)
class _LinearPathState:
    q0: tuple[float, float, float, float, float]
    qprime: tuple[float, float, float, float, float]


@dataclass(frozen=True)
class _NodeRequirement:
    node_id: str
    sigma: float
    event_type: str
    boundary_mode: Literal["allow-continuous", "mandatory-stop", "dwell"]
    dwell_seconds: float | None
    source: Literal["regularity", "event-type", "profile"]
    refutes_trajectory: bool = False


def _canonical_content_id(model: object) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)  # type: ignore[attr-defined]
    payload = normalize_numeric_identity(payload)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _outward_positive(value: float) -> float:
    return math.nextafter(value, math.inf)


def _is_close(a: float, b: float, *, tolerance: float = 1e-10) -> bool:
    return math.isclose(a, b, rel_tol=0.0, abs_tol=tolerance)


def _vector_close(
    left: tuple[float, float, float, float, float],
    right: tuple[float, float, float, float, float],
    *,
    tolerance: float = 1e-10,
) -> bool:
    return all(_is_close(a, b, tolerance=tolerance) for a, b in zip(left, right, strict=True))


def _vector_scale(
    values: tuple[float, float, float, float, float],
    scale: float,
) -> tuple[float, float, float, float, float]:
    return tuple(component * scale for component in values)


def _vector_add(
    left: tuple[float, float, float, float, float],
    right: tuple[float, float, float, float, float],
) -> tuple[float, float, float, float, float]:
    return tuple(a + b for a, b in zip(left, right, strict=True))


def _continuity_rank(label: str) -> int:
    return {"C0": 0, "C1": 1, "C2": 2, "C3": 3}[label]


def _node_evidence_by_id(path: M3CandidateAxisPath) -> dict[str, object]:
    return {item.node_id: item for item in path.regularity_certificate.node_evidence}


def _segment_slope(segment: JointPolynomialSegment) -> tuple[float, float, float, float, float]:
    if segment.interpolation != "linear":
        raise ValueError("only globally linear jointSegments are supported")
    sigma_span = segment.sigma_end - segment.sigma_start
    if sigma_span <= _EPSILON:
        raise ValueError("zero-width jointSegments are not supported in F3 timing")
    return tuple(component / sigma_span for component in segment.coefficients[1])


def _globally_linear_path_state(path: M3CandidateAxisPath) -> _LinearPathState:
    first_segment = path.joint_segments[0]
    q0 = tuple(first_segment.coefficients[0])
    reference_slope = _segment_slope(first_segment)
    for segment in path.joint_segments:
        slope = _segment_slope(segment)
        if not _vector_close(reference_slope, slope):
            raise ValueError("jointSegments must share one global affine q(sigma) slope")
        expected_start = _vector_add(q0, _vector_scale(reference_slope, segment.sigma_start))
        expected_end = _vector_add(q0, _vector_scale(reference_slope, segment.sigma_end))
        actual_start = tuple(segment.evaluate(segment.sigma_start))
        actual_end = tuple(segment.evaluate(segment.sigma_end))
        if not _vector_close(expected_start, actual_start):
            raise ValueError("jointSegments must lie on one global affine q(sigma) line")
        if not _vector_close(expected_end, actual_end):
            raise ValueError("jointSegments must lie on one global affine q(sigma) line")
    return _LinearPathState(q0=q0, qprime=reference_slope)


def _event_semantic_mode(event: NodeEvent) -> Literal["allow-continuous", "mandatory-stop", "dwell"]:
    if event.event_type == "dwell":
        return "dwell"
    if event.event_type in {
        "mandatory-stop",
        "branch-change",
        "wrap",
        "singularity-boundary",
        "collision-boundary",
        "degenerate-segment",
    }:
        return "mandatory-stop"
    return "allow-continuous"


def _mode_rank(mode: Literal["allow-continuous", "mandatory-stop", "dwell"]) -> int:
    return {"allow-continuous": 0, "mandatory-stop": 1, "dwell": 2}[mode]


def _profile_node_constraints(profile: MotionConstraintProfile) -> dict[str, object]:
    return {item.node_id: item for item in profile.node_constraints}


def _collect_node_requirements(
    path: M3CandidateAxisPath,
    profile: MotionConstraintProfile,
) -> tuple[_NodeRequirement, ...]:
    constraints_by_id = _profile_node_constraints(profile)
    events_by_id = {item.node_id: item for item in path.node_events}
    unknown = set(constraints_by_id).difference(events_by_id)
    if unknown:
        raise ValueError("motionConstraintProfile nodeConstraints must target sourceAxisPath nodeEvents")
    requirements: list[_NodeRequirement] = []
    for event in sorted(path.node_events, key=lambda item: (item.sigma, item.node_id)):
        profile_constraint = constraints_by_id.get(event.node_id)
        semantic_mode = _event_semantic_mode(event)
        profile_mode = profile_constraint.boundary_mode if profile_constraint is not None else "allow-continuous"
        boundary_mode = semantic_mode if _mode_rank(semantic_mode) >= _mode_rank(profile_mode) else profile_mode
        dwell_seconds = profile_constraint.dwell_seconds if profile_constraint is not None else None
        if boundary_mode == "dwell" and dwell_seconds is None:
            raise ValueError("dwell nodeEvents require MotionConstraintProfile dwellSeconds")
        source: Literal["regularity", "event-type", "profile"]
        if profile_constraint is not None and boundary_mode == profile_constraint.boundary_mode:
            source = "profile"
        else:
            source = "event-type"
        requirements.append(
            _NodeRequirement(
                node_id=event.node_id,
                sigma=event.sigma,
                event_type=event.event_type,
                boundary_mode=boundary_mode,
                dwell_seconds=dwell_seconds,
                source=source,
                refutes_trajectory=event.event_type == "collision-violation",
            )
        )
    return tuple(requirements)


def _aligned_segment_ids(path: M3CandidateAxisPath, sigma_start: float, sigma_end: float) -> tuple[str, ...]:
    matched = [
        segment.segment_id
        for segment in path.joint_segments
        if segment.sigma_end > sigma_start + _EPSILON and segment.sigma_start < sigma_end - _EPSILON
    ]
    if not matched:
        raise ValueError("move spans must reference at least one overlapping jointSegment")
    return tuple(matched)


def _ordered_axis_constraints(
    path: M3CandidateAxisPath,
    profile: MotionConstraintProfile,
) -> tuple[object, ...]:
    constraints_by_axis = {item.axis_id: item for item in profile.axis_constraints}
    ordered = []
    for axis in sorted(path.machine_profile.axes, key=lambda item: item.axis_order):
        resolved = constraints_by_axis.get(axis.axis_id)
        if resolved is None:
            raise ValueError("MotionConstraintProfile axisConstraints must cover every MachineProfile axis")
        ordered.append(resolved)
    return tuple(ordered)


def _sigma_limits(
    path_state: _LinearPathState,
    path: M3CandidateAxisPath,
    profile: MotionConstraintProfile,
    *,
    require_jerk: bool,
) -> tuple[float, float, float | None]:
    velocity_limits: list[float] = []
    acceleration_limits: list[float] = []
    jerk_limits: list[float] = []
    for slope, constraint in zip(path_state.qprime, _ordered_axis_constraints(path, profile), strict=True):
        magnitude = abs(slope)
        if magnitude <= _EPSILON:
            continue
        velocity_limits.append(constraint.maximum_velocity / magnitude)
        acceleration_limits.append(constraint.maximum_acceleration / magnitude)
        if require_jerk:
            if constraint.maximum_jerk is None:
                raise ValueError("smoothstep7-feasible planning requires maximumJerk on every moving axis")
            jerk_limits.append(constraint.maximum_jerk / magnitude)
    if not velocity_limits or not acceleration_limits:
        raise ValueError("the sourceAxisPath must contain a non-degenerate globally linear move")
    sigma_velocity_limit = min(velocity_limits)
    sigma_acceleration_limit = min(acceleration_limits)
    if profile.maximum_path_velocity is not None:
        sigma_velocity_limit = min(sigma_velocity_limit, profile.maximum_path_velocity)
    sigma_jerk_limit = min(jerk_limits) if require_jerk else None
    return sigma_velocity_limit, sigma_acceleration_limit, sigma_jerk_limit


def _second_order_time_law(
    distance: float,
    sigma_velocity_limit: float,
    sigma_acceleration_limit: float,
) -> TimeLawDefinition:
    if distance <= _EPSILON:
        raise ValueError("second-order move spans must cover positive sigma extent")
    threshold = sigma_velocity_limit * sigma_velocity_limit / sigma_acceleration_limit
    if distance <= threshold + _EPSILON:
        peak_velocity = math.sqrt(distance * sigma_acceleration_limit)
        acceleration_duration = peak_velocity / sigma_acceleration_limit
        return TimeLawDefinition(
            lawKind="triangular",
            durationSeconds=2.0 * acceleration_duration,
            accelerationDurationSeconds=acceleration_duration,
            decelerationDurationSeconds=acceleration_duration,
            sigmaVelocityLimit=sigma_velocity_limit,
            sigmaAccelerationLimit=sigma_acceleration_limit,
            peakSigmaVelocity=peak_velocity,
            peakSigmaAcceleration=sigma_acceleration_limit,
            peakSigmaJerk=0.0,
        )
    acceleration_duration = sigma_velocity_limit / sigma_acceleration_limit
    cruise_distance = distance - threshold
    cruise_duration = cruise_distance / sigma_velocity_limit
    return TimeLawDefinition(
        lawKind="trapezoidal",
        durationSeconds=2.0 * acceleration_duration + cruise_duration,
        accelerationDurationSeconds=acceleration_duration,
        cruiseDurationSeconds=cruise_duration,
        decelerationDurationSeconds=acceleration_duration,
        sigmaVelocityLimit=sigma_velocity_limit,
        sigmaAccelerationLimit=sigma_acceleration_limit,
        peakSigmaVelocity=sigma_velocity_limit,
        peakSigmaAcceleration=sigma_acceleration_limit,
        peakSigmaJerk=0.0,
    )


def _smoothstep7_time_law(
    distance: float,
    sigma_velocity_limit: float,
    sigma_acceleration_limit: float,
    sigma_jerk_limit: float,
) -> TimeLawDefinition:
    if distance <= _EPSILON:
        raise ValueError("smoothstep7 move spans must cover positive sigma extent")
    duration = max(
        distance * _SMOOTHSTEP7_VELOCITY_MAX / sigma_velocity_limit,
        math.sqrt(distance * _SMOOTHSTEP7_ACCELERATION_BOUND / sigma_acceleration_limit),
        (distance * _SMOOTHSTEP7_JERK_MAX / sigma_jerk_limit) ** (1.0 / 3.0),
    )
    duration = _outward_positive(duration)
    return TimeLawDefinition(
        lawKind="smoothstep7",
        durationSeconds=duration,
        sigmaVelocityLimit=sigma_velocity_limit,
        sigmaAccelerationLimit=sigma_acceleration_limit,
        sigmaJerkLimit=sigma_jerk_limit,
        peakSigmaVelocity=_outward_positive(distance * _SMOOTHSTEP7_VELOCITY_MAX / duration),
        peakSigmaAcceleration=_outward_positive(distance * _SMOOTHSTEP7_ACCELERATION_BOUND / (duration * duration)),
        peakSigmaJerk=_outward_positive(distance * _SMOOTHSTEP7_JERK_MAX / (duration * duration * duration)),
    )


def _dwell_time_law(duration: float) -> TimeLawDefinition:
    return TimeLawDefinition(
        lawKind="dwell",
        durationSeconds=duration,
        peakSigmaVelocity=0.0,
        peakSigmaAcceleration=0.0,
        peakSigmaJerk=0.0,
    )


def _required_stop_sigmas(requirements: tuple[_NodeRequirement, ...]) -> tuple[float, ...]:
    values = {
        requirement.sigma
        for requirement in requirements
        if requirement.boundary_mode in {"mandatory-stop", "dwell"}
        and _EPSILON < requirement.sigma < 1.0 - _EPSILON
    }
    return tuple(sorted(values))


def _node_contracts(
    requirements: tuple[_NodeRequirement, ...],
) -> tuple[RealizedNodeContract, ...]:
    return tuple(
        RealizedNodeContract(
            nodeId=requirement.node_id,
            sigma=requirement.sigma,
            eventType=requirement.event_type,
            boundaryMode=requirement.boundary_mode,
            dwellSeconds=requirement.dwell_seconds,
            source=requirement.source,
        )
        for requirement in requirements
    )


def _regularity_is_sufficient(
    path: M3CandidateAxisPath,
    requirements: tuple[_NodeRequirement, ...],
    *,
    require_c3: bool,
) -> bool:
    evidence_by_id = _node_evidence_by_id(path)
    needed_rank = 3 if require_c3 else 1
    for requirement in requirements:
        if requirement.boundary_mode != "allow-continuous":
            continue
        if requirement.sigma <= _EPSILON or requirement.sigma >= 1.0 - _EPSILON:
            continue
        evidence = evidence_by_id.get(requirement.node_id)
        if evidence is None or _continuity_rank(evidence.continuity_class) < needed_rank:
            return False
    return True


def _plan_spans(
    path: M3CandidateAxisPath,
    profile: MotionConstraintProfile,
    *,
    timing_mode: Literal["second-order-optimal", "smoothstep7-feasible"],
) -> tuple[ContinuousTrajectorySpan, ...]:
    path_state = _globally_linear_path_state(path)
    requirements = _collect_node_requirements(path, profile)
    if any(item.refutes_trajectory for item in requirements):
        raise ValueError("collision-violation nodeEvents refute positive F3 timing claims")
    if timing_mode == "second-order-optimal" and any(
        item.boundary_mode == "allow-continuous" and _EPSILON < item.sigma < 1.0 - _EPSILON
        for item in requirements
    ):
        raise ValueError("the Certified second-order subset does not allow moving internal nodes")
    require_c3 = timing_mode == "smoothstep7-feasible"
    if not _regularity_is_sufficient(path, requirements, require_c3=require_c3):
        raise ValueError("allow-continuous nodes do not certify the continuity required by the requested timing mode")
    sigma_velocity_limit, sigma_acceleration_limit, sigma_jerk_limit = _sigma_limits(
        path_state,
        path,
        profile,
        require_jerk=timing_mode == "smoothstep7-feasible",
    )
    stop_sigmas = _required_stop_sigmas(requirements)
    move_boundaries = (0.0, *stop_sigmas, 1.0)
    dwell_requirements = {item.sigma: item for item in requirements if item.boundary_mode == "dwell"}
    spans: list[ContinuousTrajectorySpan] = []
    current_time = 0.0
    span_index = 1
    if 0.0 in dwell_requirements:
        dwell = dwell_requirements[0.0]
        dwell_law = _dwell_time_law(dwell.dwell_seconds or 0.0)
        spans.append(
            ContinuousTrajectorySpan(
                spanId=f"span.{span_index}",
                spanKind="dwell",
                segmentIds=(),
                startTimeSeconds=current_time,
                endTimeSeconds=current_time + dwell_law.duration_seconds,
                sigmaStart=0.0,
                sigmaEnd=0.0,
                timeLaw=dwell_law,
            )
        )
        current_time += dwell_law.duration_seconds
        span_index += 1
    for sigma_start, sigma_end in zip(move_boundaries[:-1], move_boundaries[1:], strict=True):
        if sigma_end > sigma_start + _EPSILON:
            distance = sigma_end - sigma_start
            if timing_mode == "second-order-optimal":
                time_law = _second_order_time_law(distance, sigma_velocity_limit, sigma_acceleration_limit)
            else:
                assert sigma_jerk_limit is not None
                time_law = _smoothstep7_time_law(
                    distance,
                    sigma_velocity_limit,
                    sigma_acceleration_limit,
                    sigma_jerk_limit,
                )
            spans.append(
                ContinuousTrajectorySpan(
                    spanId=f"span.{span_index}",
                    spanKind="move",
                    segmentIds=_aligned_segment_ids(path, sigma_start, sigma_end),
                    startTimeSeconds=current_time,
                    endTimeSeconds=current_time + time_law.duration_seconds,
                    sigmaStart=sigma_start,
                    sigmaEnd=sigma_end,
                    timeLaw=time_law,
                )
            )
            current_time += time_law.duration_seconds
            span_index += 1
        dwell = dwell_requirements.get(sigma_end)
        if dwell is None:
            continue
        dwell_law = _dwell_time_law(dwell.dwell_seconds or 0.0)
        spans.append(
            ContinuousTrajectorySpan(
                spanId=f"span.{span_index}",
                spanKind="dwell",
                segmentIds=(),
                startTimeSeconds=current_time,
                endTimeSeconds=current_time + dwell_law.duration_seconds,
                sigmaStart=sigma_end,
                sigmaEnd=sigma_end,
                timeLaw=dwell_law,
            )
        )
        current_time += dwell_law.duration_seconds
        span_index += 1
    return tuple(spans)


def _supported_optimality(
    timing_mode: Literal["second-order-optimal", "smoothstep7-feasible"],
) -> TrajectoryOptimality:
    if timing_mode == "second-order-optimal":
        return TrajectoryOptimality(
            classification="ProvenOptimal",
            proofGapSeconds=0.0,
            rationale="closed-form triangular/trapezoidal stop-to-stop optimum on globally linear q(sigma)",
        )
    return TrajectoryOptimality(
        classification="FeasibleOnly",
        rationale="smoothstep7 stop-to-stop jerk-feasible certificate sized by conservative derivative bounds",
    )


def _unsupported_optimality(reason: str) -> TrajectoryOptimality:
    return TrajectoryOptimality(classification="NotApplicable", rationale=reason)


def _axis_usage(
    path_state: _LinearPathState,
    path: M3CandidateAxisPath,
    profile: MotionConstraintProfile,
    spans: tuple[ContinuousTrajectorySpan, ...],
) -> tuple[AxisConstraintUsage, ...]:
    usages: list[AxisConstraintUsage] = []
    constraints = _ordered_axis_constraints(path, profile)
    for axis, slope, constraint in zip(
        sorted(path.machine_profile.axes, key=lambda item: item.axis_order),
        path_state.qprime,
        constraints,
        strict=True,
    ):
        maximum_velocity = 0.0
        maximum_acceleration = 0.0
        maximum_jerk = 0.0 if constraint.maximum_jerk is not None else None
        for span in spans:
            law = span.time_law
            maximum_velocity = max(maximum_velocity, abs(slope) * law.peak_sigma_velocity)
            maximum_acceleration = max(maximum_acceleration, abs(slope) * law.peak_sigma_acceleration)
            if maximum_jerk is not None:
                maximum_jerk = max(maximum_jerk, abs(slope) * law.peak_sigma_jerk)
        usages.append(
            AxisConstraintUsage(
                axisId=axis.axis_id,
                unit=constraint.unit,
                maximumVelocity=maximum_velocity,
                velocityLimit=constraint.maximum_velocity,
                maximumAcceleration=maximum_acceleration,
                accelerationLimit=constraint.maximum_acceleration,
                maximumJerk=maximum_jerk,
                jerkLimit=constraint.maximum_jerk,
            )
        )
    return tuple(usages)


def _extrema_via_critical_roots(coefficients_desc: tuple[float, ...]) -> float:
    polynomial = np.poly1d(coefficients_desc)
    derivative = polynomial.deriv()
    candidates = [0.0, 1.0]
    for root in derivative.r:
        if abs(root.imag) > 1e-12:
            continue
        value = float(root.real)
        if -_EPSILON <= value <= 1.0 + _EPSILON:
            candidates.append(min(1.0, max(0.0, value)))
    return max(abs(float(polynomial(candidate))) for candidate in candidates)


def _smoothstep_critical_peak_checks(
    span: ContinuousTrajectorySpan,
    error_ledger: list[TrajectoryErrorLedgerEntry],
) -> None:
    if span.time_law.law_kind != "smoothstep7":
        return
    distance = span.sigma_end - span.sigma_start
    duration = span.time_law.duration_seconds
    velocity_peak = distance * _extrema_via_critical_roots((-140.0, 420.0, -420.0, 140.0, 0.0, 0.0, 0.0)) / duration
    acceleration_peak = distance * _extrema_via_critical_roots((-840.0, 2100.0, -1680.0, 420.0, 0.0, 0.0)) / (duration * duration)
    jerk_peak = distance * _extrema_via_critical_roots((-4200.0, 8400.0, -5040.0, 840.0, 0.0)) / (
        duration * duration * duration
    )
    for quantity, observed, certified in (
        ("velocity", velocity_peak, span.time_law.peak_sigma_velocity),
        ("acceleration", acceleration_peak, span.time_law.peak_sigma_acceleration),
        ("jerk", jerk_peak, span.time_law.peak_sigma_jerk),
    ):
        if observed > certified + 1e-10:
            error_ledger.append(
                TrajectoryErrorLedgerEntry(
                    entryId=f"{span.span_id}.{quantity}.cross-check",
                    quantity=quantity,
                    unit="dimensionless",
                    source="critical-root-cross-check",
                    bound=observed - certified,
                    method="smoothstep7-critical-roots",
                    code="SmoothstepCrossCheckExceededCertifiedPeak",
                    severity="error",
                    message=f"smoothstep7 {quantity} critical-root peak exceeded the certified bound",
                    relatedSegmentId=span.segment_ids[0] if span.segment_ids else None,
                )
            )


def _compare_time_laws(
    actual: TimeLawDefinition,
    expected: TimeLawDefinition,
    span_id: str,
    error_ledger: list[TrajectoryErrorLedgerEntry],
) -> None:
    def mismatch(field_name: str, actual_value: object, expected_value: object) -> None:
        error_ledger.append(
            TrajectoryErrorLedgerEntry(
                entryId=f"{span_id}.{field_name}",
                quantity="time-law",
                unit="n/a",
                source="continuous-trajectory-verifier",
                bound=1.0,
                method="deterministic-replan",
                code="TimeLawMismatch",
                severity="error",
                message=f"{field_name} did not match the deterministic F3 timing replay",
                relatedSegmentId=None,
            )
        )

    for field_name in (
        "law_kind",
        "duration_seconds",
        "acceleration_duration_seconds",
        "cruise_duration_seconds",
        "deceleration_duration_seconds",
        "sigma_velocity_limit",
        "sigma_acceleration_limit",
        "sigma_jerk_limit",
        "peak_sigma_velocity",
        "peak_sigma_acceleration",
        "peak_sigma_jerk",
    ):
        actual_value = getattr(actual, field_name)
        expected_value = getattr(expected, field_name)
        if isinstance(actual_value, float) or isinstance(expected_value, float):
            if actual_value is None or expected_value is None:
                if actual_value != expected_value:
                    mismatch(field_name, actual_value, expected_value)
                continue
            if not _is_close(float(actual_value), float(expected_value)):
                mismatch(field_name, actual_value, expected_value)
        elif actual_value != expected_value:
            mismatch(field_name, actual_value, expected_value)


def _compare_spans(
    actual: tuple[ContinuousTrajectorySpan, ...],
    expected: tuple[ContinuousTrajectorySpan, ...],
    error_ledger: list[TrajectoryErrorLedgerEntry],
) -> None:
    if len(actual) != len(expected):
        error_ledger.append(
            TrajectoryErrorLedgerEntry(
                entryId="spans.count",
                quantity="time-law",
                unit="count",
                source="continuous-trajectory-verifier",
                bound=abs(len(actual) - len(expected)),
                method="deterministic-replan",
                code="SpanCountMismatch",
                severity="error",
                message="the number of continuous spans did not match the deterministic F3 replay",
            )
        )
        return
    for index, (actual_span, expected_span) in enumerate(zip(actual, expected, strict=True), start=1):
        if actual_span.span_kind != expected_span.span_kind:
            error_ledger.append(
                TrajectoryErrorLedgerEntry(
                    entryId=f"spans.{index}.kind",
                    quantity="time-law",
                    unit="n/a",
                    source="continuous-trajectory-verifier",
                    bound=1.0,
                    method="deterministic-replan",
                    code="SpanKindMismatch",
                    severity="error",
                    message="the span kind did not match the deterministic F3 replay",
                    relatedSegmentId=actual_span.segment_ids[0] if actual_span.segment_ids else None,
                )
            )
        if actual_span.segment_ids != expected_span.segment_ids:
            error_ledger.append(
                TrajectoryErrorLedgerEntry(
                    entryId=f"spans.{index}.segments",
                    quantity="time-law",
                    unit="n/a",
                    source="continuous-trajectory-verifier",
                    bound=1.0,
                    method="deterministic-replan",
                    code="SpanSegmentMismatch",
                    severity="error",
                    message="the span segment coverage did not match the deterministic F3 replay",
                    relatedSegmentId=actual_span.segment_ids[0] if actual_span.segment_ids else None,
                )
            )
        for field_name in ("start_time_seconds", "end_time_seconds", "sigma_start", "sigma_end"):
            if not _is_close(getattr(actual_span, field_name), getattr(expected_span, field_name)):
                error_ledger.append(
                    TrajectoryErrorLedgerEntry(
                        entryId=f"spans.{index}.{field_name}",
                        quantity="time-law",
                        unit="n/a",
                        source="continuous-trajectory-verifier",
                        bound=abs(getattr(actual_span, field_name) - getattr(expected_span, field_name)),
                        method="deterministic-replan",
                        code="SpanScheduleMismatch",
                        severity="error",
                        message=f"{field_name} did not match the deterministic F3 replay",
                        relatedSegmentId=actual_span.segment_ids[0] if actual_span.segment_ids else None,
                    )
                )
        _compare_time_laws(actual_span.time_law, expected_span.time_law, actual_span.span_id, error_ledger)


def _plan_m4(
    source_axis_path: M3CandidateAxisPath,
    motion_constraint_profile: MotionConstraintProfile,
    *,
    timing_mode: Literal["second-order-optimal", "smoothstep7-feasible"],
    trajectory_id: str,
    solver_id: str,
) -> M4ContinuousTrajectory:
    spans = _plan_spans(source_axis_path, motion_constraint_profile, timing_mode=timing_mode)
    total_duration = spans[-1].end_time_seconds if spans else 0.0
    placeholder = ContinuousTrajectoryVerification(
        verificationId=f"{trajectory_id}.verification",
        solverId=_VERIFIER_ID,
        evidenceLevel="Validated",
        claimId=_CONTINUOUSLY_FEASIBLE_CLAIM_ID,
        overallStatus="Unsupported",
        totalDurationSeconds=total_duration,
        optimality=_unsupported_optimality("placeholder"),
        nodeContracts=(),
        axisConstraintUsage=(),
        errorLedger=(),
    )
    payload = {
        "artifactType": "five-axis.m4-continuous-trajectory",
        "schemaId": "five-axis.m4-continuous-trajectory@1",
        "schemaVersion": 1,
        "trajectoryId": trajectory_id,
        "sourceAxisPath": source_axis_path.model_dump(mode="json", by_alias=True, exclude_none=True),
        "sourceAxisPathContentId": _canonical_content_id(source_axis_path),
        "motionConstraintProfile": motion_constraint_profile.model_dump(mode="json", by_alias=True, exclude_none=True),
        "motionConstraintProfileContentId": _canonical_content_id(motion_constraint_profile),
        "solverId": solver_id,
        "timingMode": timing_mode,
        "spans": [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in spans],
        "verification": placeholder.model_dump(mode="json", by_alias=True, exclude_none=True),
        "provenance": (),
    }
    draft = M4ContinuousTrajectory.model_validate(payload)
    verification = verify_continuous_trajectory(draft)
    payload["verification"] = verification.model_dump(mode="json", by_alias=True, exclude_none=True)
    return M4ContinuousTrajectory.model_validate(payload)


def plan_second_order_time_law(
    source_axis_path: M3CandidateAxisPath,
    motion_constraint_profile: MotionConstraintProfile,
    *,
    trajectory_id: str = "f3.second-order.trajectory",
    solver_id: str = _SECOND_ORDER_SOLVER_ID,
) -> M4ContinuousTrajectory:
    if source_axis_path.machine_profile.profile_id != motion_constraint_profile.machine_profile_id:
        raise ValueError("motionConstraintProfile machineProfileId must match sourceAxisPath machineProfile profileId")
    if motion_constraint_profile.start_boundary.sigma_velocity != 0.0 or motion_constraint_profile.end_boundary.sigma_velocity != 0.0:
        raise ValueError("the Certified second-order subset requires zero sigmaVelocity boundary states")
    if motion_constraint_profile.start_boundary.sigma_acceleration != 0.0 or motion_constraint_profile.end_boundary.sigma_acceleration != 0.0:
        raise ValueError("the Certified second-order subset requires zero sigmaAcceleration boundary states")
    return _plan_m4(
        source_axis_path,
        motion_constraint_profile,
        timing_mode="second-order-optimal",
        trajectory_id=trajectory_id,
        solver_id=solver_id,
    )


def plan_jerk_feasible_time_law(
    source_axis_path: M3CandidateAxisPath,
    motion_constraint_profile: MotionConstraintProfile,
    *,
    trajectory_id: str = "f3.smoothstep7.trajectory",
    solver_id: str = _JERK_SOLVER_ID,
) -> M4ContinuousTrajectory:
    if source_axis_path.machine_profile.profile_id != motion_constraint_profile.machine_profile_id:
        raise ValueError("motionConstraintProfile machineProfileId must match sourceAxisPath machineProfile profileId")
    if motion_constraint_profile.start_boundary.sigma_velocity != 0.0 or motion_constraint_profile.end_boundary.sigma_velocity != 0.0:
        raise ValueError("the Certified jerk-feasible subset requires zero sigmaVelocity boundary states")
    if motion_constraint_profile.start_boundary.sigma_acceleration != 0.0 or motion_constraint_profile.end_boundary.sigma_acceleration != 0.0:
        raise ValueError("the Certified jerk-feasible subset requires zero sigmaAcceleration boundary states")
    return _plan_m4(
        source_axis_path,
        motion_constraint_profile,
        timing_mode="smoothstep7-feasible",
        trajectory_id=trajectory_id,
        solver_id=solver_id,
    )


def _evaluate_second_order_local(
    law: TimeLawDefinition,
    distance: float,
    local_time: float,
) -> tuple[float, float, float, float]:
    duration = law.duration_seconds
    if local_time <= _EPSILON:
        return 0.0, 0.0, 0.0, 0.0
    if local_time >= duration - _EPSILON:
        return distance, 0.0, 0.0, 0.0
    acceleration = law.peak_sigma_acceleration
    if law.law_kind == "triangular":
        acceleration_duration = law.acceleration_duration_seconds or 0.0
        if local_time < acceleration_duration:
            return (
                0.5 * acceleration * local_time * local_time,
                acceleration * local_time,
                acceleration,
                0.0,
            )
        remaining = duration - local_time
        return (
            distance - 0.5 * acceleration * remaining * remaining,
            acceleration * remaining,
            -acceleration,
            0.0,
        )
    acceleration_duration = law.acceleration_duration_seconds or 0.0
    cruise_duration = law.cruise_duration_seconds or 0.0
    peak_velocity = law.peak_sigma_velocity
    if local_time < acceleration_duration:
        return (
            0.5 * acceleration * local_time * local_time,
            acceleration * local_time,
            acceleration,
            0.0,
        )
    if local_time < acceleration_duration + cruise_duration:
        elapsed = local_time - acceleration_duration
        return (
            0.5 * acceleration * acceleration_duration * acceleration_duration + peak_velocity * elapsed,
            peak_velocity,
            0.0,
            0.0,
        )
    remaining = duration - local_time
    return (
        distance - 0.5 * acceleration * remaining * remaining,
        acceleration * remaining,
        -acceleration,
        0.0,
    )


def _smoothstep7_position(u: float) -> float:
    return 35.0 * u**4 - 84.0 * u**5 + 70.0 * u**6 - 20.0 * u**7


def _smoothstep7_velocity(u: float) -> float:
    return 140.0 * u**3 - 420.0 * u**4 + 420.0 * u**5 - 140.0 * u**6


def _smoothstep7_acceleration(u: float) -> float:
    return 420.0 * u**2 - 1680.0 * u**3 + 2100.0 * u**4 - 840.0 * u**5


def _smoothstep7_jerk(u: float) -> float:
    return 840.0 * u - 5040.0 * u**2 + 8400.0 * u**3 - 4200.0 * u**4


def _evaluate_smoothstep7_local(
    law: TimeLawDefinition,
    distance: float,
    local_time: float,
) -> tuple[float, float, float, float]:
    duration = law.duration_seconds
    if local_time <= _EPSILON:
        return 0.0, 0.0, 0.0, 0.0
    if local_time >= duration - _EPSILON:
        return distance, 0.0, 0.0, 0.0
    u = local_time / duration
    return (
        distance * _smoothstep7_position(u),
        distance * _smoothstep7_velocity(u) / duration,
        distance * _smoothstep7_acceleration(u) / (duration * duration),
        distance * _smoothstep7_jerk(u) / (duration * duration * duration),
    )


def _find_span(m4: M4ContinuousTrajectory, t: float) -> ContinuousTrajectorySpan:
    if t < -_EPSILON:
        raise ValueError("t must be nonnegative")
    total_duration = m4.verification.total_duration_seconds
    if t > total_duration + _EPSILON:
        raise ValueError("t must stay within the continuous trajectory duration")
    if math.isclose(t, total_duration, abs_tol=_EPSILON):
        return m4.spans[-1]
    for span in m4.spans:
        if span.start_time_seconds - _EPSILON <= t < span.end_time_seconds - _EPSILON:
            return span
    return m4.spans[-1]


def evaluate_continuous_state(m4: M4ContinuousTrajectory, t: float) -> ContinuousTrajectoryState:
    path_state = _globally_linear_path_state(m4.source_axis_path)
    span = _find_span(m4, t)
    local_time = min(span.time_law.duration_seconds, max(0.0, t - span.start_time_seconds))
    distance = span.sigma_end - span.sigma_start
    if span.span_kind == "dwell":
        sigma = span.sigma_start
        sigma_velocity = 0.0
        sigma_acceleration = 0.0
        sigma_jerk = 0.0
    elif span.time_law.law_kind in {"triangular", "trapezoidal"}:
        sigma_offset, sigma_velocity, sigma_acceleration, sigma_jerk = _evaluate_second_order_local(
            span.time_law,
            distance,
            local_time,
        )
        sigma = span.sigma_start + sigma_offset
    elif span.time_law.law_kind == "smoothstep7":
        sigma_offset, sigma_velocity, sigma_acceleration, sigma_jerk = _evaluate_smoothstep7_local(
            span.time_law,
            distance,
            local_time,
        )
        sigma = span.sigma_start + sigma_offset
    else:
        raise ValueError("unsupported timeLaw in continuous trajectory")
    q = _vector_add(path_state.q0, _vector_scale(path_state.qprime, sigma))
    qdot = _vector_scale(path_state.qprime, sigma_velocity)
    qddot = _vector_scale(path_state.qprime, sigma_acceleration)
    qjerk = _vector_scale(path_state.qprime, sigma_jerk)
    return ContinuousTrajectoryState(
        timeSeconds=t,
        spanId=span.span_id,
        sigma=sigma,
        sigmaVelocity=sigma_velocity,
        sigmaAcceleration=sigma_acceleration,
        sigmaJerk=sigma_jerk,
        jointPosition=q,
        jointVelocity=qdot,
        jointAcceleration=qddot,
        jointJerk=qjerk,
    )


def verify_continuous_trajectory(m4: M4ContinuousTrajectory) -> ContinuousTrajectoryVerification:
    error_ledger: list[TrajectoryErrorLedgerEntry] = []
    try:
        path_state = _globally_linear_path_state(m4.source_axis_path)
        requirements = _collect_node_requirements(m4.source_axis_path, m4.motion_constraint_profile)
        node_contracts = _node_contracts(requirements)
        if any(item.refutes_trajectory for item in requirements):
            expected_spans = m4.spans
            axis_usage = _axis_usage(path_state, m4.source_axis_path, m4.motion_constraint_profile, expected_spans)
            total_duration = expected_spans[-1].end_time_seconds if expected_spans else 0.0
            error_ledger.append(
                TrajectoryErrorLedgerEntry(
                    entryId="node.collision-violation",
                    quantity="time-law",
                    unit="n/a",
                    source="source-axis-path",
                    bound=1.0,
                    method="semantic-node-replay",
                    code="CollisionViolationRefuted",
                    severity="error",
                    message="collision-violation nodeEvents refute positive continuous trajectory claims",
                )
            )
        else:
            expected_spans = _plan_spans(
                m4.source_axis_path,
                m4.motion_constraint_profile,
                timing_mode=m4.timing_mode,
            )
            _compare_spans(m4.spans, expected_spans, error_ledger)
            for span in expected_spans:
                _smoothstep_critical_peak_checks(span, error_ledger)
            axis_usage = _axis_usage(path_state, m4.source_axis_path, m4.motion_constraint_profile, expected_spans)
            total_duration = expected_spans[-1].end_time_seconds if expected_spans else 0.0
        overall_status = "Refuted" if any(item.severity == "error" for item in error_ledger) else "Supported"
        evidence_level: Literal["Certified", "Validated", "Observed"] = "Certified" if overall_status == "Supported" else "Validated"
        optimality = _supported_optimality(m4.timing_mode) if overall_status == "Supported" else _unsupported_optimality(
            "the deterministic F3 timing replay did not validate the serialized trajectory"
        )
    except ValueError as exc:
        requirements = ()
        node_contracts = ()
        axis_usage = ()
        total_duration = m4.spans[-1].end_time_seconds if m4.spans else 0.0
        overall_status = "Unsupported"
        evidence_level = "Observed"
        optimality = _unsupported_optimality(str(exc))
        error_ledger.append(
            TrajectoryErrorLedgerEntry(
                entryId="trajectory.unsupported",
                quantity="time-law",
                unit="n/a",
                source="continuous-trajectory-verifier",
                bound=0.0,
                method="subset-gating",
                code="CertifiedSubsetUnsupported",
                severity="warning",
                message=str(exc),
            )
        )
    return ContinuousTrajectoryVerification(
        verificationId=f"{m4.trajectory_id}.verification",
        solverId=_VERIFIER_ID,
        evidenceLevel=evidence_level,
        claimId=_CONTINUOUSLY_FEASIBLE_CLAIM_ID,
        overallStatus=overall_status,
        totalDurationSeconds=total_duration,
        optimality=optimality,
        nodeContracts=node_contracts,
        axisConstraintUsage=axis_usage,
        errorLedger=tuple(error_ledger),
    )


__all__ = [
    "evaluate_continuous_state",
    "plan_jerk_feasible_time_law",
    "plan_second_order_time_law",
    "verify_continuous_trajectory",
]
