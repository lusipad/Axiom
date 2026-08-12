from __future__ import annotations

from ..optimization import RecommendationSet
from .models import (
    AcceptanceRecord,
    AdmissionDecision,
    ControlEnvelope,
    ControlledRuntimeAudit,
    MonitorFinding,
    ResponsibilitySnapshot,
    RollbackReceipt,
    RuntimeSpec,
    RuntimeTransition,
    StopReceipt,
    canonical_hash,
)


def _record(model_type, **payload):
    payload["contentHash"] = canonical_hash(payload)
    return model_type.model_validate(payload)


def build_control_envelope(*, baseline_parameter_set_id: str) -> ControlEnvelope:
    return _record(
        ControlEnvelope,
        envelopeId="control.r7.synthetic-shadow-envelope@1",
        permissionCeiling="Shadow",
        maximumLinearFollowingErrorMm=0.60,
        maximumOodFraction=0.50,
        maximumMonitorGapSeconds=0.10,
        deviceWriteAllowed=False,
        automaticAcceptanceAllowed=False,
        stopOnAnyBreach=True,
        rollbackParameterSetId=baseline_parameter_set_id,
    )


def _admission_reasons(
    spec: RuntimeSpec, recommendation: RecommendationSet
) -> tuple[str, ...]:
    reasons: list[str] = []
    if spec.requested_permission in {"ControlledTrial", "ClosedLoop"}:
        reasons.append("PermissionCeilingExceeded")
    elif spec.requested_permission != "Shadow":
        reasons.append("UnsupportedPermissionMode")
    if spec.device_write_requested:
        reasons.append("DeviceWriteForbidden")
    if (
        spec.require_deployment_shadow_evidence
        and spec.deployment_shadow_evidence_hash is None
    ):
        reasons.append("DeploymentShadowEvidenceMissing")
    elif spec.require_deployment_shadow_evidence:
        reasons.append("DeploymentShadowEvidenceUnverified")
    candidate = next(
        (
            item
            for item in recommendation.candidates
            if item.candidate_id == spec.candidate_id
        ),
        None,
    )
    if candidate is None:
        reasons.append("RecommendationCandidateMissing")
    elif not candidate.hard_constraints_satisfied:
        reasons.append("RecommendationHardGateFailed")
    return tuple(reasons)


def _findings(spec: RuntimeSpec) -> tuple[MonitorFinding, ...]:
    results: list[MonitorFinding] = []
    previous_time: float | None = None
    for sample in spec.trace.samples:
        reasons: list[str] = []
        if (
            sample.linear_following_error_mm
            > spec.envelope.maximum_linear_following_error_mm
        ):
            reasons.append("LinearFollowingErrorLimitExceeded")
        if sample.ood_fraction > spec.envelope.maximum_ood_fraction:
            reasons.append("OodFractionLimitExceeded")
        if (
            previous_time is not None
            and sample.time_seconds - previous_time
            > spec.envelope.maximum_monitor_gap_seconds
        ):
            reasons.append("MonitorGapLimitExceeded")
        results.append(
            MonitorFinding(
                sampleSequence=sample.sequence,
                status="Breach" if reasons else "WithinEnvelope",
                reasonCodes=tuple(reasons),
            )
        )
        previous_time = sample.time_seconds
    return tuple(results)


