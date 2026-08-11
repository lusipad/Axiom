from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Literal, cast

from pydantic import Field

from ..models import AxiomModel
from .f1_models import (
    ConstantOrientationSegment,
    DerivativeValue,
    LinePositionSegment,
    M2CandidateTaskGeometry,
    NumericTolerance,
    NodeEvent,
    NodeRegularityEvidence,
    PathProgress,
    ProvenanceRef,
    RegularityCertificate,
    SegmentIntervalMapping,
    SegmentRegularityEvidence,
    ToleranceBinding,
)
from .f2_kinematics import canonical_numeric_evidence, inverse_kinematics, normalize_numeric_identity
from .f2_models import (
    BranchGraph,
    BranchNode,
    IKSolution,
    JointPolynomialSegment,
    KinematicsCertificate,
    M3CandidateAxisPath,
    MachineProfile,
    SingularityIndicator,
)


_EPSILON = 1e-12
_VECTOR_TOLERANCE = 1e-9
_SOLVER_ID = "five-axis.closed-form-ik-endpoint-enumerator@1"
_SOLVER_VERSION = "f2-path-2026-08-11"
_CONTINUOUS_METHOD_ID = "five-axis.linear-fixed-branch-lift@1"
_BRANCH_SELECTION_POLICY_ID = "five-axis.selected-branch.lexicographic@1"
_BRANCH_CONTINUITY_POLICY_ID = "five-axis.branch-wrap-continuity.strict@1"

_SUPPORTED_PROFILE_IDS = frozenset(
    {
        "five-axis.machine-profile.canonical-table-table-ac@1",
        "five-axis.machine-profile.canonical-head-table-workpiece-c-tool-b@1",
        "five-axis.machine-profile.canonical-head-head-cb@1",
    }
)

_LiftStatus = Literal["Supported", "Refuted", "Inconclusive", "Unsupported"]
_BranchKey = tuple[str, tuple[tuple[str, int], ...]]


class PathLiftResult(AxiomModel):
    status: _LiftStatus
    reason_code: str = Field(alias="reasonCode", min_length=1)
    axis_path: M3CandidateAxisPath | None = Field(default=None, alias="axisPath")


@dataclass(frozen=True)
class _KnotSolution:
    key: _BranchKey
    branch_id: str
    solution: IKSolution


