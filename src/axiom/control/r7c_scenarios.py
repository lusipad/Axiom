from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from typing import Any

from ..models import AxiomModel, RunSpec
from .models import canonical_hash
from .r7c_models import (
    R7CAssessmentRequest,
    R7CExamplePayload,
    R7CManifest,
    R7CReadinessCheck,
    R7CScenario,
    R7CScenarioSummary,
    R7C_DEFAULT_SCENARIO_ID,
    R7C_DOMAIN_PACK_ID,
    R7C_EVALUATOR_ID,
    R7C_RUNNER_ID,
    R7C_SCENARIO_IDS,
    OpcUaTransportEvidence,
    OpcUaTransportReadinessAudit,
)


def _sealed[ModelT: AxiomModel](
    model_type: type[ModelT], payload: dict[str, Any]
) -> ModelT:
    return model_type.model_validate({**payload, "contentHash": canonical_hash(payload)})


def build_r7c_manifest() -> R7CManifest:
    return R7CManifest(
        manifestId="control.r7c-manifest@1",
        domainPackId=R7C_DOMAIN_PACK_ID,
        evaluatorVersion=R7C_EVALUATOR_ID,
        runnerId=R7C_RUNNER_ID,
        adapterId="axiom.control.opcua-shadow-read-adapter@1",
        adapterVersion="0.1.0",
        protocolStack="OPCFoundation.NetStandard.Opc.Ua.Client@1.5.378.156",
        supportedPlatforms=("Windows",),
        defaultScenarioId=R7C_DEFAULT_SCENARIO_ID,
        scenarioIds=R7C_SCENARIO_IDS,
        permissionCeiling="Shadow",
        deviceWriteAllowed=False,
        adapterContractStatus="Passed",
        networkConformanceStatus="Passed",
        vendorAdapterStatus="Open",
        realityValidationStatus="Open",
    )


def assess_r7c_opcua_transport(
    transport_evidence: OpcUaTransportEvidence | None,
) -> OpcUaTransportReadinessAudit:
    checks: list[R7CReadinessCheck] = [
        R7CReadinessCheck(
            checkId="r7c.contract",
            title="Windows read-only OPC UA Adapter contract",
            status="Passed",
            details={
                "adapterId": "axiom.control.opcua-shadow-read-adapter@1",
                "accessMode": "read-subscribe-only",
                "deviceWriteAllowed": False,
            },
        )
    ]
    if transport_evidence is None:
        checks.extend(
            (
                R7CReadinessCheck(
                    checkId="r7c.transport-evidence",
                    title="External OPC UA transport evidence",
                    status="Open",
                    reasonCode="OpcUaTransportEvidenceMissing",
                ),
                R7CReadinessCheck(
                    checkId="r7c.secure-channel",
                    title="Pinned certificate and encrypted channel",
                    status="Open",
                    reasonCode="SecureChannelEvidenceMissing",
                ),
                R7CReadinessCheck(
                    checkId="r7c.subscription-integrity",
                    title="Five-axis subscription integrity",
                    status="Open",
                    reasonCode="SubscriptionEvidenceMissing",
                ),
                R7CReadinessCheck(
                    checkId="r7c.zero-write",
                    title="Zero write and method-call receipt",
                    status="Open",
                    reasonCode="ZeroWriteReceiptMissing",
                ),
            )
        )
    else:
        checks.extend(
            (
                R7CReadinessCheck(
                    checkId="r7c.transport-evidence",
                    title="External OPC UA transport evidence",
                    status="Passed",
                    details={
                        "contentHash": transport_evidence.content_hash,
                        "declaredReal": False,
                        "countsTowardReality": False,
                    },
                ),
                R7CReadinessCheck(
                    checkId="r7c.secure-channel",
                    title="Pinned certificate and encrypted channel",
                    status="Passed",
                    details={
                        "endpointUrl": transport_evidence.endpoint.endpoint_url,
                        "securityPolicyUri": (
                            transport_evidence.endpoint.security_policy_uri
                        ),
                        "messageSecurityMode": (
                            transport_evidence.endpoint.message_security_mode
                        ),
                        "anonymous": transport_evidence.endpoint.anonymous,
                    },
                ),
                R7CReadinessCheck(
                    checkId="r7c.subscription-integrity",
                    title="Five-axis subscription integrity",
                    status="Passed",
                    details={
                        "monitoredItemCount": (
                            transport_evidence.subscription.monitored_item_count
                        ),
                        "receivedFrameCount": (
                            transport_evidence.receipt.received_frame_count
                        ),
                        "receivedSampleCount": (
                            transport_evidence.receipt.received_sample_count
                        ),
                        "droppedNotificationCount": (
                            transport_evidence.receipt.dropped_notification_count
                        ),
                    },
                ),
                R7CReadinessCheck(
                    checkId="r7c.zero-write",
                    title="Zero write and method-call receipt",
                    status="Passed",
                    details={
                        "writeOperationCount": (
                            transport_evidence.receipt.write_operation_count
                        ),
                        "methodCallOperationCount": (
                            transport_evidence.receipt.method_call_operation_count
                        ),
                        "subscribeOperationCount": (
                            transport_evidence.receipt.subscribe_operation_count
                        ),
                    },
                ),
            )
        )
    checks.extend(
        (
            R7CReadinessCheck(
                checkId="r7c.vendor-adapter",
                title="Selected controller vendor Adapter",
                status="Open",
                reasonCode="VendorAdapterUnselected",
                details={"virtualAdapterIsNotVendorAdapter": True},
            ),
            R7CReadinessCheck(
                checkId="r7c.reality-gate",
                title="Case-scoped real deployment validation",
                status="Open",
                reasonCode="RealDeploymentValidationOpen",
                details={
                    "requiresSelectedController": True,
                    "countsTowardReality": False,
                },
            ),
        )
    )
    payload: dict[str, Any] = {
        "artifactType": "axiom.control.opcua-transport-readiness",
        "schemaVersion": 1,
        "auditId": "control.r7c.opcua-transport-readiness-audit@1",
        "checks": checks,
        "readinessOutcome": "Open",
        "permissionCeiling": "Shadow",
        "deviceWriteAllowed": False,
        "adapterContractStatus": "Passed",
        "virtualTransportStatus": (
            "Passed" if transport_evidence is not None else "Open"
        ),
        "vendorAdapterStatus": "Open",
        "deploymentShadowStatus": "Open",
        "controlledTrialStatus": "Open",
        "closedLoopStatus": "Open",
        "standardsComplianceStatus": "NotAssessed",
        "realityEvidenceLevel": "None",
    }
    if transport_evidence is not None:
        payload["transportEvidenceContentHash"] = transport_evidence.content_hash
    return _sealed(OpcUaTransportReadinessAudit, payload)


