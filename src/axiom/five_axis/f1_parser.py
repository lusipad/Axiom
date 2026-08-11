from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

from .f1_models import CoordinateContext, DwellEvent, EndEvent, FeedRateEvent, FromEvent, GotoEvent, NormalizedProgram, SourceLineage


PROGRAM_SYNTAX_ID = "axiom-cl-subset@1"
_ALLOWED_UNITS = frozenset({"MM", "INCH"})
_SUPPORTED_RECORDS = frozenset({"UNITS", "FROM", "GOTO", "FEDRAT", "DWELL", "END"})
_COORDINATE_FRAME = "machine"
_AXIS_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class ParseFailure:
    code: str
    message: str
    line: int
    column: int
    source_record: str


class CLParseError(ValueError):
    def __init__(self, failure: ParseFailure):
        self.failure = failure
        super().__init__(failure.message)

    @property
    def code(self) -> str:
        return self.failure.code

    @property
    def line(self) -> int:
        return self.failure.line

    @property
    def column(self) -> int:
        return self.failure.column

    @property
    def source_record(self) -> str:
        return self.failure.source_record

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "line": self.line,
            "column": self.column,
            "sourceRecord": self.source_record,
        }


@dataclass(frozen=True, slots=True)
class _SourceLocation:
    line: int
    column: int
    source_record: str


@dataclass(frozen=True, slots=True)
class _ParsedRecord:
    name: str
    payload: str | None
    location: _SourceLocation
    statement_index: int


def parse_axiom_cl_subset(source: str) -> NormalizedProgram:
    units: str | None = None
    coordinate_context: CoordinateContext | None = None
    current_axis: tuple[float, float, float] | None = None
    current_axis_statement_id: str | None = None
    saw_from = False
    saw_goto = False
    saw_end = False
    saw_non_units_record = False
    statement_index = 0
    event_index = 0
    events: list[FromEvent | GotoEvent | FeedRateEvent | DwellEvent | EndEvent] = []

    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        record = _parse_record(raw_line, line_number, statement_index)
        if record is None:
            continue
        statement_index += 1

        if saw_end:
            raise _error("content-after-end", "END must be the final record", record.location)

        if record.name == "UNITS":
            if units is not None:
                raise _error(
                    "late-units" if saw_non_units_record else "duplicate-units",
                    "UNITS may appear exactly once and only before any other record",
                    record.location,
                )
            units = _parse_units(record.payload, record.location)
            coordinate_context = CoordinateContext(unit=units, coordinateFrame=_COORDINATE_FRAME)
            continue

        saw_non_units_record = True

        if record.name == "FROM":
            if units is None or coordinate_context is None:
                raise _error("units-required", "FROM requires a prior UNITS record", record.location)
            coordinates = _parse_coordinate_numbers(record.payload, record.location, "FROM")
            if not saw_from and len(coordinates) == 3:
                raise _error("missing-tool-axis", "The first FROM record must declare I,J,K explicitly", record.location)
            current_axis, tool_axis_source, source_tool_axis, source_statement_id = _resolve_axis(
                record=record,
                coordinates=coordinates,
                current_axis=current_axis,
                current_axis_statement_id=current_axis_statement_id,
            )
            if tool_axis_source == "explicit":
                current_axis_statement_id = _statement_id(record)
            event = FromEvent(
                eventId=_event_id("from", event_index),
                eventType="FROM",
                lineage=_lineage(record),
                coordinateContext=coordinate_context,
                position=coordinates[:3],
                toolAxis=current_axis,
                toolAxisSource=tool_axis_source,
                sourceToolAxis=source_tool_axis,
                toolAxisSourceStatementId=source_statement_id,
            )
            events.append(event)
            saw_from = True
            event_index += 1
            continue

        if record.name == "GOTO":
            if units is None or coordinate_context is None:
                raise _error("units-required", "GOTO requires a prior UNITS record", record.location)
            if not saw_from:
                raise _error("from-required", "GOTO requires a prior FROM record", record.location)
            coordinates = _parse_coordinate_numbers(record.payload, record.location, "GOTO")
            current_axis, tool_axis_source, source_tool_axis, source_statement_id = _resolve_axis(
                record=record,
                coordinates=coordinates,
                current_axis=current_axis,
                current_axis_statement_id=current_axis_statement_id,
            )
            if tool_axis_source == "explicit":
                current_axis_statement_id = _statement_id(record)
            event = GotoEvent(
                eventId=_event_id("goto", event_index),
                eventType="GOTO",
                lineage=_lineage(record),
                coordinateContext=coordinate_context,
                position=coordinates[:3],
                toolAxis=current_axis,
                toolAxisSource=tool_axis_source,
                sourceToolAxis=source_tool_axis,
                toolAxisSourceStatementId=source_statement_id,
            )
            events.append(event)
            saw_goto = True
            event_index += 1
            continue

        if record.name == "FEDRAT":
            if not saw_from or units is None:
                raise _error("from-required", "FEDRAT requires a prior FROM record", record.location)
            value = _parse_single_number(record.payload, record.location, "FEDRAT")
            if value <= 0.0:
                raise _error(
                    "invalid-feed-rate",
                    "FEDRAT must be greater than zero",
                    _token_location(record.payload, record.location, 0),
                )
            events.append(
                FeedRateEvent(
                    eventId=_event_id("feed", event_index),
                    eventType="FEDRAT",
                    lineage=_lineage(record),
                    feedRate=value,
                    unit=_feed_rate_unit(units),
                )
            )
            event_index += 1
            continue

        if record.name == "DWELL":
            if not saw_from:
                raise _error("from-required", "DWELL requires a prior FROM record", record.location)
            value = _parse_single_number(record.payload, record.location, "DWELL")
            if value < 0.0:
                raise _error(
                    "invalid-dwell",
                    "DWELL must be greater than or equal to zero",
                    _token_location(record.payload, record.location, 0),
                )
            events.append(
                DwellEvent(
                    eventId=_event_id("dwell", event_index),
                    eventType="DWELL",
                    lineage=_lineage(record),
                    duration=value,
                    unit="s",
                )
            )
            event_index += 1
            continue

        if record.name == "END":
            if not saw_from:
                raise _error("from-required", "END requires a prior FROM record", record.location)
            if not saw_goto:
                raise _error("goto-required", "END requires at least one prior GOTO record", record.location)
            events.append(
                EndEvent(
                    eventId=_event_id("end", event_index),
                    eventType="END",
                    lineage=_lineage(record),
                )
            )
            saw_end = True
            event_index += 1
            continue

    if not saw_end:
        last_line = len(source.splitlines()) or 1
        raise _error(
            "missing-end",
            "Program must terminate with END",
            _SourceLocation(line=last_line, column=1, source_record=""),
        )

    assert units is not None
    assert coordinate_context is not None

    return NormalizedProgram(
        artifactType="five-axis.normalized-program",
        schemaVersion=1,
        programId=_program_id(source),
        sourceSyntaxId=PROGRAM_SYNTAX_ID,
        coordinateContext=coordinate_context,
        events=tuple(events),
    )


