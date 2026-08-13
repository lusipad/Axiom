from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from ..five_axis.f3_sampling import M5DiscreteCommand
from ..models import AxiomModel, EvaluationCase, _require_json_number
from .models import canonical_hash
from .r7b_models import (
    DeploymentControllerProfile,
    ReadOnlyAuthorityEvidence,
)
from .r7d_models import BeckhoffRuntimeEvidence, BeckhoffTwinCatVendorProfile

R7E_DOMAIN_PACK_ID = "control.domain-pack@5"
R7E_EVALUATOR_ID = "control-beckhoff-shadow-run-evaluator@1"
R7E_RUNNER_ID = "control-beckhoff-shadow-evidence-import@1"
R7E_DEFAULT_SCENARIO_ID = "beckhoff-shadow-witness-open"
R7E_DEFAULT_CASE_ID = "control.r7e.beckhoff-shadow-run.case@1"
R7E_SCENARIO_IDS = (R7E_DEFAULT_SCENARIO_ID,)

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_AXES = ("X", "Y", "Z", "B", "C")
_NODE_ROLES = (
    "command-content-hash",
    "sample-index",
    "axis-position",
    "axis-position",
    "axis-position",
    "axis-position",
    "axis-position",
)
_CANONICAL_SIGNALS = (
    "command.content-hash",
    "command.sample-index",
    "machine.axis.X.position",
    "machine.axis.Y.position",
    "machine.axis.Z.position",
    "machine.axis.B.position",
    "machine.axis.C.position",
)