def lift_m2_path_to_m3_axis_path(
    candidate_geometry: M2CandidateTaskGeometry,
    machine_profile: MachineProfile,
) -> PathLiftResult:
    if machine_profile.profile_id not in _SUPPORTED_PROFILE_IDS:
        return PathLiftResult(status="Unsupported", reasonCode="UnsupportedMachineProfile")

    position_reason = _validate_position_subset(candidate_geometry)
    if position_reason is not None:
        return PathLiftResult(status="Unsupported", reasonCode=position_reason)

    orientation_axis = _extract_constant_orientation_axis(candidate_geometry)
    if orientation_axis is None:
        return PathLiftResult(status="Unsupported", reasonCode="UnsupportedOrientationSubset")

    knots = _merged_knots(candidate_geometry)
    knot_solutions: list[tuple[float, tuple[_KnotSolution, ...]]] = []
    source_content_id = _content_id(candidate_geometry)
    profile_content_id = _content_id(machine_profile)

    for knot_index, sigma in enumerate(knots):
        position = _position_at(candidate_geometry, sigma)
        target = {"position": position, "toolAxis": orientation_axis}
        search = inverse_kinematics(machine_profile, target)
        if search.status == "SearchInconclusive":
            return PathLiftResult(status="Inconclusive", reasonCode="InconclusiveEndpointIK")
        if not search.solutions:
            return PathLiftResult(status="Refuted", reasonCode="RefutedNoEndpointIK")
        if any(candidate.free_parameters for candidate in search.solutions):
            return PathLiftResult(status="Unsupported", reasonCode="UnsupportedSingularFreeFamily")
        current_solutions: list[_KnotSolution] = []
        for solution_index, candidate in enumerate(search.solutions):
            key = (candidate.branch_id, tuple(sorted((item.axis_id, item.turns) for item in candidate.wrap_state)))
            branch_id = _branch_id(key)
            contract = _contract_solution(
                candidate=candidate,
                sigma=sigma,
                knot_index=knot_index,
                solution_index=solution_index,
                branch_id=branch_id,
            )
            if contract.singularity.status != "regular":
                return PathLiftResult(status="Unsupported", reasonCode="UnsupportedSingularBranch")
            current_solutions.append(_KnotSolution(key=key, branch_id=branch_id, solution=contract))
        knot_solutions.append((sigma, tuple(current_solutions)))

    root_keys = tuple(item.key for item in knot_solutions[0][1])
    branch_traces: dict[_BranchKey, list[_KnotSolution]] = {key: [] for key in root_keys}
    for _, solutions in knot_solutions:
        by_key = {item.key: item for item in solutions}
        for key, trace in branch_traces.items():
            current = by_key.get(key)
            if current is None:
                continue
            if trace and current.solution.sigma < trace[-1].solution.sigma - _EPSILON:
                continue
            trace.append(current)

    branch_nodes = tuple(_branch_node_for_trace(key, trace, knots) for key, trace in branch_traces.items())
    full_branches = tuple(item for item in branch_nodes if math.isclose(item.sigma_end, 1.0, abs_tol=_EPSILON))
    if not full_branches:
        return PathLiftResult(status="Unsupported", reasonCode="UnsupportedBranchContinuity")

    selected_branch = min(full_branches, key=_branch_selection_rank)
    selected_trace = next(
        trace for key, trace in branch_traces.items() if _branch_id(key) == selected_branch.branch_id
    )
    joint_segments = _joint_segments(selected_trace)
    node_events = _node_events(joint_segments)
    regularity = _regularity_certificate(joint_segments, node_events)

    selected_solutions = tuple(item.solution for item in selected_trace)
    axis_path = M3CandidateAxisPath(
        artifactType="five-axis.m3-candidate-axis-path",
        schemaVersion=1,
        axisPathId=f"{candidate_geometry.candidate_geometry_id}.m3-path",
        sourceCandidateGeometry=candidate_geometry,
        sourceCandidateGeometryContentId=source_content_id,
        machineProfile=machine_profile,
        machineProfileContentId=profile_content_id,
        pathProgress=_path_progress(joint_segments),
        ikSolutions=tuple(
            solution
            for _, solutions in knot_solutions
            for solution in (item.solution for item in solutions)
        ),
        branchGraph=BranchGraph(
            graphId=f"{candidate_geometry.candidate_geometry_id}.branch-graph",
            rootBranchIds=tuple(branch.branch_id for branch in sorted(branch_nodes, key=_branch_selection_rank)),
            branches=tuple(sorted(branch_nodes, key=_branch_selection_rank)),
            transitions=tuple(),
        ),
        jointSegments=joint_segments,
        nodeEvents=node_events,
        regularityCertificate=regularity,
        kinematicsCertificate=_kinematics_certificate(
            candidate_geometry=candidate_geometry,
            source_content_id=source_content_id,
            machine_profile=machine_profile,
            machine_profile_content_id=profile_content_id,
            branch_graph_id=f"{candidate_geometry.candidate_geometry_id}.branch-graph",
            selected_branch_id=selected_branch.branch_id,
            selected_solutions=selected_solutions,
            interval_count=len(joint_segments),
        ),
        provenance=(
            ProvenanceRef(
                sourceStage="M2",
                sourceId=candidate_geometry.candidate_geometry_id,
                sourceContentId=source_content_id,
                method=_CONTINUOUS_METHOD_ID,
            ),
        ),
    )
    return PathLiftResult(status="Supported", reasonCode="SupportedSelectedContinuousLift", axisPath=axis_path)


def _validate_position_subset(candidate_geometry: M2CandidateTaskGeometry) -> str | None:
    if candidate_geometry.position_segments:
        if any(not isinstance(segment, LinePositionSegment) for segment in candidate_geometry.position_segments):
            return "UnsupportedPositionSegment"
        return None
    if candidate_geometry.position_semantics == "static" and candidate_geometry.static_position is not None:
        return None
    return "UnsupportedPositionSubset"


def _extract_constant_orientation_axis(
    candidate_geometry: M2CandidateTaskGeometry,
) -> tuple[float, float, float] | None:
    if not candidate_geometry.orientation_segments:
        return None
    if any(not isinstance(segment, ConstantOrientationSegment) for segment in candidate_geometry.orientation_segments):
        return None
    first_segment = cast(ConstantOrientationSegment, candidate_geometry.orientation_segments[0])
    first_axis = _normalize(first_segment.axis)
    for raw_segment in candidate_geometry.orientation_segments[1:]:
        segment = cast(ConstantOrientationSegment, raw_segment)
        axis = _normalize(segment.axis)
        if any(not math.isclose(left, right, abs_tol=_VECTOR_TOLERANCE) for left, right in zip(first_axis, axis, strict=True)):
            return None
    return first_axis


