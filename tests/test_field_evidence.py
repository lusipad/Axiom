from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from axiom.cli import main
from axiom.control.models import canonical_hash
from axiom.control.r7b_models import (
    DeploymentControllerProfile,
    ReadOnlyAuthorityEvidence,
)
from axiom.control.r7e_models import (
    BeckhoffShadowCaptureAuthorization,
    BeckhoffShadowRunEvidence,
    BeckhoffShadowWitnessProfile,
    R7EAssessmentRequest,
)
from axiom.field_evidence import (
    FieldEvidenceAssessmentReport,
    FieldEvidenceAssessmentRequest,
    assess_field_evidence,
)
from axiom.five_axis import f4_example_payload
from axiom.five_axis.f2_kinematics import normalize_numeric_identity
from axiom.five_axis.f3_sampling import M5DiscreteCommand
from axiom.physical import exact_zoh_response
from axiom.web import create_app
from tests.test_control_r7d import _complete_evidence


def _open_request() -> dict[str, object]:
    return {
        "schemaId": "axiom.field-evidence-assessment-request@1",
        "schemaVersion": 1,
        "assessmentId": "field.acceptance.test@1",
        "calibrationPairId": "field.calibration.test@1",
        "validationPairId": "field.validation.test@1",
        "calibration": {"caseId": "site.part-family-17@1"},
        "validation": {"caseId": "site.part-family-17@1"},
    }


def _seal(model_type, payload: dict[str, object]):
    sealed = copy.deepcopy(payload)
    sealed["contentHash"] = canonical_hash(sealed)
    return model_type.model_validate(sealed)


