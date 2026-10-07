from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.control import GoalToShadowRequest, rehearse_goal_to_shadow
from axiom.optimization import build_r6v2_search_request
from axiom.web import create_app


def _request(candidate_id: str | None = None) -> dict:
    payload = GoalToShadowRequest(
        searchRequest=build_r6v2_search_request("canonical-goal-conditioned-speed"),
        candidateId=candidate_id,
    )
    return payload.model_dump(mode="json", by_alias=True, exclude_none=True)


def test_goal_to_shadow_http_rehearses_the_exact_candidate() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.post("/api/v1/control/goal-to-shadow/rehearse", json=_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "Passed"
    assert (
        payload["selectedCandidateId"]
        in payload["recommendationSet"]["bestObservedCandidateIds"]
    )
    projection = payload["physicalShadowProjection"]
    assert projection["alignment"] == "exact-sample-index-time-and-command"
    assert projection["interpolationApplied"] is False
    assert projection["linearAxisIds"] == ["X", "Y", "Z"]
    assert projection["excludedRotaryAxisIds"] == ["B", "C"]
    assert projection["sampleCount"] == len(projection["shadowTrace"]["samples"])
    assert payload["runtimeAudit"]["finalState"] == "Completed"
    assert payload["deviceWriteAllowed"] is False


def test_goal_to_shadow_http_and_python_share_content_identity() -> None:
    client = TestClient(create_app(serve_frontend=False))
    raw = _request()

    http = client.post("/api/v1/control/goal-to-shadow/rehearse", json=raw)
    direct = rehearse_goal_to_shadow(GoalToShadowRequest.model_validate(raw))

    assert http.status_code == 200
    assert http.json()["contentHash"] == direct.content_hash
    assert (
        http.json()["physicalShadowProjection"]["contentHash"]
        == direct.physical_shadow_projection.content_hash
    )


def test_goal_to_shadow_http_returns_structured_block_for_unknown_candidate() -> None:
    client = TestClient(create_app(serve_frontend=False))

    response = client.post(
        "/api/v1/control/goal-to-shadow/rehearse",
        json=_request("optimization.r6v2.not-validated@1"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "Blocked"
    assert payload["reasonCodes"] == ["ExactCandidateMissing"]
    assert "physicalShadowProjection" not in payload
    assert "runtimeAudit" not in payload


def test_goal_to_shadow_endpoint_is_in_openapi() -> None:
    client = TestClient(create_app(serve_frontend=False))

    schema = client.get("/api/openapi.json").json()

    assert "/api/v1/control/goal-to-shadow/rehearse" in schema["paths"]
