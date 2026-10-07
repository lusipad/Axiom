from __future__ import annotations

import json
import platform
from importlib.resources import files
from typing import Any

from .models import canonical_hash
from .r5f_impact import assess_r5f_candidate_downstream_impact
from .r5f_models import R5FCandidateImpactReport
from .r5g_models import (
    R5G_READINESS_CHECK_IDS,
    R5G_REMAINING_GATE_IDS,
    R5G_SAFETY_BANNER,
    R5GManifest,
    R5GModelPromotionReadinessDossier,
    R5GPromotionReadinessRequest,
)


def _seal(model_type: type[Any], payload: dict[str, Any]) -> Any:
    payload["contentHash"] = canonical_hash(payload)
    return model_type.model_validate(payload)


def _identities(impact: R5FCandidateImpactReport) -> tuple[str, str, str]:
    baseline_hashes = {
        item.baseline_recommendation.search_request.surrogate_context.model_bundle.content_hash
        for item in impact.scenario_impacts
    }
    candidate_contexts = {
        item.candidate_recommendation.search_request.surrogate_context.context_hash: (
            item.candidate_recommendation.search_request.surrogate_context.model_bundle.content_hash
        )
        for item in impact.scenario_impacts
    }
    if len(baseline_hashes) != 1 or len(candidate_contexts) != 1:
        raise ValueError("R5-G requires one baseline and one candidate lineage")
    context_hash, candidate_hash = next(iter(candidate_contexts.items()))
    return next(iter(baseline_hashes)), candidate_hash, context_hash


def build_r5g_manifest() -> R5GManifest:
    return R5GManifest(
        manifestId="axiom.intelligence.r5g-manifest@1",
        schemaId="axiom.intelligence.r5g-manifest@1",
        schemaVersion=1,
        stage="R5-G",
        platform="windows",
        reviewScope="synthetic-offline-review",
        reviewReadinessStatus="ReadyForIndependentReview",
        reviewDecisionStatus="AwaitingIndependentHumanDecision",
        automaticModelPromotionAllowed=False,
        modelRegistryWriteAllowed=False,
        defaultModelChangeAllowed=False,
        realWorldGeneralizationStatus="Open",
        permissionLevel="Offline",
        deviceWriteAllowed=False,
        safetyBanner=R5G_SAFETY_BANNER,
    )


def build_r5g_promotion_readiness_request(
    impact_report: R5FCandidateImpactReport,
    *,
    prepared_by: str,
) -> R5GPromotionReadinessRequest:
    baseline_hash, _, _ = _identities(impact_report)
    return _seal(
        R5GPromotionReadinessRequest,
        {
            "schemaId": "axiom.intelligence.model-promotion-readiness-request@1",
            "requestId": "axiom.intelligence.r5g.promotion-readiness-request@1",
            "impactReport": impact_report.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "preparedBy": prepared_by,
            "reviewScope": "synthetic-offline-review",
            "rollbackBaselineModelBundleHash": baseline_hash,
            "acknowledgements": {
                "realityGateOpenAcknowledged": True,
                "deviceSafetyNotEstablishedAcknowledged": True,
                "automaticDeploymentForbiddenAcknowledged": True,
            },
        },
    )


def prepare_r5g_model_promotion_readiness(
    request: R5GPromotionReadinessRequest,
    *,
    current_platform: str | None = None,
) -> R5GModelPromotionReadinessDossier:
    runtime_platform = current_platform or platform.system()
    if runtime_platform.casefold() != "windows":
        raise ValueError("R5-G model promotion readiness only supports Windows")

    validated_request = R5GPromotionReadinessRequest.model_validate(
        request.model_dump(mode="json", by_alias=True)
    )
    source_impact = validated_request.impact_report
    replay = assess_r5f_candidate_downstream_impact(
        source_impact.source_campaign_report,
        current_platform="Windows",
    )
    if replay.content_hash != source_impact.content_hash:
        raise ValueError("R5-G source impact report cannot be reproduced")

    baseline_hash, candidate_hash, context_hash = _identities(replay)
    check_evidence = (
        replay.source_campaign_report.candidate_assessment.content_hash,
        replay.content_hash,
        replay.content_hash,
        context_hash,
        baseline_hash,
    )
    check_statuses = (
        "Passed",
        "Passed" if replay.impact_gate_status == "Passed" else "Blocked",
        "Passed",
        "Passed",
        "Passed",
    )
    checks = [
        {
            "checkId": check_id,
            "status": status,
            "evidenceHash": evidence_hash,
            "reasonCode": (
                "EvidenceSatisfied" if status == "Passed" else "ImpactGateFailed"
            ),
        }
        for check_id, status, evidence_hash in zip(
            R5G_READINESS_CHECK_IDS,
            check_statuses,
            check_evidence,
            strict=True,
        )
    ]
    remaining_gates = [
        {
            "gateId": gate_id,
            "status": "Open",
            "reasonCode": "ExternalPromotionEvidenceRequired",
        }
        for gate_id in R5G_REMAINING_GATE_IDS
    ]
    readiness_status = (
        "ReadyForIndependentReview"
        if all(status == "Passed" for status in check_statuses)
        else "Blocked"
    )
    return _seal(
        R5GModelPromotionReadinessDossier,
        {
            "schemaId": "axiom.intelligence.model-promotion-readiness-dossier@1",
            "dossierId": "axiom.intelligence.r5g.promotion-readiness-dossier@1",
            "request": validated_request.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "sourceCampaignReportHash": replay.source_campaign_report.content_hash,
            "sourceImpactReportHash": source_impact.content_hash,
            "replayedImpactReportHash": replay.content_hash,
            "baselineModelBundleHash": baseline_hash,
            "candidateModelBundleHash": candidate_hash,
            "candidateContextHash": context_hash,
            "readinessChecks": checks,
            "remainingGates": remaining_gates,
            "reviewReadinessStatus": readiness_status,
            "reviewDecisionStatus": "AwaitingIndependentHumanDecision",
            "candidateUseStatus": "EvaluatedOnly",
            "modelPromotionStatus": "NotPerformed",
            "realWorldGeneralizationStatus": "Open",
            "permissionLevel": "Offline",
            "defaultModelChanged": False,
            "modelRegistryWritePerformed": False,
            "activationPerformed": False,
            "automaticDeploymentAllowed": False,
            "deviceWriteAllowed": False,
            "safetyBanner": R5G_SAFETY_BANNER,
        },
    )


def load_r5g_fixture_manifest() -> dict[str, Any]:
    resource = files("axiom.intelligence").joinpath("fixtures", "r5g-manifest.json")
    return json.loads(resource.read_text(encoding="utf-8"))


__all__ = [
    "build_r5g_manifest",
    "build_r5g_promotion_readiness_request",
    "load_r5g_fixture_manifest",
    "prepare_r5g_model_promotion_readiness",
]
