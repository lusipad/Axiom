from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..models import RunSpec
from .models import (
    R6_DEFAULT_SCENARIO_ID,
    R6_DOMAIN_PACK_ID,
    R6_EVALUATOR_ID,
    R6_OBJECTIVE_IDS,
    R6_RUNNER_ID,
    OptimizationSearchRequest,
    R6ExamplePayload,
    R6Manifest,
    R6Scenario,
    R6ScenarioSummary,
)
from .runtime import (
    HARD_CONSTRAINT_METRIC_ID,
    INTEGRITY_METRIC_ID,
    OFFLINE_BOUNDARY_METRIC_ID,
    PARETO_COUNT_METRIC_ID,
    REALITY_VALIDATION_METRIC_ID,
)
from .search import search_recommendations


def build_r6_manifest() -> R6Manifest:
    return R6Manifest(
        manifestId="optimization.r6-manifest@1",
        domainPackId=R6_DOMAIN_PACK_ID,
        evaluatorVersion=R6_EVALUATOR_ID,
        runnerId=R6_RUNNER_ID,
        supportedPlatforms=("Windows",),
        permissionLevel="Offline",
        deviceWriteAllowed=False,
        parameterIds=("feedOverride", "samplePeriod"),
        objectiveIds=R6_OBJECTIVE_IDS,
        scenarioIds=(R6_DEFAULT_SCENARIO_ID,),
        realityValidationStatus="Open",
    )


@lru_cache(maxsize=1)
def load_r6_scenario(scenario_id: str = R6_DEFAULT_SCENARIO_ID) -> R6Scenario:
    if scenario_id != R6_DEFAULT_SCENARIO_ID:
        raise KeyError(f"unknown R6 scenario: {scenario_id}")
    search_request = OptimizationSearchRequest()
    recommendations = search_recommendations(search_request)
    summary = R6ScenarioSummary(
        scenarioId=R6_DEFAULT_SCENARIO_ID,
        title="Canonical head-table offline Pareto search",
        description=(
            "Replans feed derating and M5 sampling across six evidence-backed candidates; "
            "all recommendations remain Offline and reality validation stays Open."
        ),
        expectedOutcome="Passed",
        permissionLevel="Offline",
    )
    run_spec = {
        "subjectId": "axiom.optimization.r6.offline-recommender@1",
        "domainPackId": R6_DOMAIN_PACK_ID,
        "runnerId": R6_RUNNER_ID,
        "evaluatorVersion": R6_EVALUATOR_ID,
        "request": {
            "artifact": recommendations.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "searchSpec": search_request.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "case": {
                "caseId": "optimization.r6.offline-recommendation.case@1",
                "requiredMetrics": [
                    INTEGRITY_METRIC_ID,
                    HARD_CONSTRAINT_METRIC_ID,
                    {
                        "metricId": PARETO_COUNT_METRIC_ID,
                        "threshold": {"operator": ">=", "value": 1},
                    },
                    OFFLINE_BOUNDARY_METRIC_ID,
                ],
                "optionalMetrics": [REALITY_VALIDATION_METRIC_ID],
            },
        },
    }
    RunSpec.model_validate(run_spec)
    return R6Scenario(
        summary=summary,
        search_request=search_request,
        recommendation_set=recommendations,
        run_spec=run_spec,
    )


def list_r6_scenarios() -> tuple[R6ScenarioSummary, ...]:
    return (load_r6_scenario().summary,)


def r6_example_payload(scenario_id: str = R6_DEFAULT_SCENARIO_ID) -> R6ExamplePayload:
    scenario = load_r6_scenario(scenario_id)
    return R6ExamplePayload(
        manifest=build_r6_manifest(),
        scenario=scenario.summary,
        searchRequest=scenario.search_request,
        recommendationSet=scenario.recommendation_set,
        runSpec=scenario.run_spec,
    )


def r6_example_run_spec(scenario_id: str = R6_DEFAULT_SCENARIO_ID) -> dict[str, Any]:
    return load_r6_scenario(scenario_id).run_spec


def validate_r6_example_run_spec(scenario_id: str = R6_DEFAULT_SCENARIO_ID) -> RunSpec:
    return RunSpec.model_validate(r6_example_run_spec(scenario_id))


def build_r6_run_spec(search_request: OptimizationSearchRequest) -> RunSpec:
    recommendations = search_recommendations(search_request)
    payload = load_r6_scenario().run_spec.copy()
    payload["request"] = dict(payload["request"])
    payload["request"]["artifact"] = recommendations.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    payload["request"]["searchSpec"] = search_request.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    return RunSpec.model_validate(payload)


__all__ = [
    "build_r6_manifest",
    "build_r6_run_spec",
    "list_r6_scenarios",
    "load_r6_scenario",
    "r6_example_payload",
    "r6_example_run_spec",
    "validate_r6_example_run_spec",
]
