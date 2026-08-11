from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from axiom.five_axis.f1_models import (
    F1MathStageManifest,
    M1ReferencePath,
    M2CandidateTaskGeometry,
    NormalizedProgram,
    PathProgress,
    RegularityCertificate,
    ToleranceBinding,
)


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


def _path_progress(segment_id: str, *, progress_id: str = "progress.1") -> dict:
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
                "provenance": _provenance("M1", segment_id),
            }
        ],
    }


def _regularity_certificate(segment_id: str, node_id: str, continuity_class: str = "C1") -> dict:
    order_count = {"C0": 1, "C1": 2, "C2": 3, "C3": 4}[continuity_class]
    derivatives = [{"order": order, "components": [float(order), 0.0, 0.0]} for order in range(order_count)]
    return {
        "certificateId": f"reg.{segment_id}",
        "segmentEvidence": [
            {
                "segmentId": segment_id,
                "continuityClass": continuity_class,
                "derivatives": derivatives,
                "verificationMethod": "analytic",
            }
        ],
        "nodeEvidence": [
            {
                "nodeId": node_id,
                "continuityClass": continuity_class,
                "leftDerivatives": derivatives,
                "rightDerivatives": derivatives,
                "verificationMethod": "analytic",
            }
        ],
    }


def _normalized_program_payload(*, include_dwell: bool = False) -> dict:
    events = [
        {
            "eventId": "evt.from.1",
            "eventType": "FROM",
            "lineage": _lineage("stmt.from.1", 0, "FROM/0,0,0"),
            "coordinateContext": _coordinate_context(),
            "position": [0.0, 0.0, 0.0],
            "toolAxis": [0.0, 0.0, 1.0],
            "toolAxisSource": "explicit",
            "sourceToolAxis": [0.0, 0.0, 1.0],
            "normalizationMethod": "unit-vector@1",
        },
        {
            "eventId": "evt.feed.1",
            "eventType": "FEDRAT",
            "lineage": _lineage("stmt.feed.1", 1, "FEDRAT/1200"),
            "feedRate": 1200.0,
            "unit": "mm/min",
        },
    ]
    if include_dwell:
        events.append(
            {
                "eventId": "evt.dwell.1",
                "eventType": "DWELL",
                "lineage": _lineage("stmt.dwell.1", 2, "DWELL/0.25"),
                "duration": 0.25,
                "unit": "s",
            }
        )
    events.extend(
        [
            {
                "eventId": "evt.goto.1",
                "eventType": "GOTO",
                "lineage": _lineage("stmt.goto.1", 3, "GOTO/10,0,0"),
                "coordinateContext": _coordinate_context(),
                "position": [10.0, 0.0, 0.0],
                "toolAxis": [0.0, 0.0, 1.0],
                "toolAxisSource": "modal-inherited",
                "toolAxisSourceStatementId": "stmt.from.1",
                "sourceToolAxis": [0.0, 0.0, 1.0],
                "normalizationMethod": "unit-vector@1",
            },
            {
                "eventId": "evt.end.1",
                "eventType": "END",
                "lineage": _lineage("stmt.end.1", 4, "END"),
            },
        ]
    )
    return {
        "artifactType": "five-axis.normalized-program",
        "schemaVersion": 1,
        "programId": "program.1",
        "sourceSyntaxId": "axiom-cl-subset@1",
        "coordinateContext": _coordinate_context(),
        "events": events,
    }


def _m1_payload() -> dict:
    segment_id = "m1.seg.line.1"
    node_id = "m1.node.1"
    return {
        "artifactType": "five-axis.m1-reference-path",
        "schemaVersion": 1,
        "referencePathId": "m1.path.1",
        "coordinateContext": _coordinate_context(),
        "pathProgress": _path_progress(segment_id, progress_id="m1.progress.1"),
        "positionSemantics": "continuous",
        "positionSegments": [
            {
                "segmentId": segment_id,
                "segmentType": "line",
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "lineage": [_lineage("stmt.goto.1", 0, "GOTO/10,0,0")],
                "startPoint": [0.0, 0.0, 0.0],
                "endPoint": [10.0, 0.0, 0.0],
            }
        ],
        "nodeEvents": [
            {
                "nodeId": node_id,
                "sigma": 0.0,
                "eventType": "ordinary-junction",
                "rightSegmentId": segment_id,
            }
        ],
        "regularityCertificate": _regularity_certificate(segment_id, node_id),
    }


