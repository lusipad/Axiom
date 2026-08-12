from __future__ import annotations

from fastapi.testclient import TestClient

from axiom.web import create_app


def _client() -> TestClient:
    return TestClient(create_app(serve_frontend=False))


def test_machine_r3_manifest_example_and_run_bundle_use_real_schema() -> None:
    client = _client()

    manifest = client.get("/api/v1/machine/r3/manifest")
    scenarios = client.get("/api/v1/machine/r3/scenarios")
    example = client.get("/api/v1/examples/machine-r3", params={"scenarioId": "read-only-paired-pass"})

    assert manifest.status_code == 200
    manifest_body = manifest.json()
    assert manifest_body["manifestId"] == "machine.r3-manifest@1"
    assert manifest_body["schemaVersion"] == 1
    assert manifest_body["readOnly"] is True
    assert manifest_body["safetyBanner"] == "READ ONLY / NOT DEVICE SAFE"
    assert manifest_body["forbiddenClaims"] == ["DeviceSafe", "ProcessSafe", "safe-to-run"]
    assert manifest_body["suiteId"] == "machine-r3-fixtures@1"
    assert manifest_body["cases"][0]["id"] == "read-only-paired-pass"

    assert scenarios.status_code == 200
    assert {item["scenarioId"] for item in scenarios.json()} == {
        "read-only-paired-pass",
        "read-only-unpaired-pass",
        "missing-clock-alignment",
        "out-of-order-gap",
        "forbidden-write-operation",
    }

    assert example.status_code == 200
    payload = example.json()
    assert payload["artifact"]["captureReceipt"]["receiptId"] == "receipt:read-only-paired-pass"
    assert payload["artifact"]["captureReceipt"]["sourceId"] == "axiom.windows-file-telemetry-source@1"
    assert payload["artifact"]["captureReceipt"]["operation"] == "file-import"
    assert payload["artifact"]["captureReceipt"]["transport"] == "windows-file-json"
    assert payload["artifact"]["captureReceipt"]["capturedAt"] == "2026-08-11T09:30:00Z"
    assert len(payload["artifact"]["captureReceipt"]["traceContentHash"]) == 64
    assert payload["artifact"]["deviceIdentity"] == {
        "deviceId": "sim-840d",
        "controllerFamily": "siemens-840d",
        "machineModel": "vmc-5x-sim",
    }
    assert payload["artifact"]["frames"][0]["sequenceId"] == 100
    assert payload["artifact"]["frames"][0]["deviceTimestamp"] == "2026-08-11T09:29:58.000Z"
    assert payload["artifact"]["frames"][0]["samples"][0]["channelId"] == "pos.work"
    assert payload["artifact"]["vendorMetadata"] == {
        "programName": "DEMO_5X_R3",
        "channel": "CHANNEL_1",
    }
    assert payload["deviceProfile"]["profileId"] == "device-profile.sim-840d@1"
    assert payload["deviceProfile"]["manufacturer"] == "Axiom Simulation"
    assert payload["deviceProfile"]["machineModel"] == "vmc-5x-sim"
    assert payload["deviceProfile"]["controllerFamily"] == "siemens-840d"
    assert payload["deviceProfile"]["firmwareVersion"] == "sim-fw-1.0"
    assert payload["deviceProfile"]["exportVersion"] == "windows-file-json@1"
    assert payload["deviceProfile"]["allowedReadOnlyOperations"] == ["file-import"]
    assert payload["clockMapping"]["mappingId"] == "clock-map.sim-840d@1"
    assert payload["clockMapping"]["mappingMethod"] == "fixed-offset"
    assert payload["clockMapping"]["offsetMilliseconds"] == 10.0
    assert payload["coordinateAlignment"]["alignmentId"] == "alignment.sim-840d@1"
    assert payload["coordinateAlignment"]["sourceKind"] == "synthetic-reference"
    assert payload["coordinateAlignment"]["effectiveAt"] == "2026-08-11T00:00:00Z"
    assert payload["lineage"]["pairingStatus"] == "paired"
    assert payload["lineage"]["baselineKind"] == "reference"
    assert len(payload["lineage"]["baselineRunBundleHash"]) == 64
    assert len(payload["lineage"]["sourceCommandContentHash"]) == 64
    assert len(payload["lineage"]["upstreamClaims"]) == 7
    assert all(claim["status"] == "Supported" for claim in payload["lineage"]["upstreamClaims"])

    bundle = client.post("/api/v1/runs/evaluate", json=payload["runSpec"])
    assert bundle.status_code == 200
    run_bundle = bundle.json()
    assert run_bundle["run"]["executionStatus"] == "Succeeded"
    assert run_bundle["run"]["caseOutcome"] == "Passed"
    assert set(run_bundle["report"]["provenance"]["contextHashes"]) == {
        "deviceProfile",
        "clockMapping",
        "coordinateAlignment",
        "lineage",
    }
    assert all(claim["evidence"]["level"] == "Observed" for claim in run_bundle["claims"])
    assert not any(
        claim["claimDefinitionId"] in {"DeviceSafe", "ProcessSafe", "safe-to-run"}
        for claim in run_bundle["claims"]
    )


def test_machine_r3_unknown_scenario_returns_not_found() -> None:
    client = _client()

    assert client.get("/api/v1/examples/machine-r3", params={"scenarioId": "missing"}).status_code == 404
