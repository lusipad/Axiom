from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

import pytest

import axiom.five_axis.f1_collision as f1_collision
from axiom.five_axis.f1_models import (
    AllowedRemoval,
    AxisAlignedBoundingBox,
    CollisionContext,
    ConstantOrientationSegment,
    ContactPolicy,
    ContactRule,
    CoordinateContext,
    CorrespondenceCertificate,
    CorrespondenceInterval,
    LinePositionSegment,
    M2CandidateTaskGeometry,
    NumericTolerance,
    PathProgress,
    ProcessStateInterval,
    ProcessStateTimeline,
    ProvenanceProgressPolicy,
    SegmentIntervalMapping,
    SelectedNodeMapping,
    SourceLineage,
    SourceSegmentAllowedTargetIntervals,
    StockFixtureAABB,
    StockStateRef,
    StockUpdatePolicy,
    FailureStateSemantics,
    ToleranceBinding,
    ToolComponent,
    CanonicalNode,
    SlerpOrientationSegment,
)


def _lineage() -> SourceLineage:
    return SourceLineage(
        statement_id="statement-1",
        statement_index=0,
        line=1,
        column=1,
        source_text="GOTO/...",
        source_path="fixture.cl",
    )


def _box(min_corner: tuple[float, float, float], max_corner: tuple[float, float, float]) -> AxisAlignedBoundingBox:
    return AxisAlignedBoundingBox(min_corner=min_corner, max_corner=max_corner)


def _tool_component(
    component_id: str,
    component_kind: str,
    *,
    axis: tuple[float, float, float] = (0.0, 0.0, 1.0),
    radius: float = 0.15,
    axis_start_offset: float = -0.1,
    axis_end_offset: float = 0.1,
    aabb_min: tuple[float, float, float] = (-0.1, -0.1, -0.1),
    aabb_max: tuple[float, float, float] = (0.1, 0.1, 0.1),
) -> ToolComponent:
    payload: dict[str, object] = {
        "component_id": component_id,
        "component_kind": component_kind,
    }
    fields = ToolComponent.model_fields
    if "tool_axis" in fields:
        payload["tool_axis"] = axis
    if "radius" in fields and "axis_start_offset" in fields and "axis_end_offset" in fields:
        if "shape_type" in fields:
            payload["shape_type"] = "sphere" if abs(axis_end_offset - axis_start_offset) <= 1e-12 else "capsule"
        payload["radius"] = radius
        payload["axis_start_offset"] = axis_start_offset
        payload["axis_end_offset"] = axis_end_offset
        return ToolComponent(**payload)
    payload["aabb"] = _box(aabb_min, aabb_max)
    return ToolComponent(**payload)


def _path_progress(segment_id: str) -> PathProgress:
    return PathProgress(
        progress_id="progress-1",
        schema_version=1,
        mappings=(
            SegmentIntervalMapping(
                mapping_id="mapping-1",
                source_segment_id=segment_id,
                source_local_start=0.0,
                source_local_end=1.0,
                sigma_start=0.0,
                sigma_end=1.0,
                degenerate_kind="none",
            ),
        ),
    )


