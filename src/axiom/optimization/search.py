from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..five_axis.f3_sampling import POLYNOMIAL_POLICY_ID, verify_interval_reconstruction
from ..five_axis.f3_timing import (
    plan_jerk_feasible_time_law,
    verify_continuous_trajectory,
)
from ..five_axis.f4_adapters import (
    SUT_ADAPTER_DESCRIPTOR,
    build_adapter_invocation,
    execute_adapter,
)
from ..five_axis.f4_collision import verify_m5_configuration_collision
from ..five_axis.f4_scenarios import load_f4_scenario
from ..intelligence.interpreter import pure_python_predict_observation
from ..intelligence.models import IntelligenceSample
from ..intelligence.scenarios import load_r5_scenario
from ..models import ParameterSet
from ..physical import (
    build_r4_multirate_applicability_evidence,
    build_r4_multirate_physical_model,
    require_physical_model_sample_period,
    simulate_physical_response,
)
from .models import (
    R6_GATE_IDS,
    OptimizationCandidate,
    OptimizationSearchRequest,
    OptimizationValidationPlan,
    RecommendationSet,
    canonical_hash,
)


def _feed_code(feed_override: float) -> str:
    return f"{round(feed_override * 100):03d}"


def _period_code(sample_period: float) -> str:
    return f"{round(sample_period * 1000):03d}ms"


def _parameter_set(feed_override: float, sample_period: float) -> ParameterSet:
    return ParameterSet(
        parameterSetId=f"optimization.r6.feed-{_feed_code(feed_override)}.period-{_period_code(sample_period)}@1",
        parameterSchemaId="optimization.r6.feed-and-sampling@1",
        schemaVersion=1,
        values={"feedOverride": feed_override, "samplePeriod": sample_period},
        units={"feedOverride": "ratio", "samplePeriod": "s"},
    )


def _derated_motion_profile(base, feed_override: float):
    axis_constraints = tuple(
        constraint.model_copy(
            update={
                "maximum_velocity": constraint.maximum_velocity * feed_override,
                "maximum_acceleration": constraint.maximum_acceleration
                * feed_override**2,
                "maximum_jerk": (
                    constraint.maximum_jerk * feed_override**3
                    if constraint.maximum_jerk is not None
                    else None
                ),
            }
        )
        for constraint in base.axis_constraints
    )
    return base.model_copy(
        update={
            "profile_id": f"five-axis.r6.motion-profile.feed-{_feed_code(feed_override)}@1",
            "axis_constraints": axis_constraints,
            "maximum_path_velocity": (
                base.maximum_path_velocity * feed_override
                if base.maximum_path_velocity is not None
                else None
            ),
            "feed_source": "optimization.r6.feed-override-derating@1",
        }
    )


def _goal_feasible(
    request: OptimizationSearchRequest, objectives: dict[str, Any]
) -> bool:
    goal = request.goal
    return (
        (
            goal.maximum_cycle_time_seconds is None
            or objectives["cycleTimeSeconds"] <= goal.maximum_cycle_time_seconds
        )
        and (
            goal.maximum_linear_following_error_mm is None
            or objectives["linearFollowingErrorMaxMm"]
            <= goal.maximum_linear_following_error_mm
        )
        and (
            goal.maximum_command_sample_count is None
            or objectives["commandSampleCount"] <= goal.maximum_command_sample_count
        )
    )


def _ood_fraction(model_bundle, command, response) -> float:
    abstentions = 0
    duration = max(float(command.samples[-1].t), 1e-12)
    for index, (command_sample, response_sample) in enumerate(
        zip(command.samples, response.samples, strict=True)
    ):
        sample = IntelligenceSample(
            sampleId=f"optimization-r6-{command.content_id[:12]}-{index}",
            axisId="X",
            topology="head-table",
            trajectoryFamily="five-axis.canonical-f4",
            taskId="optimization-r6-offline",
            deviceBatchId="synthetic-sil-r4",
            pairId=f"optimization-r6-{command.content_id[:16]}",
            declaredSplitId="test",
            scenarioRole="in-domain",
            upstreamScenarioId="canonical-head-table-solver",
            sourceCommandContentId=command.content_id,
            sourceCommandSampleId=f"sample-{index}",
            labelDerivationId="optimization.r6.synthetic-r4-label@1",
            eventTime="2026-08-12T00:00:00+00:00",
            t=float(command_sample.t) / duration,
            command=float(command_sample.q[0]),
            simulation=float(response_sample.simulated[0]),
            observation=float(response_sample.simulated[0]),
        )
        abstained, _ = pure_python_predict_observation(model_bundle, sample)
        abstentions += int(abstained)
    return abstentions / len(command.samples)


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_values = (
        left["objectives"]["cycleTimeSeconds"],
        left["objectives"]["linearFollowingErrorMaxMm"],
        left["objectives"]["commandSampleCount"],
    )
    right_values = (
        right["objectives"]["cycleTimeSeconds"],
        right["objectives"]["linearFollowingErrorMaxMm"],
        right["objectives"]["commandSampleCount"],
    )
    return all(a <= b for a, b in zip(left_values, right_values, strict=True)) and any(
        a < b for a, b in zip(left_values, right_values, strict=True)
    )


