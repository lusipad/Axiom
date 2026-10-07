from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.intelligence import (
    build_r5i_preflight_request,
)
from axiom.web import create_app
from tests.test_intelligence_r5i import (
    AUTHORITY_KEY,
    AUTHORITY_KEY_ID,
    _approved_decision,
    _passed_chain,
)


def test_r5i_read_only_api_exposes_manifest_empty_registry_and_no_mutators(
    tmp_path,
) -> None:
    registry = tmp_path / "r5i-api.db"
    client = TestClient(
        create_app(
            serve_frontend=False,
            r5i_registry_path=registry,
            r5i_authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        )
    )

    manifest = client.get("/api/v1/intelligence/r5i/manifest")
    status = client.get("/api/v1/intelligence/r5i/registry/status")
    monitoring = client.get("/api/v1/intelligence/r5i/monitoring/windows")
    prediction = client.post(
        "/api/v1/intelligence/r5i/predict",
        json={"feedOverride": 0.825, "samplePeriod": 0.08},
    )

    assert manifest.status_code == 200
    assert manifest.json()["stage"] == "R5-I"
    assert manifest.json()["webStateMutationAllowed"] is False
    assert status.status_code == 200
    assert status.json()["registryInitialized"] is False
    assert monitoring.status_code == 200
    assert monitoring.json() == []
    assert prediction.status_code == 422
    assert not registry.exists()

    paths = create_app(serve_frontend=False).openapi()["paths"]
    assert "/api/v1/intelligence/r5i/promote" not in paths
    assert "/api/v1/intelligence/r5i/activate" not in paths
    assert "/api/v1/intelligence/r5i/rollback" not in paths


def test_r5i_preflight_api_replays_without_registry_write(tmp_path) -> None:
    registry = tmp_path / "r5i-preflight-api.db"
    dossier, _, _, assessment = _passed_chain()
    decision = _approved_decision(dossier, assessment)
    request = build_r5i_preflight_request(dossier, assessment, decision)
    client = TestClient(
        create_app(
            serve_frontend=False,
            r5i_registry_path=registry,
            r5i_authority_keys={AUTHORITY_KEY_ID: AUTHORITY_KEY},
        )
    )

    response = client.post(
        "/api/v1/intelligence/r5i/promotion/preflight",
        json={"request": request.model_dump(mode="json", by_alias=True)},
    )

    assert response.status_code == 200, response.text
    report = response.json()
    assert report["overallStatus"] == "Passed"
    assert report["promotionTransactionStatus"] == "Eligible"
    assert report["registryTransactionAllowed"] is True
    assert report["modelRegistryWritePerformed"] is False
    assert report["activationPerformed"] is False
    assert report["deviceWriteAllowed"] is False
    assert not registry.exists()


def test_r5i_openapi_freezes_read_only_contracts_and_old_r7e_ref() -> None:
    openapi = create_app(serve_frontend=False).openapi()
    paths = openapi["paths"]

    assert paths["/api/v1/intelligence/r5i/manifest"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5IManifest"
    }
    assert paths["/api/v1/intelligence/r5i/promotion/preflight"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5IPreflightCommand"
    }
    assert paths["/api/v1/intelligence/r5i/registry/status"]["get"]["responses"][
        "200"
    ]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5IRegistryStatus"
    }
    assert paths["/api/v1/control/r7e/assess"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R7EExamplePayload"
    }