def _aware_timestamp(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


def _absolute_namespace(value: str) -> str:
    if urlparse(value).scheme not in {"urn", "http", "https"}:
        raise ValueError("namespaceUri must be absolute")
    return value


class BeckhoffShadowWitnessNode(AxiomModel):
    canonical_signal_id: str = Field(alias="canonicalSignalId", min_length=1)
    role: Literal["command-content-hash", "sample-index", "axis-position"]
    axis_id: Literal["X", "Y", "Z", "B", "C"] | None = Field(
        default=None, alias="axisId"
    )
    namespace_uri: str = Field(alias="namespaceUri", min_length=1)
    identifier: str = Field(min_length=1)
    expected_data_type: Literal["String", "UInt32", "Double"] = Field(
        alias="expectedDataType"
    )
    unit: Literal["sha256", "index", "mm", "rad"]
    required_access_level: Literal[1] = Field(alias="requiredAccessLevel")
    required_user_access_level: Literal[1] = Field(alias="requiredUserAccessLevel")

    @field_validator("namespace_uri")
    @classmethod
    def require_absolute_namespace(cls, value: str) -> str:
        return _absolute_namespace(value)

    @model_validator(mode="after")
    def verify_role_contract(self) -> BeckhoffShadowWitnessNode:
        if self.role == "command-content-hash":
            expected = (None, "String", "sha256")
        elif self.role == "sample-index":
            expected = (None, "UInt32", "index")
        else:
            if self.axis_id is None:
                raise ValueError("axis-position node requires axisId")
            expected = (
                self.axis_id,
                "Double",
                "mm" if self.axis_id in {"X", "Y", "Z"} else "rad",
            )
        if (self.axis_id, self.expected_data_type, self.unit) != expected:
            raise ValueError("witness node role, axisId, data type and unit disagree")
        return self


class BeckhoffShadowWitnessProfile(AxiomModel):
    schema_id: Literal["axiom.control.beckhoff-shadow-witness-profile@1"] = Field(
        alias="schemaId"
    )
    profile_id: str = Field(alias="profileId", pattern=r"^.+@[0-9]+$")
    vendor_profile_content_hash: str = Field(
        alias="vendorProfileContentHash", pattern=_HASH_PATTERN
    )
    runtime_evidence_content_hash: str | None = Field(
        default=None, alias="runtimeEvidenceContentHash", pattern=_HASH_PATTERN
    )
    node_verification_evidence_content_hash: str | None = Field(
        default=None,
        alias="nodeVerificationEvidenceContentHash",
        pattern=_HASH_PATTERN,
    )
    expected_command_content_hash: str | None = Field(
        default=None, alias="expectedCommandContentHash", pattern=_HASH_PATTERN
    )
    binding_status: Literal["Open", "Bound"] = Field(alias="bindingStatus")
    platform: Literal["Windows"]
    protocol: Literal["opc-ua"]
    capture_policy: Literal["sample-index-triggered-batch-read"] = Field(
        alias="capturePolicy"
    )
    interval_policy: Literal["exact-sample-index-no-interpolation"] = Field(
        alias="intervalPolicy"
    )
    maximum_timestamp_uncertainty_ms: float = Field(
        alias="maximumTimestampUncertaintyMs", ge=0.0
    )
    maximum_sample_index_gap: Literal[0] = Field(alias="maximumSampleIndexGap")
    nodes: tuple[BeckhoffShadowWitnessNode, ...] = ()
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    method_call_allowed: Literal[False] = Field(alias="methodCallAllowed")
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @field_validator("maximum_timestamp_uncertainty_ms", mode="before")
    @classmethod
    def reject_non_json_number(cls, value: Any) -> Any:
        return _require_json_number(value)

    @model_validator(mode="after")
    def verify_binding(self) -> BeckhoffShadowWitnessProfile:
        if self.binding_status == "Open":
            if (
                self.runtime_evidence_content_hash is not None
                or self.node_verification_evidence_content_hash is not None
                or self.expected_command_content_hash is not None
                or self.nodes
            ):
                raise ValueError("Open witness profile cannot contain deployment bindings")
        else:
            if (
                self.runtime_evidence_content_hash is None
                or self.node_verification_evidence_content_hash is None
                or self.expected_command_content_hash is None
                or len(self.nodes) != 7
            ):
                raise ValueError(
                    "Bound witness profile requires runtime, node verification, command and seven nodes"
                )
            roles = tuple(node.role for node in self.nodes)
            canonical = tuple(node.canonical_signal_id for node in self.nodes)
            axes = tuple(node.axis_id for node in self.nodes[2:])
            if roles != _NODE_ROLES or canonical != _CANONICAL_SIGNALS or axes != _AXES:
                raise ValueError(
                    "Bound witness nodes must use command hash, sample index and X/Y/Z/B/C order"
                )
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("BeckhoffShadowWitnessProfile contentHash must match content")
        return self


class BeckhoffShadowAxisSample(AxiomModel):
    axis_id: Literal["X", "Y", "Z", "B", "C"] = Field(alias="axisId")
    value: float
    unit: Literal["mm", "rad"]
    quality: Literal["good", "suspect", "bad"]
    status_code: str = Field(alias="statusCode", min_length=1)
    source_timestamp: str = Field(alias="sourceTimestamp", min_length=1)
    server_timestamp: str = Field(alias="serverTimestamp", min_length=1)

    @field_validator("value", mode="before")
    @classmethod
    def require_finite_number(cls, value: Any) -> Any:
        value = _require_json_number(value)
        if not math.isfinite(float(value)):
            raise ValueError("value must be finite")
        return value

    @field_validator("source_timestamp", "server_timestamp")
    @classmethod
    def require_aware_timestamps(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @model_validator(mode="after")
    def verify_unit(self) -> BeckhoffShadowAxisSample:
        expected = "mm" if self.axis_id in {"X", "Y", "Z"} else "rad"
        if self.unit != expected:
            raise ValueError(f"axis {self.axis_id} must use {expected}")
        return self


class BeckhoffShadowWitnessFrame(AxiomModel):
    sequence: int = Field(ge=0)
    protocol_sequence_number: int = Field(alias="protocolSequenceNumber", ge=1)
    notified_sample_index: int = Field(alias="notifiedSampleIndex", ge=0)
    read_sample_index: int = Field(alias="readSampleIndex", ge=0)
    command_content_hash: str = Field(alias="commandContentHash", pattern=_HASH_PATTERN)
    host_timestamp: str = Field(alias="hostTimestamp", min_length=1)
    samples: tuple[BeckhoffShadowAxisSample, ...] = Field(min_length=5, max_length=5)

    @field_validator("host_timestamp")
    @classmethod
    def require_aware_host_timestamp(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="hostTimestamp")

    @model_validator(mode="after")
    def verify_axes(self) -> BeckhoffShadowWitnessFrame:
        if tuple(sample.axis_id for sample in self.samples) != _AXES:
            raise ValueError("frame samples must use the frozen X/Y/Z/B/C order")
        return self


class BeckhoffShadowCaptureReceipt(AxiomModel):
    status: Literal["Succeeded", "Failed"]
    opened_at: str = Field(alias="openedAt", min_length=1)
    closed_at: str = Field(alias="closedAt", min_length=1)
    subscribe_operation_count: Literal[1] = Field(alias="subscribeOperationCount")
    read_operation_count: int = Field(alias="readOperationCount", ge=0)
    write_operation_count: Literal[0] = Field(alias="writeOperationCount")
    method_call_operation_count: Literal[0] = Field(alias="methodCallOperationCount")
    received_frame_count: int = Field(alias="receivedFrameCount", ge=0)
    accepted_frame_count: int = Field(alias="acceptedFrameCount", ge=0)
    rejected_frame_count: int = Field(alias="rejectedFrameCount", ge=0)
    dropped_sample_index_count: int = Field(alias="droppedSampleIndexCount", ge=0)
    transcript_content_hash: str = Field(
        alias="transcriptContentHash", pattern=_HASH_PATTERN
    )

    @field_validator("opened_at", "closed_at")
    @classmethod
    def require_aware_timestamps(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @model_validator(mode="after")
    def verify_receipt(self) -> BeckhoffShadowCaptureReceipt:
        if datetime.fromisoformat(self.closed_at) < datetime.fromisoformat(self.opened_at):
            raise ValueError("closedAt must not precede openedAt")
        if self.accepted_frame_count + self.rejected_frame_count != self.received_frame_count:
            raise ValueError("accepted plus rejected frames must equal received frames")
        if self.status == "Succeeded" and self.accepted_frame_count == 0:
            raise ValueError("Succeeded receipt requires an accepted frame")
        return self


class BeckhoffShadowCaptureAuthorization(AxiomModel):
    schema_id: Literal["axiom.control.beckhoff-shadow-capture-authorization@1"] = Field(
        alias="schemaId"
    )
    authorization_id: str = Field(alias="authorizationId", pattern=r"^.+@[0-9]+$")
    data_owner_id: str = Field(alias="dataOwnerId", min_length=1)
    controller_profile_content_hash: str = Field(
        alias="controllerProfileContentHash", pattern=_HASH_PATTERN
    )
    command_content_hash: str = Field(alias="commandContentHash", pattern=_HASH_PATTERN)
    authorized_from: str = Field(alias="authorizedFrom", min_length=1)
    authorized_until: str = Field(alias="authorizedUntil", min_length=1)
    acquisition_purpose: Literal["deployment-shadow-validation"] = Field(
        alias="acquisitionPurpose"
    )
    captured_outside_repository: Literal[True] = Field(
        alias="capturedOutsideRepository"
    )
    evaluation_authorized: Literal[True] = Field(alias="evaluationAuthorized")
    attestation_kind: Literal["data-owner-attestation"] = Field(
        alias="attestationKind"
    )
    attestation_content_hash: str = Field(
        alias="attestationContentHash", pattern=_HASH_PATTERN
    )
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @field_validator("authorized_from", "authorized_until")
    @classmethod
    def require_aware_authorization_window(cls, value: str, info: Any) -> str:
        return _aware_timestamp(value, field_name=info.field_name)

    @model_validator(mode="after")
    def verify_authorization(self) -> BeckhoffShadowCaptureAuthorization:
        if datetime.fromisoformat(self.authorized_until) <= datetime.fromisoformat(
            self.authorized_from
        ):
            raise ValueError("authorizedUntil must be later than authorizedFrom")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError(
                "BeckhoffShadowCaptureAuthorization contentHash must match content"
            )
        return self


class BeckhoffShadowRunEvidence(AxiomModel):
    schema_id: Literal["axiom.control.beckhoff-shadow-run-evidence@1"] = Field(
        alias="schemaId"
    )
    evidence_id: str = Field(alias="evidenceId", pattern=r"^.+@[0-9]+$")
    adapter_id: Literal["axiom.control.beckhoff-shadow-witness-adapter@1"] = Field(
        alias="adapterId"
    )
    adapter_version: str = Field(alias="adapterVersion", min_length=1)
    platform: Literal["Windows"]
    source_kind: Literal["controller-live-read", "contract-fixture"] = Field(
        alias="sourceKind"
    )
    declared_real: bool = Field(alias="declaredReal")
    controller_profile_content_hash: str = Field(
        alias="controllerProfileContentHash", pattern=_HASH_PATTERN
    )
    authority_content_hash: str = Field(alias="authorityContentHash", pattern=_HASH_PATTERN)
    capture_authorization_content_hash: str = Field(
        alias="captureAuthorizationContentHash", pattern=_HASH_PATTERN
    )
    vendor_profile_content_hash: str = Field(
        alias="vendorProfileContentHash", pattern=_HASH_PATTERN
    )
    runtime_evidence_content_hash: str = Field(
        alias="runtimeEvidenceContentHash", pattern=_HASH_PATTERN
    )
    witness_profile_content_hash: str = Field(
        alias="witnessProfileContentHash", pattern=_HASH_PATTERN
    )
    command_content_hash: str = Field(alias="commandContentHash", pattern=_HASH_PATTERN)
    captured_at: str = Field(alias="capturedAt", min_length=1)
    frames: tuple[BeckhoffShadowWitnessFrame, ...] = ()
    receipt: BeckhoffShadowCaptureReceipt
    counts_toward_reality: Literal[False] = Field(alias="countsTowardReality")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(alias="processSafetyStatus")
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @field_validator("captured_at")
    @classmethod
    def require_aware_capture_time(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="capturedAt")

    @model_validator(mode="after")
    def verify_evidence(self) -> BeckhoffShadowRunEvidence:
        if self.source_kind == "contract-fixture" and self.declared_real:
            raise ValueError("contract-fixture cannot declare real evidence")
        if self.source_kind == "controller-live-read" and not self.declared_real:
            raise ValueError("controller-live-read must explicitly declare real evidence")
        if self.receipt.received_frame_count != len(self.frames):
            raise ValueError("receivedFrameCount must match frames")
        if self.receipt.transcript_content_hash != canonical_hash(list(self.frames)):
            raise ValueError("transcriptContentHash must match frames")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("BeckhoffShadowRunEvidence contentHash must match content")
        return self


class R7EReadinessCheck(AxiomModel):
    check_id: str = Field(alias="checkId", min_length=1)
    title: str = Field(min_length=1)
    status: Literal["Passed", "Open", "Blocked"]
    reason_code: str | None = Field(default=None, alias="reasonCode")
    details: dict[str, Any] = Field(default_factory=dict)


class BeckhoffShadowRunReadinessAudit(AxiomModel):
    artifact_type: Literal["axiom.control.beckhoff-shadow-run-readiness"] = Field(
        alias="artifactType"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    audit_id: Literal["control.r7e.beckhoff-shadow-run-readiness-audit@1"] = Field(
        alias="auditId"
    )
    vendor_profile_content_hash: str = Field(
        alias="vendorProfileContentHash", pattern=_HASH_PATTERN
    )
    witness_profile_content_hash: str = Field(
        alias="witnessProfileContentHash", pattern=_HASH_PATTERN
    )
    runtime_evidence_content_hash: str | None = Field(
        default=None, alias="runtimeEvidenceContentHash", pattern=_HASH_PATTERN
    )
    controller_profile_content_hash: str | None = Field(
        default=None, alias="controllerProfileContentHash", pattern=_HASH_PATTERN
    )
    authority_content_hash: str | None = Field(
        default=None, alias="authorityContentHash", pattern=_HASH_PATTERN
    )
    capture_authorization_content_hash: str | None = Field(
        default=None, alias="captureAuthorizationContentHash", pattern=_HASH_PATTERN
    )
    command_content_hash: str | None = Field(
        default=None, alias="commandContentHash", pattern=_HASH_PATTERN
    )
    shadow_evidence_content_hash: str | None = Field(
        default=None, alias="shadowEvidenceContentHash", pattern=_HASH_PATTERN
    )
    checks: tuple[R7EReadinessCheck, ...] = Field(min_length=11, max_length=11)
    readiness_outcome: Literal["Passed", "Open", "Blocked"] = Field(
        alias="readinessOutcome"
    )
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    contract_status: Literal["Passed"] = Field(alias="contractStatus")
    vendor_runtime_status: Literal["Open", "Passed", "Blocked"] = Field(
        alias="vendorRuntimeStatus"
    )
    deployment_shadow_status: Literal["Open", "Passed", "Blocked"] = Field(
        alias="deploymentShadowStatus"
    )
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    counts_toward_deployment_shadow: bool = Field(
        alias="countsTowardDeploymentShadow"
    )
    counts_toward_reality: Literal[False] = Field(alias="countsTowardReality")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(alias="processSafetyStatus")
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_audit(self) -> BeckhoffShadowRunReadinessAudit:
        expected_ids = (
            "r7e.contract",
            "r7e.vendor-runtime",
            "r7e.witness-profile",
            "r7e.authority",
            "r7e.command-binding",
            "r7e.external-provenance",
            "r7e.frame-coverage",
            "r7e.timestamp-integrity",
            "r7e.zero-write",
            "r7e.deployment-shadow",
            "r7e.reality-gate",
        )
        if tuple(check.check_id for check in self.checks) != expected_ids:
            raise ValueError("readiness checks must use the frozen R7-E order")
        expected_outcome = (
            "Blocked"
            if any(check.status == "Blocked" for check in self.checks)
            else "Passed"
            if self.deployment_shadow_status == "Passed"
            else "Open"
        )
        if self.readiness_outcome != expected_outcome:
            raise ValueError("readinessOutcome must reflect R7-E checks")
        if self.counts_toward_deployment_shadow != (
            self.deployment_shadow_status == "Passed"
        ):
            raise ValueError("countsTowardDeploymentShadow must reflect the shadow gate")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("BeckhoffShadowRunReadinessAudit contentHash must match content")
        return self


class R7EEvaluationRequest(AxiomModel):
    artifact: BeckhoffShadowRunReadinessAudit
    vendor_profile: BeckhoffTwinCatVendorProfile = Field(alias="vendorProfile")
    runtime_evidence: BeckhoffRuntimeEvidence | None = Field(
        default=None, alias="runtimeEvidence"
    )
    witness_profile: BeckhoffShadowWitnessProfile = Field(alias="witnessProfile")
    controller_profile: DeploymentControllerProfile | None = Field(
        default=None, alias="controllerProfile"
    )
    authority: ReadOnlyAuthorityEvidence | None = None
    capture_authorization: BeckhoffShadowCaptureAuthorization | None = Field(
        default=None, alias="captureAuthorization"
    )
    command: M5DiscreteCommand | None = None
    shadow_evidence: BeckhoffShadowRunEvidence | None = Field(
        default=None, alias="shadowEvidence"
    )
    case: EvaluationCase

    @model_validator(mode="after")
    def bind_support(self) -> R7EEvaluationRequest:
        expected = {
            "vendor_profile_content_hash": self.vendor_profile.content_hash,
            "witness_profile_content_hash": self.witness_profile.content_hash,
            "runtime_evidence_content_hash": (
                self.runtime_evidence.content_hash if self.runtime_evidence else None
            ),
            "controller_profile_content_hash": (
                self.controller_profile.content_hash if self.controller_profile else None
            ),
            "authority_content_hash": self.authority.content_hash if self.authority else None,
            "capture_authorization_content_hash": (
                self.capture_authorization.content_hash
                if self.capture_authorization
                else None
            ),
            "command_content_hash": self.command.content_id if self.command else None,
            "shadow_evidence_content_hash": (
                self.shadow_evidence.content_hash if self.shadow_evidence else None
            ),
        }
        for field_name, value in expected.items():
            if getattr(self.artifact, field_name) != value:
                alias = "".join(
                    word.title() if index else word
                    for index, word in enumerate(field_name.split("_"))
                )
                raise ValueError(f"audit {alias} mismatch")
        return self


class R7EManifest(AxiomModel):
    manifest_id: Literal["control.r7e-manifest@1"] = Field(alias="manifestId")
    domain_pack_id: Literal["control.domain-pack@5"] = Field(alias="domainPackId")
    evaluator_version: Literal["control-beckhoff-shadow-run-evaluator@1"] = Field(
        alias="evaluatorVersion"
    )
    runner_id: Literal["control-beckhoff-shadow-evidence-import@1"] = Field(
        alias="runnerId"
    )
    adapter_id: Literal["axiom.control.beckhoff-shadow-witness-adapter@1"] = Field(
        alias="adapterId"
    )
    target_vendor: Literal["Beckhoff Automation"] = Field(alias="targetVendor")
    target_controller_family: Literal["TwinCAT 3"] = Field(
        alias="targetControllerFamily"
    )
    minimum_twincat_build: Literal[4026] = Field(alias="minimumTwinCatBuild")
    target_interface: Literal["TF6100 OPC UA Server"] = Field(
        alias="targetInterface"
    )
    supported_platforms: tuple[Literal["Windows"], ...] = Field(
        alias="supportedPlatforms"
    )
    capture_policy: Literal["sample-index-triggered-batch-read"] = Field(
        alias="capturePolicy"
    )
    default_scenario_id: str = Field(alias="defaultScenarioId")
    scenario_ids: tuple[str, ...] = Field(alias="scenarioIds")
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    deployment_shadow_status: Literal["Open"] = Field(alias="deploymentShadowStatus")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(alias="processSafetyStatus")


class R7EScenarioSummary(AxiomModel):
    scenario_id: str = Field(alias="scenarioId")
    title: str
    description: str
    expected_outcome: Literal["Inconclusive"] = Field(alias="expectedOutcome")
    expected_readiness_outcome: Literal["Open"] = Field(
        alias="expectedReadinessOutcome"
    )
    counts_toward_deployment_shadow: Literal[False] = Field(
        alias="countsTowardDeploymentShadow"
    )
    counts_toward_reality: Literal[False] = Field(alias="countsTowardReality")


class R7EExamplePayload(AxiomModel):
    manifest: R7EManifest
    scenario: R7EScenarioSummary
    vendor_profile: BeckhoffTwinCatVendorProfile = Field(alias="vendorProfile")
    runtime_evidence: BeckhoffRuntimeEvidence | None = Field(
        default=None, alias="runtimeEvidence"
    )
    witness_profile: BeckhoffShadowWitnessProfile = Field(alias="witnessProfile")
    controller_profile: DeploymentControllerProfile | None = Field(
        default=None, alias="controllerProfile"
    )
    authority: ReadOnlyAuthorityEvidence | None = None
    capture_authorization: BeckhoffShadowCaptureAuthorization | None = Field(
        default=None, alias="captureAuthorization"
    )
    command: M5DiscreteCommand | None = None
    shadow_evidence: BeckhoffShadowRunEvidence | None = Field(
        default=None, alias="shadowEvidence"
    )
    readiness_audit: BeckhoffShadowRunReadinessAudit = Field(alias="readinessAudit")
    run_spec: dict[str, Any] = Field(alias="runSpec")


class R7EAssessmentRequest(AxiomModel):
    case_id: str | None = Field(default=None, alias="caseId", min_length=1)
    vendor_profile: BeckhoffTwinCatVendorProfile | None = Field(
        default=None, alias="vendorProfile"
    )
    runtime_evidence: BeckhoffRuntimeEvidence | None = Field(
        default=None, alias="runtimeEvidence"
    )
    witness_profile: BeckhoffShadowWitnessProfile | None = Field(
        default=None, alias="witnessProfile"
    )
    controller_profile: DeploymentControllerProfile | None = Field(
        default=None, alias="controllerProfile"
    )
    authority: ReadOnlyAuthorityEvidence | None = None
    capture_authorization: BeckhoffShadowCaptureAuthorization | None = Field(
        default=None, alias="captureAuthorization"
    )
    command: M5DiscreteCommand | None = None
    shadow_evidence: BeckhoffShadowRunEvidence | None = Field(
        default=None, alias="shadowEvidence"
    )

    @model_validator(mode="after")
    def require_case_for_pairable_evidence(self) -> R7EAssessmentRequest:
        if (
            self.case_id is None
            and (self.command is not None or self.shadow_evidence is not None)
        ):
            raise ValueError(
                "caseId is required when command or Shadow evidence is supplied"
            )
        return self


@dataclass(frozen=True, slots=True)
class R7EScenario:
    summary: R7EScenarioSummary
    vendor_profile: BeckhoffTwinCatVendorProfile
    runtime_evidence: BeckhoffRuntimeEvidence | None
    witness_profile: BeckhoffShadowWitnessProfile
    controller_profile: DeploymentControllerProfile | None
    authority: ReadOnlyAuthorityEvidence | None
    capture_authorization: BeckhoffShadowCaptureAuthorization | None
    command: M5DiscreteCommand | None
    shadow_evidence: BeckhoffShadowRunEvidence | None
    readiness_audit: BeckhoffShadowRunReadinessAudit
    run_spec: dict[str, Any]


__all__ = [
    "R7E_DEFAULT_SCENARIO_ID",
    "R7E_DEFAULT_CASE_ID",
    "R7E_DOMAIN_PACK_ID",
    "R7E_EVALUATOR_ID",
    "R7E_RUNNER_ID",
    "R7E_SCENARIO_IDS",
    "BeckhoffShadowAxisSample",
    "BeckhoffShadowCaptureAuthorization",
    "BeckhoffShadowCaptureReceipt",
    "BeckhoffShadowRunEvidence",
    "BeckhoffShadowRunReadinessAudit",
    "BeckhoffShadowWitnessFrame",
    "BeckhoffShadowWitnessNode",
    "BeckhoffShadowWitnessProfile",
    "R7EAssessmentRequest",
    "R7EExamplePayload",
    "R7EManifest",
    "R7EScenarioSummary",
]
