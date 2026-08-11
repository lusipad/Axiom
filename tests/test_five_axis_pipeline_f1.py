from __future__ import annotations

from axiom.five_axis.f1_models import CoordinateContext, EndEvent, FromEvent, GotoEvent, NormalizedProgram, SourceLineage
from axiom.five_axis.f1_pipeline import F1PipelineError, build_m1_reference_path


def _lineage(statement_id: str, statement_index: int, source_text: str) -> SourceLineage:
    return SourceLineage(
        statementId=statement_id,
        statementIndex=statement_index,
        line=statement_index + 1,
        column=1,
        sourceText=source_text,
        sourcePath="fixture.cl",
    )


def _context() -> CoordinateContext:
    return CoordinateContext(unit="MM", coordinateFrame="machine")


def _from_event(
    *,
    event_id: str = "event.from.1",
    statement_index: int = 0,
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    tool_axis: tuple[float, float, float] = (0.0, 0.0, 1.0),
) -> FromEvent:
    return FromEvent(
        eventId=event_id,
        eventType="FROM",
        lineage=_lineage(f"statement.{statement_index + 1:04d}", statement_index, "FROM/..."),
        coordinateContext=_context(),
        position=position,
        toolAxis=tool_axis,
        toolAxisSource="explicit",
    )


def _goto_event(
    statement_index: int,
    *,
    event_id: str | None = None,
    position: tuple[float, float, float],
    tool_axis: tuple[float, float, float],
) -> GotoEvent:
    return GotoEvent(
        eventId=event_id or f"event.goto.{statement_index + 1:04d}",
        eventType="GOTO",
        lineage=_lineage(f"statement.{statement_index + 1:04d}", statement_index, "GOTO/..."),
        coordinateContext=_context(),
        position=position,
        toolAxis=tool_axis,
        toolAxisSource="explicit",
    )


def _end_event(statement_index: int) -> EndEvent:
    return EndEvent(
        eventId=f"event.end.{statement_index + 1:04d}",
        eventType="END",
        lineage=_lineage(f"statement.{statement_index + 1:04d}", statement_index, "END"),
    )


def _program(*events) -> NormalizedProgram:
    return NormalizedProgram(
        artifactType="five-axis.normalized-program",
        schemaVersion=1,
        programId="program.pipeline.1",
        sourceSyntaxId="axiom-cl-subset@1",
        coordinateContext=_context(),
        events=events,
    )


def test_build_line_path_with_dwell_and_feedrate_provenance():
    program = NormalizedProgram.model_validate(
        {
            "artifactType": "five-axis.normalized-program",
            "schemaVersion": 1,
            "programId": "program.pipeline.1",
            "sourceSyntaxId": "axiom-cl-subset@1",
            "coordinateContext": {"unit": "MM", "coordinateFrame": "machine"},
            "events": [
                {
                    "eventId": "event.from.1",
                    "eventType": "FROM",
                    "lineage": _lineage("statement.0001", 0, "FROM/0,0,0,0,0,1").model_dump(by_alias=True),
                    "coordinateContext": {"unit": "MM", "coordinateFrame": "machine"},
                    "position": [0.0, 0.0, 0.0],
                    "toolAxis": [0.0, 0.0, 1.0],
                    "toolAxisSource": "explicit",
                },
                {
                    "eventId": "event.feed.1",
                    "eventType": "FEDRAT",
                    "lineage": _lineage("statement.0002", 1, "FEDRAT/1200").model_dump(by_alias=True),
                    "feedRate": 1200.0,
                    "unit": "MM/min",
                },
                {
                    "eventId": "event.goto.1",
                    "eventType": "GOTO",
                    "lineage": _lineage("statement.0003", 2, "GOTO/10,0,0").model_dump(by_alias=True),
                    "coordinateContext": {"unit": "MM", "coordinateFrame": "machine"},
                    "position": [10.0, 0.0, 0.0],
                    "toolAxis": [0.0, 0.0, 1.0],
                    "toolAxisSource": "explicit",
                },
                {
                    "eventId": "event.dwell.1",
                    "eventType": "DWELL",
                    "lineage": _lineage("statement.0004", 3, "DWELL/0.25").model_dump(by_alias=True),
                    "duration": 0.25,
                    "unit": "s",
                },
                {
                    "eventId": "event.goto.2",
                    "eventType": "GOTO",
                    "lineage": _lineage("statement.0005", 4, "GOTO/20,0,0").model_dump(by_alias=True),
                    "coordinateContext": {"unit": "MM", "coordinateFrame": "machine"},
                    "position": [20.0, 0.0, 0.0],
                    "toolAxis": [0.0, 0.0, 1.0],
                    "toolAxisSource": "explicit",
                },
                {
                    "eventId": "event.end.1",
                    "eventType": "END",
                    "lineage": _lineage("statement.0006", 5, "END").model_dump(by_alias=True),
                },
            ],
        }
    )

    path = build_m1_reference_path(program)

    assert path.reference_path_id == "program.pipeline.1.m1"
    assert path.position_semantics == "continuous"
    assert [segment.segment_type for segment in path.position_segments] == ["line", "line"]
    assert [segment.segment_type for segment in path.orientation_segments] == ["constant", "constant"]
    assert [(segment.sigma_start, segment.sigma_end) for segment in path.position_segments] == [(0.0, 0.5), (0.5, 1.0)]
    assert len(path.path_progress.mappings) == 2
    assert all(mapping.source_local_start == 0.0 for mapping in path.path_progress.mappings)
    assert all(mapping.source_local_end == 1.0 for mapping in path.path_progress.mappings)
    assert [mapping.source_segment_id for mapping in path.path_progress.mappings] == [
        "program.pipeline.1.m1.position.0001",
        "program.pipeline.1.m1.position.0002",
    ]
    assert any(node.event_type == "dwell" and node.sigma == 0.5 for node in path.node_events)
    dwell_node = next(node for node in path.node_events if node.event_type == "dwell")
    assert dwell_node.left_segment_id == "program.pipeline.1.m1.position.0001"
    assert dwell_node.right_segment_id == "program.pipeline.1.m1.position.0002"
    assert any(item.source_id == "event.feed.1" for item in path.provenance)
    assert path.regularity_certificate is not None
    assert all(item.continuity_class == "C0" for item in path.regularity_certificate.segment_evidence)
    assert [item.node_id for item in path.regularity_certificate.node_evidence] == [dwell_node.node_id]


