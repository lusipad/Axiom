from __future__ import annotations

import asyncio

import httpx

from axiom.web import create_app


EXPECTED_CLAIM_STATUS_BY_SCENARIO = {
    "nominal-certified": {
        "five-axis.geometry-valid-claim@1": "Supported",
        "five-axis.task-geometry-collision-free-claim@1": "Supported",
    },
    "geometry-tolerance-violation": {
        "five-axis.geometry-valid-claim@1": "Refuted",
        "five-axis.task-geometry-collision-free-claim@1": "Supported",
    },
    "fixture-collision": {
        "five-axis.geometry-valid-claim@1": "Supported",
        "five-axis.task-geometry-collision-free-claim@1": "Refuted",
    },
}


async def _exercise_f1_routes() -> None:
    transport = httpx.ASGITransport(app=create_app(serve_frontend=False))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        catalog = await client.get("/api/v1/catalog")
        assert catalog.status_code == 200
        f1_pack = next(
            item
            for item in catalog.json()["domainPacks"]
            if item["domainPackId"] == "five-axis.domain-pack@2"
        )
        assert f1_pack["runtimeBound"] is True

        manifest = await client.get("/api/v1/five-axis/f1/manifest")
        assert manifest.status_code == 200
        assert manifest.json()["stage"] == "F1"
        assert {item["stage"] for item in manifest.json()["artifactDescriptors"]} == {
            "M0",
            "M1",
            "M2",
        }

        scenarios = await client.get("/api/v1/five-axis/f1/scenarios")
        assert scenarios.status_code == 200
        scenario_ids = {item["scenarioId"] for item in scenarios.json()}
        assert scenario_ids == set(EXPECTED_CLAIM_STATUS_BY_SCENARIO)

        for scenario_id, expected_claims in EXPECTED_CLAIM_STATUS_BY_SCENARIO.items():
            scenario_manifest = await client.get(
                "/api/v1/five-axis/f1/manifest",
                params={"scenarioId": scenario_id},
            )
            assert scenario_manifest.status_code == 200

            example = await client.get(
                "/api/v1/examples/five-axis-f1",
                params={"scenarioId": scenario_id},
            )
            assert example.status_code == 200
            payload = example.json()
            assert scenario_manifest.json() == payload["manifest"]
            assert payload["scenario"]["scenarioId"] == scenario_id
            assert payload["scenario"]["expectedClaimStatusById"] == expected_claims
            assert payload["source"]["normalizedProgram"]["artifactType"] == "five-axis.normalized-program"
            assert payload["source"]["referencePath"]["artifactType"] == "five-axis.m1-reference-path"
            assert payload["artifacts"]["candidateGeometry"]["artifactType"] == "five-axis.m2-candidate-task-geometry"

            bundle = await client.post("/api/v1/runs/evaluate", json=payload["runSpec"])
            assert bundle.status_code == 200
            body = bundle.json()
            assert body["run"]["domainPackId"] == "five-axis.domain-pack@2"
            claims = {
                item["claimDefinitionId"]: item["status"]
                for item in body["claims"]
                if item["claimDefinitionId"] in expected_claims
            }
            assert claims == expected_claims

        missing = await client.get(
            "/api/v1/examples/five-axis-f1",
            params={"scenarioId": "missing"},
        )
        assert missing.status_code == 404
        assert "unknown F1 scenario" in missing.json()["detail"]

        missing_manifest = await client.get(
            "/api/v1/five-axis/f1/manifest",
            params={"scenarioId": "missing"},
        )
        assert missing_manifest.status_code == 404

        openapi = (await client.get("/api/openapi.json")).json()
        response_schema = openapi["paths"]["/api/v1/examples/five-axis-f1"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]
        assert response_schema["$ref"].endswith("/F1ExamplePayload")


def test_f1_public_routes_execute_versioned_real_scenarios() -> None:
    asyncio.run(_exercise_f1_routes())
