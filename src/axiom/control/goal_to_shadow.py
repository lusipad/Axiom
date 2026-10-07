from __future__ import annotations

import math
import platform
from typing import Any, Literal

from pydantic import Field, model_validator

from ..five_axis.f3_sampling import M5DiscreteCommand
from ..models import AxiomModel
from ..optimization import (
    R6V2ExactCandidate,
    R6V2SearchRequest,
    RecommendationSetV2,
    evaluate_r6v2_parameter_point,
    search_r6v2_recommendations,
)
from ..optimization.models import canonical_hash as optimization_hash
from ..physical import CanonicalParameterPointEvaluation, PhysicalResponseTrace
from .models import (
    ControlledRuntimeAudit,
    RuntimeSpec,
    ShadowSample,
    ShadowTrace,
    canonical_hash,
)
from .r7a2_models import (
    RecommendationEvidenceProjection,
    build_recommendation_evidence_projection,
)
from .runner import build_control_envelope, run_shadow

GOAL_TO_SHADOW_ADAPTER_ID = "axiom.adapter.r4-response-to-r7a-shadow@1"
GOAL_TO_SHADOW_POLICY_ID = "axiom.control.exact-physical-sample-shadow@1"
_HASH_PATTERN = r"^[0-9a-f]{64}$"


class GoalToShadowRequest(AxiomModel):
    search_request: R6V2SearchRequest = Field(alias="searchRequest")
    candidate_id: str | None = Field(
        default=None, alias="candidateId", pattern=r"^.+@[0-9]+$"
    )


