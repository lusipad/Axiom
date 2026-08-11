from __future__ import annotations

import math
import re
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel


_EPSILON = 1e-12
_CONTENT_HASH_PATTERN = r"^[0-9a-f]{64}$"
_CONTACT_CATEGORY = Literal["cutter", "shaft", "holder", "stock", "fixture", "machine"]
_CONTINUITY_CLASS = Literal["C0", "C1", "C2", "C3"]
_DEGENERATE_KIND = Literal["none", "zero-length-source", "collapsed-sigma", "point-segment"]
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_VERSIONED_ID_PATTERN = r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+@[1-9][0-9]*$"


def _require_finite_json_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("value must be a finite JSON number")
    return value


def _require_finite_vector(value: Any, *, expected: int | None = None, field_name: str) -> Any:
    if isinstance(value, (list, tuple)):
        if expected is not None and len(value) != expected:
            raise ValueError(f"{field_name} must contain exactly {expected} numbers")
        if expected is None and not value:
            raise ValueError(f"{field_name} must not be empty")
        for item in value:
            _require_finite_json_number(item)
    return value


def _require_unique_ids(items: tuple[Any, ...], *, attr: str, field_name: str) -> tuple[Any, ...]:
    values = tuple(getattr(item, attr) for item in items)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicate IDs")
    return items


def _validate_unit_interval(start: float, end: float, *, field_name: str) -> None:
    if start < -_EPSILON or end > 1.0 + _EPSILON:
        raise ValueError(f"{field_name} must stay within [0, 1]")
    if end < start - _EPSILON:
        raise ValueError(f"{field_name} must be monotone nondecreasing")


def _validate_interval_coverage(
    items: tuple[Any, ...],
    *,
    start_attr: str,
    end_attr: str,
    field_name: str,
    start_bound: float = 0.0,
    end_bound: float = 1.0,
) -> None:
    cursor = start_bound
    for item in items:
        start = getattr(item, start_attr)
        end = getattr(item, end_attr)
        if start < cursor - _EPSILON:
            raise ValueError(f"{field_name} must not overlap")
        if start > cursor + _EPSILON:
            raise ValueError(f"{field_name} must not contain gaps")
        if end < start - _EPSILON:
            raise ValueError(f"{field_name} must be monotone nondecreasing")
        cursor = max(cursor, end)
    if items:
        first = getattr(items[0], start_attr)
        last = getattr(items[-1], end_attr)
        if not math.isclose(first, start_bound, abs_tol=_EPSILON):
            raise ValueError(f"{field_name} must start at {start_bound}")
        if not math.isclose(last, end_bound, abs_tol=_EPSILON):
            raise ValueError(f"{field_name} must end at {end_bound}")


def _validate_unit_vector(vector: tuple[float, float, float], *, field_name: str) -> tuple[float, float, float]:
    norm = math.sqrt(sum(component * component for component in vector))
    if math.isclose(norm, 0.0, abs_tol=_EPSILON):
        raise ValueError(f"{field_name} must not be the zero vector")
    if not math.isclose(norm, 1.0, abs_tol=1e-9):
        raise ValueError(f"{field_name} must be unit length")
    return vector


def _validate_unit_quaternion(
    quaternion: tuple[float, float, float, float], *, field_name: str
) -> tuple[float, float, float, float]:
    norm = math.sqrt(sum(component * component for component in quaternion))
    if math.isclose(norm, 0.0, abs_tol=_EPSILON):
        raise ValueError(f"{field_name} must not be the zero quaternion")
    if not math.isclose(norm, 1.0, abs_tol=1e-9):
        raise ValueError(f"{field_name} must be unit length")
    return quaternion


