from __future__ import annotations

import hashlib
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

from axiom.control import (
    BeckhoffRuntimeEvidence,
    BeckhoffShadowRunEvidence,
    BeckhoffTwinCatVendorProfile,
    OpcUaTransportEvidence,
    assess_r7c_opcua_transport,
)

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "opcua-shadow"


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only conformance")
@pytest.mark.skipif(shutil.which("dotnet") is None, reason=".NET SDK is unavailable")
def test_dotnet_conformance_evidence_crosses_the_python_boundary(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "transport-evidence.json"
    witness_path = tmp_path / "witness-evidence.json"
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
    assert witness.receipt.read_operation_count == 5
    assert witness.receipt.write_operation_count == 0
    assert witness.receipt.method_call_operation_count == 0
    assert witness.counts_toward_reality is False
    assert witness.reality_validation_status == "Open"


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


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only preflight")
@pytest.mark.skipif(shutil.which("dotnet") is None, reason=".NET SDK is unavailable")
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
