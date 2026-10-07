from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from axiom.benchmark import (
    CncBenchmarkCase,
    _reference_corners,
    benchmark_case_hash,
    compare_cnc_exports,
    reference_path_length_mm,
    render_report_table,
)
from axiom.benchmark_standard import STANDARD_CASE_NAMES, StandardCaseSettings, render_nc_program, standard_case, standard_cases
from axiom.benchmark_trace import TraceColumns, TraceImportError, TraceImportOptions, import_controller_trace
from axiom.cli import main

# Generous limits so synthetic constant-speed traces only test geometry and timing.
LOOSE = StandardCaseSettings(maximum_acceleration_mm_s2=1e9, maximum_jerk_mm_s3=1e13)


def _point_at(case: CncBenchmarkCase, distance: float) -> tuple[float, float, float]:
    """Synthetic helper: the exact reference point at an arc-length distance."""
    arcs = {arc.segment_index: arc for arc in case.reference_arcs or ()}
    path = case.reference_path
    for index in range(len(path) - 1):
        start, end = np.asarray(path[index]), np.asarray(path[index + 1])
        arc = arcs.get(index)
        if arc is None:
            length = float(np.linalg.norm(end - start))
        else:
            center = np.asarray(arc.center_mm)
            radius = float(np.hypot(*(start[:2] - center)))
            a0 = math.atan2(start[1] - center[1], start[0] - center[0])
            a1 = math.atan2(end[1] - center[1], end[0] - center[0])
            sweep = (a1 - a0) % (2 * math.pi) if arc.direction == "ccw" else -((a0 - a1) % (2 * math.pi))
            length = radius * abs(sweep)
        if distance <= length or index == len(path) - 2:
            ratio = min(distance / length, 1.0) if length else 0.0
            if arc is None:
                return tuple(start + ratio * (end - start))
            angle = a0 + ratio * sweep
            return (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle), start[2])
        distance -= length
    raise AssertionError("unreachable")


def _trace_csv(case, speed_mm_s, *, offset=(0.0, 0.0, 0.0), still=20, bump=None, clock="cycle") -> str:
    """Synthetic constant-speed trace with stationary head/tail, as a controller CSV."""
    length = reference_path_length_mm(case)
    period = case.sample_period_seconds
    moving = math.ceil(length / (speed_mm_s * period))
    points = [_point_at(case, 0.0)] * still
    points += [_point_at(case, min(i * speed_mm_s * period, length)) for i in range(1, moving + 1)]
    points += [points[-1]] * still
    if bump is not None:
        index, dy = bump
        x, y, z = points[still + index]
        points[still + index] = (x, y + dy, z)
    header = "Cycle;X;Y;Z" if clock == "cycle" else "TimeMs;X;Y;Z"
    rows = [header]
    for i, (x, y, z) in enumerate(points):
        stamp = 1000 + i if clock == "cycle" else f"{i * period * 1000:.6f}"
        rows.append(f"{stamp};{x + offset[0]:.9f};{y + offset[1]:.9f};{z + offset[2]:.9f}")
    return "\n".join(rows) + "\n"


def _import(case, text, version, **options):
    columns = TraceColumns(cycle="Cycle") if "TimeMs" not in text.splitlines()[0] else TraceColumns(time="TimeMs", time_scale=0.001)
    return import_controller_trace(text, case, algorithm_id="planner", algorithm_version=version, options=TraceImportOptions(columns=columns, **options))


def _single_arc_case(**overrides):
    payload = standard_case("line", LOOSE).model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["referencePath"] = [[0, 0, 0], [40, 0, 0]]
    payload["referenceArcs"] = [{"segmentIndex": 0, "centerMm": [20, 0], "direction": "ccw"}]
    payload.update(overrides)
    return payload


def test_arc_distance_is_exact_and_respects_the_swept_side():
    case = CncBenchmarkCase.model_validate(_single_arc_case())
    from axiom.benchmark import _path_deviations

    path = np.asarray(case.reference_path, dtype=float)
    points = np.array([[20, -20, 0], [20, -25, 0], [20 + 20 * math.cos(-1), 20 * math.sin(-1), 0.003], [20, 20, 0]], dtype=float)
    errors, _ = _path_deviations(points, path, case.reference_arcs)
    # On the counterclockwise lower half; 5 mm outside; 3 um above; the unswept upper half is
    # measured to the nearest endpoint, not to the chord (which would give 20 mm).
    assert errors[0] == pytest.approx(0.0, abs=1e-12)
    assert errors[1] == pytest.approx(5.0)
    assert errors[2] == pytest.approx(0.003)
    assert errors[3] == pytest.approx(math.hypot(20, 20))


