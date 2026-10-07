from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r5c_endpoints_expose_separate_outputs_and_synthetic_boundary() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest_response = client.get("/api/v1/intelligence/r5c/manifest")
    scenarios_response = client.get("/api/v1/intelligence/r5c/scenarios")
    example_response = client.get("/api/v1/examples/intelligence-r5c")

    assert manifest_response.status_code == 200
    assert scenarios_response.status_code == 200
    assert example_response.status_code == 200
    manifest = manifest_response.json()
    scenarios = scenarios_response.json()
    example = example_response.json()

    assert manifest["stage"] == "R5-C"
    assert manifest["platform"] == "windows"
    assert manifest["domainPackId"] == "intelligence.domain-pack@3"
    assert manifest["outputTargets"] == [
        "cycleTimeSeconds",
        "linearFollowingErrorMaxMm",
    ]
    assert manifest["realWorldGeneralizationStatus"] == "Open"
    assert manifest["deviceWriteAllowed"] is False
    assert [item["scenarioId"] for item in scenarios] == [
        "canonical-head-table-conditional-effect"
    ]
    assert len(example["dataset"]["samples"]) == 25
    assert [len(item["sampleIds"]) for item in example["splitManifest"]["partitions"]] == [
        15,
        5,
        5,
    ]
    assert [(item["targetId"], item["unit"]) for item in example["predictionExample"]["predictions"]] == [
        ("cycleTimeSeconds", "s"),
        ("linearFollowingErrorMaxMm", "mm"),
    ]

    run_response = client.post("/api/v1/runs/evaluate", json=example["runSpec"])
    assert run_response.status_code == 200
    run_bundle = run_response.json()
    assert run_bundle["run"]["caseOutcome"] == "Passed"
    assert run_bundle["run"]["executionStatus"] == "Succeeded"


def test_r5c_prediction_endpoint_abstains_outside_declared_domain() -> None:
    client = TestClient(create_app(serve_frontend=False))
    example = client.get("/api/v1/examples/intelligence-r5c").json()

    response = client.post(
        "/api/v1/intelligence/r5c/predict",
        json={
            "modelBundle": example["modelBundle"],
            "feedOverride": 1.01,
            "samplePeriod": 0.06,
        },
    )

    assert response.status_code == 200
    prediction = response.json()
    assert prediction["status"] == "Abstained"
    assert prediction["reasonCode"] == "OutsideDeclaredDomain"
    assert prediction["predictions"] == []
    assert prediction["deviceWriteAllowed"] is False


def test_r5c_openapi_freezes_manifest_example_and_prediction_models() -> None:
    openapi = create_app(serve_frontend=False).openapi()

    manifest = openapi["paths"]["/api/v1/intelligence/r5c/manifest"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    example = openapi["paths"]["/api/v1/examples/intelligence-r5c"]["get"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]
    prediction = openapi["paths"]["/api/v1/intelligence/r5c/predict"]["post"]

    assert manifest == {"$ref": "#/components/schemas/R5CManifest"}
    assert example == {"$ref": "#/components/schemas/R5CExamplePayload"}
    assert prediction["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConditionalEffectPredictionRequest"
    }
    assert prediction["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/ConditionalEffectPrediction"}
