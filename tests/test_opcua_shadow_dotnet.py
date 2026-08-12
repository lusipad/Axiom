from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

import pytest

from axiom.control import OpcUaTransportEvidence, assess_r7c_opcua_transport


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters" / "opcua-shadow"


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only conformance")
@pytest.mark.skipif(shutil.which("dotnet") is None, reason=".NET SDK is unavailable")
def test_dotnet_conformance_evidence_crosses_the_python_boundary(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "transport-evidence.json"
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
    evidence = OpcUaTransportEvidence.model_validate_json(
        evidence_path.read_text(encoding="utf-8")
    )
    audit = assess_r7c_opcua_transport(evidence)

    assert audit.virtual_transport_status == "Passed"
    assert audit.vendor_adapter_status == "Open"
    assert audit.deployment_shadow_status == "Open"
    assert audit.reality_evidence_level == "None"


def test_production_adapter_has_no_write_or_method_call_surface() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ADAPTER / "src").rglob("*.cs")
    )
    conformance = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ADAPTER / "tests").rglob("*.cs")
    )

    assert "session.WriteAsync(" not in production
    assert "session.CallAsync(" not in production
    assert "session.WriteAsync(" in conformance
