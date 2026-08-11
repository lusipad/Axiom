from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from axiom.evaluator import _content_hash
from axiom.five_axis.f2_kinematics import normalize_numeric_identity
from axiom.five_axis.f4_models import (
    AdapterReceipt,
    CrossValidationResult,
    F4MathStageManifest,
    F4StageAcceptanceReport,
    M5CollisionVerification,
)

_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64


def _portable_content_hash(payload: dict) -> str:
    return _content_hash(normalize_numeric_identity(payload))


def _gate_claims_payload() -> list[dict]:
    return [
        {
            "claimId": "five-axis.geometry-valid-claim@1",
            "claimClass": "M2",
            "expectedStatus": "Supported",
            "evidenceLevel": "Validated",
        },
        {
            "claimId": "five-axis.task-geometry-collision-free-claim@1",
            "claimClass": "M2",
            "expectedStatus": "Supported",
            "evidenceLevel": "Validated",
        },
        {
            "claimId": "five-axis.kinematically-feasible-claim@1",
            "claimClass": "M3",
            "expectedStatus": "Supported",
            "evidenceLevel": "Validated",
        },
        {
            "claimId": "five-axis.configuration-collision-free-claim@1",
            "claimClass": "M3",
            "expectedStatus": "Supported",
            "evidenceLevel": "Validated",
        },
        {
            "claimId": "five-axis.continuously-feasible-claim@1",
            "claimClass": "M4",
            "expectedStatus": "Supported",
            "evidenceLevel": "Certified",
        },
        {
            "claimId": "five-axis.interval-certified-claim@1",
            "claimClass": "M5",
            "expectedStatus": "Supported",
            "evidenceLevel": "Certified",
        },
        {
            "claimId": "five-axis.model-collision-free-claim@1",
            "claimClass": "M5",
            "expectedStatus": "Supported",
            "evidenceLevel": "Validated",
        },
    ]


def _gate_statuses_payload() -> list[dict]:
    return [
        {"claimId": item["claimId"], "status": "Supported", "evidenceLevel": item["evidenceLevel"]}
        for item in _gate_claims_payload()
    ]


def _tolerances_payload() -> list[dict]:
    return [
        {"toleranceId": "tol.position", "target": "position", "tolerance": {"absolute": 1e-6, "unit": "mm"}},
        {"toleranceId": "tol.velocity", "target": "velocity", "tolerance": {"absolute": 1e-6, "unit": "mm/s"}},
        {"toleranceId": "tol.acceleration", "target": "acceleration", "tolerance": {"absolute": 1e-6, "unit": "mm/s^2"}},
        {"toleranceId": "tol.jerk", "target": "jerk", "tolerance": {"absolute": 1e-6, "unit": "mm/s^3"}},
    ]


def _manifest_payload() -> dict:
    return {
        "manifestId": "five-axis.f4-math-stage-manifest@1",
        "schemaId": "five-axis.f4-math-stage-manifest@1",
        "schemaVersion": 1,
        "stage": "F4",
        "artifactDescriptors": [
            {"stage": "M0", "artifactType": "five-axis.normalized-program", "schemaId": "five-axis.normalized-program@1"},
            {"stage": "M1", "artifactType": "five-axis.m1-reference-path", "schemaId": "five-axis.m1-reference-path@1"},
            {"stage": "M2", "artifactType": "five-axis.m2-candidate-task-geometry", "schemaId": "five-axis.m2-candidate-task-geometry@1"},
            {"stage": "M3", "artifactType": "five-axis.m3-candidate-axis-path", "schemaId": "five-axis.m3-candidate-axis-path@1"},
            {"stage": "M4", "artifactType": "five-axis.m4-continuous-trajectory", "schemaId": "five-axis.m4-continuous-trajectory@1"},
            {"stage": "M5", "artifactType": "five-axis.m5-discrete-command", "schemaId": "five-axis.m5-discrete-command@1"},
        ],
        "adapterTransport": "in-process",
        "capabilityIds": [
            "five-axis.adapter.in-process@1",
            "five-axis.cross-validation.strict@1",
        ],
        "fixtureContentIds": [_HASH_A],
        "policyIds": [
            "five-axis.reconstruction.polynomial@1",
            "five-axis.collision.m5-interval.strict@1",
        ],
        "numericEnvironment": {"python": "3.14", "numpy": "2"},
        "expectedMetrics": [
            {
                "metricId": "five-axis.cross-validation.max-position-gap@1",
                "expectedStatus": "Computed",
                "expectedValue": 0.0,
                "unit": "mm",
            }
        ],
        "expectedClaims": _gate_claims_payload(),
        "expectedEvidence": [
            {"evidenceId": "evidence.receipt", "evidenceKind": "adapter-receipt", "required": True},
            {"evidenceId": "evidence.cross", "evidenceKind": "cross-validation", "required": True},
        ],
        "tolerances": _tolerances_payload(),
        "decisions": [
            {"decisionId": "decision.1", "status": "accepted", "rationale": "Freeze the F4 math-only acceptance contract."}
        ],
    }


