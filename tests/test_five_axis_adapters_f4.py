from __future__ import annotations

import pytest

import axiom.five_axis.f4_adapters as adapters_module
from axiom.five_axis.f3_sampling import M5DiscreteCommand, POLYNOMIAL_POLICY_ID, verify_interval_reconstruction
from axiom.five_axis.f3_scenarios import load_f3_scenario
from axiom.five_axis.f4_adapters import (
    FROZEN_COEFFICIENT_GAP_TOLERANCE,
    FROZEN_CROSS_VALIDATION_TOLERANCES,
    REFERENCE_ADAPTER_DESCRIPTOR,
    SUT_ADAPTER_DESCRIPTOR,
    build_adapter_invocation,
    cross_validate_discrete_commands,
    execute_adapter,
)


def _scenario_m4():
    return load_f3_scenario("canonical-table-table-jerk").continuousTrajectory


def _max_sample_gap(reference: M5DiscreteCommand, sut: M5DiscreteCommand, field_name: str) -> float:
    return max(
        max(abs(a - b) for a, b in zip(getattr(left, field_name), getattr(right, field_name), strict=True))
        for left, right in zip(reference.samples, sut.samples, strict=True)
    )


def _max_coefficient_gap(reference: M5DiscreteCommand, sut: M5DiscreteCommand) -> float:
    return max(
        abs(left_value - right_value)
        for left_interval, right_interval in zip(reference.intervals, sut.intervals, strict=True)
        for left_row, right_row in zip(left_interval.certificate_coefficients, right_interval.certificate_coefficients, strict=True)
        for left_value, right_value in zip(left_row, right_row, strict=True)
    )


def test_reference_and_sut_paths_both_produce_supported_commands_within_frozen_tolerances() -> None:
    m4 = _scenario_m4()
    reference_invocation = build_adapter_invocation(
        REFERENCE_ADAPTER_DESCRIPTOR,
        m4,
        sample_period=0.08,
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=False,
    )
    sut_invocation = build_adapter_invocation(
        SUT_ADAPTER_DESCRIPTOR,
        m4,
        sample_period=0.08,
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=False,
    )

    reference_receipt, reference_command = execute_adapter(reference_invocation, m4)
    sut_receipt, sut_command = execute_adapter(sut_invocation, m4)

    assert reference_receipt.status == "Succeeded"
    assert sut_receipt.status == "Succeeded"
    assert isinstance(reference_command, M5DiscreteCommand)
    assert isinstance(sut_command, M5DiscreteCommand)
    assert reference_command.discrete_command_id != sut_command.discrete_command_id
    assert reference_command.content_id != sut_command.content_id

    reference_verification = verify_interval_reconstruction(reference_command)
    sut_verification = verify_interval_reconstruction(sut_command)
    assert reference_verification.status == "Supported"
    assert reference_verification.evidence_level == "Certified"
    assert sut_verification.status == "Supported"
    assert sut_verification.evidence_level == "Certified"

    cross_validation = cross_validate_discrete_commands(reference_command, sut_command)
    tolerance_by_target = {item.target: item.tolerance.absolute for item in FROZEN_CROSS_VALIDATION_TOLERANCES}

    assert cross_validation.status == "Supported"
    assert cross_validation.evidence_level == "Validated"
    assert cross_validation.max_position_gap <= tolerance_by_target["position"]
    assert cross_validation.max_velocity_gap <= tolerance_by_target["velocity"]
    assert cross_validation.max_acceleration_gap <= tolerance_by_target["acceleration"]
    assert cross_validation.max_jerk_gap <= tolerance_by_target["jerk"]
    assert _max_sample_gap(reference_command, sut_command, "q") <= tolerance_by_target["position"]
    assert _max_sample_gap(reference_command, sut_command, "qdot") <= tolerance_by_target["velocity"]
    assert _max_sample_gap(reference_command, sut_command, "qddot") <= tolerance_by_target["acceleration"]
    assert _max_sample_gap(reference_command, sut_command, "qjerk") <= tolerance_by_target["jerk"]
    assert _max_coefficient_gap(reference_command, sut_command) <= FROZEN_COEFFICIENT_GAP_TOLERANCE