def test_build_supports_orientation_only_goto():
    program = _program(
        _from_event(),
        _goto_event(1, position=(0.0, 0.0, 0.0), tool_axis=(1.0, 0.0, 0.0)),
        _end_event(2),
    )

    path = build_m1_reference_path(program)

    assert path.position_semantics == "continuous"
    assert len(path.position_segments) == 1
    assert path.position_segments[0].start_point == (0.0, 0.0, 0.0)
    assert path.position_segments[0].end_point == (0.0, 0.0, 0.0)
    assert len(path.orientation_segments) == 1
    assert path.orientation_segments[0].segment_type == "slerp"
    assert path.path_progress.mappings[0].source_segment_id == "program.pipeline.1.m1.position.0001"


def test_build_is_deterministic():
    program = _program(
        _from_event(),
        _goto_event(1, position=(5.0, 0.0, 0.0), tool_axis=(0.0, 0.0, 1.0)),
        _goto_event(2, position=(5.0, 0.0, 0.0), tool_axis=(0.0, 1.0, 0.0)),
        _end_event(3),
    )

    first = build_m1_reference_path(program).model_dump(mode="json", by_alias=True)
    second = build_m1_reference_path(program).model_dump(mode="json", by_alias=True)

    assert first == second


def test_second_from_is_rejected_with_structured_error():
    program = _program(
        _from_event(),
        _goto_event(1, position=(5.0, 0.0, 0.0), tool_axis=(0.0, 0.0, 1.0)),
        _from_event(event_id="event.from.2", statement_index=2, position=(5.0, 0.0, 0.0), tool_axis=(0.0, 0.0, 1.0)),
        _goto_event(3, position=(10.0, 0.0, 0.0), tool_axis=(0.0, 0.0, 1.0)),
        _end_event(4),
    )

    try:
        build_m1_reference_path(program)
    except F1PipelineError as error:
        assert error.code == "unsupported-second-from"
        assert error.source_event_id == "event.from.2"
        assert error.statement_index == 2
    else:
        raise AssertionError("expected F1PipelineError")


def test_no_motion_goto_is_rejected():
    program = _program(
        _from_event(),
        _goto_event(1, position=(0.0, 0.0, 0.0), tool_axis=(0.0, 0.0, 1.0)),
        _end_event(2),
    )

    try:
        build_m1_reference_path(program)
    except F1PipelineError as error:
        assert error.code == "no-motion-goto"
        assert error.source_event_id == "event.goto.0002"
    else:
        raise AssertionError("expected F1PipelineError")