def _adapter_receipt_payload() -> dict:
    return {
        "invocation": {
            "invocationId": "invoke.1",
            "descriptor": {
                "adapterId": "five-axis.adapter.reference",
                "version": "1",
                "role": "reference",
                "subjectId": "reference.subject",
                "subjectVersion": "2026.08.11",
                "inputType": "five-axis.m4-continuous-trajectory",
                "outputType": "five-axis.m5-discrete-command",
                "transport": "in-process",
            },
            "inputM4Id": "m4.trajectory.1",
            "inputM4ContentHash": _HASH_A,
            "policyId": "five-axis.reconstruction.polynomial@1",
            "samplePeriod": 0.5,
            "finalHold": False,
        },
        "descriptor": {
            "adapterId": "five-axis.adapter.reference",
            "version": "1",
            "role": "reference",
            "subjectId": "reference.subject",
            "subjectVersion": "2026.08.11",
            "inputType": "five-axis.m4-continuous-trajectory",
            "outputType": "five-axis.m5-discrete-command",
            "transport": "in-process",
        },
        "status": "Succeeded",
        "inputContentHash": _HASH_A,
        "outputContentHash": _HASH_B,
        "deterministicWorkUnits": 12,
        "numericEnvironment": {"python": "3.14", "numpy": "2"},
    }


def _cross_validation_payload() -> dict:
    return {
        "referenceContentHash": _HASH_A,
        "sutContentHash": _HASH_B,
        "status": "Supported",
        "maxPositionGap": 1e-7,
        "maxVelocityGap": 1e-7,
        "maxAccelerationGap": 1e-7,
        "maxJerkGap": 1e-7,
        "tolerances": _tolerances_payload(),
        "evidenceLevel": "Exact",
        "method": "five-axis.cross-validation.sampled-joint-gap@1",
    }


def _collision_verification_payload() -> dict:
    return {
        "contributesToClaimId": "five-axis.model-collision-free-claim@1",
        "commandId": "m5.command.1",
        "commandContentHash": _HASH_A,
        "sourceM3Id": "m3.path.1",
        "sourceM3ContentHash": _HASH_B,
        "collisionModelId": "five-axis.configuration-collision-model@1",
        "collisionModelContentHash": _HASH_C,
        "reconstructionPolicyId": "five-axis.reconstruction.polynomial@1",
        "status": "safe",
        "coverageStatus": "complete",
        "supportsModelCollisionAggregation": True,
        "evidenceLevel": "Validated",
        "method": "five-axis.m5-collision.interval-envelope@1",
        "intervalEvaluations": [
            {
                "intervalId": "interval.1",
                "tStart": 0.0,
                "tEnd": 0.5,
                "status": "safe",
                "minimumClearanceLowerBound": 0.01,
            }
        ],
    }


def _report_payload() -> dict:
    payload = {
        "reportId": "f4.acceptance.1",
        "stage": "F4",
        "scenarioResults": [
            {
                "scenarioId": "dual-table.nominal",
                "topology": "dual-table",
                "sutMode": "solver",
                "countsTowardClosure": True,
                "outcome": "Passed",
                "referenceReceiptStatus": "Succeeded",
                "sutReceiptStatus": "Succeeded",
                "crossValidationStatus": "Supported",
                "collisionStatus": "safe",
            },
            {
                "scenarioId": "head-table.nominal",
                "topology": "head-table",
                "sutMode": "solver",
                "countsTowardClosure": True,
                "outcome": "Passed",
                "referenceReceiptStatus": "Succeeded",
                "sutReceiptStatus": "Succeeded",
                "crossValidationStatus": "Supported",
                "collisionStatus": "safe",
            },
            {
                "scenarioId": "dual-head.replay-counterexample",
                "topology": "dual-head",
                "sutMode": "replay",
                "countsTowardClosure": False,
                "outcome": "Passed",
                "referenceReceiptStatus": "Succeeded",
                "sutReceiptStatus": "Succeeded",
                "crossValidationStatus": "Supported",
                "collisionStatus": "safe",
            },
        ],
        "topologyCoverage": [
            {"topology": "dual-table", "covered": True},
            {"topology": "head-table", "covered": True},
            {"topology": "dual-head", "covered": True},
        ],
        "counterexampleCoverage": [
            {"counterexampleId": "counterexample.reconstruction", "covered": True},
            {"counterexampleId": "counterexample.collision", "covered": True},
        ],
        "gateClaimStatuses": _gate_statuses_payload(),
        "status": "Passed",
    }
    payload["contentHash"] = _portable_content_hash(payload)
    return payload


