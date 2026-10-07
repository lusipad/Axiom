from __future__ import annotations

import os

import pytest
from pydantic import ValidationError

from axiom.intelligence import (
    ConditionalEffectDataset,
    ConditionalEffectModelBundle,
    ConditionalEffectPredictionRequest,
    build_r5c_manifest,
    evaluate_conditional_effect,
    list_r5c_scenarios,
    load_r5c_fixture_manifest,
    load_r5c_scenario,
    predict_conditional_effect,
    r5c_example_payload,
)
from axiom.run import evaluate_run


def test_r5c_default_scenario_is_deterministic_and_meets_numeric_gates() -> None:
    first = load_r5c_scenario()
    second = load_r5c_scenario()

    assert first.dataset.content_hash == second.dataset.content_hash
    assert first.model_bundle.content_hash == second.model_bundle.content_hash
    assert first.evaluation.synthetic_conditional_effect_contract_status == "Passed"
    results = {item.target_id: item for item in first.evaluation.head_results}
    assert results["cycleTimeSeconds"].normalized_rmse <= 0.02
    assert results["linearFollowingErrorMaxMm"].normalized_rmse <= 0.05
    assert all(item.conformal_coverage >= 0.80 for item in results.values())
    assert first.evaluation.ood_abstention_rate == 1.0
    assert first.evaluation.target_parity_max_abs_gap <= 1e-12
    assert first.evaluation.real_world_generalization_status == "Open"


def test_r5c_prediction_returns_separate_units_and_abstains_outside_domain() -> None:
    scenario = load_r5c_scenario()
    predicted = predict_conditional_effect(
        ConditionalEffectPredictionRequest(
            modelBundle=scenario.model_bundle,
            feedOverride=0.82,
            samplePeriod=0.055,
        )
    )
    assert predicted.status == "Predicted"
    assert [(item.target_id, item.unit) for item in predicted.predictions] == [
        ("cycleTimeSeconds", "s"),
        ("linearFollowingErrorMaxMm", "mm"),
    ]
    assert all(item.lower <= item.value <= item.upper for item in predicted.predictions)
    assert predicted.device_write_allowed is False

    abstained = predict_conditional_effect(
        ConditionalEffectPredictionRequest(
            modelBundle=scenario.model_bundle,
            feedOverride=1.01,
            samplePeriod=0.055,
        )
    )
    assert abstained.status == "Abstained"
    assert abstained.reason_code == "OutsideDeclaredDomain"
    assert abstained.predictions == ()


def test_r5c_rejects_tampered_bundle_and_split_leakage() -> None:
    scenario = load_r5c_scenario()
    bundle = scenario.model_bundle.model_dump(mode="json", by_alias=True)
    bundle["heads"][0]["weights"][0] += 1.0
    with pytest.raises(ValidationError, match="contentHash"):
        ConditionalEffectModelBundle.model_validate(bundle)

    request = scenario.evaluation_request.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    request["dataset"]["samples"][0]["declaredSplitId"] = "test"
    dataset = request["dataset"]
    dataset.pop("contentHash")
    from axiom.intelligence.models import canonical_hash

    dataset["contentHash"] = canonical_hash(dataset)
    request["dataset"] = ConditionalEffectDataset.model_validate(dataset).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    with pytest.raises(ValidationError, match="declared split"):
        type(scenario.evaluation_request).model_validate(request)


def test_r5c_core_run_and_direct_evaluation_are_semantically_equal() -> None:
    scenario = load_r5c_scenario()
    direct = evaluate_conditional_effect(scenario.evaluation_request)
    bundle = evaluate_run(scenario.run_spec)

    assert bundle.report == direct
    assert bundle.report.case_outcome.value == "Passed"
    assert bundle.report.execution_status.value == "Succeeded"
    assert bundle.report.provenance.artifact_hash == scenario.model_bundle.content_hash


def test_r5c_public_payload_and_manifest_keep_reality_open() -> None:
    manifest = build_r5c_manifest()
    payload = r5c_example_payload()

    assert manifest.stage == "R5-C"
    assert manifest.real_world_generalization_status == "Open"
    assert manifest.device_write_allowed is False
    assert [item.scenario_id for item in list_r5c_scenarios()] == [
        "canonical-head-table-conditional-effect"
    ]
    assert payload.manifest == manifest
    assert payload.prediction_example.status == "Predicted"
    assert payload.run_spec.domain_pack_id == "intelligence.domain-pack@3"


def test_packaged_r5c_fixture_manifest_freezes_environment_bound_identities() -> None:
    scenario = load_r5c_scenario()
    fixture = load_r5c_fixture_manifest()
    results = {item.target_id: item for item in scenario.evaluation.head_results}
    release_environment = os.getenv("AXIOM_REQUIRE_ENVIRONMENT_BOUND_GOLDENS") == "1"
    identities_key = (
        "windowsReleaseExpectedIdentities"
        if release_environment
        else "expectedIdentities"
    )
    gates_key = (
        "windowsReleaseExpectedGates" if release_environment else "expectedGates"
    )

    assert fixture[identities_key] == {
        "datasetContentHash": scenario.dataset.content_hash,
        "splitManifestContentHash": scenario.split_manifest.content_hash,
        "trainingReceiptContentHash": scenario.training_receipt.content_hash,
        "modelBundleContentHash": scenario.model_bundle.content_hash,
        "parityReceiptContentHash": scenario.parity_receipt.content_hash,
    }
    assert fixture[gates_key] == {
        "syntheticConditionalEffectContractStatus": scenario.evaluation.synthetic_conditional_effect_contract_status,
        "realWorldGeneralizationStatus": scenario.evaluation.real_world_generalization_status,
        "cycleTimeNormalizedRmse": results["cycleTimeSeconds"].normalized_rmse,
        "linearFollowingErrorNormalizedRmse": results[
            "linearFollowingErrorMaxMm"
        ].normalized_rmse,
        "cycleTimeConformalCoverage": results["cycleTimeSeconds"].conformal_coverage,
        "linearFollowingErrorConformalCoverage": results[
            "linearFollowingErrorMaxMm"
        ].conformal_coverage,
        "oodAbstentionRate": scenario.evaluation.ood_abstention_rate,
        "targetParityMaxAbsGap": scenario.evaluation.target_parity_max_abs_gap,
    }
