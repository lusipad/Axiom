from __future__ import annotations

import math

from fastapi.testclient import TestClient

from axiom.five_axis.f3_runtime import FIVE_AXIS_F3_DOMAIN_PACK_ID
from axiom.web import create_app


def _client() -> TestClient:
    return TestClient(create_app(serve_frontend=False))


def _javascript_json_roundtrip(value):
    if isinstance(value, float) and value == 0.0:
        return 0.0
    if isinstance(value, list):
        return [_javascript_json_roundtrip(item) for item in value]
    if isinstance(value, dict):
        return {key: _javascript_json_roundtrip(item) for key, item in value.items()}
    return value


def _contains_negative_zero(value) -> bool:
    if isinstance(value, float):
        return value == 0.0 and math.copysign(1.0, value) < 0.0
    if isinstance(value, list):
        return any(_contains_negative_zero(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_negative_zero(item) for item in value.values())
    return False


def test_f3_manifest_scenarios_and_example_are_exposed() -> None:
    client = _client()

    manifest = client.get("/api/v1/five-axis/f3/manifest")
    scenarios = client.get("/api/v1/five-axis/f3/scenarios")
    example = client.get(
        "/api/v1/examples/five-axis-f3",
        params={"scenarioId": "canonical-head-head-jerk"},
    )

    assert manifest.status_code == 200
    assert manifest.json()["stage"] == "F3"
    assert [item["stage"] for item in manifest.json()["artifactDescriptors"]] == [
        "M0",
        "M1",
        "M2",
        "M3",
        "M4",
        "M5",
    ]
    assert scenarios.status_code == 200
    assert {
        "canonical-table-table-jerk",
        "canonical-head-table-jerk",
        "canonical-head-head-jerk",
        "second-order-proven-optimal",
        "dwell-mandatory-stop",
        "zoh-moving-unsupported",
        "polynomial-interior-violation",
    }.issubset({item["scenarioId"] for item in scenarios.json()})
    assert example.status_code == 200
    payload = example.json()
    m5_descriptor = next(item for item in payload["manifest"]["artifactDescriptors"] if item["stage"] == "M5")
    assert payload["scenario"]["scenarioId"] == "canonical-head-head-jerk"
    assert payload["artifacts"]["continuousTrajectory"]["artifactType"] == (
        "five-axis.m4-continuous-trajectory"
    )
    assert payload["artifacts"]["sampledTrajectory"]["artifactType"] == (
        "five-axis.m5-sampled-trajectory"
    )
    assert m5_descriptor == {
        "stage": "M5",
        "artifactType": "five-axis.m5-sampled-trajectory",
        "schemaId": "five-axis.m5-sampled-trajectory@1",
    }
    assert payload["runSpec"]["domainPackId"] == FIVE_AXIS_F3_DOMAIN_PACK_ID
    assert _contains_negative_zero(payload["runSpec"])

    # Regression: ISSUE-001 — JSON.stringify normalizes signed zero and invalidated M5 identity.
    # Found by /qa on 2026-08-12.
    # Report: .gstack/qa-reports/qa-report-localhost-2026-08-12.md
    bundle = client.post(
        "/api/v1/runs/evaluate",
        json=_javascript_json_roundtrip(payload["runSpec"]),
    ).json()
    assert bundle["run"]["executionStatus"] == "Succeeded"
    assert bundle["run"]["caseOutcome"] == "Passed"


def test_f3_discrete_example_manifest_and_evaluation_match_runtime_contract() -> None:
    client = _client()

    example = client.get(
        "/api/v1/examples/five-axis-f3",
        params={"scenarioId": "second-order-proven-optimal"},
    )

    assert example.status_code == 200
    payload = example.json()
    descriptor = next(item for item in payload["manifest"]["artifactDescriptors"] if item["stage"] == "M5")
    assert payload["scenario"]["scenarioId"] == "second-order-proven-optimal"
    assert "sampledTrajectory" not in payload["artifacts"]
    assert payload["artifacts"]["discreteCommand"]["artifactType"] == "five-axis.m5-discrete-command"
    assert descriptor == {
        "stage": "M5",
        "artifactType": "five-axis.m5-discrete-command",
        "schemaId": "five-axis.m5-discrete-command@1",
    }

    bundle = client.post(
        "/api/v1/runs/evaluate",
        json=_javascript_json_roundtrip(payload["runSpec"]),
    )

    assert bundle.status_code == 200
    run_bundle = bundle.json()
    claims = {claim["claimDefinitionId"]: claim["status"] for claim in run_bundle["claims"]}
    assert run_bundle["run"]["executionStatus"] == "Succeeded"
    assert run_bundle["run"]["caseOutcome"] == "Unsupported"
    assert run_bundle["report"]["caseOutcome"] == "Unsupported"
    assert claims["five-axis.continuously-feasible-claim@1"] == "Supported"
    assert claims["five-axis.interval-certified-claim@1"] == "Inconclusive"
    assert not {
        "five-axis.model-collision-free-claim@1",
        "five-axis.device-safe-claim@1",
        "five-axis.process-safe-claim@1",
    }.intersection(claims)


def test_f3_unknown_scenario_returns_not_found() -> None:
    client = _client()

    assert client.get(
        "/api/v1/five-axis/f3/manifest",
        params={"scenarioId": "unknown"},
    ).status_code == 404
    assert client.get(
        "/api/v1/examples/five-axis-f3",
        params={"scenarioId": "unknown"},
    ).status_code == 404


def test_f3_domain_pack_is_runtime_bound_in_catalog() -> None:
    packs = _client().get("/api/v1/catalog").json()["domainPacks"]
    f3 = next(item for item in packs if item["domainPackId"] == FIVE_AXIS_F3_DOMAIN_PACK_ID)

    assert f3["runtimeBound"] is True
    assert f3["artifactType"] == "five-axis.m5-sampled-trajectory"
    assert {
        "five-axis.m4-continuous-trajectory",
        "five-axis.m5-sampled-trajectory",
        "five-axis.m5-discrete-command",
    }.issubset(
        {descriptor["artifactType"] for descriptor in f3["artifactTypeDescriptors"]}
    )
