from __future__ import annotations

import copy
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from axiom.benchmark import _hash, cnc_benchmark_example, cnc_diagnostics, compare_cnc_exports
from axiom.benchmark_validation import VALIDATION_SCENARIOS, evaluate_validation_experiment, validation_experiment
from axiom.cli import main
from axiom.web import create_app


@pytest.mark.parametrize("definition", VALIDATION_SCENARIOS, ids=lambda item: item["id"])
def test_declared_scenarios_meet_expected_behavior_without_production_claims(definition):
    pytest.importorskip("ruckig")
    experiment = validation_experiment(definition["id"])
    original = copy.deepcopy(experiment)
    result = evaluate_validation_experiment(experiment)
    assert experiment == original
    assert result["passed"] is True
    assert result["observedOutcome"] == definition["expectedOutcome"]
    assert experiment["provenance"]["inputRequestHash"] == _hash(experiment["request"])
    for role in ("baseline", "candidate"):
        assert experiment["request"][role]["sourceKind"] == definition["category"]
        assert experiment["provenance"]["inputExportHashes"][role] == _hash(experiment["request"][role])
    if definition["id"].startswith("aa-"):
        assert result["deterministicGeneration"] is True
    if result["observedOutcome"] == "InputRejected":
        assert result["inputErrors"] and "report" not in result and "diagnostics" not in result
    else:
        assert result["deterministicReplay"] is True
        assert result["report"] == compare_cnc_exports(experiment["request"]).model_dump(mode="json", by_alias=True, exclude_none=True)


def test_diagnostics_share_metric_operators_locations_and_hashes():
    payload = cnc_benchmark_example().model_dump(mode="json", by_alias=True, exclude_none=True)
    diagnostics = cnc_diagnostics(payload)
    report = compare_cnc_exports(payload)
    for role in ("baseline", "candidate"):
        points = diagnostics[role]["points"]
        analysis = getattr(report, role)
        assert diagnostics[role]["exportContentHash"] == analysis.export_content_hash
        assert points[0]["jerkMmS3"] is None
        assert points[1]["accelerationMmS2"] is None
        assert points[-1]["sampleIndex"] == analysis.sample_count - 1
        for order, field, suffix in ((1, "velocityMmS", "velocity"), (2, "accelerationMmS2", "acceleration"), (3, "jerkMmS3", "jerk")):
            expected = np.asarray([sample["positionMm"] for sample in payload[role]["samples"]], dtype=float)
            for _ in range(order):
                expected = np.diff(expected, axis=0) / payload["case"]["samplePeriodSeconds"]
            for point in points[order:]:
                assert point[field] == pytest.approx(expected[point["sampleIndex"] - order].tolist())
            for axis, name in enumerate(("X", "Y", "Z")):
                check = next(check for check in analysis.checks if check.check_id == f"{name}.discrete-{suffix}")
                point = next(point for point in points if point["sampleIndex"] == check.location.sample_index)
                assert abs(point[field][axis]) == check.value


def test_downsampling_retains_check_locations_and_extrema():
    pytest.importorskip("ruckig")
    payload = validation_experiment("backtracking")["request"]
    diagnostics = cnc_diagnostics(payload)
    report = compare_cnc_exports(payload)
    for role in ("baseline", "candidate"):
        series = diagnostics[role]
        assert series["sampleCount"] > series["displayCount"]
        assert series["displayCount"] <= 650
        indices = {point["sampleIndex"] for point in series["points"]}
        assert {check.location.sample_index for check in getattr(report, role).checks if check.location} <= indices
    traversal = next(check for check in report.candidate.checks if check.check_id == "sampled-line-traversal")
    assert traversal.status == "Violated"
    assert all(check.status == "WithinLimit" for check in report.candidate.checks if "discrete-" in check.check_id)


def test_diagnostics_api_and_validation_catalog_are_explicit():
    client = TestClient(create_app(serve_frontend=False))
    assert client.get("/api/v1/benchmarks/cnc/validation-cases").json() == list(VALIDATION_SCENARIOS)
    assert client.get("/api/v1/benchmarks/cnc/validation-cases/unknown").status_code == 404
    payload = cnc_benchmark_example().model_dump(mode="json", by_alias=True, exclude_none=True)
    assert client.post("/api/v1/benchmarks/cnc/diagnostics", json=payload).json() == cnc_diagnostics(payload)
    payload["candidate"]["caseContentHash"] = "0" * 64
    assert client.post("/api/v1/benchmarks/cnc/diagnostics", json=payload).status_code == 422
    pytest.importorskip("ruckig")
    assert client.get("/api/v1/benchmarks/cnc/validation-cases/aa-short").json() == validation_experiment("aa-short")


def test_validation_cli_preserves_requests_reports_rejections_and_existing_evidence(tmp_path, capsys):
    pytest.importorskip("ruckig")
    directory = tmp_path / "v1"
    assert main(["benchmark-validation-suite", "--out-dir", str(directory)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["passed"] and len(summary["cases"]) == 17
    assert main(["benchmark", str(directory / "faster-parameters.request.json")]) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "Improved"
    assert main(["benchmark", str(directory / "missing-sample.request.json")]) == 2
    assert capsys.readouterr().out == ""
    assert "report" not in json.loads((directory / "missing-sample.result.json").read_text(encoding="utf-8"))
    files = {file.name: file.read_bytes() for file in directory.iterdir()}
    assert main(["benchmark-validation-suite", "--out-dir", str(directory)]) == 2
    assert {file.name: file.read_bytes() for file in directory.iterdir()} == files
