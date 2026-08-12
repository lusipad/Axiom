from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..models import RunSpec
from ..optimization import default_recommendation_set
from .models import (
    R7_DEFAULT_SCENARIO_ID,
    R7_DOMAIN_PACK_ID,
    R7_EVALUATOR_ID,
    R7_RUNNER_ID,
    R7_SCENARIO_IDS,
    R7ExamplePayload,
    R7Manifest,
    R7Scenario,
    R7ScenarioSummary,
    RuntimeSpec,
    ShadowSample,
    ShadowTrace,
    canonical_hash,
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


def _trace(scenario_id: str, *, breach: bool = False) -> ShadowTrace:
    errors = (0.10, 0.22, 0.74 if breach else 0.31, 0.20)
    samples = tuple(
        ShadowSample(
            sequence=index,
            timeSeconds=index * 0.04,
            linearFollowingErrorMm=error,
            oodFraction=0.0,
            sourceKind="synthetic-shadow",
        )
        for index, error in enumerate(errors)
    )
    payload = {
        "traceId": f"control.r7.trace.{scenario_id}@1",
        "sourceKind": "synthetic-shadow",
        "samples": [item.model_dump(mode="json", by_alias=True) for item in samples],
    }
    return ShadowTrace.model_validate(
        {**payload, "contentHash": canonical_hash(payload)}
    )


def build_r7_manifest() -> R7Manifest:
    return R7Manifest(
        manifestId="control.r7-manifest@1",
        domainPackId=R7_DOMAIN_PACK_ID,
        evaluatorVersion=R7_EVALUATOR_ID,
        runnerId=R7_RUNNER_ID,
        supportedPlatforms=("Windows",),
        permissionCeiling="Shadow",
        deviceWriteAllowed=False,
        scenarioIds=R7_SCENARIO_IDS,
        syntheticShadowContractStatus="Passed",
        deploymentShadowStatus="Open",
        controlledTrialStatus="Open",
        closedLoopStatus="Open",
    )


@lru_cache(maxsize=len(R7_SCENARIO_IDS))
def load_r7_scenario(scenario_id: str = R7_DEFAULT_SCENARIO_ID) -> R7Scenario:
    if scenario_id not in R7_SCENARIO_IDS:
        raise KeyError(f"unknown R7 scenario: {scenario_id}")
    recommendations = default_recommendation_set()
    candidate = next(
        item
        for item in recommendations.candidates
        if item.parameter_set.values == {"feedOverride": 0.7, "samplePeriod": 0.04}
    )
    requested_permission = (
        "ControlledTrial"
        if scenario_id == "controlled-trial-without-authority"
        else "Shadow"
    )
    device_write_requested = scenario_id == "device-write-request-blocked"
    require_deployment = scenario_id == "deployment-shadow-reality-open"
    envelope = build_control_envelope(
        baseline_parameter_set_id=recommendations.baseline_parameter_set.parameter_set_id
    )
    runtime_spec = RuntimeSpec(
        schemaId="control.runtime-spec@1",
        runtimeSpecId=f"control.r7.runtime-spec.{scenario_id}@1",
        scenarioId=scenario_id,
        requestedPermission=requested_permission,
        deviceWriteRequested=device_write_requested,
        candidateId=candidate.candidate_id,
        recommendationSetContentHash=recommendations.content_hash,
        envelope=envelope,
        trace=_trace(
            scenario_id, breach=scenario_id == "synthetic-shadow-limit-breach"
        ),
        requireDeploymentShadowEvidence=require_deployment,
    )
    audit = run_shadow(runtime_spec, recommendations)
    title = {
        R7_DEFAULT_SCENARIO_ID: "Synthetic shadow nominal replay",
        "synthetic-shadow-limit-breach": "Envelope breach stops promotion",
        "deployment-shadow-reality-open": "Deployment evidence remains open",
        "controlled-trial-without-authority": "Controlled Trial permission is denied",
        "device-write-request-blocked": "Device write request is blocked",
    }[scenario_id]
    summary = R7ScenarioSummary(
        scenarioId=scenario_id,
        title=title,
        description="Windows-only deterministic shadow replay; no controller connection or device write exists.",
        expectedOutcome="Passed",
        expectedFinalState=audit.final_state,
    )
    required = [INTEGRITY_METRIC_ID, ADMISSION_METRIC_ID, NO_WRITE_METRIC_ID]
    if scenario_id == "synthetic-shadow-limit-breach":
        required.extend((STOP_METRIC_ID, ROLLBACK_METRIC_ID))
    run_spec = {
        "subjectId": "axiom.control.r7.synthetic-shadow-runtime@1",
        "domainPackId": R7_DOMAIN_PACK_ID,
        "runnerId": R7_RUNNER_ID,
        "evaluatorVersion": R7_EVALUATOR_ID,
        "request": {
            "artifact": audit.model_dump(mode="json", by_alias=True, exclude_none=True),
            "runtimeSpec": runtime_spec.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "recommendationSet": recommendations.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "case": {
                "caseId": f"control.r7.{scenario_id}.case@1",
                "requiredMetrics": required,
                "optionalMetrics": [DEPLOYMENT_METRIC_ID],
            },
        },
    }
    RunSpec.model_validate(run_spec)
    return R7Scenario(
        summary=summary,
        recommendation_set=recommendations,
        runtime_spec=runtime_spec,
        runtime_audit=audit,
        run_spec=run_spec,
    )


def list_r7_scenarios() -> tuple[R7ScenarioSummary, ...]:
    return tuple(load_r7_scenario(item).summary for item in R7_SCENARIO_IDS)


def r7_example_payload(scenario_id: str = R7_DEFAULT_SCENARIO_ID) -> R7ExamplePayload:
    scenario = load_r7_scenario(scenario_id)
    return R7ExamplePayload(
        manifest=build_r7_manifest(),
        scenario=scenario.summary,
        recommendationSet=scenario.recommendation_set,
        runtimeSpec=scenario.runtime_spec,
        runtimeAudit=scenario.runtime_audit,
        runSpec=scenario.run_spec,
    )


def r7_example_run_spec(scenario_id: str = R7_DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    return load_r7_scenario(scenario_id).run_spec


def validate_r7_example_run_spec(scenario_id: str = R7_DEFAULT_SCENARIO_ID) -> RunSpec:
    return RunSpec.model_validate(r7_example_run_spec(scenario_id))
