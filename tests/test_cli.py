import json
from pathlib import Path

import axiom.cli as cli_module
import axiom.web as web_module
from axiom.cli import main
from axiom.experiment import contour_ab_example
from axiom.five_axis import f0_example_run_spec
import uvicorn


COMPARISON_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "cnc_scenarios"
    / "comparisons"
    / "cnc-contour-ab-pass-vs-fail.json"
)


def test_cli_evaluates_a_json_request(tmp_path, capsys):
    request = {
        "artifact": {
            "artifactType": "ordered-point-sequence",
            "schemaVersion": 1,
            "points": [[0, 0], [3, 4]],
        },
        "case": {
            "caseId": "cli-test@1",
            "requiredMetrics": ["path.length.open"],
        },
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    exit_code = main(["evaluate", str(request_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["executionStatus"] == "Succeeded"
    assert output["caseOutcome"] == "Passed"
    assert output["metricResults"][0]["unit"] == "coordinate-unit"


def test_cli_uses_exit_code_two_for_malformed_json(tmp_path, capsys):
    request_path = tmp_path / "broken.json"
    request_path.write_text("{", encoding="utf-8")

    assert main(["evaluate", str(request_path)]) == 2
    assert "无法读取评估请求" in capsys.readouterr().err


def test_cli_uses_exit_code_two_when_request_file_is_missing(tmp_path, capsys):
    request_path = tmp_path / "missing.json"

    assert main(["evaluate", str(request_path)]) == 2
    assert "无法读取评估请求" in capsys.readouterr().err


def test_cli_rejects_a_request_larger_than_its_byte_budget(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli_module, "MAX_REQUEST_BYTES", 8)
    request_path = tmp_path / "oversized.json"
    request_path.write_bytes(b" " * 9)

    assert main(["evaluate", str(request_path)]) == 2
    assert "评估请求超过 8 字节限制" in capsys.readouterr().err


def test_cli_uses_exit_code_one_for_a_failed_hard_gate(tmp_path, capsys):
    request = {
        "artifact": {
            "artifactType": "ordered-point-sequence",
            "schemaVersion": 1,
            "points": [[0, 0], [3, 4]],
        },
        "case": {
            "caseId": "cli-failed-gate@1",
            "requiredMetrics": [
                {
                    "metricId": "path.length.open",
                    "threshold": {"operator": "<=", "value": 4},
                }
            ],
        },
    }
    request_path = tmp_path / "failed.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    assert main(["evaluate", str(request_path)]) == 1
    assert json.loads(capsys.readouterr().out)["caseOutcome"] == "Failed"


def test_cli_runs_an_explicit_domain_pack_run_spec(tmp_path, capsys):
    run_spec = {
        "subjectId": "imported-artifact@1",
        "domainPackId": "ordered-point.domain-pack@1",
        "runnerId": "artifact-import@1",
        "evaluatorVersion": "ordered-point-evaluator@1",
        "request": {
            "artifact": {
                "artifactType": "ordered-point-sequence",
                "schemaVersion": 1,
                "points": [[0, 0], [3, 4]],
            },
            "case": {
                "caseId": "cli-run-spec@1",
                "requiredMetrics": ["path.length.open"],
            },
        },
    }
    request_path = tmp_path / "run-spec.json"
    request_path.write_text(json.dumps(run_spec), encoding="utf-8")

    assert main(["run", str(request_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["run"]["domainPackId"] == "ordered-point.domain-pack@1"
    assert output["report"]["caseOutcome"] == "Passed"
    assert output["observation"]["artifact"]["points"] == [[0.0, 0.0], [3.0, 4.0]]


def test_cli_returns_two_for_a_malformed_domain_run_spec(tmp_path, capsys):
    request_path = tmp_path / "malformed-run-spec.json"
    request_path.write_text(json.dumps({"subjectId": "broken", "request": {}}), encoding="utf-8")

    assert main(["run", str(request_path)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["report"]["caseOutcome"] == "Invalid"
    assert output["report"]["domainFailures"][0]["code"] == "MalformedRunSpec"


def test_cli_runs_the_five_axis_f0_contract_without_math_claims(tmp_path, capsys):
    request_path = tmp_path / "five-axis-f0-run-spec.json"
    request_path.write_text(json.dumps(f0_example_run_spec()), encoding="utf-8")

    assert main(["run", str(request_path)]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["run"]["domainPackId"] == "five-axis.domain-pack@1"
    assert output["report"]["caseOutcome"] == "Passed"
    metric = output["report"]["metricResults"][0]
    assert metric["metricId"] == "five-axis.contract.readiness@1"
    assert metric["status"] == "Computed"
    assert metric["value"] is True
    assert [claim["claimDefinitionId"] for claim in output["claims"]] == [
        "axiom.core.case-outcome-claim@1"
    ]


def test_cli_returns_a_structured_invalid_report_with_exit_code_two(tmp_path, capsys):
    request = {
        "artifact": {
            "artifactType": "ordered-point-sequence",
            "schemaVersion": 1,
            "points": [],
        },
        "case": {
            "caseId": "cli-invalid-input@1",
            "requiredMetrics": ["point.count"],
        },
    }
    request_path = tmp_path / "invalid.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    assert main(["evaluate", str(request_path)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["caseOutcome"] == "Invalid"
    assert output["domainFailures"][0]["code"] == "EmptySequence"


def test_cli_compares_two_imported_runs(capsys):
    exit_code = main(["compare", str(COMPARISON_FIXTURE)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["compatibility"]["compatible"] is True
    assert {item["metricId"] for item in output["metricComparisons"]} == {
        "paired.euclidean.max",
        "paired.euclidean.rms",
    }


def test_cli_returns_one_without_deltas_for_incompatible_runs(tmp_path, capsys):
    comparison = json.loads(COMPARISON_FIXTURE.read_text(encoding="utf-8"))
    comparison["right"]["request"]["case"]["caseId"] = "different-case@1"
    comparison_path = tmp_path / "incompatible.json"
    comparison_path.write_text(json.dumps(comparison), encoding="utf-8")

    assert main(["compare", str(comparison_path)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["compatibility"]["compatible"] is False
    assert output["metricComparisons"] == []
    assert "CaseMismatch" in {item["code"] for item in output["compatibility"]["issues"]}


def test_cli_returns_two_for_a_malformed_comparison_spec(tmp_path, capsys):
    comparison_path = tmp_path / "malformed-comparison.json"
    comparison_path.write_text(json.dumps({"left": {}}), encoding="utf-8")

    assert main(["compare", str(comparison_path)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["compatibility"]["issues"][0]["code"] == "MalformedComparisonSpec"


def test_cli_rejects_a_comparison_larger_than_its_byte_budget(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli_module, "MAX_COMPARISON_BYTES", 8)
    comparison_path = tmp_path / "oversized-comparison.json"
    comparison_path.write_bytes(b" " * 9)

    assert main(["compare", str(comparison_path)]) == 2
    assert "比较请求超过 8 字节限制" in capsys.readouterr().err


def test_cli_executes_a_true_two_arm_experiment(tmp_path, capsys):
    experiment_path = tmp_path / "experiment.json"
    experiment_path.write_text(
        contour_ab_example().model_dump_json(by_alias=True),
        encoding="utf-8",
    )

    assert main(["experiment", str(experiment_path)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["executionStatus"] == "Succeeded"
    assert output["caseOutcome"] == "Failed"
    assert output["comparison"]["compatibility"]["compatible"] is True
    assert len(output["armResults"]) == 2


def test_cli_returns_two_for_a_malformed_experiment_spec(tmp_path, capsys):
    experiment_path = tmp_path / "malformed-experiment.json"
    experiment_path.write_text(json.dumps({"experimentId": "broken"}), encoding="utf-8")

    assert main(["experiment", str(experiment_path)]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "MalformedExperimentSpec"


def test_cli_rejects_an_experiment_larger_than_its_byte_budget(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli_module, "MAX_EXPERIMENT_BYTES", 8)
    experiment_path = tmp_path / "oversized-experiment.json"
    experiment_path.write_bytes(b" " * 9)

    assert main(["experiment", str(experiment_path)]) == 2
    assert "实验请求超过 8 字节限制" in capsys.readouterr().err


def test_cli_serve_forwards_the_explicit_bind_address(monkeypatch):
    app = object()
    captured = {}

    monkeypatch.setattr(web_module, "create_app", lambda: app)

    def fake_run(received_app, *, host, port):
        captured.update(app=received_app, host=host, port=port)

    monkeypatch.setattr(uvicorn, "run", fake_run)

    assert main(["serve", "--host", "0.0.0.0", "--port", "9123"]) == 0
    assert captured == {"app": app, "host": "0.0.0.0", "port": 9123}
