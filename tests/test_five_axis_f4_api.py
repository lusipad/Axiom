from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.five_axis.f4_runtime import FIVE_AXIS_F4_DOMAIN_PACK_ID
from axiom.web import create_app


_POSITIVE_SCENARIOS = (
    "canonical-dual-table-solver",
    "canonical-head-table-solver",
    "canonical-dual-head-solver",
)
_NEGATIVE_SCENARIOS = (
    "adapter-input-hash-mismatch",
    "interval-interior-collision",
)
_SEVEN_GATE_CLAIMS = {
    "five-axis.geometry-valid-claim@1",
    "five-axis.task-geometry-collision-free-claim@1",
    "five-axis.kinematically-feasible-claim@1",
    "five-axis.configuration-collision-free-claim@1",
    "five-axis.continuously-feasible-claim@1",
    "five-axis.interval-certified-claim@1",
    "five-axis.model-collision-free-claim@1",
}


def _client() -> TestClient:
    return TestClient(create_app(serve_frontend=False))


def test_f4_catalog_manifest_and_scenarios_are_exposed() -> None:
    client = _client()

    catalog = client.get("/api/v1/catalog")
    manifest = client.get("/api/v1/five-axis/f4/manifest")
    scenarios = client.get("/api/v1/five-axis/f4/scenarios")

    assert catalog.status_code == 200
    f4 = next(item for item in catalog.json()["domainPacks"] if item["domainPackId"] == FIVE_AXIS_F4_DOMAIN_PACK_ID)
    assert f4["runtimeBound"] is True
    assert f4["artifactType"] == "five-axis.m5-discrete-command"
    assert f4["runnerId"] == "five-axis.solver-adapter@1"

    assert manifest.status_code == 200
    manifest_body = manifest.json()
    assert manifest_body["stage"] == "F4"
    assert [item["stage"] for item in manifest_body["artifactDescriptors"]] == [
        "M0",
        "M1",
        "M2",
        "M3",
        "M4",
        "M5",
    ]
    assert manifest_body["artifactDescriptors"][-1] == {
        "stage": "M5",
        "artifactType": "five-axis.m5-discrete-command",
        "schemaId": "five-axis.m5-discrete-command@1",
    }

    assert scenarios.status_code == 200
    assert {item["scenarioId"] for item in scenarios.json()} == {
        *_POSITIVE_SCENARIOS,
        *_NEGATIVE_SCENARIOS,
    }


def test_f4_positive_examples_publish_runnable_specs_with_supported_math_claims() -> None:
    client = _client()

    for scenario_id in _POSITIVE_SCENARIOS:
        example = client.get("/api/v1/examples/five-axis-f4", params={"scenarioId": scenario_id})
        assert example.status_code == 200

        payload = example.json()
        assert payload["scenario"]["scenarioId"] == scenario_id
        assert payload["manifest"]["stage"] == "F4"
        assert payload["runSpec"]["domainPackId"] == FIVE_AXIS_F4_DOMAIN_PACK_ID

        bundle = client.post("/api/v1/runs/evaluate", json=payload["runSpec"])
        assert bundle.status_code == 200

        run_bundle = bundle.json()
        claims = {claim["claimDefinitionId"]: claim["status"] for claim in run_bundle["claims"]}
        assert run_bundle["run"]["executionStatus"] == "Succeeded"
        assert run_bundle["run"]["caseOutcome"] == "Passed"
        assert run_bundle["report"]["caseOutcome"] == "Passed"
        assert {claim_id: claims[claim_id] for claim_id in _SEVEN_GATE_CLAIMS} == {
            claim_id: "Supported" for claim_id in _SEVEN_GATE_CLAIMS
        }
        assert not {
            "five-axis.device-safe-claim@1",
            "five-axis.process-safe-claim@1",
        }.intersection(claims)


def test_f4_counterexample_examples_are_exposed_without_run_specs() -> None:
    client = _client()

    for scenario_id in _NEGATIVE_SCENARIOS:
        example = client.get("/api/v1/examples/five-axis-f4", params={"scenarioId": scenario_id})
        assert example.status_code == 200

        payload = example.json()
        assert payload["scenario"]["scenarioId"] == scenario_id
        assert payload["scenario"]["expectedOutcome"] == "Passed"
        assert "runSpec" not in payload


def test_f4_unknown_scenario_returns_not_found_and_openapi_is_typed() -> None:
    client = _client()

    assert client.get("/api/v1/five-axis/f4/manifest", params={"scenarioId": "unknown"}).status_code == 404
    assert client.get("/api/v1/examples/five-axis-f4", params={"scenarioId": "unknown"}).status_code == 404

    openapi = client.get("/api/openapi.json").json()
    response_schema = openapi["paths"]["/api/v1/examples/five-axis-f4"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/F4ExamplePayload")