def _collision_context() -> dict:
    return {
        "contextId": "collision.ctx.1",
        "toolComponents": [
            {
                "componentId": "tool.cutter.1",
                "componentKind": "cutter",
                "shapeType": "capsule",
                "radius": 1.0,
                "axisStartOffset": -5.0,
                "axisEndOffset": 0.0,
            },
            {
                "componentId": "tool.shaft.1",
                "componentKind": "shaft",
                "shapeType": "capsule",
                "radius": 1.5,
                "axisStartOffset": -20.0,
                "axisEndOffset": -5.0,
            },
            {
                "componentId": "tool.holder.1",
                "componentKind": "holder",
                "shapeType": "sphere",
                "radius": 3.0,
                "axisStartOffset": -22.0,
                "axisEndOffset": -22.0,
            },
        ],
        "stockFixtures": [
            {"stockFixtureId": "stock.1", "category": "stock", "aabb": {"minCorner": [-5.0, -5.0, -1.0], "maxCorner": [5.0, 5.0, 1.0]}},
            {"stockFixtureId": "fixture.1", "category": "fixture", "aabb": {"minCorner": [-6.0, -6.0, -2.0], "maxCorner": [6.0, 6.0, 2.0]}},
        ],
        "allowedRemoval": [
            {"removalId": "removal.1", "toolComponentId": "tool.cutter.1", "stockFixtureId": "stock.1"}
        ],
        "minimumClearance": {"absolute": 0.1, "unit": "mm"},
        "solverTolerance": {"absolute": 1e-6, "unit": "mm"},
        "envelopeTolerance": {"absolute": 1e-6, "unit": "mm"},
        "contactPolicy": {
            "policyId": "five-axis.contact-policy.explicit@1",
            "rules": [
                {
                    "ruleId": "contact.stock.1",
                    "leftCategory": "cutter",
                    "rightCategory": "stock",
                    "contactPolicy": "allowed",
                },
                {
                    "ruleId": "contact.fixture.1",
                    "leftCategory": "cutter",
                    "rightCategory": "fixture",
                    "contactPolicy": "forbidden",
                },
                {
                    "ruleId": "contact.shaft-holder.1",
                    "leftCategory": "shaft",
                    "rightCategory": "holder",
                    "contactPolicy": "forbidden",
                },
            ],
        },
    }


def _process_state_timeline_payload() -> dict:
    return {
        "timelineId": "timeline.1",
        "stockUpdatePolicy": {"policyId": "five-axis.stock-update.explicit-snapshot@1"},
        "failureStateSemantics": {
            "policyId": "five-axis.process-state.failure-terminal@1",
            "failedStateMeaning": "last-input-state-persists",
        },
        "intervals": [
            {
                "intervalId": "state.1",
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "motionMode": "cut",
                "spindleState": "cw",
                "toolComponentId": "tool.cutter.1",
                "coolantOn": True,
                "inputStockState": {"stateId": "stock.input.1", "contentId": "a" * 64},
                "outputStockState": {"stateId": "stock.output.1", "contentId": "b" * 64},
            }
        ],
    }


