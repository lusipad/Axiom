from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from axiom.physical.models import PhysicalResponseTrace
from axiom.physical.scenarios import load_r4_scenario
from axiom.physical.simulation import physical_model_content_hash


def _read_json(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_r4_source_and_package_fixture_manifests_are_identical() -> None:
    package_root = files("axiom.physical.fixtures")
    source_root = Path(__file__).parents[1] / "fixtures" / "physical_r4"

    package_manifest = _read_json(package_root.joinpath("manifest.json"))
    source_manifest = _read_json(source_root / "manifest.json")

    assert package_manifest == source_manifest
    assert package_manifest["platform"] == "windows"
    assert package_manifest["realityValidationStatus"] == "Open"
    assert package_manifest["scenarioOutcomes"] == {
        "in-domain-synthetic-sil": "Passed",
        "model-mismatch-detected": "Failed",
        "time-alignment-mismatch": "Failed",
        "calibration-validation-leakage": "Failed",
        "insufficient-axis-excitation": "Passed",
        "missing-coordinate-context": "Inconclusive",
    }


def test_r4_frozen_response_and_content_identities_match_runtime_scenario() -> None:
    package_root = files("axiom.physical.fixtures")
    source_root = Path(__file__).parents[1] / "fixtures" / "physical_r4"
    package_payload = _read_json(package_root.joinpath("captures/in-domain-synthetic-sil.response.json"))
    source_payload = _read_json(source_root / "captures" / "in-domain-synthetic-sil.response.json")
    response = PhysicalResponseTrace.model_validate(package_payload)
    scenario = load_r4_scenario()
    goldens = _read_json(package_root.joinpath("manifest.json"))["artifactGoldens"]

    assert package_payload == source_payload
    assert response == scenario.validationArtifact
    assert physical_model_content_hash(scenario.physicalModel) == goldens["physicalModelContentHash"]
    assert scenario.validationAnalysis.calibration.content_hash == goldens["calibrationContentHash"]
    assert response.content_hash == goldens["responseContentHash"]
    assert scenario.validationAnalysis.content_hash == goldens["validationAnalysisContentHash"]
