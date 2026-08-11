from __future__ import annotations

import pytest

from axiom.five_axis.f1_geometry import (
    UndefinedCorrespondenceError,
    build_monotone_minimax_correspondence,
    build_provenance_progress_correspondence,
)
from axiom.five_axis.f1_models import (
    CoordinateContext,
    LinePositionSegment,
    M1ReferencePath,
    MonotoneMinimaxPolicy,
    NumericTolerance,
    PathProgress,
    ProvenanceProgressPolicy,
    SegmentIntervalMapping,
    SourceLineage,
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


def _progress(progress_id: str = "progress-1", *, source_segment_id: str = "seg-1") -> PathProgress:
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


def _path(
    path_id: str,
    points: tuple[tuple[float, float, float], ...],
    *,
    progress_id: str = "progress-1",
    source_text: str = "GOTO/0,0,0",
) -> M1ReferencePath:
    segments = []
    for index, (left, right) in enumerate(zip(points, points[1:]), start=1):
        start = (index - 1) / (len(points) - 1)
        end = index / (len(points) - 1)
        segments.append(
            LinePositionSegment(
                segmentId=f"seg-{index}",
                segmentType="line",
                sigmaStart=start,
                sigmaEnd=end,
                lineage=_lineage(source_text),
                startPoint=left,
                endPoint=right,
            )
        )
    return M1ReferencePath(
        artifactType="five-axis.m1-reference-path",
        schemaVersion=1,
        referencePathId=path_id,
        coordinateContext=CoordinateContext(unit="mm", coordinateFrame="machine"),
        pathProgress=_progress(progress_id, source_segment_id="seg-1"),
        positionSemantics="continuous",
        positionSegments=tuple(segments),
        orientationSegments=(),
        nodeEvents=(),
    )


def test_provenance_progress_builds_exact_identity_certificate():
    actual = _path("actual", ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
    reference = _path("reference", ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
    policy = ProvenanceProgressPolicy(
        strategyId="five-axis.correspondence.provenance-progress@1",
        allowedSourceInterval=(0.0, 1.0),
        allowedTargetInterval=(0.0, 1.0),
        objective="preserve-source-lineage",
        deterministicTieBreak="lowest-source-segment-id",
        numericTolerance=NumericTolerance(absolute=0.0, unit="dimensionless"),
    )

    certificate = build_provenance_progress_correspondence(actual, reference, policy)

    assert certificate.source_geometry_id == actual.reference_path_id
    assert certificate.target_reference_path_id == reference.reference_path_id
    assert certificate.objective_domain == "continuous"
    assert certificate.evidence_level == "machine-replayable"
    assert certificate.primary_objective_lower == 0.0
    assert certificate.primary_objective_upper == 0.0
    assert [(interval.source_sigma_start, interval.target_sigma_start) for interval in certificate.intervals] == [(0.0, 0.0)]
    assert [(interval.source_sigma_end, interval.target_sigma_end) for interval in certificate.intervals] == [(1.0, 1.0)]


def test_monotone_minimax_prefers_earliest_target_sigma_and_stays_grid_scoped():
    actual = _path("actual", ((0.0, 0.0, 0.0), (1.0, 1.0, 0.0)))
    reference = _path(
        "reference",
        (
            (0.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
            (0.0, 0.0, 0.0),
            (1.0, 1.0, 0.0),
        ),
    )
    policy = MonotoneMinimaxPolicy(
        strategyId="five-axis.correspondence.monotone-minimax@1",
        allowedSourceInterval=(0.0, 1.0),
        allowedTargetInterval=(0.0, 1.0),
        objective="minimize-maximum-deviation",
        deterministicTieBreak="earliest-target-sigma",
        numericTolerance=NumericTolerance(absolute=1e-6, unit="mm"),
    )

    certificate = build_monotone_minimax_correspondence(actual, reference, policy, grid_size=9)
    mapped_sigmas = {
        mapping.source_node_id: next(node.sigma for node in certificate.canonical_nodes if node.node_id == mapping.target_node_id)
        for mapping in certificate.selected_node_mapping
    }

    assert certificate.objective_domain == "canonical-grid"
    assert certificate.evidence_level == "certificate-summary"
    assert mapped_sigmas["source-boundary-start"] == pytest.approx(0.0)
    assert mapped_sigmas["source-boundary-end"] == pytest.approx(1.0)
    assert certificate.primary_objective_lower == certificate.primary_objective_upper


def test_empty_allowed_interval_raises_undefined_correspondence():
    actual = _path("actual", ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
    reference = _path("reference", ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
    policy = MonotoneMinimaxPolicy(
        strategyId="five-axis.correspondence.monotone-minimax@1",
        allowedSourceInterval=(0.5, 0.5),
        allowedTargetInterval=(0.0, 1.0),
        objective="minimize-maximum-deviation",
        deterministicTieBreak="earliest-target-sigma",
        numericTolerance=NumericTolerance(absolute=1e-6, unit="mm"),
    )

    with pytest.raises(UndefinedCorrespondenceError, match="positive extent"):
        build_monotone_minimax_correspondence(actual, reference, policy)


def test_same_inputs_produce_deterministic_monotone_minimax_certificate():
    actual = _path("actual", ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)))
    reference = _path("reference", ((0.0, 0.0, 0.0), (1.0, 0.2, 0.0), (2.0, 0.0, 0.0)))
    policy = MonotoneMinimaxPolicy(
        strategyId="five-axis.correspondence.monotone-minimax@1",
        allowedSourceInterval=(0.0, 1.0),
        allowedTargetInterval=(0.0, 1.0),
        objective="minimize-maximum-deviation",
        deterministicTieBreak="earliest-target-sigma",
        numericTolerance=NumericTolerance(absolute=1e-6, unit="mm"),
    )

    first = build_monotone_minimax_correspondence(actual, reference, policy).model_dump(mode="json", by_alias=True)
    second = build_monotone_minimax_correspondence(actual, reference, policy).model_dump(mode="json", by_alias=True)

    assert first == second
