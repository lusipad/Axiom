from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from itertools import pairwise
from typing import Any

from ..models import RunSpec
from .models import (
    DeviceProfile,
    LoadedMachineTelemetryCapture,
    MachineRunLineage,
)
from .runtime import (
    MACHINE_OBSERVATION_DOMAIN_PACK_ID,
    MACHINE_OBSERVATION_EVALUATOR_ID,
    MACHINE_TRACE_IMPORT_RUNNER_ID,
    load_machine_telemetry_capture,
)


@dataclass(frozen=True, slots=True)
class MachineR3Scenario:
    summary: dict[str, Any]
    artifact: LoadedMachineTelemetryCapture | dict[str, Any]
    device_profile: DeviceProfile
    clock_mapping: dict[str, Any] | None
    coordinate_alignment: dict[str, Any] | None
    lineage: MachineRunLineage
    run_spec: dict[str, Any]


def _gap_count(artifact_payload: dict[str, Any]) -> int:
    sequence_ids = [frame["sequenceId"] for frame in artifact_payload.get("frames", [])]
    return sum(max(right - left - 1, 0) for left, right in pairwise(sequence_ids))


def _fixture_file(*parts: str):
    return resources.files("axiom.machine.fixtures").joinpath(*parts)


def load_machine_r3_manifest() -> dict[str, Any]:
    return json.loads(_fixture_file("manifest.json").read_text(encoding="utf-8"))


def load_machine_r3_scenario(scenario_id: str) -> MachineR3Scenario:
    payload = json.loads(_fixture_file(f"{scenario_id}.json").read_text(encoding="utf-8"))
    artifact_loader = payload.get("artifactLoader", "validated")
    if artifact_loader == "raw":
        capture: LoadedMachineTelemetryCapture | dict[str, Any] = json.loads(
            _fixture_file(*payload["artifactFile"].split("/")).read_text(encoding="utf-8")
        )
        artifact_payload = capture
    else:
        artifact_file = _fixture_file(*payload["artifactFile"].split("/"))
        with resources.as_file(artifact_file) as capture_path:
            capture = load_machine_telemetry_capture(capture_path)
        artifact_payload = capture.artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    device_profile = DeviceProfile.model_validate(payload["deviceProfile"])
    clock_mapping = payload.get("clockMapping")
    coordinate_alignment = payload.get("coordinateAlignment")
    lineage = MachineRunLineage.model_validate(payload["lineage"])
    summary = {
        **payload["scenario"],
        "lineageMode": lineage.pairing_status,
        "deviceLabel": f"{device_profile.device_id} / {device_profile.controller_family}",
        "hasClockAlignment": clock_mapping is not None,
        "hasCoordinateAlignment": coordinate_alignment is not None,
        "gapCount": _gap_count(artifact_payload),
    }
    request: dict[str, Any] = {
        "artifact": artifact_payload,
        "deviceProfile": device_profile.model_dump(mode="json", by_alias=True, exclude_none=True),
        "lineage": lineage.model_dump(mode="json", by_alias=True, exclude_none=True),
        "case": payload["case"],
    }
    if clock_mapping is not None:
        request["clockMapping"] = clock_mapping
    if coordinate_alignment is not None:
        request["coordinateAlignment"] = coordinate_alignment
    run_spec = RunSpec.model_validate(
        {
            "subjectId": payload["subjectId"],
            "domainPackId": MACHINE_OBSERVATION_DOMAIN_PACK_ID,
            "runnerId": MACHINE_TRACE_IMPORT_RUNNER_ID,
            "evaluatorVersion": MACHINE_OBSERVATION_EVALUATOR_ID,
            "request": request,
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True)
    return MachineR3Scenario(
        summary=summary,
        artifact=capture,
        device_profile=device_profile,
        clock_mapping=clock_mapping,
        coordinate_alignment=coordinate_alignment,
        lineage=lineage,
        run_spec=run_spec,
    )


def list_machine_r3_scenarios() -> list[dict[str, Any]]:
    manifest = load_machine_r3_manifest()
    return [load_machine_r3_scenario(case["id"]).summary for case in manifest["cases"]]


def machine_r3_example_payload(scenario_id: str) -> dict[str, Any]:
    scenario = load_machine_r3_scenario(scenario_id)
    artifact_payload = (
        scenario.artifact.artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(scenario.artifact, LoadedMachineTelemetryCapture)
        else scenario.artifact
    )
    payload: dict[str, Any] = {
        "manifest": load_machine_r3_manifest(),
        "scenario": scenario.summary,
        "artifact": artifact_payload,
        "deviceProfile": scenario.device_profile.model_dump(mode="json", by_alias=True, exclude_none=True),
        "lineage": scenario.lineage.model_dump(mode="json", by_alias=True, exclude_none=True),
        "runSpec": scenario.run_spec,
    }
    if scenario.clock_mapping is not None:
        payload["clockMapping"] = scenario.clock_mapping
    if scenario.coordinate_alignment is not None:
        payload["coordinateAlignment"] = scenario.coordinate_alignment
    return payload


def machine_r3_example_run_spec(scenario_id: str) -> dict[str, Any]:
    return load_machine_r3_scenario(scenario_id).run_spec


__all__ = [
    "MachineR3Scenario",
    "list_machine_r3_scenarios",
    "load_machine_r3_manifest",
    "load_machine_r3_scenario",
    "machine_r3_example_payload",
    "machine_r3_example_run_spec",
]
