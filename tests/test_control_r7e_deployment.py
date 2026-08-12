from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from axiom.cli import main
from axiom.control import (
    BeckhoffWitnessDeploymentReport,
    BeckhoffWitnessDeploymentNodeBinding,
    BeckhoffWitnessDeploymentRequest,
    assess_beckhoff_witness_deployment,
    build_default_beckhoff_witness_deployment_request,
    load_beckhoff_witness_plc_template,
    read_beckhoff_witness_plc_template,
)
from axiom.control.models import canonical_hash
from axiom.control.r7d_models import (
    BeckhoffChannelAccessEvidence,
    BeckhoffInstallationProbe,
    BeckhoffLicenseProbe,
    BeckhoffRuntimeEvidence,
    BeckhoffServerIdentityEvidence,
    BeckhoffTwinCatVendorProfile,
    BeckhoffWriteRejectionReceipt,
)
from axiom.five_axis import M5DiscreteCommand
from axiom.web import create_app


CANONICAL_SIGNALS = (
    "command.content-hash",
    "command.sample-index",
    "machine.axis.X.position",
    "machine.axis.Y.position",
    "machine.axis.Z.position",
    "machine.axis.B.position",
    "machine.axis.C.position",
)
ROOT = Path(__file__).resolve().parents[1]


def _nodes() -> tuple[BeckhoffWitnessDeploymentNodeBinding, ...]:
    identifiers = (
        "MAIN.fbAxiomShadow.sWitnessCommandContentHash",
        "MAIN.fbAxiomShadow.nWitnessSampleIndex",
        "MAIN.fbAxiomShadow.fWitnessAxisX",
        "MAIN.fbAxiomShadow.fWitnessAxisY",
        "MAIN.fbAxiomShadow.fWitnessAxisZ",
        "MAIN.fbAxiomShadow.fWitnessAxisB",
        "MAIN.fbAxiomShadow.fWitnessAxisC",
    )
    return tuple(
        BeckhoffWitnessDeploymentNodeBinding(
            canonicalSignalId=signal,
            namespaceUri="urn:beckhoff-controller:PLC1",
            identifier=identifier,
        )
        for signal, identifier in zip(CANONICAL_SIGNALS, identifiers, strict=True)
    )


def _complete_request() -> BeckhoffWitnessDeploymentRequest:
    vendor = BeckhoffTwinCatVendorProfile.model_construct(
        content_hash="1" * 64,
        binding_status="Bound",
    )
    runtime = BeckhoffRuntimeEvidence.model_construct(
        content_hash="2" * 64,
        profile_content_hash=vendor.content_hash,
        source_kind="vendor-runtime",
        installation=BeckhoffInstallationProbe.model_construct(status="Passed"),
        license=BeckhoffLicenseProbe.model_construct(state="Full"),
        server_identity=BeckhoffServerIdentityEvidence.model_construct(),
        channel_access=(BeckhoffChannelAccessEvidence.model_construct(),),
        write_rejection=BeckhoffWriteRejectionReceipt.model_construct(
            status="Rejected"
        ),
        transport_evidence_content_hash="3" * 64,
    )
    command = M5DiscreteCommand.model_construct(content_id="4" * 64)
    return BeckhoffWitnessDeploymentRequest.model_construct(
        schema_id="axiom.control.beckhoff-shadow-witness-deployment-request@1",
        schema_version=1,
        assessment_id="axiom.control.beckhoff-witness.test@1",
        case_id="site.part-family-17@1",
        profile_id="site.beckhoff-shadow-witness@1",
        maximum_timestamp_uncertainty_ms=20.0,
        vendor_profile=vendor,
        runtime_evidence=runtime,
        command=command,
        nodes=_nodes(),
    )


def test_twin_cat_template_is_read_only_and_publishes_sample_index_last() -> None:
    source = read_beckhoff_witness_plc_template()
    root = ElementTree.fromstring(source)
    declaration = root.findtext(".//Declaration") or ""
    implementation = root.findtext(".//Implementation/ST") or ""

    assert root.tag == "TcPlcObject"
    assert declaration.count("{attribute 'OPC.UA.DA' := '1'}") == 7
    assert declaration.count("{attribute 'OPC.UA.DA.Access' := '1'}") == 7
    assert "nWitnessSampleIndex : UDINT := 16#FFFFFFFF;" in declaration
    assert "METHOD" not in declaration
    assert "MC_" not in implementation
    assert "nWitnessSampleIndex := nSampleIndex;" in implementation
    assert implementation.index("fWitnessAxisC := fAxisC;") < implementation.index(
        "nWitnessSampleIndex := nSampleIndex;"
    )
    adapter_source = (
        ROOT
        / "adapters"
        / "opcua-shadow"
        / "src"
        / "Axiom.OpcUaShadow.Adapter"
        / "BeckhoffShadowWitnessClient.cs"
    ).read_text(encoding="utf-8")
    assert "frames.Count == 0 && notifiedIndex != 0" in adapter_source

    template = load_beckhoff_witness_plc_template()
    assert template.platform == "Windows"
    assert template.symbol_count == 7
    assert template.device_write_allowed is False
    assert template.method_call_allowed is False
    assert template.twin_cat_compile_status == "NotAssessed"
    assert len(template.source_sha256) == 64


