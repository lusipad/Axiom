from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel, EvaluationCase, ParameterSet
from ..physical.applicability import PhysicalMultirateApplicabilityEvidence

R6_DOMAIN_PACK_ID = "optimization.domain-pack@1"
R6_EVALUATOR_ID = "optimization-evaluator@1"
R6_RUNNER_ID = "optimization-offline-search@1"
R6_DEFAULT_SCENARIO_ID = "canonical-head-table-offline-pareto"

R6_GATE_IDS = (
    "five-axis.geometry-valid-claim@1",
    "five-axis.task-geometry-collision-free-claim@1",
    "five-axis.kinematically-feasible-claim@1",
    "five-axis.configuration-collision-free-claim@1",
    "five-axis.continuously-feasible-claim@1",
    "five-axis.interval-certified-claim@1",
    "five-axis.model-collision-free-claim@1",
)
R6_OBJECTIVE_IDS = (
    "cycleTimeSeconds",
    "linearFollowingErrorMaxMm",
    "commandSampleCount",
)
R6_FEED_OVERRIDES = (0.70, 0.85, 1.00)
R6_SAMPLE_PERIODS = (0.04, 0.08)


def canonical_hash(payload: Any, *, exclude: set[str] | None = None) -> str:
    if isinstance(payload, AxiomModel):
        payload = payload.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude=exclude or set()
        )
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _finite(value: Any) -> Any:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ValueError("value must be a finite JSON number")
    return value


class OptimizationGoal(AxiomModel):
    goal_id: str = Field(
        default="optimization.r6.balanced-goal@1",
        alias="goalId",
        pattern=r"^.+@[0-9]+$",
    )
    objective_ids: tuple[str, str, str] = Field(
        default=R6_OBJECTIVE_IDS, alias="objectiveIds"
    )
    maximum_cycle_time_seconds: float | None = Field(
        default=None, alias="maximumCycleTimeSeconds", gt=0.0
    )
    maximum_linear_following_error_mm: float | None = Field(
        default=None, alias="maximumLinearFollowingErrorMm", gt=0.0
    )
    maximum_command_sample_count: int | None = Field(
        default=None, alias="maximumCommandSampleCount", ge=2
    )

    @field_validator(
        "maximum_cycle_time_seconds", "maximum_linear_following_error_mm", mode="before"
    )
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return value if value is None else _finite(value)

    @model_validator(mode="after")
    def require_frozen_objectives(self) -> OptimizationGoal:
        if self.objective_ids != R6_OBJECTIVE_IDS:
            raise ValueError(
                "objectiveIds must preserve the frozen unweighted R6 objective vector"
            )
        return self


