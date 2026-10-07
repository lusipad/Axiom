from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, model_validator

from ..models import AxiomModel, EvaluationCase
from ..optimization import RecommendationSetV2
from .models import ControlledRuntimeAudit, RuntimeSpec, canonical_hash

R7A2_DEFAULT_SCENARIO_ID = "r6v2-shadow-nominal"
R7A2_SCENARIO_IDS = (
    R7A2_DEFAULT_SCENARIO_ID,
    "r6v2-exact-eligible-non-best",
    "r6v2-shadow-limit-breach",
    "r6v2-exact-ineligible-blocked",
    "r6v2-handoff-missing-blocked",
    "r6v2-device-write-request-blocked",
)
R7A2_RECOMMENDATION_ADAPTER_ID = "axiom.adapter.r6v2-to-r7a-shadow@1"

HASH_PATTERN = r"^[0-9a-f]{64}$"
SelectionClass = Literal[
    "BestObserved",
    "ParetoWithinValidated",
    "ExactEligible",
    "ExactIneligible",
]


class RecommendationEvidenceProjection(AxiomModel):
    artifact_type: Literal["axiom.control.recommendation-evidence-projection"] = Field(
        alias="artifactType"
    )
    schema_id: Literal["axiom.control.recommendation-evidence-projection@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    projection_id: str = Field(alias="projectionId", pattern=r"^.+@[0-9]+$")
    adapter_id: Literal["axiom.adapter.r6v2-to-r7a-shadow@1"] = Field(alias="adapterId")
    source_recommendation_schema_id: Literal[
        "axiom.optimization.recommendation-set@2"
    ] = Field(alias="sourceRecommendationSchemaId")
    source_recommendation_set_content_hash: str = Field(
        alias="sourceRecommendationSetContentHash", pattern=HASH_PATTERN
    )
    source_search_request_hash: str = Field(
        alias="sourceSearchRequestHash", pattern=HASH_PATTERN
    )
    surrogate_context_hash: str = Field(
        alias="surrogateContextHash", pattern=HASH_PATTERN
    )
    screening_receipt_content_hash: str = Field(
        alias="screeningReceiptContentHash", pattern=HASH_PATTERN
    )
    candidate_id: str = Field(alias="candidateId", pattern=r"^.+@[0-9]+$")
    candidate_content_hash: str = Field(
        alias="candidateContentHash", pattern=HASH_PATTERN
    )
    screening_estimate_content_hash: str = Field(
        alias="screeningEstimateContentHash", pattern=HASH_PATTERN
    )
    source_candidate_status: Literal["ExactEligible", "ExactIneligible"] = Field(
        alias="sourceCandidateStatus"
    )
    selection_class: SelectionClass = Field(alias="selectionClass")
    target_use: Literal["SyntheticShadowAdmission"] = Field(alias="targetUse")
    source_permission_level: Literal["Offline"] = Field(alias="sourcePermissionLevel")
    target_permission_ceiling: Literal["Shadow"] = Field(
        alias="targetPermissionCeiling"
    )
    automatic_acceptance_allowed: Literal[False] = Field(
        alias="automaticAcceptanceAllowed"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    optimality_scope: Literal["best-observed-within-exact-validation-budget"] = Field(
        alias="optimalityScope"
    )
    global_optimality_status: Literal["NotClaimed"] = Field(
        alias="globalOptimalityStatus"
    )
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> RecommendationEvidenceProjection:
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match RecommendationEvidenceProjection")
        return self


def _selection_class(
    recommendation: RecommendationSetV2, candidate_id: str, *, eligible: bool
) -> SelectionClass:
    if not eligible:
        return "ExactIneligible"
    if candidate_id in recommendation.best_observed_candidate_ids:
        return "BestObserved"
    if candidate_id in recommendation.pareto_candidate_ids:
        return "ParetoWithinValidated"
    return "ExactEligible"


def build_recommendation_evidence_projection(
    recommendation: RecommendationSetV2, candidate_id: str
) -> RecommendationEvidenceProjection:
    candidate = next(
        (
            item
            for item in recommendation.exact_candidates
            if item.candidate_id == candidate_id
        ),
        None,
    )
    if candidate is None:
        raise KeyError(f"candidate is not in exact validation set: {candidate_id}")
    eligible = candidate.recommendation_eligible
    payload = {
        "artifactType": "axiom.control.recommendation-evidence-projection",
        "schemaId": "axiom.control.recommendation-evidence-projection@1",
        "schemaVersion": 1,
        "projectionId": f"control.r7a2.projection.{candidate_id.rsplit('@', 1)[0]}@1",
        "adapterId": R7A2_RECOMMENDATION_ADAPTER_ID,
        "sourceRecommendationSchemaId": recommendation.schema_id,
        "sourceRecommendationSetContentHash": recommendation.content_hash,
        "sourceSearchRequestHash": canonical_hash(recommendation.search_request),
        "surrogateContextHash": recommendation.surrogate_context_hash,
        "screeningReceiptContentHash": recommendation.screening_receipt.content_hash,
        "candidateId": candidate.candidate_id,
        "candidateContentHash": candidate.content_hash,
        "screeningEstimateContentHash": candidate.screening_estimate_content_hash,
        "sourceCandidateStatus": ("ExactEligible" if eligible else "ExactIneligible"),
        "selectionClass": _selection_class(
            recommendation, candidate.candidate_id, eligible=eligible
        ),
        "targetUse": "SyntheticShadowAdmission",
        "sourcePermissionLevel": recommendation.permission_level,
        "targetPermissionCeiling": "Shadow",
        "automaticAcceptanceAllowed": False,
        "deviceWriteAllowed": False,
        "optimalityScope": recommendation.optimality_scope,
        "globalOptimalityStatus": recommendation.global_optimality_status,
    }
    payload["contentHash"] = canonical_hash(payload)
    return RecommendationEvidenceProjection.model_validate(payload)


def recommendation_projection_reason_codes(
    recommendation: RecommendationSetV2,
    candidate_id: str,
    projection: RecommendationEvidenceProjection | None,
) -> tuple[str, ...]:
    if projection is None:
        return ("RecommendationHandoffMissing",)
    candidate = next(
        (
            item
            for item in recommendation.exact_candidates
            if item.candidate_id == candidate_id
        ),
        None,
    )
    if candidate is None:
        return ("RecommendationCandidateMissing",)
    expected_status = (
        "ExactEligible" if candidate.recommendation_eligible else "ExactIneligible"
    )
    expected_selection = _selection_class(
        recommendation,
        candidate.candidate_id,
        eligible=candidate.recommendation_eligible,
    )
    matches = (
        projection.source_recommendation_set_content_hash == recommendation.content_hash
        and projection.source_search_request_hash
        == canonical_hash(recommendation.search_request)
        and projection.surrogate_context_hash == recommendation.surrogate_context_hash
        and projection.screening_receipt_content_hash
        == recommendation.screening_receipt.content_hash
        and projection.candidate_id == candidate_id
        and projection.candidate_content_hash == candidate.content_hash
        and projection.screening_estimate_content_hash
        == candidate.screening_estimate_content_hash
        and projection.source_candidate_status == expected_status
        and projection.selection_class == expected_selection
    )
    return () if matches else ("RecommendationHandoffIdentityMismatch",)


class R7A2EvaluationRequest(AxiomModel):
    artifact: ControlledRuntimeAudit
    runtime_spec: RuntimeSpec = Field(alias="runtimeSpec")
    recommendation_set: RecommendationSetV2 = Field(alias="recommendationSet")
    recommendation_projection: RecommendationEvidenceProjection | None = Field(
        default=None, alias="recommendationProjection"
    )
    case: EvaluationCase

    @model_validator(mode="after")
    def bind_context(self) -> R7A2EvaluationRequest:
        if self.runtime_spec.runtime_spec_id != self.artifact.runtime_spec_id:
            raise ValueError("runtimeSpecId must bind the audit")
        if (
            self.runtime_spec.recommendation_set_content_hash
            != self.recommendation_set.content_hash
        ):
            raise ValueError("RecommendationSet content identity mismatch")
        reasons = recommendation_projection_reason_codes(
            self.recommendation_set,
            self.runtime_spec.candidate_id,
            self.recommendation_projection,
        )
        if reasons and reasons != ("RecommendationHandoffMissing",):
            raise ValueError(
                "recommendationProjection candidateId/content identity mismatch"
            )
        return self


class R7A2Manifest(AxiomModel):
    manifest_id: Literal["control.r7a-v2-manifest@1"] = Field(alias="manifestId")
    domain_pack_id: Literal["control.domain-pack@1"] = Field(alias="domainPackId")
    evaluator_version: Literal["control-shadow-evaluator@1"] = Field(
        alias="evaluatorVersion"
    )
    runner_id: Literal["control-synthetic-shadow-replay@1"] = Field(alias="runnerId")
    source_recommendation_schema_id: Literal[
        "axiom.optimization.recommendation-set@2"
    ] = Field(alias="sourceRecommendationSchemaId")
    projection_schema_id: Literal[
        "axiom.control.recommendation-evidence-projection@1"
    ] = Field(alias="projectionSchemaId")
    supported_platforms: tuple[Literal["Windows"], ...] = Field(
        alias="supportedPlatforms"
    )
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    scenario_ids: tuple[str, ...] = Field(alias="scenarioIds")
    handoff_contract_status: Literal["Passed"] = Field(alias="handoffContractStatus")
    synthetic_shadow_contract_status: Literal["Passed"] = Field(
        alias="syntheticShadowContractStatus"
    )
    deployment_shadow_status: Literal["Open"] = Field(alias="deploymentShadowStatus")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")


class R7A2ScenarioSummary(AxiomModel):
    scenario_id: str = Field(alias="scenarioId")
    title: str
    description: str
    expected_outcome: Literal["Passed"] = Field(alias="expectedOutcome")
    expected_final_state: str = Field(alias="expectedFinalState")


class R7A2ExamplePayload(AxiomModel):
    manifest: R7A2Manifest
    scenario: R7A2ScenarioSummary
    recommendation_set: RecommendationSetV2 = Field(alias="recommendationSet")
    recommendation_projection: RecommendationEvidenceProjection | None = Field(
        alias="recommendationProjection"
    )
    runtime_spec: RuntimeSpec = Field(alias="runtimeSpec")
    runtime_audit: ControlledRuntimeAudit = Field(alias="runtimeAudit")
    run_spec: dict[str, Any] = Field(alias="runSpec")


class R7A2ReplayRequest(AxiomModel):
    scenario_id: str = Field(default=R7A2_DEFAULT_SCENARIO_ID, alias="scenarioId")


@dataclass(frozen=True)
class R7A2Scenario:
    summary: R7A2ScenarioSummary
    recommendation_set: RecommendationSetV2
    recommendation_projection: RecommendationEvidenceProjection | None
    runtime_spec: RuntimeSpec
    runtime_audit: ControlledRuntimeAudit
    run_spec: dict[str, Any]


__all__ = [
    "R7A2_DEFAULT_SCENARIO_ID",
    "R7A2_RECOMMENDATION_ADAPTER_ID",
    "R7A2_SCENARIO_IDS",
    "R7A2EvaluationRequest",
    "R7A2ExamplePayload",
    "R7A2Manifest",
    "R7A2ReplayRequest",
    "R7A2Scenario",
    "R7A2ScenarioSummary",
    "RecommendationEvidenceProjection",
    "build_recommendation_evidence_projection",
    "recommendation_projection_reason_codes",
]