def run_shadow(
    spec: RuntimeSpec, recommendation: RecommendationSet
) -> ControlledRuntimeAudit:
    reasons = _admission_reasons(spec, recommendation)
    granted = "Denied" if reasons else "Shadow"
    admission = AdmissionDecision(
        status="Blocked" if reasons else "Admitted",
        requestedPermission=spec.requested_permission,
        grantedPermission=granted,
        reasonCodes=reasons,
        recommendationSetContentHash=recommendation.content_hash,
        envelopeContentHash=spec.envelope.content_hash,
    )
    acceptance = _record(
        AcceptanceRecord,
        recordId=f"control.r7.acceptance.{spec.scenario_id}@1",
        disposition="Blocked" if reasons else "Shadow",
        grantedPermission=granted,
        recommendationSetContentHash=recommendation.content_hash,
        candidateId=spec.candidate_id,
        evidenceSnapshotHash=recommendation.content_hash,
        responsibility=ResponsibilitySnapshot(
            accountablePartyId="axiom.reference-policy-owner",
            decisionPolicyId="control.r7.fail-closed-shadow-policy@1",
            approvalMode="policy-replay",
            humanApprovalPresent=False,
            realDeviceAuthorityPresent=False,
        ),
        automatic=False,
    )
    transitions = [
        RuntimeTransition(
            sequence=0,
            fromState=None,
            toState="Prepared",
            reasonCode="RuntimeSpecValidated",
        )
    ]
    if reasons:
        transitions.append(
            RuntimeTransition(
                sequence=1,
                fromState="Prepared",
                toState="Blocked",
                reasonCode=reasons[0],
            )
        )
        findings: tuple[MonitorFinding, ...] = ()
        final_state = "Blocked"
        stop = StopReceipt(
            requested=False,
            reasonCodes=(),
            effect="NotRequired",
            deviceStopCommandIssued=False,
            deviceAcknowledged=False,
        )
        rollback = RollbackReceipt(
            status="NotRequired",
            baselineParameterSetId=spec.envelope.rollback_parameter_set_id,
            deviceWriteIssued=False,
            deviceReadbackVerified=False,
        )
    else:
        transitions.extend(
            [
                RuntimeTransition(
                    sequence=1,
                    fromState="Prepared",
                    toState="Admitted",
                    reasonCode="ShadowPolicyAdmitted",
                ),
                RuntimeTransition(
                    sequence=2,
                    fromState="Admitted",
                    toState="Monitoring",
                    reasonCode="SyntheticShadowReplayStarted",
                ),
            ]
        )
        findings = _findings(spec)
        breaches = tuple(
            reason
            for item in findings
            if item.status == "Breach"
            for reason in item.reason_codes
        )
        if breaches:
            transitions.extend(
                [
                    RuntimeTransition(
                        sequence=3,
                        fromState="Monitoring",
                        toState="StopRequested",
                        reasonCode=breaches[0],
                    ),
                    RuntimeTransition(
                        sequence=4,
                        fromState="StopRequested",
                        toState="Stopped",
                        reasonCode="ShadowReplayStopped",
                    ),
                    RuntimeTransition(
                        sequence=5,
                        fromState="Stopped",
                        toState="RollbackVerified",
                        reasonCode="BaselineWasNeverModified",
                    ),
                ]
            )
            final_state = "RollbackVerified"
            stop = StopReceipt(
                requested=True,
                reasonCodes=breaches,
                effect="PromotionSuppressed",
                deviceStopCommandIssued=False,
                deviceAcknowledged=False,
            )
            rollback = RollbackReceipt(
                status="BaselineRetained",
                baselineParameterSetId=spec.envelope.rollback_parameter_set_id,
                deviceWriteIssued=False,
                deviceReadbackVerified=False,
            )
        else:
            transitions.append(
                RuntimeTransition(
                    sequence=3,
                    fromState="Monitoring",
                    toState="Completed",
                    reasonCode="ShadowEnvelopeMaintained",
                )
            )
            final_state = "Completed"
            stop = StopReceipt(
                requested=False,
                reasonCodes=(),
                effect="NotRequired",
                deviceStopCommandIssued=False,
                deviceAcknowledged=False,
            )
            rollback = RollbackReceipt(
                status="NotRequired",
                baselineParameterSetId=spec.envelope.rollback_parameter_set_id,
                deviceWriteIssued=False,
                deviceReadbackVerified=False,
            )
    payload = {
        "artifactType": "axiom.control.runtime-audit",
        "schemaId": "axiom.control.runtime-audit@1",
        "schemaVersion": 1,
        "auditId": f"control.r7.audit.{spec.scenario_id}@1",
        "runtimeSpecId": spec.runtime_spec_id,
        "admissionDecision": admission,
        "acceptanceRecord": acceptance,
        "transitions": tuple(transitions),
        "monitorFindings": findings,
        "stopReceipt": stop,
        "rollbackReceipt": rollback,
        "finalState": final_state,
        "permissionCeiling": "Shadow",
        "deviceWriteAllowed": False,
        "deviceWritePerformed": False,
        "syntheticShadowContractStatus": "Passed",
        "deploymentShadowStatus": "Open",
        "controlledTrialStatus": "Open",
        "closedLoopStatus": "Open",
        "standardsComplianceStatus": "NotAssessed",
    }
    return _record(ControlledRuntimeAudit, **payload)