def _correspondence(segment_id: str) -> CorrespondenceCertificate:
    return CorrespondenceCertificate(
        certificate_id="corr-1",
        source_geometry_id="candidate-1",
        target_reference_path_id="source-path",
        policy=ProvenanceProgressPolicy(
            strategy_id="five-axis.correspondence.provenance-progress@1",
            allowed_source_interval=(0.0, 1.0),
            allowed_target_interval=(0.0, 1.0),
            objective="preserve-source-lineage",
            deterministic_tie_break="lowest-source-segment-id",
            numeric_tolerance=NumericTolerance(absolute=1e-6, unit="dimensionless"),
        ),
        canonical_nodes=(
            CanonicalNode(path_role="source", node_id="source-node", sigma=0.0, segment_id=segment_id),
            CanonicalNode(path_role="target", node_id="target-node", sigma=0.0, segment_id=segment_id),
        ),
        allowed_source_intervals=(
            SourceSegmentAllowedTargetIntervals(
                source_segment_id=segment_id,
                allowed_target_intervals=((0.0, 1.0),),
            ),
        ),
        selected_node_mapping=(SelectedNodeMapping(source_node_id="source-node", target_node_id="target-node"),),
        intervals=(
            CorrespondenceInterval(
                interval_id="corr-interval-1",
                source_sigma_start=0.0,
                source_sigma_end=1.0,
                target_sigma_start=0.0,
                target_sigma_end=1.0,
                source_segment_id=segment_id,
                target_segment_id=segment_id,
                correspondence_status="matched",
            ),
        ),
        primary_objective_lower=0.0,
        primary_objective_upper=0.0,
        objective_domain="continuous",
        tie_break_objective="stable",
        numeric_tolerance=NumericTolerance(absolute=1e-6, unit="dimensionless"),
        solver_version="test",
        evidence_level="machine-replayable",
    )


def _position_segment(
    *,
    segment_id: str = "line-1",
    start: tuple[float, float, float] = (-0.8, 0.0, 0.0),
    end: tuple[float, float, float] = (0.8, 0.0, 0.0),
) -> LinePositionSegment:
    return LinePositionSegment(
        segment_id=segment_id,
        segment_type="line",
        sigma_start=0.0,
        sigma_end=1.0,
        start_point=start,
        end_point=end,
        lineage=(_lineage(),),
    )


def _constant_orientation(segment_id: str = "orient-1") -> ConstantOrientationSegment:
    return ConstantOrientationSegment(
        segment_id=segment_id,
        segment_type="constant",
        sigma_start=0.0,
        sigma_end=1.0,
        axis=(0.0, 0.0, 1.0),
        lineage=(_lineage(),),
    )


def _slerp_orientation(segment_id: str = "orient-1") -> SlerpOrientationSegment:
    return SlerpOrientationSegment(
        segment_id=segment_id,
        segment_type="slerp",
        sigma_start=0.0,
        sigma_end=1.0,
        start_axis=(0.0, 0.0, 1.0),
        end_axis=(1.0, 0.0, 0.0),
        lineage=(_lineage(),),
    )


def _collision_context(
    *,
    tool_components: Sequence[ToolComponent],
    stock_box: AxisAlignedBoundingBox,
    fixture_box: AxisAlignedBoundingBox | None = None,
    allowed_removal: Sequence[AllowedRemoval] | None = None,
) -> CollisionContext:
    stock_fixtures = [
        StockFixtureAABB(stock_fixture_id="stock-1", category="stock", aabb=stock_box),
    ]
    if fixture_box is not None:
        stock_fixtures.append(StockFixtureAABB(stock_fixture_id="fixture-1", category="fixture", aabb=fixture_box))
    component_kinds = {component.component_kind for component in tool_components}
    rules: list[ContactRule] = []
    if "cutter" in component_kinds:
        rules.append(ContactRule(rule_id="cutter-stock", left_category="cutter", right_category="stock", contact_policy="allowed"))
        if fixture_box is not None:
            rules.append(
                ContactRule(rule_id="cutter-fixture", left_category="cutter", right_category="fixture", contact_policy="forbidden")
            )
    if "shaft" in component_kinds:
        rules.append(ContactRule(rule_id="shaft-stock", left_category="shaft", right_category="stock", contact_policy="forbidden"))
        if fixture_box is not None:
            rules.append(
                ContactRule(rule_id="shaft-fixture", left_category="shaft", right_category="fixture", contact_policy="forbidden")
            )
    if "holder" in component_kinds:
        rules.append(ContactRule(rule_id="holder-stock", left_category="holder", right_category="stock", contact_policy="forbidden"))
        if fixture_box is not None:
            rules.append(
                ContactRule(rule_id="holder-fixture", left_category="holder", right_category="fixture", contact_policy="forbidden")
            )
    return CollisionContext(
        context_id="ctx-1",
        tool_components=tuple(tool_components),
        stock_fixtures=tuple(stock_fixtures),
        allowed_removal=tuple(allowed_removal or (_allowed_removal(tool_component_id=tool_components[0].component_id, region=stock_box),)),
        minimum_clearance=NumericTolerance(absolute=0.0, unit="mm"),
        solver_tolerance=NumericTolerance(absolute=1e-6, unit="mm"),
        envelope_tolerance=NumericTolerance(absolute=1e-6, unit="mm"),
        contact_policy=ContactPolicy(policy_id="five-axis.contact-policy.explicit@1", rules=tuple(rules)),
    )


