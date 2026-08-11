from __future__ import annotations

import copy
import math

import pytest
from pydantic import ValidationError

import axiom.five_axis.f2_collision as f2_collision
from axiom.evaluator import _content_hash
from axiom.five_axis.f1_models import M2CandidateTaskGeometry
from axiom.five_axis.f2_kinematics import build_canonical_head_table_bc_profile
from axiom.five_axis.f2_models import M3CandidateAxisPath, MachineProfile


_HASH_A = "a" * 64


def _lineage(statement_id: str, index: int, text: str) -> dict:
    return {
        "statementId": statement_id,
        "statementIndex": index,
        "line": index + 1,
        "column": 1,
        "sourceText": text,
        "sourcePath": "fixture.cl",
    }


def _provenance(stage: str, source_id: str) -> dict:
    return {"sourceStage": stage, "sourceId": source_id, "method": "fixture"}


def _path_progress(segment_id: str, *, progress_id: str) -> dict:
    return {
        "progressId": progress_id,
        "schemaVersion": 1,
        "progressParameter": "sigma",
        "unit": "dimensionless",
        "mappings": [
            {
                "mappingId": f"{progress_id}.map.1",
                "sourceSegmentId": segment_id,
                "sourceLocalStart": 0.0,
                "sourceLocalEnd": 1.0,
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "degenerateKind": "none",
                "provenance": _provenance("M2", segment_id),
            }
        ],
    }


def _regularity_certificate(segment_id: str, node_id: str, *, certificate_id: str) -> dict:
    derivatives = [{"order": 0, "components": [0.0] * 5}, {"order": 1, "components": [1.0] * 5}]
    return {
        "certificateId": certificate_id,
        "segmentEvidence": [
            {
                "segmentId": segment_id,
                "continuityClass": "C1",
                "derivatives": derivatives,
                "verificationMethod": "analytic",
            }
        ],
        "nodeEvidence": [
            {
                "nodeId": node_id,
                "continuityClass": "C1",
                "leftDerivatives": derivatives,
                "rightDerivatives": derivatives,
                "verificationMethod": "analytic",
            }
        ],
    }


def _m2_payload() -> dict:
    segment_id = "m2.seg.1"
    node_id = "m2.node.1"
    return {
        "artifactType": "five-axis.m2-candidate-task-geometry",
        "schemaVersion": 1,
        "candidateGeometryId": "m2.geom.1",
        "sourceReferencePathId": "m1.path.1",
        "sourceReferencePathContentId": _HASH_A,
        "coordinateContext": {"unit": "mm", "coordinateFrame": "machine.work-envelope@1"},
        "pathProgress": _path_progress(segment_id, progress_id="m2.progress.1"),
        "positionSemantics": "continuous",
        "positionSegments": [
            {
                "segmentId": segment_id,
                "segmentType": "line",
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "lineage": [_lineage("stmt.goto.1", 0, "GOTO/20,0,0")],
                "startPoint": [0.0, 0.0, 0.0],
                "endPoint": [20.0, 0.0, 0.0],
            }
        ],
        "orientationSegments": [],
        "nodeEvents": [{"nodeId": node_id, "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": segment_id}],
        "regularityCertificate": _regularity_certificate(segment_id, node_id, certificate_id="m2.reg.1"),
        "tolerances": [
            {"toleranceId": "tol.position", "target": "position", "tolerance": {"absolute": 0.01, "unit": "mm"}},
            {
                "toleranceId": "tol.clearance",
                "target": "collision-clearance",
                "tolerance": {"absolute": 0.0, "unit": "mm"},
            },
        ],
        "correspondence": {
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
                {"pathRole": "source", "nodeId": node_id, "sigma": 0.0, "segmentId": segment_id},
                {"pathRole": "target", "nodeId": "m1.node.1", "sigma": 0.0, "segmentId": "m1.seg.1"},
            ],
            "allowedSourceIntervals": [{"sourceSegmentId": segment_id, "allowedTargetIntervals": [[0.0, 1.0]]}],
            "selectedNodeMapping": [{"sourceNodeId": node_id, "targetNodeId": "m1.node.1"}],
            "intervals": [
                {
                    "intervalId": "corr.interval.1",
                    "sourceSigmaStart": 0.0,
                    "sourceSigmaEnd": 1.0,
                    "targetSigmaStart": 0.0,
                    "targetSigmaEnd": 1.0,
                    "sourceSegmentId": segment_id,
                    "targetSegmentId": "m1.seg.1",
                    "correspondenceStatus": "matched",
                    "provenance": _provenance("M2", segment_id),
                }
            ],
            "primaryObjectiveLower": 0.0,
            "primaryObjectiveUpper": 0.0,
            "objectiveDomain": "continuous",
            "tieBreakObjective": "earliest-target-sigma",
            "numericTolerance": {"absolute": 1e-6, "unit": "mm"},
            "solverVersion": "solver@1",
            "evidenceLevel": "machine-replayable",
        },
        "provenance": [_provenance("M1", "m1.path.1")],
    }


