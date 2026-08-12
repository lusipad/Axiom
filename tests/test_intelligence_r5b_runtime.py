from __future__ import annotations

from copy import deepcopy

import pytest
from test_intelligence_r5b_models import _build_holdout_set

from axiom.intelligence import load_r5_scenario
from axiom.intelligence.r5b_models import R5BIntelligenceEvaluationRequest
from axiom.intelligence.r5b_runtime import (
    R5B_ALIGNMENT_COVERAGE_METRIC_ID,
    R5B_MODEL_INTEGRITY_METRIC_ID,
    R5B_REAL_WORLD_GENERALIZATION_METRIC_ID,
    R5B_SOURCE_DECLARED_REAL_METRIC_ID,
    evaluate_r5b_intelligence,
)


def _base_payload() -> dict:
    scenario = load_r5_scenario()
    return {
        "artifact": scenario.model_bundle.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "dataset": scenario.dataset.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "splitManifest": scenario.split_manifest.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "trainingReceipt": scenario.training_receipt.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "parityReceipt": scenario.parity_receipt.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "case": {
            "caseId": "r5b-runtime@1",
            "requiredMetrics": [
                "intelligence.r5b.model-integrity@1",
                "intelligence.real-world-generalization@1",
            ],
            "optionalMetrics": [
                "intelligence.r5b.source-declared-real@1",
                "intelligence.r5b.alignment-coverage@1",
            ],
        },
    }


def test_r5b_runtime_without_real_holdout_stays_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _base_payload()
    request = R5BIntelligenceEvaluationRequest.model_validate(payload)
    monkeypatch.setattr(
        "axiom.intelligence.r5b_runtime.platform.system", lambda: "Windows"
    )

    report = evaluate_r5b_intelligence(request)

    assert report.execution_status.value == "Succeeded"
    assert report.case_outcome.value == "Inconclusive"
    metrics = {item.metric_id: item for item in report.metric_results}
    assert metrics[R5B_MODEL_INTEGRITY_METRIC_ID].status.value == "Computed"
    assert metrics[R5B_MODEL_INTEGRITY_METRIC_ID].value is True
    assert (
        metrics[R5B_REAL_WORLD_GENERALIZATION_METRIC_ID].status.value
        == "InsufficientContext"
    )
    assert (
        metrics[R5B_REAL_WORLD_GENERALIZATION_METRIC_ID].reason_code
        == "RealPairedHoldoutMissing"
    )


def test_r5b_runtime_non_windows_returns_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _base_payload()
    request = R5BIntelligenceEvaluationRequest.model_validate(payload)
    monkeypatch.setattr(
        "axiom.intelligence.r5b_runtime.platform.system", lambda: "Linux"
    )

    report = evaluate_r5b_intelligence(request)

    assert report.execution_status.value == "Skipped"
    assert report.case_outcome.value == "Unsupported"
    assert all(
        result.reason_code == "UnsupportedRuntimePlatform"
        for result in report.metric_results
    )


def test_r5b_runtime_evaluates_case_scoped_holdout_without_emitting_false_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _base_payload()
    payload["realHoldoutSet"] = deepcopy(_build_holdout_set())
    request = R5BIntelligenceEvaluationRequest.model_validate(payload)
    monkeypatch.setattr(
        "axiom.intelligence.r5b_runtime.platform.system", lambda: "Windows"
    )

    report = evaluate_r5b_intelligence(request)

    metrics = {item.metric_id: item for item in report.metric_results}
    assert report.execution_status.value == "Succeeded"
    assert report.case_outcome.value == "Failed"
    assert metrics[R5B_SOURCE_DECLARED_REAL_METRIC_ID].status.value == "Computed"
    assert metrics[R5B_SOURCE_DECLARED_REAL_METRIC_ID].value is True
    assert metrics[R5B_ALIGNMENT_COVERAGE_METRIC_ID].status.value == "Computed"
    assert metrics[R5B_ALIGNMENT_COVERAGE_METRIC_ID].value is True
    assert metrics[R5B_REAL_WORLD_GENERALIZATION_METRIC_ID].status.value == "Computed"
    assert metrics[R5B_REAL_WORLD_GENERALIZATION_METRIC_ID].value is False
    assert metrics[R5B_REAL_WORLD_GENERALIZATION_METRIC_ID].details["status"] == "Open"
