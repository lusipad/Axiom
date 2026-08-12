from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r6_http_manifest_scenarios_and_example_share_the_frozen_contract() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest = client.get("/api/v1/optimization/r6/manifest")
    scenarios = client.get("/api/v1/optimization/r6/scenarios")
    example = client.get("/api/v1/examples/optimization-r6")

    assert manifest.status_code == 200
    assert scenarios.status_code == 200
    assert example.status_code == 200
    assert manifest.json()["permissionLevel"] == "Offline"
    assert scenarios.json()[0]["scenarioId"] == "canonical-head-table-offline-pareto"
    assert len(example.json()["recommendationSet"]["candidates"]) == 6


def test_r6_http_search_applies_user_goal_constraints_and_returns_a_public_run_spec() -> (
    None
):
    client = TestClient(create_app(serve_frontend=False))

    response = client.post(
        "/api/v1/optimization/r6/search",
        json={
            "schemaId": "optimization.search-request@1",
            "scenarioId": "canonical-head-table-offline-pareto",
            "goal": {
                "goalId": "optimization.r6.fast-low-sample-goal@1",
                "objectiveIds": [
                    "cycleTimeSeconds",
                    "linearFollowingErrorMaxMm",
                    "commandSampleCount",
                ],
                "maximumCycleTimeSeconds": 0.70,
                "maximumCommandSampleCount": 12,
            },
            "grid": {
                "feedOverrides": [0.70, 0.85, 1.0],
                "samplePeriods": [0.04, 0.08],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["recommendationSet"]["paretoCandidateIds"]) == 1
    assert payload["runSpec"]["domainPackId"] == "optimization.domain-pack@1"
    assert payload["recommendationSet"]["deviceWriteAllowed"] is False


def test_r6_http_rejects_unvalidated_search_period() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.post(
        "/api/v1/optimization/r6/search",
        json={
            "grid": {"feedOverrides": [1.0], "samplePeriods": [0.06]},
        },
    )

    assert response.status_code == 422