def _machine_profile_payload() -> dict:
    return {
        "artifactType": "five-axis.machine-profile",
        "schemaVersion": 1,
        "profileId": "five-axis.machine-profile.dual-head.demo@1",
        "profileVersion": 1,
        "topology": "dual-head",
        "axes": [
            {
                "axisId": "axis.x",
                "axisOrder": 0,
                "jointType": "prismatic",
                "axisSymbol": "X",
                "semanticRole": "linear-x",
                "origin": [0.0, 0.0, 0.0],
                "direction": [1.0, 0.0, 0.0],
                "installationSide": "tool",
                "sign": "positive",
                "zeroPosition": 0.0,
                "periodic": False,
                "limits": {"lower": -500.0, "upper": 500.0, "unit": "mm"},
            },
            {
                "axisId": "axis.y",
                "axisOrder": 1,
                "jointType": "prismatic",
                "axisSymbol": "Y",
                "semanticRole": "linear-y",
                "parentAxisId": "axis.x",
                "origin": [0.0, 0.0, 0.0],
                "direction": [0.0, 1.0, 0.0],
                "installationSide": "tool",
                "sign": "positive",
                "zeroPosition": 0.0,
                "periodic": False,
                "limits": {"lower": -400.0, "upper": 400.0, "unit": "mm"},
            },
            {
                "axisId": "axis.z",
                "axisOrder": 2,
                "jointType": "prismatic",
                "axisSymbol": "Z",
                "semanticRole": "linear-z",
                "parentAxisId": "axis.y",
                "origin": [0.0, 0.0, 0.0],
                "direction": [0.0, 0.0, 1.0],
                "installationSide": "tool",
                "sign": "positive",
                "zeroPosition": 0.0,
                "periodic": False,
                "limits": {"lower": -300.0, "upper": 300.0, "unit": "mm"},
            },
            {
                "axisId": "axis.c",
                "axisOrder": 3,
                "jointType": "revolute",
                "axisSymbol": "C",
                "semanticRole": "tool-rotary-primary",
                "parentAxisId": "axis.z",
                "origin": [0.0, 0.0, 100.0],
                "direction": [0.0, 0.0, 1.0],
                "installationSide": "tool",
                "sign": "positive",
                "zeroPosition": 0.0,
                "periodic": True,
                "limits": {"lower": -3.14159, "upper": 3.14159, "unit": "rad"},
            },
            {
                "axisId": "axis.b",
                "axisOrder": 4,
                "jointType": "revolute",
                "axisSymbol": "B",
                "semanticRole": "tool-rotary-secondary",
                "parentAxisId": "axis.c",
                "origin": [0.0, 0.0, 0.0],
                "direction": [0.0, 1.0, 0.0],
                "installationSide": "tool",
                "sign": "positive",
                "zeroPosition": 0.0,
                "periodic": True,
                "limits": {"lower": -6.28318, "upper": 6.28318, "unit": "rad"},
            },
        ],
        "workpieceFrame": {
            "transformId": "frame.workpiece",
            "translation": [0.0, 0.0, 0.0],
            "rotationQuaternion": [0.0, 0.0, 0.0, 1.0],
        },
        "toolMountFrame": {
            "transformId": "frame.tool",
            "translation": [0.0, 0.0, 40.0],
            "rotationQuaternion": [0.0, 0.0, 0.0, 1.0],
        },
    }


