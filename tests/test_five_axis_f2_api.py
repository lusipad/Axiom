from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.five_axis.f2_runtime import FIVE_AXIS_F2_DOMAIN_PACK_ID
from axiom.web import create_app


def _client() -> TestClient:
    return TestClient(create_app(serve_frontend=False))


def test_f2_manifest_scenarios_and_example_are_exposed() -> None:
    client = _client()

    manifest = client.get("/api/v1/five-axis/f2/manifest")
    scenarios = client.get("/api/v1/five-axis/f2/scenarios")
    example = client.get(
        "/api/v1/examples/five-axis-f2",
        params={"scenarioId": "canonical-head-head"},
    )

    assert manifest.status_code == 200
    assert manifest.json()["stage"] == "F2"
    assert scenarios.status_code == 200
    assert len(scenarios.json()) == 4
    assert example.status_code == 200
    assert example.json()["scenario"]["scenarioId"] == "canonical-head-head"
    assert example.json()["artifacts"]["axisPath"]["artifactType"] == "five-axis.m3-candidate-axis-path"


def test_f2_unknown_scenario_returns_not_found() -> None:
    client = _client()

    assert client.get(
        "/api/v1/five-axis/f2/manifest",
        params={"scenarioId": "unknown"},
    ).status_code == 404
    assert client.get(
        "/api/v1/examples/five-axis-f2",
        params={"scenarioId": "unknown"},
    ).status_code == 404


def test_f2_domain_pack_is_runtime_bound_in_catalog() -> None:
    packs = _client().get("/api/v1/catalog").json()["domainPacks"]
    f2 = next(item for item in packs if item["domainPackId"] == FIVE_AXIS_F2_DOMAIN_PACK_ID)

    assert f2["runtimeBound"] is True
    assert f2["artifactType"] == "five-axis.m3-candidate-axis-path"
