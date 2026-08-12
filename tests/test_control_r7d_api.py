from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r7d_http_manifest_scenarios_and_example_freeze_beckhoff_target() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest = client.get("/api/v1/control/r7d/manifest")
    scenarios = client.get("/api/v1/control/r7d/scenarios")
    example = client.get("/api/v1/examples/control-r7d")

    assert manifest.status_code == 200
    assert scenarios.status_code == 200
    assert example.status_code == 200
    assert manifest.json()["targetVendor"] == "Beckhoff Automation"
    assert manifest.json()["targetControllerFamily"] == "TwinCAT 3"
    assert manifest.json()["minimumTwinCatBuild"] == 4026
    assert manifest.json()["targetInterface"] == "TF6100 OPC UA Server"
    assert manifest.json()["vendorProfileStatus"] == "Passed"
    assert manifest.json()["vendorRuntimeStatus"] == "Open"
    assert scenarios.json()[0]["countsTowardReality"] is False
    assert example.json()["profile"]["bindingStatus"] == "Open"
    assert example.json()["readinessAudit"]["vendorRuntimeStatus"] == "Open"


def test_r7d_http_assessment_without_runtime_evidence_remains_open() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.post(
        "/api/v1/control/r7d/assess",
        json={"profile": None, "runtimeEvidence": None, "transportEvidence": None},
    )

    assert response.status_code == 200
    audit = response.json()["readinessAudit"]
    assert audit["readinessOutcome"] == "Open"
    assert audit["vendorProfileStatus"] == "Passed"
    assert audit["vendorRuntimeStatus"] == "Open"
    assert audit["deploymentShadowStatus"] == "Open"
    assert audit["realityValidationStatus"] == "Open"


def test_r7d_http_rejects_unknown_scenario() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.get(
        "/api/v1/examples/control-r7d", params={"scenarioId": "unknown"}
    )

    assert response.status_code == 404
