from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r7b_http_manifest_scenarios_and_example_share_the_open_boundary() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest = client.get("/api/v1/control/r7b/manifest")
    scenarios = client.get("/api/v1/control/r7b/scenarios")
    example = client.get("/api/v1/examples/control-r7b")

    assert manifest.status_code == 200
    assert scenarios.status_code == 200
    assert example.status_code == 200
    assert manifest.json()["permissionCeiling"] == "Shadow"
    assert manifest.json()["vendorAdapterStatus"] == "Open"
    assert scenarios.json()[0]["countsTowardReality"] is False
    assert example.json()["evidenceSet"] is None
    assert example.json()["readinessAudit"]["deploymentShadowStatus"] == "Open"


def test_r7b_http_assessment_does_not_promote_contract_fixture() -> None:
    client = TestClient(create_app(serve_frontend=False))
    example = client.get("/api/v1/examples/control-r7b").json()
    fixture = client.get(
        "/api/v1/examples/control-r7b", params={"scenarioId": "contract-fixture-blocked"}
    ).json()

    response = client.post(
        "/api/v1/control/r7b/assess",
        json={"evidenceSet": fixture["evidenceSet"]},
    )

    assert response.status_code == 200
    assert response.json()["readinessAudit"]["readinessOutcome"] == "Blocked"
    assert response.json()["readinessAudit"]["deploymentShadowStatus"] == "Open"
    assert example["readinessAudit"]["readinessOutcome"] == "Open"


def test_r7b_http_rejects_unknown_scenario() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.get(
        "/api/v1/examples/control-r7b", params={"scenarioId": "unknown"}
    )

    assert response.status_code == 404
