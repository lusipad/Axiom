from __future__ import annotations

import math

import pytest

from axiom.five_axis.f1_geometry import (
    GeometryEvaluationError,
    UndefinedCorrespondenceError,
    apply_correspondence,
    compute_actual_to_reference_continuous_error_certificate,
    evaluate_position,
    evaluate_tool_axis,
)
from axiom.five_axis.f1_models import (
    ArcPositionSegment,
    BezierPositionSegment,
    BSplinePositionSegment,
    CanonicalNode,
    ConstantOrientationSegment,
    CoordinateContext,
    CorrespondenceCertificate,
    CorrespondenceInterval,
    HelixPositionSegment,
    LinePositionSegment,
    M1ReferencePath,
    NumericTolerance,
    PathProgress,
    ProvenanceProgressPolicy,
    SegmentIntervalMapping,
    SelectedNodeMapping,
    SourceLineage,
    SourceSegmentAllowedTargetIntervals,
    SlerpOrientationSegment,
)


def _lineage(source_text: str = "GOTO/0,0,0") -> tuple[SourceLineage, ...]:
    return (
        SourceLineage(
            statementId="statement-0001",
            statementIndex=0,
            line=1,
            column=1,
            sourceText=source_text,
        ),
    )


def _progress(progress_id: str = "progress-1", *, source_segment_id: str) -> PathProgress:
    return PathProgress(
        progressId=progress_id,
        schemaVersion=1,
        mappings=(
            SegmentIntervalMapping(
                mappingId="map-1",
                sourceSegmentId=source_segment_id,
                sourceLocalStart=0.0,
                sourceLocalEnd=1.0,
                sigmaStart=0.0,
                sigmaEnd=1.0,
                degenerateKind="none",
            ),
        ),
    )


def _continuous_path(
    *,
    path_id: str,
    position_segments,
    orientation_segments,
    progress_id: str = "progress-1",
) -> M1ReferencePath:
    active_segment_id = (position_segments or orientation_segments)[0].segment_id
    return M1ReferencePath(
        artifactType="five-axis.m1-reference-path",
        schemaVersion=1,
        referencePathId=path_id,
        coordinateContext=CoordinateContext(unit="mm", coordinateFrame="machine"),
        pathProgress=_progress(progress_id, source_segment_id=active_segment_id),
        positionSemantics="continuous",
        positionSegments=position_segments,
        orientationSegments=orientation_segments,
        nodeEvents=(),
    )


def _orientation_only_path(
    *,
    path_id: str,
    static_position: tuple[float, float, float],
    orientation_segments,
    progress_id: str = "progress-1",
) -> M1ReferencePath:
    active_segment_id = orientation_segments[0].segment_id
    return M1ReferencePath(
        artifactType="five-axis.m1-reference-path",
        schemaVersion=1,
        referencePathId=path_id,
        coordinateContext=CoordinateContext(unit="mm", coordinateFrame="machine"),
        pathProgress=_progress(progress_id, source_segment_id=active_segment_id),
        positionSemantics="static",
        staticPosition=static_position,
        positionSegments=(),
        orientationSegments=orientation_segments,
        nodeEvents=(),
    )