def _parse_record(raw_line: str, line_number: int, statement_index: int) -> _ParsedRecord | None:
    stripped = raw_line.strip()
    if not stripped or stripped.startswith("$$"):
        return None

    column = len(raw_line) - len(raw_line.lstrip()) + 1
    location = _SourceLocation(line=line_number, column=column, source_record=raw_line)

    if "/" not in stripped:
        if stripped == "END":
            return _ParsedRecord(name="END", payload=None, location=location, statement_index=statement_index)
        if stripped in _SUPPORTED_RECORDS:
            raise _error("invalid-record-syntax", f"{stripped} requires a '/' payload", location)
        raise _error("unknown-record", f"Unsupported record '{stripped}'", location)

    record_name, payload = stripped.split("/", 1)
    if record_name not in _SUPPORTED_RECORDS:
        raise _error("unknown-record", f"Unsupported record '{record_name}'", location)
    if record_name == "END":
        raise _error("invalid-record-arity", "END must not include a payload", location)
    if payload == "":
        raise _error("invalid-record-syntax", f"{record_name} requires a non-empty payload", location)
    return _ParsedRecord(name=record_name, payload=payload, location=location, statement_index=statement_index)


def _parse_units(payload: str | None, location: _SourceLocation) -> str:
    if payload is None:
        raise _error("invalid-record-syntax", "UNITS requires a payload", location)
    tokens = _split_payload(payload, location)
    if len(tokens) != 1:
        raise _error("invalid-record-arity", "UNITS expects exactly one token", location)
    unit, token_location = tokens[0]
    if unit not in _ALLOWED_UNITS:
        raise _error("invalid-record-syntax", "UNITS must be MM or INCH", token_location)
    return unit


def _parse_single_number(payload: str | None, location: _SourceLocation, record_name: str) -> float:
    if payload is None:
        raise _error("invalid-record-syntax", f"{record_name} requires a payload", location)
    tokens = _split_payload(payload, location)
    if len(tokens) != 1:
        raise _error("invalid-record-arity", f"{record_name} expects exactly one numeric token", location)
    token, token_location = tokens[0]
    return _parse_number(token, token_location)