def _correspondence_payload() -> dict:
    return {
        "certificateId": "corr.cert.1",
        "sourceGeometryId": "m2.path.1",
        "targetReferencePathId": "m1.path.1",
        "policy": {
            "strategyId": "five-axis.correspondence.provenance-progress@1",
            "allowedSourceInterval": [0.0, 1.0],
            "allowedTargetInterval": [0.0, 1.0],
            "objective": "preserve-source-lineage",
            "deterministicTieBreak": "lowest-source-segment-id",
            "numericTolerance": {"absolute": 1e-9, "unit": "dimensionless"},
        },
        "canonicalNodes": [
            {"pathRole": "source", "nodeId": "m2.node.1", "sigma": 0.0, "segmentId": "m2.seg.line.1"},
            {"pathRole": "target", "nodeId": "reference.node.1", "sigma": 0.0, "segmentId": "m1.seg.line.1"},
        ],
        "allowedSourceIntervals": [
            {"sourceSegmentId": "m2.seg.line.1", "allowedTargetIntervals": [[0.0, 1.0]]}
        ],
        "selectedNodeMapping": [{"sourceNodeId": "m2.node.1", "targetNodeId": "reference.node.1"}],
        "intervals": [
            {
                "intervalId": "corr.interval.1",
                "sourceSigmaStart": 0.0,
                "sourceSigmaEnd": 1.0,
                "targetSigmaStart": 0.0,
                "targetSigmaEnd": 1.0,
                "sourceSegmentId": "m2.seg.line.1",
                "targetSegmentId": "m1.seg.line.1",
                "correspondenceStatus": "matched",
            }
        ],
        "primaryObjectiveLower": 0.0,
        "primaryObjectiveUpper": 0.0,
        "objectiveDomain": "continuous",
        "tieBreakObjective": "lowest-source-segment-id",
        "numericTolerance": {"absolute": 1e-9, "unit": "dimensionless"},
        "solverVersion": "corr-solver@1",
        "evidenceLevel": "machine-replayable",
    }


def _m2_payload() -> dict:
    segment_id = "m2.seg.line.1"
    node_id = "m2.node.1"
    return {
        "artifactType": "five-axis.m2-candidate-task-geometry",
        "schemaVersion": 1,
        "candidateGeometryId": "m2.path.1",
        "sourceReferencePathId": "m1.path.1",
        "sourceReferencePathContentId": "c" * 64,
        "pathProgress": _path_progress(segment_id, progress_id="m2.progress.1"),
        "positionSemantics": "continuous",
        "positionSegments": [
            {
                "segmentId": segment_id,
                "segmentType": "line",
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "lineage": [_lineage("stmt.goto.1", 0, "GOTO/10,0,0")],
                "startPoint": [0.0, 0.0, 0.0],
                "endPoint": [10.0, 0.0, 0.0],
            }
        ],
        "nodeEvents": [
            {
                "nodeId": node_id,
                "sigma": 0.0,
                "eventType": "ordinary-junction",
                "rightSegmentId": segment_id,
            }
        ],
        "regularityCertificate": _regularity_certificate(segment_id, node_id),
        "tolerances": [
            {"toleranceId": "tol.position.1", "target": "position", "tolerance": {"absolute": 0.01, "unit": "mm"}},
            {"toleranceId": "tol.orientation.1", "target": "orientation", "tolerance": {"absolute": 0.05, "unit": "rad"}},
        ],
        "correspondence": _correspondence_payload(),
        "collisionContext": _collision_context(),
        "processStateTimeline": _process_state_timeline_payload(),
    }


def _manifest_payload() -> dict:
    return {
        "manifestId": "five-axis.f1-math-stage-manifest@1",
        "schemaId": "five-axis.f1-math-stage-manifest@1",
        "schemaVersion": 1,
        "stage": "F1",
        "artifactDescriptors": [
            {"stage": "M0", "artifactType": "five-axis.normalized-program", "schemaId": "five-axis.normalized-program@1"},
            {"stage": "M1", "artifactType": "five-axis.m1-reference-path", "schemaId": "five-axis.m1-reference-path@1"},
            {
                "stage": "M2",
                "artifactType": "five-axis.m2-candidate-task-geometry",
                "schemaId": "five-axis.m2-candidate-task-geometry@1",
            },
        ],
        "capabilityIds": ["five-axis.contract.f1@1"],
        "fixtureContentIds": ["d" * 64],
        "policyIds": [
            "five-axis.correspondence.provenance-progress@1",
            "five-axis.stock-update.explicit-snapshot@1",
        ],
        "numericEnvironment": {"python": "3.12", "pydantic": "2.11"},
        "expectedMetrics": [
            {"metricId": "five-axis.position.sup@1", "expectedStatus": "Computed", "expectedValue": 0.01, "unit": "mm"}
        ],
        "expectedClaims": [
            {
                "claimId": "five-axis.geometry-valid-claim@1",
                "claimClass": "M2",
                "expectedStatus": "Supported",
                "evidenceLevel": "machine-replayable",
            }
        ],
        "expectedEvidence": [{"evidenceId": "evidence.1", "evidenceKind": "lineage", "required": True}],
        "tolerances": [
            {"toleranceId": "tol.manifest.1", "target": "position", "tolerance": {"absolute": 0.01, "unit": "mm"}}
        ],
        "decisions": [{"decisionId": "decision.1", "status": "accepted", "rationale": "F1 only publishes M0-M2 claims."}],
    }


