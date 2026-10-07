from __future__ import annotations

from copy import deepcopy
import platform

import pytest
from pydantic import ValidationError

from axiom.intelligence import (
    R5GModelPromotionReadinessDossier,
    R5GPromotionReadinessRequest,
    assess_r5f_candidate_downstream_impact,
    build_r5e_campaign_request,
    build_r5g_manifest,
    build_r5g_promotion_readiness_request,
    execute_r5e_synthetic_campaign,
    load_r5g_fixture_manifest,
    prepare_r5g_model_promotion_readiness,
)
from axiom.intelligence.models import canonical_hash


@pytest.fixture(scope="module")
def impact_report():
    campaign = execute_r5e_synthetic_campaign(
        build_r5e_campaign_request(accountable_party_id="fixture-reviewer"),
        current_platform="Windows",
    )
    return assess_r5f_candidate_downstream_impact(
        campaign, current_platform="Windows"
    )


@pytest.fixture(scope="module")
def readiness_request(impact_report):
    return build_r5g_promotion_readiness_request(
        impact_report,
        prepared_by="promotion-readiness-preparer",
    )


@pytest.fixture(scope="module")
def readiness_dossier(readiness_request):
    return prepare_r5g_model_promotion_readiness(
        readiness_request,
        current_platform="Windows",
    )


def _reseal(payload: dict[str, object]) -> None:
    payload.pop("contentHash", None)
    payload["contentHash"] = canonical_hash(payload)


def test_manifest_freezes_review_without_model_activation() -> None:
    manifest = build_r5g_manifest()

    assert manifest.stage == "R5-G"
    assert manifest.platform == "windows"
    assert manifest.review_scope == "synthetic-offline-review"
    assert manifest.review_readiness_status == "ReadyForIndependentReview"
    assert manifest.review_decision_status == "AwaitingIndependentHumanDecision"
    assert manifest.automatic_model_promotion_allowed is False
    assert manifest.model_registry_write_allowed is False
    assert manifest.default_model_change_allowed is False
    assert manifest.device_write_allowed is False


def test_readiness_dossier_preserves_candidate_and_promotion_boundaries(
    impact_report,
    readiness_dossier: R5GModelPromotionReadinessDossier,
) -> None:
    assert readiness_dossier.source_impact_report_hash == impact_report.content_hash
    assert readiness_dossier.replayed_impact_report_hash == impact_report.content_hash
    assert readiness_dossier.review_readiness_status == "ReadyForIndependentReview"
    assert (
        readiness_dossier.review_decision_status
        == "AwaitingIndependentHumanDecision"
    )
    assert readiness_dossier.candidate_use_status == "EvaluatedOnly"
    assert readiness_dossier.model_promotion_status == "NotPerformed"
    assert readiness_dossier.default_model_changed is False
    assert readiness_dossier.model_registry_write_performed is False
    assert readiness_dossier.activation_performed is False
    assert readiness_dossier.automatic_deployment_allowed is False
    assert readiness_dossier.device_write_allowed is False
    assert {item.status for item in readiness_dossier.readiness_checks} == {"Passed"}
    assert {item.status for item in readiness_dossier.remaining_gates} == {"Open"}
    assert len(readiness_dossier.remaining_gates) == 6

    baseline_hashes = {
        item.baseline_recommendation.search_request.surrogate_context.model_bundle.content_hash
        for item in impact_report.scenario_impacts
    }
    candidate_hashes = {
        item.candidate_recommendation.search_request.surrogate_context.model_bundle.content_hash
        for item in impact_report.scenario_impacts
    }
    assert baseline_hashes == {readiness_dossier.baseline_model_bundle_hash}
    assert candidate_hashes == {readiness_dossier.candidate_model_bundle_hash}
    assert (
        readiness_dossier.request.rollback_baseline_model_bundle_hash
        == readiness_dossier.baseline_model_bundle_hash
    )


def test_request_rejects_a_resealed_rollback_baseline_rebinding(
    readiness_request: R5GPromotionReadinessRequest,
) -> None:
    raw = deepcopy(readiness_request.model_dump(mode="json", by_alias=True))
    raw["rollbackBaselineModelBundleHash"] = "0" * 64
    _reseal(raw)

    with pytest.raises(ValidationError, match="rollback baseline"):
        R5GPromotionReadinessRequest.model_validate(raw)


def test_dossier_rejects_resealed_derived_state(
    readiness_dossier: R5GModelPromotionReadinessDossier,
) -> None:
    raw = deepcopy(readiness_dossier.model_dump(mode="json", by_alias=True))
    raw["reviewDecisionStatus"] = "Approved"
    _reseal(raw)

    with pytest.raises(ValidationError):
        R5GModelPromotionReadinessDossier.model_validate(raw)


def test_non_windows_fails_before_replaying_r5f(
    readiness_request: R5GPromotionReadinessRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden_replay(*_args: object, **_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("R5-F replay must not run")

    monkeypatch.setattr(
        "axiom.intelligence.r5g_readiness.assess_r5f_candidate_downstream_impact",
        forbidden_replay,
    )
    with pytest.raises(ValueError, match="only supports Windows"):
        prepare_r5g_model_promotion_readiness(
            readiness_request,
            current_platform="Linux",
        )
    assert called is False


def test_dossier_round_trips_without_upgrading_safety_claims(
    readiness_dossier: R5GModelPromotionReadinessDossier,
) -> None:
    payload = readiness_dossier.model_dump(mode="json", by_alias=True)
    assert R5GModelPromotionReadinessDossier.model_validate(payload) == readiness_dossier
    assert "DeviceSafe" not in str(payload)
    assert "ProcessSafe" not in str(payload)
    assert "safe-to-run" not in str(payload)


def _fixture_identities(
    dossier: R5GModelPromotionReadinessDossier,
) -> dict[str, str]:
    return {
        "impactReportContentHash": dossier.source_impact_report_hash,
        "requestContentHash": dossier.request.content_hash,
        "dossierContentHash": dossier.content_hash,
        "baselineModelBundleHash": dossier.baseline_model_bundle_hash,
        "candidateModelBundleHash": dossier.candidate_model_bundle_hash,
        "candidateContextHash": dossier.candidate_context_hash,
    }


def test_development_fixture_freezes_readiness_lineage(
    readiness_dossier: R5GModelPromotionReadinessDossier,
) -> None:
    if platform.python_version() != "3.14.3":
        pytest.skip("development golden requires CPython 3.14.3")
    fixture = load_r5g_fixture_manifest()
    assert _fixture_identities(readiness_dossier) == fixture[
        "developmentExpectedIdentities"
    ]
    assert fixture["boundary"] == readiness_dossier.safety_banner


def test_windows_release_fixture_freezes_readiness_lineage(
    readiness_dossier: R5GModelPromotionReadinessDossier,
) -> None:
    if platform.python_version() != "3.12.10":
        pytest.skip("release golden requires CPython 3.12.10")
    fixture = load_r5g_fixture_manifest()
    assert _fixture_identities(readiness_dossier) == fixture[
        "windowsReleaseExpectedIdentities"
    ]
