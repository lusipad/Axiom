from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..models import RunSpec
from ..optimization import load_r6v2_scenario
from .models import RuntimeSpec, ShadowSample, ShadowTrace, canonical_hash
from .r7a2_models import (
    R7A2_DEFAULT_SCENARIO_ID,
    R7A2_SCENARIO_IDS,
    R7A2ExamplePayload,
    R7A2Manifest,
    R7A2Scenario,
    R7A2ScenarioSummary,
    RecommendationEvidenceProjection,
    build_recommendation_evidence_projection,
)
from .runner import build_control_envelope, run_shadow
from .runtime import (
    ADMISSION_METRIC_ID,
    DEPLOYMENT_METRIC_ID,
    INTEGRITY_METRIC_ID,
    NO_WRITE_METRIC_ID,
    ROLLBACK_METRIC_ID,
    STOP_METRIC_ID,
)


def _trace(
    scenario_id: str, *, ood_fraction: float, breach: bool = False
) -> ShadowTrace:
    errors = (0.10, 0.22, 0.74 if breach else 0.31, 0.20)
    samples = tuple(
        ShadowSample(
            sequence=index,
            timeSeconds=index * 0.04,
            linearFollowingErrorMm=error,
            oodFraction=ood_fraction,
            sourceKind="synthetic-shadow",
        )
        for index, error in enumerate(errors)
    )
    payload = {
        "traceId": f"control.r7a2.trace.{scenario_id}@1",
        "sourceKind": "synthetic-shadow",
        "samples": [item.model_dump(mode="json", by_alias=True) for item in samples],
    }
    return ShadowTrace.model_validate(
        {**payload, "contentHash": canonical_hash(payload)}
    )


def build_r7a2_manifest() -> R7A2Manifest:
    return R7A2Manifest(
        manifestId="control.r7a-v2-manifest@1",
        domainPackId="control.domain-pack@1",
        evaluatorVersion="control-shadow-evaluator@1",
        runnerId="control-synthetic-shadow-replay@1",
        sourceRecommendationSchemaId="axiom.optimization.recommendation-set@2",
        projectionSchemaId="axiom.control.recommendation-evidence-projection@1",
        supportedPlatforms=("Windows",),
        permissionCeiling="Shadow",
        deviceWriteAllowed=False,
        scenarioIds=R7A2_SCENARIO_IDS,
        handoffContractStatus="Passed",
        syntheticShadowContractStatus="Passed",
        deploymentShadowStatus="Open",
        controlledTrialStatus="Open",
        closedLoopStatus="Open",
    )


def _candidate_for_scenario(scenario_id: str):
    recommendations = load_r6v2_scenario().recommendation_set
    if scenario_id == "r6v2-exact-ineligible-blocked":
        return recommendations, next(
            item
            for item in recommendations.exact_candidates
            if not item.recommendation_eligible
        )
    if scenario_id == "r6v2-exact-eligible-non-best":
        return recommendations, next(
            item
            for item in recommendations.exact_candidates
            if item.recommendation_eligible
            and item.candidate_id not in recommendations.best_observed_candidate_ids
        )
    best_id = recommendations.best_observed_candidate_ids[0]
    return recommendations, next(
        item
        for item in recommendations.exact_candidates
        if item.candidate_id == best_id
    )


