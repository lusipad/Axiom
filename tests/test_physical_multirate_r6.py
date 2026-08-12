from __future__ import annotations

import pytest

from axiom.five_axis.f3_sampling import POLYNOMIAL_POLICY_ID
from axiom.five_axis.f4_adapters import (
    SUT_ADAPTER_DESCRIPTOR,
    build_adapter_invocation,
    execute_adapter,
)
from axiom.five_axis.f4_scenarios import load_f4_scenario
from axiom.physical import load_r4_scenario
from axiom.physical.applicability import (
    build_r4_multirate_applicability_evidence,
    build_r4_multirate_physical_model,
    require_physical_model_sample_period,
)
from axiom.physical.simulation import simulate_physical_response


def test_r4_multirate_evidence_covers_both_r6_sample_period_endpoints() -> None:
    evidence = build_r4_multirate_applicability_evidence()

    assert evidence.status == "Passed"
    assert evidence.reality_validation_status == "Open"
    assert evidence.supported_period_min_seconds == 0.04
    assert evidence.supported_period_max_seconds == 0.08
    assert [point.sample_period_seconds for point in evidence.endpoint_evaluations] == [
        0.04,
        0.08,
    ]
    assert all(
        point.passed and point.improvement_ratio >= 0.35
        for point in evidence.endpoint_evaluations
    )


def test_r4_multirate_model_expands_only_the_evidence_backed_period_range() -> None:
    base = load_r4_scenario("in-domain-synthetic-sil").physicalModel
    expanded = build_r4_multirate_physical_model()

    with pytest.raises(ValueError, match="outside physical model applicability"):
        require_physical_model_sample_period(base, 0.04)

    require_physical_model_sample_period(expanded, 0.04)
    require_physical_model_sample_period(expanded, 0.08)
    with pytest.raises(ValueError, match="outside physical model applicability"):
        require_physical_model_sample_period(expanded, 0.02)


def test_physical_simulation_rejects_a_computable_but_out_of_applicability_period() -> (
    None
):
    base = load_r4_scenario("in-domain-synthetic-sil").physicalModel
    source = load_f4_scenario("canonical-head-table-solver").continuousTrajectory
    invocation = build_adapter_invocation(
        SUT_ADAPTER_DESCRIPTOR,
        source,
        sample_period=0.04,
        policy=POLYNOMIAL_POLICY_ID,
        final_hold=False,
    )
    receipt, command = execute_adapter(invocation, source)
    assert receipt.status == "Succeeded" and command is not None

    with pytest.raises(ValueError, match="outside physical model applicability"):
        simulate_physical_response(
            base, command, response_trace_id="five-axis.r4.out-of-domain@1"
        )


def test_r4_multirate_evidence_is_deterministic() -> None:
    first = build_r4_multirate_applicability_evidence()
    second = build_r4_multirate_applicability_evidence()

    assert first == second
    assert first.content_hash == "d78e739986212d3574fc7caef4299961f0f6b73afb1417f84b1460f984e0facc"
