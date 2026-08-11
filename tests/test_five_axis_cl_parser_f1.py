from __future__ import annotations

import pytest

from axiom.five_axis.f1_models import DwellEvent, EndEvent, FeedRateEvent, FromEvent, GotoEvent, NormalizedProgram
from axiom.five_axis.f1_parser import CLParseError, parse_axiom_cl_subset


def test_parse_minimal_valid_program():
    program = parse_axiom_cl_subset(
        "UNITS/MM\n"
        "FROM/0,0,0,0,0,1\n"
        "GOTO/1,2,3\n"
        "END\n"
    )

    assert isinstance(program, NormalizedProgram)
    assert program.artifact_type == "five-axis.normalized-program"
    assert program.schema_version == 1
    assert program.source_syntax_id == "axiom-cl-subset@1"
    assert program.coordinate_context.unit == "MM"
    assert program.coordinate_context.coordinate_frame == "machine"
    assert [type(event) for event in program.events] == [FromEvent, GotoEvent, EndEvent]
    assert program.events[0].position == (0.0, 0.0, 0.0)
    assert program.events[0].tool_axis == (0.0, 0.0, 1.0)
    assert program.events[0].tool_axis_source == "explicit"
    assert program.events[1].position == (1.0, 2.0, 3.0)
    assert program.events[1].tool_axis == (0.0, 0.0, 1.0)
    assert program.events[1].tool_axis_source == "modal-inherited"
    assert program.events[1].source_tool_axis == (0.0, 0.0, 1.0)
    assert program.events[1].tool_axis_source_statement_id == "statement-0001"
    assert program.events[1].lineage.statement_index == 2
    assert program.events[1].lineage.source_text == "GOTO/1,2,3"


def test_parse_modal_ijk_inheritance_reuses_last_explicit_axis():
    program = parse_axiom_cl_subset(
        "UNITS/INCH\n"
        "FROM/0,0,0,1,0,0\n"
        "GOTO/1,2,3\n"
        "FROM/4,5,6\n"
        "GOTO/7,8,9,0,1,0\n"
        "END\n"
    )

    assert program.coordinate_context.unit == "INCH"
    assert program.events[1].tool_axis == (1.0, 0.0, 0.0)
    assert program.events[1].tool_axis_source == "modal-inherited"
    assert program.events[1].source_tool_axis == (1.0, 0.0, 0.0)
    assert program.events[1].tool_axis_source_statement_id == "statement-0001"
    assert program.events[2].tool_axis == (1.0, 0.0, 0.0)
    assert program.events[2].tool_axis_source == "modal-inherited"
    assert program.events[2].tool_axis_source_statement_id == "statement-0001"
    assert program.events[3].tool_axis == (0.0, 1.0, 0.0)
    assert program.events[3].tool_axis_source == "explicit"
    assert program.events[3].source_tool_axis is None
    assert program.events[3].tool_axis_source_statement_id is None
    assert program.events[0].lineage.statement_id == "statement-0001"
    assert program.events[3].lineage.statement_id == "statement-0004"


def test_explicit_axis_update_becomes_the_next_modal_provenance_source():
    program = parse_axiom_cl_subset(
        "UNITS/MM\n"
        "FROM/0,0,0,0,0,1\n"
        "GOTO/1,0,0,0,1,0\n"
        "GOTO/2,0,0\n"
        "END\n"
    )

    inherited = program.events[2]
    assert isinstance(inherited, GotoEvent)
    assert inherited.tool_axis == (0.0, 1.0, 0.0)
    assert inherited.source_tool_axis == (0.0, 1.0, 0.0)
    assert inherited.tool_axis_source_statement_id == "statement-0002"
    assert NormalizedProgram.model_validate(
        program.model_dump(mode="json", by_alias=True)
    ) == program


def test_parse_feedrate_dwell_comments_and_blank_lines():
    program = parse_axiom_cl_subset(
        "\n"
        "  $$ ignored comment\n"
        "UNITS/MM\n"
        "FROM/0,0,0,0,0,1\n"
        "\n"
        "FEDRAT/1200\n"
        "DWELL/0.5\n"
        "GOTO/1,0,0\n"
        "END\n"
        "$$ trailing comment is ignored\n"
    )

    assert [type(event) for event in program.events] == [FromEvent, FeedRateEvent, DwellEvent, GotoEvent, EndEvent]
    assert program.events[1].feed_rate == 1200.0
    assert program.events[1].unit == "MM/min"
    assert program.events[2].duration == 0.5
    assert program.events[2].unit == "s"