@lru_cache(maxsize=len(R7A2_SCENARIO_IDS))
def load_r7a2_scenario(
    scenario_id: str = R7A2_DEFAULT_SCENARIO_ID,
) -> R7A2Scenario:
    if scenario_id not in R7A2_SCENARIO_IDS:
        raise KeyError(f"unknown R7-A v2 scenario: {scenario_id}")
    recommendations, candidate = _candidate_for_scenario(scenario_id)
    projection: RecommendationEvidenceProjection | None = None
    if scenario_id != "r6v2-handoff-missing-blocked":
        projection = build_recommendation_evidence_projection(
            recommendations, candidate.candidate_id
        )
    runtime_spec = RuntimeSpec(
        schemaId="control.runtime-spec@1",
        runtimeSpecId=f"control.r7a2.runtime-spec.{scenario_id}@1",
        scenarioId=scenario_id,
        requestedPermission="Shadow",
        deviceWriteRequested=scenario_id == "r6v2-device-write-request-blocked",
        candidateId=candidate.candidate_id,
        recommendationSetContentHash=recommendations.content_hash,
        envelope=build_control_envelope(
            baseline_parameter_set_id=(
                recommendations.validation_plan.rollback_parameter_set_id
            )
        ),
        trace=_trace(
            scenario_id,
            ood_fraction=candidate.ood_fraction,
            breach=scenario_id == "r6v2-shadow-limit-breach",
        ),
        requireDeploymentShadowEvidence=False,
    )
    audit = run_shadow(runtime_spec, recommendations, projection)
    title = {
        R7A2_DEFAULT_SCENARIO_ID: "R6 v2 best-observed Shadow handoff",
        "r6v2-exact-eligible-non-best": "Independent exact-eligible selection",
        "r6v2-shadow-limit-breach": "R6 v2 candidate breaches Shadow envelope",
        "r6v2-exact-ineligible-blocked": "Exact user constraint failure is blocked",
        "r6v2-handoff-missing-blocked": "Missing evidence projection is blocked",
        "r6v2-device-write-request-blocked": "Device write remains forbidden",
    }[scenario_id]
    summary = R7A2ScenarioSummary(
        scenarioId=scenario_id,
        title=title,
        description=(
            "Windows-only R6 v2 evidence handoff into deterministic synthetic "
            "Shadow; no controller connection or device write exists."
        ),
        expectedOutcome="Passed",
        expectedFinalState=audit.final_state,
    )
    required = [INTEGRITY_METRIC_ID, ADMISSION_METRIC_ID, NO_WRITE_METRIC_ID]
    if scenario_id == "r6v2-shadow-limit-breach":
        required.extend((STOP_METRIC_ID, ROLLBACK_METRIC_ID))
    request = {
        "artifact": audit.model_dump(mode="json", by_alias=True, exclude_none=True),
        "runtimeSpec": runtime_spec.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "recommendationSet": recommendations.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "case": {
            "caseId": f"control.r7a2.{scenario_id}.case@1",
            "requiredMetrics": required,
            "optionalMetrics": [DEPLOYMENT_METRIC_ID],
        },
    }
    if projection is not None:
        request["recommendationProjection"] = projection.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    run_spec = {
        "subjectId": "axiom.control.r7a2.synthetic-shadow-runtime@1",
        "domainPackId": "control.domain-pack@1",
        "runnerId": "control-synthetic-shadow-replay@1",
        "evaluatorVersion": "control-shadow-evaluator@1",
        "request": request,
    }
    RunSpec.model_validate(run_spec)
    return R7A2Scenario(
        summary=summary,
        recommendation_set=recommendations,
        recommendation_projection=projection,
        runtime_spec=runtime_spec,
        runtime_audit=audit,
        run_spec=run_spec,
    )


def list_r7a2_scenarios() -> tuple[R7A2ScenarioSummary, ...]:
    return tuple(load_r7a2_scenario(item).summary for item in R7A2_SCENARIO_IDS)


def r7a2_example_payload(
    scenario_id: str = R7A2_DEFAULT_SCENARIO_ID,
) -> R7A2ExamplePayload:
    scenario = load_r7a2_scenario(scenario_id)
    return R7A2ExamplePayload(
        manifest=build_r7a2_manifest(),
        scenario=scenario.summary,
        recommendationSet=scenario.recommendation_set,
        recommendationProjection=scenario.recommendation_projection,
        runtimeSpec=scenario.runtime_spec,
        runtimeAudit=scenario.runtime_audit,
        runSpec=scenario.run_spec,
    )


def r7a2_example_run_spec(
    scenario_id: str = R7A2_DEFAULT_SCENARIO_ID,
) -> dict[str, Any]:
    return load_r7a2_scenario(scenario_id).run_spec


def validate_r7a2_example_run_spec(
    scenario_id: str = R7A2_DEFAULT_SCENARIO_ID,
) -> RunSpec:
    return RunSpec.model_validate(r7a2_example_run_spec(scenario_id))


__all__ = [
    "build_r7a2_manifest",
    "list_r7a2_scenarios",
    "load_r7a2_scenario",
    "r7a2_example_payload",
    "r7a2_example_run_spec",
    "validate_r7a2_example_run_spec",
]
