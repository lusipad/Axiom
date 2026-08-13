from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from axiom.cli import main
from axiom.field_evidence import (
    FieldEvidenceAssessmentRequest,
    assess_field_evidence,
)
from axiom.intelligence import validate_r5b_example_run_spec
from axiom.intelligence.real_holdout_intake import (
    RealHoldoutIntakeCase,
    RealHoldoutIntakeRequest,
    assess_real_holdout_intake,
)
from axiom.intelligence.r5b_models import RealHoldoutGovernance
from axiom.machine.models import (
    ClockMapping,
    CoordinateAlignment,
    DeviceProfile,
    MachineRunLineage,
)
from axiom.machine.runtime import (
    evaluate_machine_observation,
    machine_trace_content_hash,
)
from axiom.physical.models import AxisChannelBinding
from axiom.run import evaluate_run
from axiom.web import create_app
from tests.test_field_evidence import (
    _complete_test_r7e_request,
    _open_request,
    _seal,
)


_CLAIMS = (
    "five-axis.geometry-valid-claim@1",
    "five-axis.task-geometry-collision-free-claim@1",
    "five-axis.kinematically-feasible-claim@1",
    "five-axis.configuration-collision-free-claim@1",
    "five-axis.continuously-feasible-claim@1",
    "five-axis.interval-certified-claim@1",
    "five-axis.model-collision-free-claim@1",
)


def _report(
    *,
    suffix: str,
    machine_id: str,
    case_id: str,
    start: datetime,
    shift: int,
):
    calibration = _complete_test_r7e_request(
        role="calibration",
        start=start,
        shift=shift,
        case_id=case_id,
        machine_id=machine_id,
        identity_suffix=suffix,
    )
    validation = _complete_test_r7e_request(
        role="validation",
        start=start + timedelta(hours=1),
        shift=shift + 1,
        case_id=case_id,
        machine_id=machine_id,
        identity_suffix=suffix,
    )
    return assess_field_evidence(
        FieldEvidenceAssessmentRequest(
            schemaId="axiom.field-evidence-assessment-request@1",
            schemaVersion=1,
            assessmentId=f"field.{suffix}@1",
            calibrationPairId=f"field.{suffix}.calibration@1",
            validationPairId=f"field.{suffix}.validation@1",
            calibration=calibration,
            validation=validation,
        )
    )


def _case(
    *,
    suffix: str,
    machine_id: str,
    condition_id: str,
    role: str,
    start: datetime,
    shift: int,
) -> RealHoldoutIntakeCase:
    case_id = f"site.{suffix}@1"
    report = _report(
        suffix=suffix,
        machine_id=machine_id,
        case_id=case_id,
        start=start,
        shift=shift,
    )
    validation = report.validation_pair.parsed_r7e_request()
    assert validation.command is not None
    calibration_id = f"field.{suffix}.coordinate-calibration@1"
    channels = tuple(
        {
            "channelId": f"axis.{axis}.position",
            "kind": "scalar",
            "unit": "mm" if axis in {"X", "Y", "Z"} else "rad",
            "coordinateFrame": "machine",
        }
        for axis in ("X", "Y", "Z", "B", "C")
    )
    device_profile = DeviceProfile(
        profileId=f"field.{suffix}.device-profile@1",
        deviceId=machine_id,
        manufacturer="Beckhoff Automation",
        machineModel="five-axis-test-rig",
        controllerFamily="TwinCAT 3",
        firmwareVersion="4026.17",
        exportVersion="r7e-intake@1",
        allowedReadOnlyOperations=("file-import",),
        calibrationId=calibration_id,
        channels=channels,
    )
    validation_start = start + timedelta(hours=1)
    clock = ClockMapping(
        mappingId=f"field.{suffix}.clock@1",
        deviceId=machine_id,
        mappingMethod="vendor-declared",
        deviceReferenceTimestamp=validation_start.isoformat(),
        hostReferenceTimestamp=validation_start.isoformat(),
        offsetMilliseconds=0.0,
        driftBoundMilliseconds=0.1,
    )
    alignment = CoordinateAlignment(
        alignmentId=f"field.{suffix}.alignment@1",
        deviceId=machine_id,
        machineCoordinateFrame="machine",
        workCoordinateFrame="work",
        sourceKind="calibration-record",
        effectiveAt=validation_start.isoformat(),
        calibrationStatus="calibrated",
        calibrationId=calibration_id,
        channelIds=tuple(item["channelId"] for item in channels),
    )
    lineage = MachineRunLineage(
        machineRunId=f"field.{suffix}.machine-run@1",
        pairingStatus="paired",
        baselineKind="reference",
        baselineRunBundleHash=hashlib.sha256(suffix.encode("utf-8")).hexdigest(),
        sourceCommandContentHash=validation.command.content_id,
        upstreamClaims=tuple(
            {
                "claimDefinitionId": claim_id,
                "status": "Supported",
                "reportContentHash": (str(index + 1) * 64),
            }
            for index, claim_id in enumerate(_CLAIMS)
        ),
    )
    bindings = tuple(
        AxisChannelBinding(
            axisId=axis,
            axisIndex=index,
            channelId=f"axis.{axis}.position",
            unitFamily="linear-mm" if index < 3 else "rotary-rad",
            unit="mm" if index < 3 else "rad",
        )
        for index, axis in enumerate(("X", "Y", "Z", "B", "C"))
    )
    return RealHoldoutIntakeCase(
        report=report,
        role=role,
        topology="head-table",
        trajectoryFamily=f"family-{suffix}",
        taskId=f"task-{suffix}",
        conditionId=condition_id,
        batchId=f"batch-{suffix}",
        maximumTimeErrorSeconds=1e-6,
        deviceProfile=device_profile,
        clockMapping=clock,
        coordinateAlignment=alignment,
        lineage=lineage,
        bindings=bindings,
    )


