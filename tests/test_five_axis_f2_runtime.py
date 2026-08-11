from __future__ import annotations

import copy
import math
from types import SimpleNamespace
from unittest.mock import patch

from axiom.evaluator import _content_hash
from axiom.five_axis.f2_collision import ConfigurationCollisionModel, hash_configuration_collision_model
from axiom.five_axis.f1_models import M2CandidateTaskGeometry
from axiom.five_axis.f2_models import M3CandidateAxisPath, MachineProfile
from axiom.five_axis.f2_runtime import (
    AXIS_LIMIT_MARGIN_MIN_METRIC_ID,
    CONFIGURATION_COLLISION_FREE_CLAIM_ID,
    CONFIGURATION_COLLISION_FREE_METRIC_ID,
    F2_EVALUATOR_ID,
    F2_RUNNER_ID,
    FIVE_AXIS_F2_DOMAIN_PACK,
    FIVE_AXIS_F2_DOMAIN_PACK_ID,
    FIVE_AXIS_F2_RUNTIME_BINDING,
    KINEMATICALLY_FEASIBLE_CLAIM_ID,
    KINEMATICALLY_FEASIBLE_METRIC_ID,
    ORIENTATION_RESIDUAL_MAX_METRIC_ID,
    POSITION_RESIDUAL_MAX_METRIC_ID,
    SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID,
)
from axiom.models import ClaimStatus, MetricStatus
from axiom.run import evaluate_run
from axiom.runtime import get_domain_runtime_binding


_HASH_A = "a" * 64
_TILT_RAD = 0.25
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


