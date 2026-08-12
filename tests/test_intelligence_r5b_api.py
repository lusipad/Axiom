from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_intelligence_r5b_endpoints_expose_windows_real_holdout_readiness_contract() -> (
    None
):
    client = TestClient(create_app(serve_frontend=False))

    manifest_response = client.get("/api/v1/intelligence/r5b/manifest")
    scenarios_response = client.get("/api/v1/intelligence/r5b/scenarios")
    example_response = client.get("/api/v1/examples/intelligence-r5b")

    assert manifest_response.status_code == 200
    assert scenarios_response.status_code == 200
    assert example_response.status_code == 200

    manifest = manifest_response.json()
    scenarios = scenarios_response.json()
    example = example_response.json()

    assert manifest["platform"] == "windows"
    assert manifest["stage"] == "R5-B"
    assert manifest["domainPackId"] == "intelligence.domain-pack@2"
    assert manifest["contractReadinessStatus"] == "Passed"
    assert manifest["realWorldGeneralizationStatus"] == "Open"
    assert manifest["safetyBanner"] == "REAL HOLDOUT VALIDATION / NOT DEVICE SAFE"
    assert (
        manifest["realityBanner"]
        == "NO BUNDLED REAL CAPTURE / CASE-SCOPED EVIDENCE REQUIRED"
    )
    assert manifest["requiredEvidence"]
    assert scenarios == [
        {
            "scenarioId": "real-holdout-readiness-open",
            "title": "Windows real holdout readiness (open)",
            "description": "The R5-A model lineage is sealed, but no bundled controller-export or device-read holdout exists.",
            "expectedOutcome": "Inconclusive",
            "expectedExecutionStatus": "Succeeded",
            "realWorldGeneralizationStatus": "Open",
        }
    ]
    assert example["manifest"]["domainPackId"] == "intelligence.domain-pack@2"
    assert example["runSpec"]["domainPackId"] == "intelligence.domain-pack@2"
    assert example["runSpec"]["request"].get("realHoldoutSet") is None
    assert example["readinessChecks"][0]["status"] == "Passed"
    assert example["readinessChecks"][-1]["status"] == "Open"
    assert "evaluation" not in example

    run_response = client.post("/api/v1/runs/evaluate", json=example["runSpec"])
    assert run_response.status_code == 200
    bundle = run_response.json()
    assert bundle["run"]["executionStatus"] == "Succeeded"
    assert bundle["run"]["caseOutcome"] == "Inconclusive"
    real_claim = next(
        claim
        for claim in bundle["claims"]
        if claim["claimDefinitionId"]
        == "intelligence.real-world-generalization-claim@1"
    )
    assert real_claim["status"] == "Inconclusive"
    assert real_claim["reasonCode"] == "RealPairedHoldoutMissing"
    serialized = str(bundle).lower()
    assert "device-safe" not in serialized
    assert "process-safe" not in serialized
    assert "writeback" not in serialized


def test_intelligence_r5b_unknown_scenario_returns_not_found() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.get(
        "/api/v1/examples/intelligence-r5b",
        params={"scenarioId": "missing"},
    )

    assert response.status_code == 404


def test_intelligence_r5b_openapi_freezes_response_models() -> None:
    openapi = create_app(serve_frontend=False).openapi()

    manifest_schema = openapi["paths"]["/api/v1/intelligence/r5b/manifest"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    scenarios_schema = openapi["paths"]["/api/v1/intelligence/r5b/scenarios"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    example_schema = openapi["paths"]["/api/v1/examples/intelligence-r5b"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]

    assert manifest_schema == {"$ref": "#/components/schemas/R5BManifest"}
    assert scenarios_schema["items"] == {
        "$ref": "#/components/schemas/R5BScenarioSummary"
    }
    assert example_schema == {"$ref": "#/components/schemas/R5BExamplePayload"}