def _governance(attested_at: datetime) -> RealHoldoutGovernance:
    return _seal(
        RealHoldoutGovernance,
        {
            "governanceId": "field.real-holdout-governance@1",
            "licenseId": "internal-evaluation-only",
            "allowedUses": ["real-holdout-evaluation"],
            "retentionPolicyId": "field.retention-policy@1",
            "ownerId": "field-data-owner",
            "authorizationId": "field.real-holdout-authorization@1",
            "authenticityBasis": "data-owner-attestation",
            "attestedAt": attested_at.isoformat(),
            "sensitivity": "restricted",
            "redistributionAllowed": False,
        },
    )


def _request(*, cases: tuple[RealHoldoutIntakeCase, ...]) -> RealHoldoutIntakeRequest:
    return RealHoldoutIntakeRequest(
        schemaId="axiom.intelligence.real-holdout-intake-request@1",
        schemaVersion=1,
        intakeId="field.real-holdout-intake@1",
        holdoutSetId="field.real-holdout-set@1",
        selectionId="field.real-holdout-selection@1",
        selectedBeforeEvaluation=True,
        baseRunSpec=validate_r5b_example_run_spec(),
        governance=_governance(datetime(2026, 8, 15, tzinfo=timezone.utc)),
        cases=cases,
    )


def _complete_cases() -> tuple[RealHoldoutIntakeCase, ...]:
    return (
        _case(
            suffix="a",
            machine_id="machine-a",
            condition_id="condition-a",
            role="in-domain",
            start=datetime(2026, 8, 14, 1, tzinfo=timezone.utc),
            shift=0,
        ),
        _case(
            suffix="b",
            machine_id="machine-b",
            condition_id="condition-b",
            role="in-domain",
            start=datetime(2026, 8, 14, 4, tzinfo=timezone.utc),
            shift=2,
        ),
        _case(
            suffix="c",
            machine_id="machine-c",
            condition_id="condition-c",
            role="ood-probe",
            start=datetime(2026, 8, 14, 7, tzinfo=timezone.utc),
            shift=4,
        ),
    )


def test_intake_projects_three_field_dossiers_into_one_r5b_run() -> None:
    request = _request(cases=_complete_cases())

    first = assess_real_holdout_intake(request)
    second = assess_real_holdout_intake(request)

    assert first == second
    assert first.intake_status == "Passed"
    assert first.counts_toward_reality is True
    assert first.real_holdout_set is not None
    assert first.r5b_run_spec is not None
    assert len(first.real_holdout_set.cases) == 3
    assert all(case.source_kind == "device-read" for case in first.real_holdout_set.cases)
    assert first.controlled_trial_status == "Open"
    assert first.closed_loop_status == "Open"
    assert first.device_safety_status == "NotAssessed"
    assert first.process_safety_status == "NotAssessed"

    bundle = evaluate_run(first.r5b_run_spec)
    assert bundle.report.execution_status.value == "Succeeded"
    assert bundle.report.case_outcome.value != "Invalid"


