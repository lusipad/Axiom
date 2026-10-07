"""Import controller trace recordings (CSV) as CNC benchmark exports.

A trace is accepted only on the case's fixed sample period: dropped cycles or
irregular timestamps are rejected instead of being resampled.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass

from .benchmark import BenchmarkSample, CncAlgorithmExport, CncBenchmarkCase, benchmark_case_hash

MAX_TRACE_SAMPLES = 100_000


@dataclass(frozen=True)
class TraceColumns:
    x: str = "X"
    y: str = "Y"
    z: str = "Z"
    cycle: str | None = None
    time: str | None = None
    time_scale: float = 1.0


@dataclass(frozen=True)
class TraceImportOptions:
    columns: TraceColumns = TraceColumns()
    position_scale: float = 1.0
    offset_mm: tuple[float, float, float] = (0.0, 0.0, 0.0)
    align_start_to_case: bool = False
    trim_stationary: bool = True
    stationary_tolerance_mm: float = 1e-6
    period_relative_tolerance: float = 0.01


class TraceImportError(ValueError):
    pass


def _number(row_number: int, column: str, text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise TraceImportError(f"row {row_number}: column {column!r} is not a number: {text!r}") from None
    if not math.isfinite(value):
        raise TraceImportError(f"row {row_number}: column {column!r} is not finite")
    return value


def _read_rows(text: str, options: TraceImportOptions) -> tuple[list[tuple[float, float, float]], list[float] | None]:
    columns = options.columns
    if (columns.cycle is None) == (columns.time is None):
        raise TraceImportError("declare exactly one clock column: a cycle counter or a time column")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    clock_column = columns.cycle or columns.time
    required = (columns.x, columns.y, columns.z, clock_column)
    missing = [name for name in required if name not in (reader.fieldnames or [])]
    if missing:
        raise TraceImportError(f"missing trace columns {missing}; available: {reader.fieldnames}")
    positions: list[tuple[float, float, float]] = []
    clock: list[float] = []
    for row_number, row in enumerate(reader, start=2):
        if len(positions) >= MAX_TRACE_SAMPLES * 4:
            raise TraceImportError(f"trace exceeds {MAX_TRACE_SAMPLES * 4} rows; export a shorter window")
        positions.append(tuple(_number(row_number, name, row[name]) * options.position_scale for name in (columns.x, columns.y, columns.z)))  # type: ignore[misc]
        clock.append(_number(row_number, clock_column, row[clock_column]))
    if len(positions) < 2:
        raise TraceImportError("trace must contain at least two samples")
    return positions, clock


def _validate_clock(clock: list[float], period: float, options: TraceImportOptions) -> None:
    columns = options.columns
    for index in range(1, len(clock)):
        if columns.cycle is not None:
            step = clock[index] - clock[index - 1]
            if step != 1:
                raise TraceImportError(f"cycle counter jumps by {step:g} at data row {index + 1}; dropped or repeated cycles cannot be compared")
        else:
            step = (clock[index] - clock[index - 1]) * columns.time_scale
            if abs(step - period) > options.period_relative_tolerance * period:
                raise TraceImportError(
                    f"time step {step:.9g} s at data row {index + 1} differs from the case sample period {period:.9g} s; no resampling is performed"
                )


def _trim(positions: list[tuple[float, float, float]], tolerance: float) -> tuple[int, int]:
    """Keep one stationary sample before motion starts and one after it ends."""
    def moved(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
        return math.dist(a, b) > tolerance

    first = 0
    while first + 1 < len(positions) and not moved(positions[first + 1], positions[0]):
        first += 1
    last = len(positions) - 1
    while last - 1 > first and not moved(positions[last - 1], positions[-1]):
        last -= 1
    return first, last


def import_controller_trace(
    text: str,
    case: CncBenchmarkCase,
    *,
    algorithm_id: str,
    algorithm_version: str,
    options: TraceImportOptions = TraceImportOptions(),
) -> CncAlgorithmExport:
    positions, clock = _read_rows(text, options)
    _validate_clock(clock, case.sample_period_seconds, options)
    first, last = _trim(positions, options.stationary_tolerance_mm) if options.trim_stationary else (0, len(positions) - 1)
    window = positions[first:last + 1]
    if len(window) > MAX_TRACE_SAMPLES:
        raise TraceImportError(f"trace window has {len(window)} samples; the comparison limit is {MAX_TRACE_SAMPLES}")
    offset = options.offset_mm
    if options.align_start_to_case:
        offset = tuple(window[0][axis] - case.reference_path[0][axis] for axis in range(3))  # type: ignore[assignment]
    samples = tuple(
        BenchmarkSample(
            sampleIndex=index,
            t=index * case.sample_period_seconds,
            positionMm=tuple(point[axis] - offset[axis] for axis in range(3)),
        )
        for index, point in enumerate(window)
    )
    return CncAlgorithmExport(
        algorithmId=algorithm_id,
        algorithmVersion=algorithm_version,
        sourceKind="controller-trace",
        caseContentHash=benchmark_case_hash(case),
        coordinateFrame=case.coordinate_frame,
        unit="mm",
        samplePeriodSeconds=case.sample_period_seconds,
        samples=samples,
    )
