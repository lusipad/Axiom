from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from axiom.web import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(serve_frontend=False))


@pytest.fixture(scope="module")
def readiness_dossier(client: TestClient) -> dict[str, object]:
    example = client.get("/api/v1/examples/intelligence-r5e").json()
    approved = client.post(
        "/api/v1/intelligence/r5e/campaigns/approve",
        json={
            "planRequest": example["planRequest"],
            "plan": example["plan"],
            "accountablePartyId": "r5h-api-owner",
            "syntheticOnlyAcknowledged": True,
        },
    ).json()
    campaign = client.post(
        "/api/v1/intelligence/r5e/campaigns/execute",
        json=approved,
    ).json()
    impact = client.post(
        "/api/v1/intelligence/r5f/impact/assess",
        json={"campaignReport": campaign},
    ).json()
    response = client.post(
        "/api/v1/intelligence/r5g/promotion/readiness",
        json={
            "impactReport": impact,
            "preparedBy": "r5h-api-preparer",
            "realityGateOpenAcknowledged": True,
            "deviceSafetyNotEstablishedAcknowledged": True,
            "automaticDeploymentForbiddenAcknowledged": True,
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.fixture(scope="module")
def registration_report(
    client: TestClient,
    readiness_dossier: dict[str, object],
) -> dict[str, object]:
    response = client.post(
        "/api/v1/intelligence/r5h/studies/register",
        json={
            "readinessDossier": readiness_dossier,
            "studyId": "axiom.intelligence.r5h.api-study@1",
            "createdAt": "2026-08-14T01:00:00+00:00",
            "registeredAt": "2026-08-14T01:30:00+00:00",
            "registrationAuthorityId": "r5h-api-model-owner",
            "registrationRecordId": "r5h-api-record-001",
            "cases": [
                {
                    "caseId": "field.r5h.api-case-a@1",
                    "assessmentId": "field.r5h.api-assessment-a@1",
                    "role": "in-domain",
                    "deviceId": "api-machine-a",
                    "conditionId": "cold-start",
                    "feedOverride": 0.65,
                    "samplePeriod": 0.04,
                },
                {
                    "caseId": "field.r5h.api-case-b@1",
                    "assessmentId": "field.r5h.api-assessment-b@1",
                    "role": "in-domain",
                    "deviceId": "api-machine-b",
                    "conditionId": "warm-steady",
                    "feedOverride": 0.825,
                    "samplePeriod": 0.08,
                },
                {
                    "caseId": "field.r5h.api-case-ood@1",
                    "assessmentId": "field.r5h.api-assessment-ood@1",
                    "role": "ood-probe",
                    "deviceId": "api-machine-c",
                    "conditionId": "unseen-load",
                    "feedOverride": 1.0,
                    "samplePeriod": 0.06,
                },
            ],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_r5h_api_registers_then_keeps_missing_real_evidence_open(
    client: TestClient,
    readiness_dossier: dict[str, object],
    registration_report: dict[str, object],
) -> None:
    assert registration_report["registrationStatus"] == "Passed"
    assert registration_report["realWorldGeneralizationStatus"] == "Open"
    assert registration_report["modelRegistryWritePerformed"] is False
    assert registration_report["activationPerformed"] is False
    assert len(registration_report["manifest"]["cases"]) == 3

    response = client.post(
        "/api/v1/intelligence/r5h/holdout/assess",
        json={
            "readinessDossier": readiness_dossier,
            "registrationReport": registration_report,
            "evidenceReports": [],
            "assessmentId": "axiom.intelligence.r5h.api-assessment@1",
        },
    )

    assert response.status_code == 200, response.text
    assessment = response.json()
    assert assessment["overallStatus"] == "Open"
    assert assessment["realWorldGeneralizationStatus"] == "Open"
    assert assessment["caseResults"] == []
    assert assessment["targetResults"] == []
    assert assessment["reviewDecisionStatus"] == ("AwaitingIndependentHumanDecision")
    assert assessment["modelPromotionStatus"] == "NotPerformed"
    assert assessment["defaultModelChanged"] is False
    assert assessment["modelRegistryWritePerformed"] is False
    assert assessment["activationPerformed"] is False
    assert assessment["deviceWriteAllowed"] is False


def test_r5h_openapi_freezes_registration_and_assessment_contracts() -> None:
    openapi = create_app(serve_frontend=False).openapi()
    manifest = openapi["paths"]["/api/v1/intelligence/r5h/manifest"]["get"]
    register = openapi["paths"]["/api/v1/intelligence/r5h/studies/register"]["post"]
    assess = openapi["paths"]["/api/v1/intelligence/r5h/holdout/assess"]["post"]

    assert manifest["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5HManifest"
    }
    assert register["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5HStudyRegistrationCommand"
    }
    assert register["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5HCandidateHoldoutStudyRegistrationReport"
    }
    assert assess["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5HAssessmentCommand"
    }
    assert assess["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5HCandidateHoldoutAssessment"
    }
    evidence_schema = openapi["components"]["schemas"]["R5HAssessmentCommand"][
        "properties"
    ]["evidenceReports"]
    assert evidence_schema["items"] == {
        "additionalProperties": {
            "$ref": "#/components/schemas/JsonValue",
        },
        "type": "object",
    }