def _identity_certificate(actual: M1ReferencePath, reference: M1ReferencePath) -> CorrespondenceCertificate:
    actual_segment_id = (actual.position_segments or actual.orientation_segments)[0].segment_id
    reference_segment_id = (reference.position_segments or reference.orientation_segments)[0].segment_id
    policy = ProvenanceProgressPolicy(
        strategyId="five-axis.correspondence.provenance-progress@1",
        allowedSourceInterval=(0.0, 1.0),
        allowedTargetInterval=(0.0, 1.0),
        objective="preserve-source-lineage",
        deterministicTieBreak="lowest-source-segment-id",
        numericTolerance=NumericTolerance(absolute=0.0, unit="dimensionless"),
    )
    return CorrespondenceCertificate(
        certificateId="identity-cert",
        sourceGeometryId=actual.reference_path_id,
        targetReferencePathId=reference.reference_path_id,
        policy=policy,
        canonicalNodes=(
            CanonicalNode(pathRole="source", nodeId="source-boundary-start", sigma=0.0, segmentId=actual_segment_id),
            CanonicalNode(pathRole="source", nodeId="source-boundary-end", sigma=1.0, segmentId=actual_segment_id),
            CanonicalNode(pathRole="target", nodeId="target-boundary-start", sigma=0.0, segmentId=reference_segment_id),
            CanonicalNode(pathRole="target", nodeId="target-boundary-end", sigma=1.0, segmentId=reference_segment_id),
        ),
        allowedSourceIntervals=(
            SourceSegmentAllowedTargetIntervals(
                sourceSegmentId=actual_segment_id,
                allowedTargetIntervals=((0.0, 1.0),),
            ),
        ),
        selectedNodeMapping=(
            SelectedNodeMapping(sourceNodeId="source-boundary-start", targetNodeId="target-boundary-start"),
            SelectedNodeMapping(sourceNodeId="source-boundary-end", targetNodeId="target-boundary-end"),
        ),
        intervals=(
            CorrespondenceInterval(
                intervalId="interval-1",
                sourceSigmaStart=0.0,
                sourceSigmaEnd=1.0,
                targetSigmaStart=0.0,
                targetSigmaEnd=1.0,
                sourceSegmentId=actual_segment_id,
                targetSegmentId=reference_segment_id,
                correspondenceStatus="matched",
            ),
        ),
        primaryObjectiveLower=0.0,
        primaryObjectiveUpper=0.0,
        objectiveDomain="continuous",
        tieBreakObjective="identity-sigma",
        numericTolerance=NumericTolerance(absolute=0.0, unit="dimensionless"),
        solverVersion="test-solver@1",
        evidenceLevel="machine-replayable",
    )


def test_line_zero_error_and_constant_offset_are_separated_from_orientation():
    reference = _continuous_path(
        path_id="reference-line",
        position_segments=(
            LinePositionSegment(
                segmentId="ref-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 0.0, 0.0),
                endPoint=(10.0, 0.0, 0.0),
            ),
        ),
        orientation_segments=(
            ConstantOrientationSegment(
                segmentId="ref-ori-1",
                segmentType="constant",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                axis=(0.0, 0.0, 1.0),
            ),
        ),
    )
    identical_actual = _continuous_path(
        path_id="actual-identical-line",
        position_segments=(
            LinePositionSegment(
                segmentId="act-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 0.0, 0.0),
                endPoint=(10.0, 0.0, 0.0),
            ),
        ),
        orientation_segments=(
            ConstantOrientationSegment(
                segmentId="act-ori-1",
                segmentType="constant",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                axis=(0.0, 0.0, 1.0),
            ),
        ),
    )
    shifted_actual = _continuous_path(
        path_id="actual-offset-line",
        position_segments=(
            LinePositionSegment(
                segmentId="act-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 2.0, 0.0),
                endPoint=(10.0, 2.0, 0.0),
            ),
        ),
        orientation_segments=identical_actual.orientation_segments,
    )

    zero = compute_actual_to_reference_continuous_error_certificate(
        identical_actual,
        reference,
        _identity_certificate(identical_actual, reference),
    )
    shifted = compute_actual_to_reference_continuous_error_certificate(
        shifted_actual,
        reference,
        _identity_certificate(shifted_actual, reference),
    )

    assert zero.position is not None and zero.position.level == "Exact"
    assert zero.position.bound_semantics == "rigorous-continuous"
    assert zero.position.upper == pytest.approx(0.0)
    assert shifted.position is not None and shifted.position.level in {"Certified", "Validated"}
    assert shifted.position.bound_semantics == "rigorous-continuous"
    assert shifted.position.lower == pytest.approx(2.0, abs=1e-9)
    assert shifted.position.upper <= 2.001
    assert shifted.tool_axis_angle is not None and shifted.tool_axis_angle.upper == pytest.approx(0.0)


