from __future__ import annotations

import pytest
from pydantic import ValidationError

from axiom.five_axis.f2_models import F2MathStageManifest, M3CandidateAxisPath, MachineProfile


_HASH_A = "a" * 64
_HASH_B = "b" * 64
_HASH_C = "c" * 64
_HASH_D = "d" * 64


def _lineage(statement_id: str, index: int, text: str) -> dict:
    return {
        "statementId": statement_id,
        "statementIndex": index,
        "line": index + 1,
        "column": 1,
        "sourceText": text,
        "sourcePath": "fixture.cl",
    }


def _coordinate_context() -> dict:
    return {"unit": "mm", "coordinateFrame": "machine.work-envelope@1"}


def _provenance(source_stage: str, source_id: str) -> dict:
    return {"sourceStage": source_stage, "sourceId": source_id, "method": "fixture"}


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
        "coordinateContext": _coordinate_context(),
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
            {"toleranceId": "tol.sigma", "target": "sigma", "tolerance": {"absolute": 1e-6, "unit": "dimensionless"}},
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
        "profileId": "five-axis.machine-profile.head-table.demo@1",
        "profileVersion": 1,
        "topology": "head-table",
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
                "semanticRole": "workpiece-rotary-primary",
                "origin": [0.0, 0.0, 0.0],
                "direction": [0.0, 0.0, 1.0],
                "installationSide": "workpiece",
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
                "semanticRole": "tool-rotary-primary",
                "parentAxisId": "axis.z",
                "origin": [0.0, 0.0, 120.0],
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
            "translation": [0.0, 0.0, 100.0],
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


