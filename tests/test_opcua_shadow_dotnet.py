from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from axiom.control import (
    BeckhoffRuntimeEvidence,
    BeckhoffShadowRunEvidence,
    BeckhoffTwinCatVendorProfile,
    BeckhoffWitnessNodeVerificationEvidence,
    OpcUaTransportEvidence,
    R7EAssessmentRequest,
    assess_r7c_opcua_transport,
)
from tests.test_field_evidence import _complete_test_r7e_request

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "opcua-shadow"


def _pinned_dotnet_sdk_available() -> bool:
    if shutil.which("dotnet") is None:
        return False
    pinned = json.loads((ROOT / "global.json").read_text(encoding="utf-8"))["sdk"][
        "version"
    ]
    completed = subprocess.run(
        ["dotnet", "--list-sdks"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    return completed.returncode == 0 and any(
        line.startswith(f"{pinned} ") for line in completed.stdout.splitlines()
    )


PINNED_DOTNET_SDK_AVAILABLE = _pinned_dotnet_sdk_available()


def _reseal_content_hash(payload: dict[str, object]) -> None:
    payload.pop("contentHash", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    payload["contentHash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _use_integer_lexemes_for_whole_floats(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_use_integer_lexemes_for_whole_floats(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _use_integer_lexemes_for_whole_floats(item)
            for key, item in value.items()
        }
    return value


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only conformance")
@pytest.mark.skipif(
    not PINNED_DOTNET_SDK_AVAILABLE, reason="pinned .NET SDK is unavailable"
)
def test_dotnet_conformance_evidence_crosses_the_python_boundary(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "transport-evidence.json"
    witness_path = tmp_path / "witness-evidence.json"
    node_evidence_path = tmp_path / "witness-node-evidence.json"
    completed = subprocess.run(
        [
            "dotnet",
            "run",
            "--project",
            str(
                ADAPTER
                / "tests"
                / "Axiom.OpcUaShadow.Conformance"
                / "Axiom.OpcUaShadow.Conformance.csproj"
            ),
            "-c",
            "Release",
            "--",
            "--evidence-output",
            str(evidence_path),
            "--witness-evidence-output",
            str(witness_path),
            "--witness-node-evidence-output",
            str(node_evidence_path),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Independent write rejected: True" in completed.stdout
    assert "Untrusted certificate rejected: True" in completed.stdout
    assert "Expired capture authorization rejected: True" in completed.stdout
    assert "Cancelled witness capture stopped: True" in completed.stdout
    assert "Witness timeout enforced: True" in completed.stdout
    evidence = OpcUaTransportEvidence.model_validate_json(
        evidence_path.read_text(encoding="utf-8")
    )
    audit = assess_r7c_opcua_transport(evidence)

    assert audit.virtual_transport_status == "Passed"
    assert audit.vendor_adapter_status == "Open"
    assert audit.deployment_shadow_status == "Open"
    assert audit.reality_evidence_level == "None"
    witness = BeckhoffShadowRunEvidence.model_validate_json(
        witness_path.read_text(encoding="utf-8")
    )

    assert witness.source_kind == "contract-fixture"
    assert witness.declared_real is False
    assert tuple(frame.read_sample_index for frame in witness.frames) == tuple(range(5))
    assert all(
        frame.notified_sample_index == frame.read_sample_index
        for frame in witness.frames
    )
    assert witness.receipt.subscribe_operation_count == 1
    assert witness.receipt.read_operation_count == 16
    assert witness.receipt.write_operation_count == 0
    assert witness.receipt.method_call_operation_count == 0
    assert witness.counts_toward_reality is False
    assert witness.reality_validation_status == "Open"
    node_evidence = BeckhoffWitnessNodeVerificationEvidence.model_validate_json(
        node_evidence_path.read_text(encoding="utf-8")
    )

    assert node_evidence.source_kind == "vendor-runtime"
    assert len(node_evidence.nodes) == 7
    assert node_evidence.nodes[0].browse_name == "sWitnessCommandContentHash"
    assert node_evidence.nodes[1].data_type == "UInt32"
    assert all(node.node_class == "Variable" for node in node_evidence.nodes)
    assert node_evidence.write_operation_count == 0
    assert node_evidence.method_call_operation_count == 0


def test_production_adapter_has_no_write_or_method_call_surface() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ADAPTER / "src").rglob("*.cs")
    )
    conformance = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ADAPTER / "tests").rglob("*.cs")
    )
    permission_verifier = (
        ADAPTER
        / "tools"
        / "Axiom.OpcUaShadow.BeckhoffPermissionVerifier"
        / "Program.cs"
    ).read_text(encoding="utf-8")

    assert "session.WriteAsync(" not in production
    assert "session.CallAsync(" not in production
    assert "session.WriteAsync(" in conformance
    assert permission_verifier.count("session.WriteAsync(") == 1
    assert "session.CallAsync(" not in permission_verifier
    assert "--acknowledge-non-actuating-probe" in permission_verifier


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only assembler")
@pytest.mark.skipif(
    not PINNED_DOTNET_SDK_AVAILABLE, reason="pinned .NET SDK is unavailable"
)
def test_dotnet_assembles_a_python_valid_r7e_assessment_without_network(
    tmp_path: Path,
) -> None:
    request = _complete_test_r7e_request(
        role="calibration",
        start=datetime(2026, 8, 13, 8, tzinfo=timezone.utc),
        shift=0,
    )
    assert request.vendor_profile is not None
    assert request.runtime_evidence is not None
    assert request.witness_profile is not None
    assert request.controller_profile is not None
    assert request.authority is not None
    assert request.capture_authorization is not None
    assert request.command is not None
    assert request.shadow_evidence is not None
    inputs = {
        "vendor-profile": request.vendor_profile,
        "runtime-evidence": request.runtime_evidence,
        "witness-profile": request.witness_profile,
        "controller-profile": request.controller_profile,
        "authority": request.authority,
        "capture-authorization": request.capture_authorization,
        "command": request.command,
        "shadow-evidence": request.shadow_evidence,
    }
    paths: dict[str, Path] = {}
    for name, value in inputs.items():
        path = tmp_path / f"{name}.json"
        path.write_text(
            value.model_dump_json(indent=2, by_alias=True, exclude_none=True),
            encoding="utf-8",
        )
        paths[name] = path
    output_path = tmp_path / "calibration.r7e.json"
    command = [
        "dotnet",
        "run",
        "--project",
        str(
            ADAPTER
            / "src"
            / "Axiom.OpcUaShadow.Adapter"
            / "Axiom.OpcUaShadow.Adapter.csproj"
        ),
        "-c",
        "Release",
        "--",
        "beckhoff-shadow-assessment",
        "--case-id",
        request.case_id,
    ]
    for name, path in paths.items():
        command.extend((f"--{name}", str(path)))
    command.extend(("--output", str(output_path)))

    def run_assembler(
        output: Path,
        *,
        overrides: dict[str, Path] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        invocation = list(command)
        invocation[-1] = str(output)
        for name, path in (overrides or {}).items():
            invocation[invocation.index(f"--{name}") + 1] = str(path)
        return subprocess.run(
            invocation,
            cwd=ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=120,
        )

    completed = run_assembler(output_path)

    assert completed.returncode == 0, completed.stderr
    assembled = R7EAssessmentRequest.model_validate_json(
        output_path.read_text(encoding="utf-8")
    )
    assert assembled == request
    assert json.loads(output_path.read_text(encoding="utf-8"))["caseId"] == (
        "site.test-case@1"
    )

    mismatched = _complete_test_r7e_request(
        role="validation",
        start=datetime(2026, 8, 13, 9, tzinfo=timezone.utc),
        shift=1,
    )
    assert mismatched.command is not None
    mismatched_path = tmp_path / "mismatched-command.json"
    mismatched_path.write_text(
        mismatched.command.model_dump_json(indent=2, by_alias=True),
        encoding="utf-8",
    )
    mismatched_output = tmp_path / "mismatched.r7e.json"
    rejected = run_assembler(
        mismatched_output,
        overrides={"command": mismatched_path},
    )

    assert rejected.returncode == 1
    assert "command" in rejected.stderr.lower()
    assert not mismatched_output.exists()

    original_command_payload = json.loads(
        request.command.model_dump_json(by_alias=True, exclude_none=True)
    )
    integer_float_command = _use_integer_lexemes_for_whole_floats(
        original_command_payload
    )
    assert type(original_command_payload["samples"][0]["q"][0]) is float
    assert type(integer_float_command["samples"][0]["q"][0]) is int
    integer_float_path = tmp_path / "integer-float-command.json"
    integer_float_path.write_text(
        json.dumps(integer_float_command, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    integer_float_output = tmp_path / "integer-float.r7e.json"

    integer_float_result = run_assembler(
        integer_float_output,
        overrides={"command": integer_float_path},
    )

    assert integer_float_result.returncode == 0, integer_float_result.stderr
    assert R7EAssessmentRequest.model_validate_json(
        integer_float_output.read_text(encoding="utf-8")
    ) == request

    invalid_authority = json.loads(
        request.authority.model_dump_json(by_alias=True, exclude_none=True)
    )
    invalid_authority.pop("grantedOperations")
    _reseal_content_hash(invalid_authority)
    invalid_authority_path = tmp_path / "invalid-authority.json"
    invalid_authority_path.write_text(
        json.dumps(invalid_authority, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    authority_evidence = json.loads(
        request.shadow_evidence.model_dump_json(by_alias=True, exclude_none=True)
    )
    authority_evidence["authorityContentHash"] = invalid_authority["contentHash"]
    _reseal_content_hash(authority_evidence)
    authority_evidence_path = tmp_path / "invalid-authority-evidence.json"
    authority_evidence_path.write_text(
        json.dumps(authority_evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    invalid_authority_output = tmp_path / "invalid-authority.r7e.json"

    invalid_authority_result = run_assembler(
        invalid_authority_output,
        overrides={
            "authority": invalid_authority_path,
            "shadow-evidence": authority_evidence_path,
        },
    )

    assert invalid_authority_result.returncode == 1
    assert "authority" in invalid_authority_result.stderr.lower()
    assert not invalid_authority_output.exists()

    invalid_controller = json.loads(
        request.controller_profile.model_dump_json(by_alias=True, exclude_none=True)
    )
    invalid_controller.pop("vendor")
    _reseal_content_hash(invalid_controller)
    invalid_controller_path = tmp_path / "invalid-controller.json"
    invalid_controller_path.write_text(
        json.dumps(invalid_controller, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rebound_authority = json.loads(
        request.authority.model_dump_json(by_alias=True, exclude_none=True)
    )
    rebound_authority["controllerProfileContentHash"] = invalid_controller[
        "contentHash"
    ]
    _reseal_content_hash(rebound_authority)
    rebound_authority_path = tmp_path / "rebound-authority.json"
    rebound_authority_path.write_text(
        json.dumps(rebound_authority, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rebound_authorization = json.loads(
        request.capture_authorization.model_dump_json(
            by_alias=True,
            exclude_none=True,
        )
    )
    rebound_authorization["controllerProfileContentHash"] = invalid_controller[
        "contentHash"
    ]
    _reseal_content_hash(rebound_authorization)
    rebound_authorization_path = tmp_path / "rebound-authorization.json"
    rebound_authorization_path.write_text(
        json.dumps(rebound_authorization, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    controller_evidence = json.loads(
        request.shadow_evidence.model_dump_json(by_alias=True, exclude_none=True)
    )
    controller_evidence["controllerProfileContentHash"] = invalid_controller[
        "contentHash"
    ]
    controller_evidence["authorityContentHash"] = rebound_authority["contentHash"]
    controller_evidence["captureAuthorizationContentHash"] = rebound_authorization[
        "contentHash"
    ]
    _reseal_content_hash(controller_evidence)
    controller_evidence_path = tmp_path / "invalid-controller-evidence.json"
    controller_evidence_path.write_text(
        json.dumps(controller_evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    invalid_controller_output = tmp_path / "invalid-controller.r7e.json"

    invalid_controller_result = run_assembler(
        invalid_controller_output,
        overrides={
            "controller-profile": invalid_controller_path,
            "authority": rebound_authority_path,
            "capture-authorization": rebound_authorization_path,
            "shadow-evidence": controller_evidence_path,
        },
    )

    assert invalid_controller_result.returncode == 1
    assert "controller" in invalid_controller_result.stderr.lower()
    assert not invalid_controller_output.exists()


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only preflight")
@pytest.mark.skipif(
    not PINNED_DOTNET_SDK_AVAILABLE, reason="pinned .NET SDK is unavailable"
)
def test_beckhoff_preflight_emits_hash_closed_open_boundary(tmp_path: Path) -> None:
    profile_path = ROOT / "examples" / "beckhoff-twincat-profile.windows.json"
    evidence_path = tmp_path / "beckhoff-runtime-evidence.json"
    completed = subprocess.run(
        [
            "dotnet",
            "run",
            "--project",
            str(
                ADAPTER
                / "src"
                / "Axiom.OpcUaShadow.Adapter"
                / "Axiom.OpcUaShadow.Adapter.csproj"
            ),
            "-c",
            "Release",
            "--",
            "beckhoff-preflight",
            "--profile",
            str(profile_path),
            "--output",
            str(evidence_path),
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    profile = BeckhoffTwinCatVendorProfile.model_validate_json(
        profile_path.read_text(encoding="utf-8")
    )
    evidence = BeckhoffRuntimeEvidence.model_validate_json(
        evidence_path.read_text(encoding="utf-8")
    )
    verifier_output = (
        ADAPTER
        / "src"
        / "Axiom.OpcUaShadow.Adapter"
        / "bin"
        / "Release"
        / "net8.0"
    )
    verifier_binary = verifier_output / "axiom-opcua-shadow.exe"
    if not verifier_binary.is_file():
        verifier_binary = verifier_output / "axiom-opcua-shadow.dll"

    assert evidence.profile_content_hash == profile.content_hash
    assert evidence.verifier_binary_sha256 == hashlib.sha256(
        verifier_binary.read_bytes()
    ).hexdigest()
    assert evidence.source_kind == "vendor-runtime"
    assert evidence.write_rejection.status == "NotRun"
    assert evidence.write_rejection.operation_count == 0
    assert evidence.counts_toward_reality is False
    assert evidence.reality_validation_status == "Open"
    assert evidence.device_safety_status == "NotAssessed"
    assert evidence.process_safety_status == "NotAssessed"
