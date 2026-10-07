"""Standard CNC benchmark cases (V1 suite) and their NC programs.

Each case is generated together with the NC program that commands it, so the
reference geometry evaluated by Axiom is exactly the geometry sent to the
controller. Coordinates are rounded to the NC output resolution before the
case is built.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .benchmark import (
    AXES,
    BenchmarkArc,
    BenchmarkAxisLimits,
    BenchmarkTolerances,
    CncBenchmarkCase,
    benchmark_case_hash,
)

NC_DECIMALS = 4
STANDARD_CASE_NAMES = ("line", "circle", "corner90", "small-segments", "s-curve")
ArcFormat = Literal["IJK", "R"]


@dataclass(frozen=True)
class StandardCaseSettings:
    feed_mm_min: float = 3000.0
    sample_period_seconds: float = 0.001
    coordinate_frame: str = "workpiece"
    maximum_velocity_mm_s: float = 500.0
    maximum_acceleration_mm_s2: float = 5_000.0
    maximum_jerk_mm_s3: float = 500_000.0
    maximum_path_deviation_mm: float = 0.05
    maximum_endpoint_error_mm: float = 0.001


def _round(value: float) -> float:
    rounded = round(value, NC_DECIMALS)
    return 0.0 if rounded == 0 else rounded


def _point(x: float, y: float) -> tuple[float, float, float]:
    return (_round(x), _round(y), 0.0)


def _geometry(name: str) -> tuple[list[tuple[float, float, float]], list[BenchmarkArc]]:
    """Vertices and arcs in the XY plane; every path starts at the origin."""
    if name == "line":
        return [_point(0, 0), _point(50, 0)], []
    if name == "circle":
        # Full circle R20 as two half arcs, counterclockwise from the origin.
        center = (20.0, 0.0)
        return [_point(0, 0), _point(40, 0), _point(0, 0)], [
            BenchmarkArc(segmentIndex=0, centerMm=center, direction="ccw"),
            BenchmarkArc(segmentIndex=1, centerMm=center, direction="ccw"),
        ]
    if name == "corner90":
        return [_point(0, 0), _point(30, 0), _point(30, 30)], []
    if name == "small-segments":
        # CAM-style polyline: 200 chords of 0.2 mm in X along a 2 mm sine wave.
        return [_point(0.2 * i, 2.0 * math.sin(2 * math.pi * 0.2 * i / 20.0)) for i in range(201)], []
    if name == "s-curve":
        # Two tangent R15 arcs: counterclockwise then clockwise.
        radius = 15.0
        return [_point(0, 0), _point(radius, radius), _point(2 * radius, 2 * radius)], [
            BenchmarkArc(segmentIndex=0, centerMm=(0.0, radius), direction="ccw"),
            BenchmarkArc(segmentIndex=1, centerMm=(2 * radius, radius), direction="cw"),
        ]
    raise ValueError(f"unknown standard case {name!r}; expected one of {', '.join(STANDARD_CASE_NAMES)}")


def standard_case(name: str, settings: StandardCaseSettings = StandardCaseSettings()) -> CncBenchmarkCase:
    vertices, arcs = _geometry(name)
    period = settings.sample_period_seconds
    return CncBenchmarkCase(
        caseId=f"axiom.v1.{name}",
        coordinateFrame=settings.coordinate_frame,
        unit="mm",
        samplePeriodSeconds=period,
        referencePath=tuple(vertices),
        referenceArcs=tuple(arcs) or None,
        programmedFeedMmMin=settings.feed_mm_min,
        axisLimits=tuple(
            BenchmarkAxisLimits(
                axis=axis,
                minimumPositionMm=-1000,
                maximumPositionMm=1000,
                maximumVelocityMmS=settings.maximum_velocity_mm_s,
                maximumAccelerationMmS2=settings.maximum_acceleration_mm_s2,
                maximumJerkMmS3=settings.maximum_jerk_mm_s3,
            )
            for axis in AXES
        ),
        maximumPathDeviationMm=settings.maximum_path_deviation_mm,
        maximumEndpointErrorMm=settings.maximum_endpoint_error_mm,
        comparisonTolerances=BenchmarkTolerances(
            # Durations are quantized to the sample period on a real trace.
            durationSeconds=2 * period,
            pathDeviationMm=0.001,
            pathDeviationRmsMm=0.0005,
            pathDeviationP99Mm=0.001,
            jerkMmS3=0.05 * settings.maximum_jerk_mm_s3,
        ),
    )


def standard_cases(settings: StandardCaseSettings = StandardCaseSettings()) -> tuple[CncBenchmarkCase, ...]:
    return tuple(standard_case(name, settings) for name in STANDARD_CASE_NAMES)


def _format(value: float) -> str:
    text = f"{value:.{NC_DECIMALS}f}".rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def render_nc_program(case: CncBenchmarkCase, *, arc_format: ArcFormat = "IJK", line_numbers: bool = False) -> str:
    """Render a G17/G90/G21 program whose commanded geometry equals the case path."""
    if case.programmed_feed_mm_min is None:
        raise ValueError("the case must declare programmedFeedMmMin to render an NC program")
    arcs = {arc.segment_index: arc for arc in case.reference_arcs or ()}
    path = case.reference_path
    start = path[0]
    blocks = [
        "G90 G17 G21 G94",
        f"G0 X{_format(start[0])} Y{_format(start[1])} Z{_format(start[2])}",
        "G4 P0.5",
    ]
    feed = f" F{_format(case.programmed_feed_mm_min)}"
    for index in range(len(path) - 1):
        begin, end = path[index], path[index + 1]
        if begin == end:
            continue
        arc = arcs.get(index)
        target = f"X{_format(end[0])} Y{_format(end[1])} Z{_format(end[2])}"
        if arc is None:
            blocks.append(f"G1 {target}{feed}")
        else:
            code = "G2" if arc.direction == "cw" else "G3"
            if arc_format == "IJK":
                offset = f"I{_format(arc.center_mm[0] - begin[0])} J{_format(arc.center_mm[1] - begin[1])}"
            else:
                radius = math.hypot(begin[0] - arc.center_mm[0], begin[1] - arc.center_mm[1])
                a0 = math.atan2(begin[1] - arc.center_mm[1], begin[0] - arc.center_mm[0])
                a1 = math.atan2(end[1] - arc.center_mm[1], end[0] - arc.center_mm[0])
                sweep = (a1 - a0) % (2 * math.pi) if arc.direction == "ccw" else (a0 - a1) % (2 * math.pi)
                # R format: a negative radius selects the arc longer than 180 degrees.
                offset = f"R{_format(-radius if sweep > math.pi + 1e-9 else radius)}"
            blocks.append(f"{code} {target} {offset}{feed}")
        feed = ""
    blocks += ["G4 P0.5", "M30"]
    header = [f"(AXIOM CASE {case.case_id})", f"(CASE HASH {benchmark_case_hash(case)})"]
    if line_numbers:
        blocks = [f"N{10 * (number + 1)} {block}" for number, block in enumerate(blocks)]
    return "\n".join(header + blocks) + "\n"