def _m3_payload() -> dict:
    segment_id = "m3.seg.1"
    node_id = "m3.node.1"
    return {
        "artifactType": "five-axis.m3-candidate-axis-path",
        "schemaVersion": 1,
        "axisPathId": "m3.path.1",
        "sourceCandidateGeometry": _m2_payload(),
        "sourceCandidateGeometryContentId": _HASH_B,
        "machineProfile": _machine_profile_payload(),
        "machineProfileContentId": _HASH_C,
        "pathProgress": _path_progress(segment_id, progress_id="m3.progress.1"),
        "ikSolutions": [
            _ik_solution("ik.0", 0.0, [0.0, 0.0, 0.0, 0.0, 0.0]),
            _ik_solution("ik.1", 1.0, [20.0, 0.0, 0.0, 0.25, 0.5]),
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
                "interpolation": "linear",
                "coefficientBasis": "local-power@1",
                "coefficients": [
                    [0.0, 0.0, 0.0, 0.0, 0.0],
                    [20.0, 0.0, 0.0, 0.25, 0.5],
                ],
            }
        ],
        "nodeEvents": [{"nodeId": node_id, "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": segment_id}],
        "regularityCertificate": _regularity_certificate(segment_id, node_id, certificate_id="m3.reg.1"),
        "kinematicsCertificate": {
            "certificateId": "kin.cert.1",
            "machineProfileId": "five-axis.machine-profile.head-table.demo@1",
            "machineProfileContentId": _HASH_C,
            "sourceCandidateGeometryId": "m2.geom.1",
            "sourceCandidateGeometryContentId": _HASH_B,
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


def _manifest_payload() -> dict:
    return {
        "manifestId": "five-axis.f2-math-stage-manifest@1",
        "schemaId": "five-axis.f2-math-stage-manifest@1",
        "schemaVersion": 1,
        "stage": "F2",
        "artifactDescriptors": [
            {"stage": "M0", "artifactType": "five-axis.normalized-program", "schemaId": "five-axis.normalized-program@1"},
            {"stage": "M1", "artifactType": "five-axis.m1-reference-path", "schemaId": "five-axis.m1-reference-path@1"},
            {"stage": "M2", "artifactType": "five-axis.m2-candidate-task-geometry", "schemaId": "five-axis.m2-candidate-task-geometry@1"},
            {"stage": "M3", "artifactType": "five-axis.m3-candidate-axis-path", "schemaId": "five-axis.m3-candidate-axis-path@1"},
        ],
        "machineProfileSchemaId": "five-axis.machine-profile@1",
        "machineProfileId": "five-axis.machine-profile.head-table.demo@1",
        "machineProfileContentId": _HASH_C,
        "capabilityIds": ["five-axis.machine-profile.bound@1", "five-axis.configuration.collision.checked@1"],
        "fixtureContentIds": [_HASH_D],
        "policyIds": ["five-axis.ik-branch-graph.strict@1"],
        "numericEnvironment": {"python": "3.14", "solver": "ik-demo-2026-08-11"},
        "expectedMetrics": [
            {"metricId": "five-axis.position-residual.max@1", "expectedStatus": "Computed", "expectedValue": 1e-6, "unit": "mm"}
        ],
        "expectedClaims": [
            {
                "claimId": "five-axis.kinematically-feasible-claim@1",
                "claimClass": "M3",
                "expectedStatus": "Supported",
                "evidenceLevel": "machine-replayable",
            }
        ],
        "expectedEvidence": [{"evidenceId": "evidence.kin", "evidenceKind": "kinematics", "required": True}],
        "tolerances": [
            {"toleranceId": "tol.position", "target": "position", "tolerance": {"absolute": 1e-5, "unit": "mm"}},
            {"toleranceId": "tol.orientation", "target": "orientation", "tolerance": {"absolute": 1e-5, "unit": "rad"}},
        ],
        "decisions": [{"decisionId": "decision.1", "status": "accepted", "rationale": "Freeze F2 contract surface."}],
    }


def test_machine_profile_accepts_head_table_topology() -> None:
    profile = MachineProfile.model_validate(_machine_profile_payload())
    assert profile.profile_id == "five-axis.machine-profile.head-table.demo@1"
    assert profile.topology == "head-table"
    assert tuple(axis.axis_symbol for axis in profile.axes) == ("X", "Y", "Z", "C", "B")


def test_machine_profile_rejects_topology_side_mismatch() -> None:
    payload = _machine_profile_payload()
    payload["axes"][4]["installationSide"] = "workpiece"
    payload["axes"][4]["semanticRole"] = "workpiece-rotary-secondary"
    payload["axes"][4]["parentAxisId"] = "axis.c"
    with pytest.raises(ValidationError, match="installationSide counts must match topology"):
        MachineProfile.model_validate(payload)


def test_machine_profile_rejects_cross_side_parent() -> None:
    payload = _machine_profile_payload()
    payload["axes"][4]["parentAxisId"] = "axis.c"
    with pytest.raises(ValidationError, match="preceding axis on the same installationSide"):
        MachineProfile.model_validate(payload)


def test_m3_candidate_axis_path_roundtrips() -> None:
    payload = _m3_payload()
    candidate = M3CandidateAxisPath.model_validate(payload)
    dumped = candidate.model_dump(mode="json", by_alias=True)
    roundtrip = M3CandidateAxisPath.model_validate(dumped)
    assert roundtrip.kinematics_certificate.machine_profile_content_id == _HASH_C
    assert roundtrip.joint_segments[0].coefficients[1][3] == pytest.approx(0.25)


def test_m3_candidate_axis_path_rejects_non_rotary_wrap_axis() -> None:
    payload = _m3_payload()
    payload["ikSolutions"][0]["wrapState"][0]["axisId"] = "axis.x"
    with pytest.raises(ValidationError, match="wrapState may only reference revolute"):
        M3CandidateAxisPath.model_validate(payload)


def test_m3_candidate_axis_path_rejects_missing_segment_coverage() -> None:
    payload = _m3_payload()
    payload["pathProgress"]["mappings"][0]["sourceSegmentId"] = "m3.seg.unknown"
    with pytest.raises(ValidationError, match="pathProgress mappings must target actual jointSegments"):
        M3CandidateAxisPath.model_validate(payload)


def test_f2_manifest_allows_positive_m3_claims_but_blocks_device_safe() -> None:
    manifest = F2MathStageManifest.model_validate(_manifest_payload())
    assert manifest.expected_claims[0].claim_id == "five-axis.kinematically-feasible-claim@1"

    payload = _manifest_payload()
    payload["expectedClaims"] = [
        {
            "claimId": "five-axis.device-safe-claim@1",
            "claimClass": "DeviceSafe",
            "expectedStatus": "Supported",
            "evidenceLevel": "machine-replayable",
        }
    ]
    with pytest.raises(ValidationError, match="must not publish positive M4/M5/DeviceSafe claims"):
        F2MathStageManifest.model_validate(payload)


def test_f2_manifest_rejects_non_whitelisted_supported_m3_claim() -> None:
    payload = _manifest_payload()
    payload["expectedClaims"] = [
        {
            "claimId": "five-axis.model-collision-free-claim@1",
            "claimClass": "M3",
            "expectedStatus": "Supported",
            "evidenceLevel": "machine-replayable",
        }
    ]
    with pytest.raises(ValidationError, match="frozen whitelist IDs"):
        F2MathStageManifest.model_validate(payload)