def test_position_can_pass_while_orientation_fails_and_inverse():
    reference = _continuous_path(
        path_id="reference-pose",
        position_segments=(
            LinePositionSegment(
                segmentId="ref-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 0.0, 0.0),
                endPoint=(1.0, 0.0, 0.0),
            ),
        ),
        orientation_segments=(
            ConstantOrientationSegment(
                segmentId="ref-ori-1",
                segmentType="constant",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                axis=(0.0, 0.0, 1.0),
            ),
        ),
    )
    same_position_bad_orientation = _continuous_path(
        path_id="actual-orientation-fail",
        position_segments=(
            LinePositionSegment(
                segmentId="act-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 0.0, 0.0),
                endPoint=(1.0, 0.0, 0.0),
            ),
        ),
        orientation_segments=(
            ConstantOrientationSegment(
                segmentId="act-ori-1",
                segmentType="constant",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                axis=(0.0, 1.0, 0.0),
            ),
        ),
    )
    same_orientation_bad_position = _continuous_path(
        path_id="actual-position-fail",
        position_segments=(
            LinePositionSegment(
                segmentId="act-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 0.5, 0.0),
                endPoint=(1.0, 0.5, 0.0),
            ),
        ),
        orientation_segments=(
            ConstantOrientationSegment(
                segmentId="act-ori-1",
                segmentType="constant",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                axis=(0.0, 0.0, 1.0),
            ),
        ),
    )

    orientation_fail = compute_actual_to_reference_continuous_error_certificate(
        same_position_bad_orientation,
        reference,
        _identity_certificate(same_position_bad_orientation, reference),
    )
    position_fail = compute_actual_to_reference_continuous_error_certificate(
        same_orientation_bad_position,
        reference,
        _identity_certificate(same_orientation_bad_position, reference),
    )

    assert orientation_fail.position is not None and orientation_fail.position.upper == pytest.approx(0.0)
    assert orientation_fail.tool_axis_angle is not None
    assert orientation_fail.tool_axis_angle.upper == pytest.approx(math.pi / 2.0, abs=1e-6)
    assert position_fail.tool_axis_angle is not None and position_fail.tool_axis_angle.upper == pytest.approx(0.0)
    assert position_fail.position is not None and position_fail.position.lower == pytest.approx(0.5, abs=1e-9)
    assert position_fail.position.upper <= 0.501


def test_bezier_can_violate_midspan_while_endpoints_still_match():
    reference = _continuous_path(
        path_id="reference-line",
        position_segments=(
            LinePositionSegment(
                segmentId="ref-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 0.0, 0.0),
                endPoint=(1.0, 0.0, 0.0),
            ),
        ),
        orientation_segments=(),
    )
    actual = _continuous_path(
        path_id="actual-bezier",
        position_segments=(
            BezierPositionSegment(
                segmentId="act-seg-1",
                segmentType="bezier",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                controlPoints=((0.0, 0.0, 0.0), (0.25, 0.6, 0.0), (0.75, 0.6, 0.0), (1.0, 0.0, 0.0)),
            ),
        ),
        orientation_segments=(),
    )

    error = compute_actual_to_reference_continuous_error_certificate(
        actual,
        reference,
        _identity_certificate(actual, reference),
    )

    assert error.position is not None
    assert error.position.upper > 0.4
    assert error.position.lower > 0.3


def test_slerp_clamps_dot_product_and_returns_finite_unit_axis():
    path = _orientation_only_path(
        path_id="slerp-path",
        static_position=(3.0, 4.0, 5.0),
        orientation_segments=(
            SlerpOrientationSegment(
                segmentId="ori-1",
                segmentType="slerp",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startAxis=(0.0, 0.0, 1.0),
                endAxis=(0.0, 0.0, 1.0),
            ),
        ),
    )

    axis = evaluate_tool_axis(path, 0.5)
    assert evaluate_position(path, 0.5) == pytest.approx((3.0, 4.0, 5.0))
    assert all(math.isfinite(value) for value in axis)
    assert math.sqrt(sum(value * value for value in axis)) == pytest.approx(1.0, abs=1e-12)