def _subtract3(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return (left[0] - right[0], left[1] - right[1], left[2] - right[2])


def _dot3(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _cross3(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _norm3(vector: tuple[float, float, float]) -> float:
    return math.sqrt(_dot3(vector, vector))


def _rotate_about_axis(
    vector: tuple[float, float, float], axis: tuple[float, float, float], angle: float
) -> tuple[float, float, float]:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    cross = _cross3(axis, vector)
    dot = _dot3(axis, vector)
    return (
        vector[0] * cosine + cross[0] * sine + axis[0] * dot * (1.0 - cosine),
        vector[1] * cosine + cross[1] * sine + axis[1] * dot * (1.0 - cosine),
        vector[2] * cosine + cross[2] * sine + axis[2] * dot * (1.0 - cosine),
    )


def _required_orders(continuity_class: _CONTINUITY_CLASS) -> set[int]:
    return {
        "C0": {0},
        "C1": {0, 1},
        "C2": {0, 1, 2},
        "C3": {0, 1, 2, 3},
    }[continuity_class]


class CoordinateContext(AxiomModel):
    unit: str = Field(min_length=1)
    coordinate_frame: str = Field(alias="coordinateFrame", min_length=1)


class SourceLineage(AxiomModel):
    statement_id: str = Field(alias="statementId", min_length=1, pattern=_ID_PATTERN)
    statement_index: int = Field(alias="statementIndex", ge=0)
    line: int = Field(ge=1)
    column: int = Field(ge=1)
    source_text: str = Field(alias="sourceText", min_length=1)
    source_path: str | None = Field(default=None, alias="sourcePath")


class ProvenanceRef(AxiomModel):
    source_stage: Literal["M0", "M1", "M2"] = Field(alias="sourceStage")
    source_id: str = Field(alias="sourceId", min_length=1, pattern=_ID_PATTERN)
    source_content_id: str | None = Field(default=None, alias="sourceContentId", pattern=_CONTENT_HASH_PATTERN)
    method: str | None = None


class MotionEventBase(AxiomModel):
    event_id: str = Field(alias="eventId", min_length=1, pattern=_ID_PATTERN)
    event_type: str = Field(alias="eventType")
    lineage: SourceLineage


class FromEvent(MotionEventBase):
    event_type: Literal["FROM"] = Field(alias="eventType")
    coordinate_context: CoordinateContext = Field(alias="coordinateContext")
    position: tuple[float, float, float]
    tool_axis: tuple[float, float, float] = Field(alias="toolAxis")
    tool_axis_source: Literal["explicit", "modal-inherited"] = Field(alias="toolAxisSource")
    tool_axis_source_statement_id: str | None = Field(
        default=None,
        alias="toolAxisSourceStatementId",
        pattern=_ID_PATTERN,
    )
    source_tool_axis: tuple[float, float, float] | None = Field(default=None, alias="sourceToolAxis")
    normalization_method: str | None = Field(default=None, alias="normalizationMethod")

    @field_validator("position", mode="before")
    @classmethod
    def reject_invalid_position(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="position")

    @field_validator("tool_axis", "source_tool_axis", mode="before")
    @classmethod
    def reject_invalid_tool_axis(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_vector(value, expected=3, field_name="toolAxis")

    @model_validator(mode="after")
    def require_nonzero_axis(self) -> "FromEvent":
        _validate_unit_vector(self.tool_axis, field_name="toolAxis")
        if self.source_tool_axis is not None:
            _validate_unit_vector(self.source_tool_axis, field_name="sourceToolAxis")
        if self.normalization_method is not None and self.source_tool_axis is None:
            raise ValueError("normalizationMethod requires sourceToolAxis")
        if self.tool_axis_source == "explicit" and self.tool_axis_source_statement_id is not None:
            raise ValueError("explicit toolAxisSource forbids toolAxisSourceStatementId")
        return self


class GotoEvent(MotionEventBase):
    event_type: Literal["GOTO"] = Field(alias="eventType")
    coordinate_context: CoordinateContext = Field(alias="coordinateContext")
    position: tuple[float, float, float]
    tool_axis: tuple[float, float, float] = Field(alias="toolAxis")
    tool_axis_source: Literal["explicit", "modal-inherited"] = Field(alias="toolAxisSource")
    tool_axis_source_statement_id: str | None = Field(
        default=None,
        alias="toolAxisSourceStatementId",
        pattern=_ID_PATTERN,
    )
    source_tool_axis: tuple[float, float, float] | None = Field(default=None, alias="sourceToolAxis")
    normalization_method: str | None = Field(default=None, alias="normalizationMethod")

    @field_validator("position", mode="before")
    @classmethod
    def reject_invalid_position(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="position")

    @field_validator("tool_axis", "source_tool_axis", mode="before")
    @classmethod
    def reject_invalid_tool_axis(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_vector(value, expected=3, field_name="toolAxis")

    @model_validator(mode="after")
    def require_nonzero_axis(self) -> "GotoEvent":
        _validate_unit_vector(self.tool_axis, field_name="toolAxis")
        if self.source_tool_axis is not None:
            _validate_unit_vector(self.source_tool_axis, field_name="sourceToolAxis")
        if self.normalization_method is not None and self.source_tool_axis is None:
            raise ValueError("normalizationMethod requires sourceToolAxis")
        if self.tool_axis_source == "explicit" and self.tool_axis_source_statement_id is not None:
            raise ValueError("explicit toolAxisSource forbids toolAxisSourceStatementId")
        return self


class FeedRateEvent(MotionEventBase):
    event_type: Literal["FEDRAT"] = Field(alias="eventType")
    feed_rate: float = Field(alias="feedRate", gt=0)
    unit: str = Field(min_length=1)

    @field_validator("feed_rate", mode="before")
    @classmethod
    def reject_invalid_feed_rate(cls, value: Any) -> Any:
        return _require_finite_json_number(value)


class DwellEvent(MotionEventBase):
    event_type: Literal["DWELL"] = Field(alias="eventType")
    duration: float = Field(ge=0)
    unit: Literal["s"]

    @field_validator("duration", mode="before")
    @classmethod
    def reject_invalid_duration(cls, value: Any) -> Any:
        return _require_finite_json_number(value)


class EndEvent(MotionEventBase):
    event_type: Literal["END"] = Field(alias="eventType")


NormalizedProgramEvent = Annotated[
    FromEvent | GotoEvent | FeedRateEvent | DwellEvent | EndEvent,
    Field(discriminator="event_type"),
]


class NormalizedProgram(AxiomModel):
    artifact_type: Literal["five-axis.normalized-program"] = Field(alias="artifactType")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    program_id: str = Field(alias="programId", min_length=1, pattern=_ID_PATTERN)
    source_syntax_id: str = Field(alias="sourceSyntaxId", min_length=1)
    coordinate_context: CoordinateContext = Field(alias="coordinateContext")
    events: tuple[NormalizedProgramEvent, ...] = Field(min_length=2)
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_strict_subset_order(self) -> "NormalizedProgram":
        if self.source_syntax_id != "axiom-cl-subset@1" and re.fullmatch(_VERSIONED_ID_PATTERN, self.source_syntax_id) is None:
            raise ValueError("sourceSyntaxId must be axiom-cl-subset@1 or an importer ID")
        _require_unique_ids(self.events, attr="event_id", field_name="events")
        if self.events[0].event_type != "FROM":
            raise ValueError("NormalizedProgram must start with FROM")
        if self.events[-1].event_type != "END":
            raise ValueError("NormalizedProgram must end with END")
        end_seen = False
        goto_seen = False
        last_explicit_axis: tuple[float, float, float] | None = None
        last_explicit_axis_statement_id: str | None = None
        for event in self.events:
            if end_seen:
                raise ValueError("END must be the final event")
            if event.event_type == "END":
                end_seen = True
            if event.event_type == "GOTO":
                goto_seen = True
            if isinstance(event, FromEvent | GotoEvent):
                if event.tool_axis_source == "explicit":
                    last_explicit_axis_statement_id = event.lineage.statement_id
                    last_explicit_axis = event.tool_axis
                    if event.source_tool_axis is not None and event.source_tool_axis != event.tool_axis:
                        raise ValueError("explicit sourceToolAxis must equal toolAxis when provided")
                else:
                    if last_explicit_axis_statement_id is None or last_explicit_axis is None:
                        raise ValueError("modal-inherited toolAxisSource requires prior explicit tool axis")
                    if event.tool_axis_source_statement_id is None:
                        raise ValueError("modal-inherited toolAxisSource requires toolAxisSourceStatementId")
                    if event.source_tool_axis is None:
                        raise ValueError("modal-inherited toolAxisSource requires sourceToolAxis")
                    if event.tool_axis_source_statement_id != last_explicit_axis_statement_id:
                        raise ValueError("toolAxisSourceStatementId must reference the most recent explicit tool axis")
                    if event.source_tool_axis != last_explicit_axis:
                        raise ValueError("sourceToolAxis must equal the most recent explicit tool axis")
                    if event.tool_axis != last_explicit_axis:
                        raise ValueError("modal-inherited toolAxis must equal the most recent explicit tool axis")
        if not goto_seen:
            raise ValueError("NormalizedProgram must contain at least one GOTO")
        return self


class SegmentIntervalMapping(AxiomModel):
    mapping_id: str = Field(alias="mappingId", min_length=1, pattern=_ID_PATTERN)
    source_segment_id: str = Field(alias="sourceSegmentId", min_length=1, pattern=_ID_PATTERN)
    source_local_start: float = Field(alias="sourceLocalStart")
    source_local_end: float = Field(alias="sourceLocalEnd")
    sigma_start: float = Field(alias="sigmaStart")
    sigma_end: float = Field(alias="sigmaEnd")
    degenerate_kind: _DEGENERATE_KIND = Field(alias="degenerateKind")
    provenance: ProvenanceRef | None = None

    @field_validator("source_local_start", "source_local_end", "sigma_start", "sigma_end", mode="before")
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_monotone_mapping(self) -> "SegmentIntervalMapping":
        _validate_unit_interval(
            self.source_local_start,
            self.source_local_end,
            field_name="sourceLocal interval",
        )
        _validate_unit_interval(self.sigma_start, self.sigma_end, field_name="sigma interval")
        is_degenerate = math.isclose(self.source_local_start, self.source_local_end, abs_tol=_EPSILON) or math.isclose(
            self.sigma_start, self.sigma_end, abs_tol=_EPSILON
        )
        if is_degenerate and self.degenerate_kind == "none":
            raise ValueError("degenerateKind must describe degenerate intervals")
        if not is_degenerate and self.degenerate_kind != "none":
            raise ValueError("degenerateKind must be none for nondegenerate intervals")
        return self


class PathProgress(AxiomModel):
    progress_id: str = Field(alias="progressId", min_length=1, pattern=_ID_PATTERN)
    schema_version: Literal[1] = Field(alias="schemaVersion")
    progress_parameter: Literal["sigma"] = Field(default="sigma", alias="progressParameter")
    unit: Literal["dimensionless"] = "dimensionless"
    mappings: tuple[SegmentIntervalMapping, ...] = Field(min_length=1)
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_closed_sigma_coverage(self) -> "PathProgress":
        _require_unique_ids(self.mappings, attr="mapping_id", field_name="mappings")
        _validate_interval_coverage(
            self.mappings,
            start_attr="sigma_start",
            end_attr="sigma_end",
            field_name="mappings",
        )
        mappings_by_source: dict[str, list[SegmentIntervalMapping]] = {}
        for mapping in self.mappings:
            mappings_by_source.setdefault(mapping.source_segment_id, []).append(mapping)
        for source_segment_id, source_mappings in mappings_by_source.items():
            cursor = 0.0
            has_nondegenerate = False
            first_nondegenerate_start: float | None = None
            for mapping in source_mappings:
                if mapping.degenerate_kind != "none":
                    continue
                has_nondegenerate = True
                if first_nondegenerate_start is None:
                    first_nondegenerate_start = mapping.source_local_start
                if mapping.source_local_start < cursor - _EPSILON:
                    raise ValueError(f"source-local mappings for {source_segment_id} must not overlap")
                if mapping.source_local_start > cursor + _EPSILON:
                    raise ValueError(f"source-local mappings for {source_segment_id} must not contain gaps")
                cursor = mapping.source_local_end
            if has_nondegenerate:
                if first_nondegenerate_start is None or not math.isclose(first_nondegenerate_start, 0.0, abs_tol=_EPSILON):
                    raise ValueError(f"source-local mappings for {source_segment_id} must start at 0.0")
                if not math.isclose(cursor, 1.0, abs_tol=_EPSILON):
                    raise ValueError(f"source-local mappings for {source_segment_id} must end at 1.0")
        return self


class NodeEvent(AxiomModel):
    node_id: str = Field(alias="nodeId", min_length=1, pattern=_ID_PATTERN)
    sigma: float
    event_type: Literal[
        "ordinary-junction",
        "mandatory-stop",
        "dwell",
        "branch-change",
        "wrap",
        "singularity-boundary",
        "collision-boundary",
        "collision-violation",
        "degenerate-segment",
    ] = Field(alias="eventType")
    left_segment_id: str | None = Field(default=None, alias="leftSegmentId", pattern=_ID_PATTERN)
    right_segment_id: str | None = Field(default=None, alias="rightSegmentId", pattern=_ID_PATTERN)
    provenance: ProvenanceRef | None = None

    @field_validator("sigma", mode="before")
    @classmethod
    def reject_invalid_sigma(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_unit_sigma(self) -> "NodeEvent":
        _validate_unit_interval(self.sigma, self.sigma, field_name="sigma")
        return self


class DerivativeValue(AxiomModel):
    order: int = Field(ge=0, le=3)
    components: tuple[float, ...] = Field(min_length=1)

    @field_validator("components", mode="before")
    @classmethod
    def reject_invalid_components(cls, value: Any) -> Any:
        return _require_finite_vector(value, field_name="components")


class SegmentRegularityEvidence(AxiomModel):
    segment_id: str = Field(alias="segmentId", min_length=1, pattern=_ID_PATTERN)
    continuity_class: _CONTINUITY_CLASS = Field(alias="continuityClass")
    derivatives: tuple[DerivativeValue, ...] = Field(min_length=1)
    verification_method: str = Field(alias="verificationMethod", min_length=1)

    @model_validator(mode="after")
    def require_required_orders(self) -> "SegmentRegularityEvidence":
        orders = {item.order for item in self.derivatives}
        if len(orders) != len(self.derivatives):
            raise ValueError("SegmentRegularityEvidence derivatives must not repeat orders")
        if not _required_orders(self.continuity_class).issubset(orders):
            raise ValueError("SegmentRegularityEvidence must cover all derivative orders for the class")
        return self


class NodeRegularityEvidence(AxiomModel):
    node_id: str = Field(alias="nodeId", min_length=1, pattern=_ID_PATTERN)
    continuity_class: _CONTINUITY_CLASS = Field(alias="continuityClass")
    left_derivatives: tuple[DerivativeValue, ...] = Field(alias="leftDerivatives", min_length=1)
    right_derivatives: tuple[DerivativeValue, ...] = Field(alias="rightDerivatives", min_length=1)
    verification_method: str = Field(alias="verificationMethod", min_length=1)

    @model_validator(mode="after")
    def require_required_orders(self) -> "NodeRegularityEvidence":
        required = _required_orders(self.continuity_class)
        left_orders = {item.order for item in self.left_derivatives}
        right_orders = {item.order for item in self.right_derivatives}
        if len(left_orders) != len(self.left_derivatives):
            raise ValueError("leftDerivatives must not repeat orders")
        if len(right_orders) != len(self.right_derivatives):
            raise ValueError("rightDerivatives must not repeat orders")
        if not required.issubset(left_orders) or not required.issubset(right_orders):
            raise ValueError("NodeRegularityEvidence must cover all one-sided derivative orders for the class")
        return self


class RegularityCertificate(AxiomModel):
    certificate_id: str = Field(alias="certificateId", min_length=1, pattern=_ID_PATTERN)
    segment_evidence: tuple[SegmentRegularityEvidence, ...] = Field(alias="segmentEvidence", default_factory=tuple)
    node_evidence: tuple[NodeRegularityEvidence, ...] = Field(alias="nodeEvidence", default_factory=tuple)

    @model_validator(mode="after")
    def require_unique_targets(self) -> "RegularityCertificate":
        _require_unique_ids(self.segment_evidence, attr="segment_id", field_name="segmentEvidence")
        _require_unique_ids(self.node_evidence, attr="node_id", field_name="nodeEvidence")
        return self


class PositionSegmentBase(AxiomModel):
    segment_id: str = Field(alias="segmentId", min_length=1, pattern=_ID_PATTERN)
    segment_type: str = Field(alias="segmentType")
    sigma_start: float = Field(alias="sigmaStart")
    sigma_end: float = Field(alias="sigmaEnd")
    lineage: tuple[SourceLineage, ...] = Field(min_length=1)
    is_degenerate: bool = Field(default=False, alias="isDegenerate")
    provenance: ProvenanceRef | None = None

    @field_validator("sigma_start", "sigma_end", mode="before")
    @classmethod
    def reject_invalid_sigma(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_valid_sigma(self) -> "PositionSegmentBase":
        _validate_unit_interval(self.sigma_start, self.sigma_end, field_name="sigma")
        is_zero_width = math.isclose(self.sigma_start, self.sigma_end, abs_tol=_EPSILON)
        if is_zero_width and not self.is_degenerate:
            raise ValueError("isDegenerate must be true for zero-width segments")
        if not is_zero_width and self.is_degenerate:
            raise ValueError("isDegenerate may only be true for zero-width segments")
        return self


class LinePositionSegment(PositionSegmentBase):
    segment_type: Literal["line"] = Field(alias="segmentType")
    start_point: tuple[float, float, float] = Field(alias="startPoint")
    end_point: tuple[float, float, float] = Field(alias="endPoint")

    @field_validator("start_point", "end_point", mode="before")
    @classmethod
    def reject_invalid_points(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="point")


class ArcPositionSegment(PositionSegmentBase):
    segment_type: Literal["arc"] = Field(alias="segmentType")
    center: tuple[float, float, float]
    start_point: tuple[float, float, float] = Field(alias="startPoint")
    end_point: tuple[float, float, float] = Field(alias="endPoint")
    radius: float = Field(gt=0)
    normal: tuple[float, float, float]
    sweep_radians: float = Field(alias="sweepRadians")

    @field_validator("center", "start_point", "end_point", "normal", mode="before")
    @classmethod
    def reject_invalid_vectors(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="vector")

    @field_validator("radius", "sweep_radians", mode="before")
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_valid_normal(self) -> "ArcPositionSegment":
        _validate_unit_vector(self.normal, field_name="normal")
        start_vector = _subtract3(self.start_point, self.center)
        end_vector = _subtract3(self.end_point, self.center)
        start_radius = _norm3(start_vector)
        end_radius = _norm3(end_vector)
        if not math.isclose(start_radius, self.radius, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("startPoint must lie on the declared arc radius")
        if not math.isclose(end_radius, self.radius, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("endPoint must lie on the declared arc radius")
        if not math.isclose(_dot3(start_vector, self.normal), 0.0, abs_tol=1e-9):
            raise ValueError("startPoint must lie in the arc plane")
        if not math.isclose(_dot3(end_vector, self.normal), 0.0, abs_tol=1e-9):
            raise ValueError("endPoint must lie in the arc plane")
        if math.isclose(self.sweep_radians, 0.0, abs_tol=1e-9):
            raise ValueError("sweepRadians must be non-zero")
        if abs(self.sweep_radians) > 2.0 * math.pi + 1e-9:
            raise ValueError("sweepRadians must stay within a single revolution")
        rotated = _rotate_about_axis(start_vector, self.normal, self.sweep_radians)
        if _norm3(_subtract3(rotated, end_vector)) > 1e-8:
            raise ValueError("sweepRadians is inconsistent with the signed arc geometry")
        if _norm3(_subtract3(start_vector, end_vector)) <= 1e-9 and not math.isclose(
            abs(self.sweep_radians),
            2.0 * math.pi,
            abs_tol=1e-9,
        ):
            raise ValueError("coincident arc endpoints require a full-turn sweep")
        return self


class HelixPositionSegment(PositionSegmentBase):
    segment_type: Literal["helix"] = Field(alias="segmentType")
    center: tuple[float, float, float]
    axis: tuple[float, float, float]
    start_point: tuple[float, float, float] = Field(alias="startPoint")
    radius: float = Field(gt=0)
    pitch_per_turn: float = Field(alias="pitchPerTurn")
    turns: float = Field(gt=0)

    @field_validator("center", "axis", "start_point", mode="before")
    @classmethod
    def reject_invalid_vectors(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="vector")

    @field_validator("radius", "pitch_per_turn", "turns", mode="before")
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_valid_axis(self) -> "HelixPositionSegment":
        _validate_unit_vector(self.axis, field_name="axis")
        radial = _subtract3(self.start_point, self.center)
        if not math.isclose(_dot3(radial, self.axis), 0.0, abs_tol=1e-9):
            raise ValueError("startPoint must be perpendicular to the helix axis")
        if not math.isclose(_norm3(radial), self.radius, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("startPoint must lie on the declared helix radius")
        return self


class BezierPositionSegment(PositionSegmentBase):
    segment_type: Literal["bezier"] = Field(alias="segmentType")
    control_points: tuple[tuple[float, float, float], ...] = Field(alias="controlPoints", min_length=2)

    @field_validator("control_points", mode="before")
    @classmethod
    def reject_invalid_control_points(cls, value: Any) -> Any:
        if isinstance(value, list):
            for point in value:
                _require_finite_vector(point, expected=3, field_name="controlPoints")
        return value


class BSplinePositionSegment(PositionSegmentBase):
    segment_type: Literal["bspline"] = Field(alias="segmentType")
    degree: int = Field(ge=1)
    control_points: tuple[tuple[float, float, float], ...] = Field(alias="controlPoints", min_length=2)
    knots: tuple[float, ...] = Field(min_length=2)
    weights: tuple[float, ...] | None = None

    @field_validator("control_points", mode="before")
    @classmethod
    def reject_invalid_control_points(cls, value: Any) -> Any:
        if isinstance(value, list):
            for point in value:
                _require_finite_vector(point, expected=3, field_name="controlPoints")
        return value

    @field_validator("knots", "weights", mode="before")
    @classmethod
    def reject_invalid_sequences(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_vector(value, field_name="sequence")

    @model_validator(mode="after")
    def require_valid_bspline(self) -> "BSplinePositionSegment":
        if len(self.knots) != len(self.control_points) + self.degree + 1:
            raise ValueError("knots length must equal len(controlPoints) + degree + 1")
        if any(right < left for left, right in zip(self.knots, self.knots[1:])):
            raise ValueError("knots must be monotone nondecreasing")
        if self.weights is not None:
            if len(self.weights) != len(self.control_points):
                raise ValueError("weights length must match controlPoints length")
            if any(weight <= 0 for weight in self.weights):
                raise ValueError("weights must be positive")
        return self


PositionSegment = Annotated[
    LinePositionSegment | ArcPositionSegment | HelixPositionSegment | BezierPositionSegment | BSplinePositionSegment,
    Field(discriminator="segment_type"),
]


class OrientationSegmentBase(AxiomModel):
    segment_id: str = Field(alias="segmentId", min_length=1, pattern=_ID_PATTERN)
    segment_type: str = Field(alias="segmentType")
    sigma_start: float = Field(alias="sigmaStart")
    sigma_end: float = Field(alias="sigmaEnd")
    lineage: tuple[SourceLineage, ...] = Field(min_length=1)
    provenance: ProvenanceRef | None = None

    @field_validator("sigma_start", "sigma_end", mode="before")
    @classmethod
    def reject_invalid_sigma(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_valid_sigma(self) -> "OrientationSegmentBase":
        _validate_unit_interval(self.sigma_start, self.sigma_end, field_name="sigma")
        if math.isclose(self.sigma_start, self.sigma_end, abs_tol=_EPSILON):
            raise ValueError("orientation segments must have positive sigma extent")
        return self


class ConstantOrientationSegment(OrientationSegmentBase):
    segment_type: Literal["constant"] = Field(alias="segmentType")
    axis: tuple[float, float, float]

    @field_validator("axis", mode="before")
    @classmethod
    def reject_invalid_orientation(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="axis")

    @model_validator(mode="after")
    def require_valid_orientation(self) -> "ConstantOrientationSegment":
        _validate_unit_vector(self.axis, field_name="axis")
        return self


class SlerpOrientationSegment(OrientationSegmentBase):
    segment_type: Literal["slerp"] = Field(alias="segmentType")
    start_axis: tuple[float, float, float] = Field(alias="startAxis")
    end_axis: tuple[float, float, float] = Field(alias="endAxis")
    antipodal_policy: Literal["reject"] = Field(default="reject", alias="antipodalPolicy")

    @field_validator("start_axis", "end_axis", mode="before")
    @classmethod
    def reject_invalid_orientation(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="axis")

    @model_validator(mode="after")
    def require_valid_orientation(self) -> "SlerpOrientationSegment":
        _validate_unit_vector(self.start_axis, field_name="startAxis")
        _validate_unit_vector(self.end_axis, field_name="endAxis")
        if math.isclose(_dot3(self.start_axis, self.end_axis), -1.0, abs_tol=1e-9):
            raise ValueError("antipodal tool-axis interpolation is rejected")
        return self


OrientationSegment = Annotated[
    ConstantOrientationSegment | SlerpOrientationSegment,
    Field(discriminator="segment_type"),
]


class M1ReferencePath(AxiomModel):
    artifact_type: Literal["five-axis.m1-reference-path"] = Field(alias="artifactType")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    reference_path_id: str = Field(alias="referencePathId", min_length=1, pattern=_ID_PATTERN)
    coordinate_context: CoordinateContext = Field(alias="coordinateContext")
    path_progress: PathProgress = Field(alias="pathProgress")
    position_semantics: Literal["continuous", "static"] = Field(default="continuous", alias="positionSemantics")
    static_position: tuple[float, float, float] | None = Field(default=None, alias="staticPosition")
    position_segments: tuple[PositionSegment, ...] = Field(alias="positionSegments", default_factory=tuple)
    orientation_segments: tuple[OrientationSegment, ...] = Field(alias="orientationSegments", default_factory=tuple)
    node_events: tuple[NodeEvent, ...] = Field(alias="nodeEvents", default_factory=tuple)
    regularity_certificate: RegularityCertificate | None = Field(default=None, alias="regularityCertificate")
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @field_validator("static_position", mode="before")
    @classmethod
    def reject_invalid_static_position(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_vector(value, expected=3, field_name="staticPosition")

    @model_validator(mode="after")
    def require_consistent_segment_domains(self) -> "M1ReferencePath":
        if not self.position_segments and not self.orientation_segments:
            raise ValueError("M1ReferencePath requires positionSegments or orientationSegments")
        if self.position_segments and self.position_semantics != "continuous":
            raise ValueError("positionSemantics must be continuous when positionSegments are present")
        if not self.position_segments and self.position_semantics != "static":
            raise ValueError("positionSemantics must be static when positionSegments are absent")
        if not self.position_segments and self.static_position is None:
            raise ValueError("orientation-only paths require staticPosition")
        if self.position_segments and self.static_position is not None:
            raise ValueError("continuous position paths forbid staticPosition")
        _require_unique_ids(self.position_segments, attr="segment_id", field_name="positionSegments")
        _require_unique_ids(self.orientation_segments, attr="segment_id", field_name="orientationSegments")
        _require_unique_ids(self.node_events, attr="node_id", field_name="nodeEvents")
        segment_ids = {segment.segment_id for segment in self.position_segments} | {
            segment.segment_id for segment in self.orientation_segments
        }
        if any(mapping.source_segment_id not in segment_ids for mapping in self.path_progress.mappings):
            raise ValueError("pathProgress mappings must target actual segments")
        if any(
            event.left_segment_id is not None and event.left_segment_id not in segment_ids
            for event in self.node_events
        ):
            raise ValueError("nodeEvents leftSegmentId must target actual segments")
        if any(
            event.right_segment_id is not None and event.right_segment_id not in segment_ids
            for event in self.node_events
        ):
            raise ValueError("nodeEvents rightSegmentId must target actual segments")
        if self.position_segments:
            _validate_interval_coverage(
                self.position_segments,
                start_attr="sigma_start",
                end_attr="sigma_end",
                field_name="positionSegments",
            )
        if self.orientation_segments:
            _validate_interval_coverage(
                self.orientation_segments,
                start_attr="sigma_start",
                end_attr="sigma_end",
                field_name="orientationSegments",
            )
        if any(event.sigma < -_EPSILON or event.sigma > 1.0 + _EPSILON for event in self.node_events):
            raise ValueError("nodeEvents sigma must stay within [0, 1]")
        if self.regularity_certificate is not None:
            node_ids = {event.node_id for event in self.node_events}
            if any(item.segment_id not in segment_ids for item in self.regularity_certificate.segment_evidence):
                raise ValueError("regularityCertificate segment targets must match actual segments")
            if any(item.node_id not in node_ids for item in self.regularity_certificate.node_evidence):
                raise ValueError("regularityCertificate node targets must match actual nodeEvents")
        return self


class NumericTolerance(AxiomModel):
    absolute: float = Field(ge=0)
    relative: float | None = Field(default=None, ge=0)
    unit: str = Field(min_length=1)

    @field_validator("absolute", "relative", mode="before")
    @classmethod
    def reject_invalid_values(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_json_number(value)


class ProvenanceProgressPolicy(AxiomModel):
    strategy_id: Literal["five-axis.correspondence.provenance-progress@1"] = Field(alias="strategyId")
    allowed_source_interval: tuple[float, float] = Field(alias="allowedSourceInterval")
    allowed_target_interval: tuple[float, float] = Field(alias="allowedTargetInterval")
    objective: Literal["preserve-source-lineage"]
    deterministic_tie_break: Literal["lowest-source-segment-id", "lowest-target-sigma"] = Field(
        alias="deterministicTieBreak"
    )
    numeric_tolerance: NumericTolerance = Field(alias="numericTolerance")

    @field_validator("allowed_source_interval", "allowed_target_interval", mode="before")
    @classmethod
    def reject_invalid_interval(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=2, field_name="interval")

    @model_validator(mode="after")
    def require_valid_intervals(self) -> "ProvenanceProgressPolicy":
        _validate_unit_interval(
            self.allowed_source_interval[0],
            self.allowed_source_interval[1],
            field_name="allowedSourceInterval",
        )
        _validate_unit_interval(
            self.allowed_target_interval[0],
            self.allowed_target_interval[1],
            field_name="allowedTargetInterval",
        )
        return self


class MonotoneMinimaxPolicy(AxiomModel):
    strategy_id: Literal["five-axis.correspondence.monotone-minimax@1"] = Field(alias="strategyId")
    allowed_source_interval: tuple[float, float] = Field(alias="allowedSourceInterval")
    allowed_target_interval: tuple[float, float] = Field(alias="allowedTargetInterval")
    objective: Literal["minimize-maximum-deviation"]
    deterministic_tie_break: Literal["earliest-target-sigma", "lowest-candidate-id"] = Field(
        alias="deterministicTieBreak"
    )
    numeric_tolerance: NumericTolerance = Field(alias="numericTolerance")

    @field_validator("allowed_source_interval", "allowed_target_interval", mode="before")
    @classmethod
    def reject_invalid_interval(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=2, field_name="interval")

    @model_validator(mode="after")
    def require_valid_intervals(self) -> "MonotoneMinimaxPolicy":
        _validate_unit_interval(
            self.allowed_source_interval[0],
            self.allowed_source_interval[1],
            field_name="allowedSourceInterval",
        )
        _validate_unit_interval(
            self.allowed_target_interval[0],
            self.allowed_target_interval[1],
            field_name="allowedTargetInterval",
        )
        return self


CorrespondencePolicy = Annotated[
    ProvenanceProgressPolicy | MonotoneMinimaxPolicy,
    Field(discriminator="strategy_id"),
]


class CorrespondenceInterval(AxiomModel):
    interval_id: str = Field(alias="intervalId", min_length=1, pattern=_ID_PATTERN)
    source_sigma_start: float = Field(alias="sourceSigmaStart")
    source_sigma_end: float = Field(alias="sourceSigmaEnd")
    target_sigma_start: float = Field(alias="targetSigmaStart")
    target_sigma_end: float = Field(alias="targetSigmaEnd")
    source_segment_id: str | None = Field(default=None, alias="sourceSegmentId", pattern=_ID_PATTERN)
    target_segment_id: str | None = Field(default=None, alias="targetSegmentId", pattern=_ID_PATTERN)
    correspondence_status: Literal["matched", "clamped", "collapsed"] = Field(alias="correspondenceStatus")
    provenance: ProvenanceRef | None = None

    @field_validator(
        "source_sigma_start",
        "source_sigma_end",
        "target_sigma_start",
        "target_sigma_end",
        mode="before",
    )
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_valid_intervals(self) -> "CorrespondenceInterval":
        _validate_unit_interval(self.source_sigma_start, self.source_sigma_end, field_name="source sigma")
        _validate_unit_interval(self.target_sigma_start, self.target_sigma_end, field_name="target sigma")
        return self


class CanonicalNode(AxiomModel):
    path_role: Literal["source", "target"] = Field(alias="pathRole")
    node_id: str = Field(alias="nodeId", min_length=1, pattern=_ID_PATTERN)
    sigma: float
    segment_id: str | None = Field(default=None, alias="segmentId", pattern=_ID_PATTERN)

    @field_validator("sigma", mode="before")
    @classmethod
    def reject_invalid_sigma(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_unit_sigma(self) -> "CanonicalNode":
        _validate_unit_interval(self.sigma, self.sigma, field_name="sigma")
        return self


class SourceSegmentAllowedTargetIntervals(AxiomModel):
    source_segment_id: str = Field(alias="sourceSegmentId", min_length=1, pattern=_ID_PATTERN)
    allowed_target_intervals: tuple[tuple[float, float], ...] = Field(
        alias="allowedTargetIntervals",
        min_length=1,
    )

    @field_validator("allowed_target_intervals", mode="before")
    @classmethod
    def reject_invalid_intervals(cls, value: Any) -> Any:
        if isinstance(value, list):
            for interval in value:
                _require_finite_vector(interval, expected=2, field_name="allowedTargetIntervals")
        return value

    @model_validator(mode="after")
    def require_valid_intervals(self) -> "SourceSegmentAllowedTargetIntervals":
        cursor = 0.0
        for interval in self.allowed_target_intervals:
            _validate_unit_interval(interval[0], interval[1], field_name="allowedTargetIntervals")
            if interval[0] < cursor - _EPSILON:
                raise ValueError("allowedTargetIntervals must be sorted and non-overlapping")
            cursor = interval[1]
        return self


class SelectedNodeMapping(AxiomModel):
    source_node_id: str = Field(alias="sourceNodeId", min_length=1, pattern=_ID_PATTERN)
    target_node_id: str = Field(alias="targetNodeId", min_length=1, pattern=_ID_PATTERN)


class CorrespondenceCertificate(AxiomModel):
    certificate_id: str = Field(alias="certificateId", min_length=1, pattern=_ID_PATTERN)
    source_geometry_id: str = Field(alias="sourceGeometryId", min_length=1, pattern=_ID_PATTERN)
    target_reference_path_id: str = Field(alias="targetReferencePathId", min_length=1, pattern=_ID_PATTERN)
    policy: CorrespondencePolicy
    canonical_nodes: tuple[CanonicalNode, ...] = Field(alias="canonicalNodes", min_length=1)
    allowed_source_intervals: tuple[SourceSegmentAllowedTargetIntervals, ...] = Field(
        alias="allowedSourceIntervals",
        min_length=1,
    )
    selected_node_mapping: tuple[SelectedNodeMapping, ...] = Field(alias="selectedNodeMapping", min_length=1)
    intervals: tuple[CorrespondenceInterval, ...] = Field(min_length=1)
    primary_objective_lower: float = Field(alias="primaryObjectiveLower")
    primary_objective_upper: float = Field(alias="primaryObjectiveUpper")
    objective_domain: Literal["continuous", "canonical-grid"] = Field(alias="objectiveDomain")
    tie_break_objective: str = Field(alias="tieBreakObjective", min_length=1)
    numeric_tolerance: NumericTolerance = Field(alias="numericTolerance")
    solver_version: str = Field(alias="solverVersion", min_length=1)
    evidence_level: Literal["machine-replayable", "certificate-summary"] = Field(alias="evidenceLevel")
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @field_validator("primary_objective_lower", "primary_objective_upper", mode="before")
    @classmethod
    def reject_invalid_objectives(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_policy_bounded_coverage(self) -> "CorrespondenceCertificate":
        _require_unique_ids(self.intervals, attr="interval_id", field_name="intervals")
        _require_unique_ids(self.canonical_nodes, attr="node_id", field_name="canonicalNodes")
        _require_unique_ids(self.allowed_source_intervals, attr="source_segment_id", field_name="allowedSourceIntervals")
        if len({(item.source_node_id, item.target_node_id) for item in self.selected_node_mapping}) != len(
            self.selected_node_mapping
        ):
            raise ValueError("selectedNodeMapping must not contain duplicate pairs")
        if len({item.source_node_id for item in self.selected_node_mapping}) != len(self.selected_node_mapping):
            raise ValueError("selectedNodeMapping sourceNodeId must be unique")
        if len({item.target_node_id for item in self.selected_node_mapping}) != len(self.selected_node_mapping):
            raise ValueError("selectedNodeMapping targetNodeId must be unique")
        _validate_interval_coverage(
            self.intervals,
            start_attr="source_sigma_start",
            end_attr="source_sigma_end",
            field_name="intervals(source)",
            start_bound=self.policy.allowed_source_interval[0],
            end_bound=self.policy.allowed_source_interval[1],
        )
        _validate_interval_coverage(
            self.intervals,
            start_attr="target_sigma_start",
            end_attr="target_sigma_end",
            field_name="intervals(target)",
            start_bound=self.policy.allowed_target_interval[0],
            end_bound=self.policy.allowed_target_interval[1],
        )
        if self.primary_objective_upper < self.primary_objective_lower:
            raise ValueError("primaryObjectiveUpper must be >= primaryObjectiveLower")
        canonical_source_nodes = {node.node_id for node in self.canonical_nodes if node.path_role == "source"}
        canonical_target_nodes = {node.node_id for node in self.canonical_nodes if node.path_role == "target"}
        if any(item.source_node_id not in canonical_source_nodes for item in self.selected_node_mapping):
            raise ValueError("selectedNodeMapping sourceNodeId must reference canonical source nodes")
        if any(item.target_node_id not in canonical_target_nodes for item in self.selected_node_mapping):
            raise ValueError("selectedNodeMapping targetNodeId must reference canonical target nodes")
        for item in self.allowed_source_intervals:
            for interval in item.allowed_target_intervals:
                if interval[0] < self.policy.allowed_target_interval[0] - _EPSILON:
                    raise ValueError("allowedSourceIntervals must stay within the policy target interval")
                if interval[1] > self.policy.allowed_target_interval[1] + _EPSILON:
                    raise ValueError("allowedSourceIntervals must stay within the policy target interval")
        return self


class AxisAlignedBoundingBox(AxiomModel):
    min_corner: tuple[float, float, float] = Field(alias="minCorner")
    max_corner: tuple[float, float, float] = Field(alias="maxCorner")

    @field_validator("min_corner", "max_corner", mode="before")
    @classmethod
    def reject_invalid_corner(cls, value: Any) -> Any:
        return _require_finite_vector(value, expected=3, field_name="corner")

    @model_validator(mode="after")
    def require_valid_bounds(self) -> "AxisAlignedBoundingBox":
        if any(high < low for low, high in zip(self.min_corner, self.max_corner)):
            raise ValueError("AABB maxCorner must be >= minCorner component-wise")
        return self


class ToolComponent(AxiomModel):
    component_id: str = Field(alias="componentId", min_length=1, pattern=_ID_PATTERN)
    component_kind: Literal["cutter", "shaft", "holder"] = Field(alias="componentKind")
    shape_type: Literal["sphere", "capsule"] = Field(alias="shapeType")
    radius: float = Field(gt=0)
    axis_start_offset: float = Field(alias="axisStartOffset")
    axis_end_offset: float = Field(alias="axisEndOffset")

    @field_validator("radius", "axis_start_offset", "axis_end_offset", mode="before")
    @classmethod
    def reject_invalid_shape_numbers(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_unique_shape_semantics(self) -> "ToolComponent":
        if self.axis_end_offset < self.axis_start_offset:
            raise ValueError("axisEndOffset must be >= axisStartOffset")
        if self.shape_type == "sphere" and not math.isclose(
            self.axis_start_offset,
            self.axis_end_offset,
            abs_tol=1e-9,
        ):
            raise ValueError("sphere components require equal axis offsets")
        return self


class StockFixtureAABB(AxiomModel):
    stock_fixture_id: str = Field(alias="stockFixtureId", min_length=1, pattern=_ID_PATTERN)
    category: Literal["stock", "fixture"] = Field(alias="category")
    aabb: AxisAlignedBoundingBox


class ContactRule(AxiomModel):
    rule_id: str = Field(alias="ruleId", min_length=1, pattern=_ID_PATTERN)
    left_category: _CONTACT_CATEGORY = Field(alias="leftCategory")
    right_category: _CONTACT_CATEGORY = Field(alias="rightCategory")
    contact_policy: Literal["allowed", "forbidden"] = Field(alias="contactPolicy")

    @model_validator(mode="after")
    def require_distinct_categories(self) -> "ContactRule":
        if self.left_category == self.right_category:
            raise ValueError("ContactRule must describe two distinct categories")
        return self


class AllowedRemoval(AxiomModel):
    removal_id: str = Field(alias="removalId", min_length=1, pattern=_ID_PATTERN)
    tool_component_id: str = Field(alias="toolComponentId", min_length=1, pattern=_ID_PATTERN)
    stock_fixture_id: str = Field(alias="stockFixtureId", min_length=1, pattern=_ID_PATTERN)
    region: AxisAlignedBoundingBox | None = None


class ContactPolicy(AxiomModel):
    policy_id: Literal["five-axis.contact-policy.explicit@1"] = Field(alias="policyId")
    default_policy: Literal["forbidden"] = Field(default="forbidden", alias="defaultPolicy")
    rules: tuple[ContactRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_rules(self) -> "ContactPolicy":
        _require_unique_ids(self.rules, attr="rule_id", field_name="rules")
        return self


class StockUpdatePolicy(AxiomModel):
    policy_id: Literal["five-axis.stock-update.explicit-snapshot@1", "five-axis.stock-update.nominal-sweep@1"] = (
        Field(alias="policyId")
    )


class FailureStateSemantics(AxiomModel):
    policy_id: Literal["five-axis.process-state.failure-terminal@1"] = Field(alias="policyId")
    failed_state_meaning: Literal["last-input-state-persists"] = Field(alias="failedStateMeaning")


class CollisionContext(AxiomModel):
    context_id: str = Field(alias="contextId", min_length=1, pattern=_ID_PATTERN)
    tool_components: tuple[ToolComponent, ...] = Field(alias="toolComponents", min_length=1)
    stock_fixtures: tuple[StockFixtureAABB, ...] = Field(alias="stockFixtures", min_length=1)
    allowed_removal: tuple[AllowedRemoval, ...] = Field(alias="allowedRemoval", min_length=1)
    minimum_clearance: NumericTolerance = Field(alias="minimumClearance")
    solver_tolerance: NumericTolerance = Field(alias="solverTolerance")
    envelope_tolerance: NumericTolerance = Field(alias="envelopeTolerance")
    contact_policy: ContactPolicy = Field(alias="contactPolicy")
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_unique_component_ids(self) -> "CollisionContext":
        _require_unique_ids(self.tool_components, attr="component_id", field_name="toolComponents")
        _require_unique_ids(self.stock_fixtures, attr="stock_fixture_id", field_name="stockFixtures")
        _require_unique_ids(self.allowed_removal, attr="removal_id", field_name="allowedRemoval")
        tool_ids = {item.component_id for item in self.tool_components}
        tool_kinds = {item.component_kind for item in self.tool_components}
        stock_ids = {item.stock_fixture_id for item in self.stock_fixtures if item.category == "stock"}
        if any(item.tool_component_id not in tool_ids for item in self.allowed_removal):
            raise ValueError("allowedRemoval toolComponentId must reference toolComponents")
        if any(item.stock_fixture_id not in stock_ids for item in self.allowed_removal):
            raise ValueError("allowedRemoval stockFixtureId must reference stock stockFixtures")
        explicit_categories = tool_kinds | {item.category for item in self.stock_fixtures} | {"machine"}
        for rule in self.contact_policy.rules:
            if rule.left_category not in explicit_categories or rule.right_category not in explicit_categories:
                raise ValueError("ContactRule categories must align with explicit cutter/shaft/holder/stock/fixture/machine taxonomy")
        if len({tuple(sorted((rule.left_category, rule.right_category))) for rule in self.contact_policy.rules}) != len(
            self.contact_policy.rules
        ):
            raise ValueError("ContactPolicy rules must not repeat category pairs")
        return self


class StockStateRef(AxiomModel):
    state_id: str = Field(alias="stateId", min_length=1, pattern=_ID_PATTERN)
    content_id: str = Field(alias="contentId", pattern=_CONTENT_HASH_PATTERN)


class ProcessStateInterval(AxiomModel):
    interval_id: str = Field(alias="intervalId", min_length=1, pattern=_ID_PATTERN)
    sigma_start: float = Field(alias="sigmaStart")
    sigma_end: float = Field(alias="sigmaEnd")
    motion_mode: Literal["rapid", "cut", "dwell", "approach", "retract"] = Field(alias="motionMode")
    spindle_state: Literal["off", "cw", "ccw"] = Field(alias="spindleState")
    tool_component_id: str | None = Field(default=None, alias="toolComponentId", pattern=_ID_PATTERN)
    coolant_on: bool = Field(alias="coolantOn")
    input_stock_state: StockStateRef = Field(alias="inputStockState")
    output_stock_state: StockStateRef | None = Field(default=None, alias="outputStockState")

    @field_validator("sigma_start", "sigma_end", mode="before")
    @classmethod
    def reject_invalid_sigma(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_valid_interval(self) -> "ProcessStateInterval":
        _validate_unit_interval(self.sigma_start, self.sigma_end, field_name="sigma")
        if math.isclose(self.sigma_start, self.sigma_end, abs_tol=_EPSILON):
            raise ValueError("ProcessStateInterval must have positive sigma extent")
        return self


class ProcessStateTimeline(AxiomModel):
    timeline_id: str = Field(alias="timelineId", min_length=1, pattern=_ID_PATTERN)
    stock_update_policy: StockUpdatePolicy = Field(alias="stockUpdatePolicy")
    failure_state_semantics: FailureStateSemantics = Field(alias="failureStateSemantics")
    intervals: tuple[ProcessStateInterval, ...] = Field(min_length=1)
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_unit_coverage(self) -> "ProcessStateTimeline":
        _require_unique_ids(self.intervals, attr="interval_id", field_name="intervals")
        _validate_interval_coverage(
            self.intervals,
            start_attr="sigma_start",
            end_attr="sigma_end",
            field_name="intervals",
        )
        if self.stock_update_policy.policy_id == "five-axis.stock-update.explicit-snapshot@1":
            if any(interval.output_stock_state is None for interval in self.intervals):
                raise ValueError("explicit-snapshot stockUpdatePolicy requires outputStockState on every interval")
        for left, right in zip(self.intervals, self.intervals[1:]):
            if left.output_stock_state is not None:
                if left.output_stock_state != right.input_stock_state:
                    raise ValueError("adjacent process-state intervals must chain outputStockState to next inputStockState")
        return self


class ToleranceBinding(AxiomModel):
    tolerance_id: str = Field(alias="toleranceId", min_length=1, pattern=_ID_PATTERN)
    target: Literal["position", "orientation", "sigma", "collision-clearance"]
    tolerance: NumericTolerance

    @model_validator(mode="after")
    def require_compatible_unit(self) -> "ToleranceBinding":
        if self.target == "orientation" and self.tolerance.unit not in {"rad", "deg"}:
            raise ValueError("orientation tolerance must use rad or deg")
        if self.target == "sigma":
            if self.tolerance.unit != "dimensionless":
                raise ValueError("sigma tolerance must be dimensionless")
            if self.tolerance.absolute > 1.0 + _EPSILON:
                raise ValueError("sigma tolerance absolute value must stay within [0, 1]")
        return self


class M2CandidateTaskGeometry(AxiomModel):
    artifact_type: Literal["five-axis.m2-candidate-task-geometry"] = Field(alias="artifactType")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    candidate_geometry_id: str = Field(alias="candidateGeometryId", min_length=1, pattern=_ID_PATTERN)
    source_reference_path_id: str = Field(alias="sourceReferencePathId", min_length=1, pattern=_ID_PATTERN)
    source_reference_path_content_id: str | None = Field(
        default=None,
        alias="sourceReferencePathContentId",
        pattern=_CONTENT_HASH_PATTERN,
    )
    coordinate_context: CoordinateContext = Field(alias="coordinateContext")
    path_progress: PathProgress = Field(alias="pathProgress")
    position_semantics: Literal["continuous", "static"] = Field(default="continuous", alias="positionSemantics")
    static_position: tuple[float, float, float] | None = Field(default=None, alias="staticPosition")
    position_segments: tuple[PositionSegment, ...] = Field(alias="positionSegments", default_factory=tuple)
    orientation_segments: tuple[OrientationSegment, ...] = Field(alias="orientationSegments", default_factory=tuple)
    node_events: tuple[NodeEvent, ...] = Field(alias="nodeEvents", default_factory=tuple)
    regularity_certificate: RegularityCertificate | None = Field(default=None, alias="regularityCertificate")
    tolerances: tuple[ToleranceBinding, ...] = Field(min_length=1)
    correspondence: CorrespondenceCertificate
    collision_context: CollisionContext | None = Field(default=None, alias="collisionContext")
    process_state_timeline: ProcessStateTimeline | None = Field(default=None, alias="processStateTimeline")
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @field_validator("static_position", mode="before")
    @classmethod
    def reject_invalid_static_position(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_vector(value, expected=3, field_name="staticPosition")

    @model_validator(mode="after")
    def require_bound_geometry(self) -> "M2CandidateTaskGeometry":
        if not self.position_segments and not self.orientation_segments:
            raise ValueError("M2CandidateTaskGeometry requires positionSegments or orientationSegments")
        if self.position_segments and self.position_semantics != "continuous":
            raise ValueError("positionSemantics must be continuous when positionSegments are present")
        if not self.position_segments and self.position_semantics != "static":
            raise ValueError("positionSemantics must be static when positionSegments are absent")
        if not self.position_segments and self.static_position is None:
            raise ValueError("orientation-only paths require staticPosition")
        if self.position_segments and self.static_position is not None:
            raise ValueError("continuous position paths forbid staticPosition")
        _require_unique_ids(self.position_segments, attr="segment_id", field_name="positionSegments")
        _require_unique_ids(self.orientation_segments, attr="segment_id", field_name="orientationSegments")
        _require_unique_ids(self.node_events, attr="node_id", field_name="nodeEvents")
        _require_unique_ids(self.tolerances, attr="tolerance_id", field_name="tolerances")
        segment_ids = {segment.segment_id for segment in self.position_segments} | {
            segment.segment_id for segment in self.orientation_segments
        }
        if any(mapping.source_segment_id not in segment_ids for mapping in self.path_progress.mappings):
            raise ValueError("pathProgress mappings must target actual segments")
        if any(
            event.left_segment_id is not None and event.left_segment_id not in segment_ids
            for event in self.node_events
        ):
            raise ValueError("nodeEvents leftSegmentId must target actual segments")
        if any(
            event.right_segment_id is not None and event.right_segment_id not in segment_ids
            for event in self.node_events
        ):
            raise ValueError("nodeEvents rightSegmentId must target actual segments")
        if self.position_segments:
            _validate_interval_coverage(
                self.position_segments,
                start_attr="sigma_start",
                end_attr="sigma_end",
                field_name="positionSegments",
            )
        if self.orientation_segments:
            _validate_interval_coverage(
                self.orientation_segments,
                start_attr="sigma_start",
                end_attr="sigma_end",
                field_name="orientationSegments",
            )
        if self.regularity_certificate is not None:
            node_ids = {event.node_id for event in self.node_events}
            if any(item.segment_id not in segment_ids for item in self.regularity_certificate.segment_evidence):
                raise ValueError("regularityCertificate segment targets must match actual segments")
            if any(item.node_id not in node_ids for item in self.regularity_certificate.node_evidence):
                raise ValueError("regularityCertificate node targets must match actual nodeEvents")
        if self.correspondence.source_geometry_id != self.candidate_geometry_id:
            raise ValueError("correspondence sourceGeometryId must match M2 candidateGeometryId")
        if self.correspondence.target_reference_path_id != self.source_reference_path_id:
            raise ValueError("correspondence targetReferencePathId must match M2 sourceReferencePathId")
        source_node_ids = {event.node_id for event in self.node_events}
        canonical_source_nodes = {
            node.node_id: node
            for node in self.correspondence.canonical_nodes
            if node.path_role == "source"
        }
        if any(interval.source_segment_id is not None and interval.source_segment_id not in segment_ids for interval in self.correspondence.intervals):
            raise ValueError("correspondence sourceSegmentId must target actual M2 segments")
        if any(node.segment_id is not None and node.segment_id not in segment_ids for node in canonical_source_nodes.values()):
            raise ValueError("correspondence canonical source nodes must target actual M2 segments")
        if not source_node_ids.issubset(canonical_source_nodes):
            raise ValueError("correspondence canonical source nodes must include all M2 nodeEvents")
        if (self.collision_context is None) != (self.process_state_timeline is None):
            raise ValueError("collisionContext and processStateTimeline must both be present or both be absent")
        if self.collision_context is not None and self.process_state_timeline is not None:
            tool_component_ids = {component.component_id for component in self.collision_context.tool_components}
            if any(
                interval.tool_component_id is not None and interval.tool_component_id not in tool_component_ids
                for interval in self.process_state_timeline.intervals
            ):
                raise ValueError("processStateTimeline toolComponentId must reference collisionContext toolComponents")
        return self


class ArtifactDescriptor(AxiomModel):
    stage: Literal["M0", "M1", "M2"]
    artifact_type: str = Field(alias="artifactType", min_length=1)
    schema_id: str = Field(alias="schemaId", min_length=1, pattern=_VERSIONED_ID_PATTERN)

    @model_validator(mode="after")
    def require_frozen_descriptor(self) -> "ArtifactDescriptor":
        expected = {
            "M0": ("five-axis.normalized-program", "five-axis.normalized-program@1"),
            "M1": ("five-axis.m1-reference-path", "five-axis.m1-reference-path@1"),
            "M2": ("five-axis.m2-candidate-task-geometry", "five-axis.m2-candidate-task-geometry@1"),
        }[self.stage]
        if (self.artifact_type, self.schema_id) != expected:
            raise ValueError("ArtifactDescriptor must use the frozen F1 artifact/schema mapping")
        return self


class ExpectedMetric(AxiomModel):
    metric_id: str = Field(alias="metricId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    expected_status: Literal["Computed", "Inconclusive", "UnsupportedCapability", "InsufficientContext"] = Field(
        alias="expectedStatus"
    )
    expected_value: bool | float | None = Field(default=None, alias="expectedValue")
    unit: str | None = None

    @field_validator("expected_value", mode="before")
    @classmethod
    def reject_invalid_expected_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, bool):
            return value
        return _require_finite_json_number(value)


class ExpectedClaim(AxiomModel):
    claim_id: str = Field(alias="claimId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    claim_class: Literal["M0", "M1", "M2", "M3", "M4", "M5", "DeviceSafe"] = Field(alias="claimClass")
    expected_status: Literal["Supported", "Refuted", "Inconclusive", "Unsupported", "Insufficient"] = Field(
        alias="expectedStatus"
    )
    evidence_level: str | None = Field(default=None, alias="evidenceLevel")

    @model_validator(mode="after")
    def reject_forbidden_positive_claim(self) -> "ExpectedClaim":
        if self.claim_class in {"M3", "M4", "M5", "DeviceSafe"} and self.expected_status == "Supported":
            raise ValueError("F1MathStageManifest must not publish positive M3/M4/M5/DeviceSafe claims")
        if self.expected_status == "Supported" and self.claim_id not in {
            "five-axis.geometry-valid-claim@1",
            "five-axis.task-geometry-collision-free-claim@1",
        }:
            raise ValueError("F1MathStageManifest Supported claims must use the F1 whitelist IDs")
        return self


class ExpectedEvidence(AxiomModel):
    evidence_id: str = Field(alias="evidenceId", min_length=1, pattern=_ID_PATTERN)
    evidence_kind: Literal["lineage", "regularity", "correspondence", "collision", "process-state"] = Field(
        alias="evidenceKind"
    )
    required: bool


class StageDecision(AxiomModel):
    decision_id: str = Field(alias="decisionId", min_length=1, pattern=_ID_PATTERN)
    status: Literal["accepted", "rejected", "deferred"]
    rationale: str = Field(min_length=1)


class F1MathStageManifest(AxiomModel):
    manifest_id: Literal["five-axis.f1-math-stage-manifest@1"] = Field(alias="manifestId")
    schema_id: Literal["five-axis.f1-math-stage-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["F1"]
    artifact_descriptors: tuple[ArtifactDescriptor, ...] = Field(alias="artifactDescriptors", min_length=3)
    capability_ids: tuple[str, ...] = Field(alias="capabilityIds", min_length=1)
    fixture_content_ids: tuple[str, ...] = Field(alias="fixtureContentIds", min_length=1)
    policy_ids: tuple[str, ...] = Field(alias="policyIds", min_length=1)
    numeric_environment: dict[str, str] = Field(alias="numericEnvironment", min_length=1)
    expected_metrics: tuple[ExpectedMetric, ...] = Field(alias="expectedMetrics", min_length=1)
    expected_claims: tuple[ExpectedClaim, ...] = Field(alias="expectedClaims", min_length=1)
    expected_evidence: tuple[ExpectedEvidence, ...] = Field(alias="expectedEvidence", min_length=1)
    tolerances: tuple[ToleranceBinding, ...] = Field(min_length=1)
    decisions: tuple[StageDecision, ...] = Field(min_length=1)

    @field_validator("capability_ids", "policy_ids")
    @classmethod
    def require_unique_versioned_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("IDs must not contain duplicates")
        for item in value:
            if not isinstance(item, str) or not item:
                raise ValueError("IDs must not contain empty values")
            if re.fullmatch(_VERSIONED_ID_PATTERN, item) is None:
                raise ValueError("IDs must be versioned identifiers")
        return value

    @field_validator("fixture_content_ids")
    @classmethod
    def require_unique_fixture_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("fixtureContentIds must not contain duplicates")
        for item in value:
            if not isinstance(item, str) or re.fullmatch(_CONTENT_HASH_PATTERN, item) is None:
                raise ValueError("fixtureContentIds must contain content hashes")
        return value

    @model_validator(mode="after")
    def require_frozen_manifest_sets(self) -> "F1MathStageManifest":
        _require_unique_ids(self.artifact_descriptors, attr="stage", field_name="artifactDescriptors")
        _require_unique_ids(self.expected_metrics, attr="metric_id", field_name="expectedMetrics")
        _require_unique_ids(self.expected_claims, attr="claim_id", field_name="expectedClaims")
        _require_unique_ids(self.expected_evidence, attr="evidence_id", field_name="expectedEvidence")
        _require_unique_ids(self.tolerances, attr="tolerance_id", field_name="tolerances")
        _require_unique_ids(self.decisions, attr="decision_id", field_name="decisions")
        if tuple(descriptor.stage for descriptor in self.artifact_descriptors) != ("M0", "M1", "M2"):
            raise ValueError("artifactDescriptors must freeze M0, M1, M2 in order")
        return self


__all__ = [
    "ArcPositionSegment",
    "AxisAlignedBoundingBox",
    "BezierPositionSegment",
    "CollisionContext",
    "ConstantOrientationSegment",
    "ContactRule",
    "CoordinateContext",
    "CorrespondenceCertificate",
    "CorrespondenceInterval",
    "CorrespondencePolicy",
    "DerivativeValue",
    "DwellEvent",
    "FeedRateEvent",
    "FromEvent",
    "GotoEvent",
    "HelixPositionSegment",
    "LinePositionSegment",
    "M1ReferencePath",
    "M2CandidateTaskGeometry",
    "F1MathStageManifest",
    "ExpectedClaim",
    "ExpectedEvidence",
    "ExpectedMetric",
    "MonotoneMinimaxPolicy",
    "NodeEvent",
    "NodeRegularityEvidence",
    "NormalizedProgram",
    "NormalizedProgramEvent",
    "NumericTolerance",
    "PathProgress",
    "ProcessStateInterval",
    "ProcessStateTimeline",
    "ProvenanceProgressPolicy",
    "ProvenanceRef",
    "RegularityCertificate",
    "SegmentIntervalMapping",
    "SegmentRegularityEvidence",
    "SlerpOrientationSegment",
    "SourceLineage",
    "StageDecision",
    "StockFixtureAABB",
    "StockPolicy",
    "ToleranceBinding",
    "ToolComponent",
    "ArtifactDescriptor",
]
