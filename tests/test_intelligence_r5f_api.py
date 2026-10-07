from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r5f_manifest_and_impact_endpoint_keep_candidate_evaluated_only() -> None:
    client = TestClient(create_app(serve_frontend=False))
    manifest_response = client.get("/api/v1/intelligence/r5f/manifest")
    assert manifest_response.status_code == 200
    assert manifest_response.json()["candidateUseStatus"] == "EvaluatedOnly"

    example = client.get("/api/v1/examples/intelligence-r5e").json()
    approved = client.post(
        "/api/v1/intelligence/r5e/campaigns/approve",
        json={
            "planRequest": example["planRequest"],
            "plan": example["plan"],
            "accountablePartyId": "web-impact-reviewer",
            "syntheticOnlyAcknowledged": True,
        },
    ).json()
    campaign_report = client.post(
        "/api/v1/intelligence/r5e/campaigns/execute", json=approved
    ).json()

    response = client.post(
        "/api/v1/intelligence/r5f/impact/assess",
        json={"campaignReport": campaign_report},
    )

    assert response.status_code == 200
    report = response.json()
    assert report["impactGateStatus"] == "Passed"
    assert len(report["scenarioImpacts"]) == 3
    assert report["candidateUseStatus"] == "EvaluatedOnly"
    assert report["modelPromotionStatus"] == "NotPerformed"
    assert report["realWorldGeneralizationStatus"] == "Open"
    assert report["deviceWriteAllowed"] is False


def test_r5f_openapi_freezes_the_read_only_impact_contract() -> None:
    openapi = create_app(serve_frontend=False).openapi()
    manifest = openapi["paths"]["/api/v1/intelligence/r5f/manifest"]["get"]
    assess = openapi["paths"]["/api/v1/intelligence/r5f/impact/assess"]["post"]

    assert manifest["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5FManifest"
    }
    assert assess["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5FImpactAssessmentCommand"
    }
    assert assess["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5FCandidateImpactReport"
    }