def _axis_limit_state() -> list[dict]:
    return [
        {"axisId": "axis.x", "status": "within", "distanceToLower": 100.0, "distanceToUpper": 100.0},
        {"axisId": "axis.y", "status": "within", "distanceToLower": 100.0, "distanceToUpper": 100.0},
        {"axisId": "axis.z", "status": "within", "distanceToLower": 100.0, "distanceToUpper": 100.0},
        {"axisId": "axis.c", "status": "within", "distanceToLower": 1.0, "distanceToUpper": 1.0},
        {"axisId": "axis.b", "status": "within", "distanceToLower": 1.0, "distanceToUpper": 1.0},
    ]


def _ik_solution(solution_id: str, sigma: float, values: list[float]) -> dict:
    return {
        "solutionId": solution_id,
        "sigma": sigma,
        "branchId": "branch.1",
        "jointValues": values,
        "wrapState": [{"axisId": "axis.c", "turns": 0}, {"axisId": "axis.b", "turns": 0}],
        "axisLimitState": _axis_limit_state(),
        "residuals": [
            {"metricId": "five-axis.position-residual.max@1", "value": 1e-6, "unit": "mm"},
            {"metricId": "five-axis.orientation-residual.max@1", "value": 1e-6, "unit": "rad"},
        ],
        "singularity": {"status": "regular", "conditioningMetric": 5.0, "minimumSingularValue": 0.2},
        "withinLimits": True,
    }