def test_f1_models_accept_minimal_valid_contracts_and_roundtrip():
    program = NormalizedProgram.model_validate(_normalized_program_payload())
    reference_path = M1ReferencePath.model_validate(_m1_payload())
    candidate = M2CandidateTaskGeometry.model_validate(_m2_payload())
    manifest = F1MathStageManifest.model_validate(_manifest_payload())

    dumped = candidate.model_dump(mode="json", by_alias=True, exclude_none=True)
    roundtrip = M2CandidateTaskGeometry.model_validate(dumped)

    assert program.events[0].event_type == "FROM"
    assert program.events[2].tool_axis_source_statement_id == "stmt.from.1"
    assert reference_path.path_progress.progress_id == "m1.progress.1"
    assert candidate.correspondence.policy.strategy_id == "five-axis.correspondence.provenance-progress@1"
    assert manifest.stage == "F1"
    assert roundtrip.model_dump(mode="json", by_alias=True, exclude_none=True) == dumped


def test_m2_can_parse_without_collision_support_objects():
    payload = _m2_payload()
    payload.pop("collisionContext")
    payload.pop("processStateTimeline")

    candidate = M2CandidateTaskGeometry.model_validate(payload)

    assert candidate.collision_context is None
    assert candidate.process_state_timeline is None


def test_f1_models_accept_dwell_orientation_only_and_degenerate_segment_forms():
    program_payload = _normalized_program_payload(include_dwell=True)
    program = NormalizedProgram.model_validate(program_payload)

    orientation_only = {
        "artifactType": "five-axis.m1-reference-path",
        "schemaVersion": 1,
        "referencePathId": "m1.axis.only",
        "coordinateContext": _coordinate_context(),
        "pathProgress": _path_progress("m1.axis.seg.1", progress_id="m1.axis.progress"),
        "positionSemantics": "static",
        "staticPosition": [0.0, 0.0, 0.0],
        "orientationSegments": [
            {
                "segmentId": "m1.axis.seg.1",
                "segmentType": "slerp",
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "lineage": [_lineage("stmt.axis.1", 0, "AXIS/0,0,1->0,1,0")],
                "startAxis": [0.0, 0.0, 1.0],
                "endAxis": [0.0, 1.0, 0.0],
                "antipodalPolicy": "reject",
            }
        ],
        "nodeEvents": [{"nodeId": "m1.axis.node.1", "sigma": 0.0, "eventType": "dwell"}],
    }
    degenerate = copy.deepcopy(_m1_payload())
    degenerate["positionSegments"] = [
        {
            "segmentId": "m1.seg.zero.1",
            "segmentType": "line",
            "sigmaStart": 0.0,
            "sigmaEnd": 0.0,
            "isDegenerate": True,
            "lineage": [_lineage("stmt.zero.1", 0, "GOTO/0,0,0")],
            "startPoint": [0.0, 0.0, 0.0],
            "endPoint": [0.0, 0.0, 0.0],
        },
        degenerate["positionSegments"][0],
    ]
    degenerate["pathProgress"]["mappings"] = [
        {
            "mappingId": "m1.progress.zero",
            "sourceSegmentId": "m1.seg.zero.1",
            "sourceLocalStart": 0.0,
            "sourceLocalEnd": 0.0,
            "sigmaStart": 0.0,
            "sigmaEnd": 0.0,
            "degenerateKind": "point-segment",
        },
        degenerate["pathProgress"]["mappings"][0],
    ]
    degenerate["nodeEvents"] = [
        {"nodeId": "m1.node.zero.1", "sigma": 0.0, "eventType": "degenerate-segment", "rightSegmentId": "m1.seg.zero.1"},
        degenerate["nodeEvents"][0],
    ]
    degenerate["regularityCertificate"] = _regularity_certificate("m1.seg.line.1", "m1.node.1")

    assert any(event.event_type == "DWELL" for event in program.events)
    assert M1ReferencePath.model_validate(orientation_only).position_semantics == "static"
    assert M1ReferencePath.model_validate(degenerate).position_segments[0].is_degenerate is True