def test_arc_and_helix_respect_declared_endpoints():
    arc_path = _continuous_path(
        path_id="arc-path",
        position_segments=(
            ArcPositionSegment(
                segmentId="seg-1",
                segmentType="arc",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                center=(0.0, 0.0, 0.0),
                startPoint=(1.0, 0.0, 0.0),
                endPoint=(0.0, 1.0, 0.0),
                radius=1.0,
                normal=(0.0, 0.0, 1.0),
                sweepRadians=math.pi / 2.0,
            ),
        ),
        orientation_segments=(),
    )
    helix_path = _continuous_path(
        path_id="helix-path",
        position_segments=(
            HelixPositionSegment(
                segmentId="seg-1",
                segmentType="helix",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                center=(0.0, 0.0, 0.0),
                axis=(0.0, 0.0, 1.0),
                startPoint=(1.0, 0.0, 0.0),
                radius=1.0,
                pitchPerTurn=2.0,
                turns=1.0,
            ),
        ),
        orientation_segments=(),
    )

    assert evaluate_position(arc_path, 0.0) == pytest.approx((1.0, 0.0, 0.0))
    assert evaluate_position(arc_path, 1.0) == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)
    assert evaluate_position(helix_path, 0.0) == pytest.approx((1.0, 0.0, 0.0))
    assert evaluate_position(helix_path, 1.0) == pytest.approx((1.0, 0.0, 2.0), abs=1e-9)