def _merged_knots(candidate_geometry: M2CandidateTaskGeometry) -> tuple[float, ...]:
    values = {0.0, 1.0}
    for orientation_segment in candidate_geometry.orientation_segments:
        values.add(float(orientation_segment.sigma_start))
        values.add(float(orientation_segment.sigma_end))
    for position_segment in candidate_geometry.position_segments:
        values.add(float(position_segment.sigma_start))
        values.add(float(position_segment.sigma_end))
    return tuple(sorted(values))


def _position_at(candidate_geometry: M2CandidateTaskGeometry, sigma: float) -> tuple[float, float, float]:
    if not candidate_geometry.position_segments:
        assert candidate_geometry.static_position is not None
        return _tuple3(candidate_geometry.static_position)
    for raw_segment in candidate_geometry.position_segments:
        segment = cast(LinePositionSegment, raw_segment)
        if sigma < segment.sigma_start - _EPSILON or sigma > segment.sigma_end + _EPSILON:
            continue
        span = segment.sigma_end - segment.sigma_start
        local = 0.0 if math.isclose(span, 0.0, abs_tol=_EPSILON) else (sigma - segment.sigma_start) / span
        return _tuple3(
            float(start + (end - start) * local)
            for start, end in zip(segment.start_point, segment.end_point, strict=True)
        )
    raise ValueError("sigma is not covered by the supported position subset")


def _branch_id(key: _BranchKey) -> str:
    base_branch_id, wraps = key
    if not wraps:
        return f"{base_branch_id}.wrap.none"
    parts = []
    for axis_id, turns in wraps:
        suffix = f"m{abs(turns)}" if turns < 0 else str(turns)
        parts.append(f"{axis_id.lower()}{suffix}")
    return f"{base_branch_id}.wrap.{'.'.join(parts)}"


def _contract_solution(
    *,
    candidate: Any,
    sigma: float,
    knot_index: int,
    solution_index: int,
    branch_id: str,
) -> IKSolution:
    maximum = max(candidate.singularity.singular_values, default=0.0)
    minimum = candidate.singularity.minimum_singular_value
    conditioning = canonical_numeric_evidence(maximum / minimum) if minimum > _EPSILON else None
    return IKSolution(
        solutionId=f"{branch_id}.k{knot_index}.s{solution_index}",
        sigma=sigma,
        branchId=branch_id,
        jointValues=tuple(value for _, value in candidate.joint_values),
        wrapState=candidate.wrap_state,
        freeParameters=tuple(),
        axisLimitState=candidate.axis_limit_state,
        residuals=candidate.residuals,
        singularity=SingularityIndicator(
            status="singular" if candidate.singularity.singular else "regular",
            conditioningMetric=conditioning,
            minimumSingularValue=minimum,
        ),
        withinLimits=candidate.within_limits,
    )


def _branch_node_for_trace(key: _BranchKey, trace: list[_KnotSolution], knots: tuple[float, ...]) -> BranchNode:
    if not trace:
        raise ValueError("root branch trace must contain at least one solution")
    sigma_end = trace[-1].solution.sigma
    return BranchNode(
        branchId=_branch_id(key),
        sigmaStart=0.0,
        sigmaEnd=sigma_end,
        solutionIds=tuple(item.solution.solution_id for item in trace),
        status="active" if math.isclose(sigma_end, knots[-1], abs_tol=_EPSILON) else "terminated",
    )


def _branch_selection_rank(branch: BranchNode) -> tuple[int, tuple[int, ...], str]:
    wrap_values = tuple(_parse_wrap_turns(branch.branch_id))
    return (sum(abs(value) for value in wrap_values), wrap_values, branch.branch_id)


def _parse_wrap_turns(branch_id: str) -> tuple[int, ...]:
    if branch_id.endswith(".wrap.none"):
        return tuple()
    suffix = branch_id.split(".wrap.", maxsplit=1)[1]
    values: list[int] = []
    for item in suffix.split("."):
        digits = item.lstrip("abcdefghijklmnopqrstuvwxyz")
        if digits.startswith("m"):
            values.append(-int(digits[1:]))
        else:
            values.append(int(digits))
    return tuple(values)