def _interval(
    *,
    interval_id: str,
    sigma_start: float,
    sigma_end: float,
    input_state_id: str = "state-in",
    output_state_id: str | None = "state-out",
    input_content_id: str = "0" * 64,
    output_content_id: str | None = None,
    tool_component_id: str | None = "cutter-1",
    motion_mode: str = "cut",
) -> ProcessStateInterval:
    return ProcessStateInterval(
        interval_id=interval_id,
        sigma_start=sigma_start,
        sigma_end=sigma_end,
        motion_mode=motion_mode,
        spindle_state="cw",
        tool_component_id=tool_component_id,
        coolant_on=False,
        input_stock_state=StockStateRef(state_id=input_state_id, content_id=input_content_id),
        output_stock_state=None
        if output_state_id is None
        else StockStateRef(state_id=output_state_id, content_id=output_content_id or ("1" * 64)),
    )


def _timeline(policy_id: str, intervals: Sequence[ProcessStateInterval]) -> ProcessStateTimeline:
    return ProcessStateTimeline(
        timeline_id="timeline-1",
        stock_update_policy=StockUpdatePolicy(policy_id=policy_id),
        failure_state_semantics=FailureStateSemantics(
            policy_id="five-axis.process-state.failure-terminal@1",
            failed_state_meaning="last-input-state-persists",
        ),
        intervals=tuple(intervals),
    )


def _task(
    *,
    collision_context: CollisionContext,
    intervals: Sequence[ProcessStateInterval],
    orientation: ConstantOrientationSegment | SlerpOrientationSegment | None = None,
    position: LinePositionSegment | None = None,
    policy_id: str = "five-axis.stock-update.explicit-snapshot@1",
) -> M2CandidateTaskGeometry:
    position_segment = position or _position_segment()
    orientation_segment = orientation or _constant_orientation()
    return M2CandidateTaskGeometry(
        artifact_type="five-axis.m2-candidate-task-geometry",
        schema_version=1,
        candidate_geometry_id="candidate-1",
        source_reference_path_id="source-path",
        coordinate_context=CoordinateContext(unit="MM", coordinate_frame="workpiece"),
        path_progress=_path_progress(position_segment.segment_id),
        position_segments=(position_segment,),
        orientation_segments=(orientation_segment,),
        node_events=tuple(),
        tolerances=(
            ToleranceBinding(
                tolerance_id="tol-1",
                target="collision-clearance",
                tolerance=NumericTolerance(absolute=1e-6, unit="mm"),
            ),
        ),
        correspondence=_correspondence(position_segment.segment_id),
        collision_context=collision_context,
        process_state_timeline=_timeline(policy_id, intervals),
    )


def _allowed_removal(tool_component_id: str = "cutter-1", region: AxisAlignedBoundingBox | None = None) -> AllowedRemoval:
    return AllowedRemoval(
        removal_id=f"removal-{tool_component_id}",
        tool_component_id=tool_component_id,
        stock_fixture_id="stock-1",
        region=region,
    )