def _m2_payload(*, end_x: float = 20.0) -> dict:
    segment_id = "m2.seg.1"
    orientation_segment_id = "m2.ori.1"
    node_id = "m2.node.1"
    tool_axis = [math.sin(_TILT_RAD), 0.0, math.cos(_TILT_RAD)]
    z_height = 40.0 * math.cos(_TILT_RAD)
    x_offset = 40.0 * math.sin(_TILT_RAD)
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
                "startPoint": [x_offset, 0.0, z_height],
                "endPoint": [end_x + x_offset, 0.0, z_height],
            }
        ],
        "orientationSegments": [
            {
                "segmentId": orientation_segment_id,
                "segmentType": "constant",
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "lineage": [_lineage("stmt.axis.1", 1, "TLAXIS/0.2474,0,0.9689")],
                "axis": tool_axis,
            }
        ],
        "nodeEvents": [{"nodeId": node_id, "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": segment_id}],
        "regularityCertificate": _regularity_certificate(segment_id, node_id, certificate_id="m2.reg.1"),
        "tolerances": [
            {"toleranceId": "tol.position", "target": "position", "tolerance": {"absolute": 0.01, "unit": "mm"}},
            {"toleranceId": "tol.orientation", "target": "orientation", "tolerance": {"absolute": 0.01, "unit": "rad"}},
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


def _m2_content_hash() -> str:
    artifact = M2CandidateTaskGeometry.model_validate(_m2_payload())
    return _content_hash(artifact.model_dump(mode="json", by_alias=True, exclude_none=True))


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


def _machine_profile_content_hash() -> str:
    profile = MachineProfile.model_validate(_machine_profile_payload())
    return _content_hash(profile.model_dump(mode="json", by_alias=True, exclude_none=True))


def _axis_limit_state(*, violated: bool = False) -> list[dict]:
    statuses = {
        "axis.x": ("violated-upper", 1000.0, -20.0) if violated else ("within", 100.0, 100.0),
        "axis.y": ("within", 100.0, 100.0),
        "axis.z": ("within", 100.0, 100.0),
        "axis.c": ("within", 1.0, 1.0),
        "axis.b": ("within", 1.0, 1.0),
    }
    return [
        {
            "axisId": axis_id,
            "status": status,
            "distanceToLower": lower,
            "distanceToUpper": upper,
        }
        for axis_id, (status, lower, upper) in statuses.items()
    ]


def _ik_solution(solution_id: str, sigma: float, values: list[float], *, violated: bool = False) -> dict:
    return {
        "solutionId": solution_id,
        "sigma": sigma,
        "branchId": "branch.1",
        "jointValues": values,
        "wrapState": [{"axisId": "axis.c", "turns": 0}, {"axisId": "axis.b", "turns": 0}],
        "axisLimitState": _axis_limit_state(violated=violated),
        "residuals": [
            {"metricId": POSITION_RESIDUAL_MAX_METRIC_ID, "value": 1e-6, "unit": "mm"},
            {"metricId": ORIENTATION_RESIDUAL_MAX_METRIC_ID, "value": 1e-6, "unit": "rad"},
        ],
        "singularity": {"status": "regular", "conditioningMetric": 5.0, "minimumSingularValue": 0.2},
        "withinLimits": not violated,
    }


def _m3_payload(
    *,
    evidence_level: str = "Certified",
    selected_branch_id: str = "branch.1",
    branch_status: str = "active",
    interval_count: int = 1,
    violated_end_solution: bool = False,
    rotary_motion: bool = False,
    singularity_handling: str = "regular-only",
    minimum_singular_value_lower_bound: float = 0.2,
) -> dict:
    segment_id = "m3.seg.1"
    node_id = "m3.node.1"
    end_x = 520.0 if violated_end_solution else 20.0
    m2_payload = _m2_payload(end_x=end_x)
    m2_content_hash = _content_hash(M2CandidateTaskGeometry.model_validate(m2_payload).model_dump(mode="json", by_alias=True, exclude_none=True))
    machine_profile_content_hash = _machine_profile_content_hash()
    if rotary_motion:
        coefficients = [
            [0.0, 0.0, 0.0, 0.0, _TILT_RAD],
            [0.0, 0.0, 0.0, 1.0, 0.0],
        ]
        final_values = [0.0, 0.0, 0.0, 1.0, _TILT_RAD]
    else:
        coefficients = [
            [0.0, 0.0, 0.0, 0.0, _TILT_RAD],
            [end_x, 0.0, 0.0, 0.0, 0.0],
        ]
        final_values = [end_x, 0.0, 0.0, 0.0, _TILT_RAD]
    return {
        "artifactType": "five-axis.m3-candidate-axis-path",
        "schemaVersion": 1,
        "axisPathId": "m3.path.1",
        "sourceCandidateGeometry": m2_payload,
        "sourceCandidateGeometryContentId": m2_content_hash,
        "machineProfile": _machine_profile_payload(),
        "machineProfileContentId": machine_profile_content_hash,
        "pathProgress": _path_progress(segment_id, progress_id="m3.progress.1"),
        "ikSolutions": [
            _ik_solution("ik.0", 0.0, [0.0, 0.0, 0.0, 0.0, _TILT_RAD]),
            _ik_solution("ik.1", 1.0, final_values, violated=violated_end_solution),
        ],
        "branchGraph": {
            "graphId": "graph.1",
            "rootBranchIds": ["branch.1"],
            "branches": [
                {
                    "branchId": "branch.1",
                    "sigmaStart": 0.0,
                    "sigmaEnd": 1.0,
                    "solutionIds": ["ik.0", "ik.1"],
                    "status": branch_status,
                }
            ],
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
                "interpolation": "linear",
                "coefficientBasis": "local-power@1",
                "coefficients": coefficients,
            }
        ],
        "nodeEvents": [{"nodeId": node_id, "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": segment_id}],
        "regularityCertificate": _regularity_certificate(segment_id, node_id, certificate_id="m3.reg.1"),
        "kinematicsCertificate": {
            "certificateId": "kin.cert.1",
            "machineProfileId": "five-axis.machine-profile.dual-head.demo@1",
            "machineProfileContentId": machine_profile_content_hash,
            "sourceCandidateGeometryId": "m2.geom.1",
            "sourceCandidateGeometryContentId": m2_content_hash,
            "branchGraphId": "graph.1",
            "solverId": "five-axis.ik-solver.demo@1",
            "solverVersion": "ik-demo-2026-08-11",
            "evidenceLevel": evidence_level,
            "continuousMethod": "five-axis.linear-fixed-branch-lift@1",
            "claimScope": "selected-continuous-lift",
            "selectedBranchId": selected_branch_id,
            "intervalCount": interval_count,
            "positionResidualUpperBound": 1e-5,
            "orientationResidualUpperBound": 1e-5,
            "axisLimitNormalizedMarginLowerBound": 0.48,
            "minimumSingularValueLowerBound": minimum_singular_value_lower_bound,
            "singularityHandling": singularity_handling,
            "policyIds": [
                "five-axis.closed-form-ik-policy@1",
                "five-axis.branch-wrap-continuity.strict@1",
                "five-axis.selected-branch.lexicographic@1",
            ],
            "numericEnvironment": {"python": "3.14", "solver": "ik-demo-2026-08-11"},
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


def _axis_path(**kwargs) -> M3CandidateAxisPath:
    return M3CandidateAxisPath.model_validate(_m3_payload(**kwargs))


def _collision_model(
    *,
    machine_column_min_x: float,
    machine_column_max_x: float,
    fixture_min_x: float,
    fixture_max_x: float,
    rotary_anchor: bool = False,
    coverage_status: str = "complete",
    covered_pair_kinds: tuple[str, ...] = ("machine-self", "environment"),
    content_id_override: str | None = None,
) -> dict:
    machine_profile_content_hash = _machine_profile_content_hash()
    moving_anchor = {"anchorType": "axis", "anchorAxisId": "axis.c"} if rotary_anchor else {"anchorType": "axis", "anchorAxisId": "axis.x"}
    model = {
        "modelId": "five-axis.configuration-collision.demo@1",
        "machineProfileId": "five-axis.machine-profile.dual-head.demo@1",
        "machineProfileContentId": machine_profile_content_hash,
        "policyId": "five-axis.configuration-collision.explicit-pairs@1",
        "coverageStatus": coverage_status,
        "coveredPairKinds": list(covered_pair_kinds),
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
                "localAabb": {
                    "minCorner": [machine_column_min_x, -0.2, -0.2],
                    "maxCorner": [machine_column_max_x, 0.2, 0.2],
                },
            },
            {
                "entityId": "fixture",
                "entityKind": "environment",
                "anchorType": "base",
                "localAabb": {"minCorner": [fixture_min_x, -0.5, -0.5], "maxCorner": [fixture_max_x, 0.5, 0.5]},
            },
        ],
        "pairs": [
            {
                "pairId": "self-1",
                "pairKind": "machine-self",
                "leftEntityId": "moving-head",
                "rightEntityId": "machine-column",
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
    content_id = hash_configuration_collision_model(ConfigurationCollisionModel.model_validate(model))
    return {**model, "contentId": content_id_override or content_id}


def _run_spec(artifact: M3CandidateAxisPath, *metric_ids: str, collision_model: dict | None = None) -> dict:
    request: dict = {
        "artifact": artifact.model_dump(mode="json", by_alias=True, exclude_none=True),
        "case": {
            "caseId": "five-axis.f2.runtime-contract@1",
            "requiredMetrics": list(metric_ids),
        },
    }
    if collision_model is not None:
        request["collisionModel"] = collision_model
    return {
        "subjectId": "five-axis.f2.fixture@1",
        "domainPackId": FIVE_AXIS_F2_DOMAIN_PACK_ID,
        "runnerId": F2_RUNNER_ID,
        "evaluatorVersion": F2_EVALUATOR_ID,
        "request": request,
    }


def _claim(bundle, claim_definition_id: str):
    return next(claim for claim in bundle.claims if claim.claim_definition_id == claim_definition_id)


def test_f2_domain_pack_declares_m0_m1_m2_m3_and_runtime_binding() -> None:
    assert [(item.artifact_type, item.schema_version, item.role) for item in FIVE_AXIS_F2_DOMAIN_PACK.artifact_type_descriptors] == [
        ("five-axis.normalized-program", 1, "run-input"),
        ("five-axis.m1-reference-path", 1, "run-input"),
        ("five-axis.m2-candidate-task-geometry", 1, "run-input"),
        ("five-axis.m3-candidate-axis-path", 1, "run-input"),
    ]
    assert FIVE_AXIS_F2_DOMAIN_PACK.artifact_type == "five-axis.m3-candidate-axis-path"
    assert get_domain_runtime_binding(FIVE_AXIS_F2_DOMAIN_PACK_ID) is FIVE_AXIS_F2_RUNTIME_BINDING


def test_m3_runs_through_generic_core_binding_and_freezes_continuous_metrics() -> None:
    artifact = _axis_path()

    bundle = evaluate_run(
        _run_spec(
            artifact,
            POSITION_RESIDUAL_MAX_METRIC_ID,
            ORIENTATION_RESIDUAL_MAX_METRIC_ID,
            AXIS_LIMIT_MARGIN_MIN_METRIC_ID,
            SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID,
            KINEMATICALLY_FEASIBLE_METRIC_ID,
        )
    )

    assert bundle.run.domain_pack_id == FIVE_AXIS_F2_DOMAIN_PACK_ID
    assert bundle.report.case_outcome.value == "Passed"
    assert bundle.metric_result(POSITION_RESIDUAL_MAX_METRIC_ID).value == 0.0
    assert bundle.metric_result(ORIENTATION_RESIDUAL_MAX_METRIC_ID).value == 0.0
    assert bundle.metric_result(AXIS_LIMIT_MARGIN_MIN_METRIC_ID).unit == "dimensionless"
    assert bundle.metric_result(AXIS_LIMIT_MARGIN_MIN_METRIC_ID).value == 0.48
    assert bundle.metric_result(SINGULARITY_MINIMUM_SINGULAR_VALUE_METRIC_ID).value == 0.0259321311968
    assert [capability.capability_id for capability in bundle.report.capabilities] == [
        "five-axis.path-progress.bound@1",
        "five-axis.regularity.certified@1",
        "five-axis.machine-profile.bound@1",
    ]


def test_kinematically_feasible_claim_is_supported_only_for_certified_selected_continuous_lift() -> None:
    artifact = _axis_path()

    bundle = evaluate_run(_run_spec(artifact, KINEMATICALLY_FEASIBLE_METRIC_ID))

    result = bundle.metric_result(KINEMATICALLY_FEASIBLE_METRIC_ID)
    claim = _claim(bundle, KINEMATICALLY_FEASIBLE_CLAIM_ID)
    assert result.status is MetricStatus.COMPUTED
    assert result.value is True
    assert result.evidence is not None and result.evidence.level == "Certified"
    assert claim.status is ClaimStatus.SUPPORTED


def test_replay_singularity_gate_uses_raw_decision_instead_of_canonical_evidence() -> None:
    artifact = _axis_path()
    canonical_evidence_above_raw_threshold = SimpleNamespace(
        minimum_singular_value=1e-8,
        singular=False,
    )

    with patch(
        "axiom.five_axis.f2_runtime.jacobian_evidence",
        return_value=canonical_evidence_above_raw_threshold,
    ):
        bundle = evaluate_run(_run_spec(artifact, KINEMATICALLY_FEASIBLE_METRIC_ID))

    result = bundle.metric_result(KINEMATICALLY_FEASIBLE_METRIC_ID)
    claim = _claim(bundle, KINEMATICALLY_FEASIBLE_CLAIM_ID)
    assert result.status is MetricStatus.COMPUTED
    assert result.value is True
    assert result.details["minimumSingularValueMin"] == 1e-8
    assert claim.status is ClaimStatus.SUPPORTED


def test_kinematically_feasible_claim_is_refuted_for_explicit_selected_lift_limit_violation() -> None:
    artifact = _axis_path(violated_end_solution=True)

    bundle = evaluate_run(_run_spec(artifact, KINEMATICALLY_FEASIBLE_METRIC_ID))

    result = bundle.metric_result(KINEMATICALLY_FEASIBLE_METRIC_ID)
    claim = _claim(bundle, KINEMATICALLY_FEASIBLE_CLAIM_ID)
    assert result.status is MetricStatus.COMPUTED
    assert result.value is False
    assert result.reason_code == "SelectedLiftViolatesAxisLimits"
    assert claim.status is ClaimStatus.REFUTED


def test_kinematically_feasible_claim_stays_inconclusive_for_validated_only_certificate() -> None:
    artifact = _axis_path(evidence_level="Validated")

    bundle = evaluate_run(_run_spec(artifact, KINEMATICALLY_FEASIBLE_METRIC_ID))

    result = bundle.metric_result(KINEMATICALLY_FEASIBLE_METRIC_ID)
    claim = _claim(bundle, KINEMATICALLY_FEASIBLE_CLAIM_ID)
    assert result.status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert result.reason_code == "KinematicsCertificateRequiresExactOrCertifiedEvidence"
    assert claim.status is ClaimStatus.INCONCLUSIVE
    assert claim.details["metricStatus"] == "UnsupportedCapability"


def test_kinematically_feasible_claim_requires_whitelisted_method_and_policy_ids() -> None:
    artifact = _axis_path()
    payload = artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["kinematicsCertificate"]["continuousMethod"] = "five-axis.untrusted-lift@1"
    payload["kinematicsCertificate"]["policyIds"] = ["five-axis.closed-form-ik-policy@1"]
    artifact = M3CandidateAxisPath.model_validate(payload)

    bundle = evaluate_run(_run_spec(artifact, KINEMATICALLY_FEASIBLE_METRIC_ID))

    result = bundle.metric_result(KINEMATICALLY_FEASIBLE_METRIC_ID)
    assert result.status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert result.reason_code == "KinematicsContinuousMethodUnsupported"


def test_kinematically_feasible_claim_recomputes_real_embedded_content_hashes() -> None:
    payload = _m3_payload()
    payload["sourceCandidateGeometryContentId"] = "d" * 64
    payload["kinematicsCertificate"]["sourceCandidateGeometryContentId"] = "d" * 64
    artifact = M3CandidateAxisPath.model_validate(payload)

    bundle = evaluate_run(_run_spec(artifact, KINEMATICALLY_FEASIBLE_METRIC_ID))

    result = bundle.metric_result(KINEMATICALLY_FEASIBLE_METRIC_ID)
    assert result.status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert result.reason_code == "SourceCandidateGeometryContentHashMismatch"


def test_configuration_collision_claim_is_inconclusive_when_collision_model_is_missing() -> None:
    artifact = _axis_path()

    bundle = evaluate_run(_run_spec(artifact, CONFIGURATION_COLLISION_FREE_METRIC_ID))

    result = bundle.metric_result(CONFIGURATION_COLLISION_FREE_METRIC_ID)
    claim = _claim(bundle, CONFIGURATION_COLLISION_FREE_CLAIM_ID)
    assert result.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert result.reason_code == "CollisionModelRequired"
    assert claim.status is ClaimStatus.INCONCLUSIVE
    assert claim.details["metricStatus"] == "InsufficientContext"


def test_configuration_collision_claim_is_supported_for_safe_closed_certificate() -> None:
    artifact = _axis_path()
    collision_model = _collision_model(
        machine_column_min_x=30.0,
        machine_column_max_x=30.5,
        fixture_min_x=40.0,
        fixture_max_x=40.5,
    )

    bundle = evaluate_run(_run_spec(artifact, CONFIGURATION_COLLISION_FREE_METRIC_ID, collision_model=collision_model))

    result = bundle.metric_result(CONFIGURATION_COLLISION_FREE_METRIC_ID)
    claim = _claim(bundle, CONFIGURATION_COLLISION_FREE_CLAIM_ID)
    assert result.status is MetricStatus.COMPUTED
    assert result.value is True
    assert claim.status is ClaimStatus.SUPPORTED
    assert bundle.report.capabilities[-1].capability_id == "five-axis.configuration.collision.checked@1"


def test_configuration_collision_claim_is_refuted_when_continuous_segment_contains_collision() -> None:
    artifact = _axis_path()
    collision_model = _collision_model(
        machine_column_min_x=10.2,
        machine_column_max_x=10.6,
        fixture_min_x=40.0,
        fixture_max_x=40.5,
    )

    bundle = evaluate_run(_run_spec(artifact, CONFIGURATION_COLLISION_FREE_METRIC_ID, collision_model=collision_model))

    result = bundle.metric_result(CONFIGURATION_COLLISION_FREE_METRIC_ID)
    claim = _claim(bundle, CONFIGURATION_COLLISION_FREE_CLAIM_ID)
    assert result.status is MetricStatus.COMPUTED
    assert result.value is False
    assert result.reason_code == "CollisionWitnessFound"
    assert claim.status is ClaimStatus.REFUTED


def test_configuration_collision_claim_stays_inconclusive_for_partial_safe_coverage() -> None:
    artifact = _axis_path()
    collision_model = _collision_model(
        machine_column_min_x=30.0,
        machine_column_max_x=30.5,
        fixture_min_x=40.0,
        fixture_max_x=40.5,
        coverage_status="partial",
        covered_pair_kinds=("machine-self", "environment"),
    )

    bundle = evaluate_run(_run_spec(artifact, CONFIGURATION_COLLISION_FREE_METRIC_ID, collision_model=collision_model))

    result = bundle.metric_result(CONFIGURATION_COLLISION_FREE_METRIC_ID)
    claim = _claim(bundle, CONFIGURATION_COLLISION_FREE_CLAIM_ID)
    assert result.status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert result.reason_code == "ConfigurationCollisionClaimUnavailable"
    assert claim.status is ClaimStatus.INCONCLUSIVE


def test_configuration_collision_claim_reuses_lift_gate() -> None:
    artifact = _axis_path()
    payload = artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["kinematicsCertificate"]["continuousMethod"] = "five-axis.untrusted-lift@1"
    artifact = M3CandidateAxisPath.model_validate(payload)
    collision_model = _collision_model(
        machine_column_min_x=30.0,
        machine_column_max_x=30.5,
        fixture_min_x=40.0,
        fixture_max_x=40.5,
    )

    bundle = evaluate_run(_run_spec(artifact, CONFIGURATION_COLLISION_FREE_METRIC_ID, collision_model=collision_model))

    result = bundle.metric_result(CONFIGURATION_COLLISION_FREE_METRIC_ID)
    assert result.status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert result.reason_code == "KinematicsContinuousMethodUnsupported"


def test_positive_lift_rejects_rotary_motion_outside_fixed_branch_proof() -> None:
    bundle = evaluate_run(
        _run_spec(_axis_path(rotary_motion=True), KINEMATICALLY_FEASIBLE_METRIC_ID)
    )

    result = bundle.metric_result(KINEMATICALLY_FEASIBLE_METRIC_ID)
    assert result.status == MetricStatus.UNSUPPORTED_CAPABILITY
    assert result.reason_code == "RotaryMotionUnsupportedByLinearFixedBranchProof"


def test_f2_runtime_provenance_and_claim_hashes_are_deterministic() -> None:
    artifact = _axis_path()
    collision_model = _collision_model(
        machine_column_min_x=30.0,
        machine_column_max_x=30.5,
        fixture_min_x=40.0,
        fixture_max_x=40.5,
    )
    spec = _run_spec(
        artifact,
        KINEMATICALLY_FEASIBLE_METRIC_ID,
        CONFIGURATION_COLLISION_FREE_METRIC_ID,
        collision_model=collision_model,
    )

    first = evaluate_run(spec).model_dump(mode="json", by_alias=True, exclude_none=True)
    second = evaluate_run(copy.deepcopy(spec)).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert first == second
    assert first["report"]["provenance"]["runnerId"] == F2_RUNNER_ID
    assert first["report"]["provenance"]["evaluatorVersion"] == F2_EVALUATOR_ID
