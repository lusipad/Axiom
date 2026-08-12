from __future__ import annotations

from copy import deepcopy
import inspect

import pytest

from axiom.intelligence import (
    DEFAULT_SCENARIO_ID,
    build_r5_manifest,
    list_r5_scenarios,
    load_r5_fixture_manifest,
    load_r5_scenario,
    pure_python_predict_observation,
    r5_example_payload,
    r5_example_run_spec,
)
from axiom.intelligence.models import IntelligenceEvaluationRequest, TargetParityReceipt
from axiom.intelligence import interpreter as target_interpreter
from axiom.intelligence.runtime import (
    REAL_PAIRED_HOLDOUT_CAPABILITY_ID,
    REAL_WORLD_GENERALIZATION_METRIC_ID,
    R5_DOMAIN_PACK,
    evaluate_intelligence,
)
from axiom.intelligence.training import dataset_samples_for_split, train_r5_bundle, validate_dataset_split_contract
from axiom.run import evaluate_run, validate_run_bundle_integrity


def test_r5_payload_and_manifest_expose_required_surfaces() -> None:
    payload = r5_example_payload()

    assert payload["manifest"]["domainPackId"] == "intelligence.domain-pack@1"
    assert payload["manifest"]["platform"] == "windows"
    assert payload["manifest"]["safetyBanner"] == "SYNTHETIC INTELLIGENCE / NOT DEVICE SAFE"
    assert payload["scenario"]["scenarioId"] == DEFAULT_SCENARIO_ID
    assert set(payload) == {"manifest", "scenario", "dataset", "splitManifest", "modelBundle", "evaluation", "runSpec"}
    assert payload["evaluation"]["syntheticLearningContractStatus"] == "Passed"
    assert payload["evaluation"]["realWorldGeneralizationStatus"] == "Open"
    assert payload["evaluation"]["oodDetectionRate"] == 1.0
    assert payload["evaluation"]["conformalCoverage"] >= 0.80
    assert payload["evaluation"]["targetParityMaxAbsGap"] <= 1e-12
    assert payload["evaluation"]["axisResults"][0]["status"] == "Validated"
    assert payload["modelBundle"]["inputContractId"] == "axiom.intelligence.x-residual-input@1"
    assert payload["modelBundle"]["preprocessorId"] == "axiom.intelligence.polynomial-feature-map@1"
    assert payload["modelBundle"]["outputContractId"] == "axiom.intelligence.residual-with-abstention@1"
    assert payload["dataset"]["governance"]["redistributionAllowed"] is False
    assert payload["dataset"]["coverageGaps"]
    upstream_by_split = {
        split_id: {
            sample["upstreamScenarioId"]
            for sample in payload["dataset"]["samples"]
            if sample["declaredSplitId"] == split_id
        }
        for split_id in ("train", "validation", "test")
    }
    assert upstream_by_split == {
        "train": {"canonical-dual-table-solver"},
        "validation": {"canonical-head-table-solver"},
        "test": {"canonical-dual-head-solver"},
    }
    assert all(len(sample["sourceCommandContentId"]) == 64 for sample in payload["dataset"]["samples"])


def test_r5_training_and_public_evaluate_run_replay_deterministically() -> None:
    scenario = load_r5_scenario()
    retrained_bundle, retrained_receipt, retrained_parity, retrained_evaluation = train_r5_bundle(
        scenario.dataset,
        scenario.split_manifest,
    )
    first = evaluate_run(r5_example_run_spec())
    second = evaluate_run(deepcopy(r5_example_run_spec()))

    assert retrained_bundle.content_hash == scenario.model_bundle.content_hash
    assert retrained_receipt.content_hash == scenario.training_receipt.content_hash
    assert retrained_parity.content_hash == scenario.parity_receipt.content_hash
    assert retrained_evaluation.synthetic_learning_contract_status == "Passed"
    assert first.bundle_hash == second.bundle_hash
    assert first.run.execution_status.value == "Succeeded"
    assert first.run.case_outcome.value == "Passed"
    assert validate_run_bundle_integrity(first) == []
    claims = {claim.claim_definition_id: claim for claim in first.claims}
    assert claims["intelligence.synthetic-learning-contract-claim@1"].status.value == "Supported"
    assert claims["intelligence.real-world-generalization-claim@1"].status.value == "Inconclusive"
    assert claims["intelligence.real-world-generalization-claim@1"].reason_code == "RealPairedHoldoutMissing"
    assert not {
        "five-axis.device-safe-claim@1",
        "five-axis.process-safe-claim@1",
    }.intersection(claims)