@pytest.mark.parametrize(
    "arcs",
    (
        [{"segmentIndex": 1, "centerMm": [20, 0], "direction": "ccw"}],
        [{"segmentIndex": 0, "centerMm": [21, 0], "direction": "ccw"}],
        [{"segmentIndex": 0, "centerMm": [20, 0], "direction": "ccw"}, {"segmentIndex": 0, "centerMm": [20, 0], "direction": "cw"}],
    ),
)
def test_inconsistent_arcs_are_rejected(arcs):
    with pytest.raises(ValidationError):
        CncBenchmarkCase.model_validate(_single_arc_case(referenceArcs=arcs))
    with pytest.raises(ValidationError):
        CncBenchmarkCase.model_validate(_single_arc_case(referencePath=[[0, 0, 0], [40, 0, 1]]))


def test_standard_suite_geometry_corners_and_programs_agree():
    cases = {case.case_id.rsplit(".", 1)[-1]: case for case in standard_cases()}
    assert tuple(cases) == STANDARD_CASE_NAMES
    lengths = {name: reference_path_length_mm(case) for name, case in cases.items()}
    assert lengths["line"] == pytest.approx(50)
    assert lengths["circle"] == pytest.approx(2 * math.pi * 20)
    assert lengths["corner90"] == pytest.approx(60)
    assert lengths["s-curve"] == pytest.approx(math.pi * 15)
    assert [round(angle) for _, angle in _reference_corners(cases["corner90"])] == [90]
    for name in ("line", "circle", "small-segments", "s-curve"):
        assert _reference_corners(cases[name]) == []
    for name, case in cases.items():
        program = render_nc_program(case)
        assert benchmark_case_hash(case) in program
        targets = [tuple(float(v) for v in m) for m in re.findall(r"^G[123] X(\S+) Y(\S+) Z(\S+)", program, re.M)]
        assert targets == [tuple(point) for point in case.reference_path[1:]], name
        for arc, match in zip(case.reference_arcs or (), re.findall(r"^G[23] .* I(\S+) J(\S+)", program, re.M)):
            start = case.reference_path[arc.segment_index]
            assert (start[0] + float(match[0]), start[1] + float(match[1])) == pytest.approx(arc.center_mm)
    assert "R-" not in render_nc_program(cases["circle"], arc_format="R")


def test_controller_trace_import_trims_aligns_and_reproduces_geometry():
    case = standard_case("corner90", LOOSE)
    speed = case.programmed_feed_mm_min / 60.0
    text = _trace_csv(case, speed, offset=(100.0, -50.0, 5.0))
    export = _import(case, text, "A", offset_mm=(100.0, -50.0, 5.0))
    assert export.source_kind == "controller-trace"
    assert export.samples[0].position_mm == pytest.approx((0, 0, 0))
    assert export.samples[1].position_mm != export.samples[0].position_mm
    # Same result when the offset is unknown and the first sample is aligned to the case start.
    aligned = _import(case, text, "A", align_start_to_case=True)
    assert [s.position_mm for s in aligned.samples] == pytest.approx([s.position_mm for s in export.samples])
    report = compare_cnc_exports({"case": case, "baseline": export, "candidate": export})
    metrics = report.baseline.metrics
    assert metrics["sampledPathDeviationMaxMm"].value < 1e-6
    assert metrics["durationSeconds"].value == pytest.approx(60 / speed, abs=2 * case.sample_period_seconds)
    assert metrics["feedUtilization"].value == pytest.approx(1.0, rel=0.01)
    assert metrics["cornerSpeedMinMmS"].location.reference_segment_index == 1
    assert report.outcome == "WithinTolerance"


