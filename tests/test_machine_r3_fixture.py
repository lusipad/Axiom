from __future__ import annotations

import hashlib
import json
from pathlib import Path

from axiom.machine import load_machine_telemetry_capture
from axiom.machine.scenarios import (
    list_machine_r3_scenarios,
    load_machine_r3_manifest,
    load_machine_r3_scenario,
    machine_r3_example_payload,
)

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "machine_r3"
PACKAGE_FIXTURE_ROOT = Path(__file__).parents[1] / "src" / "axiom" / "machine" / "fixtures"


def test_machine_r3_manifest_and_scenarios_stay_in_sync() -> None:
    manifest = load_machine_r3_manifest()
    listed = list_machine_r3_scenarios()
    manifest_ids = [case["id"] for case in manifest["cases"]]
    listed_ids = [item["scenarioId"] for item in listed]
    assert listed_ids == manifest_ids
    assert {
        "scenarioId",
        "title",
        "description",
        "expectedExecutionStatus",
        "expectedCaseOutcome",
        "lineageMode",
        "deviceLabel",
        "hasClockAlignment",
        "hasCoordinateAlignment",
        "gapCount",
    }.issubset(set(listed[0]))
    assert sorted(path.name for path in FIXTURE_ROOT.glob("*.json") if path.name != "manifest.json") == sorted(
        f"{scenario_id}.json" for scenario_id in manifest_ids
    )


def test_source_and_packaged_machine_fixtures_are_semantically_identical() -> None:
    source_files = sorted(FIXTURE_ROOT.rglob("*.json"))
    assert source_files
    for source in source_files:
        packaged = PACKAGE_FIXTURE_ROOT / source.relative_to(FIXTURE_ROOT)
        assert packaged.is_file()
        assert json.loads(packaged.read_text(encoding="utf-8")) == json.loads(
            source.read_text(encoding="utf-8")
        )


def test_machine_r3_example_payload_keeps_raw_and_derived_fields_separate() -> None:
    payload = machine_r3_example_payload("read-only-paired-pass")
    assert set(payload) == {
        "manifest",
        "scenario",
        "artifact",
        "deviceProfile",
        "clockMapping",
        "coordinateAlignment",
        "lineage",
        "runSpec",
    }
    assert "clockMapping" not in payload["artifact"]
    assert "coordinateAlignment" not in payload["artifact"]
    assert payload["artifact"]["vendorMetadata"]["programName"] == "DEMO_5X_R3"


def test_machine_r3_fixture_scenario_exposes_expected_outcome_metadata() -> None:
    scenario = load_machine_r3_scenario("out-of-order-gap")
    assert scenario.summary["expectedCaseOutcome"] == "Failed"
    assert scenario.summary["expectedExecutionStatus"] == "Succeeded"
    assert scenario.run_spec["request"]["artifact"]["traceId"] == "trace:out-of-order-gap"
    assert scenario.summary["gapCount"] == 1


def test_machine_loader_is_read_only_and_emits_source_file_hash(tmp_path: Path) -> None:
    source = FIXTURE_ROOT / "captures" / "read-only-paired-pass.trace.json"
    copied = tmp_path / source.name
    original_bytes = source.read_bytes()
    copied.write_bytes(original_bytes)
    loaded = load_machine_telemetry_capture(copied)
    assert copied.read_bytes() == original_bytes
    assert loaded.source_file_hash == hashlib.sha256(original_bytes).hexdigest()


def test_paired_lineage_freezes_real_f4_windows_golden_bindings() -> None:
    machine_case = json.loads((FIXTURE_ROOT / "read-only-paired-pass.json").read_text(encoding="utf-8"))
    f4_manifest = json.loads((Path(__file__).parents[1] / "fixtures" / "five_axis_f4" / "manifest.json").read_text(encoding="utf-8"))
    f4_case = next(case for case in f4_manifest["cases"] if case["id"] == "canonical-head-table-solver")
    f4_windows = next(identity for identity in f4_manifest["environmentBoundIdentities"] if identity["label"] == "windows-haswell-single-thread-python-3.12-reference-2026-08-11")
    assert machine_case["lineage"]["baselineRunBundleHash"] == f4_windows["bundleHashes"]["canonical-head-table-solver"]
    assert machine_case["lineage"]["sourceCommandContentHash"] == f4_case["expectedReferenceCommandContentId"]
