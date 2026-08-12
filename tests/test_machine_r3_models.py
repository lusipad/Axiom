from __future__ import annotations

import pytest
from pydantic import ValidationError

from axiom.machine.models import (
    CoordinateAlignment,
    DeviceProfile,
    MachineRunLineage,
    MachineTelemetryTrace,
    TelemetrySample,
)


def _trace_payload() -> dict:
    return {
        "artifactType": "machine.telemetry-trace",
        "schemaVersion": 1,
        "traceId": "trace:read-only-paired-pass",
        "sourceKind": "synthetic-replay",
        "captureReceipt": {
            "receiptId": "receipt:read-only-paired-pass",
            "sourceId": "axiom.windows-file-telemetry-source@1",
            "operation": "file-import",
            "transport": "windows-file-json",
            "capturedAt": "2026-08-11T09:30:00Z",
            "traceContentHash": "d6e4fc5d8f79d0cbdf39d415f7427c92bf07e19326f705ed839fceb6ec162850",
        },
        "deviceIdentity": {
            "deviceId": "sim-840d",
            "controllerFamily": "siemens-840d",
            "machineModel": "vmc-5x-sim",
        },
        "frames": [
            {
                "sequenceId": 100,
                "deviceTimestamp": "2026-08-11T09:29:58.000Z",
                "samples": [
                    {"channelId": "pos.work", "value": [0.0, 0.0, 5.0], "unit": "mm"},
                    {"channelId": "feed.actual", "value": 1200.0, "unit": "mm/min"},
                ],
            },
            {
                "sequenceId": 101,
                "deviceTimestamp": "2026-08-11T09:29:58.020Z",
                "samples": [
                    {"channelId": "pos.work", "value": [1.5, 0.0, 4.7], "unit": "mm"},
                    {"channelId": "feed.actual", "value": 1200.0, "unit": "mm/min"},
                ],
            },
        ],
        "vendorMetadata": {"programName": "DEMO_5X_R3", "channel": "CHANNEL_1"},
    }


def _paired_lineage_payload() -> dict:
    return {
        "machineRunId": "machine-run:paired-pass",
        "pairingStatus": "paired",
        "baselineKind": "reference",
        "baselineRunBundleHash": "beec29557d6bf8c22363616c65a73f4394e484c9b516478898e9c4039bc44d79",
        "sourceCommandContentHash": "085ab2047f6089fb3fa681c7a83ee3aa63c9d379b55529bbbabbd0411874d218",
        "upstreamClaims": [
            {"claimDefinitionId": "five-axis.geometry-valid-claim@1", "status": "Supported"},
            {"claimDefinitionId": "five-axis.task-geometry-collision-free-claim@1", "status": "Supported"},
            {"claimDefinitionId": "five-axis.kinematically-feasible-claim@1", "status": "Supported"},
            {"claimDefinitionId": "five-axis.configuration-collision-free-claim@1", "status": "Supported"},
            {"claimDefinitionId": "five-axis.continuously-feasible-claim@1", "status": "Supported"},
            {"claimDefinitionId": "five-axis.interval-certified-claim@1", "status": "Supported"},
            {"claimDefinitionId": "five-axis.model-collision-free-claim@1", "status": "Supported"},
        ],
    }


def test_machine_trace_rejects_write_operations() -> None:
    payload = _trace_payload()
    payload["captureReceipt"]["operation"] = "parameter-write"
    with pytest.raises(ValidationError, match="operation"):
        MachineTelemetryTrace.model_validate(payload)


def test_machine_sample_rejects_boolean_number_coercion() -> None:
    with pytest.raises(ValidationError, match="JSON number"):
        TelemetrySample.model_validate({"channelId": "feed.actual", "value": True, "unit": "mm/min"})


def test_machine_trace_preserves_frame_order_and_vendor_metadata() -> None:
    payload = _trace_payload()
    payload["frames"][0]["sequenceId"] = 101
    payload["frames"][1]["sequenceId"] = 100
    trace = MachineTelemetryTrace.model_validate(payload)
    assert [frame.sequence_id for frame in trace.frames] == [101, 100]
    assert trace.vendor_metadata == {"programName": "DEMO_5X_R3", "channel": "CHANNEL_1"}


def test_paired_lineage_requires_full_f4_claim_set() -> None:
    payload = _paired_lineage_payload()
    payload["upstreamClaims"] = payload["upstreamClaims"][:-1]
    with pytest.raises(ValidationError, match="seven frozen F4 claims"):
        MachineRunLineage.model_validate(payload)


def test_coordinate_alignment_requires_declared_channel_ids() -> None:
    DeviceProfile.model_validate(
        {
            "profileId": "device-profile.sim-840d@1",
            "deviceId": "sim-840d",
            "manufacturer": "Axiom Simulation",
            "machineModel": "vmc-5x-sim",
            "controllerFamily": "siemens-840d",
            "exportVersion": "windows-file-json@1",
            "allowedReadOnlyOperations": ["file-import"],
            "channels": [{"channelId": "pos.work", "kind": "position-vector", "unit": "mm"}],
        }
    )
    with pytest.raises(ValidationError, match="channelIds"):
        CoordinateAlignment.model_validate(
            {
                "alignmentId": "alignment.sim-840d@1",
                "deviceId": "sim-840d",
                "machineCoordinateFrame": "machine",
                "workCoordinateFrame": "workpiece",
                "sourceKind": "synthetic-reference",
                "effectiveAt": "2026-08-11T00:00:00Z",
                "calibrationStatus": "calibrated",
                "channelIds": [],
            }
        )


def test_device_profile_rejects_duplicate_read_only_operations() -> None:
    with pytest.raises(ValidationError, match="allows only file-import exactly once"):
        DeviceProfile.model_validate(
            {
                "profileId": "device-profile.sim-840d@1",
                "deviceId": "sim-840d",
                "manufacturer": "Axiom Simulation",
                "machineModel": "vmc-5x-sim",
                "controllerFamily": "siemens-840d",
                "exportVersion": "windows-file-json@1",
                "allowedReadOnlyOperations": ["file-import", "file-import"],
                "channels": [{"channelId": "pos.work", "kind": "position-vector", "unit": "mm"}],
            }
        )
