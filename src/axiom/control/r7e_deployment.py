from __future__ import annotations

import hashlib
from importlib import resources
from typing import Any, Literal, TypeVar
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from ..five_axis.f3_sampling import M5DiscreteCommand
from ..models import AxiomModel, _require_json_number
from .models import canonical_hash
from .r7d_models import BeckhoffRuntimeEvidence, BeckhoffTwinCatVendorProfile
from .r7d_scenarios import assess_r7d_beckhoff
from .r7e_models import (
    BeckhoffShadowWitnessNode,
    BeckhoffShadowWitnessProfile,
    R7EAssessmentRequest,
)

BECKHOFF_WITNESS_DEPLOYMENT_REQUEST_SCHEMA_ID = (
    "axiom.control.beckhoff-shadow-witness-deployment-request@1"
)
BECKHOFF_WITNESS_DEPLOYMENT_REPORT_SCHEMA_ID = (
    "axiom.control.beckhoff-shadow-witness-deployment-report@1"
)
BECKHOFF_WITNESS_PLC_TEMPLATE_ID = (
    "axiom.control.beckhoff-shadow-witness-plc-template@1"
)
BECKHOFF_WITNESS_PLC_TEMPLATE_FILE = "FB_AxiomShadowWitness.TcPOU"

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_CANONICAL_SIGNALS = (
    "command.content-hash",
    "command.sample-index",
    "machine.axis.X.position",
    "machine.axis.Y.position",
    "machine.axis.Z.position",
    "machine.axis.B.position",
    "machine.axis.C.position",
)
_CHECK_IDS = (
    "r7e.deployment.template",
    "r7e.deployment.vendor-profile",
    "r7e.deployment.vendor-runtime",
    "r7e.deployment.command",
    "r7e.deployment.nodes",
)


class BeckhoffWitnessDeploymentNodeBinding(AxiomModel):
    canonical_signal_id: Literal[
        "command.content-hash",
        "command.sample-index",
        "machine.axis.X.position",
        "machine.axis.Y.position",
        "machine.axis.Z.position",
        "machine.axis.B.position",
        "machine.axis.C.position",
    ] = Field(alias="canonicalSignalId")
    namespace_uri: str = Field(alias="namespaceUri", min_length=1)
    identifier: str = Field(min_length=1)

    @field_validator("namespace_uri")
    @classmethod
    def require_absolute_namespace(cls, value: str) -> str:
        if urlparse(value).scheme not in {"urn", "http", "https"}:
            raise ValueError("namespaceUri must be absolute")
        return value


