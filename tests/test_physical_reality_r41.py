from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from axiom.physical import (
    FIVE_AXIS_REALITY_DOMAIN_PACK_ID,
    R41_DEFAULT_SCENARIO_ID,
    PhysicalRealityEvidencePair,
    assess_r41_reality,
    build_r41_manifest,
    exact_zoh_response,
    list_r41_scenarios,
    r41_example_payload,
    validate_r41_example_run_spec,
)
from axiom.run import evaluate_run


def _reality_pair_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    validation_source_kind: str = "controller-live-read",
    reuse_evidence: bool = False,
    validation_case_id: str = "five-axis.r4.1.case@1",
    validation_captured_at: str = "2026-08-13T09:00:00+00:00",
    validation_sample_period: float = 0.1,
) -> tuple[PhysicalRealityEvidencePair, PhysicalRealityEvidencePair]:
    times = tuple(index / 10 for index in range(10))
    calibration_commands = tuple(
        tuple((index % 4) * (axis + 1) / 10 for index in range(10))
        for axis in range(5)
    )
    validation_commands = tuple(
        tuple(((index * 3 + axis) % 5) * (axis + 1) / 12 for index in range(10))
        for axis in range(5)
    )
    biases = (0.02, -0.01, 0.03, 0.002, -0.003)
    sealed_audit = SimpleNamespace(deployment_shadow_status="Passed")

    def request(
        command_hash: str,
        evidence_hash: str,
        authorization_hash: str,
        captured_at: str,
        commands: tuple[tuple[float, ...], ...],
        *,
        source_kind: str,
        case_id: str,
        sample_period: float = 0.1,
    ) -> SimpleNamespace:
        captured = datetime.fromisoformat(captured_at)
        command = SimpleNamespace(
            content_id=command_hash,
            sample_period=sample_period,
            samples=tuple(
                SimpleNamespace(
                    sample_index=index,
                    t=times[index],
                    q=tuple(axis[index] for axis in commands),
                )
                for index in range(len(times))
            ),
        )
        observations = tuple(
            exact_zoh_response(
                commands[axis],
                times,
                time_constant_seconds=0.1,
                bias=biases[axis],
            )
            for axis in range(5)
        )
        evidence = SimpleNamespace(
            content_hash=evidence_hash,
            capture_authorization_content_hash=authorization_hash,
            captured_at=captured_at,
            source_kind=source_kind,
            declared_real=source_kind == "controller-live-read",
            frames=tuple(
                SimpleNamespace(
                    samples=tuple(
                        SimpleNamespace(value=observations[axis][index])
                        for axis in range(5)
                    )
                )
                for index in range(len(times))
            ),
        )
        return SimpleNamespace(
            artifact=sealed_audit,
            vendor_profile=SimpleNamespace(),
            runtime_evidence=SimpleNamespace(),
            witness_profile=SimpleNamespace(),
            controller_profile=SimpleNamespace(
                content_hash="f" * 64,
                machine_id="beckhoff-five-axis-01",
                controller_family="TwinCAT 3",
            ),
            authority=SimpleNamespace(),
            capture_authorization=SimpleNamespace(
                content_hash=authorization_hash,
                authorized_from=(captured - timedelta(minutes=1)).isoformat(),
                authorized_until=(captured + timedelta(minutes=1)).isoformat(),
            ),
            command=command,
            shadow_evidence=evidence,
            case=SimpleNamespace(case_id=case_id),
        )

    calibration_request = request(
        "1" * 64,
        "2" * 64,
        "3" * 64,
        "2026-08-13T08:00:00+00:00",
        calibration_commands,
        source_kind="controller-live-read",
        case_id="five-axis.r4.1.case@1",
    )
    validation_request = request(
        "4" * 64,
        "2" * 64 if reuse_evidence else "5" * 64,
        "3" * 64 if reuse_evidence else "6" * 64,
        (
            "2026-08-13T08:00:00+00:00"
            if reuse_evidence
            else validation_captured_at
        ),
        validation_commands,
        source_kind=validation_source_kind,
        case_id=validation_case_id,
        sample_period=validation_sample_period,
    )
    requests = {
        "reality.calibration@1": calibration_request,
        "reality.validation@1": validation_request,
    }
    monkeypatch.setattr(
        PhysicalRealityEvidencePair,
        "parsed_r7e_request",
        lambda self: requests[self.pair_id],
    )
    monkeypatch.setattr(
        "axiom.control.r7e_scenarios.assess_r7e_shadow",
        lambda *_args: sealed_audit,
    )
    calibration = PhysicalRealityEvidencePair.model_construct(
        pair_id="reality.calibration@1",
        role="calibration",
        r7e_request={},
        command_content_hash="1" * 64,
        shadow_evidence_content_hash="2" * 64,
        pair_content_hash="7" * 64,
    )
    validation = PhysicalRealityEvidencePair.model_construct(
        pair_id="reality.validation@1",
        role="validation",
        r7e_request={},
        command_content_hash="4" * 64,
        shadow_evidence_content_hash="2" * 64 if reuse_evidence else "5" * 64,
        pair_content_hash="8" * 64,
    )
    return calibration, validation


