from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .f1_models import (
    ConstantOrientationSegment,
    DerivativeValue,
    DwellEvent,
    FeedRateEvent,
    FromEvent,
    GotoEvent,
    LinePositionSegment,
    M1ReferencePath,
    NodeEvent,
    NodeRegularityEvidence,
    NormalizedProgram,
    OrientationSegment,
    PathProgress,
    PositionSegment,
    ProvenanceRef,
    RegularityCertificate,
    SegmentIntervalMapping,
    SegmentRegularityEvidence,
    SlerpOrientationSegment,
)


_PIPELINE_ID = "five-axis.f1-pipeline@1"
_SOURCE_SYNTAX_ID = "axiom-cl-subset@1"
_VECTOR_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class PipelineFailure:
    code: str
    message: str
    source_event_id: str | None = None
    statement_id: str | None = None
    statement_index: int | None = None


class F1PipelineError(ValueError):
    def __init__(self, failure: PipelineFailure):
        self.failure = failure
        super().__init__(failure.message)

    @property
    def code(self) -> str:
        return self.failure.code

    @property
    def source_event_id(self) -> str | None:
        return self.failure.source_event_id

    @property
    def statement_id(self) -> str | None:
        return self.failure.statement_id

    @property
    def statement_index(self) -> int | None:
        return self.failure.statement_index

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "sourceEventId": self.source_event_id,
            "statementId": self.statement_id,
            "statementIndex": self.statement_index,
        }


@dataclass(frozen=True, slots=True)
class _Pose:
    position: tuple[float, float, float]
    tool_axis: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class _MotionStep:
    index: int
    event: GotoEvent
    source_pose: _Pose
    target_pose: _Pose
    position_changed: bool
    axis_changed: bool
    sigma_start: float
    sigma_end: float


