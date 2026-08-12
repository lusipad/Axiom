from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r41_http_contract_exposes_open_two_run_windows_protocol() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest = client.get("/api/v1/physical/r41/manifest")
    scenarios = client.get("/api/v1/physical/r41/scenarios")
    example = client.get("/api/v1/examples/physical-r41")

    assert manifest.status_code == 200
    assert scenarios.status_code == 200
    assert example.status_code == 200
    assert manifest.json()["supportedPlatforms"] == ["Windows"]
    assert manifest.json()["requiredIndependentRuns"] == 2
    assert manifest.json()["interpolationAllowed"] is False
    assert manifest.json()["realityValidationStatus"] == "Open"
    assert scenarios.json()[0]["countsTowardReality"] is False
    assert example.json()["calibrationPair"] is None
    assert example.json()["validationPair"] is None


def test_r41_http_empty_assessment_remains_inconclusive() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.post("/api/v1/physical/r41/assess", json={})

    assert response.status_code == 200
    analysis = response.json()["analysis"]
    assert analysis["realityValidationStatus"] == "Open"
    assert analysis["countsTowardReality"] is False
    assert analysis["deviceSafetyStatus"] == "NotAssessed"
    assert analysis["processSafetyStatus"] == "NotAssessed"


def test_r41_http_rejects_unknown_scenario() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.get(
        "/api/v1/examples/physical-r41", params={"scenarioId": "unknown"}
    )

    assert response.status_code == 404
