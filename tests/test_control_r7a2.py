from __future__ import annotations

import json
import os

import pytest
from pydantic import ValidationError

from axiom import evaluate_run
from axiom.control import (
    R7A2_SCENARIO_IDS,
    R7A2EvaluationRequest,
    R7_DOMAIN_PACK,
    build_recommendation_evidence_projection,
    build_r7a2_manifest,
    load_r7_scenario,
    load_r7a2_scenario,
    r7a2_example_payload,
    validate_r7a2_example_run_spec,
)
from axiom.models import RunSpec


def test_r7a_v1_environment_bound_identities_remain_frozen() -> None:
    scenario = load_r7_scenario()
    bundle = evaluate_run(scenario.run_spec)
    replay = evaluate_run(scenario.run_spec)
    release_environment = os.getenv("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1"

    assert scenario.recommendation_set.content_hash == (
        "f4a4bd3d44b21f9bd068005bbdd5c88c5f7c4b63b3493b3a73c72105ddf0b97d"
        if release_environment
        else "77489ae7d7f51edb0fc8d38979898f893c67d41f50d366f361fb754d9edf5596"
    )
    assert scenario.runtime_audit.content_hash == (
        "1f373fc0555cc7e2e6465cf05e05fe830f7b65b69e1cdf0d8509a04322570a98"
        if release_environment
        else "8a7b18f08850025f11d5c6a77fecb5bcd5b612a4ef327b3e88fe254222cec95e"
    )
    assert bundle.report.content_hash == replay.report.content_hash
    assert bundle.bundle_hash == replay.bundle_hash


def test_r7a2_default_projection_and_audit_environment_identities_are_frozen() -> None:
    scenario = load_r7a2_scenario()
    release_environment = os.getenv("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1"

    assert scenario.recommendation_projection is not None
    assert scenario.recommendation_projection.content_hash == (
        "b0350aa07c5c6449c7979801990be462fb06a628435024b0d211e5986f5e73a0"
        if release_environment
        else "a6e413de7e29253bb6154b6dc6c24298af594752837ae1a2d55f58ed14a23160"
    )
    assert scenario.runtime_audit.content_hash == (
        "aecbe8e456901a443d1e3776193155b8b82717f52453adff6a87c5009822d12d"
        if release_environment
        else "1a9878a396bf3ec48dcfcca6b04950e9b465da4b826e402d172ec3f244a1dfe7"
    )


def test_r7a2_default_projects_exact_r6v2_evidence_without_auto_acceptance() -> None:
    payload = r7a2_example_payload()
    projection = payload.recommendation_projection
    recommendation = payload.recommendation_set
    audit = payload.runtime_audit

    assert projection is not None
    assert recommendation.schema_id == "axiom.optimization.recommendation-set@2"
    assert (
        projection.source_recommendation_set_content_hash == recommendation.content_hash
    )
    assert projection.candidate_id in recommendation.best_observed_candidate_ids
    assert projection.source_candidate_status == "ExactEligible"
    assert projection.selection_class == "BestObserved"
    assert projection.target_use == "SyntheticShadowAdmission"
    assert projection.device_write_allowed is False
    assert projection.automatic_acceptance_allowed is False
    assert audit.final_state == "Completed"
    assert audit.admission_decision.status == "Admitted"
    assert audit.acceptance_record.automatic is False
    assert audit.acceptance_record.evidence_snapshot_hash == projection.content_hash
    assert audit.acceptance_record.content_hash != projection.content_hash
    assert audit.deployment_shadow_status == "Open"
    assert audit.controlled_trial_status == "Open"
    assert audit.closed_loop_status == "Open"


def test_r7a2_exact_eligible_non_best_candidate_can_be_independently_selected() -> None:
    scenario = load_r7a2_scenario("r6v2-exact-eligible-non-best")

    assert scenario.recommendation_projection is not None
    assert scenario.recommendation_projection.source_candidate_status == "ExactEligible"
    assert scenario.recommendation_projection.selection_class in {
        "ParetoWithinValidated",
        "ExactEligible",
    }
    assert scenario.runtime_audit.final_state == "Completed"
    assert scenario.runtime_audit.acceptance_record.automatic is False


def test_r7a2_exact_constraint_failure_is_blocked_before_monitoring() -> None:
    scenario = load_r7a2_scenario("r6v2-exact-ineligible-blocked")

    assert scenario.recommendation_projection is not None
    assert (
        scenario.recommendation_projection.source_candidate_status == "ExactIneligible"
    )
    assert scenario.runtime_audit.final_state == "Blocked"
    assert "RecommendationGoalConstraintFailed" in (
        scenario.runtime_audit.admission_decision.reason_codes
    )
    assert scenario.runtime_audit.monitor_findings == ()


def test_r7a2_missing_projection_fails_closed() -> None:
    scenario = load_r7a2_scenario("r6v2-handoff-missing-blocked")

    assert scenario.recommendation_projection is None
    assert scenario.runtime_audit.final_state == "Blocked"
    assert "RecommendationHandoffMissing" in (
        scenario.runtime_audit.admission_decision.reason_codes
    )


def test_r7a2_limit_breach_stops_only_the_synthetic_shadow_replay() -> None:
    audit = load_r7a2_scenario("r6v2-shadow-limit-breach").runtime_audit

    assert audit.final_state == "RollbackVerified"
    assert audit.stop_receipt.effect == "PromotionSuppressed"
    assert audit.stop_receipt.device_stop_command_issued is False
    assert audit.rollback_receipt.status == "BaselineRetained"
    assert audit.rollback_receipt.device_write_issued is False


def test_r7a2_device_write_request_is_blocked() -> None:
    audit = load_r7a2_scenario("r6v2-device-write-request-blocked").runtime_audit

    assert audit.final_state == "Blocked"
    assert "DeviceWriteForbidden" in audit.admission_decision.reason_codes
    assert audit.device_write_performed is False


def test_r7a2_projection_rejects_tampering_and_cross_candidate_rebinding() -> None:
    scenario = load_r7a2_scenario()
    projection = scenario.recommendation_projection
    assert projection is not None
    raw = projection.model_dump(mode="json", by_alias=True)
    raw["candidateContentHash"] = "0" * 64

    with pytest.raises(ValidationError, match="contentHash"):
        type(projection).model_validate(raw)

    other = next(
        candidate
        for candidate in scenario.recommendation_set.exact_candidates
        if candidate.candidate_id != projection.candidate_id
    )
    rebound = build_recommendation_evidence_projection(
        scenario.recommendation_set, other.candidate_id
    )
    request = scenario.run_spec["request"] | {
        "recommendationProjection": rebound.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    }

    with pytest.raises(ValidationError, match="candidateId"):
        R7A2EvaluationRequest.model_validate(request)


def test_r7a2_public_run_replays_projection_and_keeps_deployment_open() -> None:
    bundle = evaluate_run(validate_r7a2_example_run_spec())
    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}

    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.run.case_outcome.value == "Passed"
    assert claims["control.runtime-audit-integrity-claim@1"] == "Supported"
    assert claims["control.admission-policy-enforced-claim@1"] == "Supported"
    assert claims["control.no-device-write-boundary-claim@1"] == "Supported"
    assert claims["control.deployment-readiness-claim@1"] == "Inconclusive"
    assert "recommendationProjection" in bundle.report.provenance.context_hashes


def test_r7a2_tampered_projection_is_invalid_in_public_run() -> None:
    payload = validate_r7a2_example_run_spec().model_dump(mode="json", by_alias=True)
    payload["request"]["recommendationProjection"]["candidateContentHash"] = "0" * 64

    bundle = evaluate_run(RunSpec.model_validate(payload))

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Invalid"
    assert bundle.report.domain_failures[0].code == "MalformedEvaluationRequest"


def test_r7_domain_pack_explicitly_accepts_both_recommendation_context_schemas() -> (
    None
):
    versions = {
        descriptor.schema_version
        for descriptor in R7_DOMAIN_PACK.artifact_type_descriptors
        if descriptor.artifact_type == "axiom.optimization.recommendation-set"
        and descriptor.role == "context"
    }

    assert versions == {1, 2}


def test_r7a2_manifest_and_serialized_output_keep_the_permission_boundary() -> None:
    manifest = build_r7a2_manifest()
    serialized = json.dumps(
        r7a2_example_payload().model_dump(mode="json", by_alias=True), sort_keys=True
    )

    assert manifest.scenario_ids == R7A2_SCENARIO_IDS
    assert manifest.supported_platforms == ("Windows",)
    assert manifest.source_recommendation_schema_id == (
        "axiom.optimization.recommendation-set@2"
    )
    assert manifest.permission_ceiling == "Shadow"
    assert manifest.device_write_allowed is False
    assert manifest.deployment_shadow_status == "Open"
    assert "DeviceSafe" not in serialized
    assert "ProcessSafe" not in serialized
    assert "safe-to-run" not in serialized


def test_r7a2_non_windows_runtime_is_explicitly_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiom.control import runtime as runtime_module

    monkeypatch.setattr(runtime_module.platform, "system", lambda: "Linux")

    bundle = evaluate_run(validate_r7a2_example_run_spec())

    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Unsupported"
    assert all(
        result.reason_code == "UnsupportedRuntimePlatform"
        for result in bundle.report.metric_results
    )