def test_time_column_with_millisecond_scale_is_accepted():
    case = standard_case("circle", LOOSE)
    export = _import(case, _trace_csv(case, 40.0, clock="time"), "A")
    report = compare_cnc_exports({"case": case, "baseline": export, "candidate": export})
    assert report.baseline.metrics["sampledPathDeviationMaxMm"].value < 1e-6


def test_dropped_cycles_irregular_clocks_and_missing_columns_are_rejected():
    case = standard_case("line", LOOSE)
    lines = _trace_csv(case, 50.0).splitlines()
    with pytest.raises(TraceImportError, match="cycle counter jumps"):
        _import(case, "\n".join(lines[:30] + lines[31:]), "A")
    timed = _trace_csv(case, 50.0, clock="time").splitlines()
    timed[30] = "29.5" + timed[30][timed[30].index(";"):]
    with pytest.raises(TraceImportError, match="no resampling"):
        _import(case, "\n".join(timed), "A")
    with pytest.raises(TraceImportError, match="missing trace columns"):
        import_controller_trace("Cycle;X;Y\n1;0;0\n2;1;0\n", case, algorithm_id="p", algorithm_version="A", options=TraceImportOptions(columns=TraceColumns(cycle="Cycle")))
    with pytest.raises(TraceImportError, match="exactly one clock"):
        import_controller_trace("\n".join(lines), case, algorithm_id="p", algorithm_version="A")


def test_faster_but_less_accurate_candidate_is_a_tradeoff():
    case = standard_case("s-curve", LOOSE)
    baseline = _import(case, _trace_csv(case, 40.0), "release")
    candidate = _import(case, _trace_csv(case, 50.0, bump=(200, 0.004)), "new")
    report = compare_cnc_exports({"case": case, "baseline": baseline, "candidate": candidate})
    statuses = {item.metric_id: item.status for item in report.differences}
    assert statuses["durationSeconds"] == "Improved"
    assert statuses["sampledPathDeviationMaxMm"] == "Regressed"
    assert "sampledPathDeviationRmsMm" in statuses and "discreteJerkMax" in statuses
    assert report.differences[-1].metric_id == "computationSeconds"
    assert report.outcome == "Tradeoff"
    table = render_report_table(report)
    assert "最大轮廓误差" in table and "结论：取舍" in table


def test_cli_generates_imports_and_prints_a_table(tmp_path: Path, capsys):
    out = tmp_path / "suite"
    assert main(["benchmark-standard-cases", "--out-dir", str(out), "--only", "line", "--max-acceleration", "1e9", "--max-jerk", "1e13"]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["line.case.json", "line.nc"]
    case = CncBenchmarkCase.model_validate(json.loads((out / "line.case.json").read_text(encoding="utf-8")))
    for version, speed in (("A", 40.0), ("B", 50.0)):
        (tmp_path / f"{version}.csv").write_text(_trace_csv(case, speed), encoding="utf-8")
        assert main(["benchmark-import-trace", str(tmp_path / f"{version}.csv"), "--case", str(out / "line.case.json"), "--algorithm-id", "planner", "--algorithm-version", version, "--cycle-column", "Cycle", "--out", str(tmp_path / f"{version}.json")]) == 0
    capsys.readouterr()
    code = main(["benchmark", "--case", str(out / "line.case.json"), "--baseline", str(tmp_path / "A.json"), "--candidate", str(tmp_path / "B.json"), "--format", "table"])
    text = capsys.readouterr().out
    assert code == 0 and "结论：改善" in text and "加工时间" in text
    (tmp_path / "bad.csv").write_text("Cycle;X;Y;Z\n1;0;0;0\n3;1;0;0\n", encoding="utf-8")
    assert main(["benchmark-import-trace", str(tmp_path / "bad.csv"), "--case", str(out / "line.case.json"), "--algorithm-id", "p", "--algorithm-version", "A", "--cycle-column", "Cycle"]) == 2
    assert "cycle counter jumps" in capsys.readouterr().err


def test_existing_example_case_identity_is_unchanged():
    root = Path(__file__).resolve().parents[1] / "examples" / "cnc-benchmark"
    case = json.loads((root / "case.json").read_text(encoding="utf-8-sig"))
    baseline = json.loads((root / "baseline.json").read_text(encoding="utf-8-sig"))
    assert benchmark_case_hash(case) == baseline["caseContentHash"]
