from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel, EvaluationCase
from .models import canonical_hash
from .r7c_models import OpcUaTransportEvidence

R7D_DOMAIN_PACK_ID = "control.domain-pack@4"
R7D_EVALUATOR_ID = "control-beckhoff-vendor-readiness-evaluator@1"
R7D_RUNNER_ID = "control-beckhoff-evidence-import@1"
R7D_DEFAULT_SCENARIO_ID = "beckhoff-twincat-runtime-open"
R7D_SCENARIO_IDS = (R7D_DEFAULT_SCENARIO_ID,)

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_AXES = ("X", "Y", "Z", "B", "C")
_REQUIRED_PACKAGES = ("TwinCAT.Standard.XAR", "TF6100.OpcUaServer.XAR")


def _aware_timestamp(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


def _absolute_uri(value: str, *, field_name: str) -> str:
    if urlparse(value).scheme not in {"urn", "http", "https"}:
        raise ValueError(f"{field_name} must be an absolute URI")
    return value


class BeckhoffNodeBinding(AxiomModel):
    namespace_uri: str = Field(alias="namespaceUri", min_length=1)
    identifier: str = Field(min_length=1)
    expected_data_type: Literal["Double"] = Field(alias="expectedDataType")
    required_access_level: Literal[1] = Field(alias="requiredAccessLevel")
    required_user_access_level: Literal[1] = Field(alias="requiredUserAccessLevel")

    @field_validator("namespace_uri")
    @classmethod
    def require_absolute_namespace(cls, value: str) -> str:
        return _absolute_uri(value, field_name="namespaceUri")


class BeckhoffAxisSignal(AxiomModel):
    axis_id: Literal["X", "Y", "Z", "B", "C"] = Field(alias="axisId")
    canonical_signal_id: str = Field(alias="canonicalSignalId", min_length=1)
    quantity: Literal["axis-position"]
    unit: Literal["mm", "rad"]
    node_binding: BeckhoffNodeBinding | None = Field(
        default=None, alias="nodeBinding"
    )

    @model_validator(mode="after")
    def verify_axis_unit(self) -> BeckhoffAxisSignal:
        expected = "mm" if self.axis_id in {"X", "Y", "Z"} else "rad"
        if self.unit != expected:
            raise ValueError(f"axis {self.axis_id} must use {expected}")
        return self


class BeckhoffLicenseBinding(AxiomModel):
    namespace_uri: str = Field(alias="namespaceUri", min_length=1)
    result_identifier: str = Field(alias="resultIdentifier", min_length=1)
    expiration_identifier: str | None = Field(
        default=None, alias="expirationIdentifier", min_length=1
    )
    result_data_type: Literal["Int32"] = Field(alias="resultDataType")
    full_result_codes: tuple[Literal[0, 255], ...] = Field(
        alias="fullResultCodes", min_length=2, max_length=2
    )
    trial_result_codes: tuple[Literal[254], ...] = Field(
        alias="trialResultCodes", min_length=1, max_length=1
    )

    @model_validator(mode="after")
    def verify_license_binding(self) -> BeckhoffLicenseBinding:
        _absolute_uri(self.namespace_uri, field_name="namespaceUri")
        if self.full_result_codes != (0, 255) or self.trial_result_codes != (254,):
            raise ValueError("license result code mapping must use the frozen Beckhoff values")
        return self


class BeckhoffPermissionProbe(AxiomModel):
    purpose: Literal["non-actuating-readonly-permission-canary"]
    deployment_owner_attested_non_actuating: Literal[True] = Field(
        alias="deploymentOwnerAttestedNonActuating"
    )
    node_binding: BeckhoffNodeBinding = Field(alias="nodeBinding")


class BeckhoffServerIdentityBinding(AxiomModel):
    endpoint_url: str = Field(alias="endpointUrl", min_length=1)
    server_application_uri: str = Field(alias="serverApplicationUri", min_length=1)
    server_certificate_sha256: str = Field(
        alias="serverCertificateSha256", pattern=_HASH_PATTERN
    )
    product_uri: str = Field(alias="productUri", min_length=1)
    manufacturer_name: str = Field(alias="manufacturerName", min_length=1)
    product_name: str = Field(alias="productName", min_length=1)
    software_version: str = Field(alias="softwareVersion", min_length=1)
    build_number: str = Field(alias="buildNumber", min_length=1)

    @model_validator(mode="after")
    def verify_identity_uris(self) -> BeckhoffServerIdentityBinding:
        endpoint = urlparse(self.endpoint_url)
        if endpoint.scheme != "opc.tcp" or not endpoint.hostname or endpoint.port is None:
            raise ValueError("endpointUrl must be an absolute opc.tcp URL with a port")
        _absolute_uri(self.server_application_uri, field_name="serverApplicationUri")
        _absolute_uri(self.product_uri, field_name="productUri")
        if "beckhoff" not in self.manufacturer_name.casefold():
            raise ValueError("manufacturerName must identify Beckhoff")
        product = self.product_name.casefold()
        if "twincat" not in product or "opc ua" not in product:
            raise ValueError("productName must identify the TwinCAT OPC UA Server")
        return self


class BeckhoffTwinCatVendorProfile(AxiomModel):
    schema_id: Literal["axiom.control.beckhoff-twincat-profile@1"] = Field(
        alias="schemaId"
    )
    profile_id: str = Field(alias="profileId", pattern=r"^.+@[0-9]+$")
    vendor_id: Literal["beckhoff"] = Field(alias="vendorId")
    vendor_name: Literal["Beckhoff Automation"] = Field(alias="vendorName")
    controller_family: Literal["TwinCAT 3"] = Field(alias="controllerFamily")
    minimum_twincat_build: Literal[4026] = Field(alias="minimumTwinCatBuild")
    opcua_server_product: Literal["TF6100 OPC UA Server"] = Field(
        alias="opcUaServerProduct"
    )
    required_license_id: Literal["TF6100"] = Field(alias="requiredLicenseId")
    accepted_runtime_license_states: tuple[Literal["Full", "Trial"], ...] = Field(
        alias="acceptedRuntimeLicenseStates", min_length=2, max_length=2
    )
    deployment_required_license_state: Literal["Full"] = Field(
        alias="deploymentRequiredLicenseState"
    )
    required_packages: tuple[
        Literal["TwinCAT.Standard.XAR", "TF6100.OpcUaServer.XAR"], ...
    ] = Field(alias="requiredPackages", min_length=2, max_length=2)
    optional_engineering_package: Literal["TF6100.OpcUaServer.XAE"] = Field(
        alias="optionalEngineeringPackage"
    )
    supported_platforms: tuple[Literal["Windows"], ...] = Field(
        alias="supportedPlatforms", min_length=1, max_length=1
    )
    protocol: Literal["opc-ua"]
    default_endpoint_url: Literal["opc.tcp://localhost:4840"] = Field(
        alias="defaultEndpointUrl"
    )
    message_security_mode: Literal["SignAndEncrypt"] = Field(
        alias="messageSecurityMode"
    )
    identity_type: Literal["username"] = Field(alias="identityType")
    access_mode: Literal["read-subscribe-only"] = Field(alias="accessMode")
    binding_status: Literal["Open", "Bound"] = Field(alias="bindingStatus")
    server_identity: BeckhoffServerIdentityBinding | None = Field(
        default=None, alias="serverIdentity"
    )
    license_binding: BeckhoffLicenseBinding | None = Field(
        default=None, alias="licenseBinding"
    )
    permission_probe: BeckhoffPermissionProbe | None = Field(
        default=None, alias="permissionProbe"
    )
    channels: tuple[BeckhoffAxisSignal, ...] = Field(min_length=5, max_length=5)
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_profile(self) -> BeckhoffTwinCatVendorProfile:
        if self.accepted_runtime_license_states != ("Full", "Trial"):
            raise ValueError("acceptedRuntimeLicenseStates must be Full then Trial")
        if self.required_packages != _REQUIRED_PACKAGES:
            raise ValueError("requiredPackages must use the frozen TwinCAT/TF6100 order")
        axes = tuple(channel.axis_id for channel in self.channels)
        if axes != _AXES:
            raise ValueError("channels must use the frozen X/Y/Z/B/C order")
        canonical_ids = tuple(channel.canonical_signal_id for channel in self.channels)
        if len(set(canonical_ids)) != len(canonical_ids):
            raise ValueError("channels must have unique canonicalSignalId values")
        bindings = tuple(channel.node_binding for channel in self.channels)
        if self.binding_status == "Open":
            if (
                self.server_identity is not None
                or self.license_binding is not None
                or self.permission_probe is not None
                or any(binding is not None for binding in bindings)
            ):
                raise ValueError("Open profile cannot contain deployment identity or node bindings")
        elif (
            self.server_identity is None
            or self.license_binding is None
            or self.permission_probe is None
            or any(binding is None for binding in bindings)
        ):
            raise ValueError(
                "Bound profile requires server, license, permission probe and axis bindings"
            )
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("BeckhoffTwinCatVendorProfile contentHash must match content")
        return self


class BeckhoffPackageReceipt(AxiomModel):
    package_id: Literal["TwinCAT.Standard.XAR", "TF6100.OpcUaServer.XAR"] = Field(
        alias="packageId"
    )
    version: str = Field(min_length=1)
    installed: Literal[True]
    receipt_sha256: str = Field(alias="receiptSha256", pattern=_HASH_PATTERN)


class BeckhoffServerBinaryReceipt(AxiomModel):
    relative_path: str = Field(alias="relativePath", min_length=1)
    product_name: str = Field(alias="productName", min_length=1)
    company_name: str = Field(alias="companyName", min_length=1)
    file_version: str = Field(alias="fileVersion", min_length=1)
    sha256: str = Field(pattern=_HASH_PATTERN)


class BeckhoffInstallationProbe(AxiomModel):
    status: Literal["Open", "Passed", "Blocked"]
    reason_code: str | None = Field(default=None, alias="reasonCode")
    tcpkg_available: bool = Field(alias="tcpkgAvailable")
    tcpkg_sha256: str | None = Field(
        default=None, alias="tcpkgSha256", pattern=_HASH_PATTERN
    )
    twincat_build: int | None = Field(default=None, alias="twinCatBuild", ge=1)
    packages: tuple[BeckhoffPackageReceipt, ...] = ()
    server_binary: BeckhoffServerBinaryReceipt | None = Field(
        default=None, alias="serverBinary"
    )

    @model_validator(mode="after")
    def verify_probe(self) -> BeckhoffInstallationProbe:
        if self.status == "Passed":
            package_ids = tuple(package.package_id for package in self.packages)
            if (
                not self.tcpkg_available
                or self.tcpkg_sha256 is None
                or self.twincat_build is None
                or self.twincat_build < 4026
                or package_ids != _REQUIRED_PACKAGES
                or self.server_binary is None
            ):
                raise ValueError("Passed installation probe is incomplete")
        if self.status != "Passed" and self.reason_code is None:
            raise ValueError("non-Passed installation probe requires reasonCode")
        return self


class BeckhoffLicenseProbe(AxiomModel):
    license_id: Literal["TF6100"] = Field(alias="licenseId")
    state: Literal["Full", "Trial", "Missing", "Unknown"]
    source: str = Field(min_length=1)
    result_code: int | None = Field(default=None, alias="resultCode")
    result_node_id: str | None = Field(default=None, alias="resultNodeId", min_length=1)
    expiration_text: str | None = Field(
        default=None, alias="expirationText", min_length=1
    )
    receipt_sha256: str | None = Field(
        default=None, alias="receiptSha256", pattern=_HASH_PATTERN
    )

    @model_validator(mode="after")
    def require_receipt_for_active_license(self) -> BeckhoffLicenseProbe:
        if self.state in {"Full", "Trial"} and self.receipt_sha256 is None:
            raise ValueError("active TF6100 license requires receiptSha256")
        if self.state == "Full" and self.result_code not in {0, 255}:
            raise ValueError("Full TF6100 license requires Beckhoff result code 0 or 255")
        if self.state == "Trial" and self.result_code != 254:
            raise ValueError("Trial TF6100 license requires Beckhoff result code 254")
        return self


class BeckhoffServerIdentityEvidence(BeckhoffServerIdentityBinding):
    build_date: str = Field(alias="buildDate", min_length=1)

    @field_validator("build_date")
    @classmethod
    def require_aware_build_date(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="buildDate")


class BeckhoffChannelAccessEvidence(AxiomModel):
    axis_id: Literal["X", "Y", "Z", "B", "C"] = Field(alias="axisId")
    canonical_signal_id: str = Field(alias="canonicalSignalId", min_length=1)
    namespace_uri: str = Field(alias="namespaceUri", min_length=1)
    identifier: str = Field(min_length=1)
    data_type: Literal["Double"] = Field(alias="dataType")
    access_level: int = Field(alias="accessLevel", ge=0, le=255)
    user_access_level: int = Field(alias="userAccessLevel", ge=0, le=255)

    @field_validator("namespace_uri")
    @classmethod
    def require_absolute_namespace(cls, value: str) -> str:
        return _absolute_uri(value, field_name="namespaceUri")


class BeckhoffWriteRejectionReceipt(AxiomModel):
    verifier_id: Literal[
        "axiom.control.beckhoff-independent-write-rejection-verifier@1"
    ] = Field(alias="verifierId")
    status: Literal["NotRun", "Rejected", "Accepted"]
    operation_count: Literal[0, 1] = Field(alias="operationCount")
    probe_namespace_uri: str | None = Field(
        default=None, alias="probeNamespaceUri", min_length=1
    )
    probe_identifier: str | None = Field(
        default=None, alias="probeIdentifier", min_length=1
    )
    value_hash_before: str | None = Field(
        default=None, alias="valueHashBefore", pattern=_HASH_PATTERN
    )
    value_hash_after: str | None = Field(
        default=None, alias="valueHashAfter", pattern=_HASH_PATTERN
    )
    status_code: str | None = Field(default=None, alias="statusCode")
    server_value_unchanged: bool | None = Field(
        default=None, alias="serverValueUnchanged"
    )
    receipt_sha256: str | None = Field(
        default=None, alias="receiptSha256", pattern=_HASH_PATTERN
    )

    @model_validator(mode="after")
    def verify_write_receipt(self) -> BeckhoffWriteRejectionReceipt:
        if self.status == "NotRun":
            if self.operation_count != 0 or any(
                value is not None
                for value in (
                    self.status_code,
                    self.server_value_unchanged,
                    self.receipt_sha256,
                    self.probe_namespace_uri,
                    self.probe_identifier,
                    self.value_hash_before,
                    self.value_hash_after,
                )
            ):
                raise ValueError("NotRun write receipt cannot contain operation evidence")
        elif self.operation_count != 1 or any(
            value is None
            for value in (
                self.receipt_sha256,
                self.probe_namespace_uri,
                self.probe_identifier,
                self.value_hash_before,
                self.value_hash_after,
            )
        ):
            raise ValueError("write verifier result requires one operation and receiptSha256")
        elif self.status == "Rejected" and (
            self.status_code not in {"BadNotWritable", "BadUserAccessDenied"}
            or self.server_value_unchanged is not True
            or self.value_hash_before != self.value_hash_after
        ):
            raise ValueError("Rejected write must be denied and leave the value unchanged")
        if self.status != "NotRun" and self.receipt_sha256 != canonical_hash(
            self, exclude={"receipt_sha256"}
        ):
            raise ValueError("write rejection receiptSha256 must match content")
        return self


class BeckhoffRuntimeEvidence(AxiomModel):
    schema_id: Literal["axiom.control.beckhoff-runtime-evidence@1"] = Field(
        alias="schemaId"
    )
    evidence_id: str = Field(alias="evidenceId", pattern=r"^.+@[0-9]+$")
    profile_content_hash: str = Field(
        alias="profileContentHash", pattern=_HASH_PATTERN
    )
    profile_file_sha256: str = Field(alias="profileFileSha256", pattern=_HASH_PATTERN)
    verifier_id: Literal["axiom.control.beckhoff-twincat-read-verifier@1"] = Field(
        alias="verifierId"
    )
    verifier_version: Literal["0.2.0"] = Field(alias="verifierVersion")
    verifier_binary_sha256: str = Field(
        alias="verifierBinarySha256", pattern=_HASH_PATTERN
    )
    platform: Literal["Windows"]
    source_kind: Literal["vendor-runtime", "contract-fixture"] = Field(
        alias="sourceKind"
    )
    captured_at: str = Field(alias="capturedAt", min_length=1)
    installation: BeckhoffInstallationProbe
    license: BeckhoffLicenseProbe
    server_identity: BeckhoffServerIdentityEvidence | None = Field(
        default=None, alias="serverIdentity"
    )
    channel_access: tuple[BeckhoffChannelAccessEvidence, ...] | None = Field(
        default=None, alias="channelAccess"
    )
    write_rejection: BeckhoffWriteRejectionReceipt = Field(alias="writeRejection")
    transport_evidence_content_hash: str | None = Field(
        default=None, alias="transportEvidenceContentHash", pattern=_HASH_PATTERN
    )
    declared_real: Literal[False] = Field(alias="declaredReal")
    counts_toward_reality: Literal[False] = Field(alias="countsTowardReality")
    reality_validation_status: Literal["Open"] = Field(
        alias="realityValidationStatus"
    )
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(
        alias="processSafetyStatus"
    )
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @field_validator("captured_at")
    @classmethod
    def require_aware_capture_time(cls, value: str) -> str:
        return _aware_timestamp(value, field_name="capturedAt")

    @model_validator(mode="after")
    def verify_runtime_evidence(self) -> BeckhoffRuntimeEvidence:
        if self.channel_access is not None:
            axes = tuple(channel.axis_id for channel in self.channel_access)
            if axes != _AXES:
                raise ValueError("channelAccess must use the frozen X/Y/Z/B/C order")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("BeckhoffRuntimeEvidence contentHash must match content")
        return self


class R7DReadinessCheck(AxiomModel):
    check_id: str = Field(alias="checkId", min_length=1)
    title: str = Field(min_length=1)
    status: Literal["Passed", "Open", "Blocked"]
    reason_code: str | None = Field(default=None, alias="reasonCode")
    details: dict[str, Any] = Field(default_factory=dict)


class BeckhoffVendorReadinessAudit(AxiomModel):
    artifact_type: Literal["axiom.control.beckhoff-vendor-readiness"] = Field(
        alias="artifactType"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    audit_id: Literal["control.r7d.beckhoff-vendor-readiness-audit@1"] = Field(
        alias="auditId"
    )
    profile_content_hash: str = Field(alias="profileContentHash", pattern=_HASH_PATTERN)
    runtime_evidence_content_hash: str | None = Field(
        default=None, alias="runtimeEvidenceContentHash", pattern=_HASH_PATTERN
    )
    transport_evidence_content_hash: str | None = Field(
        default=None, alias="transportEvidenceContentHash", pattern=_HASH_PATTERN
    )
    checks: tuple[R7DReadinessCheck, ...] = Field(min_length=9, max_length=9)
    readiness_outcome: Literal["Open", "Blocked"] = Field(alias="readinessOutcome")
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    vendor_profile_status: Literal["Passed"] = Field(alias="vendorProfileStatus")
    vendor_runtime_status: Literal["Open", "Passed", "Blocked"] = Field(
        alias="vendorRuntimeStatus"
    )
    deployment_shadow_status: Literal["Open"] = Field(alias="deploymentShadowStatus")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(
        alias="processSafetyStatus"
    )
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_audit(self) -> BeckhoffVendorReadinessAudit:
        expected_ids = (
            "r7d.target",
            "r7d.profile",
            "r7d.installation",
            "r7d.license",
            "r7d.server-identity",
            "r7d.node-mapping",
            "r7d.readonly-enforcement",
            "r7d.transport",
            "r7d.reality-gate",
        )
        if tuple(check.check_id for check in self.checks) != expected_ids:
            raise ValueError("readiness checks must use the frozen R7-D order")
        has_blocked = any(check.status == "Blocked" for check in self.checks)
        if has_blocked != (self.readiness_outcome == "Blocked"):
            raise ValueError("readinessOutcome must reflect blocked checks")
        runtime_checks = self.checks[2:8]
        expected_runtime = (
            "Blocked"
            if any(check.status == "Blocked" for check in runtime_checks)
            else "Passed"
            if all(check.status == "Passed" for check in runtime_checks)
            else "Open"
        )
        if self.vendor_runtime_status != expected_runtime:
            raise ValueError("vendorRuntimeStatus must reflect runtime checks")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("BeckhoffVendorReadinessAudit contentHash must match content")
        return self


class R7DEvaluationRequest(AxiomModel):
    artifact: BeckhoffVendorReadinessAudit
    profile: BeckhoffTwinCatVendorProfile
    runtime_evidence: BeckhoffRuntimeEvidence | None = Field(
        default=None, alias="runtimeEvidence"
    )
    transport_evidence: OpcUaTransportEvidence | None = Field(
        default=None, alias="transportEvidence"
    )
    case: EvaluationCase

    @model_validator(mode="after")
    def bind_evidence(self) -> R7DEvaluationRequest:
        if self.artifact.profile_content_hash != self.profile.content_hash:
            raise ValueError("audit profileContentHash mismatch")
        runtime_hash = (
            self.runtime_evidence.content_hash if self.runtime_evidence is not None else None
        )
        transport_hash = (
            self.transport_evidence.content_hash
            if self.transport_evidence is not None
            else None
        )
        if self.artifact.runtime_evidence_content_hash != runtime_hash:
            raise ValueError("audit runtimeEvidenceContentHash mismatch")
        if self.artifact.transport_evidence_content_hash != transport_hash:
            raise ValueError("audit transportEvidenceContentHash mismatch")
        return self


class R7DManifest(AxiomModel):
    manifest_id: Literal["control.r7d-manifest@1"] = Field(alias="manifestId")
    domain_pack_id: Literal["control.domain-pack@4"] = Field(alias="domainPackId")
    evaluator_version: Literal[
        "control-beckhoff-vendor-readiness-evaluator@1"
    ] = Field(alias="evaluatorVersion")
    runner_id: Literal["control-beckhoff-evidence-import@1"] = Field(alias="runnerId")
    vendor_profile_id: Literal[
        "axiom.control.beckhoff-twincat-default-profile@1"
    ] = Field(alias="vendorProfileId")
    verifier_id: Literal["axiom.control.beckhoff-twincat-read-verifier@1"] = Field(
        alias="verifierId"
    )
    verifier_version: Literal["0.2.0"] = Field(alias="verifierVersion")
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
    default_scenario_id: str = Field(alias="defaultScenarioId")
    scenario_ids: tuple[str, ...] = Field(alias="scenarioIds")
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    vendor_profile_status: Literal["Passed"] = Field(alias="vendorProfileStatus")
    vendor_runtime_status: Literal["Open"] = Field(alias="vendorRuntimeStatus")
    deployment_shadow_status: Literal["Open"] = Field(alias="deploymentShadowStatus")
    reality_validation_status: Literal["Open"] = Field(
        alias="realityValidationStatus"
    )
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(
        alias="processSafetyStatus"
    )


class R7DScenarioSummary(AxiomModel):
    scenario_id: str = Field(alias="scenarioId")
    title: str
    description: str
    expected_outcome: Literal["Inconclusive"] = Field(alias="expectedOutcome")
    expected_readiness_outcome: Literal["Open"] = Field(
        alias="expectedReadinessOutcome"
    )
    counts_toward_reality: Literal[False] = Field(alias="countsTowardReality")


class R7DExamplePayload(AxiomModel):
    manifest: R7DManifest
    scenario: R7DScenarioSummary
    profile: BeckhoffTwinCatVendorProfile
    readiness_audit: BeckhoffVendorReadinessAudit = Field(alias="readinessAudit")
    runtime_evidence: BeckhoffRuntimeEvidence | None = Field(
        default=None, alias="runtimeEvidence"
    )
    transport_evidence: OpcUaTransportEvidence | None = Field(
        default=None, alias="transportEvidence"
    )
    run_spec: dict[str, Any] = Field(alias="runSpec")


class R7DAssessmentRequest(AxiomModel):
    profile: BeckhoffTwinCatVendorProfile | None = None
    runtime_evidence: BeckhoffRuntimeEvidence | None = Field(
        default=None, alias="runtimeEvidence"
    )
    transport_evidence: OpcUaTransportEvidence | None = Field(
        default=None, alias="transportEvidence"
    )


@dataclass(frozen=True, slots=True)
class R7DScenario:
    summary: R7DScenarioSummary
    profile: BeckhoffTwinCatVendorProfile
    readiness_audit: BeckhoffVendorReadinessAudit
    runtime_evidence: BeckhoffRuntimeEvidence | None
    transport_evidence: OpcUaTransportEvidence | None
    run_spec: dict[str, Any]


__all__ = [
    "BeckhoffRuntimeEvidence",
    "BeckhoffTwinCatVendorProfile",
    "BeckhoffVendorReadinessAudit",
    "R7DAssessmentRequest",
    "R7DExamplePayload",
    "R7DManifest",
    "R7DScenarioSummary",
    "R7D_DEFAULT_SCENARIO_ID",
    "R7D_DOMAIN_PACK_ID",
    "R7D_EVALUATOR_ID",
    "R7D_RUNNER_ID",
    "R7D_SCENARIO_IDS",
]
