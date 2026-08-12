from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r7e_http_contract_exposes_only_open_windows_example() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest = client.get("/api/v1/control/r7e/manifest")
    scenarios = client.get("/api/v1/control/r7e/scenarios")
    example = client.get("/api/v1/examples/control-r7e")

    assert manifest.status_code == 200
    assert scenarios.status_code == 200
    assert example.status_code == 200
    assert manifest.json()["supportedPlatforms"] == ["Windows"]
    assert manifest.json()["capturePolicy"] == "sample-index-triggered-batch-read"
    assert manifest.json()["deploymentShadowStatus"] == "Open"
    assert scenarios.json()[0]["countsTowardDeploymentShadow"] is False
    assert example.json()["witnessProfile"]["bindingStatus"] == "Open"
    assert example.json()["shadowEvidence"] is None


def test_r7e_http_empty_assessment_keeps_deployment_and_reality_open() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.post("/api/v1/control/r7e/assess", json={})

    assert response.status_code == 200
    audit = response.json()["readinessAudit"]
    assert audit["readinessOutcome"] == "Open"
    assert audit["deploymentShadowStatus"] == "Open"
    assert audit["realityValidationStatus"] == "Open"
    assert audit["countsTowardDeploymentShadow"] is False
    assert audit["countsTowardReality"] is False


def test_r7e_http_assessment_preserves_explicit_case_identity() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.post(
        "/api/v1/control/r7e/assess",
        json={"caseId": "site.part-family-17@1"},
    )

    assert response.status_code == 200
    assert response.json()["runSpec"]["request"]["case"]["caseId"] == (
        "site.part-family-17@1"
    )


def test_r7e_http_rejects_unknown_scenario() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.get(
        "/api/v1/examples/control-r7e", params={"scenarioId": "unknown"}
    )

    assert response.status_code == 404
