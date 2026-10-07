from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def test_r7a2_http_manifest_scenarios_and_example_share_the_handoff() -> None:
    client = TestClient(create_app(serve_frontend=False))

    manifest = client.get("/api/v1/control/r7a-v2/manifest")
    scenarios = client.get("/api/v1/control/r7a-v2/scenarios")
    example = client.get("/api/v1/examples/control-r7a-v2")

    assert manifest.status_code == 200
    assert scenarios.status_code == 200
    assert example.status_code == 200
    assert manifest.json()["sourceRecommendationSchemaId"] == (
        "axiom.optimization.recommendation-set@2"
    )
    assert manifest.json()["permissionCeiling"] == "Shadow"
    assert scenarios.json()[0]["scenarioId"] == "r6v2-shadow-nominal"
    payload = example.json()
    assert payload["recommendationSet"]["schemaId"] == (
        "axiom.optimization.recommendation-set@2"
    )
    assert payload["recommendationProjection"]["selectionClass"] == "BestObserved"
    assert payload["runtimeAudit"]["finalState"] == "Completed"


def test_r7a2_http_replay_exposes_blocked_and_stop_paths() -> None:
    client = TestClient(create_app(serve_frontend=False))

    blocked = client.post(
        "/api/v1/control/r7a-v2/replay",
        json={"scenarioId": "r6v2-exact-ineligible-blocked"},
    )
    stopped = client.post(
        "/api/v1/control/r7a-v2/replay",
        json={"scenarioId": "r6v2-shadow-limit-breach"},
    )

    assert blocked.status_code == 200
    assert blocked.json()["runtimeAudit"]["finalState"] == "Blocked"
    assert (
        "RecommendationGoalConstraintFailed"
        in blocked.json()["runtimeAudit"]["admissionDecision"]["reasonCodes"]
    )
    assert stopped.status_code == 200
    assert stopped.json()["runtimeAudit"]["finalState"] == "RollbackVerified"
    assert stopped.json()["runSpec"]["domainPackId"] == "control.domain-pack@1"


def test_r7a2_http_rejects_unknown_scenario() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.get(
        "/api/v1/examples/control-r7a-v2", params={"scenarioId": "unknown"}
    )

    assert response.status_code == 404
