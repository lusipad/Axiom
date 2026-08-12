from __future__ import annotations

import asyncio

import httpx
import pytest

from axiom.web import create_app


async def _exercise_experiment_api() -> None:
    app = create_app(serve_frontend=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        catalog = await client.get("/api/v1/catalog")
        assert catalog.status_code == 200
        subject_ids = {item["subjectId"] for item in catalog.json()["subjects"]}
        assert "ordered-point.offset-baseline" in subject_ids
        assert "ordered-point.offset-compensated" in subject_ids
        ordered_pack = next(
            item
            for item in catalog.json()["domainPacks"]
            if item["domainPackId"] == "ordered-point.domain-pack@1"
        )
        assert ordered_pack["runtimeBound"] is True
        five_axis_pack = next(
            item
            for item in catalog.json()["domainPacks"]
            if item["domainPackId"] == "five-axis.domain-pack@1"
        )
        assert five_axis_pack["runtimeBound"] is True
        five_axis_f1_pack = next(
            item
            for item in catalog.json()["domainPacks"]
            if item["domainPackId"] == "five-axis.domain-pack@2"
        )
        assert five_axis_f1_pack["runtimeBound"] is True
        intelligence_r5b_pack = next(
            item
            for item in catalog.json()["domainPacks"]
            if item["domainPackId"] == "intelligence.domain-pack@2"
        )
        assert intelligence_r5b_pack["runtimeBound"] is True
        assert any(
            item["adapterId"] == "five-axis.sampled-cartesian-to-ordered-point@1"
            and item["sourceArtifactType"] == "five-axis.sampled-cartesian-position-view"
            and item["targetArtifactType"] == "ordered-point-sequence"
            for item in catalog.json()["artifactAdapters"]
        )

        run_response = await client.post(
            "/api/v1/runs/evaluate",
            json={
                "subjectId": "imported-artifact@1",
                "domainPackId": "ordered-point.domain-pack@1",
                "request": {
                    "artifact": {
                        "artifactType": "ordered-point-sequence",
                        "schemaVersion": 1,
                        "points": [[0, 0], [3, 4]],
                    },
                    "case": {
                        "caseId": "web-domain-run@1",
                        "requiredMetrics": ["path.length.open"],
                    },
                },
            },
        )
        assert run_response.status_code == 200
        assert run_response.json()["report"]["caseOutcome"] == "Passed"
        assert run_response.json()["run"]["domainPackId"] == "ordered-point.domain-pack@1"

        five_axis_manifest = await client.get("/api/v1/five-axis/f0/manifest")
        assert five_axis_manifest.status_code == 200
        assert five_axis_manifest.json()["manifestId"] == "five-axis.math-stage-manifest@1"

        five_axis_example = await client.get("/api/v1/examples/five-axis-f0")
        assert five_axis_example.status_code == 200
        assert five_axis_example.json()["domainPackId"] == "five-axis.domain-pack@1"

        five_axis_run = await client.post("/api/v1/runs/evaluate", json=five_axis_example.json())
        assert five_axis_run.status_code == 200
        assert five_axis_run.json()["run"]["domainPackId"] == "five-axis.domain-pack@1"
        assert five_axis_run.json()["report"]["metricResults"][0]["metricId"] == "five-axis.contract.readiness@1"

        example = await client.get("/api/v1/examples/contour-ab")
        assert example.status_code == 200

        response = await client.post("/api/v1/experiments/run", json=example.json())
        assert response.status_code == 200
        body = response.json()
        assert body["executionStatus"] == "Succeeded"
        assert body["comparison"]["compatibility"]["compatible"] is True

        replay = await client.post("/api/v1/experiments/run", json=example.json())
        assert replay.json() == body


async def _submit_malformed_experiment() -> httpx.Response:
    app = create_app(serve_frontend=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/v1/experiments/run", json={"experimentId": "broken"})


async def _submit_malformed_run() -> httpx.Response:
    app = create_app(serve_frontend=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/api/v1/runs/evaluate", json={"domainPackId": "broken"})


async def _submit_unknown_subject() -> httpx.Response:
    app = create_app(serve_frontend=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        example = (await client.get("/api/v1/examples/contour-ab")).json()
        example["arms"][1]["subjectId"] = "vendor.missing-subject"
        return await client.post("/api/v1/experiments/run", json=example)


async def _get_frontend(app) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/")


def test_web_api_exposes_health_catalog_example_and_true_experiment_execution():
    asyncio.run(_exercise_experiment_api())


def test_web_api_rejects_a_malformed_experiment_with_structured_validation():
    response = asyncio.run(_submit_malformed_experiment())

    assert response.status_code == 422
    assert response.json()["detail"]


def test_web_api_rejects_a_malformed_run_at_the_typed_boundary():
    response = asyncio.run(_submit_malformed_run())

    assert response.status_code == 422
    assert response.json()["detail"]


def test_web_api_returns_business_failure_as_a_structured_report_without_fake_run_data():
    response = asyncio.run(_submit_unknown_subject())

    assert response.status_code == 200
    body = response.json()
    assert body["executionStatus"] == "ExecutionFailed"
    assert body["caseOutcome"] == "Inconclusive"
    assert body.get("comparison") is None
    assert "runBundle" not in body["armResults"][1]
    assert body["armResults"][1]["failure"]["code"] == "UnknownSubject"


def test_web_app_serves_the_built_workbench_and_fails_clearly_without_assets(tmp_path):
    response = asyncio.run(_get_frontend(create_app()))

    assert response.status_code == 200
    assert '<div id="root"></div>' in response.text

    with pytest.raises(RuntimeError, match="web assets are missing"):
        create_app(frontend_dir=tmp_path)