def _parse_coordinate_numbers(
    payload: str | None,
    location: _SourceLocation,
    record_name: str,
) -> tuple[float, ...]:
    if payload is None:
        raise _error("invalid-record-syntax", f"{record_name} requires a payload", location)
    tokens = _split_payload(payload, location)
    if len(tokens) not in {3, 6}:
        raise _error("invalid-record-arity", f"{record_name} expects X,Y,Z or X,Y,Z,I,J,K", location)
    return tuple(_parse_number(token, token_location) for token, token_location in tokens)


def _split_payload(payload: str, location: _SourceLocation) -> list[tuple[str, _SourceLocation]]:
    record_name = location.source_record.strip().split("/", 1)[0]
    payload_column = location.column + len(record_name) + 1
    pieces: list[tuple[str, _SourceLocation]] = []
    start = 0

    for index, char in enumerate(payload):
        if char == ",":
            pieces.append(_slice_token(payload, start, index, location, payload_column))
            start = index + 1

    pieces.append(_slice_token(payload, start, len(payload), location, payload_column))
    return pieces


def _slice_token(
    payload: str,
    start: int,
    end: int,
    location: _SourceLocation,
    payload_column: int,
) -> tuple[str, _SourceLocation]:
    raw_token = payload[start:end]
    trimmed = raw_token.strip()
    leading_spaces = len(raw_token) - len(raw_token.lstrip())
    token_location = _SourceLocation(
        line=location.line,
        column=payload_column + start + leading_spaces,
        source_record=location.source_record,
    )
    if trimmed == "":
        raise _error("invalid-record-syntax", "Empty payload token is not allowed", token_location)
    return (trimmed, token_location)


def _parse_number(token: str, location: _SourceLocation) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise _error("invalid-number", f"Invalid numeric token '{token}'", location) from exc
    if not math.isfinite(value):
        raise _error("non-finite-number", f"Numeric token '{token}' must be finite", location)
    return value


def _resolve_axis(
    *,
    record: _ParsedRecord,
    coordinates: tuple[float, ...],
    current_axis: tuple[float, float, float] | None,
    current_axis_statement_id: str | None,
) -> tuple[tuple[float, float, float], str, tuple[float, float, float] | None, str | None]:
    if len(coordinates) == 3:
        if current_axis is None:
            raise _error(
                "missing-tool-axis",
                "I,J,K may only be omitted after an explicit tool axis has been established",
                record.location,
            )
        if current_axis_statement_id is None:
            raise _error(
                "missing-tool-axis-provenance",
                "Modal I,J,K inheritance requires an explicit source statement",
                record.location,
            )
        return (current_axis, "modal-inherited", current_axis, current_axis_statement_id)

    axis = (coordinates[3], coordinates[4], coordinates[5])
    axis_location = _token_location(record.payload, record.location, 3)
    norm = math.sqrt(sum(component * component for component in axis))
    if math.isclose(norm, 0.0, abs_tol=_AXIS_TOLERANCE):
        raise _error("zero-tool-axis", "Tool axis I,J,K must not be the zero vector", axis_location)
    if not math.isclose(norm, 1.0, abs_tol=_AXIS_TOLERANCE):
        raise _error("invalid-tool-axis", "Tool axis I,J,K must be unit length", axis_location)
    return (axis, "explicit", None, None)


def _statement_id(record: _ParsedRecord) -> str:
    return f"statement-{record.statement_index:04d}"


def _token_location(payload: str | None, location: _SourceLocation, index: int) -> _SourceLocation:
    if payload is None:
        return location
    tokens = _split_payload(payload, location)
    if index >= len(tokens):
        return location
    return tokens[index][1]


def _lineage(record: _ParsedRecord) -> SourceLineage:
    return SourceLineage(
        statementId=_statement_id(record),
        statementIndex=record.statement_index,
        sourceText=record.location.source_record,
        line=record.location.line,
        column=record.location.column,
    )


def _event_id(prefix: str, event_index: int) -> str:
    return f"{prefix}-{event_index:04d}"


def _program_id(source: str) -> str:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"five-axis.normalized-program:{digest}"


def _feed_rate_unit(units: str) -> str:
    return f"{units}/min"


def _error(code: str, message: str, location: _SourceLocation) -> CLParseError:
    return CLParseError(
        ParseFailure(
            code=code,
            message=message,
            line=location.line,
            column=location.column,
            source_record=location.source_record,
        )
    )


__all__ = [
    "CLParseError",
    "PROGRAM_SYNTAX_ID",
    "ParseFailure",
    "parse_axiom_cl_subset",
]