@pytest.mark.parametrize(
    ("source", "code", "line", "column", "record"),
    [
        ("HELLO/1\n", "unknown-record", 1, 1, "HELLO/1"),
        ("UNITS/MM\nUNITS/INCH\nFROM/0,0,0,0,0,1\nGOTO/1,0,0\nEND\n", "duplicate-units", 2, 1, "UNITS/INCH"),
        (
            "UNITS/MM\nFROM/0,0,0,0,0,1\nUNITS/INCH\nGOTO/1,0,0\nEND\n",
            "late-units",
            3,
            1,
            "UNITS/INCH",
        ),
        ("FROM/0,0,0,0,0,1\nGOTO/1,0,0\nEND\n", "units-required", 1, 1, "FROM/0,0,0,0,0,1"),
        ("UNITS/MM\nGOTO/1,2,3,0,0,1\nEND\n", "from-required", 2, 1, "GOTO/1,2,3,0,0,1"),
        ("UNITS/MM\nFROM/1,2,3\nGOTO/2,3,4\nEND\n", "missing-tool-axis", 2, 1, "FROM/1,2,3"),
        (
            "UNITS/MM\nFROM/0,0,0,0,0,1\nGOTO/1,2,3,4\nEND\n",
            "invalid-record-arity",
            3,
            1,
            "GOTO/1,2,3,4",
        ),
        (
            "UNITS/MM\nFROM/0,0,0,0,0,1\nFEDRAT/NaN\nGOTO/1,0,0\nEND\n",
            "non-finite-number",
            3,
            8,
            "FEDRAT/NaN",
        ),
        ("UNITS/MM\nFROM/0,0,0,0,0,0\nGOTO/1,0,0\nEND\n", "zero-tool-axis", 2, 12, "FROM/0,0,0,0,0,0"),
        (
            "UNITS/MM\nFROM/0,0,0,0,0,2\nGOTO/1,0,0\nEND\n",
            "invalid-tool-axis",
            2,
            12,
            "FROM/0,0,0,0,0,2",
        ),
        ("UNITS/MM\nFROM/0,0,0,0,0,1\nGOTO/1,0,0\nEND\nDWELL/1\n", "content-after-end", 5, 1, "DWELL/1"),
        ("UNITS/MM\nFROM/0,0,0,0,0,1\nGOTO/1,0,0\n", "missing-end", 3, 1, ""),
        (
            "UNITS/MM\nFROM/0,0,0,0,0,1\nDWELL/abc\nGOTO/1,0,0\nEND\n",
            "invalid-number",
            3,
            7,
            "DWELL/abc",
        ),
        ("UNITS/MM\nFEDRAT/10\nFROM/0,0,0,0,0,1\nGOTO/1,0,0\nEND\n", "from-required", 2, 1, "FEDRAT/10"),
        ("UNITS/MM\nFROM/0,0,0,0,0,1\nEND\n", "goto-required", 3, 1, "END"),
    ],
)
def test_parse_reports_structured_errors(source: str, code: str, line: int, column: int, record: str):
    with pytest.raises(CLParseError) as exc_info:
        parse_axiom_cl_subset(source)

    error = exc_info.value
    assert error.code == code
    assert error.line == line
    assert error.column == column
    assert error.source_record == record
    assert error.to_dict()["sourceRecord"] == record


def test_same_input_parses_deterministically():
    source = (
        "UNITS/MM\n"
        "$$ comment\n"
        "FROM/0,0,0,0,0,1\n"
        "FEDRAT/1500\n"
        "GOTO/1,2,3\n"
        "DWELL/2\n"
        "END\n"
    )

    first = parse_axiom_cl_subset(source).model_dump(mode="json", by_alias=True)
    second = parse_axiom_cl_subset(source).model_dump(mode="json", by_alias=True)

    assert first == second
