from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r6v2_http_manifest_scenarios_and_example_are_typed() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest = client.get("/api/v1/optimization/r6v2/manifest")
    scenarios = client.get("/api/v1/optimization/r6v2/scenarios")
    example = client.get("/api/v1/examples/optimization-r6v2")

    assert manifest.status_code == 200
    assert scenarios.status_code == 200
    assert example.status_code == 200
    assert manifest.json()["domainPackId"] == "optimization.domain-pack@2"
    assert len(scenarios.json()) == 3
    assert example.json()["recommendationSet"]["screeningReceipt"][
        "candidateCount"
    ] == 135
    assert example.json()["recommendationSet"]["globalOptimalityStatus"] == (
        "NotClaimed"
    )

    openapi = client.get("/api/openapi.json").json()
    assert openapi["paths"]["/api/v1/optimization/r6v2/search"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/R6V2SearchRequest"
    }


def test_r6v2_http_search_accepts_explicit_quality_intent_and_returns_run_spec() -> (
    None
):
    client = TestClient(create_app(serve_frontend=False))
    example = client.get(
        "/api/v1/examples/optimization-r6v2",
        params={"scenarioId": "canonical-goal-conditioned-quality"},
    ).json()

    response = client.post(
        "/api/v1/optimization/r6v2/search", json=example["searchRequest"]
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["runSpec"]["domainPackId"] == "optimization.domain-pack@2"
    assert payload["recommendationSet"]["searchRequest"]["intent"][
        "primaryObjectiveId"
    ] == "linearFollowingErrorMaxMm"
    assert payload["recommendationSet"]["bestObservedCandidateIds"]


def test_r6v2_http_rejects_underspecified_or_weighted_goal() -> None:
    client = TestClient(create_app(serve_frontend=False))
    example = client.get("/api/v1/examples/optimization-r6v2").json()
    request = example["searchRequest"]
    request["intent"] = {
        "primaryObjectiveId": "cycleTimeSeconds",
        "maximumLinearFollowingErrorMm": 0.46,
        "weights": [1.0, 1.0, 1.0],
    }

    response = client.post("/api/v1/optimization/r6v2/search", json=request)

    assert response.status_code == 422