def _run_spec(
    audit: OpcUaTransportReadinessAudit,
    transport_evidence: OpcUaTransportEvidence | None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "artifact": audit.model_dump(mode="json", by_alias=True, exclude_none=True),
        "case": {
            "caseId": "control.r7c.opcua-transport-readiness.case@1",
            "requiredMetrics": [
                "control.opcua-adapter-contract-ready@1",
                "control.opcua-real-deployment@1",
            ],
            "optionalMetrics": [
                "control.opcua-virtual-transport@1",
                "control.opcua-secure-channel@1",
                "control.opcua-subscription-integrity@1",
                "control.opcua-zero-write@1",
                "control.opcua-vendor-adapter@1",
            ],
        },
    }
    if transport_evidence is not None:
        request["transportEvidence"] = transport_evidence.model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    return {
        "subjectId": "axiom.control.opcua-transport-readiness@1",
        "subjectVersion": "1",
        "domainPackId": R7C_DOMAIN_PACK_ID,
        "runnerId": R7C_RUNNER_ID,
        "evaluatorVersion": R7C_EVALUATOR_ID,
        "request": request,
    }


@lru_cache(maxsize=1)
def _scenario() -> R7CScenario:
    audit = assess_r7c_opcua_transport(None)
    summary = R7CScenarioSummary(
        scenarioId=R7C_DEFAULT_SCENARIO_ID,
        title="Windows OPC UA transport evidence (open)",
        description=(
            "The Adapter implementation and localhost conformance test exist, but no "
            "capture evidence has been imported into this Run."
        ),
        expectedOutcome="Inconclusive",
        expectedReadinessOutcome="Open",
        countsTowardReality=False,
    )
    return R7CScenario(
        summary=summary,
        readiness_audit=audit,
        transport_evidence=None,
        run_spec=_run_spec(audit, None),
    )


def list_r7c_scenarios() -> tuple[R7CScenarioSummary, ...]:
    return (_scenario().summary,)


def load_r7c_scenario(
    scenario_id: str = R7C_DEFAULT_SCENARIO_ID,
) -> R7CScenario:
    if scenario_id != R7C_DEFAULT_SCENARIO_ID:
        raise KeyError(
            f"unknown R7-C scenario '{scenario_id}'; expected: {R7C_DEFAULT_SCENARIO_ID}"
        )
    return _scenario()


def _payload(
    summary: R7CScenarioSummary,
    transport_evidence: OpcUaTransportEvidence | None,
) -> R7CExamplePayload:
    audit = assess_r7c_opcua_transport(transport_evidence)
    run_spec = _run_spec(audit, transport_evidence)
    RunSpec.model_validate(run_spec)
    return R7CExamplePayload(
        manifest=build_r7c_manifest(),
        scenario=summary,
        readinessAudit=audit,
        transportEvidence=transport_evidence,
        runSpec=run_spec,
    )


def r7c_example_payload(
    scenario_id: str = R7C_DEFAULT_SCENARIO_ID,
) -> R7CExamplePayload:
    scenario = load_r7c_scenario(scenario_id)
    return _payload(scenario.summary, scenario.transport_evidence)


def assess_r7c_payload(request: R7CAssessmentRequest) -> R7CExamplePayload:
    summary = R7CScenarioSummary(
        scenarioId="external-opcua-transport-assessment",
        title="External Windows OPC UA transport evidence assessment",
        description=(
            "The transport evidence is validated without selecting a controller vendor, "
            "granting device authority, or closing the reality gate."
        ),
        expectedOutcome="Inconclusive",
        expectedReadinessOutcome="Open",
        countsTowardReality=False,
    )
    return _payload(summary, request.transport_evidence)


def r7c_example_run_spec(
    scenario_id: str = R7C_DEFAULT_SCENARIO_ID,
) -> dict[str, Any]:
    return deepcopy(load_r7c_scenario(scenario_id).run_spec)


def validate_r7c_example_run_spec(
    scenario_id: str = R7C_DEFAULT_SCENARIO_ID,
) -> RunSpec:
    return RunSpec.model_validate(r7c_example_run_spec(scenario_id))


__all__ = [
    "assess_r7c_opcua_transport",
    "assess_r7c_payload",
    "build_r7c_manifest",
    "list_r7c_scenarios",
    "load_r7c_scenario",
    "r7c_example_payload",
    "r7c_example_run_spec",
    "validate_r7c_example_run_spec",
]
