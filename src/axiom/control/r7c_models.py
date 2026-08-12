from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel, EvaluationCase
from .models import canonical_hash

R7C_DOMAIN_PACK_ID = "control.domain-pack@3"
R7C_EVALUATOR_ID = "control-opcua-transport-readiness-evaluator@1"
R7C_RUNNER_ID = "control-opcua-transport-import@1"
R7C_DEFAULT_SCENARIO_ID = "opcua-transport-evidence-open"
R7C_SCENARIO_IDS = (R7C_DEFAULT_SCENARIO_ID,)

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_AXES = ("X", "Y", "Z", "B", "C")
_SECURITY_POLICIES = (
    "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256",
    "http://opcfoundation.org/UA/SecurityPolicy#Aes256_Sha256_RsaPss",
)


def _aware_timestamp(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


class OpcUaTransportEndpoint(AxiomModel):
    endpoint_url: str = Field(alias="endpointUrl", min_length=1)
    server_application_uri: str = Field(alias="serverApplicationUri", min_length=1)
    server_certificate_sha256: str = Field(
        alias="serverCertificateSha256", pattern=_HASH_PATTERN
    )
    client_application_uri: str = Field(alias="clientApplicationUri", min_length=1)
    client_certificate_sha256: str = Field(
        alias="clientCertificateSha256", pattern=_HASH_PATTERN
    )
    security_policy_uri: str = Field(alias="securityPolicyUri")
    message_security_mode: Literal["SignAndEncrypt"] = Field(
        alias="messageSecurityMode"
    )
    identity_type: Literal["username"] = Field(alias="identityType")
    principal_id: str = Field(alias="principalId", min_length=1)
    anonymous: Literal[False]

    @model_validator(mode="after")
    def verify_secure_endpoint(self) -> OpcUaTransportEndpoint:
        endpoint = urlparse(self.endpoint_url)
        if endpoint.scheme != "opc.tcp" or not endpoint.hostname or endpoint.port is None:
            raise ValueError("endpointUrl must be an absolute opc.tcp URL with a port")
        for name, value in (
            ("serverApplicationUri", self.server_application_uri),
            ("clientApplicationUri", self.client_application_uri),
        ):
            parsed = urlparse(value)
            if parsed.scheme != "urn":
                raise ValueError(f"{name} must be an absolute urn")
        if self.security_policy_uri not in _SECURITY_POLICIES:
            raise ValueError("securityPolicyUri is not in the frozen allowlist")
        return self


class OpcUaSubscriptionEvidence(AxiomModel):
    requested_publishing_interval_ms: int = Field(
        alias="requestedPublishingIntervalMs", ge=10, le=10_000
    )
    revised_publishing_interval_ms: int = Field(
        alias="revisedPublishingIntervalMs", gt=0, le=10_000
    )
    requested_sampling_interval_ms: int = Field(
        alias="requestedSamplingIntervalMs", ge=1, le=10_000
    )
    queue_size: int = Field(alias="queueSize", ge=1, le=10_000)
    monitored_item_count: Literal[5] = Field(alias="monitoredItemCount")


class OpcUaChannelEvidence(AxiomModel):
    channel_id: str = Field(alias="channelId", min_length=1)
    namespace_uri: str = Field(alias="namespaceUri", min_length=1)
    identifier: str = Field(min_length=1)
    canonical_signal_id: str = Field(alias="canonicalSignalId", min_length=1)
    quantity: Literal["axis-position"]
    axis_id: Literal["X", "Y", "Z", "B", "C"] = Field(alias="axisId")
    unit: Literal["mm", "rad"]

    @model_validator(mode="after")
    def verify_axis_unit(self) -> OpcUaChannelEvidence:
        if urlparse(self.namespace_uri).scheme not in {"urn", "http", "https"}:
            raise ValueError("namespaceUri must be absolute")
        expected = "mm" if self.axis_id in {"X", "Y", "Z"} else "rad"
        if self.unit != expected:
            raise ValueError(f"axis {self.axis_id} must use {expected}")
        return self


class OpcUaTransportSample(AxiomModel):
    channel_id: str = Field(alias="channelId", min_length=1)
    value_type: Literal["Double"] = Field(alias="valueType")
    value_text: str = Field(alias="valueText", min_length=1)
    unit: Literal["mm", "rad"]
    quality: Literal["good"]
    status_code: Literal["Good"] = Field(alias="statusCode")
    source_timestamp: str = Field(alias="sourceTimestamp", min_length=1)
    server_timestamp: str = Field(alias="serverTimestamp", min_length=1)

    @field_validator("source_timestamp", "server_timestamp")
    @classmethod
    def require_aware_timestamps(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @field_validator("value_text")
    @classmethod
    def require_finite_number(cls, value: str) -> str:
        try:
            parsed = float(value)
        except ValueError as exc:
            raise ValueError("valueText must contain a JSON-compatible number") from exc
        if not math.isfinite(parsed):
            raise ValueError("valueText must be finite")
        return value


class OpcUaTransportFrame(AxiomModel):
    sequence: int = Field(ge=0)
    protocol_sequence_number: int = Field(alias="protocolSequenceNumber", ge=1)
    host_timestamp: str = Field(alias="hostTimestamp", min_length=1)
    samples: tuple[OpcUaTransportSample, ...] = Field(min_length=5, max_length=5)

    @field_validator("host_timestamp")
    @classmethod
    def require_aware_host_timestamp(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="hostTimestamp")

    @model_validator(mode="after")
    def require_unique_channels(self) -> OpcUaTransportFrame:
        channels = tuple(sample.channel_id for sample in self.samples)
        if len(channels) != len(set(channels)):
            raise ValueError("frame samples must have unique channelId values")
        return self


class OpcUaTransportReceipt(AxiomModel):
    status: Literal["Succeeded"]
    opened_at: str = Field(alias="openedAt", min_length=1)
    closed_at: str = Field(alias="closedAt", min_length=1)
    read_operation_count: Literal[0] = Field(alias="readOperationCount")
    subscribe_operation_count: Literal[1] = Field(alias="subscribeOperationCount")
    write_operation_count: Literal[0] = Field(alias="writeOperationCount")
    method_call_operation_count: Literal[0] = Field(alias="methodCallOperationCount")
    received_frame_count: int = Field(alias="receivedFrameCount", ge=2)
    received_sample_count: int = Field(alias="receivedSampleCount", ge=10)
    dropped_notification_count: int = Field(alias="droppedNotificationCount", ge=0)
    transcript_content_hash: str = Field(
        alias="transcriptContentHash", pattern=_HASH_PATTERN
    )

    @field_validator("opened_at", "closed_at")
    @classmethod
    def require_aware_timestamps(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @model_validator(mode="after")
    def verify_interval(self) -> OpcUaTransportReceipt:
        if datetime.fromisoformat(self.closed_at) < datetime.fromisoformat(self.opened_at):
            raise ValueError("closedAt must not precede openedAt")
        return self


class OpcUaTransportEvidence(AxiomModel):
    schema_id: Literal["axiom.control.opcua-transport-evidence@1"] = Field(
        alias="schemaId"
    )
    evidence_id: str = Field(alias="evidenceId", pattern=r"^.+@[0-9]+$")
    adapter_id: Literal["axiom.control.opcua-shadow-read-adapter@1"] = Field(
        alias="adapterId"
    )
    adapter_version: str = Field(alias="adapterVersion", min_length=1)
    platform: Literal["Windows"]
    protocol: Literal["opc-ua"]
    access_mode: Literal["read-subscribe-only"] = Field(alias="accessMode")
    declared_real: Literal[False] = Field(alias="declaredReal")
    counts_toward_reality: Literal[False] = Field(alias="countsTowardReality")
    config_file_sha256: str = Field(alias="configFileSha256", pattern=_HASH_PATTERN)
    endpoint: OpcUaTransportEndpoint
    subscription: OpcUaSubscriptionEvidence
    channels: tuple[OpcUaChannelEvidence, ...] = Field(min_length=5, max_length=5)
    frames: tuple[OpcUaTransportFrame, ...] = Field(min_length=2)
    receipt: OpcUaTransportReceipt
    virtual_transport_status: Literal["Passed"] = Field(alias="virtualTransportStatus")
    vendor_adapter_status: Literal["Open"] = Field(alias="vendorAdapterStatus")
    reality_validation_status: Literal["Open"] = Field(
        alias="realityValidationStatus"
    )
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(
        alias="processSafetyStatus"
    )
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_transport_contract(self) -> OpcUaTransportEvidence:
        axes = tuple(channel.axis_id for channel in self.channels)
        if axes != _AXES:
            raise ValueError("channels must use the frozen X/Y/Z/B/C order")
        channel_ids = tuple(channel.channel_id for channel in self.channels)
        canonical_ids = tuple(channel.canonical_signal_id for channel in self.channels)
        if len(set(channel_ids)) != 5 or len(set(canonical_ids)) != 5:
            raise ValueError("channels must have unique channelId and canonicalSignalId values")
        if tuple(frame.sequence for frame in self.frames) != tuple(range(len(self.frames))):
            raise ValueError("frame sequence must be contiguous")
        protocol_sequences = tuple(
            frame.protocol_sequence_number for frame in self.frames
        )
        if any(right <= left for left, right in zip(protocol_sequences, protocol_sequences[1:])):
            raise ValueError("protocolSequenceNumber must be strictly increasing")
        host_times = tuple(datetime.fromisoformat(frame.host_timestamp) for frame in self.frames)
        if any(right <= left for left, right in zip(host_times, host_times[1:])):
            raise ValueError("hostTimestamp must be strictly increasing")
        for frame in self.frames:
            if tuple(sample.channel_id for sample in frame.samples) != channel_ids:
                raise ValueError("every frame must use the frozen channel order")
            for channel, sample in zip(self.channels, frame.samples):
                if sample.unit != channel.unit:
                    raise ValueError("sample unit must match channel unit")
        for channel_index in range(5):
            source_times = tuple(
                datetime.fromisoformat(frame.samples[channel_index].source_timestamp)
                for frame in self.frames
            )
            if any(right <= left for left, right in zip(source_times, source_times[1:])):
                raise ValueError("sourceTimestamp must be strictly increasing per channel")
        dropped = sum(
            right - left - 1
            for left, right in zip(protocol_sequences, protocol_sequences[1:])
        )
        if self.receipt.dropped_notification_count != dropped:
            raise ValueError("droppedNotificationCount must match protocol sequence gaps")
        if dropped != 0:
            raise ValueError("Passed virtual transport evidence cannot contain dropped notifications")
        if self.receipt.received_frame_count != len(self.frames):
            raise ValueError("receivedFrameCount mismatch")
        if self.receipt.received_sample_count != len(self.frames) * 5:
            raise ValueError("receivedSampleCount mismatch")
        if self.receipt.transcript_content_hash != canonical_hash(list(self.frames)):
            raise ValueError("transcriptContentHash must match frames")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("OpcUaTransportEvidence contentHash must match content")
        return self


class R7CReadinessCheck(AxiomModel):
    check_id: str = Field(alias="checkId", min_length=1)
    title: str = Field(min_length=1)
    status: Literal["Passed", "Open", "Blocked"]
    reason_code: str | None = Field(default=None, alias="reasonCode")
    details: dict[str, Any] = Field(default_factory=dict)


class OpcUaTransportReadinessAudit(AxiomModel):
    artifact_type: Literal["axiom.control.opcua-transport-readiness"] = Field(
        alias="artifactType"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    audit_id: Literal["control.r7c.opcua-transport-readiness-audit@1"] = Field(
        alias="auditId"
    )
    transport_evidence_content_hash: str | None = Field(
        default=None, alias="transportEvidenceContentHash", pattern=_HASH_PATTERN
    )
    checks: tuple[R7CReadinessCheck, ...] = Field(min_length=7, max_length=7)
    readiness_outcome: Literal["Open", "Blocked"] = Field(alias="readinessOutcome")
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    adapter_contract_status: Literal["Passed"] = Field(alias="adapterContractStatus")
    virtual_transport_status: Literal["Open", "Passed"] = Field(
        alias="virtualTransportStatus"
    )
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
    def verify_audit(self) -> OpcUaTransportReadinessAudit:
        expected_ids = (
            "r7c.contract",
            "r7c.transport-evidence",
            "r7c.secure-channel",
            "r7c.subscription-integrity",
            "r7c.zero-write",
            "r7c.vendor-adapter",
            "r7c.reality-gate",
        )
        if tuple(check.check_id for check in self.checks) != expected_ids:
            raise ValueError("readiness checks must use the frozen R7-C order")
        has_blocked = any(check.status == "Blocked" for check in self.checks)
        if has_blocked != (self.readiness_outcome == "Blocked"):
            raise ValueError("readinessOutcome must reflect blocked checks")
        evidence_passed = self.checks[1].status == "Passed"
        if evidence_passed != (self.virtual_transport_status == "Passed"):
            raise ValueError("virtualTransportStatus must reflect transport evidence")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("OpcUaTransportReadinessAudit contentHash must match content")
        return self


class R7CEvaluationRequest(AxiomModel):
    artifact: OpcUaTransportReadinessAudit
    transport_evidence: OpcUaTransportEvidence | None = Field(
        default=None, alias="transportEvidence"
    )
    case: EvaluationCase

    @model_validator(mode="after")
    def bind_evidence(self) -> R7CEvaluationRequest:
        expected = (
            self.transport_evidence.content_hash
            if self.transport_evidence is not None
            else None
        )
        if self.artifact.transport_evidence_content_hash != expected:
            raise ValueError("audit transportEvidenceContentHash mismatch")
        return self


class R7CManifest(AxiomModel):
    manifest_id: Literal["control.r7c-manifest@1"] = Field(alias="manifestId")
    domain_pack_id: Literal["control.domain-pack@3"] = Field(alias="domainPackId")
    evaluator_version: Literal[
        "control-opcua-transport-readiness-evaluator@1"
    ] = Field(alias="evaluatorVersion")
    runner_id: Literal["control-opcua-transport-import@1"] = Field(alias="runnerId")
    adapter_id: Literal["axiom.control.opcua-shadow-read-adapter@1"] = Field(
        alias="adapterId"
    )
    adapter_version: Literal["0.1.0"] = Field(alias="adapterVersion")
    protocol_stack: Literal[
        "OPCFoundation.NetStandard.Opc.Ua.Client@1.5.378.156"
    ] = Field(alias="protocolStack")
    supported_platforms: tuple[Literal["Windows"], ...] = Field(
        alias="supportedPlatforms"
    )
    default_scenario_id: str = Field(alias="defaultScenarioId")
    scenario_ids: tuple[str, ...] = Field(alias="scenarioIds")
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    adapter_contract_status: Literal["Passed"] = Field(alias="adapterContractStatus")
    network_conformance_status: Literal["Passed"] = Field(
        alias="networkConformanceStatus"
    )
    vendor_adapter_status: Literal["Open"] = Field(alias="vendorAdapterStatus")
    reality_validation_status: Literal["Open"] = Field(
        alias="realityValidationStatus"
    )


class R7CScenarioSummary(AxiomModel):
    scenario_id: str = Field(alias="scenarioId")
    title: str
    description: str
    expected_outcome: Literal["Inconclusive"] = Field(alias="expectedOutcome")
    expected_readiness_outcome: Literal["Open"] = Field(
        alias="expectedReadinessOutcome"
    )
    counts_toward_reality: Literal[False] = Field(alias="countsTowardReality")


class R7CExamplePayload(AxiomModel):
    manifest: R7CManifest
    scenario: R7CScenarioSummary
    readiness_audit: OpcUaTransportReadinessAudit = Field(alias="readinessAudit")
    transport_evidence: OpcUaTransportEvidence | None = Field(
        default=None, alias="transportEvidence"
    )
    run_spec: dict[str, Any] = Field(alias="runSpec")


class R7CAssessmentRequest(AxiomModel):
    transport_evidence: OpcUaTransportEvidence | None = Field(
        default=None, alias="transportEvidence"
    )


@dataclass(frozen=True, slots=True)
class R7CScenario:
    summary: R7CScenarioSummary
    readiness_audit: OpcUaTransportReadinessAudit
    transport_evidence: OpcUaTransportEvidence | None
    run_spec: dict[str, Any]


__all__ = [
    "R7CAssessmentRequest",
    "R7CExamplePayload",
    "R7CManifest",
    "R7CScenarioSummary",
    "R7C_DEFAULT_SCENARIO_ID",
    "R7C_DOMAIN_PACK_ID",
    "R7C_EVALUATOR_ID",
    "R7C_RUNNER_ID",
    "R7C_SCENARIO_IDS",
    "OpcUaTransportEvidence",
    "OpcUaTransportReadinessAudit",
]