def test_r41_manifest_freezes_two_run_windows_reality_protocol() -> None:
    manifest = build_r41_manifest()

    assert manifest.domain_pack_id == FIVE_AXIS_REALITY_DOMAIN_PACK_ID
    assert manifest.supported_platforms == ("Windows",)
    assert manifest.required_independent_runs == 2
    assert manifest.calibration_role == "calibration"
    assert manifest.validation_role == "validation"
    assert manifest.interpolation_allowed is False
    assert manifest.reality_validation_status == "Open"
    assert manifest.device_safety_status == "NotAssessed"


def test_r41_default_payload_does_not_bundle_fake_real_pairs() -> None:
    payload = r41_example_payload()

    assert payload.scenario.scenario_id == R41_DEFAULT_SCENARIO_ID
    assert payload.calibration_pair is None
    assert payload.validation_pair is None
    assert payload.analysis.reality_validation_status == "Open"
    assert payload.analysis.counts_toward_reality is False


def test_r41_default_run_is_inconclusive_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.physical import reality_runtime

    monkeypatch.setattr(reality_runtime.platform, "system", lambda: "Windows")

    bundle = evaluate_run(validate_r41_example_run_spec())

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Inconclusive"
    contract = next(
        result
        for result in bundle.report.metric_results
        if result.metric_id == "five-axis.physical.reality-contract-valid@1"
    )
    assert contract.evidence is not None
    assert contract.evidence.level == "Validated"
    assert contract.evidence.method.endswith(".typed-contract-check@1")
    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}
    assert claims["five-axis.physical-reality-contract-claim@1"] == "Supported"
    assert claims["five-axis.physical-model-reality-validated-claim@2"] == "Inconclusive"


def test_r41_non_windows_runtime_is_structured_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.physical import reality_runtime

    monkeypatch.setattr(reality_runtime.platform, "system", lambda: "Linux")

    bundle = evaluate_run(validate_r41_example_run_spec())

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Unsupported"
    assert all(
        result.reason_code == "UnsupportedRuntimePlatform"
        for result in bundle.report.metric_results
    )


def test_r41_public_catalog_contains_no_real_or_safety_claim_fixture() -> None:
    serialized = json.dumps(
        r41_example_payload().model_dump(mode="json", by_alias=True), sort_keys=True
    )
    scenarios = list_r41_scenarios()

    assert scenarios
    assert all(scenario.counts_toward_reality is False for scenario in scenarios)
    assert "controller-live-read" not in serialized
    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized


def test_r41_disjoint_real_stubs_exercise_calibration_and_holdout_math(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, validation = _reality_pair_stubs(monkeypatch)

    analysis = assess_r41_reality(calibration, validation)

    assert analysis.reality_validation_status == "Passed"
    assert analysis.counts_toward_reality is True
    assert analysis.model is not None
    assert analysis.model.schema_id == "five-axis.physical-model-definition@2"
    assert analysis.model.applicability.case_id == "five-axis.r4.1.case@1"
    assert len(analysis.axes) == 5
    assert analysis.linear_improvement_ratio is not None
    assert analysis.linear_improvement_ratio > 0.2
    assert analysis.rotary_improvement_ratio is not None
    assert analysis.rotary_improvement_ratio > 0.2
    assert analysis.device_safety_status == "NotAssessed"
    assert analysis.process_safety_status == "NotAssessed"


def test_r41_reused_calibration_evidence_blocks_holdout_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, validation = _reality_pair_stubs(
        monkeypatch, reuse_evidence=True
    )

    analysis = assess_r41_reality(calibration, validation)

    assert analysis.reality_validation_status == "Blocked"
    assert analysis.counts_toward_reality is False
    assert analysis.checks[1].reason_code == "CalibrationValidationLeakage"
    assert analysis.model is None


def test_r41_contract_fixture_cannot_be_promoted_to_reality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, validation = _reality_pair_stubs(
        monkeypatch, validation_source_kind="contract-fixture"
    )

    analysis = assess_r41_reality(calibration, validation)

    assert analysis.reality_validation_status == "Blocked"
    assert analysis.counts_toward_reality is False
    assert analysis.checks[2].reason_code == (
        "R7EDeploymentEvidenceInvalidOrDifferentDevice"
    )


def test_r41_validation_must_follow_calibration_in_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, validation = _reality_pair_stubs(
        monkeypatch,
        validation_captured_at="2026-08-13T07:00:00+00:00",
    )

    analysis = assess_r41_reality(calibration, validation)

    assert analysis.reality_validation_status == "Blocked"
    assert analysis.checks[1].reason_code == "CalibrationValidationLeakage"


def test_r41_validation_must_stay_in_the_calibration_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, validation = _reality_pair_stubs(
        monkeypatch,
        validation_case_id="five-axis.r4.1.other-case@1",
    )

    analysis = assess_r41_reality(calibration, validation)

    assert analysis.reality_validation_status == "Blocked"
    assert analysis.checks[2].reason_code == (
        "R7EDeploymentEvidenceInvalidOrDifferentDevice"
    )


def test_r41_validation_rejects_sample_period_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, validation = _reality_pair_stubs(
        monkeypatch,
        validation_sample_period=0.2,
    )

    analysis = assess_r41_reality(calibration, validation)

    assert analysis.reality_validation_status == "Blocked"
    assert analysis.checks[3].reason_code == "SamplePeriodMismatch"