class BeckhoffWitnessDeploymentRequest(AxiomModel):
    schema_id: Literal[
        "axiom.control.beckhoff-shadow-witness-deployment-request@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    assessment_id: str = Field(alias="assessmentId", pattern=r"^.+@[0-9]+$")
    case_id: str = Field(alias="caseId", min_length=1)
    profile_id: str = Field(alias="profileId", pattern=r"^.+@[0-9]+$")
    maximum_timestamp_uncertainty_ms: float = Field(
        alias="maximumTimestampUncertaintyMs", ge=0.0, allow_inf_nan=False
    )
    vendor_profile: BeckhoffTwinCatVendorProfile | None = Field(
        default=None, alias="vendorProfile"
    )
    runtime_evidence: BeckhoffRuntimeEvidence | None = Field(
        default=None, alias="runtimeEvidence"
    )
    command: M5DiscreteCommand | None = None
    nodes: tuple[BeckhoffWitnessDeploymentNodeBinding, ...] = ()

    @field_validator("maximum_timestamp_uncertainty_ms", mode="before")
    @classmethod
    def reject_non_json_number(cls, value: Any) -> Any:
        return _require_json_number(value)

    @model_validator(mode="after")
    def verify_nodes(self) -> BeckhoffWitnessDeploymentRequest:
        if self.nodes and len(self.nodes) != 7:
            raise ValueError("nodes must be empty or contain all seven witness bindings")
        if self.nodes:
            signals = tuple(node.canonical_signal_id for node in self.nodes)
            if signals != _CANONICAL_SIGNALS:
                raise ValueError("nodes must use the frozen canonical signal order")
            identities = tuple(
                (node.namespace_uri, node.identifier) for node in self.nodes
            )
            if len(set(identities)) != len(identities):
                raise ValueError("witness node bindings must be unique")
        return self


class BeckhoffWitnessPlcTemplate(AxiomModel):
    template_id: Literal[
        "axiom.control.beckhoff-shadow-witness-plc-template@1"
    ] = Field(alias="templateId")
    file_name: Literal["FB_AxiomShadowWitness.TcPOU"] = Field(alias="fileName")
    object_format: Literal["TwinCAT-TcPOU"] = Field(alias="objectFormat")
    platform: Literal["Windows"]
    source_encoding: Literal["UTF-8"] = Field(alias="sourceEncoding")
    line_ending_policy: Literal["LF-normalized"] = Field(alias="lineEndingPolicy")
    source_sha256: str = Field(alias="sourceSha256", pattern=_HASH_PATTERN)
    symbol_count: Literal[7] = Field(alias="symbolCount")
    snapshot_policy: Literal["sample-index-published-last"] = Field(
        alias="snapshotPolicy"
    )
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    method_call_allowed: Literal[False] = Field(alias="methodCallAllowed")
    template_validation_status: Literal["ContractChecked"] = Field(
        alias="templateValidationStatus"
    )
    twin_cat_compile_status: Literal["NotAssessed"] = Field(
        alias="twinCatCompileStatus"
    )
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_content_hash(self) -> BeckhoffWitnessPlcTemplate:
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("BeckhoffWitnessPlcTemplate contentHash must match content")
        return self


class BeckhoffWitnessDeploymentCheck(AxiomModel):
    check_id: str = Field(alias="checkId", min_length=1)
    title: str = Field(min_length=1)
    status: Literal["Passed", "Open", "Blocked"]
    reason_code: str | None = Field(default=None, alias="reasonCode")
    details: dict[str, Any] = Field(default_factory=dict)


class BeckhoffWitnessDeploymentReport(AxiomModel):
    schema_id: Literal[
        "axiom.control.beckhoff-shadow-witness-deployment-report@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    assessment_id: str = Field(alias="assessmentId", pattern=r"^.+@[0-9]+$")
    case_id: str = Field(alias="caseId", min_length=1)
    request_content_hash: str = Field(alias="requestContentHash", pattern=_HASH_PATTERN)
    template: BeckhoffWitnessPlcTemplate
    checks: tuple[BeckhoffWitnessDeploymentCheck, ...] = Field(
        min_length=5, max_length=5
    )
    profile_binding_status: Literal["Open", "Bound", "Blocked"] = Field(
        alias="profileBindingStatus"
    )
    runtime_precondition_status: Literal["Open", "Passed", "Blocked"] = Field(
        alias="runtimePreconditionStatus"
    )
    capture_preparation_status: Literal["Open", "Passed", "Blocked"] = Field(
        alias="capturePreparationStatus"
    )
    witness_profile: BeckhoffShadowWitnessProfile | None = Field(
        default=None, alias="witnessProfile"
    )
    assessment_request: R7EAssessmentRequest | None = Field(
        default=None, alias="assessmentRequest"
    )
    permission_ceiling: Literal["Shadow"] = Field(alias="permissionCeiling")
    device_write_allowed: Literal[False] = Field(alias="deviceWriteAllowed")
    method_call_allowed: Literal[False] = Field(alias="methodCallAllowed")
    capture_authorization_status: Literal["Open"] = Field(
        alias="captureAuthorizationStatus"
    )
    deployment_shadow_status: Literal["Open"] = Field(alias="deploymentShadowStatus")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(alias="processSafetyStatus")
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_report(self) -> BeckhoffWitnessDeploymentReport:
        if tuple(check.check_id for check in self.checks) != _CHECK_IDS:
            raise ValueError("deployment checks must use the frozen order")
        if self.runtime_precondition_status != self.checks[2].status:
            raise ValueError("runtimePreconditionStatus must match its check")
        statuses = tuple(check.status for check in self.checks)
        if "Blocked" in statuses:
            expected_profile, expected_preparation = "Blocked", "Blocked"
        elif all(status == "Passed" for status in statuses):
            expected_profile, expected_preparation = "Bound", "Passed"
        else:
            expected_profile, expected_preparation = "Open", "Open"
        if (
            self.profile_binding_status,
            self.capture_preparation_status,
        ) != (expected_profile, expected_preparation):
            raise ValueError("deployment aggregate statuses must match checks")
        ready = expected_preparation == "Passed"
        if ready != (self.witness_profile is not None):
            raise ValueError("Passed preparation requires a witness profile")
        if ready != (self.assessment_request is not None):
            raise ValueError("Passed preparation requires an R7-E assessment request")
        if ready:
            assert self.assessment_request is not None
            assert self.witness_profile is not None
            if (
                self.assessment_request.case_id != self.case_id
                or self.assessment_request.witness_profile != self.witness_profile
            ):
                raise ValueError("R7-E assessment request must bind this case and profile")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("BeckhoffWitnessDeploymentReport contentHash must match content")
        return self


_SealedModel = TypeVar("_SealedModel", bound=AxiomModel)


def _sealed(model_type: type[_SealedModel], payload: dict[str, Any]) -> _SealedModel:
    normalized = {key: value for key, value in payload.items() if value is not None}
    return model_type.model_validate(
        {**normalized, "contentHash": canonical_hash(normalized)}
    )


def _normalized_template_source() -> str:
    source = (
        resources.files("axiom.control.deployment")
        .joinpath(BECKHOFF_WITNESS_PLC_TEMPLATE_FILE)
        .read_text(encoding="utf-8")
    )
    return source.replace("\r\n", "\n")


def read_beckhoff_witness_plc_template() -> str:
    return _normalized_template_source()


def load_beckhoff_witness_plc_template() -> BeckhoffWitnessPlcTemplate:
    source_hash = hashlib.sha256(
        _normalized_template_source().encode("utf-8")
    ).hexdigest()
    return _sealed(
        BeckhoffWitnessPlcTemplate,
        {
            "templateId": BECKHOFF_WITNESS_PLC_TEMPLATE_ID,
            "fileName": BECKHOFF_WITNESS_PLC_TEMPLATE_FILE,
            "objectFormat": "TwinCAT-TcPOU",
            "platform": "Windows",
            "sourceEncoding": "UTF-8",
            "lineEndingPolicy": "LF-normalized",
            "sourceSha256": source_hash,
            "symbolCount": 7,
            "snapshotPolicy": "sample-index-published-last",
            "deviceWriteAllowed": False,
            "methodCallAllowed": False,
            "templateValidationStatus": "ContractChecked",
            "twinCatCompileStatus": "NotAssessed",
        },
    )


def build_default_beckhoff_witness_deployment_request(
) -> BeckhoffWitnessDeploymentRequest:
    return BeckhoffWitnessDeploymentRequest(
        schemaId=BECKHOFF_WITNESS_DEPLOYMENT_REQUEST_SCHEMA_ID,
        schemaVersion=1,
        assessmentId="axiom.control.beckhoff-shadow-witness-deployment.open@1",
        caseId="control.r7e.beckhoff-shadow-run.case@1",
        profileId="axiom.control.beckhoff-shadow-witness.site@1",
        maximumTimestampUncertaintyMs=20.0,
    )


def _check(
    check_id: str,
    title: str,
    status: Literal["Passed", "Open", "Blocked"],
    reason_code: str | None = None,
    **details: Any,
) -> BeckhoffWitnessDeploymentCheck:
    return BeckhoffWitnessDeploymentCheck(
        checkId=check_id,
        title=title,
        status=status,
        reasonCode=reason_code,
        details=details,
    )


def _runtime_check(
    vendor_profile: BeckhoffTwinCatVendorProfile | None,
    runtime_evidence: BeckhoffRuntimeEvidence | None,
) -> BeckhoffWitnessDeploymentCheck:
    title = "Bound TwinCAT 3 / TF6100 vendor runtime"
    if runtime_evidence is None:
        return _check(
            "r7e.deployment.vendor-runtime",
            title,
            "Open",
            "BeckhoffRuntimeEvidenceMissing",
        )
    if vendor_profile is None:
        return _check(
            "r7e.deployment.vendor-runtime",
            title,
            "Blocked",
            "BeckhoffVendorProfileMissing",
        )
    readiness = assess_r7d_beckhoff(vendor_profile, runtime_evidence, None)
    binding_check_ids = (
        "r7d.installation",
        "r7d.license",
        "r7d.server-identity",
        "r7d.node-mapping",
        "r7d.readonly-enforcement",
    )
    checks_by_id = {check.check_id: check for check in readiness.checks}
    failed_binding = next(
        (
            checks_by_id[check_id]
            for check_id in binding_check_ids
            if checks_by_id[check_id].status != "Passed"
        ),
        None,
    )
    if failed_binding is not None:
        return _check(
            "r7e.deployment.vendor-runtime",
            title,
            "Blocked",
            failed_binding.reason_code or "BeckhoffVendorRuntimeNotDeploymentReady",
            r7dCheckId=failed_binding.check_id,
        )
    if (
        runtime_evidence.license.state != "Full"
        or runtime_evidence.transport_evidence_content_hash is None
    ):
        return _check(
            "r7e.deployment.vendor-runtime",
            title,
            "Blocked",
            "BeckhoffVendorRuntimeNotDeploymentReady",
        )
    return _check(
        "r7e.deployment.vendor-runtime",
        title,
        "Passed",
        runtimeEvidenceContentHash=runtime_evidence.content_hash,
        validatedR7DCheckIds=binding_check_ids,
    )


def _request_content_hash(request: BeckhoffWitnessDeploymentRequest) -> str:
    return canonical_hash(
        {
            "schemaId": request.schema_id,
            "schemaVersion": request.schema_version,
            "assessmentId": request.assessment_id,
            "caseId": request.case_id,
            "profileId": request.profile_id,
            "maximumTimestampUncertaintyMs": (
                request.maximum_timestamp_uncertainty_ms
            ),
            "vendorProfileContentHash": (
                request.vendor_profile.content_hash
                if request.vendor_profile is not None
                else None
            ),
            "runtimeEvidenceContentHash": (
                request.runtime_evidence.content_hash
                if request.runtime_evidence is not None
                else None
            ),
            "commandContentId": (
                request.command.content_id if request.command is not None else None
            ),
            "nodes": [
                node.model_dump(mode="json", by_alias=True) for node in request.nodes
            ],
        }
    )


def _build_witness_profile(
    request: BeckhoffWitnessDeploymentRequest,
) -> BeckhoffShadowWitnessProfile:
    assert request.vendor_profile is not None
    assert request.runtime_evidence is not None
    assert request.command is not None
    roles = (
        ("command-content-hash", None, "String", "sha256"),
        ("sample-index", None, "UInt32", "index"),
        ("axis-position", "X", "Double", "mm"),
        ("axis-position", "Y", "Double", "mm"),
        ("axis-position", "Z", "Double", "mm"),
        ("axis-position", "B", "Double", "rad"),
        ("axis-position", "C", "Double", "rad"),
    )
    nodes = tuple(
        BeckhoffShadowWitnessNode(
            canonicalSignalId=binding.canonical_signal_id,
            role=role,
            axisId=axis,
            namespaceUri=binding.namespace_uri,
            identifier=binding.identifier,
            expectedDataType=data_type,
            unit=unit,
            requiredAccessLevel=1,
            requiredUserAccessLevel=1,
        )
        for binding, (role, axis, data_type, unit) in zip(
            request.nodes, roles, strict=True
        )
    )
    return _sealed(
        BeckhoffShadowWitnessProfile,
        {
            "schemaId": "axiom.control.beckhoff-shadow-witness-profile@1",
            "profileId": request.profile_id,
            "vendorProfileContentHash": request.vendor_profile.content_hash,
            "runtimeEvidenceContentHash": request.runtime_evidence.content_hash,
            "expectedCommandContentHash": request.command.content_id,
            "bindingStatus": "Bound",
            "platform": "Windows",
            "protocol": "opc-ua",
            "capturePolicy": "sample-index-triggered-batch-read",
            "intervalPolicy": "exact-sample-index-no-interpolation",
            "maximumTimestampUncertaintyMs": (
                request.maximum_timestamp_uncertainty_ms
            ),
            "maximumSampleIndexGap": 0,
            "nodes": nodes,
            "permissionCeiling": "Shadow",
            "deviceWriteAllowed": False,
            "methodCallAllowed": False,
        },
    )


def assess_beckhoff_witness_deployment(
    request: BeckhoffWitnessDeploymentRequest,
) -> BeckhoffWitnessDeploymentReport:
    template = load_beckhoff_witness_plc_template()
    vendor_check = (
        _check(
            "r7e.deployment.vendor-profile",
            "Bound Beckhoff TwinCAT vendor profile",
            "Open",
            "BeckhoffVendorProfileMissing",
        )
        if request.vendor_profile is None
        else _check(
            "r7e.deployment.vendor-profile",
            "Bound Beckhoff TwinCAT vendor profile",
            "Passed" if request.vendor_profile.binding_status == "Bound" else "Blocked",
            (
                None
                if request.vendor_profile.binding_status == "Bound"
                else "BeckhoffVendorProfileNotBound"
            ),
            vendorProfileContentHash=request.vendor_profile.content_hash,
        )
    )
    runtime_check = _runtime_check(request.vendor_profile, request.runtime_evidence)
    command_check = (
        _check(
            "r7e.deployment.command",
            "Authoritative M5 command content identity",
            "Open",
            "M5DiscreteCommandMissing",
        )
        if request.command is None
        else _check(
            "r7e.deployment.command",
            "Authoritative M5 command content identity",
            "Passed",
            commandContentId=request.command.content_id,
        )
    )
    node_check = (
        _check(
            "r7e.deployment.nodes",
            "Seven explicit read-only witness node bindings",
            "Open",
            "WitnessNodeBindingsMissing",
        )
        if not request.nodes
        else _check(
            "r7e.deployment.nodes",
            "Seven explicit read-only witness node bindings",
            "Passed",
            nodeCount=len(request.nodes),
        )
    )
    checks = (
        _check(
            "r7e.deployment.template",
            "TwinCAT witness source contract",
            "Passed",
            templateContentHash=template.content_hash,
        ),
        vendor_check,
        runtime_check,
        command_check,
        node_check,
    )
    statuses = tuple(check.status for check in checks)
    if "Blocked" in statuses:
        profile_status: Literal["Open", "Bound", "Blocked"] = "Blocked"
        preparation_status: Literal["Open", "Passed", "Blocked"] = "Blocked"
    elif all(status == "Passed" for status in statuses):
        profile_status = "Bound"
        preparation_status = "Passed"
    else:
        profile_status = "Open"
        preparation_status = "Open"

    witness_profile = None
    assessment_request = None
    if preparation_status == "Passed":
        witness_profile = _build_witness_profile(request)
        assessment_request = R7EAssessmentRequest.model_construct(
            case_id=request.case_id,
            vendor_profile=request.vendor_profile,
            runtime_evidence=request.runtime_evidence,
            witness_profile=witness_profile,
            command=request.command,
        )

    return _sealed(
        BeckhoffWitnessDeploymentReport,
        {
            "schemaId": BECKHOFF_WITNESS_DEPLOYMENT_REPORT_SCHEMA_ID,
            "schemaVersion": 1,
            "assessmentId": request.assessment_id,
            "caseId": request.case_id,
            "requestContentHash": _request_content_hash(request),
            "template": template,
            "checks": checks,
            "profileBindingStatus": profile_status,
            "runtimePreconditionStatus": runtime_check.status,
            "capturePreparationStatus": preparation_status,
            "witnessProfile": witness_profile,
            "assessmentRequest": assessment_request,
            "permissionCeiling": "Shadow",
            "deviceWriteAllowed": False,
            "methodCallAllowed": False,
            "captureAuthorizationStatus": "Open",
            "deploymentShadowStatus": "Open",
            "realityValidationStatus": "Open",
            "controlledTrialStatus": "Open",
            "closedLoopStatus": "Open",
            "deviceSafetyStatus": "NotAssessed",
            "processSafetyStatus": "NotAssessed",
        },
    )


__all__ = [
    "BECKHOFF_WITNESS_DEPLOYMENT_REPORT_SCHEMA_ID",
    "BECKHOFF_WITNESS_DEPLOYMENT_REQUEST_SCHEMA_ID",
    "BECKHOFF_WITNESS_PLC_TEMPLATE_FILE",
    "BECKHOFF_WITNESS_PLC_TEMPLATE_ID",
    "BeckhoffWitnessDeploymentCheck",
    "BeckhoffWitnessDeploymentNodeBinding",
    "BeckhoffWitnessDeploymentReport",
    "BeckhoffWitnessDeploymentRequest",
    "BeckhoffWitnessPlcTemplate",
    "assess_beckhoff_witness_deployment",
    "build_default_beckhoff_witness_deployment_request",
    "load_beckhoff_witness_plc_template",
    "read_beckhoff_witness_plc_template",
]