def build_m1_reference_path(program: NormalizedProgram) -> M1ReferencePath:
    if program.source_syntax_id != _SOURCE_SYNTAX_ID:
        raise _failure(
            "unsupported-source-syntax",
            f"F1 pipeline only supports {_SOURCE_SYNTAX_ID}",
        )

    first_event = program.events[0]
    if not isinstance(first_event, FromEvent):
        raise _failure("missing-from", "NormalizedProgram must start with FROM")

    current_pose = _Pose(position=first_event.position, tool_axis=first_event.tool_axis)
    motions: list[_MotionStep] = []
    dwells_by_boundary: dict[int, list[DwellEvent]] = {}
    carried_provenance: list[ProvenanceRef] = []

    for event in program.events[1:]:
        if isinstance(event, FeedRateEvent):
            carried_provenance.append(_event_provenance(event.event_id, method="carried-feedrate"))
            continue
        if isinstance(event, DwellEvent):
            dwells_by_boundary.setdefault(len(motions), []).append(event)
            continue
        if isinstance(event, FromEvent):
            raise _failure(
                "unsupported-second-from",
                "F1 pipeline does not support a second FROM after initialization",
                event=event,
            )
        if isinstance(event, GotoEvent):
            _require_coordinate_context(program, event)
            target_pose = _Pose(position=event.position, tool_axis=event.tool_axis)
            position_changed = not _same_point(current_pose.position, target_pose.position)
            axis_changed = not _same_point(current_pose.tool_axis, target_pose.tool_axis)
            if not position_changed and not axis_changed:
                raise _failure(
                    "no-motion-goto",
                    "GOTO must change position or tool axis to produce an M1 path segment",
                    event=event,
                )
            motions.append(
                _MotionStep(
                    index=len(motions),
                    event=event,
                    source_pose=current_pose,
                    target_pose=target_pose,
                    position_changed=position_changed,
                    axis_changed=axis_changed,
                    sigma_start=0.0,
                    sigma_end=0.0,
                )
            )
            current_pose = target_pose
            continue

    if not motions:
        raise _failure("no-motion-program", "NormalizedProgram must contain at least one motion-producing GOTO")

    reference_path_id = f"{program.program_id}.m1"
    progress_id = f"{reference_path_id}.progress"

    position_segments: list[PositionSegment] = []
    orientation_segments: list[OrientationSegment] = []
    mappings: list[SegmentIntervalMapping] = []
    primary_segment_ids: list[str] = []

    step_count = len(motions)
    for step in motions:
        sigma_start = step.index / step_count
        sigma_end = (step.index + 1) / step_count
        step = _MotionStep(
            index=step.index,
            event=step.event,
            source_pose=step.source_pose,
            target_pose=step.target_pose,
            position_changed=step.position_changed,
            axis_changed=step.axis_changed,
            sigma_start=sigma_start,
            sigma_end=sigma_end,
        )
        motion_provenance = _event_provenance(step.event.event_id)
        position_segment_id = f"{reference_path_id}.position.{step.index + 1:04d}"
        position_segments.append(
            LinePositionSegment(
                segmentId=position_segment_id,
                segmentType="line",
                sigmaStart=sigma_start,
                sigmaEnd=sigma_end,
                lineage=(step.event.lineage,),
                startPoint=step.source_pose.position,
                endPoint=step.target_pose.position,
                provenance=motion_provenance,
            )
        )

        orientation_segment_id = f"{reference_path_id}.orientation.{step.index + 1:04d}"
        if step.axis_changed:
            if math.isclose(_dot(step.source_pose.tool_axis, step.target_pose.tool_axis), -1.0, abs_tol=_VECTOR_TOLERANCE):
                raise _failure(
                    "antipodal-tool-axis",
                    "Tool-axis interpolation rejects antipodal orientations",
                    event=step.event,
                )
            orientation_segments.append(
                SlerpOrientationSegment(
                    segmentId=orientation_segment_id,
                    segmentType="slerp",
                    sigmaStart=sigma_start,
                    sigmaEnd=sigma_end,
                    lineage=(step.event.lineage,),
                    startAxis=step.source_pose.tool_axis,
                    endAxis=step.target_pose.tool_axis,
                    provenance=motion_provenance,
                )
            )
        else:
            orientation_segments.append(
                ConstantOrientationSegment(
                    segmentId=orientation_segment_id,
                    segmentType="constant",
                    sigmaStart=sigma_start,
                    sigmaEnd=sigma_end,
                    lineage=(step.event.lineage,),
                    axis=step.target_pose.tool_axis,
                    provenance=motion_provenance,
                )
            )

        primary_segment_ids.append(position_segment_id)
        mappings.append(
            SegmentIntervalMapping(
                mappingId=f"{progress_id}.map.{step.index + 1:04d}",
                sourceSegmentId=position_segment_id,
                sourceLocalStart=0.0,
                sourceLocalEnd=1.0,
                sigmaStart=sigma_start,
                sigmaEnd=sigma_end,
                degenerateKind="none",
                provenance=motion_provenance,
            )
        )

    node_events = _build_node_events(reference_path_id, primary_segment_ids, dwells_by_boundary)
    regularity_certificate = _build_regularity_certificate(
        reference_path_id=reference_path_id,
        position_segments=tuple(position_segments),
        orientation_segments=tuple(orientation_segments),
        motions=tuple(motions),
        node_events=node_events,
    )

    path_provenance = [_program_provenance(program.program_id), *carried_provenance]
    if program.provenance:
        path_provenance.extend(program.provenance)

    return M1ReferencePath(
        artifactType="five-axis.m1-reference-path",
        schemaVersion=1,
        referencePathId=reference_path_id,
        coordinateContext=program.coordinate_context,
        pathProgress=PathProgress(
            progressId=progress_id,
            schemaVersion=1,
            progressParameter="sigma",
            unit="dimensionless",
            mappings=tuple(mappings),
            provenance=tuple(path_provenance),
        ),
        positionSemantics="continuous",
        positionSegments=tuple(position_segments),
        orientationSegments=tuple(orientation_segments),
        nodeEvents=node_events,
        regularityCertificate=regularity_certificate,
        provenance=tuple(path_provenance),
    )


def _build_node_events(
    reference_path_id: str,
    primary_segment_ids: list[str],
    dwells_by_boundary: dict[int, list[DwellEvent]],
) -> tuple[NodeEvent, ...]:
    step_count = len(primary_segment_ids)
    node_events: list[NodeEvent] = []

    for boundary_index in range(step_count + 1):
        sigma = boundary_index / step_count
        left_segment_id = primary_segment_ids[boundary_index - 1] if boundary_index > 0 else None
        right_segment_id = primary_segment_ids[boundary_index] if boundary_index < step_count else None
        dwell_events = dwells_by_boundary.get(boundary_index, [])
        if dwell_events:
            for dwell_index, dwell in enumerate(dwell_events, start=1):
                node_events.append(
                    NodeEvent(
                        nodeId=f"{reference_path_id}.node.dwell.{boundary_index:04d}.{dwell_index:02d}",
                        sigma=sigma,
                        eventType="dwell",
                        leftSegmentId=left_segment_id,
                        rightSegmentId=right_segment_id,
                        provenance=_event_provenance(dwell.event_id, method="dwell-node"),
                    )
                )
            continue
        if boundary_index == 0:
            node_events.append(
                NodeEvent(
                    nodeId=f"{reference_path_id}.node.start",
                    sigma=0.0,
                    eventType="ordinary-junction",
                    rightSegmentId=right_segment_id,
                )
            )
            continue
        if boundary_index == step_count:
            continue
        node_events.append(
            NodeEvent(
                nodeId=f"{reference_path_id}.node.boundary.{boundary_index:04d}",
                sigma=sigma,
                eventType="ordinary-junction",
                leftSegmentId=left_segment_id,
                rightSegmentId=right_segment_id,
            )
        )

    return tuple(node_events)