def _m3_payload(*, coefficients: list[list[float]], interpolation: str = "linear", end_values: list[float] | None = None) -> dict:
    segment_id = "m3.seg.1"
    node_id = "m3.node.1"
    final_values = end_values or [2.0, 0.0, 0.0, 0.0, 0.0]
    source_geometry = _m2_payload()
    machine_profile = _machine_profile_payload()
    source_content_id = _content_hash(
        M2CandidateTaskGeometry.model_validate(source_geometry).model_dump(
            mode="json", by_alias=True, exclude_none=True
        )
    )
    machine_content_id = _content_hash(
        MachineProfile.model_validate(machine_profile).model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    return {
        "artifactType": "five-axis.m3-candidate-axis-path",
        "schemaVersion": 1,
        "axisPathId": "m3.path.1",
        "sourceCandidateGeometry": source_geometry,
        "sourceCandidateGeometryContentId": source_content_id,
        "machineProfile": machine_profile,
        "machineProfileContentId": machine_content_id,
        "pathProgress": _path_progress(segment_id, progress_id="m3.progress.1"),
        "ikSolutions": [
            _ik_solution("ik.0", 0.0, [0.0, 0.0, 0.0, 0.0, 0.0]),
            _ik_solution("ik.1", 1.0, final_values),
        ],
        "branchGraph": {
            "graphId": "graph.1",
            "rootBranchIds": ["branch.1"],
            "branches": [{"branchId": "branch.1", "sigmaStart": 0.0, "sigmaEnd": 1.0, "solutionIds": ["ik.0", "ik.1"], "status": "active"}],
            "transitions": [],
        },
        "jointSegments": [
            {
                "segmentId": segment_id,
                "branchId": "branch.1",
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "startSolutionId": "ik.0",
                "endSolutionId": "ik.1",
                "continuityClass": "C1",
                "interpolation": interpolation,
                "coefficientBasis": "local-power@1",
                "coefficients": coefficients,
            }
        ],
        "nodeEvents": [{"nodeId": node_id, "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": segment_id}],
        "regularityCertificate": _regularity_certificate(segment_id, node_id, certificate_id="m3.reg.1"),
        "kinematicsCertificate": {
            "certificateId": "kin.cert.1",
            "machineProfileId": "five-axis.machine-profile.dual-head.demo@1",
            "machineProfileContentId": machine_content_id,
            "sourceCandidateGeometryId": "m2.geom.1",
            "sourceCandidateGeometryContentId": source_content_id,
            "branchGraphId": "graph.1",
            "solverId": "five-axis.ik-solver.demo@1",
            "solverVersion": "ik-demo-2026-08-11",
            "evidenceLevel": "Exact",
            "continuousMethod": "five-axis.constant-axis-linear-lift@1",
            "claimScope": "selected-continuous-lift",
            "selectedBranchId": "branch.1",
            "intervalCount": 1,
            "positionResidualUpperBound": 1e-6,
            "orientationResidualUpperBound": 1e-6,
            "axisLimitNormalizedMarginLowerBound": 0.1,
            "minimumSingularValueLowerBound": 0.2,
            "singularityHandling": "regular-only",
            "policyIds": ["five-axis.ik-branch-selection@1"],
            "numericEnvironment": {"python": "3.14", "numpy": "2"},
            "positionTolerance": {"toleranceId": "kin.pos", "target": "position", "tolerance": {"absolute": 1e-5, "unit": "mm"}},
            "orientationTolerance": {
                "toleranceId": "kin.ori",
                "target": "orientation",
                "tolerance": {"absolute": 1e-5, "unit": "rad"},
            },
            "provenance": [_provenance("M2", "m2.geom.1")],
        },
        "provenance": [_provenance("M2", "m2.geom.1")],
    }


def _axis_path(*, rotary: bool = False) -> M3CandidateAxisPath:
    if rotary:
        coefficients = [
            [0.0, 0.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0, 1.0, 0.0],
        ]
        payload = _m3_payload(coefficients=coefficients, interpolation="linear", end_values=[0.0, 0.0, 0.0, 1.0, 0.0])
    else:
        coefficients = [
            [0.0, 0.0, 0.0, 0.0, 0.0],
            [2.0, 0.0, 0.0, 0.0, 0.0],
        ]
        payload = _m3_payload(coefficients=coefficients, interpolation="linear")
    return M3CandidateAxisPath.model_validate(payload)


def _collision_model(*, active_branch_ids: tuple[str, ...] = tuple(), rotary_anchor: bool = False) -> dict:
    moving_anchor = {"anchorType": "axis", "anchorAxisId": "axis.c"} if rotary_anchor else {"anchorType": "axis", "anchorAxisId": "axis.x"}
    model = {
        "modelId": "five-axis.configuration-collision.demo@1",
        "machineProfileId": "five-axis.machine-profile.dual-head.demo@1",
        "machineProfileContentId": _content_hash(
            MachineProfile.model_validate(_machine_profile_payload()).model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
        ),
        "policyId": "five-axis.configuration-collision.explicit-pairs@1",
        "coverageStatus": "complete",
        "coveredPairKinds": ["machine-self", "environment"],
        "minimumClearance": {"absolute": 0.0, "unit": "mm"},
        "solverTolerance": {"absolute": 1e-6, "unit": "mm"},
        "entities": [
            {
                "entityId": "moving-head",
                "entityKind": "machine-component",
                **moving_anchor,
                "localAabb": {"minCorner": [0.0, -0.2, -0.2], "maxCorner": [0.4, 0.2, 0.2]},
            },
            {
                "entityId": "machine-column",
                "entityKind": "machine-component",
                "anchorType": "base",
                "localAabb": {"minCorner": [0.9, -0.2, -0.2], "maxCorner": [1.1, 0.2, 0.2]},
            },
            {
                "entityId": "fixture",
                "entityKind": "environment",
                "anchorType": "base",
                "localAabb": {"minCorner": [4.0, -0.5, -0.5], "maxCorner": [4.5, 0.5, 0.5]},
            },
        ],
        "pairs": [
            {
                "pairId": "self-1",
                "pairKind": "machine-self",
                "leftEntityId": "moving-head",
                "rightEntityId": "machine-column",
                "activeBranchIds": list(active_branch_ids),
            },
            {
                "pairId": "env-1",
                "pairKind": "environment",
                "leftEntityId": "moving-head",
                "rightEntityId": "fixture",
            },
        ],
        "provenance": [_provenance("M2", "m2.geom.1")],
    }
    content_id = f2_collision.hash_configuration_collision_model(
        f2_collision.ConfigurationCollisionModel.model_validate(model)
    )
    return {**model, "contentId": content_id}


def test_q_free_point_reports_safe_clearance_and_bindings() -> None:
    axis_path = _axis_path()
    result = f2_collision.evaluate_configuration_q_free(
        axis_path,
        collision_model=_collision_model(),
        sigma=0.0,
    )

    assert result.status == "safe"
    assert result.collision_free is True
    assert result.minimum_clearance_lower_bound == pytest.approx(0.5)
    assert result.machine_profile_id == axis_path.machine_profile.profile_id
    assert result.machine_profile_content_id == axis_path.machine_profile_content_id
    assert result.segment_id == "m3.seg.1"
    assert result.branch_id == "branch.1"
    assert result.policy_id == "five-axis.configuration-collision.explicit-pairs@1"
    assert result.claim_id is None
    assert result.certificate_kind == "point-check"


def test_path_certificate_is_required_for_positive_configuration_claim() -> None:
    axis_path = _axis_path()

    result = f2_collision.evaluate_configuration_path_collision(
        axis_path,
        collision_model=_collision_model(active_branch_ids=("branch.other",)),
    )

    assert result.query_kind == "path"
    assert result.status == "safe"
    assert result.certificate_kind == "proof"
    assert result.claim_id == "five-axis.configuration-collision-free-claim@1"
    assert result.sigma_start == 0.0
    assert result.sigma_end == 1.0


def test_partial_collision_context_cannot_publish_configuration_claim() -> None:
    axis_path = _axis_path()
    payload = _collision_model(active_branch_ids=("branch.other",))
    payload.pop("contentId")
    payload["coverageStatus"] = "partial"
    payload["contentId"] = f2_collision.hash_configuration_collision_model(
        f2_collision.ConfigurationCollisionModel.model_validate(payload)
    )

    result = f2_collision.evaluate_configuration_path_collision(axis_path, collision_model=payload)

    assert result.status == "safe"
    assert result.claim_id is None


def test_negative_collision_tolerance_is_rejected() -> None:
    payload = _collision_model()
    payload.pop("contentId")
    payload["solverTolerance"]["absolute"] = -0.1

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        f2_collision.ConfigurationCollisionModel.model_validate(payload)


def test_tampered_machine_profile_content_cannot_produce_safe_proof() -> None:
    axis_path = _axis_path()
    changed_frame = axis_path.machine_profile.tool_mount_frame.model_copy(update={"translation": (0.0, 0.0, -99.0)})
    changed_profile = axis_path.machine_profile.model_copy(update={"tool_mount_frame": changed_frame})
    tampered_path = axis_path.model_copy(update={"machine_profile": changed_profile})

    result = f2_collision.evaluate_configuration_path_collision(
        tampered_path,
        collision_model=_collision_model(active_branch_ids=("branch.other",)),
    )

    assert result.status == "unsupported"
    assert result.collision_free is None
    assert result.reason_code == "MachineProfileContentHashMismatch"


def test_workpiece_axis_anchor_composes_base_frame_before_axis_motion() -> None:
    payload = build_canonical_head_table_bc_profile().model_dump(mode="json", by_alias=True)
    payload["profileId"] = "five-axis.machine-profile.head-table.offset-frame@1"
    payload["workpieceFrame"]["translation"] = [10.0, 0.0, 0.0]
    profile = MachineProfile.model_validate(payload)
    entity = f2_collision.CollisionEntity.model_validate(
        {
            "entityId": "workpiece-point",
            "entityKind": "machine-component",
            "anchorType": "axis",
            "anchorAxisId": "C",
            "localAabb": {
                "minCorner": [1.0, 0.0, 0.0],
                "maxCorner": [1.0, 0.0, 0.0],
            },
        }
    )

    box = f2_collision._entity_box_at_q(profile, entity, (0.0, 0.0, 0.0, 0.5 * math.pi, 0.0))

    assert box.min_corner == pytest.approx((10.0, 1.0, 0.0))
    assert box.max_corner == pytest.approx((10.0, 1.0, 0.0))


def test_segment_certificate_refutes_interior_collision_with_safe_endpoints() -> None:
    axis_path = _axis_path()
    result = f2_collision.evaluate_configuration_segment_collision(
        axis_path,
        collision_model=_collision_model(),
        segment_id="m3.seg.1",
    )

    self_pair = next(pair for pair in result.pair_results if pair.pair_id == "self-1")
    assert result.status == "collision"
    assert result.collision_free is False
    assert result.certificate_kind == "counterexample"
    assert self_pair.status == "collision"
    assert self_pair.witness_sigma is not None
    assert 0.0 < self_pair.witness_sigma < 1.0


def test_boundary_contact_counts_as_collision() -> None:
    axis_path = _axis_path()
    result = f2_collision.evaluate_configuration_q_free(
        axis_path,
        collision_model=_collision_model(),
        sigma=0.25,
    )

    assert result.status == "collision"
    assert result.collision_free is False
    assert result.minimum_clearance_lower_bound == pytest.approx(0.0)


def test_rotary_interval_reports_unsupported_instead_of_claiming_proof() -> None:
    axis_path = _axis_path(rotary=True)
    result = f2_collision.evaluate_configuration_segment_collision(
        axis_path,
        collision_model=_collision_model(rotary_anchor=True),
        segment_id="m3.seg.1",
    )

    assert result.status == "unsupported"
    assert result.collision_free is None
    assert result.reason_code == "UnsupportedRotaryIntervalMotion"
    assert any(pair.status == "unsupported" for pair in result.pair_results)


def test_branch_filtered_pairs_are_not_applicable() -> None:
    axis_path = _axis_path()
    result = f2_collision.evaluate_configuration_q_free(
        axis_path,
        collision_model=_collision_model(active_branch_ids=("branch.other",)),
        sigma=0.0,
    )

    self_pair = next(pair for pair in result.pair_results if pair.pair_id == "self-1")
    assert self_pair.status == "not-applicable"
    assert result.status == "safe"


def test_safe_subinterval_certificate_is_deterministic_and_bound() -> None:
    axis_path = _axis_path()
    collision_model = _collision_model()
    first = f2_collision.evaluate_configuration_segment_collision(
        axis_path,
        collision_model=collision_model,
        segment_id="m3.seg.1",
        sigma_start=0.0,
        sigma_end=0.2,
    )
    second = f2_collision.evaluate_configuration_segment_collision(
        axis_path,
        collision_model=copy.deepcopy(collision_model),
        segment_id="m3.seg.1",
        sigma_start=0.0,
        sigma_end=0.2,
    )

    assert first.model_dump(mode="json", by_alias=True) == second.model_dump(mode="json", by_alias=True)
    assert first.status == "safe"
    assert first.claim_id is None
    assert first.branch_id == "branch.1"
    assert first.segment_id == "m3.seg.1"
    assert first.collision_model_content_id == collision_model["contentId"]
    assert first.forbidden_claim_ids == (
        "five-axis.model-collision-free-claim@1",
        "five-axis.device-safe-claim@1",
    )