def test_default_deployment_request_stays_open_without_site_bindings() -> None:
    request = build_default_beckhoff_witness_deployment_request()
    first = assess_beckhoff_witness_deployment(request)
    second = assess_beckhoff_witness_deployment(request)

    assert first.profile_binding_status == "Open"
    assert first.runtime_precondition_status == "Open"
    assert first.capture_preparation_status == "Open"
    assert first.witness_profile is None
    assert first.assessment_request is None
    assert first.deployment_shadow_status == "Open"
    assert first.reality_validation_status == "Open"
    assert first.device_safety_status == "NotAssessed"
    assert first.process_safety_status == "NotAssessed"
    assert first.content_hash == second.content_hash


def test_deployment_request_requires_empty_or_all_seven_nodes_in_frozen_order() -> None:
    payload = build_default_beckhoff_witness_deployment_request().model_dump(
        mode="json", by_alias=True
    )
    payload["nodes"] = [
        {
            "canonicalSignalId": CANONICAL_SIGNALS[0],
            "namespaceUri": "urn:beckhoff-controller:PLC1",
            "identifier": "MAIN.commandHash",
        }
    ]
    with pytest.raises(ValidationError, match="empty or contain all seven"):
        BeckhoffWitnessDeploymentRequest.model_validate(payload)

    payload["nodes"] = [
        node.model_dump(mode="json", by_alias=True) for node in reversed(_nodes())
    ]
    with pytest.raises(ValidationError, match="frozen canonical signal order"):
        BeckhoffWitnessDeploymentRequest.model_validate(payload)

    duplicate_nodes = [
        node.model_dump(mode="json", by_alias=True) for node in _nodes()
    ]
    duplicate_nodes[-1]["namespaceUri"] = duplicate_nodes[0]["namespaceUri"]
    duplicate_nodes[-1]["identifier"] = duplicate_nodes[0]["identifier"]
    payload["nodes"] = duplicate_nodes
    with pytest.raises(ValidationError, match="must be unique"):
        BeckhoffWitnessDeploymentRequest.model_validate(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_deployment_request_rejects_non_finite_timestamp_uncertainty(
    value: float,
) -> None:
    payload = build_default_beckhoff_witness_deployment_request().model_dump(
        mode="json", by_alias=True
    )
    payload["maximumTimestampUncertaintyMs"] = value

    with pytest.raises(ValidationError):
        BeckhoffWitnessDeploymentRequest.model_validate(payload)


def test_complete_static_binding_emits_bound_profile_but_keeps_shadow_open() -> None:
    report = assess_beckhoff_witness_deployment(_complete_request())

    assert report.profile_binding_status == "Bound"
    assert report.runtime_precondition_status == "Passed"
    assert report.capture_preparation_status == "Passed"
    assert report.witness_profile is not None
    assert report.witness_profile.binding_status == "Bound"
    assert tuple(
        node.canonical_signal_id for node in report.witness_profile.nodes
    ) == CANONICAL_SIGNALS
    assert report.assessment_request is not None
    assert report.assessment_request.controller_profile is None
    assert report.assessment_request.authority is None
    assert report.assessment_request.capture_authorization is None
    assert report.deployment_shadow_status == "Open"
    assert report.reality_validation_status == "Open"


def test_runtime_identity_mismatch_blocks_profile_generation() -> None:
    request = _complete_request()
    request.runtime_evidence.profile_content_hash = "f" * 64

    report = assess_beckhoff_witness_deployment(request)

    assert report.runtime_precondition_status == "Blocked"
    assert report.profile_binding_status == "Blocked"
    assert report.capture_preparation_status == "Blocked"
    assert report.witness_profile is None
    assert any(
        check.reason_code == "RuntimeEvidenceProfileMismatch"
        for check in report.checks
    )


def test_deployment_report_rejects_a_resealed_status_upgrade() -> None:
    report = assess_beckhoff_witness_deployment(
        build_default_beckhoff_witness_deployment_request()
    )
    payload = report.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={"content_hash"}
    )
    payload["profileBindingStatus"] = "Bound"
    payload["capturePreparationStatus"] = "Passed"
    payload["contentHash"] = canonical_hash(payload)

    with pytest.raises(ValidationError, match="aggregate statuses"):
        BeckhoffWitnessDeploymentReport.model_validate(payload)


def test_cli_and_http_return_the_same_open_deployment_report(tmp_path, capsys) -> None:
    request = build_default_beckhoff_witness_deployment_request()
    request_path = tmp_path / "deployment.json"
    request_path.write_text(
        request.model_dump_json(indent=2, by_alias=True), encoding="utf-8"
    )

    assert main(["beckhoff-witness-deployment", str(request_path)]) == 1
    cli_report = json.loads(capsys.readouterr().out)

    client = TestClient(create_app(serve_frontend=False))
    response = client.post(
        "/api/v1/control/r7e/deployment/assess",
        json=request.model_dump(mode="json", by_alias=True),
    )

    assert response.status_code == 200
    assert response.json() == cli_report
    template_response = client.get("/api/v1/control/r7e/deployment/template")
    assert template_response.status_code == 200
    assert "FB_AxiomShadowWitness" in template_response.text
    assert "attachment" in template_response.headers["content-disposition"]
