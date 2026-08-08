import json

import axiom.cli as cli_module
from axiom.cli import main


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