def _test_command(role: str, shift: int) -> M5DiscreteCommand:
    payload = copy.deepcopy(
        f4_example_payload("canonical-head-table-solver")["artifacts"][
            "referenceCommand"
        ]
    )
    payload["discreteCommandId"] = f"test.{role}.command.v1"
    for index, sample in enumerate(payload["samples"]):
        sample["q"] = [
            ((index + shift) % 4) * 0.1,
            ((index * 2 + shift) % 5) * 0.12,
            ((index * 3 + shift) % 6) * 0.08,
            ((index * 2 + 1 + shift) % 5) * 0.01,
            ((index * 3 + 2 + shift) % 7) * 0.012,
        ]
    identity = copy.deepcopy(payload)
    identity.pop("contentId")
    canonical = json.dumps(
        normalize_numeric_identity(identity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    payload["contentId"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return M5DiscreteCommand.model_validate(payload)


def _controller_context():
    profile, runtime, _transport = _complete_evidence()
    controller = _seal(
        DeploymentControllerProfile,
        {
            "profileId": "test.beckhoff.controller@1",
            "vendor": "Beckhoff Automation",
            "controllerFamily": "TwinCAT 3",
            "controllerModel": "CX-Test",
            "softwareVersion": "4026.17",
            "machineId": "test-five-axis-01",
            "interfaceType": "opc-ua",
            "targetStatus": "Selected",
        },
    )
    authority = _seal(
        ReadOnlyAuthorityEvidence,
        {
            "evidenceId": "test.authority@1",
            "controllerProfileContentHash": controller.content_hash,
            "principalId": "test-shadow-reader",
            "enforcementPoint": "controller",
            "grantedOperations": ["read", "subscribe"],
            "deniedOperations": [
                "parameter-write",
                "program-transfer",
                "cycle-start",
                "feed-hold",
                "reset",
                "jog",
                "safety-bypass",
            ],
            "attestationKind": "independent-audit",
            "attestationContentHash": "1" * 64,
            "verificationStatus": "Verified",
            "trustAnchorContentHash": "2" * 64,
        },
    )
    return profile, runtime, controller, authority


def _complete_test_r7e_request(
    *,
    role: str,
    start: datetime,
    shift: int,
    inject_holdout_noise: bool = False,
) -> R7EAssessmentRequest:
    profile, runtime, controller, authority = _controller_context()
    command = _test_command(role, shift)
    nodes: list[dict[str, object]] = [
        {
            "canonicalSignalId": "command.content-hash",
            "role": "command-content-hash",
            "namespaceUri": "urn:test:plc",
            "identifier": "MAIN.CommandHash",
            "expectedDataType": "String",
            "unit": "sha256",
            "requiredAccessLevel": 1,
            "requiredUserAccessLevel": 1,
        },
        {
            "canonicalSignalId": "command.sample-index",
            "role": "sample-index",
            "namespaceUri": "urn:test:plc",
            "identifier": "MAIN.SampleIndex",
            "expectedDataType": "UInt32",
            "unit": "index",
            "requiredAccessLevel": 1,
            "requiredUserAccessLevel": 1,
        },
    ]
    for axis in ("X", "Y", "Z", "B", "C"):
        nodes.append(
            {
                "canonicalSignalId": f"machine.axis.{axis}.position",
                "role": "axis-position",
                "axisId": axis,
                "namespaceUri": "urn:test:plc",
                "identifier": f"MAIN.Axis{axis}Position",
                "expectedDataType": "Double",
                "unit": "mm" if axis in {"X", "Y", "Z"} else "rad",
                "requiredAccessLevel": 1,
                "requiredUserAccessLevel": 1,
            }
        )
    witness = _seal(
        BeckhoffShadowWitnessProfile,
        {
            "schemaId": "axiom.control.beckhoff-shadow-witness-profile@1",
            "profileId": f"test.{role}.witness@1",
            "vendorProfileContentHash": profile.content_hash,
            "runtimeEvidenceContentHash": runtime.content_hash,
            "nodeVerificationEvidenceContentHash": (
                "8" if role == "calibration" else "9"
            )
            * 64,
            "expectedCommandContentHash": command.content_id,
            "bindingStatus": "Bound",
            "platform": "Windows",
            "protocol": "opc-ua",
            "capturePolicy": "sample-index-triggered-batch-read",
            "intervalPolicy": "exact-sample-index-no-interpolation",
            "maximumTimestampUncertaintyMs": 20.0,
            "maximumSampleIndexGap": 0,
            "nodes": nodes,
            "permissionCeiling": "Shadow",
            "deviceWriteAllowed": False,
            "methodCallAllowed": False,
        },
    )
    end = start + timedelta(seconds=float(command.samples[-1].t))
    authorization = _seal(
        BeckhoffShadowCaptureAuthorization,
        {
            "schemaId": "axiom.control.beckhoff-shadow-capture-authorization@1",
            "authorizationId": f"test.{role}.authorization@1",
            "dataOwnerId": "test-owner",
            "controllerProfileContentHash": controller.content_hash,
            "commandContentHash": command.content_id,
            "authorizedFrom": (start - timedelta(seconds=1)).isoformat(),
            "authorizedUntil": (end + timedelta(seconds=1)).isoformat(),
            "acquisitionPurpose": "deployment-shadow-validation",
            "capturedOutsideRepository": True,
            "evaluationAuthorized": True,
            "attestationKind": "data-owner-attestation",
            "attestationContentHash": ("3" if role == "calibration" else "4")
            * 64,
        },
    )
    times = tuple(float(sample.t) for sample in command.samples)
    commands = tuple(
        tuple(float(sample.q[axis]) for sample in command.samples)
        for axis in range(5)
    )
    biases = (0.02, -0.01, 0.03, 0.002, -0.003)
    observations = tuple(
        exact_zoh_response(
            commands[axis],
            times,
            time_constant_seconds=0.1,
            bias=biases[axis],
        )
        for axis in range(5)
    )
    if inject_holdout_noise:
        observations = tuple(
            tuple(
                value + (10 if axis < 3 else 1) * (1 if index % 2 else -1)
                for index, value in enumerate(series)
            )
            for axis, series in enumerate(observations)
        )
    frames = []
    for index, sample in enumerate(command.samples):
        timestamp = (start + timedelta(seconds=float(sample.t))).isoformat()
        frames.append(
            {
                "sequence": index,
                "protocolSequenceNumber": index + 1,
                "notifiedSampleIndex": index,
                "readSampleIndex": index,
                "commandContentHash": command.content_id,
                "hostTimestamp": timestamp,
                "samples": [
                    {
                        "axisId": axis,
                        "value": observations[axis_index][index],
                        "unit": "mm" if axis in {"X", "Y", "Z"} else "rad",
                        "quality": "good",
                        "statusCode": "Good",
                        "sourceTimestamp": timestamp,
                        "serverTimestamp": timestamp,
                    }
                    for axis_index, axis in enumerate(("X", "Y", "Z", "B", "C"))
                ],
            }
        )
    evidence = _seal(
        BeckhoffShadowRunEvidence,
        {
            "schemaId": "axiom.control.beckhoff-shadow-run-evidence@1",
            "evidenceId": f"test.{role}.evidence@1",
            "adapterId": "axiom.control.beckhoff-shadow-witness-adapter@1",
            "adapterVersion": "test-only",
            "platform": "Windows",
            "sourceKind": "controller-live-read",
            "declaredReal": True,
            "controllerProfileContentHash": controller.content_hash,
            "authorityContentHash": authority.content_hash,
            "captureAuthorizationContentHash": authorization.content_hash,
            "vendorProfileContentHash": profile.content_hash,
            "runtimeEvidenceContentHash": runtime.content_hash,
            "witnessProfileContentHash": witness.content_hash,
            "commandContentHash": command.content_id,
            "capturedAt": end.isoformat(),
            "frames": frames,
            "receipt": {
                "status": "Succeeded",
                "openedAt": start.isoformat(),
                "closedAt": end.isoformat(),
                "subscribeOperationCount": 1,
                "readOperationCount": len(frames),
                "writeOperationCount": 0,
                "methodCallOperationCount": 0,
                "receivedFrameCount": len(frames),
                "acceptedFrameCount": len(frames),
                "rejectedFrameCount": 0,
                "droppedSampleIndexCount": 0,
                "transcriptContentHash": canonical_hash(frames),
            },
            "countsTowardReality": False,
            "realityValidationStatus": "Open",
            "deviceSafetyStatus": "NotAssessed",
            "processSafetyStatus": "NotAssessed",
        },
    )
    return R7EAssessmentRequest(
        caseId="site.test-case@1",
        vendorProfile=profile,
        runtimeEvidence=runtime,
        witnessProfile=witness,
        controllerProfile=controller,
        authority=authority,
        captureAuthorization=authorization,
        command=command,
        shadowEvidence=evidence,
    )


def test_field_evidence_requires_two_distinct_runs_in_one_explicit_case() -> None:
    missing_case = _open_request()
    missing_case["validation"] = {}
    with pytest.raises(ValidationError, match="explicit caseId"):
        FieldEvidenceAssessmentRequest.model_validate(missing_case)

    different_case = _open_request()
    different_case["validation"] = {"caseId": "site.part-family-18@1"}
    with pytest.raises(ValidationError, match="same caseId"):
        FieldEvidenceAssessmentRequest.model_validate(different_case)

    reused_pair_id = _open_request()
    reused_pair_id["validationPairId"] = reused_pair_id["calibrationPairId"]
    with pytest.raises(ValidationError, match="must be distinct"):
        FieldEvidenceAssessmentRequest.model_validate(reused_pair_id)


def test_field_evidence_open_inputs_stay_open_and_deterministic() -> None:
    request = FieldEvidenceAssessmentRequest.model_validate(_open_request())

    first = assess_field_evidence(request)
    second = assess_field_evidence(request)

    assert first == second
    assert first.content_hash == second.content_hash
    assert first.overall_status == "Open"
    assert first.counts_toward_reality is False
    assert first.calibration_pair is None
    assert first.validation_pair is None
    assert first.reality_assessment.analysis.reality_validation_status == "Open"
    assert first.validation_scope == "single-device-case-scoped"
    assert first.controlled_trial_status == "Open"
    assert first.closed_loop_status == "Open"
    assert first.device_safety_status == "NotAssessed"
    assert first.process_safety_status == "NotAssessed"


def test_field_evidence_orchestrates_passed_blocked_and_refuted_gates() -> None:
    calibration = _complete_test_r7e_request(
        role="calibration",
        start=datetime(2026, 8, 13, 8, tzinfo=timezone.utc),
        shift=0,
    )
    validation = _complete_test_r7e_request(
        role="validation",
        start=datetime(2026, 8, 13, 9, tzinfo=timezone.utc),
        shift=1,
    )

    def assess(validation_request: R7EAssessmentRequest):
        return assess_field_evidence(
            FieldEvidenceAssessmentRequest(
                schemaId="axiom.field-evidence-assessment-request@1",
                schemaVersion=1,
                assessmentId="field.acceptance.full-test@1",
                calibrationPairId="field.calibration.full-test@1",
                validationPairId="field.validation.full-test@1",
                calibration=calibration,
                validation=validation_request,
            )
        )

    passed = assess(validation)
    assert passed.overall_status == "Passed"
    assert passed.counts_toward_reality is True
    assert passed.calibration_pair is not None
    assert passed.validation_pair is not None
    assert passed.reality_assessment.analysis.reality_validation_status == "Passed"
    assert passed.device_safety_status == "NotAssessed"
    assert passed.process_safety_status == "NotAssessed"

    blocked = assess(calibration)
    assert blocked.overall_status == "Blocked"
    assert blocked.counts_toward_reality is False
    assert blocked.reality_assessment.analysis.checks[1].reason_code == (
        "CalibrationValidationLeakage"
    )

    refuted = assess(
        _complete_test_r7e_request(
            role="noisy-validation",
            start=datetime(2026, 8, 13, 10, tzinfo=timezone.utc),
            shift=2,
            inject_holdout_noise=True,
        )
    )
    assert refuted.overall_status == "Refuted"
    assert refuted.counts_toward_reality is False
    assert refuted.reality_assessment.analysis.fit_status == "Refuted"


def test_field_evidence_report_rejects_hash_tampering() -> None:
    report = assess_field_evidence(
        FieldEvidenceAssessmentRequest.model_validate(_open_request())
    )
    tampered = report.model_dump(mode="json", by_alias=True, exclude_none=True)
    tampered["assessmentId"] = "field.acceptance.tampered@1"

    with pytest.raises(ValidationError, match="contentHash"):
        FieldEvidenceAssessmentReport.model_validate(tampered)


def test_field_evidence_cli_returns_one_for_open_gate(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = FieldEvidenceAssessmentRequest.model_validate(_open_request())
    expected = assess_field_evidence(request).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    request_path = tmp_path / "field-evidence.json"
    request_path.write_text(json.dumps(_open_request()), encoding="utf-8")

    assert main(["field-evidence", str(request_path)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output == expected


def test_field_evidence_cli_pairs_two_ready_r7e_assessments(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _open_request()
    calibration_path = tmp_path / "calibration.r7e.json"
    validation_path = tmp_path / "validation.r7e.json"
    calibration_path.write_text(
        json.dumps(payload["calibration"]), encoding="utf-8"
    )
    validation_path.write_text(
        json.dumps(payload["validation"]), encoding="utf-8"
    )
    expected = assess_field_evidence(
        FieldEvidenceAssessmentRequest.model_validate(payload)
    ).model_dump(mode="json", by_alias=True, exclude_none=True)

    exit_code = main(
        [
            "field-evidence",
            "--calibration",
            str(calibration_path),
            "--validation",
            str(validation_path),
            "--assessment-id",
            str(payload["assessmentId"]),
            "--calibration-pair-id",
            str(payload["calibrationPairId"]),
            "--validation-pair-id",
            str(payload["validationPairId"]),
        ]
    )

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out) == expected


def test_field_evidence_cli_pair_mode_rejects_malformed_r7e_input(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    calibration_path = tmp_path / "calibration.r7e.json"
    validation_path = tmp_path / "validation.r7e.json"
    calibration_path.write_text('{"caseId":"site.case@1","unexpected":true}', encoding="utf-8")
    validation_path.write_text('{"caseId":"site.case@1"}', encoding="utf-8")

    exit_code = main(
        [
            "field-evidence",
            "--calibration",
            str(calibration_path),
            "--validation",
            str(validation_path),
            "--assessment-id",
            "field.assessment@1",
            "--calibration-pair-id",
            "field.calibration@1",
            "--validation-pair-id",
            "field.validation@1",
        ]
    )

    assert exit_code == 2
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "MalformedR7EAssessmentRequest"
    assert error["role"] == "calibration"


def test_field_evidence_cli_returns_two_for_malformed_request(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = _open_request()
    request["validation"] = {"caseId": "site.other-case@1"}
    request_path = tmp_path / "field-evidence.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    assert main(["field-evidence", str(request_path)]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "MalformedFieldEvidenceAssessmentRequest"


def test_field_evidence_http_returns_one_deterministic_report() -> None:
    client = TestClient(create_app(serve_frontend=False))
    expected = assess_field_evidence(
        FieldEvidenceAssessmentRequest.model_validate(_open_request())
    ).model_dump(mode="json", by_alias=True, exclude_none=True)

    first = client.post("/api/v1/field-evidence/assess", json=_open_request())
    second = client.post("/api/v1/field-evidence/assess", json=_open_request())

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json() == expected


def test_field_evidence_http_rejects_cross_case_pairing() -> None:
    client = TestClient(create_app(serve_frontend=False))
    request = _open_request()
    request["validation"] = {"caseId": "site.part-family-18@1"}

    response = client.post("/api/v1/field-evidence/assess", json=request)

    assert response.status_code == 422
