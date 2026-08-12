from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta
from importlib import resources
from typing import Any

import pytest

from axiom.intelligence import load_r5_scenario
from axiom.intelligence.r5b_models import (
    R5BIntelligenceEvaluationRequest,
    RealHoldoutCaseEvidence,
    RealHoldoutGovernance,
    RealHoldoutSelectionReceipt,
    RealPairedHoldoutSet,
)
from axiom.machine.models import MachineObservationRequest
from axiom.machine.runtime import machine_trace_content_hash
from axiom.physical.models import PhysicalResponseTrace


def _load_response_payload() -> dict[str, Any]:
    text = (
        resources.files("axiom.physical.fixtures.captures")
        .joinpath("in-domain-synthetic-sil.response.json")
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def _canonical_json_hash(
    payload: dict[str, Any], *, exclude_keys: set[str] | None = None
) -> str:
    value = deepcopy(payload)
    for key in exclude_keys or set():
        value.pop(key, None)
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    import hashlib

    return hashlib.sha256(encoded).hexdigest()


def _case_content_hash(payload: dict[str, Any]) -> str:
    model = RealHoldoutCaseEvidence.model_construct(
        case_id=payload["caseId"],
        role=payload["role"],
        topology=payload["topology"],
        trajectory_family=payload["trajectoryFamily"],
        task_id=payload["taskId"],
        condition_id=payload["conditionId"],
        batch_id=payload["batchId"],
        pair_id=payload["pairId"],
        source_kind=payload["sourceKind"],
        observation=MachineObservationRequest.model_validate(payload["observation"]),
        response_trace=PhysicalResponseTrace.model_validate(payload["responseTrace"]),
        scalar_channel_id=payload["scalarChannelId"],
        scalar_unit=payload["scalarUnit"],
        capture_start_time=payload["captureStartTime"],
        capture_end_time=payload["captureEndTime"],
        device_time_anchor=payload["deviceTimeAnchor"],
        maximum_time_error_seconds=payload["maximumTimeErrorSeconds"],
        content_hash="",
    )
    from axiom.intelligence.models import canonical_hash

    return canonical_hash(model, exclude={"content_hash"})


def _governance_content_hash(payload: dict[str, Any]) -> str:
    model = RealHoldoutGovernance.model_construct(
        governance_id=payload["governanceId"],
        license_id=payload["licenseId"],
        allowed_uses=tuple(payload["allowedUses"]),
        retention_policy_id=payload["retentionPolicyId"],
        owner_id=payload["ownerId"],
        authorization_id=payload["authorizationId"],
        authenticity_basis=payload["authenticityBasis"],
        attested_at=payload["attestedAt"],
        sensitivity=payload["sensitivity"],
        redistribution_allowed=payload["redistributionAllowed"],
        content_hash="",
    )
    from axiom.intelligence.models import canonical_hash

    return canonical_hash(model, exclude={"content_hash"})


def _selection_content_hash(payload: dict[str, Any]) -> str:
    model = RealHoldoutSelectionReceipt.model_construct(
        selection_id=payload["selectionId"],
        model_bundle_hash=payload["modelBundleHash"],
        training_dataset_hash=payload["trainingDatasetHash"],
        selected_before_evaluation=payload["selectedBeforeEvaluation"],
        leakage_dimensions=tuple(payload["leakageDimensions"]),
        case_ids=tuple(payload["caseIds"]),
        content_hash="",
    )
    from axiom.intelligence.models import canonical_hash

    return canonical_hash(model, exclude={"content_hash"})


def _set_content_hash(payload: dict[str, Any]) -> str:
    model = RealPairedHoldoutSet.model_construct(
        artifact_type=payload["artifactType"],
        schema_id=payload["schemaId"],
        schema_version=payload["schemaVersion"],
        holdout_set_id=payload["holdoutSetId"],
        model_bundle_hash=payload["modelBundleHash"],
        training_dataset_hash=payload["trainingDatasetHash"],
        governance=RealHoldoutGovernance.model_validate(payload["governance"]),
        selection=RealHoldoutSelectionReceipt.model_validate(payload["selection"]),
        cases=tuple(
            RealHoldoutCaseEvidence.model_validate(item) for item in payload["cases"]
        ),
        content_hash="",
    )
    from axiom.intelligence.models import canonical_hash

    return canonical_hash(model, exclude={"content_hash"})


def _build_case(
    case_index: int,
    *,
    role: str,
    source_kind: str,
    observed_x: tuple[float, float],
    ood: bool = False,
) -> dict[str, Any]:
    response = _load_response_payload()
    response["responseTraceId"] = f"five-axis.r5b.response.{case_index}@1"
    response["sourceCommandId"] = f"five-axis.m5.command.r5b.{case_index}"
    response["samples"] = response["samples"][:2]
    for sample_index, sample in enumerate(response["samples"]):
        sample["sampleIndex"] = sample_index
        sample["t"] = 0.02 * sample_index
        if ood:
            sample["command"][0] = sample["simulated"][0] + 1_000_000.0
    response["contentHash"] = _canonical_json_hash(
        response, exclude_keys={"contentHash"}
    )

    anchor = datetime.fromisoformat(f"2026-08-12T10:{case_index:02d}:00+00:00")
    machine_trace = {
        "artifactType": "machine.telemetry-trace",
        "schemaVersion": 1,
        "traceId": f"trace:r5b:{case_index}",
        "sourceKind": source_kind,
        "captureReceipt": {
            "receiptId": f"receipt:r5b:{case_index}",
            "sourceId": "axiom.windows-file-telemetry-source@1",
            "operation": "file-import",
            "transport": "windows-file-json",
            "capturedAt": anchor.isoformat(),
            "traceContentHash": "0" * 64,
        },
        "deviceIdentity": {
            "deviceId": f"sim-840d-{case_index}",
            "controllerFamily": "siemens-840d",
            "machineModel": "vmc-5x-sim",
        },
        "frames": [
            {
                "sequenceId": 100,
                "deviceTimestamp": anchor.isoformat(),
                "samples": [
                    {
                        "channelId": "pos.work",
                        "value": [float(observed_x[0]), 0.0, 5.0],
                        "unit": "mm",
                    },
                    {"channelId": "feed.actual", "value": 1200.0, "unit": "mm/min"},
                    {
                        "channelId": "axis.x.actual",
                        "value": float(observed_x[0]),
                        "unit": "mm",
                    },
                ],
            },
            {
                "sequenceId": 101,
                "deviceTimestamp": (anchor + timedelta(seconds=0.02)).isoformat(),
                "samples": [
                    {
                        "channelId": "pos.work",
                        "value": [float(observed_x[1]), 0.0, 4.7],
                        "unit": "mm",
                    },
                    {"channelId": "feed.actual", "value": 1200.0, "unit": "mm/min"},
                    {
                        "channelId": "axis.x.actual",
                        "value": float(observed_x[1]),
                        "unit": "mm",
                    },
                ],
            },
        ],
        "vendorMetadata": {"programName": "R5B_TEST", "channel": "CHANNEL_1"},
    }
    from axiom.machine.models import MachineTelemetryTrace

    trace_model = MachineTelemetryTrace.model_validate(machine_trace)
    machine_trace["captureReceipt"]["traceContentHash"] = machine_trace_content_hash(
        trace_model
    )

    return {
        "caseId": f"holdout-case-{case_index}",
        "role": role,
        "topology": "dual-table" if role == "in-domain" else "dual-head",
        "trajectoryFamily": f"holdout-family-{case_index}",
        "taskId": f"holdout-task-{case_index}",
        "conditionId": f"holdout-condition-{case_index}",
        "batchId": f"holdout-batch-{case_index}",
        "pairId": f"holdout-pair-{case_index}",
        "sourceKind": source_kind,
        "observation": {
            "artifact": machine_trace,
            "deviceProfile": {
                "profileId": f"device-profile.r5b-{case_index}@1",
                "deviceId": f"sim-840d-{case_index}",
                "manufacturer": "Axiom Simulation",
                "machineModel": "vmc-5x-sim",
                "controllerFamily": "siemens-840d",
                "firmwareVersion": "sim-fw-1.0",
                "exportVersion": "windows-file-json@1",
                "allowedReadOnlyOperations": ["file-import"],
                "calibrationId": f"calibration.r5b-{case_index}@1",
                "channels": [
                    {
                        "channelId": "pos.work",
                        "kind": "position-vector",
                        "unit": "mm",
                        "coordinateFrame": "workpiece",
                    },
                    {"channelId": "feed.actual", "kind": "scalar", "unit": "mm/min"},
                    {"channelId": "axis.x.actual", "kind": "scalar", "unit": "mm"},
                ],
            },
            "clockMapping": {
                "mappingId": f"clock-map.r5b-{case_index}@1",
                "deviceId": f"sim-840d-{case_index}",
                "mappingMethod": "fixed-offset",
                "deviceReferenceTimestamp": anchor.isoformat(),
                "hostReferenceTimestamp": anchor.isoformat(),
                "offsetMilliseconds": 0.0,
                "driftBoundMilliseconds": 0.0,
            },
            "coordinateAlignment": {
                "alignmentId": f"alignment.r5b-{case_index}@1",
                "deviceId": f"sim-840d-{case_index}",
                "machineCoordinateFrame": "machine",
                "workCoordinateFrame": "workpiece",
                "sourceKind": "calibration-record",
                "effectiveAt": anchor.isoformat(),
                "calibrationStatus": "calibrated",
                "calibrationId": f"calibration.r5b-{case_index}@1",
                "channelIds": ["pos.work", "axis.x.actual"],
            },
            "lineage": {
                "machineRunId": f"machine-run:r5b:{case_index}",
                "pairingStatus": "paired",
                "baselineKind": "reference",
                "baselineRunBundleHash": "beec29557d6bf8c22363616c65a73f4394e484c9b516478898e9c4039bc44d79",
                "sourceCommandContentHash": response["sourceCommandContentId"],
                "upstreamClaims": [
                    {
                        "claimDefinitionId": "five-axis.geometry-valid-claim@1",
                        "status": "Supported",
                    },
                    {
                        "claimDefinitionId": "five-axis.task-geometry-collision-free-claim@1",
                        "status": "Supported",
                    },
                    {
                        "claimDefinitionId": "five-axis.kinematically-feasible-claim@1",
                        "status": "Supported",
                    },
                    {
                        "claimDefinitionId": "five-axis.configuration-collision-free-claim@1",
                        "status": "Supported",
                    },
                    {
                        "claimDefinitionId": "five-axis.continuously-feasible-claim@1",
                        "status": "Supported",
                    },
                    {
                        "claimDefinitionId": "five-axis.interval-certified-claim@1",
                        "status": "Supported",
                    },
                    {
                        "claimDefinitionId": "five-axis.model-collision-free-claim@1",
                        "status": "Supported",
                    },
                ],
            },
            "case": {
                "caseId": f"machine-r3-r5b-{case_index}@1",
                "requiredMetrics": [
                    "machine-observation.raw-integrity@1",
                    "machine-observation.read-only-capture@1",
                    "machine-observation.lineage-complete@1",
                    "machine-observation.clock-aligned@1",
                    "machine-observation.coordinate-context@1",
                ],
            },
        },
        "responseTrace": response,
        "scalarChannelId": "axis.x.actual",
        "scalarUnit": "mm",
        "captureStartTime": anchor.isoformat(),
        "captureEndTime": (anchor + timedelta(seconds=0.02)).isoformat(),
        "deviceTimeAnchor": anchor.isoformat(),
        "maximumTimeErrorSeconds": 0.0,
        "contentHash": "",
    }


def _build_holdout_set() -> dict[str, Any]:
    scenario = load_r5_scenario()
    cases = [
        _build_case(
            1,
            role="in-domain",
            source_kind="controller-export",
            observed_x=(21.66763547681415, 21.66763547681415),
        ),
        _build_case(
            2,
            role="in-domain",
            source_kind="device-read",
            observed_x=(21.66763547681415, 21.66763547681415),
        ),
        _build_case(
            3,
            role="ood-probe",
            source_kind="controller-export",
            observed_x=(0.0, 0.0),
            ood=True,
        ),
    ]
    for case in cases:
        case["contentHash"] = _case_content_hash(case)
    payload = {
        "artifactType": "axiom.intelligence.real-paired-holdout-set",
        "schemaId": "axiom.intelligence.real-paired-holdout-set@1",
        "schemaVersion": 1,
        "holdoutSetId": "axiom.intelligence.real-holdout.contract@1",
        "modelBundleHash": scenario.model_bundle.content_hash,
        "trainingDatasetHash": scenario.dataset.content_hash,
        "governance": {
            "governanceId": "axiom.intelligence.real-holdout-governance@1",
            "licenseId": "axiom.internal.eval-license@1",
            "allowedUses": ["real-holdout-evaluation"],
            "retentionPolicyId": "axiom.retention.eval@1",
            "ownerId": "axiom-test-owner",
            "authorizationId": "axiom.real-holdout-authorization@1",
            "authenticityBasis": "data-owner-attestation",
            "attestedAt": "2026-08-12T11:00:00+00:00",
            "sensitivity": "internal",
            "redistributionAllowed": False,
            "contentHash": "",
        },
        "selection": {
            "selectionId": "axiom.intelligence.real-holdout-selection@1",
            "modelBundleHash": scenario.model_bundle.content_hash,
            "trainingDatasetHash": scenario.dataset.content_hash,
            "selectedBeforeEvaluation": True,
            "leakageDimensions": ["device", "condition", "task", "batch", "time"],
            "caseIds": [case["caseId"] for case in cases],
            "contentHash": "",
        },
        "cases": cases,
        "contentHash": "",
    }
    payload["governance"]["contentHash"] = _governance_content_hash(
        payload["governance"]
    )
    payload["selection"]["contentHash"] = _selection_content_hash(payload["selection"])
    payload["contentHash"] = _set_content_hash(payload)
    return payload


def test_r5b_real_holdout_contract_accepts_case_scoped_windows_payload() -> None:
    holdout = RealPairedHoldoutSet.model_validate(_build_holdout_set())

    assert holdout.governance.authenticity_basis == "data-owner-attestation"
    assert holdout.selection.leakage_dimensions == (
        "device",
        "condition",
        "task",
        "batch",
        "time",
    )
    assert [case.case_id for case in holdout.cases] == list(holdout.selection.case_ids)


def test_r5b_request_rejects_holdout_that_starts_before_training_window() -> None:
    scenario = load_r5_scenario()
    payload = {
        "artifact": scenario.model_bundle.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "dataset": scenario.dataset.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "splitManifest": scenario.split_manifest.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "trainingReceipt": scenario.training_receipt.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "parityReceipt": scenario.parity_receipt.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "realHoldoutSet": _build_holdout_set(),
        "case": {
            "caseId": "r5b-holdout-contract@1",
            "requiredMetrics": [
                "intelligence.r5b.model-integrity@1",
                "intelligence.real-world-generalization@1",
            ],
        },
    }
    payload["realHoldoutSet"]["cases"][0]["captureStartTime"] = (
        "2026-08-11T00:00:00+00:00"
    )
    payload["realHoldoutSet"]["cases"][0]["contentHash"] = _case_content_hash(
        payload["realHoldoutSet"]["cases"][0]
    )
    payload["realHoldoutSet"]["contentHash"] = _set_content_hash(
        payload["realHoldoutSet"]
    )

    with pytest.raises(
        ValueError,
        match="captureStartTime must be later than the training dataset window",
    ):
        R5BIntelligenceEvaluationRequest.model_validate(payload)


def test_r5b_holdout_rejects_synthetic_source_and_missing_clock() -> None:
    synthetic = _build_holdout_set()
    synthetic["cases"][0]["sourceKind"] = "synthetic-replay"
    synthetic["cases"][0]["observation"]["artifact"]["sourceKind"] = "synthetic-replay"
    with pytest.raises(ValueError, match="controller-export|device-read"):
        RealPairedHoldoutSet.model_validate(synthetic)

    missing_clock = _build_holdout_set()
    missing_clock["cases"][0]["observation"]["clockMapping"] = None
    with pytest.raises(ValueError, match="requires clockMapping"):
        RealPairedHoldoutSet.model_validate(missing_clock)


def test_r5b_holdout_rejects_governance_tamper_and_condition_leak() -> None:
    tampered = _build_holdout_set()
    tampered["governance"]["ownerId"] = "different-owner"
    with pytest.raises(
        ValueError, match="contentHash must match RealHoldoutGovernance"
    ):
        RealPairedHoldoutSet.model_validate(tampered)

    leaked = _build_holdout_set()
    leaked["cases"][1]["conditionId"] = leaked["cases"][0]["conditionId"]
    leaked["cases"][1]["contentHash"] = _case_content_hash(leaked["cases"][1])
    with pytest.raises(ValueError, match="span at least two conditions"):
        RealPairedHoldoutSet.model_validate(leaked)


def test_r5b_holdout_attestation_must_follow_capture_completion() -> None:
    payload = _build_holdout_set()
    payload["governance"]["attestedAt"] = "2026-08-12T09:00:00+00:00"
    payload["governance"]["contentHash"] = _governance_content_hash(
        payload["governance"]
    )

    with pytest.raises(
        ValueError, match="attestedAt must not precede capture completion"
    ):
        RealPairedHoldoutSet.model_validate(payload)