def _joint_segments(trace: list[_KnotSolution]) -> tuple[JointPolynomialSegment, ...]:
    segments: list[JointPolynomialSegment] = []
    for index, (left, right) in enumerate(zip(trace, trace[1:])):
        delta = tuple(
            end - start
            for start, end in zip(left.solution.joint_values, right.solution.joint_values, strict=True)
        )
        segments.append(
            JointPolynomialSegment(
                segmentId=f"{left.branch_id}.seg.{index}",
                branchId=left.branch_id,
                sigmaStart=left.solution.sigma,
                sigmaEnd=right.solution.sigma,
                startSolutionId=left.solution.solution_id,
                endSolutionId=right.solution.solution_id,
                continuityClass="C3",
                interpolation="linear",
                coefficientBasis="local-power@1",
                coefficients=(left.solution.joint_values, delta),
            )
        )
    return tuple(segments)


def _node_events(joint_segments: tuple[JointPolynomialSegment, ...]) -> tuple[NodeEvent, ...]:
    events: list[NodeEvent] = []
    for index, (left, right) in enumerate(zip(joint_segments, joint_segments[1:])):
        events.append(
            NodeEvent(
                nodeId=f"{left.branch_id}.node.{index}",
                sigma=left.sigma_end,
                eventType="ordinary-junction",
                leftSegmentId=left.segment_id,
                rightSegmentId=right.segment_id,
            )
        )
    return tuple(events)


def _regularity_certificate(
    joint_segments: tuple[JointPolynomialSegment, ...],
    node_events: tuple[NodeEvent, ...],
) -> RegularityCertificate:
    segment_evidence = tuple(_segment_regularity(segment) for segment in joint_segments)
    node_evidence = tuple(
        _node_regularity(event, left, right)
        for event, left, right in zip(node_events, joint_segments, joint_segments[1:])
    )
    return RegularityCertificate(
        certificateId=f"{joint_segments[0].branch_id}.regularity",
        segmentEvidence=segment_evidence,
        nodeEvidence=node_evidence,
    )


def _segment_regularity(segment: JointPolynomialSegment) -> SegmentRegularityEvidence:
    span = segment.sigma_end - segment.sigma_start
    slope = tuple(
        0.0 if math.isclose(span, 0.0, abs_tol=_EPSILON) else coefficient / span
        for coefficient in segment.coefficients[1]
    )
    zero = (0.0, 0.0, 0.0, 0.0, 0.0)
    return SegmentRegularityEvidence(
        segmentId=segment.segment_id,
        continuityClass="C3",
        derivatives=(
            DerivativeValue(order=0, components=segment.coefficients[0]),
            DerivativeValue(order=1, components=slope),
            DerivativeValue(order=2, components=zero),
            DerivativeValue(order=3, components=zero),
        ),
        verificationMethod="analytic-linear-joint-polynomial@1",
    )


def _node_regularity(
    event: NodeEvent,
    left_segment: JointPolynomialSegment,
    right_segment: JointPolynomialSegment,
) -> NodeRegularityEvidence:
    left_value = left_segment.evaluate(left_segment.sigma_end)
    right_value = right_segment.evaluate(right_segment.sigma_start)
    left_span = left_segment.sigma_end - left_segment.sigma_start
    right_span = right_segment.sigma_end - right_segment.sigma_start
    left_slope = tuple(
        0.0 if math.isclose(left_span, 0.0, abs_tol=_EPSILON) else coefficient / left_span
        for coefficient in left_segment.coefficients[1]
    )
    right_slope = tuple(
        0.0 if math.isclose(right_span, 0.0, abs_tol=_EPSILON) else coefficient / right_span
        for coefficient in right_segment.coefficients[1]
    )
    c1 = all(math.isclose(left, right, abs_tol=1e-9) for left, right in zip(left_slope, right_slope, strict=True))
    continuity: Literal["C0", "C1"] = "C1" if c1 else "C0"
    left_derivatives = [DerivativeValue(order=0, components=left_value)]
    right_derivatives = [DerivativeValue(order=0, components=right_value)]
    if c1:
        left_derivatives.append(DerivativeValue(order=1, components=left_slope))
        right_derivatives.append(DerivativeValue(order=1, components=right_slope))
    return NodeRegularityEvidence(
        nodeId=event.node_id,
        continuityClass=continuity,
        leftDerivatives=tuple(left_derivatives),
        rightDerivatives=tuple(right_derivatives),
        verificationMethod="analytic-one-sided-joint-derivatives@1",
    )


def _path_progress(joint_segments: tuple[JointPolynomialSegment, ...]) -> PathProgress:
    return PathProgress(
        progressId=f"{joint_segments[0].branch_id}.progress",
        schemaVersion=1,
        progressParameter="sigma",
        unit="dimensionless",
        mappings=tuple(
            SegmentIntervalMapping(
                mappingId=f"{segment.segment_id}.map",
                sourceSegmentId=segment.segment_id,
                sourceLocalStart=0.0,
                sourceLocalEnd=1.0,
                sigmaStart=segment.sigma_start,
                sigmaEnd=segment.sigma_end,
                degenerateKind="none",
            )
            for segment in joint_segments
        ),
    )