class OptimizationParameterGrid(AxiomModel):
    feed_overrides: tuple[float, ...] = Field(
        default=R6_FEED_OVERRIDES, alias="feedOverrides", min_length=1
    )
    sample_periods: tuple[float, ...] = Field(
        default=R6_SAMPLE_PERIODS, alias="samplePeriods", min_length=1
    )

    @field_validator("feed_overrides", "sample_periods", mode="before")
    @classmethod
    def reject_non_finite_entries(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            for item in value:
                _finite(item)
        return value

    @model_validator(mode="after")
    def require_frozen_search_domain(self) -> OptimizationParameterGrid:
        if tuple(sorted(set(self.feed_overrides))) != self.feed_overrides:
            raise ValueError("feedOverrides must be unique and ascending")
        if tuple(sorted(set(self.sample_periods))) != self.sample_periods:
            raise ValueError("samplePeriods must be unique and ascending")
        if not set(self.feed_overrides).issubset(R6_FEED_OVERRIDES):
            raise ValueError(
                "feedOverrides must be selected from the validated R6 grid"
            )
        if not set(self.sample_periods).issubset(R6_SAMPLE_PERIODS):
            raise ValueError(
                "samplePeriods must be selected from the validated R6 grid"
            )
        return self


class OptimizationSearchRequest(AxiomModel):
    schema_id: Literal["optimization.search-request@1"] = Field(
        default="optimization.search-request@1", alias="schemaId"
    )
    scenario_id: Literal["canonical-head-table-offline-pareto"] = Field(
        default=R6_DEFAULT_SCENARIO_ID, alias="scenarioId"
    )
    goal: OptimizationGoal = Field(default_factory=OptimizationGoal)
    grid: OptimizationParameterGrid = Field(default_factory=OptimizationParameterGrid)


class OptimizationObjectiveVector(AxiomModel):
    cycle_time_seconds: float = Field(alias="cycleTimeSeconds", gt=0.0)
    linear_following_error_max_mm: float = Field(
        alias="linearFollowingErrorMaxMm", ge=0.0
    )
    command_sample_count: int = Field(alias="commandSampleCount", ge=2)

    @field_validator(
        "cycle_time_seconds", "linear_following_error_max_mm", mode="before"
    )
    @classmethod
    def reject_non_finite(cls, value: Any) -> Any:
        return _finite(value)


class OptimizationGateReceipt(AxiomModel):
    claim_id: str = Field(alias="claimId")
    status: Literal["Supported", "Refuted", "Inconclusive"]
    evidence_content_hash: str = Field(
        alias="evidenceContentHash", pattern=r"^[0-9a-f]{64}$"
    )
    method: str = Field(min_length=1)
    reason_code: str | None = Field(default=None, alias="reasonCode")


class OptimizationCandidate(AxiomModel):
    candidate_id: str = Field(alias="candidateId", pattern=r"^.+@[0-9]+$")
    parameter_set: ParameterSet = Field(alias="parameterSet")
    objectives: OptimizationObjectiveVector
    gate_receipts: tuple[OptimizationGateReceipt, ...] = Field(
        alias="gateReceipts", min_length=7, max_length=7
    )
    physical_applicability_passed: bool = Field(alias="physicalApplicabilityPassed")
    hard_constraints_satisfied: bool = Field(alias="hardConstraintsSatisfied")
    goal_feasible: bool = Field(alias="goalFeasible")
    pareto_optimal: bool = Field(alias="paretoOptimal")
    m4_content_hash: str = Field(alias="m4ContentHash", pattern=r"^[0-9a-f]{64}$")
    m5_content_hash: str = Field(alias="m5ContentHash", pattern=r"^[0-9a-f]{64}$")
    physical_response_content_hash: str = Field(
        alias="physicalResponseContentHash", pattern=r"^[0-9a-f]{64}$"
    )
    ood_fraction: float = Field(alias="oodFraction", ge=0.0, le=1.0)
    epistemic_status: Literal["InDomain", "PartiallyOutOfDomain", "Unavailable"] = (
        Field(alias="epistemicStatus")
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    promotion_eligible: Literal[False] = Field(alias="promotionEligible")
    explanation: str = Field(min_length=1)
    candidate_content_hash: str = Field(
        alias="candidateContentHash", pattern=r"^[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def require_gate_and_content_consistency(self) -> OptimizationCandidate:
        if tuple(receipt.claim_id for receipt in self.gate_receipts) != R6_GATE_IDS:
            raise ValueError(
                "gateReceipts must exactly cover the seven frozen R6 mathematical gates"
            )
        expected_hard = self.physical_applicability_passed and all(
            receipt.status == "Supported" for receipt in self.gate_receipts
        )
        if self.hard_constraints_satisfied != expected_hard:
            raise ValueError(
                "hardConstraintsSatisfied must be derived from all hard gates"
            )
        payload = self.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
            exclude={"candidate_content_hash"},
        )
        if self.candidate_content_hash != canonical_hash(payload):
            raise ValueError("candidateContentHash must match candidate content")
        return self


class OptimizationValidationPlan(AxiomModel):
    plan_id: Literal["optimization.r6.offline-validation-plan@1"] = Field(
        alias="planId"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    remaining_gates: tuple[str, ...] = Field(alias="remainingGates", min_length=1)
    stop_conditions: tuple[str, ...] = Field(alias="stopConditions", min_length=1)
    rollback_parameter_set_id: str = Field(
        alias="rollbackParameterSetId", pattern=r"^.+@[0-9]+$"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")


class RecommendationSet(AxiomModel):
    artifact_type: Literal["axiom.optimization.recommendation-set"] = Field(
        alias="artifactType"
    )
    schema_id: Literal["axiom.optimization.recommendation-set@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    recommendation_set_id: Literal["axiom.optimization.r6.canonical-head-table@1"] = (
        Field(alias="recommendationSetId")
    )
    search_request: OptimizationSearchRequest = Field(alias="searchRequest")
    baseline_parameter_set: ParameterSet = Field(alias="baselineParameterSet")
    candidates: tuple[OptimizationCandidate, ...] = Field(min_length=1)
    pareto_candidate_ids: tuple[str, ...] = Field(alias="paretoCandidateIds")
    physical_applicability_evidence: PhysicalMultirateApplicabilityEvidence = Field(
        alias="physicalApplicabilityEvidence"
    )
    validation_plan: OptimizationValidationPlan = Field(alias="validationPlan")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    automatic_acceptance_allowed: Literal[False] = Field(
        alias="automaticAcceptanceAllowed"
    )
    shadow_status: Literal["Open"] = Field(alias="shadowStatus")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")
    content_hash: str = Field(alias="contentHash", pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_pareto_and_content_identity(self) -> RecommendationSet:
        expected = tuple(
            candidate.candidate_id
            for candidate in self.candidates
            if candidate.pareto_optimal
        )
        if self.pareto_candidate_ids != expected:
            raise ValueError(
                "paretoCandidateIds must identify exactly the Pareto candidates"
            )
        payload = self.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude={"content_hash"}
        )
        if self.content_hash != canonical_hash(payload):
            raise ValueError("contentHash must match RecommendationSet content")
        return self


class OptimizationEvaluationRequest(AxiomModel):
    artifact: RecommendationSet
    search_spec: OptimizationSearchRequest = Field(alias="searchSpec")
    case: EvaluationCase

    @model_validator(mode="after")
    def bind_search_request(self) -> OptimizationEvaluationRequest:
        if self.artifact.search_request != self.search_spec:
            raise ValueError("artifact searchRequest must match searchSpec")
        return self


class R6Manifest(AxiomModel):
    manifest_id: Literal["optimization.r6-manifest@1"] = Field(alias="manifestId")
    domain_pack_id: Literal["optimization.domain-pack@1"] = Field(alias="domainPackId")
    evaluator_version: Literal["optimization-evaluator@1"] = Field(
        alias="evaluatorVersion"
    )
    runner_id: Literal["optimization-offline-search@1"] = Field(alias="runnerId")
    supported_platforms: tuple[Literal["Windows"], ...] = Field(
        alias="supportedPlatforms"
    )
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    parameter_ids: tuple[str, str] = Field(alias="parameterIds")
    objective_ids: tuple[str, str, str] = Field(alias="objectiveIds")
    scenario_ids: tuple[str, ...] = Field(alias="scenarioIds")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")


class R6ScenarioSummary(AxiomModel):
    scenario_id: str = Field(alias="scenarioId")
    title: str
    description: str
    expected_outcome: Literal["Passed"] = Field(alias="expectedOutcome")
    permission_level: Literal["Offline"] = Field(alias="permissionLevel")


class R6ExamplePayload(AxiomModel):
    manifest: R6Manifest
    scenario: R6ScenarioSummary
    search_request: OptimizationSearchRequest = Field(alias="searchRequest")
    recommendation_set: RecommendationSet = Field(alias="recommendationSet")
    run_spec: dict[str, Any] = Field(alias="runSpec")


@dataclass(frozen=True)
class R6Scenario:
    summary: R6ScenarioSummary
    search_request: OptimizationSearchRequest
    recommendation_set: RecommendationSet
    run_spec: dict[str, Any]


__all__ = [
    "R6_DEFAULT_SCENARIO_ID",
    "R6_DOMAIN_PACK_ID",
    "R6_EVALUATOR_ID",
    "R6_FEED_OVERRIDES",
    "R6_GATE_IDS",
    "R6_OBJECTIVE_IDS",
    "R6_RUNNER_ID",
    "R6_SAMPLE_PERIODS",
    "OptimizationCandidate",
    "OptimizationEvaluationRequest",
    "OptimizationGateReceipt",
    "OptimizationGoal",
    "OptimizationObjectiveVector",
    "OptimizationParameterGrid",
    "OptimizationSearchRequest",
    "OptimizationValidationPlan",
    "R6ExamplePayload",
    "R6Manifest",
    "R6Scenario",
    "R6ScenarioSummary",
    "RecommendationSet",
    "canonical_hash",
]