def test_spline_rejects_out_of_domain_evaluation():
    path = _continuous_path(
        path_id="spline-path",
        position_segments=(
            BSplinePositionSegment(
                segmentId="seg-1",
                segmentType="bspline",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                degree=2,
                controlPoints=((0.0, 0.0, 0.0), (0.5, 0.5, 0.0), (1.0, 0.0, 0.0)),
                knots=(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
            ),
        ),
        orientation_segments=(),
    )

    with pytest.raises(GeometryEvaluationError, match="within \\[0, 1\\]"):
        evaluate_position(path, -1e-6)
    with pytest.raises(GeometryEvaluationError, match="within \\[0, 1\\]"):
        evaluate_position(path, 1.0 + 1e-6)


def test_antipodal_runtime_rejection_does_not_pick_arbitrary_great_circle():
    invalid = SlerpOrientationSegment.model_construct(
        segment_id="ori-1",
        segment_type="slerp",
        sigma_start=0.0,
        sigma_end=1.0,
        lineage=_lineage(),
        start_axis=(0.0, 0.0, 1.0),
        end_axis=(0.0, 0.0, -1.0),
        antipodal_policy="reject",
    )
    path = M1ReferencePath.model_construct(
        artifact_type="five-axis.m1-reference-path",
        schema_version=1,
        reference_path_id="invalid-antipodal",
        coordinate_context=CoordinateContext(unit="mm", coordinateFrame="machine"),
        path_progress=_progress(source_segment_id="ori-1"),
        position_semantics="static",
        static_position=(0.0, 0.0, 0.0),
        position_segments=(),
        orientation_segments=(invalid,),
        node_events=(),
        regularity_certificate=None,
        provenance=(),
    )

    with pytest.raises(GeometryEvaluationError, match="antipodal"):
        evaluate_tool_axis(path, 0.5)


def test_wrong_certificate_ids_raise_undefined_correspondence():
    reference = _continuous_path(
        path_id="reference-line",
        position_segments=(
            LinePositionSegment(
                segmentId="ref-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 0.0, 0.0),
                endPoint=(1.0, 0.0, 0.0),
            ),
        ),
        orientation_segments=(),
    )
    actual = _continuous_path(
        path_id="actual-line",
        position_segments=(
            LinePositionSegment(
                segmentId="act-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 0.0, 0.0),
                endPoint=(1.0, 0.0, 0.0),
            ),
        ),
        orientation_segments=(),
    )
    wrong = _identity_certificate(actual, reference).model_copy(
        update={"source_geometry_id": "other.geometry"},
    )

    with pytest.raises(UndefinedCorrespondenceError, match="sourceGeometryId"):
        compute_actual_to_reference_continuous_error_certificate(actual, reference, wrong)


def test_static_position_differences_are_measured_and_not_misclassified_as_exact():
    reference = _orientation_only_path(
        path_id="reference-static",
        static_position=(0.0, 0.0, 0.0),
        orientation_segments=(
            ConstantOrientationSegment(
                segmentId="ref-ori-1",
                segmentType="constant",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                axis=(0.0, 0.0, 1.0),
            ),
        ),
    )
    actual = _orientation_only_path(
        path_id="actual-static",
        static_position=(0.0, 3.0, 4.0),
        orientation_segments=(
            ConstantOrientationSegment(
                segmentId="act-ori-1",
                segmentType="constant",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                axis=(0.0, 0.0, 1.0),
            ),
        ),
    )

    error = compute_actual_to_reference_continuous_error_certificate(actual, reference, _identity_certificate(actual, reference))

    assert error.position is not None
    assert error.position.level == "Certified"
    assert error.position.bound_semantics == "rigorous-continuous"
    assert error.position.lower == pytest.approx(5.0)
    assert error.position.upper == pytest.approx(5.0)
    assert error.tool_axis_angle is not None and error.tool_axis_angle.level == "Exact"


def test_nurbs_validated_sampling_uses_observed_sample_semantics():
    reference = _continuous_path(
        path_id="reference-nurbs",
        position_segments=(
            BSplinePositionSegment(
                segmentId="ref-seg-1",
                segmentType="bspline",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                degree=2,
                controlPoints=((0.0, 0.0, 0.0), (0.5, 0.4, 0.0), (1.0, 0.0, 0.0)),
                knots=(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
                weights=(1.0, 1.0, 1.0),
            ),
        ),
        orientation_segments=(),
    )
    actual = _continuous_path(
        path_id="actual-nurbs",
        position_segments=(
            BSplinePositionSegment(
                segmentId="act-seg-1",
                segmentType="bspline",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                degree=2,
                controlPoints=((0.0, 0.0, 0.0), (0.5, 0.6, 0.0), (1.0, 0.0, 0.0)),
                knots=(0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
                weights=(1.0, 1.0, 1.0),
            ),
        ),
        orientation_segments=(),
    )

    error = compute_actual_to_reference_continuous_error_certificate(actual, reference, _identity_certificate(actual, reference))

    assert error.position is not None
    assert error.position.level == "Validated"
    assert error.position.bound_semantics == "observed-samples"
    assert error.position.upper >= error.position.lower


def test_apply_correspondence_is_piecewise_linear():
    reference = _continuous_path(
        path_id="reference-line",
        position_segments=(
            LinePositionSegment(
                segmentId="ref-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 0.0, 0.0),
                endPoint=(1.0, 0.0, 0.0),
            ),
        ),
        orientation_segments=(),
    )
    actual = _continuous_path(
        path_id="actual-line",
        position_segments=(
            LinePositionSegment(
                segmentId="act-seg-1",
                segmentType="line",
                sigmaStart=0.0,
                sigmaEnd=1.0,
                lineage=_lineage(),
                startPoint=(0.0, 0.0, 0.0),
                endPoint=(1.0, 0.0, 0.0),
            ),
        ),
        orientation_segments=(),
    )

    assert apply_correspondence(_identity_certificate(actual, reference), 0.25) == pytest.approx(0.25)
