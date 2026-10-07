from __future__ import annotations

import hashlib
import math
import platform
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from ..control.r7e_models import R7EAssessmentRequest, R7EExamplePayload
from ..field_evidence import (
    FieldEvidenceAssessmentReport,
    FieldEvidenceAssessmentRequest,
    assess_field_evidence,
)
from ..physical import (
    build_r4_multirate_physical_model,
    evaluate_canonical_parameter_point,
)
from .models import canonical_hash
from .r5c_interpreter import predict_conditional_effect
from .r5c_models import ConditionalEffectPredictionRequest
from .r5g_models import R5GModelPromotionReadinessDossier
from .r5g_readiness import prepare_r5g_model_promotion_readiness
from .r5h_models import (
    R5H_CHECK_IDS,
    R5H_SAFETY_BANNER,
    R5HCandidateHoldoutAssessment,
    R5HCandidateHoldoutAssessmentRequest,
    R5HCandidateHoldoutCasePlan,
    R5HCandidateHoldoutCaseResult,
    R5HCandidateHoldoutCaseSpec,
    R5HCandidateHoldoutCheck,
    R5HCandidateHoldoutStudyManifest,
    R5HCandidateHoldoutStudyRegistration,
    R5HCandidateHoldoutStudyRegistrationReport,
    R5HCandidateHoldoutStudyRegistrationRequest,
    R5HCaseTargetResult,
    R5HExactOperatingPoint,
    R5HManifest,
    R5HPredictionValue,
    R5HTargetAssessmentResult,
    _linear_actual_from_report,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)
_EPSILON = 1e-12


def _seal(model_type: type[_ModelT], payload: dict[str, Any]) -> _ModelT:
    draft = {**payload, "contentHash": "0" * 64}
    provisional = model_type.model_construct(**draft)
    draft["contentHash"] = canonical_hash(
        provisional,
        exclude={"content_hash"},
    )
    return model_type.model_validate(draft)


def _require_windows(current_platform: str) -> None:
    if current_platform.lower() != "windows":
        raise ValueError("R5-H candidate real holdout only supports Windows")


def _model_bundles(dossier: R5GModelPromotionReadinessDossier) -> tuple[Any, Any]:
    first = dossier.request.impact_report.scenario_impacts[0]
    baseline = (
        first.baseline_recommendation.search_request.surrogate_context.model_bundle
    )
    candidate = (
        first.candidate_recommendation.search_request.surrogate_context.model_bundle
    )
    if baseline.content_hash != dossier.baseline_model_bundle_hash:
        raise ValueError("R5-H baseline model must match readiness dossier")
    if candidate.content_hash != dossier.candidate_model_bundle_hash:
        raise ValueError("R5-H candidate model must match readiness dossier")
    return baseline, candidate


def _replay_dossier(dossier: R5GModelPromotionReadinessDossier) -> bool:
    replayed = prepare_r5g_model_promotion_readiness(
        dossier.request,
        current_platform="Windows",
    )
    return replayed.content_hash == dossier.content_hash


