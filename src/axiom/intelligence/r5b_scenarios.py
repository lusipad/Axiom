from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ..models import RunSpec
from .models import (
    DatasetSnapshot,
    ModelBundle,
    SplitManifest,
    TargetParityReceipt,
    TrainingReceipt,
)
from .r5b_models import (
    R5B_DOMAIN_PACK_ID,
    R5B_EVALUATOR_ID,
    R5B_REQUIRED_EVIDENCE,
    R5B_RUNNER_ID,
    R5BAcceptanceThresholds,
    R5BExamplePayload,
    R5BManifest,
    R5BReadinessCheck,
    R5BScenarioSummary,
)
from .r5b_runtime import (
    R5B_ALIGNMENT_COVERAGE_METRIC_ID,
    R5B_CONFORMAL_COVERAGE_METRIC_ID,
    R5B_GOVERNANCE_VALID_METRIC_ID,
    R5B_HOLDOUT_ISOLATION_METRIC_ID,
    R5B_MODEL_INTEGRITY_METRIC_ID,
    R5B_OBSERVED_IMPROVEMENT_METRIC_ID,
    R5B_OOD_ABSTENTION_METRIC_ID,
    R5B_REAL_WORLD_GENERALIZATION_METRIC_ID,
    R5B_SOURCE_DECLARED_REAL_METRIC_ID,
)
from .scenarios import load_r5_scenario

R5B_DEFAULT_SCENARIO_ID = "real-holdout-readiness-open"


@dataclass(frozen=True, slots=True)
class R5BScenario:
    summary: R5BScenarioSummary
    readiness_checks: tuple[R5BReadinessCheck, ...]
    model_bundle: ModelBundle
    dataset: DatasetSnapshot
    split_manifest: SplitManifest
    training_receipt: TrainingReceipt
    parity_receipt: TargetParityReceipt
    run_spec: dict[str, Any]


def build_r5b_manifest() -> dict[str, Any]:
    return R5BManifest(
        manifestId="axiom.intelligence.r5b-manifest@1",
        schemaId="axiom.intelligence.r5b-manifest@1",
        schemaVersion=1,
        stage="R5-B",
        domainPackId=R5B_DOMAIN_PACK_ID,
        platform="windows",
        defaultScenarioId=R5B_DEFAULT_SCENARIO_ID,
        contractReadinessStatus="Passed",
        realWorldGeneralizationStatus="Open",
        safetyBanner="REAL HOLDOUT VALIDATION / NOT DEVICE SAFE",
        realityBanner="NO BUNDLED REAL CAPTURE / CASE-SCOPED EVIDENCE REQUIRED",
        requiredEvidence=R5B_REQUIRED_EVIDENCE,
        acceptanceThresholds=R5BAcceptanceThresholds(
            minimumInDomainCases=2,
            minimumTotalCases=3,
            minimumDistinctDevices=2,
            minimumDistinctConditions=2,
            requiredAlignmentCoverage=1.0,
            minimumImprovementRatio=0.2,
            minimumConformalCoverage=0.8,
            requiredOodAbstentionRate=1.0,
            maximumTargetParityGap=1e-12,
        ),
    ).model_dump(mode="json", by_alias=True, exclude_none=True)


def _readiness_checks() -> tuple[R5BReadinessCheck, ...]:
    return (
        R5BReadinessCheck(
            checkId="r5b.windows-runtime",
            title="Windows-only runtime",
            status="Passed",
            detail="The validator is bound to the Windows acceptance matrix and exposes no device write path.",
        ),
        R5BReadinessCheck(
            checkId="r5b.model-lineage",
            title="Frozen R5-A model lineage",
            status="Passed",
            detail="ModelBundle, DatasetSnapshot, SplitManifest, TrainingReceipt, and parity identities stay sealed.",
        ),
        R5BReadinessCheck(
            checkId="r5b.real-source-governance",
            title="Real source and governance",
            status="Open",
            detail="No controller-export or device-read capture with owner attestation and evaluation license is bundled.",
        ),
        R5BReadinessCheck(
            checkId="r5b.holdout-isolation",
            title="Cross-device and cross-condition holdout",
            status="Open",
            detail="At least two in-domain devices and conditions plus one OOD case must be supplied externally.",
        ),
        R5BReadinessCheck(
            checkId="r5b.case-scoped-claim",
            title="Case-scoped real-world claim",
            status="Open",
            detail="Only a complete external Windows holdout set can support a claim limited to its submitted cases.",
        ),
    )


