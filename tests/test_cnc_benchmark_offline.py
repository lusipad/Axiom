from __future__ import annotations

import json
import math
import sys

import pytest
from pydantic import ValidationError

from axiom.benchmark import CncBenchmarkCase, _hash, benchmark_case_hash, compare_cnc_exports
from axiom.benchmark_offline import RuckigOfflineOptions, generate_ruckig_export, offline_cases
from axiom.cli import main


@pytest.fixture
def local_sut():
    return pytest.importorskip("ruckig")


@pytest.mark.parametrize("case", offline_cases(), ids=lambda case: case.case_id)
def test_local_export_is_deterministic_bound_and_honestly_labelled(case, local_sut):
    export, manifest = generate_ruckig_export(case)
    repeated, repeated_manifest = generate_ruckig_export(case)
    assert (export, manifest) == (repeated, repeated_manifest)
    assert export.source_kind == "offline-sut" and export.computation is None
    assert export.case_content_hash == benchmark_case_hash(case)
    assert manifest["exportContentHash"] == _hash(export)
    assert manifest["generatorInputHash"] == _hash(manifest["generatorInput"])
    parameters = manifest["generatorInput"]["parameters"]
    assert parameters["limitScale"] == 0.99
    assert parameters["maxJerk"] == [case.axis_limits[0].maximum_jerk_mm_s3 * 0.99]
    assert export.samples[0].position_mm == pytest.approx(case.reference_path[0])
    assert export.samples[-1].position_mm == pytest.approx(case.reference_path[-1], abs=1e-12)
    assert all(sample.sample_index == i and sample.t == i * case.sample_period_seconds for i, sample in enumerate(export.samples))
    report = compare_cnc_exports({"case": case, "baseline": export, "candidate": repeated})
    assert report.outcome == "WithinTolerance"
    assert "Offline SUT validation" in " ".join(report.reasons)


def test_long_move_matches_independent_piecewise_cubic_solution(local_sut):
    case = offline_cases()[0]
    export, manifest = generate_ruckig_export(case, RuckigOfflineOptions(limitScale=1))
    # D=100, V=10, A=100, J=1000: tj=0.1, no acceleration plateau,
    # cruise=9.8 and total=10.2. This oracle does not call Ruckig or Axiom metrics.
    assert manifest["trajectoryDurationSeconds"] == pytest.approx(10.2, abs=1e-12)
    def expected(t):
        if t > 5.1:
            return 100 - expected(10.2 - t)
        if t <= 0.1:
            return 1000 * t**3 / 6
        if t <= 0.2:
            u = t - 0.1
            return 1 / 6 + 5 * u + 50 * u**2 - 1000 * u**3 / 6
        return 1 + 10 * (t - 0.2)
    for sample in export.samples:
        assert sample.position_mm[0] == pytest.approx(expected(sample.t), abs=1e-10)
        assert sample.position_mm[1:] == (0, 0)


@pytest.mark.parametrize("name,lower_bound", [
    ("short", 4 * (0.001 / (2 * 1000)) ** (1 / 3)),
    ("velocity-boundary", 1 / 1 + 2 * math.sqrt(1 / 1000)),
])
def test_discrete_duration_matches_independent_rest_to_rest_lower_bound(name, lower_bound, local_sut):
    case = next(c for c in offline_cases() if c.case_id.endswith(name))
    export, _ = generate_ruckig_export(case, RuckigOfflineOptions(limitScale=1))
    assert lower_bound - 1e-12 <= export.samples[-1].t <= lower_bound + case.sample_period_seconds + 1e-12


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_offset_and_negative_motion_preserve_stationary_axes(axis, local_sut):
    payload = offline_cases()[1].model_dump(mode="json", by_alias=True)
    start = [2.0, -3.0, 4.0]
    end = start.copy()
    end[axis] -= 0.001
    payload["referencePath"] = [start, end]
    case = CncBenchmarkCase.model_validate(payload)
    export, _ = generate_ruckig_export(case)
    assert export.samples[-1].position_mm == pytest.approx(end, abs=1e-12)
    for index in range(3):
        if index != axis:
            assert all(sample.position_mm[index] == start[index] for sample in export.samples)
    assert compare_cnc_exports({"case": case, "baseline": export, "candidate": export}).outcome == "WithinTolerance"


