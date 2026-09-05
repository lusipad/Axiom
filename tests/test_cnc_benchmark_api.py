from __future__ import annotations

import json

from fastapi.testclient import TestClient

from axiom.benchmark import cnc_benchmark_example, compare_cnc_exports
from axiom.cli import main
from axiom.web import create_app


def test_cli_http_and_python_produce_the_same_report(tmp_path, capsys):
    payload = cnc_benchmark_example().model_dump(mode="json", by_alias=True, exclude_none=True)
    paths = {}
    for role, value in payload.items():
        paths[role] = tmp_path / f"{role}.json"
        paths[role].write_text(json.dumps(value), encoding="utf-8-sig")
    expected = compare_cnc_exports(payload).model_dump(mode="json", by_alias=True, exclude_none=True)
    assert main(["benchmark", "--case", str(paths["case"]), "--baseline", str(paths["baseline"]), "--candidate", str(paths["candidate"])]) == 1
    assert json.loads(capsys.readouterr().out) == expected
    client = TestClient(create_app(serve_frontend=False))
    response = client.post("/api/v1/benchmarks/cnc/compare", json=payload)
    assert response.status_code == 200
    assert response.json() == expected
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["benchmark", str(request_path)]) == 1
    assert json.loads(capsys.readouterr().out) == expected
    assert main(["benchmark-case-hash", str(paths["case"])]) == 0
    assert capsys.readouterr().out.strip() == payload["baseline"]["caseContentHash"]
    assert client.post("/api/v1/benchmarks/cnc/case-hash", json=payload["case"]).json()["caseContentHash"] == payload["baseline"]["caseContentHash"]


def test_invalid_input_produces_a_structured_error_and_no_report(tmp_path, capsys):
    assert main(["benchmark"]) == 2
    assert "MalformedCncBenchmark" in capsys.readouterr().err
    broken = tmp_path / "broken.json"
    broken.write_text("[]", encoding="utf-8")
    assert main(["benchmark", str(broken)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "MalformedCncBenchmark" in captured.err
    assert main(["benchmark", str(broken), "--case", str(broken)]) == 2
    capsys.readouterr()
    client = TestClient(create_app(serve_frontend=False))
    payload = cnc_benchmark_example().model_dump(mode="json", by_alias=True)
    payload["candidate"]["caseContentHash"] = "0" * 64
    assert client.post("/api/v1/benchmarks/cnc/compare", json=payload).status_code == 422


def test_discoverable_example_remains_synthetic_and_matches_cli(capsys):
    client = TestClient(create_app(serve_frontend=False))
    example = client.get("/api/v1/benchmarks/cnc/example").json()
    assert example["baseline"]["sourceKind"] == "synthetic-example"
    assert main(["benchmark-example"]) == 0
    assert json.loads(capsys.readouterr().out) == example
    schemas = client.get("/api/openapi.json").json()["components"]["schemas"]
    assert "CncBenchmarkRequest" in schemas
