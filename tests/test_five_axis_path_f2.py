from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Callable, cast

import pytest

from axiom.five_axis.f1_models import ConstantOrientationSegment, LinePositionSegment, M2CandidateTaskGeometry
from axiom.five_axis.f2_kinematics import (
    build_canonical_head_head_cb_profile,
    build_canonical_head_table_bc_profile,
    build_canonical_table_table_ac_profile,
    forward_kinematics,
)
from axiom.five_axis.f2_models import M3CandidateAxisPath, MachineProfile
from axiom.five_axis.f2_path import lift_m2_path_to_m3_axis_path


def _hash_model(model: Any) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lineage(statement_id: str, index: int, text: str) -> dict[str, object]:
    return {
        "statementId": statement_id,
        "statementIndex": index,
        "line": index + 1,
        "column": 1,
        "sourceText": text,
        "sourcePath": "fixture.cl",
    }


def _position_segment(
    *,
    segment_id: str,
    sigma_start: float,
    sigma_end: float,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> dict[str, object]:
    return {
        "segmentId": segment_id,
        "segmentType": "line",
        "sigmaStart": sigma_start,
        "sigmaEnd": sigma_end,
        "lineage": [_lineage(f"stmt.{segment_id}", 0, f"GOTO/{end[0]},{end[1]},{end[2]}")],
        "startPoint": list(start),
        "endPoint": list(end),
    }


def _orientation_segment(
    *,
    segment_id: str,
    sigma_start: float,
    sigma_end: float,
    axis: tuple[float, float, float],
) -> dict[str, object]:
    return {
        "segmentId": segment_id,
        "segmentType": "constant",
        "sigmaStart": sigma_start,
        "sigmaEnd": sigma_end,
        "lineage": [_lineage(f"stmt.{segment_id}", 0, "TOOLAXIS")],
        "axis": list(axis),
    }


def _path_progress(position_segments: list[dict[str, object]]) -> dict[str, object]:
    return {
        "progressId": "m2.progress.1",
        "schemaVersion": 1,
        "progressParameter": "sigma",
        "unit": "dimensionless",
        "mappings": [
            {
                "mappingId": f"{segment['segmentId']}.map",
                "sourceSegmentId": segment["segmentId"],
                "sourceLocalStart": 0.0,
                "sourceLocalEnd": 1.0,
                "sigmaStart": segment["sigmaStart"],
                "sigmaEnd": segment["sigmaEnd"],
                "degenerateKind": "none",
            }
            for segment in position_segments
        ],
    }


def _correspondence(position_segments: list[dict[str, object]]) -> dict[str, object]:
    return {
        "certificateId": "corr.1",
        "sourceGeometryId": "m2.geom.1",
        "targetReferencePathId": "m1.path.1",
        "policy": {
            "strategyId": "five-axis.correspondence.monotone-minimax@1",
            "allowedSourceInterval": [0.0, 1.0],
            "allowedTargetInterval": [0.0, 1.0],
            "objective": "minimize-maximum-deviation",
            "deterministicTieBreak": "earliest-target-sigma",
            "numericTolerance": {"absolute": 1e-6, "unit": "mm"},
        },
        "canonicalNodes": [
            {"pathRole": "source", "nodeId": "m2.node.start", "sigma": 0.0, "segmentId": position_segments[0]["segmentId"]},
            {"pathRole": "target", "nodeId": "m1.node.start", "sigma": 0.0, "segmentId": "m1.seg.1"},
        ],
        "allowedSourceIntervals": [
            {"sourceSegmentId": segment["segmentId"], "allowedTargetIntervals": [[segment["sigmaStart"], segment["sigmaEnd"]]]}
            for segment in position_segments
        ],
        "selectedNodeMapping": [{"sourceNodeId": "m2.node.start", "targetNodeId": "m1.node.start"}],
        "intervals": [
            {
                "intervalId": f"corr.{index}",
                "sourceSigmaStart": segment["sigmaStart"],
                "sourceSigmaEnd": segment["sigmaEnd"],
                "targetSigmaStart": segment["sigmaStart"],
                "targetSigmaEnd": segment["sigmaEnd"],
                "sourceSegmentId": segment["segmentId"],
                "targetSegmentId": f"m1.seg.{index}",
                "correspondenceStatus": "matched",
            }
            for index, segment in enumerate(position_segments, start=1)
        ],
        "primaryObjectiveLower": 0.0,
        "primaryObjectiveUpper": 0.0,
        "objectiveDomain": "continuous",
        "tieBreakObjective": "earliest-target-sigma",
        "numericTolerance": {"absolute": 1e-6, "unit": "mm"},
        "solverVersion": "solver@1",
        "evidenceLevel": "machine-replayable",
    }


def _candidate_geometry(
    *,
    position_segments: list[dict[str, object]],
    orientation_segments: list[dict[str, object]],
    position_semantics: str = "continuous",
    static_position: tuple[float, float, float] | None = None,
) -> M2CandidateTaskGeometry:
    payload: dict[str, object] = {
        "artifactType": "five-axis.m2-candidate-task-geometry",
        "schemaVersion": 1,
        "candidateGeometryId": "m2.geom.1",
        "sourceReferencePathId": "m1.path.1",
        "sourceReferencePathContentId": "a" * 64,
        "coordinateContext": {"unit": "mm", "coordinateFrame": "machine.work-envelope@1"},
        "pathProgress": _path_progress(position_segments or [{"segmentId": orientation_segments[0]["segmentId"], "sigmaStart": 0.0, "sigmaEnd": 1.0}]),
        "positionSemantics": position_semantics,
        "positionSegments": position_segments,
        "orientationSegments": orientation_segments,
        "nodeEvents": [],
        "tolerances": [
            {"toleranceId": "tol.position", "target": "position", "tolerance": {"absolute": 1e-6, "unit": "mm"}},
            {"toleranceId": "tol.orientation", "target": "orientation", "tolerance": {"absolute": 1e-9, "unit": "rad"}},
        ],
        "correspondence": _correspondence(position_segments or [_position_segment(segment_id="virtual.pos", sigma_start=0.0, sigma_end=1.0, start=static_position or (0.0, 0.0, 0.0), end=static_position or (0.0, 0.0, 0.0))]),
        "provenance": [{"sourceStage": "M1", "sourceId": "m1.path.1", "method": "fixture"}],
    }
    if static_position is not None:
        payload["staticPosition"] = list(static_position)
    return M2CandidateTaskGeometry.model_validate(payload)


def _supported_task() -> M2CandidateTaskGeometry:
    return _candidate_geometry(
        position_segments=[
            _position_segment(
                segment_id="m2.seg.1",
                sigma_start=0.0,
                sigma_end=1.0,
                start=(10.0, -20.0, 40.0),
                end=(30.0, 25.0, 55.0),
            )
        ],
        orientation_segments=[
            _orientation_segment(
                segment_id="m2.orient.1",
                sigma_start=0.0,
                sigma_end=1.0,
                axis=(0.5, 0.5, math.sqrt(0.5)),
            )
        ],
    )


@pytest.mark.parametrize(
    "builder",
    [
        build_canonical_table_table_ac_profile,
        build_canonical_head_table_bc_profile,
        build_canonical_head_head_cb_profile,
    ],
)
def test_lift_supports_all_three_canonical_profiles(
    builder: Callable[[], MachineProfile],
) -> None:
    candidate = _supported_task()
    profile = builder()

    result = lift_m2_path_to_m3_axis_path(candidate, profile)

    assert result.status == "Supported"
    assert result.axis_path is not None
    axis_path = result.axis_path
    start_segment = cast(LinePositionSegment, candidate.position_segments[0])
    end_segment = cast(LinePositionSegment, candidate.position_segments[-1])
    orientation_segment = cast(ConstantOrientationSegment, candidate.orientation_segments[0])
    assert axis_path.machine_profile.profile_id == profile.profile_id
    assert axis_path.kinematics_certificate.evidence_level == "Exact"
    assert axis_path.kinematics_certificate.claim_scope == "selected-continuous-lift"
    assert axis_path.kinematics_certificate.interval_count == len(axis_path.joint_segments)
    assert all(segment.branch_id == axis_path.kinematics_certificate.selected_branch_id for segment in axis_path.joint_segments)

    for segment in axis_path.joint_segments:
        for sigma in (segment.sigma_start, segment.sigma_end):
            joints = dict(zip((axis.axis_id for axis in axis_path.machine_profile.axes), segment.evaluate(sigma), strict=True))
            pose = forward_kinematics(axis_path.machine_profile, joints)
            expected_position = (
                start_segment.start_point
                if math.isclose(sigma, 0.0, abs_tol=1e-12)
                else end_segment.end_point
            )
            assert pose.position == pytest.approx(expected_position, abs=1e-6)
            assert pose.tool_axis == pytest.approx(orientation_segment.axis, abs=1e-9)


def test_wrap_candidates_are_deterministically_selected() -> None:
    candidate = _supported_task()
    profile = build_canonical_head_table_bc_profile()

    first = lift_m2_path_to_m3_axis_path(candidate, profile)
    second = lift_m2_path_to_m3_axis_path(candidate, profile)

    assert first.status == "Supported"
    assert second.status == "Supported"
    assert first.axis_path is not None
    assert second.axis_path is not None
    assert len(first.axis_path.branch_graph.branches) >= 2
    assert first.axis_path.kinematics_certificate.selected_branch_id.endswith(".wrap.c0")
    assert first.axis_path.model_dump(mode="json", by_alias=True) == second.axis_path.model_dump(mode="json", by_alias=True)


def test_multi_segment_path_emits_node_event_and_c0_node_regularity() -> None:
    candidate = _candidate_geometry(
        position_segments=[
            _position_segment(
                segment_id="m2.seg.1",
                sigma_start=0.0,
                sigma_end=0.5,
                start=(0.0, 0.0, 40.0),
                end=(10.0, 0.0, 40.0),
            ),
            _position_segment(
                segment_id="m2.seg.2",
                sigma_start=0.5,
                sigma_end=1.0,
                start=(10.0, 0.0, 40.0),
                end=(10.0, 12.0, 42.0),
            ),
        ],
        orientation_segments=[
            _orientation_segment(segment_id="m2.orient.1", sigma_start=0.0, sigma_end=1.0, axis=(0.4, 0.3, 0.8660254037844386))
        ],
    )
    profile = build_canonical_table_table_ac_profile()

    result = lift_m2_path_to_m3_axis_path(candidate, profile)

    assert result.status == "Supported"
    assert result.axis_path is not None
    assert len(result.axis_path.joint_segments) == 2
    assert len(result.axis_path.node_events) == 1
    assert result.axis_path.node_events[0].event_type == "ordinary-junction"
    assert result.axis_path.regularity_certificate.node_evidence[0].continuity_class == "C0"


def test_axis_limit_counterexample_is_refuted() -> None:
    candidate = _candidate_geometry(
        position_segments=[
            _position_segment(
                segment_id="m2.seg.1",
                sigma_start=0.0,
                sigma_end=1.0,
                start=(0.0, 0.0, 40.0),
                end=(700.0, 0.0, 40.0),
            )
        ],
        orientation_segments=[_orientation_segment(segment_id="m2.orient.1", sigma_start=0.0, sigma_end=1.0, axis=(0.5, 0.5, math.sqrt(0.5)))],
    )

    result = lift_m2_path_to_m3_axis_path(candidate, build_canonical_head_head_cb_profile())

    assert result.status == "Refuted"
    assert result.reason_code == "RefutedNoEndpointIK"


def test_varying_orientation_is_unsupported() -> None:
    candidate = _candidate_geometry(
        position_segments=[
            _position_segment(
                segment_id="m2.seg.1",
                sigma_start=0.0,
                sigma_end=1.0,
                start=(0.0, 0.0, 40.0),
                end=(20.0, 5.0, 40.0),
            )
        ],
        orientation_segments=[
            _orientation_segment(segment_id="m2.orient.1", sigma_start=0.0, sigma_end=0.5, axis=(0.0, 0.0, 1.0)),
            _orientation_segment(segment_id="m2.orient.2", sigma_start=0.5, sigma_end=1.0, axis=(1.0, 0.0, 0.0)),
        ],
    )

    result = lift_m2_path_to_m3_axis_path(candidate, build_canonical_table_table_ac_profile())

    assert result.status == "Unsupported"
    assert result.reason_code == "UnsupportedOrientationSubset"


def test_singular_free_family_is_unsupported() -> None:
    candidate = _candidate_geometry(
        position_segments=[
            _position_segment(
                segment_id="m2.seg.1",
                sigma_start=0.0,
                sigma_end=1.0,
                start=(0.0, 0.0, 40.0),
                end=(10.0, 0.0, 40.0),
            )
        ],
        orientation_segments=[_orientation_segment(segment_id="m2.orient.1", sigma_start=0.0, sigma_end=1.0, axis=(0.0, 0.0, 1.0))],
    )

    result = lift_m2_path_to_m3_axis_path(candidate, build_canonical_head_table_bc_profile())

    assert result.status == "Unsupported"
    assert result.reason_code == "UnsupportedSingularFreeFamily"


def test_supported_result_roundtrips_and_binds_content_ids() -> None:
    candidate = _supported_task()
    profile = build_canonical_head_head_cb_profile()

    result = lift_m2_path_to_m3_axis_path(candidate, profile)

    assert result.status == "Supported"
    assert result.axis_path is not None
    axis_path = result.axis_path
    dumped = axis_path.model_dump(mode="json", by_alias=True)
    roundtrip = M3CandidateAxisPath.model_validate(dumped)

    assert roundtrip.machine_profile_content_id == _hash_model(profile)
    assert roundtrip.source_candidate_geometry_content_id == _hash_model(candidate)
    assert roundtrip.kinematics_certificate.machine_profile_content_id == roundtrip.machine_profile_content_id
    assert roundtrip.kinematics_certificate.source_candidate_geometry_content_id == roundtrip.source_candidate_geometry_content_id
    assert roundtrip.kinematics_certificate.selected_branch_id == roundtrip.joint_segments[0].branch_id
    assert roundtrip.kinematics_certificate.interval_count == len(roundtrip.joint_segments)