def _snapshot_hash(stock_fixtures: Mapping[str, Sequence[AxisAlignedBoundingBox]]) -> str:
    payload = {
        stock_fixture_id: [
            {"minCorner": list(box.min_corner), "maxCorner": list(box.max_corner)}
            for box in boxes
        ]
        for stock_fixture_id, boxes in sorted(stock_fixtures.items())
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _snapshot_payload(
    stock_fixtures: Mapping[str, Sequence[AxisAlignedBoundingBox]],
    *,
    content_id: str | None = None,
) -> dict[str, object]:
    actual_content_id = _snapshot_hash(stock_fixtures)
    return {
        "contentId": content_id or actual_content_id,
        "stockFixtures": stock_fixtures,
    }


def _single_stock_snapshot(stock_box: AxisAlignedBoundingBox, *, content_id: str | None = None) -> tuple[dict[str, object], str]:
    stock_fixtures = {"stock-1": (stock_box,)}
    actual_content_id = _snapshot_hash(stock_fixtures)
    return _snapshot_payload(stock_fixtures, content_id=content_id), actual_content_id


def _seed_state(
    stock_box: AxisAlignedBoundingBox,
    *,
    state_id: str = "state-in",
    content_id: str | None = None,
) -> tuple[Mapping[str, Mapping[str, object]], str]:
    snapshot, actual_content_id = _single_stock_snapshot(stock_box, content_id=content_id)
    return {state_id: snapshot}, actual_content_id


def _seed_explicit_pair(
    input_box: AxisAlignedBoundingBox,
    *,
    input_state_id: str = "state-in",
    output_state_id: str = "state-out",
    output_box: AxisAlignedBoundingBox | None = None,
    input_content_id: str | None = None,
    output_content_id: str | None = None,
) -> tuple[Mapping[str, Mapping[str, object]], str, str]:
    seeded_input, input_hash = _seed_state(input_box, state_id=input_state_id, content_id=input_content_id)
    output_snapshot, output_hash = _single_stock_snapshot(output_box or input_box, content_id=output_content_id)
    return {
        **seeded_input,
        output_state_id: output_snapshot,
    }, input_hash, output_hash


def test_allowed_cutting_is_not_reported_as_collision():
    stock_box = _box((-0.4, -0.4, -0.2), (0.4, 0.4, 0.2))
    seeded, stock_hash, output_hash = _seed_explicit_pair(stock_box)
    cutter = _tool_component("cutter-1", "cutter")
    holder = _tool_component(
        "holder-1",
        "holder",
        radius=0.08,
        axis_start_offset=0.4,
        axis_end_offset=0.7,
        aabb_min=(-0.08, -0.08, 0.4),
        aabb_max=(0.08, 0.08, 0.7),
    )
    context = _collision_context(
        tool_components=(cutter, holder),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=stock_hash,
                output_content_id=output_hash,
            ),
        ),
    )

    result = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded)

    assert result.collision_free is True
    assert result.overcut_free is True
    assert result.evidence_level == "Certified"
    assert result.reason_code == "CollisionCertified"
    assert all(finding.finding_kind != "forbidden-contact" for finding in result.findings)
    assert all(finding.finding_kind != "overcut" for finding in result.findings)
    assert any(finding.finding_kind == "allowed-removal-contact" for finding in result.findings)


def test_holder_fixture_interference_is_forbidden():
    stock_box = _box((2.0, 2.0, 2.0), (3.0, 3.0, 3.0))
    fixture_box = _box((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))
    seeded, stock_hash, output_hash = _seed_explicit_pair(stock_box)
    cutter = _tool_component("cutter-1", "cutter")
    holder = _tool_component(
        "holder-1",
        "holder",
        radius=0.18,
        axis_start_offset=-0.1,
        axis_end_offset=0.1,
        aabb_min=(-0.18, -0.18, -0.1),
        aabb_max=(0.18, 0.18, 0.1),
    )
    context = _collision_context(
        tool_components=(cutter, holder),
        stock_box=stock_box,
        fixture_box=fixture_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=stock_hash,
                output_content_id=output_hash,
            ),
        ),
    )

    result = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded)

    assert result.collision_free is False
    assert result.reason_code == "ForbiddenContact"
    assert any(
        finding.finding_kind == "forbidden-contact" and finding.stock_fixture_id == "fixture-1"
        for finding in result.findings
    )


