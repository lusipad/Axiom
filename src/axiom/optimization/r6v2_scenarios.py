from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
import json
from typing import Any

from ..models import RunSpec
from .models import R6_OBJECTIVE_IDS
from .r6v2_models import (
    R6V2_DEFAULT_SCENARIO_ID,
    R6V2_DOMAIN_PACK_ID,
    R6V2_EVALUATOR_ID,
    R6V2_EXACT_VALIDATION_BUDGET,
    R6V2_RUNNER_ID,
    R6V2_SCENARIO_IDS,
    R6V2_SCREENING_CANDIDATE_COUNT,
    R6V2ExamplePayload,
    R6V2Manifest,
    R6V2Scenario,
    R6V2ScenarioSummary,
    R6V2SearchRequest,
    RecommendationSetV2,
)
from .r6v2_runtime import (
    EXACT_FEASIBLE_COUNT_METRIC_ID,
    EXACT_INTEGRITY_METRIC_ID,
    EXACT_VALIDATION_COUNT_METRIC_ID,
    OFFLINE_BOUNDARY_METRIC_ID,
    REALITY_VALIDATION_METRIC_ID,
    SCREENING_CONTRACT_METRIC_ID,
)
from .r6v2_search import (
    build_r6v2_search_request,
    search_r6v2_recommendations,
)


_SCENARIO_COPY = {
    "canonical-goal-conditioned-speed": (
        "Goal-conditioned speed search",
        "Minimize exact cycle time subject to linear following-error and command-count limits.",
    ),
    "canonical-goal-conditioned-quality": (
        "Goal-conditioned quality search",
        "Minimize exact linear following error subject to cycle-time and command-count limits.",
    ),
    "canonical-goal-conditioned-compact-command": (
        "Goal-conditioned compact-command search",
        "Minimize exact command count subject to cycle-time and linear following-error limits.",
    ),
}


def build_r6v2_manifest() -> R6V2Manifest:
    return R6V2Manifest(
        manifestId="optimization.r6v2-manifest@1",
        schemaId="optimization.r6v2-manifest@1",
        schemaVersion=2,
        domainPackId=R6V2_DOMAIN_PACK_ID,
        evaluatorVersion=R6V2_EVALUATOR_ID,
        runnerId=R6V2_RUNNER_ID,
        supportedPlatforms=("Windows",),
        parameterIds=("feedOverride", "samplePeriod"),
        objectiveIds=R6_OBJECTIVE_IDS,
        scenarioIds=R6V2_SCENARIO_IDS,
        screeningCandidateCount=R6V2_SCREENING_CANDIDATE_COUNT,
        exactValidationBudget=R6V2_EXACT_VALIDATION_BUDGET,
        optimalityScope="best-observed-within-exact-validation-budget",
        globalOptimalityStatus="NotClaimed",
        permissionLevel="Offline",
        deviceWriteAllowed=False,
        realityValidationStatus="Open",
    )


def _summary(search_request: R6V2SearchRequest) -> R6V2ScenarioSummary:
    title, description = _SCENARIO_COPY[search_request.scenario_id]
    return R6V2ScenarioSummary(
        scenarioId=search_request.scenario_id,
        title=title,
        description=description,
        primaryObjectiveId=search_request.intent.primary_objective_id,
        expectedOutcome="Passed",
        permissionLevel="Offline",
        globalOptimalityStatus="NotClaimed",
    )


def build_r6v2_run_spec(
    search_request: R6V2SearchRequest,
    recommendation_set: RecommendationSetV2 | None = None,
) -> RunSpec:
    recommendations = recommendation_set or search_r6v2_recommendations(
        search_request
    )
    payload = {
        "subjectId": "axiom.optimization.r6v2.offline-recommender@1",
        "domainPackId": R6V2_DOMAIN_PACK_ID,
        "runnerId": R6V2_RUNNER_ID,
        "evaluatorVersion": R6V2_EVALUATOR_ID,
        "request": {
            "artifact": recommendations.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "searchSpec": search_request.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "case": {
                "caseId": (
                    f"optimization.r6v2.{search_request.scenario_id}.case@1"
                ),
                "requiredMetrics": [
                    SCREENING_CONTRACT_METRIC_ID,
                    EXACT_INTEGRITY_METRIC_ID,
                    {
                        "metricId": EXACT_VALIDATION_COUNT_METRIC_ID,
                        "threshold": {"operator": "<=", "value": 27},
                    },
                    {
                        "metricId": EXACT_FEASIBLE_COUNT_METRIC_ID,
                        "threshold": {"operator": ">=", "value": 1},
                    },
                    OFFLINE_BOUNDARY_METRIC_ID,
                ],
                "optionalMetrics": [REALITY_VALIDATION_METRIC_ID],
            },
        },
    }
    return RunSpec.model_validate(payload)


@lru_cache(maxsize=3)
def load_r6v2_scenario(
    scenario_id: str = R6V2_DEFAULT_SCENARIO_ID,
) -> R6V2Scenario:
    if scenario_id not in R6V2_SCENARIO_IDS:
        raise KeyError(f"unknown R6 v2 scenario: {scenario_id}")
    search_request = build_r6v2_search_request(scenario_id)
    recommendations = search_r6v2_recommendations(search_request)
    run_spec = build_r6v2_run_spec(search_request, recommendations)
    return R6V2Scenario(
        summary=_summary(search_request),
        search_request=search_request,
        recommendation_set=recommendations,
        run_spec=run_spec.model_dump(mode="json", by_alias=True, exclude_none=True),
    )


def list_r6v2_scenarios() -> tuple[R6V2ScenarioSummary, ...]:
    return tuple(load_r6v2_scenario(scenario_id).summary for scenario_id in R6V2_SCENARIO_IDS)


def load_r6v2_fixture_manifest() -> dict[str, Any]:
    resource = files("axiom.optimization").joinpath(
        "fixtures", "r6v2-manifest.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def r6v2_payload_for_request(
    search_request: R6V2SearchRequest,
) -> R6V2ExamplePayload:
    recommendations = search_r6v2_recommendations(search_request)
    run_spec = build_r6v2_run_spec(search_request, recommendations)
    return R6V2ExamplePayload(
        manifest=build_r6v2_manifest(),
        scenario=_summary(search_request),
        searchRequest=search_request,
        recommendationSet=recommendations,
        runSpec=run_spec.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
    )


def r6v2_example_payload(
    scenario_id: str = R6V2_DEFAULT_SCENARIO_ID,
) -> R6V2ExamplePayload:
    scenario = load_r6v2_scenario(scenario_id)
    return R6V2ExamplePayload(
        manifest=build_r6v2_manifest(),
        scenario=scenario.summary,
        searchRequest=scenario.search_request,
        recommendationSet=scenario.recommendation_set,
        runSpec=scenario.run_spec,
    )


def r6v2_example_run_spec(
    scenario_id: str = R6V2_DEFAULT_SCENARIO_ID,
) -> dict[str, Any]:
    return load_r6v2_scenario(scenario_id).run_spec


def validate_r6v2_example_run_spec(
    scenario_id: str = R6V2_DEFAULT_SCENARIO_ID,
) -> RunSpec:
    return RunSpec.model_validate(r6v2_example_run_spec(scenario_id))


__all__ = [
    "build_r6v2_manifest",
    "build_r6v2_run_spec",
    "list_r6v2_scenarios",
    "load_r6v2_fixture_manifest",
    "load_r6v2_scenario",
    "r6v2_example_payload",
    "r6v2_example_run_spec",
    "r6v2_payload_for_request",
    "validate_r6v2_example_run_spec",
]
