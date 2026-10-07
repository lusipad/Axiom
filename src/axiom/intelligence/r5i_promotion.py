from __future__ import annotations

import hashlib
import hmac
import platform
from collections.abc import Mapping
from datetime import datetime
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel

from ..control.r7e_models import R7EEvaluationRequest
from .models import canonical_hash
from .r5g_models import R5GModelPromotionReadinessDossier
from .r5g_readiness import prepare_r5g_model_promotion_readiness
from .r5h_holdout import assess_r5h_candidate_real_holdout
from .r5h_models import R5HCandidateHoldoutAssessment
from .r5i_models import (
    R5I_PREFLIGHT_CHECK_IDS,
    R5I_SAFETY_BANNER,
    R5IManifest,
    R5IPromotionDecision,
    R5IPromotionPreflightCheck,
    R5IPromotionPreflightReport,
    R5IPromotionPreflightRequest,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _seal(model_type: type[_ModelT], payload: dict[str, Any]) -> _ModelT:
    draft = {**payload, "contentHash": "0" * 64}
    provisional = model_type.model_construct(**draft)
    draft["contentHash"] = canonical_hash(
        provisional,
        exclude={"content_hash"},
    )
    return model_type.model_validate(draft)


def _authorization_proof(signed_body_hash: str, authority_key: bytes) -> str:
    return hmac.new(
        authority_key,
        signed_body_hash.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


@lru_cache(maxsize=4)
def _replay_dossier_json(payload: str) -> str:
    dossier = R5GModelPromotionReadinessDossier.model_validate_json(payload)
    return prepare_r5g_model_promotion_readiness(
        dossier.request,
        current_platform="Windows",
    ).content_hash


@lru_cache(maxsize=4)
def _replay_holdout_json(payload: str) -> str:
    assessment = R5HCandidateHoldoutAssessment.model_validate_json(payload)
    return assess_r5h_candidate_real_holdout(
        assessment.request,
        current_platform="Windows",
    ).content_hash


def build_r5i_manifest() -> R5IManifest:
    return R5IManifest(
        manifestId="axiom.intelligence.r5i-manifest@1",
        schemaId="axiom.intelligence.r5i-manifest@1",
        schemaVersion=1,
        stage="R5-I",
        platform="windows",
        lifecycleScope="local-conditional-effect-model",
        registryKind="sqlite-local",
        sourceDossierSchemaId=(
            "axiom.intelligence.model-promotion-readiness-dossier@1"
        ),
        sourceHoldoutSchemaId=(
            "axiom.intelligence.candidate-real-holdout-assessment@1"
        ),
        promotionDecisionSchemaId="axiom.intelligence.promotion-decision@1",
        checkIds=R5I_PREFLIGHT_CHECK_IDS,
        webStateMutationAllowed=False,
        localCliTransactionRequired=True,
        automaticModelPromotionAllowed=False,
        automaticRollbackAllowed=False,
        automaticDeploymentAllowed=False,
        deviceWriteAllowed=False,
        safetyBanner=R5I_SAFETY_BANNER,
    )


def build_r5i_promotion_decision(
    dossier: R5GModelPromotionReadinessDossier,
    holdout_assessment: R5HCandidateHoldoutAssessment,
    *,
    decision_id: str,
    decision: str,
    decided_by: str,
    decided_at: str,
    authority_key_id: str,
    authority_key: bytes,
) -> R5IPromotionDecision:
    if not isinstance(authority_key, bytes) or len(authority_key) < 16:
        raise ValueError("authority key must contain at least 16 bytes")
    body = {
        "schemaId": "axiom.intelligence.promotion-decision@1",
        "schemaVersion": 1,
        "decisionId": decision_id,
        "dossierContentHash": dossier.content_hash,
        "holdoutAssessmentContentHash": holdout_assessment.content_hash,
        "candidateModelBundleHash": dossier.candidate_model_bundle_hash,
        "rollbackBaselineModelBundleHash": dossier.baseline_model_bundle_hash,
        "decision": decision,
        "decidedBy": decided_by,
        "decidedAt": decided_at,
        "authorityKeyId": authority_key_id,
    }
    signed_body_hash = canonical_hash(body)
    return _seal(
        R5IPromotionDecision,
        {
            **body,
            "signedBodyHash": signed_body_hash,
            "authorizationProof": _authorization_proof(
                signed_body_hash,
                authority_key,
            ),
        },
    )


def build_r5i_preflight_request(
    dossier: R5GModelPromotionReadinessDossier,
    holdout_assessment: R5HCandidateHoldoutAssessment,
    promotion_decision: R5IPromotionDecision,
) -> R5IPromotionPreflightRequest:
    return _seal(
        R5IPromotionPreflightRequest,
        {
            "schemaId": "axiom.intelligence.promotion-preflight-request@1",
            "schemaVersion": 1,
            "readinessDossier": dossier,
            "holdoutAssessment": holdout_assessment,
            "promotionDecision": promotion_decision,
            "platform": "windows",
        },
    )


def _check(
    check_id: str,
    *,
    passed: bool,
    reason_code: str,
    evidence: Any,
) -> R5IPromotionPreflightCheck:
    return R5IPromotionPreflightCheck(
        checkId=check_id,
        status="Passed" if passed else "Blocked",
        evidenceHash=canonical_hash(
            {
                "checkId": check_id,
                "passed": passed,
                "reasonCode": reason_code,
                "evidence": evidence,
            }
        ),
        reasonCode=reason_code,
    )


def _latest_validation_close(
    assessment: R5HCandidateHoldoutAssessment,
) -> datetime | None:
    closed: list[datetime] = []
    for report in assessment.request.evidence_reports:
        request = R7EEvaluationRequest.model_validate(
            report.validation_assessment.run_spec["request"]
        )
        if request.shadow_evidence is None:
            return None
        closed.append(datetime.fromisoformat(request.shadow_evidence.receipt.closed_at))
    return max(closed) if closed else None


def _blocked_platform_checks(
    request: R5IPromotionPreflightRequest,
    current_platform: str,
) -> tuple[R5IPromotionPreflightCheck, ...]:
    checks = [
        _check(
            R5I_PREFLIGHT_CHECK_IDS[0],
            passed=False,
            reason_code="UnsupportedRuntimePlatform",
            evidence={"currentPlatform": current_platform, "required": "Windows"},
        )
    ]
    checks.extend(
        _check(
            check_id,
            passed=False,
            reason_code="RuntimePlatformPrerequisiteBlocked",
            evidence={"requestContentHash": request.content_hash},
        )
        for check_id in R5I_PREFLIGHT_CHECK_IDS[1:]
    )
    return tuple(checks)


def preflight_r5i_model_promotion(
    request: R5IPromotionPreflightRequest,
    *,
    authority_keys: Mapping[str, bytes],
    current_platform: str | None = None,
) -> R5IPromotionPreflightReport:
    request = R5IPromotionPreflightRequest.model_validate(
        request.model_dump(mode="json", by_alias=True)
    )
    runtime_platform = current_platform or platform.system()
    dossier = request.readiness_dossier
    assessment = request.holdout_assessment
    decision = request.promotion_decision

    if runtime_platform.lower() != "windows":
        checks = _blocked_platform_checks(request, runtime_platform)
    else:
        platform_check = _check(
            R5I_PREFLIGHT_CHECK_IDS[0],
            passed=True,
            reason_code="WindowsRuntimeMatched",
            evidence={"currentPlatform": runtime_platform},
        )

        try:
            holdout_replayed = _replay_holdout_json(
                assessment.model_dump_json(by_alias=True)
            ) == assessment.content_hash
        except (TypeError, ValueError):
            holdout_replayed = False
        holdout_passed = (
            holdout_replayed
            and assessment.overall_status == "Passed"
            and assessment.real_world_generalization_status == "CaseScopedPassed"
        )
        holdout_check = _check(
            R5I_PREFLIGHT_CHECK_IDS[1],
            passed=holdout_passed,
            reason_code=(
                "CaseScopedHoldoutPassed"
                if holdout_passed
                else "CaseScopedHoldoutRequired"
            ),
            evidence={
                "assessmentContentHash": assessment.content_hash,
                "replayed": holdout_replayed,
                "overallStatus": assessment.overall_status,
                "realWorldGeneralizationStatus": (
                    assessment.real_world_generalization_status
                ),
            },
        )

        try:
            dossier_replayed = _replay_dossier_json(
                dossier.model_dump_json(by_alias=True)
            ) == dossier.content_hash
        except (TypeError, ValueError):
            dossier_replayed = False
        dossier_passed = (
            dossier_replayed
            and dossier.review_readiness_status == "ReadyForIndependentReview"
        )
        dossier_check = _check(
            R5I_PREFLIGHT_CHECK_IDS[2],
            passed=dossier_passed,
            reason_code=(
                "PromotionDossierReplayed"
                if dossier_passed
                else "PromotionDossierNotReady"
            ),
            evidence={
                "dossierContentHash": dossier.content_hash,
                "replayed": dossier_replayed,
                "reviewReadinessStatus": dossier.review_readiness_status,
            },
        )

        lineage_passed = (
            assessment.readiness_dossier_content_hash == dossier.content_hash
            and assessment.request.readiness_dossier.content_hash == dossier.content_hash
            and assessment.baseline_model_bundle_hash
            == dossier.baseline_model_bundle_hash
            and assessment.candidate_model_bundle_hash
            == dossier.candidate_model_bundle_hash
            and decision.dossier_content_hash == dossier.content_hash
            and decision.holdout_assessment_content_hash == assessment.content_hash
            and decision.candidate_model_bundle_hash
            == dossier.candidate_model_bundle_hash
            and decision.rollback_baseline_model_bundle_hash
            == dossier.baseline_model_bundle_hash
        )
        lineage_check = _check(
            R5I_PREFLIGHT_CHECK_IDS[3],
            passed=lineage_passed,
            reason_code=(
                "EvidenceLineageBound" if lineage_passed else "EvidenceLineageMismatch"
            ),
            evidence={
                "dossierContentHash": dossier.content_hash,
                "assessmentContentHash": assessment.content_hash,
                "decisionContentHash": decision.content_hash,
                "candidateModelBundleHash": dossier.candidate_model_bundle_hash,
                "rollbackBaselineModelBundleHash": (
                    dossier.baseline_model_bundle_hash
                ),
            },
        )

        reviewer = decision.decided_by.strip().casefold()
        preparer = dossier.request.prepared_by.strip().casefold()
        registrant = (
            assessment.request.study_registration.registration_authority_id
            .strip()
            .casefold()
        )
        reviewer_passed = reviewer not in {preparer, registrant}
        reviewer_check = _check(
            R5I_PREFLIGHT_CHECK_IDS[4],
            passed=reviewer_passed,
            reason_code=(
                "IndependentReviewerVerified"
                if reviewer_passed
                else "IndependentReviewerRequired"
            ),
            evidence={
                "decidedBy": decision.decided_by,
                "preparedBy": dossier.request.prepared_by,
                "registrationAuthorityId": (
                    assessment.request.study_registration.registration_authority_id
                ),
            },
        )

        authority_key = authority_keys.get(decision.authority_key_id)
        key_available = (
            isinstance(authority_key, bytes) and len(authority_key) >= 16
        )
        proof_passed = bool(
            key_available
            and hmac.compare_digest(
                decision.authorization_proof,
                _authorization_proof(decision.signed_body_hash, authority_key),
            )
        )
        proof_reason = (
            "AuthorizationProofVerified"
            if proof_passed
            else "AuthorizationProofMismatch"
            if key_available
            else "AuthorityKeyUnavailable"
        )
        proof_check = _check(
            R5I_PREFLIGHT_CHECK_IDS[5],
            passed=proof_passed,
            reason_code=proof_reason,
            evidence={
                "authorityKeyId": decision.authority_key_id,
                "signedBodyHash": decision.signed_body_hash,
                "keyAvailable": key_available,
            },
        )

        latest_close = _latest_validation_close(assessment)
        decision_time = datetime.fromisoformat(decision.decided_at)
        chronology_passed = latest_close is not None and decision_time > latest_close
        chronology_check = _check(
            R5I_PREFLIGHT_CHECK_IDS[6],
            passed=chronology_passed,
            reason_code=(
                "DecisionAfterEvidence"
                if chronology_passed
                else "DecisionMustFollowCompletedEvidence"
            ),
            evidence={
                "decidedAt": decision.decided_at,
                "latestValidationClosedAt": (
                    latest_close.isoformat() if latest_close is not None else None
                ),
            },
        )
        checks = (
            platform_check,
            holdout_check,
            dossier_check,
            lineage_check,
            reviewer_check,
            proof_check,
            chronology_check,
        )

    all_passed = all(check.status == "Passed" for check in checks)
    overall = (
        "Blocked"
        if not all_passed
        else "Rejected"
        if decision.decision == "Reject"
        else "Passed"
    )
    review_status = (
        "Invalid"
        if not all_passed
        else "Rejected"
        if decision.decision == "Reject"
        else "Approved"
    )
    return _seal(
        R5IPromotionPreflightReport,
        {
            "schemaId": "axiom.intelligence.promotion-preflight-report@1",
            "schemaVersion": 1,
            "requestContentHash": request.content_hash,
            "dossierContentHash": dossier.content_hash,
            "holdoutAssessmentContentHash": assessment.content_hash,
            "promotionDecisionContentHash": decision.content_hash,
            "candidateModelBundleHash": dossier.candidate_model_bundle_hash,
            "rollbackBaselineModelBundleHash": dossier.baseline_model_bundle_hash,
            "checks": checks,
            "overallStatus": overall,
            "promotionTransactionStatus": {
                "Passed": "Eligible",
                "Blocked": "Blocked",
                "Rejected": "Rejected",
            }[overall],
            "reviewDecisionStatus": review_status,
            "authorizationVerified": checks[5].status == "Passed",
            "registryTransactionAllowed": overall == "Passed",
            "realWorldGeneralizationStatus": (
                assessment.real_world_generalization_status
            ),
            "modelPromotionStatus": "NotPerformed",
            "modelRegistryWritePerformed": False,
            "activationPerformed": False,
            "defaultModelChanged": False,
            "automaticModelPromotionAllowed": False,
            "automaticDeploymentAllowed": False,
            "deviceWriteAllowed": False,
            "permissionLevel": "Offline",
            "safetyBanner": R5I_SAFETY_BANNER,
        },
    )


__all__ = [
    "build_r5i_manifest",
    "build_r5i_preflight_request",
    "build_r5i_promotion_decision",
    "preflight_r5i_model_promotion",
]