def _build_open_scenario() -> R5BScenario:
    r5a = load_r5_scenario()
    run_spec: dict[str, Any] = {
        "subjectId": "axiom.intelligence.x-residual-model.real-holdout@1",
        "subjectVersion": "1",
        "domainPackId": R5B_DOMAIN_PACK_ID,
        "runnerId": R5B_RUNNER_ID,
        "evaluatorVersion": R5B_EVALUATOR_ID,
        "request": {
            "artifact": r5a.model_bundle.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "dataset": r5a.dataset.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "splitManifest": r5a.split_manifest.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "trainingReceipt": r5a.training_receipt.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "parityReceipt": r5a.parity_receipt.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "realHoldoutSet": None,
            "case": {
                "caseId": "axiom.intelligence.real-holdout-readiness.case@1",
                "requiredMetrics": [
                    R5B_MODEL_INTEGRITY_METRIC_ID,
                    R5B_REAL_WORLD_GENERALIZATION_METRIC_ID,
                ],
                "optionalMetrics": [
                    R5B_SOURCE_DECLARED_REAL_METRIC_ID,
                    R5B_GOVERNANCE_VALID_METRIC_ID,
                    R5B_HOLDOUT_ISOLATION_METRIC_ID,
                    R5B_ALIGNMENT_COVERAGE_METRIC_ID,
                    {
                        "metricId": R5B_OBSERVED_IMPROVEMENT_METRIC_ID,
                        "threshold": {"operator": ">=", "value": 0.2},
                    },
                    {
                        "metricId": R5B_CONFORMAL_COVERAGE_METRIC_ID,
                        "threshold": {"operator": ">=", "value": 0.8},
                    },
                    {
                        "metricId": R5B_OOD_ABSTENTION_METRIC_ID,
                        "threshold": {"operator": ">=", "value": 1.0},
                    },
                ],
            },
        },
    }
    RunSpec.model_validate(run_spec)
    return R5BScenario(
        summary=R5BScenarioSummary(
            scenarioId=R5B_DEFAULT_SCENARIO_ID,
            title="Windows real holdout readiness (open)",
            description=(
                "The R5-A model lineage is sealed, but no bundled controller-export or device-read holdout exists."
            ),
            expectedOutcome="Inconclusive",
            expectedExecutionStatus="Succeeded",
            realWorldGeneralizationStatus="Open",
        ),
        readiness_checks=_readiness_checks(),
        model_bundle=r5a.model_bundle,
        dataset=r5a.dataset,
        split_manifest=r5a.split_manifest,
        training_receipt=r5a.training_receipt,
        parity_receipt=r5a.parity_receipt,
        run_spec=run_spec,
    )


@lru_cache(maxsize=1)
def _scenario() -> R5BScenario:
    return _build_open_scenario()


def list_r5b_scenarios() -> tuple[R5BScenarioSummary, ...]:
    return (_scenario().summary,)


def load_r5b_scenario(scenario_id: str = R5B_DEFAULT_SCENARIO_ID) -> R5BScenario:
    if scenario_id != R5B_DEFAULT_SCENARIO_ID:
        raise KeyError(
            f"unknown R5-B scenario '{scenario_id}'; expected: {R5B_DEFAULT_SCENARIO_ID}"
        )
    return _scenario()


def r5b_example_payload(scenario_id: str = R5B_DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    scenario = load_r5b_scenario(scenario_id)
    payload = R5BExamplePayload(
        manifest=R5BManifest.model_validate(build_r5b_manifest()),
        scenario=scenario.summary,
        readinessChecks=scenario.readiness_checks,
        modelBundle=scenario.model_bundle,
        dataset=scenario.dataset,
        splitManifest=scenario.split_manifest,
        trainingReceipt=scenario.training_receipt,
        parityReceipt=scenario.parity_receipt,
        realHoldoutSet=None,
        runSpec=RunSpec.model_validate(scenario.run_spec),
    )
    return payload.model_dump(mode="json", by_alias=True, exclude_none=False)


def r5b_example_run_spec(scenario_id: str = R5B_DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    return deepcopy(load_r5b_scenario(scenario_id).run_spec)


def validate_r5b_example_run_spec(
    scenario_id: str = R5B_DEFAULT_SCENARIO_ID,
) -> RunSpec:
    return RunSpec.model_validate(r5b_example_run_spec(scenario_id))


__all__ = [
    "R5B_DEFAULT_SCENARIO_ID",
    "R5BScenario",
    "build_r5b_manifest",
    "list_r5b_scenarios",
    "load_r5b_scenario",
    "r5b_example_payload",
    "r5b_example_run_spec",
    "validate_r5b_example_run_spec",
]