def test_intake_preserves_raw_samples_timestamps_and_upstream_hashes() -> None:
    source_case = _complete_cases()[0]
    report = assess_real_holdout_intake(_request(cases=_complete_cases()))
    assert report.real_holdout_set is not None
    projected = report.real_holdout_set.cases[0]
    validation = source_case.report.validation_pair.parsed_r7e_request()
    assert validation.shadow_evidence is not None

    assert projected.observation.artifact.capture_receipt.trace_content_hash == (
        machine_trace_content_hash(projected.observation.artifact)
    )
    assert projected.observation.artifact.vendor_metadata[
        "sourceValidationShadowEvidenceContentHash"
    ] == validation.shadow_evidence.content_hash
    r3_report = evaluate_machine_observation(projected.observation)
    assert all(
        result.status.value == "Computed" and result.value is True
        for result in r3_report.metric_results
    )
    assert projected.observation.artifact.vendor_metadata[
        "sourceFieldEvidenceReportContentHash"
    ] == source_case.report.content_hash
    for source_frame, projected_frame in zip(
        validation.shadow_evidence.frames,
        projected.observation.artifact.frames,
        strict=True,
    ):
        assert projected_frame.device_timestamp == source_frame.samples[0].source_timestamp
        assert [sample.value for sample in projected_frame.samples] == [
            sample.value for sample in source_frame.samples
        ]

    axes = source_case.report.reality_assessment.analysis.axes
    assert [sample.t for sample in projected.response_trace.samples] == list(axes[0].times)
    assert [sample.simulated[0] for sample in projected.response_trace.samples] == list(
        axes[0].simulation
    )


def test_intake_stays_open_until_case_device_condition_and_ood_coverage_exist() -> None:
    report = assess_real_holdout_intake(_request(cases=_complete_cases()[:1]))

    assert report.intake_status == "Open"
    assert report.counts_toward_reality is False
    assert report.real_holdout_set is None
    assert report.r5b_run_spec is None
    assert any(check.reason_code == "RealHoldoutCoverageIncomplete" for check in report.checks)


def test_intake_does_not_vacuously_pass_source_or_projection_checks_without_cases() -> None:
    report = assess_real_holdout_intake(_request(cases=()))

    assert report.intake_status == "Open"
    checks = {check.check_id: check for check in report.checks}
    assert checks["real-holdout-intake.field-reality"].status == "Open"
    assert checks["real-holdout-intake.field-reality"].reason_code == (
        "FieldEvidenceMissing"
    )
    assert checks["real-holdout-intake.r3-r4-projection"].status == "Open"
    assert checks["real-holdout-intake.r3-r4-projection"].reason_code == (
        "FieldEvidenceMissing"
    )


def test_intake_blocks_reused_field_report() -> None:
    cases = list(_complete_cases())
    duplicate = cases[0].model_copy(
        update={
            "role": "ood-probe",
            "task_id": "task-duplicate",
            "condition_id": "condition-duplicate",
            "batch_id": "batch-duplicate",
        }
    )
    report = assess_real_holdout_intake(_request(cases=(cases[0], cases[1], duplicate)))

    assert report.intake_status == "Blocked"
    assert report.real_holdout_set is None
    assert any(check.reason_code == "FieldEvidenceReportReused" for check in report.checks)


def test_intake_keeps_a_valid_open_field_gate_open() -> None:
    cases = list(_complete_cases())
    open_report = assess_field_evidence(
        FieldEvidenceAssessmentRequest.model_validate(_open_request())
    )
    cases[0] = cases[0].model_copy(update={"report": open_report})

    report = assess_real_holdout_intake(_request(cases=tuple(cases)))

    assert report.intake_status == "Open"
    assert report.real_holdout_set is None
    assert report.projected_cases[0].status == "Open"
    assert report.projected_cases[0].reason_code == "FieldEvidenceOpen"


def test_intake_blocks_lineage_that_does_not_bind_the_validation_command() -> None:
    cases = list(_complete_cases())
    invalid_lineage = cases[0].lineage.model_copy(
        update={"source_command_content_hash": "f" * 64}
    )
    cases[0] = cases[0].model_copy(update={"lineage": invalid_lineage})

    report = assess_real_holdout_intake(_request(cases=tuple(cases)))

    assert report.intake_status == "Blocked"
    assert report.real_holdout_set is None
    projection = next(
        check
        for check in report.checks
        if check.check_id == "real-holdout-intake.r3-r4-projection"
    )
    assert projection.reason_code == "R7EProjectionInvalid"


def test_intake_blocks_governance_attested_before_capture_completion() -> None:
    request = _request(cases=_complete_cases()).model_copy(
        update={
            "governance": _governance(
                datetime(2026, 8, 13, tzinfo=timezone.utc)
            )
        }
    )

    report = assess_real_holdout_intake(request)

    assert report.intake_status == "Blocked"
    assert report.real_holdout_set is None
    governance = next(
        check
        for check in report.checks
        if check.check_id == "real-holdout-intake.governance"
    )
    assert governance.reason_code == "GovernanceAttestationPrecedesCaptureCompletion"


