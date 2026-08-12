from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, model_validator

from ..models import AxiomModel, EvaluationCase
from ..optimization import RecommendationSet

R7_DOMAIN_PACK_ID = "control.domain-pack@1"
R7_EVALUATOR_ID = "control-shadow-evaluator@1"
R7_RUNNER_ID = "control-synthetic-shadow-replay@1"
R7_DEFAULT_SCENARIO_ID = "synthetic-shadow-nominal"
R7_SCENARIO_IDS = (
    R7_DEFAULT_SCENARIO_ID,
    "synthetic-shadow-limit-breach",
    "deployment-shadow-reality-open",
    "controlled-trial-without-authority",
    "device-write-request-blocked",
)

PermissionLevel = Literal[
    "Denied", "Offline", "Advisory", "Shadow", "ControlledTrial", "ClosedLoop"
]
RuntimeState = Literal[
    "Prepared",
    "Admitted",
    "Blocked",
    "Monitoring",
    "StopRequested",
    "Stopped",
    "RollbackVerified",
    "Completed",
]


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
        default=_json_default,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, AxiomModel):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


class ControlEnvelope(AxiomModel):
    envelope_id: Literal["control.r7.synthetic-shadow-envelope@1"] = Field(
        alias="envelopeId"
    )
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    maximum_linear_following_error_mm: float = Field(
        alias="maximumLinearFollowingErrorMm", gt=0.0
    )
    maximum_ood_fraction: float = Field(alias="maximumOodFraction", ge=0.0, le=1.0)
    maximum_monitor_gap_seconds: float = Field(alias="maximumMonitorGapSeconds", gt=0.0)
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    automatic_acceptance_allowed: Literal[False] = Field(
        alias="automaticAcceptanceAllowed"
    )
    stop_on_any_breach: Literal[True] = Field(alias="stopOnAnyBreach")
    rollback_parameter_set_id: str = Field(
        alias="rollbackParameterSetId", pattern=r"^.+@[0-9]+$"
    )
    content_hash: str = Field(alias="contentHash", pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_identity(self) -> ControlEnvelope:
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("ControlEnvelope contentHash must match content")
        return self


class ShadowSample(AxiomModel):
    sequence: int = Field(ge=0)
    time_seconds: float = Field(alias="timeSeconds", ge=0.0)
    linear_following_error_mm: float = Field(alias="linearFollowingErrorMm", ge=0.0)
    ood_fraction: float = Field(alias="oodFraction", ge=0.0, le=1.0)
    source_kind: Literal["synthetic-shadow"] = Field(alias="sourceKind")


class ShadowTrace(AxiomModel):
    trace_id: str = Field(alias="traceId", pattern=r"^.+@[0-9]+$")
    source_kind: Literal["synthetic-shadow"] = Field(alias="sourceKind")
    samples: tuple[ShadowSample, ...] = Field(min_length=2)
    content_hash: str = Field(alias="contentHash", pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_trace(self) -> ShadowTrace:
        if tuple(sample.sequence for sample in self.samples) != tuple(
            range(len(self.samples))
        ):
            raise ValueError("ShadowTrace sequence must be contiguous")
        if any(
            right.time_seconds <= left.time_seconds
            for left, right in zip(self.samples, self.samples[1:])
        ):
            raise ValueError("ShadowTrace timestamps must be strictly increasing")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("ShadowTrace contentHash must match content")
        return self


class RuntimeSpec(AxiomModel):
    schema_id: Literal["control.runtime-spec@1"] = Field(alias="schemaId")
    runtime_spec_id: str = Field(alias="runtimeSpecId", pattern=r"^.+@[0-9]+$")
    scenario_id: str = Field(alias="scenarioId")
    requested_permission: PermissionLevel = Field(alias="requestedPermission")
    device_write_requested: bool = Field(alias="deviceWriteRequested")
    candidate_id: str = Field(alias="candidateId", pattern=r"^.+@[0-9]+$")
    recommendation_set_content_hash: str = Field(
        alias="recommendationSetContentHash", pattern=r"^[0-9a-f]{64}$"
    )
    envelope: ControlEnvelope
    trace: ShadowTrace
    require_deployment_shadow_evidence: bool = Field(
        alias="requireDeploymentShadowEvidence"
    )
    deployment_shadow_evidence_hash: str | None = Field(
        default=None, alias="deploymentShadowEvidenceHash", pattern=r"^[0-9a-f]{64}$"
    )


class ResponsibilitySnapshot(AxiomModel):
    accountable_party_id: str = Field(alias="accountablePartyId", min_length=1)
    decision_policy_id: str = Field(alias="decisionPolicyId", pattern=r"^.+@[0-9]+$")
    approval_mode: Literal["policy-replay"] = Field(alias="approvalMode")
    human_approval_present: Literal[False] = Field(alias="humanApprovalPresent")
    real_device_authority_present: Literal[False] = Field(
        alias="realDeviceAuthorityPresent"
    )


class AdmissionDecision(AxiomModel):
    status: Literal["Admitted", "Blocked"]
    requested_permission: PermissionLevel = Field(alias="requestedPermission")
    granted_permission: PermissionLevel = Field(alias="grantedPermission")
    reason_codes: tuple[str, ...] = Field(alias="reasonCodes")
    recommendation_set_content_hash: str = Field(
        alias="recommendationSetContentHash", pattern=r"^[0-9a-f]{64}$"
    )
    envelope_content_hash: str = Field(
        alias="envelopeContentHash", pattern=r"^[0-9a-f]{64}$"
    )


class AcceptanceRecord(AxiomModel):
    record_id: str = Field(alias="recordId", pattern=r"^.+@[0-9]+$")
    disposition: Literal["Shadow", "Blocked"]
    granted_permission: PermissionLevel = Field(alias="grantedPermission")
    recommendation_set_content_hash: str = Field(
        alias="recommendationSetContentHash", pattern=r"^[0-9a-f]{64}$"
    )
    candidate_id: str = Field(alias="candidateId")
    evidence_snapshot_hash: str = Field(
        alias="evidenceSnapshotHash", pattern=r"^[0-9a-f]{64}$"
    )
    responsibility: ResponsibilitySnapshot
    automatic: Literal[False]
    content_hash: str = Field(alias="contentHash", pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_identity(self) -> AcceptanceRecord:
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("AcceptanceRecord contentHash must match content")
        return self


class RuntimeTransition(AxiomModel):
    sequence: int = Field(ge=0)
    from_state: RuntimeState | None = Field(default=None, alias="fromState")
    to_state: RuntimeState = Field(alias="toState")
    reason_code: str = Field(alias="reasonCode", min_length=1)


class MonitorFinding(AxiomModel):
    sample_sequence: int = Field(alias="sampleSequence", ge=0)
    status: Literal["WithinEnvelope", "Breach"]
    reason_codes: tuple[str, ...] = Field(alias="reasonCodes")


class StopReceipt(AxiomModel):
    requested: bool
    reason_codes: tuple[str, ...] = Field(alias="reasonCodes")
    effect: Literal["NotRequired", "PromotionSuppressed"]
    device_stop_command_issued: Literal[False] = Field(alias="deviceStopCommandIssued")
    device_acknowledged: Literal[False] = Field(alias="deviceAcknowledged")


class RollbackReceipt(AxiomModel):
    status: Literal["NotRequired", "BaselineRetained"]
    baseline_parameter_set_id: str = Field(alias="baselineParameterSetId")
    device_write_issued: Literal[False] = Field(alias="deviceWriteIssued")
    device_readback_verified: Literal[False] = Field(alias="deviceReadbackVerified")


class ControlledRuntimeAudit(AxiomModel):
    artifact_type: Literal["axiom.control.runtime-audit"] = Field(alias="artifactType")
    schema_id: Literal["axiom.control.runtime-audit@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    audit_id: str = Field(alias="auditId", pattern=r"^.+@[0-9]+$")
    runtime_spec_id: str = Field(alias="runtimeSpecId")
    admission_decision: AdmissionDecision = Field(alias="admissionDecision")
    acceptance_record: AcceptanceRecord = Field(alias="acceptanceRecord")
    transitions: tuple[RuntimeTransition, ...] = Field(min_length=2)
    monitor_findings: tuple[MonitorFinding, ...] = Field(alias="monitorFindings")
    stop_receipt: StopReceipt = Field(alias="stopReceipt")
    rollback_receipt: RollbackReceipt = Field(alias="rollbackReceipt")
    final_state: RuntimeState = Field(alias="finalState")
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    device_write_performed: Literal[False] = Field(alias="deviceWritePerformed")
    synthetic_shadow_contract_status: Literal["Passed"] = Field(
        alias="syntheticShadowContractStatus"
    )
    deployment_shadow_status: Literal["Open"] = Field(alias="deploymentShadowStatus")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    standards_compliance_status: Literal["NotAssessed"] = Field(
        alias="standardsComplianceStatus"
    )
    content_hash: str = Field(alias="contentHash", pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def verify_state_and_identity(self) -> ControlledRuntimeAudit:
        expected_sequence = tuple(range(len(self.transitions)))
        if tuple(item.sequence for item in self.transitions) != expected_sequence:
            raise ValueError("transitions must have contiguous sequence numbers")
        previous: RuntimeState | None = None
        for item in self.transitions:
            if item.from_state != previous:
                raise ValueError("transition fromState must match preceding state")
            previous = item.to_state
        if previous != self.final_state:
            raise ValueError("finalState must match the final transition")
        if (
            self.admission_decision.status == "Blocked"
            and self.final_state != "Blocked"
        ):
            raise ValueError("blocked admission must finish in Blocked")
        if self.final_state == "RollbackVerified" and (
            not self.stop_receipt.requested
            or self.rollback_receipt.status != "BaselineRetained"
        ):
            raise ValueError(
                "RollbackVerified requires stop and baseline retention receipts"
            )
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("ControlledRuntimeAudit contentHash must match content")
        return self


class ControlEvaluationRequest(AxiomModel):
    artifact: ControlledRuntimeAudit
    runtime_spec: RuntimeSpec = Field(alias="runtimeSpec")
    recommendation_set: RecommendationSet = Field(alias="recommendationSet")
    case: EvaluationCase

    @model_validator(mode="after")
    def bind_context(self) -> ControlEvaluationRequest:
        if self.runtime_spec.runtime_spec_id != self.artifact.runtime_spec_id:
            raise ValueError("runtimeSpecId must bind the audit")
        if (
            self.runtime_spec.recommendation_set_content_hash
            != self.recommendation_set.content_hash
        ):
            raise ValueError("RecommendationSet content identity mismatch")
        return self


class R7Manifest(AxiomModel):
    manifest_id: Literal["control.r7-manifest@1"] = Field(alias="manifestId")
    domain_pack_id: Literal["control.domain-pack@1"] = Field(alias="domainPackId")
    evaluator_version: Literal["control-shadow-evaluator@1"] = Field(
        alias="evaluatorVersion"
    )
    runner_id: Literal["control-synthetic-shadow-replay@1"] = Field(alias="runnerId")
    supported_platforms: tuple[Literal["Windows"], ...] = Field(
        alias="supportedPlatforms"
    )
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    scenario_ids: tuple[str, ...] = Field(alias="scenarioIds")
    synthetic_shadow_contract_status: Literal["Passed"] = Field(
        alias="syntheticShadowContractStatus"
    )
    deployment_shadow_status: Literal["Open"] = Field(alias="deploymentShadowStatus")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")


class R7ScenarioSummary(AxiomModel):
    scenario_id: str = Field(alias="scenarioId")
    title: str
    description: str
    expected_outcome: Literal["Passed"] = Field(alias="expectedOutcome")
    expected_final_state: RuntimeState = Field(alias="expectedFinalState")


class R7ExamplePayload(AxiomModel):
    manifest: R7Manifest
    scenario: R7ScenarioSummary
    recommendation_set: RecommendationSet = Field(alias="recommendationSet")
    runtime_spec: RuntimeSpec = Field(alias="runtimeSpec")
    runtime_audit: ControlledRuntimeAudit = Field(alias="runtimeAudit")
    run_spec: dict[str, Any] = Field(alias="runSpec")


class R7ReplayRequest(AxiomModel):
    scenario_id: str = Field(default=R7_DEFAULT_SCENARIO_ID, alias="scenarioId")


@dataclass(frozen=True)
class R7Scenario:
    summary: R7ScenarioSummary
    recommendation_set: RecommendationSet
    runtime_spec: RuntimeSpec
    runtime_audit: ControlledRuntimeAudit
    run_spec: dict[str, Any]