@pytest.mark.parametrize("continuity_class", ["C0", "C1", "C2", "C3"])
def test_regularity_certificate_supports_c0_through_c3(continuity_class: str):
    payload = _regularity_certificate("seg.1", "node.1", continuity_class=continuity_class)
    certificate = RegularityCertificate.model_validate(payload)

    assert certificate.segment_evidence[0].continuity_class == continuity_class
    assert certificate.node_evidence[0].continuity_class == continuity_class


@pytest.mark.parametrize(
    ("builder", "mutator", "expected"),
    [
        (_normalized_program_payload, lambda payload: payload["events"][0].__setitem__("position", [float("inf"), 0.0, 0.0]), "finite JSON number"),
        (_normalized_program_payload, lambda payload: payload["events"][0].__setitem__("toolAxis", [0.0, 0.0, 0.0]), "zero vector"),
        (_normalized_program_payload, lambda payload: payload["events"][2].pop("toolAxisSourceStatementId"), "modal-inherited toolAxisSource requires toolAxisSourceStatementId"),
        (_normalized_program_payload, lambda payload: payload["events"][2].__setitem__("sourceToolAxis", [1.0, 0.0, 0.0]), "sourceToolAxis must equal the most recent explicit tool axis"),
        (_normalized_program_payload, lambda payload: payload["events"][0].__setitem__("toolAxisSourceStatementId", "stmt.bad.1"), "explicit toolAxisSource forbids toolAxisSourceStatementId"),
        (_normalized_program_payload, lambda payload: payload.__setitem__("sourceSyntaxId", "garbage@1"), "sourceSyntaxId must be axiom-cl-subset@1 or an importer ID"),
        (_normalized_program_payload, lambda payload: payload.__setitem__("sourceSyntaxId", "@1"), "sourceSyntaxId must be axiom-cl-subset@1 or an importer ID"),
        (_m1_payload, lambda payload: payload["pathProgress"]["mappings"][0].__setitem__("sourceSegmentId", "missing.seg"), "pathProgress mappings must target actual segments"),
        (_m1_payload, lambda payload: payload["positionSegments"].append(copy.deepcopy(payload["positionSegments"][0])), "duplicate IDs"),
        (_m1_payload, lambda payload: payload.__setitem__("staticPosition", [0.0, 0.0, 0.0]), "continuous position paths forbid staticPosition"),
        (_m2_payload, lambda payload: payload["tolerances"][1]["tolerance"].__setitem__("unit", "mm"), "orientation tolerance must use rad or deg"),
        (_m2_payload, lambda payload: payload["processStateTimeline"]["intervals"][0].pop("outputStockState"), "explicit-snapshot stockUpdatePolicy requires outputStockState"),
        (_m2_payload, lambda payload: payload["correspondence"].__setitem__("sourceGeometryId", "other.m2.path"), "correspondence sourceGeometryId must match M2 candidateGeometryId"),
        (_m2_payload, lambda payload: payload["processStateTimeline"]["intervals"][0].__setitem__("toolComponentId", "missing.tool"), "processStateTimeline toolComponentId must reference collisionContext toolComponents"),
    ],
)
def test_f1_models_reject_invalid_contract_boundaries(builder, mutator, expected: str):
    payload = builder()
    mutator(payload)

    model = {
        _normalized_program_payload: NormalizedProgram,
        _m1_payload: M1ReferencePath,
        _m2_payload: M2CandidateTaskGeometry,
    }[builder]

    with pytest.raises(ValidationError, match=expected):
        model.model_validate(payload)