def test_incomplete_intake_still_blocks_known_invalid_governance() -> None:
    request = _request(cases=_complete_cases()[:1]).model_copy(
        update={
            "governance": _governance(
                datetime(2026, 8, 13, tzinfo=timezone.utc)
            )
        }
    )

    report = assess_real_holdout_intake(request)

    assert report.intake_status == "Blocked"
    governance = next(
        check
        for check in report.checks
        if check.check_id == "real-holdout-intake.governance"
    )
    assert governance.status == "Blocked"
    assert governance.reason_code == "GovernanceAttestationPrecedesCaptureCompletion"


def test_intake_blocks_overlapping_capture_windows() -> None:
    cases = list(_complete_cases())
    cases[2] = _case(
        suffix="overlap",
        machine_id="machine-c",
        condition_id="condition-c",
        role="ood-probe",
        start=datetime(2026, 8, 14, 4, tzinfo=timezone.utc),
        shift=4,
    )

    report = assess_real_holdout_intake(_request(cases=tuple(cases)))

    assert report.intake_status == "Blocked"
    assert report.real_holdout_set is None
    output = next(
        check
        for check in report.checks
        if check.check_id == "real-holdout-intake.output"
    )
    assert output.reason_code == "RealHoldoutSetInvalid"


def test_intake_requires_selection_before_evaluation_and_real_alignment() -> None:
    payload = _request(cases=_complete_cases()).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    payload["selectedBeforeEvaluation"] = False
    with pytest.raises(ValidationError, match="selectedBeforeEvaluation"):
        RealHoldoutIntakeRequest.model_validate(payload)

    payload = _request(cases=_complete_cases()).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    alignment = deepcopy(payload["cases"][0]["coordinateAlignment"])
    alignment["sourceKind"] = "synthetic-reference"
    payload["cases"][0]["coordinateAlignment"] = alignment
    with pytest.raises(ValidationError, match="synthetic-reference"):
        RealHoldoutIntakeRequest.model_validate(payload)


def test_intake_cli_and_http_share_one_deterministic_report(
    tmp_path,
    capsys,
) -> None:
    request = _request(cases=_complete_cases())
    expected = assess_real_holdout_intake(request).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    request_path = tmp_path / "real-holdout-intake.json"
    request_path.write_text(
        request.model_dump_json(indent=2, by_alias=True, exclude_none=True),
        encoding="utf-8",
    )

    assert main(["real-holdout-intake", str(request_path)]) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    assert cli_payload == expected

    response = TestClient(create_app()).post(
        "/api/v1/intelligence/r5b/intake/assess",
        json=request.model_dump(mode="json", by_alias=True, exclude_none=True),
    )
    assert response.status_code == 200
    assert response.json() == expected


def test_intake_cli_rejects_malformed_input(tmp_path, capsys) -> None:
    request_path = tmp_path / "malformed-real-holdout-intake.json"
    request_path.write_text('{"schemaId":"wrong"}', encoding="utf-8")

    assert main(["real-holdout-intake", str(request_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["code"] == "MalformedRealHoldoutIntakeRequest"


def test_intake_cli_assembles_base_governance_and_case_files(tmp_path, capsys) -> None:
    request = _request(cases=_complete_cases())
    base_path = tmp_path / "base-r5b-run.json"
    governance_path = tmp_path / "governance.json"
    base_path.write_text(
        request.base_run_spec.model_dump_json(
            indent=2, by_alias=True, exclude_none=True
        ),
        encoding="utf-8",
    )
    governance_path.write_text(
        request.governance.model_dump_json(
            indent=2, by_alias=True, exclude_none=True
        ),
        encoding="utf-8",
    )
    case_paths = []
    for index, case in enumerate(request.cases):
        path = tmp_path / f"case-{index}.json"
        path.write_text(
            case.model_dump_json(indent=2, by_alias=True, exclude_none=True),
            encoding="utf-8",
        )
        case_paths.append(path)

    argv = [
        "real-holdout-intake",
        "--base-run-spec",
        str(base_path),
        "--governance",
        str(governance_path),
    ]
    for path in case_paths:
        argv.extend(("--case", str(path)))

    assert main(argv) == 0
    actual = json.loads(capsys.readouterr().out)
    expected = assess_real_holdout_intake(request).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    assert actual == expected


def test_intake_cli_rejects_incomplete_multi_file_input(capsys) -> None:
    assert main(["real-holdout-intake"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "IncompleteRealHoldoutIntakeInput"