@pytest.mark.parametrize("damage", ["offset", "unfinished", "stationary", "backward", "overspeed"])
def test_injected_trajectory_faults_cannot_be_promoted(damage, local_sut):
    case = offline_cases()[1]
    export, _ = generate_ruckig_export(case)
    candidate = export.model_dump(mode="json", by_alias=True, exclude_none=True)
    samples = candidate["samples"]
    if damage == "offset":
        samples[10]["positionMm"][1] += 0.01
    elif damage == "unfinished":
        samples[-1]["positionMm"][0] /= 2
    elif damage == "stationary":
        for sample in samples:
            sample["positionMm"][0] = 0
    elif damage == "backward":
        samples[10]["positionMm"][0] = samples[5]["positionMm"][0]
    else:
        samples[10]["positionMm"][0] = 1.0
    report = compare_cnc_exports({"case": case, "baseline": export, "candidate": candidate})
    assert report.outcome == "CandidateViolatesLimits"
    if damage == "overspeed":
        assert next(c for c in report.candidate.checks if c.check_id == "X.discrete-velocity").status == "Violated"


@pytest.mark.parametrize("damage", ["missing", "reordered", "clock", "case-hash"])
def test_injected_contract_faults_are_rejected(damage, local_sut):
    case = offline_cases()[1]
    export, _ = generate_ruckig_export(case)
    candidate = export.model_dump(mode="json", by_alias=True)
    if damage == "missing":
        del candidate["samples"][5]
    elif damage == "reordered":
        candidate["samples"][5], candidate["samples"][6] = candidate["samples"][6], candidate["samples"][5]
    elif damage == "clock":
        candidate["samples"][5]["t"] += 0.0001
    else:
        candidate["caseContentHash"] = "0" * 64
    with pytest.raises(ValidationError):
        compare_cnc_exports({"case": case, "baseline": export, "candidate": candidate})


def test_unsupported_geometry_is_rejected_before_loading_sut(monkeypatch):
    monkeypatch.setitem(sys.modules, "ruckig", None)
    for path in ([[0, 0, 0], [1, 1, 0]], [[0, 0, 0], [1, 0, 0], [2, 0, 0]]):
        payload = offline_cases()[0].model_dump(mode="json", by_alias=True)
        payload["referencePath"] = path
        with pytest.raises(ValueError, match="single-axis|moving axis"):
            generate_ruckig_export(payload)


def test_missing_optional_dependency_has_actionable_error(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(sys.modules, "ruckig", None)
    assert main(["benchmark-offline-suite", "--out-dir", str(tmp_path / "run")]) == 2
    assert ".[offline]" in capsys.readouterr().err
    assert not (tmp_path / "run").exists()


def test_sample_budget_and_position_limits_fail_without_outputs(local_sut):
    payload = offline_cases()[0].model_dump(mode="json", by_alias=True)
    payload["samplePeriodSeconds"] = 1e-6
    with pytest.raises(ValueError, match="100000 samples"):
        generate_ruckig_export(payload)
    payload = offline_cases()[1].model_dump(mode="json", by_alias=True)
    payload["samplePeriodSeconds"] = 1
    with pytest.raises(ValueError, match="4..100000 samples"):
        generate_ruckig_export(payload)
    payload["referencePath"][1][0] = 201
    with pytest.raises(ValueError, match="position limits"):
        generate_ruckig_export(payload)


@pytest.mark.parametrize("scale", [0, -1, 1.01, float("nan"), float("inf"), True])
def test_invalid_generator_scale_is_rejected(scale):
    with pytest.raises(ValidationError):
        RuckigOfflineOptions(limitScale=scale)


def test_cli_suite_replays_serialized_files_and_does_not_overwrite(tmp_path, capsys, local_sut):
    first, second = tmp_path / "run-1", tmp_path / "run-2"
    for directory in (first, second):
        assert main(["benchmark-offline-suite", "--out-dir", str(directory)]) == 0
        assert json.loads(capsys.readouterr().out)["passed"] is True
    assert sorted(p.name for p in first.iterdir()) == sorted(p.name for p in second.iterdir())
    for path in first.iterdir():
        assert path.read_bytes() == (second / path.name).read_bytes()
    for name in ("long", "short", "velocity-boundary"):
        assert main(["benchmark", str(first / f"{name}.request.json")]) == 0
        assert json.loads(capsys.readouterr().out) == json.loads((first / f"{name}.report.json").read_text())
    saved = (first / "summary.json").read_bytes()
    assert main(["benchmark-offline-suite", "--out-dir", str(first)]) == 2
    assert "overwritten" in capsys.readouterr().err
    assert (first / "summary.json").read_bytes() == saved
    assert main(["benchmark-ruckig", "--case", str(first / "short.case.json"), "--out", str(tmp_path / "short.json")]) == 0
    capsys.readouterr()
    manifest = json.loads((tmp_path / "short.manifest.json").read_text())
    assert manifest["exportContentHash"] == _hash(json.loads((tmp_path / "short.json").read_text()))
    assert main(["benchmark-ruckig", "--case", str(first / "short.case.json"), "--out", str(tmp_path / "short.json")]) == 2
    assert "already exist" in capsys.readouterr().err
