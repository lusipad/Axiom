from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r5d_manifest_example_and_plan_endpoints_are_semantically_equal() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest_response = client.get("/api/v1/intelligence/r5d/manifest")
    example_response = client.get("/api/v1/examples/intelligence-r5d")
    assert manifest_response.status_code == 200
    assert example_response.status_code == 200

    manifest = manifest_response.json()
    example = example_response.json()
    plan_response = client.post(
        "/api/v1/intelligence/r5d/plan", json=example["request"]
    )

    assert plan_response.status_code == 200
    assert manifest["stage"] == "R5-D"
    assert manifest["automaticExecutionAllowed"] is False
    assert plan_response.json() == example["plan"]
    assert len(example["plan"]["proposals"]) == 5
    assert example["plan"]["deviceWriteAllowed"] is False


def test_r5d_api_rejects_invalid_batch_size() -> None:
    client = TestClient(create_app(serve_frontend=False))
    request = client.get("/api/v1/examples/intelligence-r5d").json()["request"]
    request["batchSize"] = 11

    response = client.post("/api/v1/intelligence/r5d/plan", json=request)

    assert response.status_code == 422


def test_r5d_openapi_freezes_typed_contracts() -> None:
    openapi = create_app(serve_frontend=False).openapi()

    manifest = openapi["paths"]["/api/v1/intelligence/r5d/manifest"]["get"]
    example = openapi["paths"]["/api/v1/examples/intelligence-r5d"]["get"]
    plan = openapi["paths"]["/api/v1/intelligence/r5d/plan"]["post"]

    assert manifest["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5DManifest"
    }
    assert example["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5DExamplePayload"
    }
    assert plan["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5DExperimentPlanRequest"
    }
    assert plan["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SimulationExperimentPlan"
    }
