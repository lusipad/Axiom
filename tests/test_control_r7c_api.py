from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r7c_http_manifest_scenarios_and_example_share_the_open_boundary() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest = client.get("/api/v1/control/r7c/manifest")
    scenarios = client.get("/api/v1/control/r7c/scenarios")
    example = client.get("/api/v1/examples/control-r7c")

    assert manifest.status_code == 200
    assert scenarios.status_code == 200
    assert example.status_code == 200
    assert manifest.json()["supportedPlatforms"] == ["Windows"]
    assert manifest.json()["networkConformanceStatus"] == "Passed"
    assert manifest.json()["vendorAdapterStatus"] == "Open"
    assert manifest.json()["realityValidationStatus"] == "Open"
    assert scenarios.json()[0]["countsTowardReality"] is False
    assert example.json()["transportEvidence"] is None
    assert example.json()["readinessAudit"]["virtualTransportStatus"] == "Open"


def test_r7c_http_assessment_without_evidence_remains_open() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.post(
        "/api/v1/control/r7c/assess",
        json={"transportEvidence": None},
    )

    assert response.status_code == 200
    audit = response.json()["readinessAudit"]
    assert audit["readinessOutcome"] == "Open"
    assert audit["virtualTransportStatus"] == "Open"
    assert audit["vendorAdapterStatus"] == "Open"
    assert audit["deploymentShadowStatus"] == "Open"


def test_r7c_http_rejects_unknown_scenario() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.get(
        "/api/v1/examples/control-r7c", params={"scenarioId": "unknown"}
    )

    assert response.status_code == 404