def test_nominal_overcut_is_reported():
    stock_box = _box((-0.5, -0.5, -0.2), (0.5, 0.5, 0.2))
    allowed_box = _box((-0.1, -0.5, -0.2), (0.1, 0.5, 0.2))
    seeded, stock_hash, output_hash = _seed_explicit_pair(stock_box)
    cutter = _tool_component("cutter-1", "cutter")
    context = _collision_context(
        tool_components=(cutter,),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(region=allowed_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=stock_hash,
                output_content_id=output_hash,
            ),
        ),
    )

    result = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded)

    assert result.collision_free is False
    assert result.overcut_free is False
    assert any(finding.finding_kind == "overcut" for finding in result.findings)


def test_shaft_stock_contact_is_forbidden():
    stock_box = _box((-0.2, -0.2, -0.2), (0.2, 0.2, 0.2))
    seeded, stock_hash, output_hash = _seed_explicit_pair(stock_box)
    shaft = _tool_component(
        "shaft-1",
        "shaft",
        radius=0.12,
        axis_start_offset=-0.05,
        axis_end_offset=0.05,
    )
    context = _collision_context(tool_components=(shaft,), stock_box=stock_box)
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=stock_hash,
                output_content_id=output_hash,
                tool_component_id="shaft-1",
            ),
        ),
        position=_position_segment(start=(0.0, 0.0, 0.0), end=(0.0, 0.0, 0.0)),
    )

    result = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded)

    assert result.collision_free is False
    assert any(
        finding.finding_kind == "forbidden-contact" and finding.component_id == "shaft-1"
        for finding in result.findings
    )


def test_safe_endpoints_can_still_refute_interval_interior_collision():
    stock_box = _box((2.0, 2.0, 2.0), (3.0, 3.0, 3.0))
    fixture_box = _box((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))
    seeded, stock_hash, output_hash = _seed_explicit_pair(stock_box)
    cutter = _tool_component("cutter-1", "cutter")
    holder = _tool_component(
        "holder-1",
        "holder",
        radius=0.18,
        axis_start_offset=-0.1,
        axis_end_offset=0.1,
        aabb_min=(-0.18, -0.18, -0.1),
        aabb_max=(0.18, 0.18, 0.1),
    )
    context = _collision_context(
        tool_components=(cutter, holder),
        stock_box=stock_box,
        fixture_box=fixture_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=stock_hash,
                output_content_id=output_hash,
            ),
        ),
        position=_position_segment(start=(-1.0, 0.0, 0.0), end=(1.0, 0.0, 0.0)),
    )

    result = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded)

    finding = next(finding for finding in result.findings if finding.finding_kind == "forbidden-contact")
    assert result.collision_free is False
    assert finding.sample_sigma is not None
    assert 0.0 < finding.sample_sigma < 1.0


def test_unresolved_pair_does_not_claim_certified_safety():
    stock_box = _box((2.0, 2.0, 2.0), (3.0, 3.0, 3.0))
    fixture_box = _box((-0.8, -0.05, -0.05), (-0.7, 0.05, 0.05))
    seeded, stock_hash, output_hash = _seed_explicit_pair(stock_box)
    holder = _tool_component(
        "holder-1",
        "holder",
        radius=0.08,
        axis_start_offset=0.0,
        axis_end_offset=0.0,
    )
    context = _collision_context(tool_components=(holder,), stock_box=stock_box, fixture_box=fixture_box)
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=stock_hash,
                output_content_id=output_hash,
                tool_component_id="holder-1",
            ),
        ),
        position=_position_segment(start=(-1.0, 0.0, 0.0), end=(0.0, 0.0, 0.0)),
    )

    result = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded, max_subdivision_depth=0)

    assert result.collision_free is None
    assert result.reason_code == "ForbiddenContactUnresolved"
    assert result.state_transitions[0].status == "Failed"
    assert any(
        finding.finding_kind == "forbidden-contact" and finding.evidence_level == "Validated"
        for finding in result.findings
    )