def test_f4_manifest_accepts_frozen_seven_gate_contract() -> None:
    manifest = F4MathStageManifest.model_validate(_manifest_payload())

    assert manifest.stage == "F4"
    assert manifest.artifact_descriptors[-1].artifact_type == "five-axis.m5-discrete-command"
    assert tuple(item.claim_id for item in manifest.expected_claims) == tuple(item["claimId"] for item in _gate_claims_payload())


def test_adapter_receipt_cross_validation_and_collision_contracts_reject_invalid_combinations() -> None:
    receipt = AdapterReceipt.model_validate(_adapter_receipt_payload())
    cross_validation = CrossValidationResult.model_validate(_cross_validation_payload())
    collision = M5CollisionVerification.model_validate(_collision_verification_payload())

    assert receipt.status == "Succeeded"
    assert cross_validation.status == "Supported"
    assert collision.supports_model_collision_aggregation is True

    bad_receipt = _adapter_receipt_payload()
    bad_receipt["failureCode"] = "ShouldNotExist"
    bad_receipt["failureMessage"] = "Succeeded receipts cannot carry failure details."
    with pytest.raises(ValidationError, match="Succeeded receipts must not declare failureCode or failureMessage"):
        AdapterReceipt.model_validate(bad_receipt)

    mismatched_success = _adapter_receipt_payload()
    mismatched_success["inputContentHash"] = _HASH_C
    with pytest.raises(
        ValidationError,
        match="Succeeded receipts require inputContentHash to equal invocation.inputM4ContentHash",
    ):
        AdapterReceipt.model_validate(mismatched_success)

    failed_mismatch = _adapter_receipt_payload()
    failed_mismatch.update(
        status="Failed",
        inputContentHash=_HASH_C,
        outputContentHash=None,
        failureCode="InputContentHashMismatch",
        failureMessage="The supplied M4 artifact did not match the invocation binding.",
    )
    failed_receipt = AdapterReceipt.model_validate(failed_mismatch)
    assert failed_receipt.input_content_hash == _HASH_C

    bad_cross_validation = _cross_validation_payload()
    bad_cross_validation["maxJerkGap"] = 1e-3
    with pytest.raises(ValidationError, match="Supported cross-validation requires maxJerkGap to satisfy tolerances"):
        CrossValidationResult.model_validate(bad_cross_validation)

    bad_collision = _collision_verification_payload()
    bad_collision["coverageStatus"] = "partial"
    with pytest.raises(
        ValidationError,
        match="supportsModelCollisionAggregation may be true only for safe results with complete coverage",
    ):
        M5CollisionVerification.model_validate(bad_collision)


def test_stage_acceptance_report_seals_content_hash_and_replay_stays_out_of_closure() -> None:
    report = F4StageAcceptanceReport.model_validate(_report_payload())
    assert report.status == "Passed"
    assert report.scenario_results[-1].counts_toward_closure is False

    replay_payload = _report_payload()
    replay_payload["scenarioResults"][2]["countsTowardClosure"] = True
    replay_payload["contentHash"] = _portable_content_hash(
        {key: value for key, value in replay_payload.items() if key != "contentHash"}
    )
    with pytest.raises(ValidationError, match="replay SUT scenarios must not count toward closure"):
        F4StageAcceptanceReport.model_validate(replay_payload)

    tampered_payload = _report_payload()
    tampered_payload["reportId"] = "f4.acceptance.2"
    with pytest.raises(ValidationError, match="contentHash must equal the canonical content hash of the report payload"):
        F4StageAcceptanceReport.model_validate(tampered_payload)


@pytest.mark.parametrize(
    ("claim_id", "claim_class"),
    [
        ("five-axis.device-safe-claim@1", "DeviceSafe"),
        ("five-axis.process-safe-claim@1", "ProcessSafe"),
    ],
)
def test_f4_manifest_rejects_forbidden_device_or_process_claims(claim_id: str, claim_class: str) -> None:
    payload = _manifest_payload()
    payload["expectedClaims"][-1] = {
        "claimId": claim_id,
        "claimClass": claim_class,
        "expectedStatus": "Supported",
        "evidenceLevel": "Observed",
    }

    with pytest.raises(ValidationError, match="must not publish DeviceSafe or ProcessSafe claims"):
        F4MathStageManifest.model_validate(payload)


def test_f4_manifest_rejects_missing_gate_whitelist_member() -> None:
    payload = _manifest_payload()
    payload["expectedClaims"] = copy.deepcopy(payload["expectedClaims"][:-1])
    payload["expectedClaims"].append(
        {
            "claimId": "five-axis.some-other-claim@1",
            "claimClass": "M5",
            "expectedStatus": "Supported",
            "evidenceLevel": "Observed",
        }
    )

    with pytest.raises(ValidationError, match="frozen seven-gate whitelist"):
        F4MathStageManifest.model_validate(payload)
