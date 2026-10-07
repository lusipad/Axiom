from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def _javascript_number_round_trip(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _javascript_number_round_trip(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_javascript_number_round_trip(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def test_r5g_api_builds_a_readiness_dossier_without_promotion() -> None:
    client = TestClient(create_app(serve_frontend=False))
    manifest = client.get("/api/v1/intelligence/r5g/manifest")
    assert manifest.status_code == 200
    assert manifest.json()["reviewDecisionStatus"] == (
        "AwaitingIndependentHumanDecision"
    )

    example = client.get("/api/v1/examples/intelligence-r5e").json()
    approved = client.post(
        "/api/v1/intelligence/r5e/campaigns/approve",
        json={
            "planRequest": example["planRequest"],
            "plan": example["plan"],
            "accountablePartyId": "web-readiness-reviewer",
            "syntheticOnlyAcknowledged": True,
        },
    ).json()
    campaign = client.post(
        "/api/v1/intelligence/r5e/campaigns/execute", json=approved
    ).json()
    impact = client.post(
        "/api/v1/intelligence/r5f/impact/assess",
        json={"campaignReport": campaign},
    ).json()
    impact = _javascript_number_round_trip(impact)

    response = client.post(
        "/api/v1/intelligence/r5g/promotion/readiness",
        json={
            "impactReport": impact,
            "preparedBy": "web-promotion-readiness-preparer",
            "realityGateOpenAcknowledged": True,
            "deviceSafetyNotEstablishedAcknowledged": True,
            "automaticDeploymentForbiddenAcknowledged": True,
        },
    )

    assert response.status_code == 200
    dossier = response.json()
    assert dossier["reviewReadinessStatus"] == "ReadyForIndependentReview"
    assert dossier["reviewDecisionStatus"] == "AwaitingIndependentHumanDecision"
    assert dossier["modelPromotionStatus"] == "NotPerformed"
    assert dossier["defaultModelChanged"] is False
    assert dossier["modelRegistryWritePerformed"] is False
    assert dossier["deviceWriteAllowed"] is False


def test_r5g_openapi_freezes_the_readiness_contract() -> None:
    openapi = create_app(serve_frontend=False).openapi()
    manifest = openapi["paths"]["/api/v1/intelligence/r5g/manifest"]["get"]
    prepare = openapi["paths"][
        "/api/v1/intelligence/r5g/promotion/readiness"
    ]["post"]

    assert manifest["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/R5GManifest"}
    assert prepare["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R5GPromotionReadinessCommand"
    }
    assert prepare["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/R5GModelPromotionReadinessDossier"}
