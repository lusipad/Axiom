from __future__ import annotations

import copy

import axiom.five_axis.f3_runtime as f3_runtime_module
from axiom.five_axis.f3_runtime import (
    CONTINUOUSLY_FEASIBLE_CLAIM_ID,
    CONTINUOUSLY_FEASIBLE_METRIC_ID,
    FIVE_AXIS_F3_DOMAIN_PACK,
    FIVE_AXIS_F3_DOMAIN_PACK_ID,
    FIVE_AXIS_F3_RUNTIME_BINDING,
    INTERVAL_CERTIFIED_CLAIM_ID,
    INTERVAL_CERTIFIED_METRIC_ID,
)
from axiom.five_axis.f3_scenarios import (
    load_f3_scenario,
    validate_f3_example_run_spec,
)
from axiom.models import ClaimStatus, MetricStatus
from axiom.run import evaluate_run, validate_run_bundle_integrity
from axiom.runtime import get_domain_runtime_binding


def _claims(bundle) -> dict[str, ClaimStatus]:
    return {claim.claim_definition_id: claim.status for claim in bundle.claims}


def test_f3_domain_pack_is_bound_without_core_special_case() -> None:
    assert get_domain_runtime_binding(FIVE_AXIS_F3_DOMAIN_PACK_ID) is FIVE_AXIS_F3_RUNTIME_BINDING
    assert FIVE_AXIS_F3_DOMAIN_PACK.domain_pack_id == FIVE_AXIS_F3_DOMAIN_PACK_ID
    assert {
        descriptor.artifact_type
        for descriptor in FIVE_AXIS_F3_DOMAIN_PACK.artifact_type_descriptors
    } == {
        "five-axis.m4-continuous-trajectory",
        "five-axis.m5-sampled-trajectory",
        "five-axis.m5-discrete-command",
    }


def test_canonical_jerk_run_supports_only_the_two_f3_claims() -> None:
    bundle = evaluate_run(validate_f3_example_run_spec("canonical-table-table-jerk"))

    assert validate_run_bundle_integrity(bundle) == []
    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Passed"
    claims = _claims(bundle)
    assert claims[CONTINUOUSLY_FEASIBLE_CLAIM_ID] is ClaimStatus.SUPPORTED
    assert claims[INTERVAL_CERTIFIED_CLAIM_ID] is ClaimStatus.SUPPORTED
    assert not {
        "five-axis.model-collision-free-claim@1",
        "five-axis.device-safe-claim@1",
        "five-axis.process-safe-claim@1",
    }.intersection(claims)


def test_second_order_scenario_proves_continuous_optimality_but_not_foh_closure() -> None:
    scenario = load_f3_scenario("second-order-proven-optimal")
    bundle = evaluate_run(validate_f3_example_run_spec("second-order-proven-optimal"))

    assert scenario.continuousTrajectory.verification.optimality.classification == "ProvenOptimal"
    assert scenario.continuousTrajectory.verification.optimality.proof_gap_seconds == 0.0
    assert bundle.metric_result(CONTINUOUSLY_FEASIBLE_METRIC_ID).value is True
    interval = bundle.metric_result(INTERVAL_CERTIFIED_METRIC_ID)
    assert interval.status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert interval.reason_code == "FullDerivativeClosureUnsupportedByPolicy"
    assert _claims(bundle)[INTERVAL_CERTIFIED_CLAIM_ID] is ClaimStatus.INCONCLUSIVE


def test_zoh_moving_command_stays_inconclusive_for_interval_claim() -> None:
    bundle = evaluate_run(validate_f3_example_run_spec("zoh-moving-unsupported"))

    interval = bundle.metric_result(INTERVAL_CERTIFIED_METRIC_ID)
    assert interval.status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert interval.reason_code == "FullDerivativeClosureUnsupportedByPolicy"
    assert _claims(bundle)[CONTINUOUSLY_FEASIBLE_CLAIM_ID] is ClaimStatus.SUPPORTED
    assert _claims(bundle)[INTERVAL_CERTIFIED_CLAIM_ID] is ClaimStatus.INCONCLUSIVE


def test_polynomial_counterexample_refutes_an_interior_limit_violation() -> None:
    scenario = load_f3_scenario("polynomial-interior-violation")
    assert scenario.sampledTrajectory is not None
    assert all(sample.qdot == (0.0, 0.0, 0.0, 0.0, 0.0) for sample in scenario.sampledTrajectory.samples)

    bundle = evaluate_run(validate_f3_example_run_spec("polynomial-interior-violation"))

    interval = bundle.metric_result(INTERVAL_CERTIFIED_METRIC_ID)
    assert interval.status is MetricStatus.COMPUTED
    assert interval.value is False
    assert interval.reason_code == "DeclaredCapabilityRefuted"
    verification = interval.details["reconstructionVerification"]
    velocity = next(item for item in verification["quantities"] if item["quantity"] == "velocity")
    assert velocity["status"] == "Refuted"
    assert any(
        item.get("reasonCode") == "IntervalInteriorLimitExceeded"
        for item in velocity["axisResults"]
    )
    assert _claims(bundle)[INTERVAL_CERTIFIED_CLAIM_ID] is ClaimStatus.REFUTED


def test_f3_run_bundle_is_deterministic() -> None:
    spec = validate_f3_example_run_spec("canonical-head-head-jerk")

    first = evaluate_run(spec)
    second = evaluate_run(copy.deepcopy(spec))

    assert first.model_dump(mode="json", by_alias=True, exclude_none=True) == second.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    assert first.bundle_hash


def test_f3_runtime_replays_each_verifier_at_most_once_per_evaluation(monkeypatch) -> None:
    counts = {"continuous": 0, "reconstruction": 0}
    original_continuous = f3_runtime_module.verify_continuous_trajectory
    original_reconstruction = f3_runtime_module.verify_interval_reconstruction

    def counted_continuous(*args, **kwargs):
        counts["continuous"] += 1
        return original_continuous(*args, **kwargs)

    def counted_reconstruction(*args, **kwargs):
        counts["reconstruction"] += 1
        return original_reconstruction(*args, **kwargs)

    monkeypatch.setattr(f3_runtime_module, "verify_continuous_trajectory", counted_continuous)
    monkeypatch.setattr(f3_runtime_module, "verify_interval_reconstruction", counted_reconstruction)

    bundle = evaluate_run(validate_f3_example_run_spec("canonical-table-table-jerk"))

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Passed"
    assert counts == {"continuous": 1, "reconstruction": 1}