@pytest.mark.parametrize(
    ("field_name", "expected_message"),
    [
        ("trajectory_family", "trajectoryFamily identities must be split-disjoint"),
        ("task_id", "taskId identities must be split-disjoint"),
        ("device_batch_id", "deviceBatchId identities must be split-disjoint"),
        ("pair_id", "pairId identities must be split-disjoint"),
    ],
)
def test_split_contract_rejects_each_connected_identity_leak(
    field_name: str,
    expected_message: str,
) -> None:
    scenario = load_r5_scenario()
    train_sample = next(sample for sample in scenario.dataset.samples if sample.declared_split_id == "train")
    leaked_dataset = scenario.dataset.model_copy(
        update={
            "samples": tuple(
                sample.model_copy(update={field_name: getattr(train_sample, field_name)})
                if sample.sample_id == "validation-0"
                else sample
                for sample in scenario.dataset.samples
            )
        }
    )

    with pytest.raises(ValueError, match=expected_message):
        validate_dataset_split_contract(leaked_dataset, scenario.split_manifest)


def test_split_contract_rejects_time_reversal() -> None:
    scenario = load_r5_scenario()
    reversed_manifest = scenario.split_manifest.model_copy(
        update={
            "partitions": (
                scenario.split_manifest.partitions[0],
                scenario.split_manifest.partitions[1].model_copy(
                    update={"start_time": scenario.split_manifest.partitions[0].start_time}
                ),
                scenario.split_manifest.partitions[2],
            )
        }
    )

    with pytest.raises(ValueError, match="time windows|forward-only in time"):
        validate_dataset_split_contract(scenario.dataset, reversed_manifest)


def test_split_contract_rejects_unassigned_dataset_sample() -> None:
    scenario = load_r5_scenario()
    test_partition = scenario.split_manifest.partitions[2]
    incomplete_manifest = scenario.split_manifest.model_copy(
        update={
            "partitions": (
                scenario.split_manifest.partitions[0],
                scenario.split_manifest.partitions[1],
                test_partition.model_copy(update={"sample_ids": test_partition.sample_ids[:-1]}),
            )
        }
    )

    with pytest.raises(ValueError, match="assign every dataset sample exactly once"):
        validate_dataset_split_contract(scenario.dataset, incomplete_manifest)


def test_parity_receipt_status_must_match_frozen_tolerance() -> None:
    payload = load_r5_scenario().parity_receipt.model_dump(mode="json", by_alias=True)
    payload["maxAbsGap"] = 1e-3

    with pytest.raises(ValueError, match="status must match maxAbsGap tolerance"):
        TargetParityReceipt.model_validate(payload)


def test_ood_probe_must_abstain() -> None:
    scenario = load_r5_scenario()
    ood_samples = dataset_samples_for_split(
        scenario.dataset,
        scenario.split_manifest,
        split_id="test",
        scenario_role="ood-probe",
    )

    assert ood_samples
    for sample in ood_samples:
        assert pure_python_predict_observation(scenario.model_bundle, sample) == (True, None)


def test_target_interpreter_is_independent_from_training_numeric_stack() -> None:
    source = inspect.getsource(target_interpreter)

    assert "numpy" not in source
    assert "from .training" not in source