def test_path_progress_rejects_sigma_gap_overlap_and_incomplete_source_local_coverage():
    gap_payload = {
        "progressId": "gap.progress.1",
        "schemaVersion": 1,
        "progressParameter": "sigma",
        "unit": "dimensionless",
        "mappings": [
            {
                "mappingId": "gap.map.1",
                "sourceSegmentId": "seg.1",
                "sourceLocalStart": 0.0,
                "sourceLocalEnd": 0.5,
                "sigmaStart": 0.0,
                "sigmaEnd": 0.4,
                "degenerateKind": "none",
            },
            {
                "mappingId": "gap.map.2",
                "sourceSegmentId": "seg.1",
                "sourceLocalStart": 0.5,
                "sourceLocalEnd": 1.0,
                "sigmaStart": 0.5,
                "sigmaEnd": 1.0,
                "degenerateKind": "none",
            },
        ],
    }
    overlap_payload = copy.deepcopy(gap_payload)
    overlap_payload["progressId"] = "overlap.progress.1"
    overlap_payload["mappings"][1]["sigmaStart"] = 0.3
    incomplete_local_payload = copy.deepcopy(gap_payload)
    incomplete_local_payload["progressId"] = "incomplete.progress.1"
    incomplete_local_payload["mappings"] = [
        {
            "mappingId": "incomplete.map.1",
            "sourceSegmentId": "seg.1",
            "sourceLocalStart": 0.1,
            "sourceLocalEnd": 1.0,
            "sigmaStart": 0.0,
            "sigmaEnd": 1.0,
            "degenerateKind": "none",
        }
    ]
    reverse_local_payload = copy.deepcopy(gap_payload)
    reverse_local_payload["progressId"] = "reverse.progress.1"
    reverse_local_payload["mappings"] = [
        {
            "mappingId": "reverse.map.1",
            "sourceSegmentId": "seg.1",
            "sourceLocalStart": 0.5,
            "sourceLocalEnd": 1.0,
            "sigmaStart": 0.0,
            "sigmaEnd": 0.5,
            "degenerateKind": "none",
        },
        {
            "mappingId": "reverse.map.2",
            "sourceSegmentId": "seg.1",
            "sourceLocalStart": 0.0,
            "sourceLocalEnd": 0.5,
            "sigmaStart": 0.5,
            "sigmaEnd": 1.0,
            "degenerateKind": "none",
        },
    ]

    with pytest.raises(ValidationError, match="must not contain gaps"):
        PathProgress.model_validate(gap_payload)
    with pytest.raises(ValidationError, match="must not overlap"):
        PathProgress.model_validate(overlap_payload)
    with pytest.raises(ValidationError, match="must not contain gaps"):
        PathProgress.model_validate(incomplete_local_payload)
    with pytest.raises(ValidationError, match="must not contain gaps"):
        PathProgress.model_validate(reverse_local_payload)


def test_manifest_rejects_forbidden_positive_claims_and_duplicate_policy_ids():
    positive_claim = _manifest_payload()
    positive_claim["expectedClaims"][0]["claimClass"] = "M4"

    duplicate_policy_ids = _manifest_payload()
    duplicate_policy_ids["policyIds"] = [
        "five-axis.correspondence.provenance-progress@1",
        "five-axis.correspondence.provenance-progress@1",
    ]

    with pytest.raises(ValidationError, match="must not publish positive M3/M4/M5/DeviceSafe claims"):
        F1MathStageManifest.model_validate(positive_claim)
    with pytest.raises(ValidationError, match="duplicates"):
        F1MathStageManifest.model_validate(duplicate_policy_ids)

    non_whitelist_claim = _manifest_payload()
    non_whitelist_claim["expectedClaims"][0]["claimId"] = "five-axis.other-claim@1"
    with pytest.raises(ValidationError, match="Supported claims must use the F1 whitelist IDs"):
        F1MathStageManifest.model_validate(non_whitelist_claim)


