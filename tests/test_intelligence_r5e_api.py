from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r5e_explicit_approval_and_execution_endpoints_close_one_batch() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest_response = client.get("/api/v1/intelligence/r5e/manifest")
    example_response = client.get("/api/v1/examples/intelligence-r5e")
    assert manifest_response.status_code == 200
    assert example_response.status_code == 200

    manifest = manifest_response.json()
    example = example_response.json()
    approval_response = client.post(
        "/api/v1/intelligence/r5e/campaigns/approve",
        json={
            "planRequest": example["planRequest"],
            "plan": example["plan"],
            "accountablePartyId": "web-reviewer",
            "syntheticOnlyAcknowledged": True,
        },
    )
    assert approval_response.status_code == 200
    approved = approval_response.json()
    assert approved["approval"]["accountablePartyId"] == "web-reviewer"
    assert approved["approval"]["humanApprovalPresent"] is True

    execution_response = client.post(
        "/api/v1/intelligence/r5e/campaigns/execute", json=approved
    )
    assert execution_response.status_code == 200
    report = execution_response.json()
    assert manifest["stage"] == "R5-E"
    assert manifest["automaticExecutionAllowed"] is False
    assert report["campaignExecutionStatus"] == "Succeeded"
    assert len(report["dataset"]["samples"]) == 30
    assert report["candidateAssessment"]["candidateGateStatus"] == "Passed"
    assert report["modelPromotionStatus"] == "NotPerformed"
    assert report["realWorldGeneralizationStatus"] == "Open"
    assert report["deviceWriteAllowed"] is False


def test_r5e_api_requires_the_explicit_synthetic_only_acknowledgement() -> None:
    client = TestClient(create_app(serve_frontend=False))
    example = client.get("/api/v1/examples/intelligence-r5e").json()

    response = client.post(
        "/api/v1/intelligence/r5e/campaigns/approve",
        json={
            "planRequest": example["planRequest"],
            "plan": example["plan"],
            "accountablePartyId": "web-reviewer",
            "syntheticOnlyAcknowledged": False,
        },
    )

    assert response.status_code == 422


def test_r5e_openapi_freezes_manifest_approval_and_execution_contracts() -> None:
    openapi = create_app(serve_frontend=False).openapi()

    manifest = openapi["paths"]["/api/v1/intelligence/r5e/manifest"]["get"]
    example = openapi["paths"]["/api/v1/examples/intelligence-r5e"]["get"]
    approve = openapi["paths"]["/api/v1/intelligence/r5e/campaigns/approve"]["post"]
    execute = openapi["paths"]["/api/v1/intelligence/r5e/campaigns/execute"]["post"]

    assert manifest["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5EManifest"
    }
    assert example["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5EExamplePayload"
    }
    assert approve["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5ECampaignApprovalCommand"
    }
    assert approve["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5ESyntheticCampaignRequest"
    }
    assert execute["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5ESyntheticCampaignRequest"
    }
    assert execute["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5ESyntheticCampaignReport"
    }