@pytest.mark.parametrize(
    "scenario_id",
    ["group-leak", "time-order-reversal", "bundle-tamper", "parity-tamper"],
)
def test_tampered_scenarios_are_rejected(scenario_id: str) -> None:
    scenario = load_r5_scenario(scenario_id)
    payload = r5_example_payload(scenario_id)
    bundle = evaluate_run(r5_example_run_spec(scenario_id))

    assert scenario.summary.expected_outcome == "Invalid"
    assert scenario.summary.expected_execution_status == "Skipped"
    assert "evaluation" not in payload
    assert bundle.run.execution_status.value == "Skipped"
    assert bundle.run.case_outcome.value == "Invalid"
    assert bundle.report.domain_failures[0].code in {"MalformedEvaluationRequest", "IntegrityReplayMismatch"}


def test_non_windows_gate_returns_skipped_without_positive_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    request = IntelligenceEvaluationRequest.model_validate(r5_example_run_spec()["request"])
    monkeypatch.setattr("axiom.intelligence.runtime.platform.system", lambda: "Linux")

    report = evaluate_intelligence(request)

    assert report.execution_status.value == "Skipped"
    assert report.case_outcome.value == "Unsupported"
    assert all(result.reason_code == "UnsupportedRuntimePlatform" for result in report.metric_results)
    assert not any(result.value is True for result in report.metric_results if result.status.value == "Computed")


def test_manifest_and_scenario_catalog_are_stable() -> None:
    manifest = build_r5_manifest()
    scenario_ids = [item.scenario_id for item in list_r5_scenarios()]

    assert manifest["defaultScenarioId"] == DEFAULT_SCENARIO_ID
    assert manifest["stage"] == "R5-A"
    assert manifest["syntheticLearningContractStatus"] == "Passed"
    assert manifest["realWorldGeneralizationStatus"] == "Open"
    assert scenario_ids == [
        DEFAULT_SCENARIO_ID,
        "group-leak",
        "time-order-reversal",
        "bundle-tamper",
        "parity-tamper",
    ]


def test_metric_capabilities_keep_real_holdout_explicitly_unresolved() -> None:
    real_metric = R5_DOMAIN_PACK.metric_definition(REAL_WORLD_GENERALIZATION_METRIC_ID)
    supported_capabilities = set(R5_DOMAIN_PACK.capability_ids)

    assert real_metric.requires == (REAL_PAIRED_HOLDOUT_CAPABILITY_ID,)
    assert REAL_PAIRED_HOLDOUT_CAPABILITY_ID not in supported_capabilities
    for definition in R5_DOMAIN_PACK.metric_definitions:
        if definition.metric_id != REAL_WORLD_GENERALIZATION_METRIC_ID:
            assert set(definition.requires) <= supported_capabilities


def test_packaged_r5_fixture_manifest_freezes_portable_identities_and_gates() -> None:
    scenario = load_r5_scenario()
    fixture = load_r5_fixture_manifest()

    assert fixture["expectedIdentities"] == {
        "datasetContentHash": scenario.dataset.content_hash,
        "splitManifestContentHash": scenario.split_manifest.content_hash,
        "trainingReceiptContentHash": scenario.training_receipt.content_hash,
        "modelBundleContentHash": scenario.model_bundle.content_hash,
        "parityReceiptContentHash": scenario.parity_receipt.content_hash,
    }
    assert fixture["expectedGates"]["syntheticLearningContractStatus"] == "Passed"
    assert fixture["expectedGates"]["realWorldGeneralizationStatus"] == "Open"
    assert fixture["expectedGates"]["xImprovementRatio"] == scenario.evaluation.axis_results[0].improvement_ratio
    assert fixture["expectedGates"]["conformalCoverage"] == scenario.evaluation.conformal_coverage
    assert fixture["expectedGates"]["oodDetectionRate"] == scenario.evaluation.ood_detection_rate
    assert fixture["expectedGates"]["targetParityMaxAbsGap"] == scenario.evaluation.target_parity_max_abs_gap