def test_antipodal_orientation_and_regular_certificate_target_mismatch_are_rejected():
    orientation_only = {
        "artifactType": "five-axis.m1-reference-path",
        "schemaVersion": 1,
        "referencePathId": "m1.axis.bad",
        "coordinateContext": _coordinate_context(),
        "pathProgress": _path_progress("m1.axis.bad.seg", progress_id="m1.axis.bad.progress"),
        "positionSemantics": "static",
        "staticPosition": [0.0, 0.0, 0.0],
        "orientationSegments": [
            {
                "segmentId": "m1.axis.bad.seg",
                "segmentType": "slerp",
                "sigmaStart": 0.0,
                "sigmaEnd": 1.0,
                "lineage": [_lineage("stmt.axis.bad", 0, "AXIS/0,0,1->0,0,-1")],
                "startAxis": [0.0, 0.0, 1.0],
                "endAxis": [0.0, 0.0, -1.0],
                "antipodalPolicy": "reject",
            }
        ],
        "nodeEvents": [{"nodeId": "m1.axis.bad.node", "sigma": 0.0, "eventType": "ordinary-junction"}],
        "regularityCertificate": _regularity_certificate("wrong.seg", "m1.axis.bad.node"),
    }

    with pytest.raises(ValidationError, match="antipodal tool-axis interpolation is rejected"):
        M1ReferencePath.model_validate(orientation_only)

    mismatch = _m1_payload()
    mismatch["regularityCertificate"] = _regularity_certificate("wrong.seg", "m1.node.1")
    with pytest.raises(ValidationError, match="regularityCertificate segment targets must match actual segments"):
        M1ReferencePath.model_validate(mismatch)


def test_m2_orientation_only_requires_static_position_and_correspondence_targets():
    payload = _m2_payload()
    payload["positionSegments"] = []
    payload["positionSemantics"] = "static"
    payload["staticPosition"] = [0.0, 0.0, 0.0]
    payload["orientationSegments"] = [
        {
            "segmentId": "m2.axis.seg.1",
            "segmentType": "constant",
            "sigmaStart": 0.0,
            "sigmaEnd": 1.0,
            "lineage": [_lineage("stmt.axis.m2", 0, "AXIS/0,0,1")],
            "axis": [0.0, 0.0, 1.0],
        }
    ]
    payload["pathProgress"] = _path_progress("m2.axis.seg.1", progress_id="m2.axis.progress")
    payload["nodeEvents"] = [{"nodeId": "m2.axis.node.1", "sigma": 0.0, "eventType": "ordinary-junction", "rightSegmentId": "m2.axis.seg.1"}]
    payload["regularityCertificate"] = _regularity_certificate("m2.axis.seg.1", "m2.axis.node.1")
    payload["correspondence"]["targetReferencePathId"] = "m1.path.1"
    payload["correspondence"]["canonicalNodes"] = [
        {"pathRole": "source", "nodeId": "m2.axis.node.1", "sigma": 0.0, "segmentId": "m2.axis.seg.1"},
        {"pathRole": "target", "nodeId": "reference.node.1", "sigma": 0.0, "segmentId": "m1.seg.line.1"},
    ]
    payload["correspondence"]["allowedSourceIntervals"][0]["sourceSegmentId"] = "m2.axis.seg.1"
    payload["correspondence"]["selectedNodeMapping"] = [{"sourceNodeId": "m2.axis.node.1", "targetNodeId": "reference.node.1"}]
    payload["correspondence"]["intervals"][0]["sourceSegmentId"] = "m2.axis.seg.1"
    payload["correspondence"]["intervals"][0]["targetSegmentId"] = "m1.seg.line.1"

    candidate = M2CandidateTaskGeometry.model_validate(payload)
    assert candidate.static_position == (0.0, 0.0, 0.0)

    missing_static = copy.deepcopy(payload)
    missing_static.pop("staticPosition")
    with pytest.raises(ValidationError, match="orientation-only paths require staticPosition"):
        M2CandidateTaskGeometry.model_validate(missing_static)

    bad_source = copy.deepcopy(payload)
    bad_source["correspondence"]["canonicalNodes"][0]["segmentId"] = "missing.seg"
    with pytest.raises(ValidationError, match="canonical source nodes must target actual M2 segments"):
        M2CandidateTaskGeometry.model_validate(bad_source)