class PhysicalShadowProjection(AxiomModel):
    artifact_type: Literal["axiom.control.physical-shadow-projection"] = Field(
        alias="artifactType"
    )
    schema_id: Literal["axiom.control.physical-shadow-projection@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    projection_id: str = Field(alias="projectionId", pattern=r"^.+@[0-9]+$")
    adapter_id: Literal["axiom.adapter.r4-response-to-r7a-shadow@1"] = Field(
        alias="adapterId"
    )
    policy_id: Literal["axiom.control.exact-physical-sample-shadow@1"] = Field(
        alias="policyId"
    )
    candidate_id: str = Field(alias="candidateId", pattern=r"^.+@[0-9]+$")
    candidate_content_hash: str = Field(
        alias="candidateContentHash", pattern=_HASH_PATTERN
    )
    candidate_m4_content_hash: str = Field(
        alias="candidateM4ContentHash", pattern=_HASH_PATTERN
    )
    source_command_m4_content_id: str = Field(
        alias="sourceCommandM4ContentId", pattern=_HASH_PATTERN
    )
    source_m5_content_hash: str = Field(
        alias="sourceM5ContentHash", pattern=_HASH_PATTERN
    )
    source_physical_response_content_hash: str = Field(
        alias="sourcePhysicalResponseContentHash", pattern=_HASH_PATTERN
    )
    source_command: M5DiscreteCommand = Field(alias="sourceCommand")
    physical_response: PhysicalResponseTrace = Field(alias="physicalResponse")
    shadow_trace: ShadowTrace = Field(alias="shadowTrace")
    sample_count: int = Field(alias="sampleCount", ge=2)
    alignment: Literal["exact-sample-index-time-and-command"]
    interpolation_applied: Literal[False] = Field(alias="interpolationApplied")
    linear_axis_ids: tuple[Literal["X", "Y", "Z"], ...] = Field(
        alias="linearAxisIds", min_length=3, max_length=3
    )
    linear_axis_unit: Literal["mm"] = Field(alias="linearAxisUnit")
    excluded_rotary_axis_ids: tuple[Literal["B", "C"], ...] = Field(
        alias="excludedRotaryAxisIds", min_length=2, max_length=2
    )
    ood_projection_policy: Literal["candidate-constant-per-sample"] = Field(
        alias="oodProjectionPolicy"
    )
    candidate_ood_fraction: float = Field(alias="candidateOodFraction", ge=0.0, le=1.0)
    maximum_linear_following_error_mm: float = Field(
        alias="maximumLinearFollowingErrorMm", ge=0.0
    )
    source_kind: Literal["synthetic-sil"] = Field(alias="sourceKind")
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_exact_projection(self) -> PhysicalShadowProjection:
        if self.linear_axis_ids != ("X", "Y", "Z"):
            raise ValueError("linearAxisIds must preserve X/Y/Z order")
        if self.excluded_rotary_axis_ids != ("B", "C"):
            raise ValueError("excludedRotaryAxisIds must preserve B/C order")
        if self.candidate_m4_content_hash != optimization_hash(
            self.source_command.source_m4
        ):
            raise ValueError("candidate M4 content identity mismatch")
        if (
            self.source_command_m4_content_id
            != self.source_command.source_m4_content_id
        ):
            raise ValueError("source command M4 content identity mismatch")
        if self.source_m5_content_hash != self.source_command.content_id:
            raise ValueError("source M5 content identity mismatch")
        response = self.physical_response
        if (
            self.source_physical_response_content_hash != response.content_hash
            or response.source_command_content_id != self.source_m5_content_hash
        ):
            raise ValueError("physical response content identity mismatch")
        if response.axis_units != ("mm", "mm", "mm", "rad", "rad"):
            raise ValueError("physical response must preserve X/Y/Z/B/C units")
        if not (
            self.sample_count
            == len(self.source_command.samples)
            == len(response.samples)
            == len(self.shadow_trace.samples)
        ):
            raise ValueError("exact projection sample count mismatch")
        derived_maximum = 0.0
        for command, physical, shadow in zip(
            self.source_command.samples,
            response.samples,
            self.shadow_trace.samples,
            strict=True,
        ):
            if (
                command.sample_index != physical.sample_index
                or command.sample_index != shadow.sequence
                or not math.isclose(command.t, physical.t, abs_tol=1e-12)
                or not math.isclose(command.t, shadow.time_seconds, abs_tol=1e-12)
                or tuple(command.q) != tuple(physical.command)
            ):
                raise ValueError("exact projection sample binding mismatch")
            error = max(
                abs(float(physical.command[index]) - float(physical.simulated[index]))
                for index in range(3)
            )
            if not math.isclose(shadow.linear_following_error_mm, error, abs_tol=1e-12):
                raise ValueError("Shadow linear following error mismatch")
            if not math.isclose(
                shadow.ood_fraction, self.candidate_ood_fraction, abs_tol=1e-12
            ):
                raise ValueError("Shadow OOD projection mismatch")
            derived_maximum = max(derived_maximum, error)
        if not math.isclose(
            self.maximum_linear_following_error_mm,
            derived_maximum,
            abs_tol=1e-12,
        ):
            raise ValueError("maximum linear following error mismatch")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match PhysicalShadowProjection")
        return self


class GoalToShadowReport(AxiomModel):
    artifact_type: Literal["axiom.control.goal-to-shadow-report"] = Field(
        alias="artifactType"
    )
    schema_id: Literal["axiom.control.goal-to-shadow-report@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    report_id: str = Field(alias="reportId", pattern=r"^.+@[0-9]+$")
    status: Literal["Passed", "Blocked"]
    reason_codes: tuple[str, ...] = Field(alias="reasonCodes")
    current_platform: str = Field(alias="currentPlatform", min_length=1)
    source_search_request_hash: str = Field(
        alias="sourceSearchRequestHash", pattern=_HASH_PATTERN
    )
    selected_candidate_id: str | None = Field(
        default=None, alias="selectedCandidateId", pattern=r"^.+@[0-9]+$"
    )
    recommendation_set: RecommendationSetV2 | None = Field(
        default=None, alias="recommendationSet"
    )
    recommendation_projection: RecommendationEvidenceProjection | None = Field(
        default=None, alias="recommendationProjection"
    )
    physical_shadow_projection: PhysicalShadowProjection | None = Field(
        default=None, alias="physicalShadowProjection"
    )
    runtime_spec: RuntimeSpec | None = Field(default=None, alias="runtimeSpec")
    runtime_audit: ControlledRuntimeAudit | None = Field(
        default=None, alias="runtimeAudit"
    )
    synthetic_sil_status: Literal["Passed", "Blocked"] = Field(
        alias="syntheticSilStatus"
    )
    deployment_shadow_status: Literal["Open"] = Field(alias="deploymentShadowStatus")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(alias="processSafetyStatus")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    automatic_acceptance_allowed: Literal[False] = Field(
        alias="automaticAcceptanceAllowed"
    )
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_report(self) -> GoalToShadowReport:
        downstream = (
            self.recommendation_projection,
            self.physical_shadow_projection,
            self.runtime_spec,
            self.runtime_audit,
        )
        if self.status == "Passed":
            if self.reason_codes or any(item is None for item in downstream):
                raise ValueError("Passed report requires the complete downstream chain")
            assert self.recommendation_set is not None
            assert self.selected_candidate_id is not None
            assert self.recommendation_projection is not None
            assert self.physical_shadow_projection is not None
            assert self.runtime_spec is not None
            assert self.runtime_audit is not None
            candidate = next(
                (
                    item
                    for item in self.recommendation_set.exact_candidates
                    if item.candidate_id == self.selected_candidate_id
                ),
                None,
            )
            if candidate is None or not candidate.recommendation_eligible:
                raise ValueError("Passed report requires an exact-eligible candidate")
            if (
                self.current_platform != "Windows"
                or self.source_search_request_hash
                != canonical_hash(self.recommendation_set.search_request)
                or self.recommendation_projection.candidate_id
                != self.selected_candidate_id
                or self.recommendation_projection.candidate_content_hash
                != candidate.content_hash
                or self.physical_shadow_projection.candidate_id
                != self.selected_candidate_id
                or self.physical_shadow_projection.candidate_content_hash
                != candidate.content_hash
                or self.runtime_spec.candidate_id != self.selected_candidate_id
                or self.runtime_spec.recommendation_set_content_hash
                != self.recommendation_set.content_hash
                or self.runtime_spec.trace.content_hash
                != self.physical_shadow_projection.shadow_trace.content_hash
                or self.runtime_audit.runtime_spec_id
                != self.runtime_spec.runtime_spec_id
                or self.runtime_audit.admission_decision.status != "Admitted"
            ):
                raise ValueError("Goal-to-Shadow downstream identity mismatch")
        else:
            if not self.reason_codes:
                raise ValueError("Blocked report requires at least one reasonCode")
            if any(item is not None for item in downstream):
                raise ValueError("Blocked report must not expose a downstream chain")
        if self.synthetic_sil_status != self.status:
            raise ValueError("syntheticSilStatus must match report status")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match GoalToShadowReport")
        return self


class GoalToShadowProjectionError(ValueError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def _record(model_type: type[AxiomModel], payload: dict[str, Any]) -> Any:
    sealed = {key: value for key, value in payload.items() if value is not None}
    sealed["contentHash"] = canonical_hash(sealed)
    return model_type.model_validate(sealed)


def build_physical_shadow_projection(
    recommendation: RecommendationSetV2,
    candidate: R6V2ExactCandidate,
    point: CanonicalParameterPointEvaluation,
) -> PhysicalShadowProjection:
    bound_candidate = next(
        (
            item
            for item in recommendation.exact_candidates
            if item.candidate_id == candidate.candidate_id
        ),
        None,
    )
    if bound_candidate is None:
        raise GoalToShadowProjectionError(
            "ExactCandidateMissing", "candidate is not in the exact validation set"
        )
    if bound_candidate.content_hash != candidate.content_hash:
        raise GoalToShadowProjectionError(
            "ExactCandidateIdentityMismatch",
            "candidate content does not match the exact validation set",
        )
    checks = (
        (
            optimization_hash(point.continuous_trajectory) == candidate.m4_content_hash,
            "ExactReplayM4IdentityMismatch",
        ),
        (
            point.command.content_id == candidate.m5_content_hash,
            "ExactReplayM5IdentityMismatch",
        ),
        (
            point.response.content_hash == candidate.physical_response_content_hash,
            "ExactReplayPhysicalResponseIdentityMismatch",
        ),
    )
    for passed, reason_code in checks:
        if not passed:
            raise GoalToShadowProjectionError(
                reason_code, "exact candidate replay content identity mismatch"
            )
    if not (
        len(point.command.samples) == len(point.response.samples)
        and len(point.response.samples) >= 2
    ):
        raise GoalToShadowProjectionError(
            "ExactReplaySampleCountMismatch",
            "command and response sample counts differ",
        )
    shadow_samples: list[ShadowSample] = []
    for command, response in zip(
        point.command.samples, point.response.samples, strict=True
    ):
        if (
            command.sample_index != response.sample_index
            or not math.isclose(command.t, response.t, abs_tol=1e-12)
            or tuple(command.q) != tuple(response.command)
        ):
            raise GoalToShadowProjectionError(
                "ExactReplaySampleBindingMismatch",
                "command and response samples are not exactly aligned",
            )
        shadow_samples.append(
            ShadowSample(
                sequence=response.sample_index,
                timeSeconds=response.t,
                linearFollowingErrorMm=max(
                    abs(
                        float(response.command[index])
                        - float(response.simulated[index])
                    )
                    for index in range(3)
                ),
                oodFraction=candidate.ood_fraction,
                sourceKind="synthetic-shadow",
            )
        )
    trace_payload = {
        "traceId": f"control.goal-to-shadow.trace.{candidate.candidate_id}",
        "sourceKind": "synthetic-shadow",
        "samples": [
            item.model_dump(mode="json", by_alias=True) for item in shadow_samples
        ],
    }
    trace = ShadowTrace.model_validate(
        {**trace_payload, "contentHash": canonical_hash(trace_payload)}
    )
    maximum = max(item.linear_following_error_mm for item in shadow_samples)
    if not math.isclose(
        maximum,
        candidate.objectives.linear_following_error_max_mm,
        abs_tol=1e-12,
    ):
        raise GoalToShadowProjectionError(
            "ExactReplayLinearErrorMismatch",
            "projected maximum linear error differs from the exact candidate",
        )
    payload: dict[str, Any] = {
        "artifactType": "axiom.control.physical-shadow-projection",
        "schemaId": "axiom.control.physical-shadow-projection@1",
        "schemaVersion": 1,
        "projectionId": f"control.goal-to-shadow.physical.{candidate.candidate_id}",
        "adapterId": GOAL_TO_SHADOW_ADAPTER_ID,
        "policyId": GOAL_TO_SHADOW_POLICY_ID,
        "candidateId": candidate.candidate_id,
        "candidateContentHash": candidate.content_hash,
        "candidateM4ContentHash": candidate.m4_content_hash,
        "sourceCommandM4ContentId": point.command.source_m4_content_id,
        "sourceM5ContentHash": point.command.content_id,
        "sourcePhysicalResponseContentHash": point.response.content_hash,
        "sourceCommand": point.command,
        "physicalResponse": point.response,
        "shadowTrace": trace,
        "sampleCount": len(shadow_samples),
        "alignment": "exact-sample-index-time-and-command",
        "interpolationApplied": False,
        "linearAxisIds": ("X", "Y", "Z"),
        "linearAxisUnit": "mm",
        "excludedRotaryAxisIds": ("B", "C"),
        "oodProjectionPolicy": "candidate-constant-per-sample",
        "candidateOodFraction": candidate.ood_fraction,
        "maximumLinearFollowingErrorMm": maximum,
        "sourceKind": "synthetic-sil",
    }
    return _record(PhysicalShadowProjection, payload)


def _report(
    request: GoalToShadowRequest,
    *,
    current_platform: str,
    status: Literal["Passed", "Blocked"],
    reasons: tuple[str, ...],
    selected_candidate_id: str | None = None,
    recommendation: RecommendationSetV2 | None = None,
    recommendation_projection: RecommendationEvidenceProjection | None = None,
    physical_projection: PhysicalShadowProjection | None = None,
    runtime_spec: RuntimeSpec | None = None,
    runtime_audit: ControlledRuntimeAudit | None = None,
) -> GoalToShadowReport:
    report_suffix = (
        selected_candidate_id or request.search_request.scenario_id
    ).replace("@", "-")
    payload: dict[str, Any] = {
        "artifactType": "axiom.control.goal-to-shadow-report",
        "schemaId": "axiom.control.goal-to-shadow-report@1",
        "schemaVersion": 1,
        "reportId": f"control.goal-to-shadow.report.{report_suffix}@1",
        "status": status,
        "reasonCodes": reasons,
        "currentPlatform": current_platform,
        "sourceSearchRequestHash": canonical_hash(request.search_request),
        "selectedCandidateId": selected_candidate_id,
        "recommendationSet": recommendation,
        "recommendationProjection": recommendation_projection,
        "physicalShadowProjection": physical_projection,
        "runtimeSpec": runtime_spec,
        "runtimeAudit": runtime_audit,
        "syntheticSilStatus": status,
        "deploymentShadowStatus": "Open",
        "realityValidationStatus": "Open",
        "controlledTrialStatus": "Open",
        "closedLoopStatus": "Open",
        "deviceSafetyStatus": "NotAssessed",
        "processSafetyStatus": "NotAssessed",
        "deviceWriteAllowed": False,
        "automaticAcceptanceAllowed": False,
    }
    return _record(GoalToShadowReport, payload)


def rehearse_goal_to_shadow(
    request: GoalToShadowRequest,
    *,
    current_platform: str | None = None,
) -> GoalToShadowReport:
    resolved_platform = current_platform or platform.system()
    if resolved_platform != "Windows":
        return _report(
            request,
            current_platform=resolved_platform,
            status="Blocked",
            reasons=("UnsupportedRuntimePlatform",),
            selected_candidate_id=request.candidate_id,
        )
    recommendation = search_r6v2_recommendations(request.search_request)
    candidate_id = request.candidate_id
    if candidate_id is None:
        if not recommendation.best_observed_candidate_ids:
            return _report(
                request,
                current_platform=resolved_platform,
                status="Blocked",
                reasons=("BestObservedCandidateUnavailable",),
                recommendation=recommendation,
            )
        candidate_id = recommendation.best_observed_candidate_ids[0]
    candidate = next(
        (
            item
            for item in recommendation.exact_candidates
            if item.candidate_id == candidate_id
        ),
        None,
    )
    if candidate is None:
        return _report(
            request,
            current_platform=resolved_platform,
            status="Blocked",
            reasons=("ExactCandidateMissing",),
            selected_candidate_id=candidate_id,
            recommendation=recommendation,
        )
    if not candidate.recommendation_eligible:
        return _report(
            request,
            current_platform=resolved_platform,
            status="Blocked",
            reasons=("ExactCandidateIneligible",),
            selected_candidate_id=candidate_id,
            recommendation=recommendation,
        )
    feed_override = float(candidate.parameter_set.values["feedOverride"])
    sample_period = float(candidate.parameter_set.values["samplePeriod"])
    point = evaluate_r6v2_parameter_point(
        feed_override=feed_override,
        sample_period=sample_period,
    )
    try:
        physical_projection = build_physical_shadow_projection(
            recommendation, candidate, point
        )
    except GoalToShadowProjectionError as exc:
        return _report(
            request,
            current_platform=resolved_platform,
            status="Blocked",
            reasons=(exc.reason_code,),
            selected_candidate_id=candidate_id,
            recommendation=recommendation,
        )
    recommendation_projection = build_recommendation_evidence_projection(
        recommendation, candidate_id
    )
    candidate_stem = candidate_id.rsplit("@", 1)[0]
    scenario_id = f"goal-to-shadow.{candidate_stem}"
    runtime_spec = RuntimeSpec(
        schemaId="control.runtime-spec@1",
        runtimeSpecId=f"control.goal-to-shadow.runtime-spec.{candidate_stem}@1",
        scenarioId=scenario_id,
        requestedPermission="Shadow",
        deviceWriteRequested=False,
        candidateId=candidate_id,
        recommendationSetContentHash=recommendation.content_hash,
        envelope=build_control_envelope(
            baseline_parameter_set_id=(
                recommendation.validation_plan.rollback_parameter_set_id
            )
        ),
        trace=physical_projection.shadow_trace,
        requireDeploymentShadowEvidence=False,
    )
    runtime_audit = run_shadow(runtime_spec, recommendation, recommendation_projection)
    return _report(
        request,
        current_platform=resolved_platform,
        status="Passed",
        reasons=(),
        selected_candidate_id=candidate_id,
        recommendation=recommendation,
        recommendation_projection=recommendation_projection,
        physical_projection=physical_projection,
        runtime_spec=runtime_spec,
        runtime_audit=runtime_audit,
    )


__all__ = [
    "GOAL_TO_SHADOW_ADAPTER_ID",
    "GOAL_TO_SHADOW_POLICY_ID",
    "GoalToShadowProjectionError",
    "GoalToShadowReport",
    "GoalToShadowRequest",
    "PhysicalShadowProjection",
    "build_physical_shadow_projection",
    "rehearse_goal_to_shadow",
]
