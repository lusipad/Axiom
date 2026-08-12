from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel, EvaluationCase, _require_json_number
from .models import canonical_hash

R7B_DOMAIN_PACK_ID = "control.domain-pack@2"
R7B_EVALUATOR_ID = "control-deployment-shadow-readiness-evaluator@1"
R7B_RUNNER_ID = "control-deployment-shadow-import@1"
R7B_DEFAULT_SCENARIO_ID = "deployment-shadow-readiness-open"
R7B_SCENARIO_IDS = (R7B_DEFAULT_SCENARIO_ID, "contract-fixture-blocked")

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_DENIED_DEVICE_OPERATIONS = (
    "parameter-write",
    "program-transfer",
    "cycle-start",
    "feed-hold",
    "reset",
    "jog",
    "safety-bypass",
)

InterfaceType = Literal["opc-ua", "focas2", "heidenhain-dnc", "controller-export"]
EvidenceSourceKind = Literal[
    "contract-fixture", "controller-live-read", "controller-export"
]
ReadinessStatus = Literal["Passed", "Open", "Blocked"]
DeviceOperation = Literal[
    "parameter-write",
    "program-transfer",
    "cycle-start",
    "feed-hold",
    "reset",
    "jog",
    "safety-bypass",
]


def _aware_timestamp(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


class DeploymentControllerProfile(AxiomModel):
    profile_id: str = Field(alias="profileId", pattern=r"^.+@[0-9]+$")
    vendor: str = Field(min_length=1)
    controller_family: str = Field(alias="controllerFamily", min_length=1)
    controller_model: str = Field(alias="controllerModel", min_length=1)
    software_version: str = Field(alias="softwareVersion", min_length=1)
    machine_id: str = Field(alias="machineId", min_length=1)
    interface_type: InterfaceType = Field(alias="interfaceType")
    target_status: Literal["Unselected", "Selected"] = Field(alias="targetStatus")
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> DeploymentControllerProfile:
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("DeploymentControllerProfile contentHash must match content")
        return self


class ReadOnlyAuthorityEvidence(AxiomModel):
    evidence_id: str = Field(alias="evidenceId", pattern=r"^.+@[0-9]+$")
    controller_profile_content_hash: str = Field(
        alias="controllerProfileContentHash", pattern=_HASH_PATTERN
    )
    principal_id: str = Field(alias="principalId", min_length=1)
    enforcement_point: Literal["controller"] = Field(alias="enforcementPoint")
    granted_operations: tuple[Literal["read", "subscribe"], ...] = Field(
        alias="grantedOperations", min_length=1
    )
    denied_operations: tuple[DeviceOperation, ...] = Field(
        alias="deniedOperations", min_length=len(_DENIED_DEVICE_OPERATIONS)
    )
    attestation_kind: Literal[
        "controller-signed",
        "vendor-signed",
        "independent-audit",
        "unverified-contract-fixture",
    ] = Field(alias="attestationKind")
    attestation_content_hash: str = Field(
        alias="attestationContentHash", pattern=_HASH_PATTERN
    )
    verification_status: Literal["Verified", "Unverified"] = Field(
        alias="verificationStatus"
    )
    trust_anchor_content_hash: str | None = Field(
        default=None, alias="trustAnchorContentHash", pattern=_HASH_PATTERN
    )
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_read_only_contract(self) -> ReadOnlyAuthorityEvidence:
        if len(set(self.granted_operations)) != len(self.granted_operations):
            raise ValueError("grantedOperations must be unique")
        if tuple(self.denied_operations) != _DENIED_DEVICE_OPERATIONS:
            raise ValueError("deniedOperations must cover every frozen device operation")
        if self.verification_status == "Verified" and self.trust_anchor_content_hash is None:
            raise ValueError("Verified authority requires trustAnchorContentHash")
        if (
            self.verification_status == "Verified"
            and self.attestation_kind == "unverified-contract-fixture"
        ):
            raise ValueError("contract fixture authority cannot be Verified")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("ReadOnlyAuthorityEvidence contentHash must match content")
        return self


class DeploymentShadowSample(AxiomModel):
    channel_id: str = Field(alias="channelId", min_length=1)
    value: float | str
    unit: str | None = None
    quality: Literal["good", "suspect", "bad"]

    @field_validator("value", mode="before")
    @classmethod
    def reject_non_json_numbers(cls, value: Any) -> Any:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return _require_json_number(value)
        return value


class DeploymentShadowFrame(AxiomModel):
    sequence: int = Field(ge=0)
    controller_timestamp: str = Field(alias="controllerTimestamp", min_length=1)
    host_timestamp: str = Field(alias="hostTimestamp", min_length=1)
    samples: tuple[DeploymentShadowSample, ...] = Field(min_length=1)

    @field_validator("controller_timestamp", "host_timestamp")
    @classmethod
    def require_aware_timestamps(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @model_validator(mode="after")
    def require_unique_channels(self) -> DeploymentShadowFrame:
        channels = tuple(sample.channel_id for sample in self.samples)
        if len(channels) != len(set(channels)):
            raise ValueError("frame samples must have unique channelId values")
        return self


class DeploymentShadowCapture(AxiomModel):
    artifact_type: Literal["axiom.control.deployment-shadow-capture"] = Field(
        alias="artifactType"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    capture_id: str = Field(alias="captureId", pattern=r"^.+@[0-9]+$")
    source_kind: EvidenceSourceKind = Field(alias="sourceKind")
    declared_real: bool = Field(alias="declaredReal")
    controller_profile_content_hash: str = Field(
        alias="controllerProfileContentHash", pattern=_HASH_PATTERN
    )
    frames: tuple[DeploymentShadowFrame, ...] = Field(min_length=2)
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_capture(self) -> DeploymentShadowCapture:
        if self.source_kind == "contract-fixture" and self.declared_real:
            raise ValueError("contract-fixture cannot declare real evidence")
        if self.source_kind != "contract-fixture" and not self.declared_real:
            raise ValueError("controller evidence must explicitly declare real provenance")
        expected_sequence = tuple(range(len(self.frames)))
        if tuple(frame.sequence for frame in self.frames) != expected_sequence:
            raise ValueError("capture frame sequence must be contiguous")
        if any(
            datetime.fromisoformat(right.controller_timestamp)
            <= datetime.fromisoformat(left.controller_timestamp)
            for left, right in zip(self.frames, self.frames[1:])
        ):
            raise ValueError("controller timestamps must be strictly increasing")
        if any(
            datetime.fromisoformat(right.host_timestamp)
            <= datetime.fromisoformat(left.host_timestamp)
            for left, right in zip(self.frames, self.frames[1:])
        ):
            raise ValueError("host timestamps must be strictly increasing")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("DeploymentShadowCapture contentHash must match content")
        return self


class DeploymentSignalMapping(AxiomModel):
    source_channel_id: str = Field(alias="sourceChannelId", min_length=1)
    canonical_signal_id: str = Field(alias="canonicalSignalId", min_length=1)
    quantity: Literal["axis-position", "controller-state", "alarm"]
    axis_id: str | None = Field(default=None, alias="axisId", min_length=1)
    unit: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def require_axis_context(self) -> DeploymentSignalMapping:
        if self.quantity == "axis-position" and (
            self.axis_id is None or self.unit is None
        ):
            raise ValueError("axis-position mapping requires axisId and unit")
        return self


class ClockSignalBinding(AxiomModel):
    binding_id: str = Field(alias="bindingId", pattern=r"^.+@[0-9]+$")
    controller_profile_content_hash: str = Field(
        alias="controllerProfileContentHash", pattern=_HASH_PATTERN
    )
    clock_method: Literal[
        "controller-clock-synchronized", "ptp", "ntp", "vendor-declared", "contract-fixture"
    ] = Field(alias="clockMethod")
    maximum_timestamp_uncertainty_ms: float = Field(
        alias="maximumTimestampUncertaintyMs", ge=0.0
    )
    maximum_observed_gap_ms: float = Field(alias="maximumObservedGapMs", ge=0.0)
    required_maximum_gap_ms: float = Field(alias="requiredMaximumGapMs", gt=0.0)
    coverage_fraction: float = Field(alias="coverageFraction", ge=0.0, le=1.0)
    signal_mappings: tuple[DeploymentSignalMapping, ...] = Field(
        alias="signalMappings", min_length=1
    )
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @field_validator(
        "maximum_timestamp_uncertainty_ms",
        "maximum_observed_gap_ms",
        "required_maximum_gap_ms",
        "coverage_fraction",
        mode="before",
    )
    @classmethod
    def reject_non_json_floats(cls, value: Any) -> Any:
        return _require_json_number(value)

    @model_validator(mode="after")
    def verify_binding(self) -> ClockSignalBinding:
        sources = tuple(item.source_channel_id for item in self.signal_mappings)
        canonical = tuple(item.canonical_signal_id for item in self.signal_mappings)
        if len(sources) != len(set(sources)) or len(canonical) != len(set(canonical)):
            raise ValueError("signalMappings must have unique source and canonical IDs")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("ClockSignalBinding contentHash must match content")
        return self


class DeploymentAdapterReceipt(AxiomModel):
    receipt_id: str = Field(alias="receiptId", pattern=r"^.+@[0-9]+$")
    adapter_id: str = Field(alias="adapterId", pattern=r"^.+@[0-9]+$")
    adapter_version: str = Field(alias="adapterVersion", min_length=1)
    platform: Literal["Windows"]
    protocol: InterfaceType
    access_mode: Literal["read-subscribe-only"] = Field(alias="accessMode")
    controller_profile_content_hash: str = Field(
        alias="controllerProfileContentHash", pattern=_HASH_PATTERN
    )
    capture_content_hash: str = Field(alias="captureContentHash", pattern=_HASH_PATTERN)
    status: Literal["Succeeded", "Failed"]
    opened_at: str = Field(alias="openedAt", min_length=1)
    closed_at: str = Field(alias="closedAt", min_length=1)
    read_operation_count: int = Field(alias="readOperationCount", ge=0)
    write_operation_count: Literal[0] = Field(alias="writeOperationCount")
    received_sample_count: int = Field(alias="receivedSampleCount", ge=0)
    dropped_sample_count: int = Field(alias="droppedSampleCount", ge=0)
    transcript_content_hash: str = Field(
        alias="transcriptContentHash", pattern=_HASH_PATTERN
    )
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @field_validator("opened_at", "closed_at")
    @classmethod
    def require_aware_timestamps(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @model_validator(mode="after")
    def verify_receipt(self) -> DeploymentAdapterReceipt:
        if datetime.fromisoformat(self.closed_at) < datetime.fromisoformat(self.opened_at):
            raise ValueError("closedAt must not precede openedAt")
        if self.status == "Succeeded" and self.received_sample_count == 0:
            raise ValueError("Succeeded receipt requires received samples")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("DeploymentAdapterReceipt contentHash must match content")
        return self


class ExternalEvidenceProvenance(AxiomModel):
    provenance_id: str = Field(alias="provenanceId", pattern=r"^.+@[0-9]+$")
    data_owner_id: str = Field(alias="dataOwnerId", min_length=1)
    acquisition_purpose: Literal["deployment-shadow-validation"] = Field(
        alias="acquisitionPurpose"
    )
    captured_outside_repository: bool = Field(alias="capturedOutsideRepository")
    evaluation_authorized: bool = Field(alias="evaluationAuthorized")
    source_content_hash: str = Field(alias="sourceContentHash", pattern=_HASH_PATTERN)
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> ExternalEvidenceProvenance:
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("ExternalEvidenceProvenance contentHash must match content")
        return self


class DeploymentShadowEvidenceSet(AxiomModel):
    schema_id: Literal["axiom.control.deployment-shadow-evidence-set@1"] = Field(
        alias="schemaId"
    )
    evidence_set_id: str = Field(alias="evidenceSetId", pattern=r"^.+@[0-9]+$")
    controller_profile: DeploymentControllerProfile = Field(alias="controllerProfile")
    authority: ReadOnlyAuthorityEvidence
    capture: DeploymentShadowCapture
    adapter_receipt: DeploymentAdapterReceipt = Field(alias="adapterReceipt")
    clock_signal_binding: ClockSignalBinding = Field(alias="clockSignalBinding")
    provenance: ExternalEvidenceProvenance
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_cross_object_identity(self) -> DeploymentShadowEvidenceSet:
        profile_hash = self.controller_profile.content_hash
        if self.authority.controller_profile_content_hash != profile_hash:
            raise ValueError("authority controllerProfileContentHash mismatch")
        if self.capture.controller_profile_content_hash != profile_hash:
            raise ValueError("capture controllerProfileContentHash mismatch")
        if self.adapter_receipt.controller_profile_content_hash != profile_hash:
            raise ValueError("adapterReceipt controllerProfileContentHash mismatch")
        if self.clock_signal_binding.controller_profile_content_hash != profile_hash:
            raise ValueError("clockSignalBinding controllerProfileContentHash mismatch")
        if self.adapter_receipt.capture_content_hash != self.capture.content_hash:
            raise ValueError("adapterReceipt captureContentHash mismatch")
        if self.provenance.source_content_hash != self.capture.content_hash:
            raise ValueError("provenance sourceContentHash mismatch")
        if self.adapter_receipt.protocol != self.controller_profile.interface_type:
            raise ValueError("adapterReceipt protocol must match controller interfaceType")
        observed_sample_count = sum(len(frame.samples) for frame in self.capture.frames)
        if self.adapter_receipt.received_sample_count != observed_sample_count:
            raise ValueError("adapterReceipt receivedSampleCount mismatch")
        mapped_channels = {
            item.source_channel_id for item in self.clock_signal_binding.signal_mappings
        }
        observed_channels = {
            sample.channel_id
            for frame in self.capture.frames
            for sample in frame.samples
        }
        if not mapped_channels.issubset(observed_channels):
            raise ValueError("signalMappings must reference observed capture channels")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("DeploymentShadowEvidenceSet contentHash must match content")
        return self


class R7BReadinessCheck(AxiomModel):
    check_id: str = Field(alias="checkId", min_length=1)
    title: str = Field(min_length=1)
    status: ReadinessStatus
    reason_code: str | None = Field(default=None, alias="reasonCode")
    details: dict[str, Any] = Field(default_factory=dict)


class DeploymentShadowReadinessAudit(AxiomModel):
    artifact_type: Literal["axiom.control.deployment-shadow-readiness"] = Field(
        alias="artifactType"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    audit_id: str = Field(alias="auditId", pattern=r"^.+@[0-9]+$")
    evidence_set_content_hash: str | None = Field(
        default=None, alias="evidenceSetContentHash", pattern=_HASH_PATTERN
    )
    checks: tuple[R7BReadinessCheck, ...] = Field(min_length=6)
    readiness_outcome: Literal["Open", "Blocked"] = Field(alias="readinessOutcome")
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    contract_readiness_status: Literal["Passed"] = Field(alias="contractReadinessStatus")
    vendor_adapter_status: Literal["Open"] = Field(alias="vendorAdapterStatus")
    deployment_shadow_status: Literal["Open"] = Field(alias="deploymentShadowStatus")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    standards_compliance_status: Literal["NotAssessed"] = Field(
        alias="standardsComplianceStatus"
    )
    reality_evidence_level: Literal["None"] = Field(alias="realityEvidenceLevel")
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_audit(self) -> DeploymentShadowReadinessAudit:
        expected_ids = (
            "r7b.contract",
            "r7b.external-evidence",
            "r7b.vendor-adapter",
            "r7b.authority",
            "r7b.capture-integrity",
            "r7b.clock-signal-coverage",
            "r7b.reality-gate",
        )
        if tuple(check.check_id for check in self.checks) != expected_ids:
            raise ValueError("readiness checks must use the frozen R7-B order")
        has_blocked = any(check.status == "Blocked" for check in self.checks)
        if has_blocked != (self.readiness_outcome == "Blocked"):
            raise ValueError("readinessOutcome must reflect blocked checks")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("DeploymentShadowReadinessAudit contentHash must match content")
        return self


class R7BEvaluationRequest(AxiomModel):
    artifact: DeploymentShadowReadinessAudit
    evidence_set: DeploymentShadowEvidenceSet | None = Field(
        default=None, alias="evidenceSet"
    )
    case: EvaluationCase

    @model_validator(mode="after")
    def bind_evidence(self) -> R7BEvaluationRequest:
        expected = self.evidence_set.content_hash if self.evidence_set is not None else None
        if self.artifact.evidence_set_content_hash != expected:
            raise ValueError("readiness audit evidenceSetContentHash mismatch")
        return self


class R7BManifest(AxiomModel):
    manifest_id: Literal["control.r7b-manifest@1"] = Field(alias="manifestId")
    domain_pack_id: Literal["control.domain-pack@2"] = Field(alias="domainPackId")
    evaluator_version: Literal["control-deployment-shadow-readiness-evaluator@1"] = Field(
        alias="evaluatorVersion"
    )
    runner_id: Literal["control-deployment-shadow-import@1"] = Field(alias="runnerId")
    supported_platforms: tuple[Literal["Windows"], ...] = Field(
        alias="supportedPlatforms"
    )
    default_scenario_id: str = Field(alias="defaultScenarioId")
    scenario_ids: tuple[str, ...] = Field(alias="scenarioIds")
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    contract_readiness_status: Literal["Passed"] = Field(alias="contractReadinessStatus")
    vendor_adapter_status: Literal["Open"] = Field(alias="vendorAdapterStatus")
    deployment_shadow_status: Literal["Open"] = Field(alias="deploymentShadowStatus")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")


class R7BScenarioSummary(AxiomModel):
    scenario_id: str = Field(alias="scenarioId")
    title: str
    description: str
    expected_outcome: Literal["Inconclusive"] = Field(alias="expectedOutcome")
    expected_readiness_outcome: Literal["Open", "Blocked"] = Field(
        alias="expectedReadinessOutcome"
    )
    counts_toward_reality: Literal[False] = Field(alias="countsTowardReality")


class R7BExamplePayload(AxiomModel):
    manifest: R7BManifest
    scenario: R7BScenarioSummary
    readiness_audit: DeploymentShadowReadinessAudit = Field(alias="readinessAudit")
    evidence_set: DeploymentShadowEvidenceSet | None = Field(
        default=None, alias="evidenceSet"
    )
    run_spec: dict[str, Any] = Field(alias="runSpec")


class R7BAssessmentRequest(AxiomModel):
    evidence_set: DeploymentShadowEvidenceSet | None = Field(
        default=None, alias="evidenceSet"
    )


@dataclass(frozen=True, slots=True)
class R7BScenario:
    summary: R7BScenarioSummary
    readiness_audit: DeploymentShadowReadinessAudit
    evidence_set: DeploymentShadowEvidenceSet | None
    run_spec: dict[str, Any]


__all__ = [
    "R7B_DEFAULT_SCENARIO_ID",
    "R7B_DOMAIN_PACK_ID",
    "R7B_EVALUATOR_ID",
    "R7B_RUNNER_ID",
    "R7B_SCENARIO_IDS",
    "ClockSignalBinding",
    "DeploymentAdapterReceipt",
    "DeploymentControllerProfile",
    "DeploymentShadowCapture",
    "DeploymentShadowEvidenceSet",
    "DeploymentShadowFrame",
    "DeploymentShadowReadinessAudit",
    "DeploymentShadowSample",
    "DeploymentSignalMapping",
    "ExternalEvidenceProvenance",
    "R7BAssessmentRequest",
    "R7BEvaluationRequest",
    "R7BExamplePayload",
    "R7BManifest",
    "R7BReadinessCheck",
    "R7BScenario",
    "R7BScenarioSummary",
    "ReadOnlyAuthorityEvidence",
]