def test_contact_rule_taxonomy_selected_node_mapping_and_stock_state_chain_are_strict():
    payload = _m2_payload()
    payload["correspondence"]["selectedNodeMapping"].append(
        {"sourceNodeId": "m2.node.1", "targetNodeId": "reference.node.1"}
    )
    with pytest.raises(ValidationError, match="selectedNodeMapping must not contain duplicate pairs"):
        M2CandidateTaskGeometry.model_validate(payload)

    payload = _m2_payload()
    payload["correspondence"]["allowedSourceIntervals"][0]["allowedTargetIntervals"] = [[0.4, 0.8], [0.2, 0.3]]
    with pytest.raises(ValidationError, match="allowedTargetIntervals must be sorted and non-overlapping"):
        M2CandidateTaskGeometry.model_validate(payload)

    payload = _m2_payload()
    payload["collisionContext"]["contactPolicy"]["rules"][0]["leftCategory"] = "machine"
    payload["collisionContext"]["contactPolicy"]["rules"][0]["rightCategory"] = "stock"
    payload["collisionContext"]["contactPolicy"]["rules"][1]["leftCategory"] = "machine"
    payload["collisionContext"]["contactPolicy"]["rules"][1]["rightCategory"] = "fixture"
    payload["processStateTimeline"]["intervals"][0]["sigmaEnd"] = 0.5
    payload["processStateTimeline"]["intervals"][0]["outputStockState"] = {"stateId": "stock.output.mid", "contentId": "b" * 64}
    payload["processStateTimeline"]["intervals"].append(
        {
            "intervalId": "state.2",
            "sigmaStart": 0.5,
            "sigmaEnd": 1.0,
            "motionMode": "retract",
            "spindleState": "off",
            "toolComponentId": "tool.cutter.1",
            "coolantOn": False,
            "inputStockState": {"stateId": "wrong.chain", "contentId": "c" * 64},
            "outputStockState": {"stateId": "stock.output.2", "contentId": "d" * 64},
        }
    )
    with pytest.raises(ValidationError, match="adjacent process-state intervals must chain outputStockState to next inputStockState"):
        M2CandidateTaskGeometry.model_validate(payload)


def test_arc_and_helix_require_geometric_consistency():
    arc = copy.deepcopy(_m1_payload())
    arc["positionSegments"] = [
        {
            "segmentId": "arc.seg.1",
            "segmentType": "arc",
            "sigmaStart": 0.0,
            "sigmaEnd": 1.0,
            "lineage": [_lineage("stmt.arc.1", 0, "ARC/...")],
            "center": [0.0, 0.0, 0.0],
            "startPoint": [1.0, 0.0, 0.0],
            "endPoint": [0.0, 1.0, 0.0],
            "radius": 1.0,
            "normal": [0.0, 0.0, 1.0],
            "sweepRadians": -1.5707963267948966,
        }
    ]
    arc["pathProgress"] = _path_progress("arc.seg.1", progress_id="arc.progress.1")
    arc["regularityCertificate"] = _regularity_certificate("arc.seg.1", "m1.node.1")

    helix = copy.deepcopy(_m1_payload())
    helix["positionSegments"] = [
        {
            "segmentId": "helix.seg.1",
            "segmentType": "helix",
            "sigmaStart": 0.0,
            "sigmaEnd": 1.0,
            "lineage": [_lineage("stmt.helix.1", 0, "HELIX/...")],
            "center": [0.0, 0.0, 0.0],
            "axis": [0.0, 0.0, 1.0],
            "startPoint": [0.0, 0.0, 1.0],
            "radius": 1.0,
            "pitchPerTurn": 2.0,
            "turns": 1.0,
        }
    ]
    helix["pathProgress"] = _path_progress("helix.seg.1", progress_id="helix.progress.1")
    helix["regularityCertificate"] = _regularity_certificate("helix.seg.1", "m1.node.1")

    with pytest.raises(ValidationError, match="sweepRadians is inconsistent with the signed arc geometry"):
        M1ReferencePath.model_validate(arc)
    with pytest.raises(ValidationError, match="startPoint must be perpendicular to the helix axis"):
        M1ReferencePath.model_validate(helix)