def test_same_path_yields_different_result_on_different_stock_stage():
    stock_box = _box((-0.4, -0.4, -0.2), (0.4, 0.4, 0.2))
    later_stage_box = _box((2.0, 2.0, 2.0), (3.0, 3.0, 3.0))
    first_seed, first_hash, first_output_hash = _seed_explicit_pair(stock_box)
    second_seed, second_hash, second_output_hash = _seed_explicit_pair(later_stage_box)
    cutter = _tool_component("cutter-1", "cutter")
    context = _collision_context(
        tool_components=(cutter,),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    first_task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=first_hash,
                output_content_id=first_output_hash,
            ),
        ),
    )
    second_task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=second_hash,
                output_content_id=second_output_hash,
            ),
        ),
    )

    first = f1_collision.evaluate_task_collision(first_task, stock_state_geometries=first_seed)
    second = f1_collision.evaluate_task_collision(second_task, stock_state_geometries=second_seed)

    assert any(finding.finding_kind == "allowed-removal-contact" for finding in first.findings)
    assert all(finding.finding_kind != "allowed-removal-contact" for finding in second.findings)
    assert first.reason_code == "CollisionCertified"
    assert second.reason_code == "CollisionCertified"
    assert first.minimum_clearance_lower_bound < second.minimum_clearance_lower_bound


def test_missing_collision_context_is_reported():
    stock_box = _box((-0.4, -0.4, -0.2), (0.4, 0.4, 0.2))
    seeded, stock_hash, output_hash = _seed_explicit_pair(stock_box)
    cutter = _tool_component("cutter-1", "cutter")
    context = _collision_context(
        tool_components=(cutter,),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=stock_hash,
                output_content_id=output_hash,
            ),
        ),
    )
    missing_context = task.model_copy(update={"collision_context": None})

    result = f1_collision.evaluate_task_collision(missing_context, stock_state_geometries=seeded)

    assert result.collision_free is None
    assert result.reason_code == "CollisionContextRequired"


def test_missing_allowed_removal_for_active_cutter_is_insufficient():
    stock_box = _box((-0.4, -0.4, -0.2), (0.4, 0.4, 0.2))
    seeded, stock_hash, output_hash = _seed_explicit_pair(stock_box)
    cutter = _tool_component("cutter-1", "cutter")
    other_cutter = _tool_component("cutter-2", "cutter")
    context = _collision_context(
        tool_components=(cutter, other_cutter),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(tool_component_id="cutter-2", region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=stock_hash,
                output_content_id=output_hash,
            ),
        ),
    )

    result = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded)

    assert result.collision_free is None
    assert result.reason_code == "AllowedRemovalRequired"
    assert any(finding.reason_code == "AllowedRemovalRequired" for finding in result.findings)


def test_explicit_snapshot_missing_output_is_blocked():
    stock_box = _box((-0.4, -0.4, -0.2), (0.4, 0.4, 0.2))
    seeded, stock_hash = _seed_state(stock_box, state_id="s0")
    cutter = _tool_component("cutter-1", "cutter")
    context = _collision_context(
        tool_components=(cutter,),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_state_id="s0",
                output_state_id="s1",
                input_content_id=stock_hash,
                output_content_id=stock_hash,
            ),
        ),
        policy_id="five-axis.stock-update.explicit-snapshot@1",
    )

    result = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded)

    assert result.state_transitions[0].status == "Failed"
    assert result.state_transitions[0].reason_code == "MissingOutputSnapshot"
    assert result.reason_code == "MissingOutputSnapshot"


def test_explicit_snapshot_hash_mismatch_blocks_input():
    stock_box = _box((-0.4, -0.4, -0.2), (0.4, 0.4, 0.2))
    seeded, _, output_hash = _seed_explicit_pair(stock_box, input_content_id="f" * 64, output_content_id="f" * 64)
    cutter = _tool_component("cutter-1", "cutter")
    context = _collision_context(
        tool_components=(cutter,),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id="e" * 64,
                output_content_id=output_hash,
            ),
        ),
    )

    result = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded)

    assert result.state_transitions[0].status == "Blocked"
    assert result.state_transitions[0].reason_code == "ProvidedInputSnapshotHashMismatch"
    assert result.collision_free is None