def _gate_claim_status(status: str) -> str:
    if status in {"Supported", "safe"}:
        return "Supported"
    if status in {"Refuted", "collision"}:
        return "Refuted"
    if status in {
        "Inconclusive",
        "Unsupported",
        "Insufficient",
        "unsupported",
        "unresolved",
    }:
        return "Inconclusive"
    raise ValueError(f"unsupported R6 gate status: {status}")


def _candidate_sort_key(
    candidate: dict[str, Any],
) -> tuple[float, float, int, float, float]:
    values = candidate["parameterSet"]["values"]
    objectives = candidate["objectives"]
    return (
        objectives["cycleTimeSeconds"],
        objectives["linearFollowingErrorMaxMm"],
        objectives["commandSampleCount"],
        values["feedOverride"],
        values["samplePeriod"],
    )


def search_recommendations(
    request: OptimizationSearchRequest | None = None,
) -> RecommendationSet:
    request = request or OptimizationSearchRequest()
    upstream = load_f4_scenario("canonical-head-table-solver")
    physical_model = build_r4_multirate_physical_model()
    applicability_evidence = build_r4_multirate_applicability_evidence()
    intelligence_bundle = load_r5_scenario().model_bundle
    upstream_gates = {
        item.claim_id: item
        for item in upstream.stageAcceptanceReport.gate_claim_statuses
    }
    candidates: list[dict[str, Any]] = []

    for feed_override in request.grid.feed_overrides:
        profile = _derated_motion_profile(
            upstream.motionConstraintProfile, feed_override
        )
        m4 = plan_jerk_feasible_time_law(
            upstream.axisPath,
            profile,
            trajectory_id=f"five-axis.r6.m4.feed-{_feed_code(feed_override)}-v1",
        )
        m4_verification = verify_continuous_trajectory(m4)
        for sample_period in request.grid.sample_periods:
            require_physical_model_sample_period(physical_model, sample_period)
            invocation = build_adapter_invocation(
                SUT_ADAPTER_DESCRIPTOR,
                m4,
                sample_period=sample_period,
                policy=POLYNOMIAL_POLICY_ID,
                final_hold=False,
                invocation_id=(
                    f"optimization.r6.feed-{_feed_code(feed_override)}.period-{_period_code(sample_period)}.invoke"
                ),
            )
            receipt, command = execute_adapter(invocation, m4)
            if receipt.status != "Succeeded" or command is None:
                raise ValueError(f"R6 adapter failed: {receipt.failure_code}")
            interval_verification = verify_interval_reconstruction(command)
            collision_verification = verify_m5_configuration_collision(
                command,
                collision_model=upstream.collisionModel,
            )
            response = simulate_physical_response(
                physical_model,
                command,
                response_trace_id=(
                    f"optimization.r6.feed-{_feed_code(feed_override)}.period-{_period_code(sample_period)}.response@1"
                ),
            )
            linear_error = max(
                abs(float(sample.command[axis]) - float(sample.simulated[axis]))
                for sample in response.samples
                for axis in range(3)
            )
            objectives = {
                "cycleTimeSeconds": m4_verification.total_duration_seconds,
                "linearFollowingErrorMaxMm": linear_error,
                "commandSampleCount": len(command.samples),
            }
            gate_statuses = {
                claim_id: _gate_claim_status(upstream_gates[claim_id].status)
                for claim_id in R6_GATE_IDS[:4]
            }
            gate_statuses[R6_GATE_IDS[4]] = _gate_claim_status(
                m4_verification.overall_status
            )
            gate_statuses[R6_GATE_IDS[5]] = _gate_claim_status(
                interval_verification.status
            )
            gate_statuses[R6_GATE_IDS[6]] = _gate_claim_status(
                collision_verification.status
            )
            evidence_by_gate = {
                claim_id: canonical_hash(upstream_gates[claim_id])
                for claim_id in R6_GATE_IDS[:4]
            }
            evidence_by_gate[R6_GATE_IDS[4]] = canonical_hash(m4_verification)
            evidence_by_gate[R6_GATE_IDS[5]] = canonical_hash(interval_verification)
            evidence_by_gate[R6_GATE_IDS[6]] = canonical_hash(collision_verification)
            gate_receipts = [
                {
                    "claimId": claim_id,
                    "status": gate_statuses[claim_id],
                    "evidenceContentHash": evidence_by_gate[claim_id],
                    "method": "optimization.r6.inherited-f4-gate@1"
                    if index < 4
                    else "optimization.r6.replay@1",
                }
                for index, claim_id in enumerate(R6_GATE_IDS)
            ]
            hard_satisfied = all(
                item["status"] == "Supported" for item in gate_receipts
            )
            parameter_set = _parameter_set(feed_override, sample_period)
            ood_fraction = _ood_fraction(intelligence_bundle, command, response)
            candidates.append(
                {
                    "candidateId": parameter_set.parameter_set_id,
                    "parameterSet": parameter_set.model_dump(
                        mode="json", by_alias=True
                    ),
                    "objectives": objectives,
                    "gateReceipts": gate_receipts,
                    "physicalApplicabilityPassed": applicability_evidence.status
                    == "Passed",
                    "hardConstraintsSatisfied": hard_satisfied
                    and applicability_evidence.status == "Passed",
                    "goalFeasible": _goal_feasible(request, objectives),
                    "paretoOptimal": False,
                    "m4ContentHash": canonical_hash(m4),
                    "m5ContentHash": command.content_id,
                    "physicalResponseContentHash": response.content_hash,
                    "oodFraction": ood_fraction,
                    "epistemicStatus": "InDomain"
                    if ood_fraction == 0.0
                    else "PartiallyOutOfDomain",
                    "permissionLevel": "Offline",
                    "deviceWriteAllowed": False,
                    "promotionEligible": False,
                    "explanation": (
                        f"feedOverride={feed_override:.2f} trades cycle time against linear following error; "
                        f"samplePeriod={sample_period:.2f}s trades command count against sampled response error. "
                        "This candidate remains offline because reality validation is open."
                    ),
                }
            )

    eligible = [
        item
        for item in candidates
        if item["hardConstraintsSatisfied"] and item["goalFeasible"]
    ]
    pareto_ids = {
        item["candidateId"]
        for item in eligible
        if not any(_dominates(other, item) for other in eligible if other is not item)
    }
    candidates.sort(key=_candidate_sort_key)
    sealed: list[OptimizationCandidate] = []
    for candidate in candidates:
        candidate["paretoOptimal"] = candidate["candidateId"] in pareto_ids
        candidate["candidateContentHash"] = canonical_hash(candidate)
        sealed.append(OptimizationCandidate.model_validate(candidate))

    baseline = _parameter_set(1.0, 0.08)
    validation_plan = OptimizationValidationPlan(
        planId="optimization.r6.offline-validation-plan@1",
        permissionLevel="Offline",
        remainingGates=(
            "independent-real-device-holdout",
            "shadow-observation-without-write",
            "controlled-trial-approval",
            "r7-online-stop-and-rollback",
        ),
        stopConditions=(
            "any mathematical gate becomes non-Supported",
            "physical model applicability or identity mismatch",
            "OOD fraction is non-zero for promotion",
            "clock, coordinate, calibration, or lineage context is incomplete",
        ),
        rollbackParameterSetId=baseline.parameter_set_id,
        deviceWriteAllowed=False,
    )
    payload = {
        "artifactType": "axiom.optimization.recommendation-set",
        "schemaId": "axiom.optimization.recommendation-set@1",
        "schemaVersion": 1,
        "recommendationSetId": "axiom.optimization.r6.canonical-head-table@1",
        "searchRequest": request.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "baselineParameterSet": baseline.model_dump(mode="json", by_alias=True),
        "candidates": [
            item.model_dump(mode="json", by_alias=True, exclude_none=True)
            for item in sealed
        ],
        "paretoCandidateIds": [
            item.candidate_id for item in sealed if item.pareto_optimal
        ],
        "physicalApplicabilityEvidence": applicability_evidence.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "validationPlan": validation_plan.model_dump(mode="json", by_alias=True),
        "permissionLevel": "Offline",
        "deviceWriteAllowed": False,
        "automaticAcceptanceAllowed": False,
        "shadowStatus": "Open",
        "realityValidationStatus": "Open",
    }
    payload["contentHash"] = canonical_hash(payload)
    return RecommendationSet.model_validate(payload)


@lru_cache(maxsize=1)
def default_recommendation_set() -> RecommendationSet:
    return search_recommendations(OptimizationSearchRequest())


__all__ = ["default_recommendation_set", "search_recommendations"]
