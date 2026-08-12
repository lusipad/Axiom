from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r7_http_manifest_scenarios_and_example_share_the_contract() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest = client.get("/api/v1/control/r7/manifest")
    scenarios = client.get("/api/v1/control/r7/scenarios")
    example = client.get("/api/v1/examples/control-r7")

    assert manifest.status_code == 200
    assert scenarios.status_code == 200
    assert example.status_code == 200
    assert manifest.json()["permissionCeiling"] == "Shadow"
    assert manifest.json()["deviceWriteAllowed"] is False
    assert scenarios.json()[0]["scenarioId"] == "synthetic-shadow-nominal"
    assert example.json()["runtimeAudit"]["finalState"] == "Completed"


def test_r7_http_replay_returns_a_public_run_spec_and_stop_receipts() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.post(
        "/api/v1/control/r7/replay",
        json={"scenarioId": "synthetic-shadow-limit-breach"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtimeAudit"]["finalState"] == "RollbackVerified"
    assert payload["runtimeAudit"]["stopReceipt"]["deviceStopCommandIssued"] is False
    assert payload["runtimeAudit"]["rollbackReceipt"]["status"] == "BaselineRetained"
    assert payload["runSpec"]["domainPackId"] == "control.domain-pack@1"


def test_r7_http_rejects_unknown_scenario() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.get(
        "/api/v1/examples/control-r7", params={"scenarioId": "unknown"}
    )

    assert response.status_code == 404