def _build_regularity_certificate(
    *,
    reference_path_id: str,
    position_segments: tuple[PositionSegment, ...],
    orientation_segments: tuple[OrientationSegment, ...],
    motions: tuple[_MotionStep, ...],
    node_events: tuple[NodeEvent, ...],
) -> RegularityCertificate:
    segment_evidence = [
        *(_segment_evidence(segment) for segment in position_segments),
        *(_segment_evidence(segment) for segment in orientation_segments),
    ]
    node_evidence: list[NodeRegularityEvidence] = []

    for node_event in node_events:
        if node_event.left_segment_id is None or node_event.right_segment_id is None:
            continue
        boundary_index = _boundary_index(node_event.sigma, len(motions))
        left_pose = motions[boundary_index - 1].target_pose
        right_pose = motions[boundary_index].source_pose
        node_evidence.append(
            NodeRegularityEvidence(
                nodeId=node_event.node_id,
                continuityClass="C0",
                leftDerivatives=(_pose_value(left_pose),),
                rightDerivatives=(_pose_value(right_pose),),
                verificationMethod="pose-match@1",
            )
        )

    return RegularityCertificate(
        certificateId=f"{reference_path_id}.regularity",
        segmentEvidence=tuple(segment_evidence),
        nodeEvidence=tuple(node_evidence),
    )


def _segment_evidence(segment: PositionSegment | OrientationSegment) -> SegmentRegularityEvidence:
    if isinstance(segment, LinePositionSegment):
        components = segment.start_point
        verification_method = "analytic-line@1"
    elif isinstance(segment, ConstantOrientationSegment):
        components = segment.axis
        verification_method = "analytic-constant-axis@1"
    else:
        components = segment.start_axis
        verification_method = "analytic-slerp@1"
    return SegmentRegularityEvidence(
        segmentId=segment.segment_id,
        continuityClass="C0",
        derivatives=(DerivativeValue(order=0, components=components),),
        verificationMethod=verification_method,
    )


def _pose_value(pose: _Pose) -> DerivativeValue:
    return DerivativeValue(order=0, components=(*pose.position, *pose.tool_axis))


def _boundary_index(sigma: float, step_count: int) -> int:
    boundary = round(sigma * step_count)
    if boundary <= 0:
        return 0
    if boundary >= step_count:
        return step_count
    return boundary


def _require_coordinate_context(program: NormalizedProgram, event: FromEvent | GotoEvent) -> None:
    if event.coordinate_context != program.coordinate_context:
        raise _failure(
            "coordinate-context-mismatch",
            "All motion events must match the program coordinate context",
            event=event,
        )


def _event_provenance(source_id: str, *, method: str = _PIPELINE_ID) -> ProvenanceRef:
    return ProvenanceRef(sourceStage="M0", sourceId=source_id, method=method)


def _program_provenance(source_id: str) -> ProvenanceRef:
    return ProvenanceRef(sourceStage="M0", sourceId=source_id, method=_PIPELINE_ID)


def _same_point(left: tuple[float, float, float], right: tuple[float, float, float]) -> bool:
    return all(math.isclose(a, b, abs_tol=_VECTOR_TOLERANCE) for a, b in zip(left, right, strict=True))


def _dot(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _failure(code: str, message: str, *, event: FromEvent | GotoEvent | None = None) -> F1PipelineError:
    return F1PipelineError(
        PipelineFailure(
            code=code,
            message=message,
            source_event_id=None if event is None else event.event_id,
            statement_id=None if event is None else event.lineage.statement_id,
            statement_index=None if event is None else event.lineage.statement_index,
        )
    )


__all__ = [
    "F1PipelineError",
    "PipelineFailure",
    "build_m1_reference_path",
]