def _kinematics_certificate(
    *,
    candidate_geometry: M2CandidateTaskGeometry,
    source_content_id: str,
    machine_profile: MachineProfile,
    machine_profile_content_id: str,
    branch_graph_id: str,
    selected_branch_id: str,
    selected_solutions: tuple[IKSolution, ...],
    interval_count: int,
) -> KinematicsCertificate:
    position_tolerance = _tolerance(candidate_geometry.tolerances, "position", default_absolute=1e-6, unit="mm")
    orientation_tolerance = _tolerance(candidate_geometry.tolerances, "orientation", default_absolute=1e-9, unit="rad")
    position_residual = max(
        _residual_value(solution, "five-axis.position-residual.max@1") for solution in selected_solutions
    )
    orientation_residual = max(
        _residual_value(solution, "five-axis.orientation-residual.max@1") for solution in selected_solutions
    )
    axis_limit_margin = min(
        min(
            min(
                (value - axis.limits.lower) / (axis.limits.upper - axis.limits.lower),
                (axis.limits.upper - value) / (axis.limits.upper - axis.limits.lower),
            )
            for axis, value in zip(machine_profile.axes, solution.joint_values, strict=True)
        )
        for solution in selected_solutions
    )
    minimum_singular = min(
        solution.singularity.minimum_singular_value or 0.0 for solution in selected_solutions
    )
    return KinematicsCertificate(
        certificateId=f"{candidate_geometry.candidate_geometry_id}.kinematics",
        machineProfileId=machine_profile.profile_id,
        machineProfileContentId=machine_profile_content_id,
        sourceCandidateGeometryId=candidate_geometry.candidate_geometry_id,
        sourceCandidateGeometryContentId=source_content_id,
        branchGraphId=branch_graph_id,
        solverId=_SOLVER_ID,
        solverVersion=_SOLVER_VERSION,
        evidenceLevel="Exact",
        continuousMethod=_CONTINUOUS_METHOD_ID,
        claimScope="selected-continuous-lift",
        selectedBranchId=selected_branch_id,
        intervalCount=interval_count,
        positionResidualUpperBound=position_residual,
        orientationResidualUpperBound=orientation_residual,
        axisLimitNormalizedMarginLowerBound=axis_limit_margin,
        minimumSingularValueLowerBound=minimum_singular,
        singularityHandling="regular-only",
        policyIds=(
            "five-axis.closed-form-ik-policy@1",
            _BRANCH_CONTINUITY_POLICY_ID,
            _BRANCH_SELECTION_POLICY_ID,
        ),
        numericEnvironment={
            "arithmetic": "ieee-754-binary64",
            "numericEvidencePolicy": "twelve-significant-digits@1",
        },
        positionTolerance=position_tolerance,
        orientationTolerance=orientation_tolerance,
        provenance=(
            ProvenanceRef(
                sourceStage="M2",
                sourceId=candidate_geometry.candidate_geometry_id,
                sourceContentId=source_content_id,
                method=_SOLVER_ID,
            ),
        ),
    )


def _tolerance(
    tolerances: tuple[ToleranceBinding, ...],
    target: Literal["position", "orientation"],
    *,
    default_absolute: float,
    unit: Literal["mm", "rad"],
) -> ToleranceBinding:
    for item in tolerances:
        if item.target == target:
            return item
    return ToleranceBinding(
        toleranceId=f"auto.{target}",
        target=target,
        tolerance=NumericTolerance(absolute=default_absolute, unit=unit),
    )


def _residual_value(solution: IKSolution, metric_id: str) -> float:
    for residual in solution.residuals:
        if residual.metric_id == metric_id:
            return residual.value
    raise ValueError(f"missing residual metric {metric_id}")


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = math.sqrt(sum(component * component for component in vector))
    if math.isclose(norm, 0.0, abs_tol=_EPSILON):
        raise ValueError("zero vector is not supported")
    return _tuple3(component / norm for component in vector)


def _tuple3(values: Any) -> tuple[float, float, float]:
    a, b, c = values
    return (float(a), float(b), float(c))


def _content_id(model: Any) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload = normalize_numeric_identity(payload)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["PathLiftResult", "lift_m2_path_to_m3_axis_path"]