def _case_token(case: R5HCandidateHoldoutCaseSpec) -> str:
    encoded = (
        f"{case.case_id}|{case.feed_override:.15g}|{case.sample_period:.15g}"
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _evaluate_operating_point(
    case: R5HCandidateHoldoutCaseSpec,
    *,
    physical_model: Any,
) -> Any:
    token = _case_token(case)
    return evaluate_canonical_parameter_point(
        physical_model,
        feed_override=case.feed_override,
        sample_period=case.sample_period,
        profile_id=f"five-axis.r5h.motion-profile-{token}@1",
        feed_source="intelligence.r5h.candidate-holdout-study@1",
        trajectory_id=f"five-axis.r5h.m4-{token}.v1",
        invocation_id=f"intelligence.r5h.{token}.invoke",
        response_trace_id=f"intelligence.r5h.response-{token}@1",
    )


def _exact_operating_point(point: Any) -> R5HExactOperatingPoint:
    return R5HExactOperatingPoint(
        plannedM4ContentHash=point.command.source_m4_content_id,
        plannedM5ContentHash=point.command.content_id,
        exactCycleTimeSeconds=(point.continuous_verification.total_duration_seconds),
        commandSampleCount=len(point.command.samples),
        numericEnvironment=dict(point.adapter_receipt.numeric_environment),
    )


def build_r5h_manifest() -> R5HManifest:
    return R5HManifest(
        manifestId="axiom.intelligence.r5h-manifest@1",
        schemaId="axiom.intelligence.r5h-manifest@1",
        schemaVersion=1,
        stage="R5-H",
        platform="windows",
        reviewScope="candidate-case-scoped-real-holdout",
        sourceDossierSchemaId=(
            "axiom.intelligence.model-promotion-readiness-dossier@1"
        ),
        requiredEvidenceSchemaId="axiom.field-evidence-assessment-report@1",
        bundledRealEvidencePresent=False,
        realWorldGeneralizationStatus="Open",
        modelRegistryWriteAllowed=False,
        activationAllowed=False,
        automaticDeploymentAllowed=False,
        deviceWriteAllowed=False,
        checkIds=R5H_CHECK_IDS,
        targetIds=("cycleTimeSeconds", "linearFollowingErrorMaxMm"),
        safetyBanner=R5H_SAFETY_BANNER,
    )


def build_r5h_study_registration_request(
    dossier: R5GModelPromotionReadinessDossier,
    *,
    study_id: str,
    created_at: str,
    registered_at: str,
    registration_authority_id: str,
    registration_record_id: str,
    cases: tuple[R5HCandidateHoldoutCaseSpec, ...],
) -> R5HCandidateHoldoutStudyRegistrationRequest:
    return _seal(
        R5HCandidateHoldoutStudyRegistrationRequest,
        {
            "schemaId": (
                "axiom.intelligence.candidate-holdout-study-registration-request@1"
            ),
            "schemaVersion": 1,
            "studyId": study_id,
            "readinessDossier": dossier,
            "createdAt": created_at,
            "registeredAt": registered_at,
            "registrationAuthorityId": registration_authority_id,
            "registrationRecordId": registration_record_id,
            "registrationMethod": "external-owner-attestation",
            "maximumCandidateRmseRegressionRatio": 0.0,
            "minimumCandidateIntervalCoverage": 1.0,
            "cases": cases,
            "platform": "windows",
        },
    )


def register_r5h_candidate_holdout_study(
    request: R5HCandidateHoldoutStudyRegistrationRequest,
    *,
    current_platform: str | None = None,
) -> R5HCandidateHoldoutStudyRegistrationReport:
    _require_windows(current_platform or platform.system())
    if not _replay_dossier(request.readiness_dossier):
        raise ValueError("R5-H readiness dossier deterministic replay failed")
    baseline, candidate = _model_bundles(request.readiness_dossier)
    physical_model = build_r4_multirate_physical_model()
    plans: list[R5HCandidateHoldoutCasePlan] = []
    for case in request.cases:
        point = _evaluate_operating_point(case, physical_model=physical_model)
        plans.append(
            _seal(
                R5HCandidateHoldoutCasePlan,
                {
                    **case.model_dump(mode="json", by_alias=True, exclude_none=True),
                    "exactOperatingPoint": _exact_operating_point(point),
                    "plannedCommand": point.command,
                },
            )
        )
    manifest = _seal(
        R5HCandidateHoldoutStudyManifest,
        {
            "artifactType": ("axiom.intelligence.candidate-holdout-study-manifest"),
            "schemaId": ("axiom.intelligence.candidate-holdout-study-manifest@1"),
            "schemaVersion": 1,
            "studyId": request.study_id,
            "readinessDossierContentHash": request.readiness_dossier.content_hash,
            "baselineModelBundleHash": baseline.content_hash,
            "candidateModelBundleHash": candidate.content_hash,
            "createdAt": request.created_at,
            "maximumCandidateRmseRegressionRatio": (
                request.maximum_candidate_rmse_regression_ratio
            ),
            "minimumCandidateIntervalCoverage": (
                request.minimum_candidate_interval_coverage
            ),
            "minimumInDomainCases": 2,
            "minimumDevices": 2,
            "minimumConditions": 2,
            "oodProbeRequired": True,
            "cases": tuple(plans),
            "platform": "windows",
        },
    )
    registration = _seal(
        R5HCandidateHoldoutStudyRegistration,
        {
            "artifactType": ("axiom.intelligence.candidate-holdout-study-registration"),
            "schemaId": ("axiom.intelligence.candidate-holdout-study-registration@1"),
            "schemaVersion": 1,
            "studyId": request.study_id,
            "manifestContentHash": manifest.content_hash,
            "registeredAt": request.registered_at,
            "registrationAuthorityId": request.registration_authority_id,
            "registrationRecordId": request.registration_record_id,
            "registrationMethod": request.registration_method,
            "trustBoundary": (
                "external authority attestation; not cryptographically "
                "verified by Axiom"
            ),
        },
    )
    return _seal(
        R5HCandidateHoldoutStudyRegistrationReport,
        {
            "schemaId": (
                "axiom.intelligence.candidate-holdout-study-registration-report@1"
            ),
            "schemaVersion": 1,
            "requestContentHash": request.content_hash,
            "manifest": manifest,
            "registration": registration,
            "registrationStatus": "Passed",
            "realWorldGeneralizationStatus": "Open",
            "modelPromotionStatus": "NotPerformed",
            "modelRegistryWritePerformed": False,
            "activationPerformed": False,
            "deviceWriteAllowed": False,
            "safetyBanner": R5H_SAFETY_BANNER,
        },
    )


def build_r5h_assessment_request(
    dossier: R5GModelPromotionReadinessDossier,
    registration_report: R5HCandidateHoldoutStudyRegistrationReport,
    *,
    evidence_reports: tuple[FieldEvidenceAssessmentReport, ...],
    assessment_id: str = "axiom.intelligence.r5h.candidate-holdout-assessment@1",
) -> R5HCandidateHoldoutAssessmentRequest:
    return _seal(
        R5HCandidateHoldoutAssessmentRequest,
        {
            "schemaId": (
                "axiom.intelligence.candidate-real-holdout-assessment-request@1"
            ),
            "schemaVersion": 1,
            "assessmentId": assessment_id,
            "readinessDossier": dossier,
            "studyManifest": registration_report.manifest,
            "studyRegistration": registration_report.registration,
            "evidenceReports": evidence_reports,
            "platform": "windows",
        },
    )


def _r7e_request(payload: R7EExamplePayload, *, case_id: str) -> R7EAssessmentRequest:
    return R7EAssessmentRequest(
        caseId=case_id,
        vendorProfile=payload.vendor_profile,
        runtimeEvidence=payload.runtime_evidence,
        witnessProfile=payload.witness_profile,
        controllerProfile=payload.controller_profile,
        authority=payload.authority,
        captureAuthorization=payload.capture_authorization,
        command=payload.command,
        shadowEvidence=payload.shadow_evidence,
    )


def _replay_field_report(report: FieldEvidenceAssessmentReport) -> bool:
    r41_request = report.reality_assessment.run_spec.get("request", {})
    replayed = assess_field_evidence(
        FieldEvidenceAssessmentRequest(
            schemaId="axiom.field-evidence-assessment-request@1",
            schemaVersion=1,
            assessmentId=report.assessment_id,
            calibrationPairId=report.calibration_pair_id,
            validationPairId=report.validation_pair_id,
            calibration=_r7e_request(
                report.calibration_assessment,
                case_id=report.case_id,
            ),
            validation=_r7e_request(
                report.validation_assessment,
                case_id=report.case_id,
            ),
            fitImprovementMinimum=r41_request.get("fitImprovementMinimum", 0.2),
            excitationSpanMinimum=r41_request.get("excitationSpanMinimum", 1e-6),
            decompositionTolerance=r41_request.get("decompositionTolerance", 1e-12),
        )
    )
    return replayed.content_hash == report.content_hash


def _prediction_value(
    *,
    actual: float,
    prediction: Any,
) -> R5HPredictionValue:
    return R5HPredictionValue(
        value=prediction.value,
        lower=prediction.lower,
        upper=prediction.upper,
        absoluteError=abs(prediction.value - actual),
        intervalCovered=prediction.lower <= actual <= prediction.upper,
    )


def _linear_actual(report: FieldEvidenceAssessmentReport) -> float:
    return _linear_actual_from_report(report)


def _case_result(
    *,
    plan: R5HCandidateHoldoutCasePlan,
    report: FieldEvidenceAssessmentReport,
    baseline_bundle: Any,
    candidate_bundle: Any,
) -> R5HCandidateHoldoutCaseResult:
    baseline_prediction = predict_conditional_effect(
        ConditionalEffectPredictionRequest(
            modelBundle=baseline_bundle,
            feedOverride=plan.feed_override,
            samplePeriod=plan.sample_period,
        )
    )
    candidate_prediction = predict_conditional_effect(
        ConditionalEffectPredictionRequest(
            modelBundle=candidate_bundle,
            feedOverride=plan.feed_override,
            samplePeriod=plan.sample_period,
        )
    )
    if baseline_prediction.status != "Predicted" or candidate_prediction.status != (
        "Predicted"
    ):
        raise ValueError("R5-H in-domain operating point prediction abstained")
    baseline_by_target = {
        item.target_id: item for item in baseline_prediction.predictions
    }
    candidate_by_target = {
        item.target_id: item for item in candidate_prediction.predictions
    }
    actuals = {
        "cycleTimeSeconds": plan.exact_operating_point.exact_cycle_time_seconds,
        "linearFollowingErrorMaxMm": _linear_actual(report),
    }
    semantics = {
        "cycleTimeSeconds": ("s", "exact-planner", False),
        "linearFollowingErrorMaxMm": ("mm", "controller-live-read", True),
    }
    targets: list[R5HCaseTargetResult] = []
    for target_id in ("cycleTimeSeconds", "linearFollowingErrorMaxMm"):
        unit, evidence_source, counts_toward_reality = semantics[target_id]
        actual = actuals[target_id]
        targets.append(
            R5HCaseTargetResult(
                targetId=target_id,
                unit=unit,
                evidenceSource=evidence_source,
                countsTowardReality=counts_toward_reality,
                actual=actual,
                baseline=_prediction_value(
                    actual=actual,
                    prediction=baseline_by_target[target_id],
                ),
                candidate=_prediction_value(
                    actual=actual,
                    prediction=candidate_by_target[target_id],
                ),
            )
        )
    validation = report.validation_pair.parsed_r7e_request()
    assert validation.shadow_evidence is not None
    return _seal(
        R5HCandidateHoldoutCaseResult,
        {
            "caseId": plan.case_id,
            "assessmentId": plan.assessment_id,
            "role": plan.role,
            "deviceId": plan.device_id,
            "conditionId": plan.condition_id,
            "feedOverride": plan.feed_override,
            "samplePeriod": plan.sample_period,
            "evidenceReportContentHash": report.content_hash,
            "capturedAt": validation.shadow_evidence.captured_at,
            "realityEvidenceStatus": "Passed",
            "targets": tuple(targets),
        },
    )


def _target_results(
    case_results: tuple[R5HCandidateHoldoutCaseResult, ...],
    manifest: R5HCandidateHoldoutStudyManifest,
) -> tuple[R5HTargetAssessmentResult, ...]:
    in_domain = tuple(result for result in case_results if result.role == "in-domain")
    results: list[R5HTargetAssessmentResult] = []
    semantics = {
        "cycleTimeSeconds": ("s", "exact-planner", False),
        "linearFollowingErrorMaxMm": ("mm", "controller-live-read", True),
    }
    for target_index, target_id in enumerate(
        ("cycleTimeSeconds", "linearFollowingErrorMaxMm")
    ):
        targets = tuple(result.targets[target_index] for result in in_domain)
        baseline_rmse = math.sqrt(
            math.fsum(item.baseline.absolute_error**2 for item in targets)
            / len(targets)
        )
        candidate_rmse = math.sqrt(
            math.fsum(item.candidate.absolute_error**2 for item in targets)
            / len(targets)
        )
        regression_ratio = (candidate_rmse - baseline_rmse) / max(
            baseline_rmse,
            _EPSILON,
        )
        coverage = math.fsum(
            1.0 if item.candidate.interval_covered else 0.0 for item in targets
        ) / len(targets)
        noninferior = candidate_rmse <= (
            baseline_rmse * (1.0 + manifest.maximum_candidate_rmse_regression_ratio)
            + _EPSILON
        )
        coverage_passed = coverage >= manifest.minimum_candidate_interval_coverage
        unit, evidence_source, counts_toward_reality = semantics[target_id]
        results.append(
            R5HTargetAssessmentResult(
                targetId=target_id,
                unit=unit,
                evidenceSource=evidence_source,
                countsTowardReality=counts_toward_reality,
                inDomainCaseCount=len(in_domain),
                baselineRmse=baseline_rmse,
                candidateRmse=candidate_rmse,
                candidateRmseRegressionRatio=regression_ratio,
                candidateIntervalCoverage=coverage,
                status=("Passed" if noninferior and coverage_passed else "Refuted"),
            )
        )
    return tuple(results)


def _check(
    check_id: str,
    title: str,
    status: str,
    reason_code: str,
    **details: Any,
) -> R5HCandidateHoldoutCheck:
    return R5HCandidateHoldoutCheck(
        checkId=check_id,
        title=title,
        status=status,
        reasonCode=reason_code,
        details=details,
    )


def assess_r5h_candidate_real_holdout(
    request: R5HCandidateHoldoutAssessmentRequest,
    *,
    current_platform: str | None = None,
) -> R5HCandidateHoldoutAssessment:
    _require_windows(current_platform or platform.system())
    manifest = request.study_manifest
    registration = request.study_registration
    baseline, candidate = _model_bundles(request.readiness_dossier)

    dossier_ok = _replay_dossier(request.readiness_dossier)
    physical_model = build_r4_multirate_physical_model()
    exact_ok = True
    for plan in manifest.cases:
        point = _evaluate_operating_point(plan, physical_model=physical_model)
        if (
            _exact_operating_point(point) != plan.exact_operating_point
            or point.command != plan.planned_command
        ):
            exact_ok = False
            break

    expected_ids = tuple(plan.assessment_id for plan in manifest.cases)
    report_ids = tuple(report.assessment_id for report in request.evidence_reports)
    evidence_complete = report_ids == expected_ids
    unexpected_evidence = any(item not in expected_ids for item in report_ids) or (
        len(report_ids) == len(expected_ids)
        and set(report_ids) == set(expected_ids)
        and report_ids != expected_ids
    )
    reports_by_id = {
        report.assessment_id: report for report in request.evidence_reports
    }

    field_replays_ok = True
    registration_before_capture = True
    command_binding_ok = exact_ok
    reality_status = "Passed"
    validated_reports: list[
        tuple[R5HCandidateHoldoutCasePlan, FieldEvidenceAssessmentReport]
    ] = []
    if evidence_complete:
        for plan in manifest.cases:
            report = reports_by_id[plan.assessment_id]
            if not _replay_field_report(report):
                field_replays_ok = False
                break
            if report.overall_status == "Blocked":
                reality_status = "Blocked"
            elif report.overall_status == "Refuted" and reality_status != "Blocked":
                reality_status = "Refuted"
            elif report.overall_status == "Open" and reality_status == "Passed":
                reality_status = "Open"
            if report.overall_status != "Passed" or not report.counts_toward_reality:
                continue
            if report.case_id != plan.case_id:
                command_binding_ok = False
                continue
            analysis = report.reality_assessment.analysis
            if (
                analysis.reality_validation_status != "Passed"
                or not analysis.counts_toward_reality
                or analysis.model is None
                or report.validation_pair is None
            ):
                reality_status = "Blocked"
                continue
            validation = report.validation_pair.parsed_r7e_request()
            if validation.command is None or validation.shadow_evidence is None:
                command_binding_ok = False
                continue
            if (
                validation.command.content_id
                != plan.exact_operating_point.planned_m5_content_hash
                or not math.isclose(
                    validation.command.sample_period,
                    plan.sample_period,
                    rel_tol=0.0,
                    abs_tol=1e-15,
                )
                or analysis.model.applicability.device_id != plan.device_id
                or not math.isclose(
                    analysis.model.applicability.sample_period_seconds,
                    plan.sample_period,
                    rel_tol=0.0,
                    abs_tol=1e-15,
                )
                or validation.shadow_evidence.source_kind != "controller-live-read"
                or not validation.shadow_evidence.declared_real
            ):
                command_binding_ok = False
                continue
            if datetime.fromisoformat(registration.registered_at) >= (
                datetime.fromisoformat(validation.shadow_evidence.receipt.opened_at)
            ):
                registration_before_capture = False
                continue
            validated_reports.append((plan, report))
    elif unexpected_evidence:
        field_replays_ok = False

    all_reports_valid = (
        evidence_complete
        and field_replays_ok
        and command_binding_ok
        and registration_before_capture
        and reality_status == "Passed"
        and len(validated_reports) == len(manifest.cases)
    )
    case_results: tuple[R5HCandidateHoldoutCaseResult, ...] = ()
    target_results: tuple[R5HTargetAssessmentResult, ...] = ()
    if all_reports_valid:
        case_results = tuple(
            _case_result(
                plan=plan,
                report=report,
                baseline_bundle=baseline,
                candidate_bundle=candidate,
            )
            for plan, report in validated_reports
        )
        target_results = _target_results(case_results, manifest)

    checks = (
        _check(
            R5H_CHECK_IDS[0],
            "R5-G dossier deterministic lineage",
            "Passed" if dossier_ok else "Blocked",
            "DossierReplayMatched" if dossier_ok else "DossierReplayMismatch",
            dossierContentHash=request.readiness_dossier.content_hash,
        ),
        _check(
            R5H_CHECK_IDS[1],
            "Study registered before every validation capture",
            ("Passed" if registration_before_capture else "Blocked"),
            (
                "RegistrationPrecedesCapture"
                if registration_before_capture
                else "RegistrationNotBeforeCapture"
            ),
            registrationContentHash=registration.content_hash,
        ),
        _check(
            R5H_CHECK_IDS[2],
            "Exact study evidence coverage",
            (
                "Passed"
                if evidence_complete
                else "Blocked"
                if unexpected_evidence
                else "Open"
            ),
            (
                "AllStudyCasesPresent"
                if evidence_complete
                else "UnexpectedEvidence"
                if unexpected_evidence
                else "RealEvidenceMissing"
            ),
            expectedAssessmentIds=list(expected_ids),
            receivedAssessmentIds=list(report_ids),
        ),
        _check(
            R5H_CHECK_IDS[3],
            "Exact operating point and command binding",
            (
                "Passed"
                if evidence_complete and field_replays_ok and command_binding_ok
                else "Blocked"
                if evidence_complete
                and (not field_replays_ok or not command_binding_ok)
                else "Open"
            ),
            (
                "ExactCommandsMatched"
                if evidence_complete and field_replays_ok and command_binding_ok
                else "ExactCommandMismatch"
                if evidence_complete
                else "RealEvidenceMissing"
            ),
            exactPlanningReplayMatched=exact_ok,
        ),
        _check(
            R5H_CHECK_IDS[4],
            "R4.1 controller-live-read reality evidence",
            reality_status if evidence_complete else "Open",
            (
                "AllR41RealityGatesPassed"
                if evidence_complete and reality_status == "Passed"
                else "R41RealityEvidenceUnavailable"
                if not evidence_complete or reality_status == "Open"
                else "R41RealityGateDidNotPass"
            ),
        ),
        _check(
            R5H_CHECK_IDS[5],
            "Cycle head exact-planner holdout",
            target_results[0].status if target_results else "Open",
            (
                "CycleHeadNoninferior"
                if target_results and target_results[0].status == "Passed"
                else "CycleHeadRefuted"
                if target_results
                else "AssessmentIncomplete"
            ),
            countsTowardReality=False,
        ),
        _check(
            R5H_CHECK_IDS[6],
            "Linear error head real command-observation holdout",
            target_results[1].status if target_results else "Open",
            (
                "LinearRealityHeadNoninferior"
                if target_results and target_results[1].status == "Passed"
                else "LinearRealityHeadRefuted"
                if target_results
                else "AssessmentIncomplete"
            ),
            countsTowardReality=True,
        ),
        _check(
            R5H_CHECK_IDS[7],
            "Candidate dual-head noninferiority and coverage",
            (
                "Passed"
                if target_results
                and all(result.status == "Passed" for result in target_results)
                else "Refuted"
                if target_results
                else "Open"
            ),
            (
                "CandidateHoldoutGatePassed"
                if target_results
                and all(result.status == "Passed" for result in target_results)
                else "CandidateHoldoutGateRefuted"
                if target_results
                else "AssessmentIncomplete"
            ),
        ),
    )
    statuses = tuple(check.status for check in checks)
    if "Blocked" in statuses:
        overall_status = "Blocked"
    elif "Refuted" in statuses:
        overall_status = "Refuted"
    elif all(status == "Passed" for status in statuses):
        overall_status = "Passed"
    else:
        overall_status = "Open"
    reality = {
        "Passed": "CaseScopedPassed",
        "Open": "Open",
        "Refuted": "Refuted",
        "Blocked": "Blocked",
    }[overall_status]
    return _seal(
        R5HCandidateHoldoutAssessment,
        {
            "artifactType": ("axiom.intelligence.candidate-real-holdout-assessment"),
            "schemaId": ("axiom.intelligence.candidate-real-holdout-assessment@1"),
            "schemaVersion": 1,
            "assessmentId": request.assessment_id,
            "request": request,
            "readinessDossierContentHash": request.readiness_dossier.content_hash,
            "studyManifestContentHash": manifest.content_hash,
            "studyRegistrationContentHash": registration.content_hash,
            "baselineModelBundleHash": baseline.content_hash,
            "candidateModelBundleHash": candidate.content_hash,
            "checks": checks,
            "caseResults": case_results,
            "targetResults": target_results,
            "overallStatus": overall_status,
            "realWorldGeneralizationStatus": reality,
            "reviewDecisionStatus": "AwaitingIndependentHumanDecision",
            "candidateUseStatus": "EvaluatedOnly",
            "modelPromotionStatus": "NotPerformed",
            "defaultModelChanged": False,
            "modelRegistryWritePerformed": False,
            "activationPerformed": False,
            "automaticDeploymentAllowed": False,
            "deviceWriteAllowed": False,
            "permissionLevel": "Offline",
            "safetyBanner": R5H_SAFETY_BANNER,
        },
    )


__all__ = [
    "assess_r5h_candidate_real_holdout",
    "build_r5h_assessment_request",
    "build_r5h_manifest",
    "build_r5h_study_registration_request",
    "register_r5h_candidate_holdout_study",
]