def test_sut_path_does_not_depend_on_reference_sampler(monkeypatch: pytest.MonkeyPatch) -> None:
    m4 = _scenario_m4()
    invocation = build_adapter_invocation(
        SUT_ADAPTER_DESCRIPTOR,
        m4,
        sample_period=0.25,
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=False,
    )

    def explode(*args, **kwargs):
        raise RuntimeError("reference sampler should not run")

    monkeypatch.setattr(adapters_module, "sample_continuous_trajectory", explode)
    receipt, command = execute_adapter(invocation, m4)

    assert receipt.status == "Succeeded"
    assert isinstance(command, M5DiscreteCommand)


def test_cross_validation_measures_solver_equivalence_independently_of_limit_certification() -> None:
    m4 = _scenario_m4()
    commands = []
    for descriptor in (REFERENCE_ADAPTER_DESCRIPTOR, SUT_ADAPTER_DESCRIPTOR):
        invocation = build_adapter_invocation(
            descriptor,
            m4,
            sample_period=0.25,
            policy=POLYNOMIAL_POLICY_ID,
            final_hold=False,
        )
        receipt, command = execute_adapter(invocation, m4)
        assert receipt.status == "Succeeded"
        assert isinstance(command, M5DiscreteCommand)
        commands.append(command)

    assert verify_interval_reconstruction(commands[0]).status == "Unsupported"
    assert verify_interval_reconstruction(commands[1]).status == "Unsupported"
    assert cross_validate_discrete_commands(commands[0], commands[1]).status == "Supported"


def test_unknown_adapter_and_identity_mismatch_are_structurally_unsupported() -> None:
    m4 = _scenario_m4()
    unknown_invocation = build_adapter_invocation(
        REFERENCE_ADAPTER_DESCRIPTOR.model_copy(update={"adapter_id": "five-axis.f4.unknown-adapter"}),
        m4,
        sample_period=0.25,
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=False,
    )
    mismatch_invocation = build_adapter_invocation(
        REFERENCE_ADAPTER_DESCRIPTOR.model_copy(update={"subject_id": "five-axis.wrong-subject"}),
        m4,
        sample_period=0.25,
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=False,
    )

    unknown_receipt, unknown_command = execute_adapter(unknown_invocation, m4)
    mismatch_receipt, mismatch_command = execute_adapter(mismatch_invocation, m4)

    assert unknown_command is None
    assert unknown_receipt.status == "Unsupported"
    assert unknown_receipt.failure_code == "AdapterNotRegistered"
    assert mismatch_command is None
    assert mismatch_receipt.status == "Unsupported"
    assert mismatch_receipt.failure_code == "AdapterIdentityMismatch"


def test_non_polynomial_policy_is_structurally_unsupported() -> None:
    m4 = _scenario_m4()
    invocation = build_adapter_invocation(
        REFERENCE_ADAPTER_DESCRIPTOR,
        m4,
        sample_period=0.25,
        policy="five-axis.reconstruction.foh@1",
        final_hold=False,
    )

    receipt, command = execute_adapter(invocation, m4)

    assert command is None
    assert receipt.status == "Unsupported"
    assert receipt.failure_code == "UnsupportedPolicy"


def test_tampered_input_hash_fails_without_fake_success() -> None:
    m4 = _scenario_m4()
    invocation = build_adapter_invocation(
        REFERENCE_ADAPTER_DESCRIPTOR,
        m4,
        sample_period=0.25,
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=False,
    ).model_copy(update={"input_m4_content_hash": "b" * 64})

    receipt, command = execute_adapter(invocation, m4)

    assert command is None
    assert receipt.status == "Failed"
    assert receipt.failure_code == "InputContentHashMismatch"
    assert receipt.output_content_hash is None


def test_execution_failure_returns_failed_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    m4 = _scenario_m4()
    invocation = build_adapter_invocation(
        SUT_ADAPTER_DESCRIPTOR,
        m4,
        sample_period=0.25,
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=False,
    )

    def explode(*args, **kwargs):
        raise RuntimeError("synthetic sut failure")

    monkeypatch.setitem(
        adapters_module._ADAPTER_REGISTRY,
        adapters_module.SUT_ADAPTER_DESCRIPTOR.adapter_id,
        adapters_module._RegisteredAdapter(
            descriptor=adapters_module.SUT_ADAPTER_DESCRIPTOR,
            builder=explode,
        ),
    )
    receipt, command = execute_adapter(invocation, m4)

    assert command is None
    assert receipt.status == "Failed"
    assert receipt.failure_code == "AdapterExecutionFailed"
    assert receipt.output_content_hash is None