def test_nominal_sweep_output_hash_mismatch_blocks_downstream_interval():
    stock_box = _box((2.0, 2.0, 2.0), (3.0, 3.0, 3.0))
    seeded, stock_hash = _seed_state(stock_box, state_id="s0")
    cutter = _tool_component("cutter-1", "cutter")
    context = _collision_context(
        tool_components=(cutter,),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=0.5,
                input_state_id="s0",
                output_state_id="s1",
                input_content_id=stock_hash,
                output_content_id="1" * 64,
            ),
            _interval(
                interval_id="i2",
                sigma_start=0.5,
                sigma_end=1.0,
                input_state_id="s1",
                output_state_id="s2",
                input_content_id="1" * 64,
                output_content_id="2" * 64,
            ),
        ),
        policy_id="five-axis.stock-update.nominal-sweep@1",
    )

    result = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded)

    assert result.state_transitions[0].status == "Failed"
    assert result.state_transitions[0].reason_code == "OutputSnapshotHashMismatch"
    assert result.state_transitions[1].status == "Blocked"
    assert result.state_transitions[1].reason_code == "UpstreamProcessStateInvalid"


def test_same_input_is_deterministic():
    stock_box = _box((-0.4, -0.4, -0.2), (0.4, 0.4, 0.2))
    seeded, stock_hash, output_hash = _seed_explicit_pair(stock_box)
    cutter = _tool_component("cutter-1", "cutter")
    context = _collision_context(
        tool_components=(cutter,),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=stock_hash,
                output_content_id=output_hash,
            ),
        ),
    )

    first = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded).model_dump(mode="json", by_alias=True)
    second = f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded).model_dump(mode="json", by_alias=True)

    assert first == second


def test_programmer_type_error_is_not_swallowed(monkeypatch: pytest.MonkeyPatch):
    stock_box = _box((-0.4, -0.4, -0.2), (0.4, 0.4, 0.2))
    seeded, stock_hash, output_hash = _seed_explicit_pair(stock_box)
    cutter = _tool_component("cutter-1", "cutter")
    context = _collision_context(
        tool_components=(cutter,),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_content_id=stock_hash,
                output_content_id=output_hash,
            ),
        ),
    )

    def _boom(*_args, **_kwargs):
        raise TypeError("programmer bug")

    monkeypatch.setattr(f1_collision, "_evaluate_geometry_position", _boom)

    with pytest.raises(TypeError, match="programmer bug"):
        f1_collision.evaluate_task_collision(task, stock_state_geometries=seeded)


def test_nominal_sweep_fragment_cap_reports_unsupported_regularized_difference():
    stock_box = _box((-0.4, -0.4, -0.2), (0.4, 0.4, 0.2))
    seeded, stock_hash = _seed_state(stock_box, state_id="s0")
    cutter = _tool_component("cutter-1", "cutter")
    context = _collision_context(
        tool_components=(cutter,),
        stock_box=stock_box,
        allowed_removal=(_allowed_removal(region=stock_box),),
    )
    task = _task(
        collision_context=context,
        intervals=(
            _interval(
                interval_id="i1",
                sigma_start=0.0,
                sigma_end=1.0,
                input_state_id="s0",
                output_state_id="s1",
                input_content_id=stock_hash,
                output_content_id="f" * 64,
            ),
        ),
        policy_id="five-axis.stock-update.nominal-sweep@1",
    )

    result = f1_collision.evaluate_task_collision(
        task,
        stock_state_geometries=seeded,
        max_regularized_difference_fragments=1,
    )

    assert result.collision_free is None
    assert result.overcut_free is None
    assert result.reason_code == "UnsupportedRegularizedDifference"
    assert result.state_transitions[0].status == "Failed"
    assert result.state_transitions[0].reason_code == "UnsupportedRegularizedDifference"
