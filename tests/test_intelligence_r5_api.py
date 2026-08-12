from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_intelligence_r5_endpoints_expose_typed_windows_contract() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest_response = client.get("/api/v1/intelligence/r5/manifest")
    scenarios_response = client.get("/api/v1/intelligence/r5/scenarios")
    example_response = client.get("/api/v1/examples/intelligence-r5")

    assert manifest_response.status_code == 200
    assert scenarios_response.status_code == 200
    assert example_response.status_code == 200
    manifest = manifest_response.json()
    scenarios = scenarios_response.json()
    example = example_response.json()
    assert manifest["platform"] == "windows"
    assert manifest["stage"] == "R5-A"
    assert manifest["syntheticLearningContractStatus"] == "Passed"
    assert manifest["realWorldGeneralizationStatus"] == "Open"
    assert manifest["safetyBanner"] == "SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE"
    assert scenarios[0]["scenarioId"] == "synthetic-residual-contract"
    assert scenarios[0]["expectedOutcome"] == "Passed"
    assert scenarios[1]["expectedOutcome"] == "Invalid"
    assert example["runSpec"]["domainPackId"] == "intelligence.domain-pack@1"
    assert example["evaluation"]["syntheticLearningContractStatus"] == "Passed"
    assert example["evaluation"]["realWorldGeneralizationStatus"] == "Open"
    assert example["evaluation"]["axisResults"][0]["status"] == "Validated"
    assert example["evaluation"]["oodDetectionRate"] == 1.0


def test_intelligence_r5_unknown_scenario_returns_not_found() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.get(
        "/api/v1/examples/intelligence-r5",
        params={"scenarioId": "missing"},
    )

    assert response.status_code == 404


def test_intelligence_r5_counterexample_does_not_publish_positive_evaluation() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.get(
        "/api/v1/examples/intelligence-r5",
        params={"scenarioId": "group-leak"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scenario"]["expectedExecutionStatus"] == "Skipped"
    assert payload["scenario"]["expectedOutcome"] == "Invalid"
    assert "evaluation" not in payload


def test_intelligence_r5_openapi_freezes_response_models() -> None:
    openapi = create_app(serve_frontend=False).openapi()

    manifest_schema = openapi["paths"]["/api/v1/intelligence/r5/manifest"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    scenarios_schema = openapi["paths"]["/api/v1/intelligence/r5/scenarios"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    example_schema = openapi["paths"]["/api/v1/examples/intelligence-r5"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    assert manifest_schema == {"$ref": "#/components/schemas/R5Manifest"}
    assert scenarios_schema["items"] == {"$ref": "#/components/schemas/R5ScenarioSummary"}
    assert example_schema == {"$ref": "#/components/schemas/R5ExamplePayload"}
