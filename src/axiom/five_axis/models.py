from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel


_VERSIONED_ID_PATTERN = r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+@[1-9][0-9]*$"
_CONTENT_HASH_PATTERN = r"^[0-9a-f]{64}$"
_REGULARITY_CLASSES = ("C0", "C1", "C2", "G0", "G1", "G2", "unknown")


def _require_json_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("value must be a finite JSON number")
    return value


def _require_unique_strings(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return values


def _stage_envelope_payload(envelope: "StageEnvelope") -> dict[str, Any]:
    payload = envelope.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload.pop("contentId", None)
    return payload


def _stage_envelope_content_id(envelope: "StageEnvelope") -> str:
    canonical = json.dumps(
        _stage_envelope_payload(envelope),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CartesianCoordinateSpec(AxiomModel):
    coordinate_system: Literal["cartesian"] = Field(default="cartesian", alias="coordinateSystem")
    axes: tuple[Literal["X"], Literal["Y"], Literal["Z"]] = Field(default=("X", "Y", "Z"))
    unit: str = Field(min_length=1)
    coordinate_frame: str = Field(alias="coordinateFrame", min_length=1)

    @model_validator(mode="after")
    def require_xyz_axes(self) -> "CartesianCoordinateSpec":
        if self.axes != ("X", "Y", "Z"):
            raise ValueError("CartesianCoordinateSpec axes must be exactly ('X', 'Y', 'Z')")
        return self


class PathProgress(AxiomModel):
    progress_kind: Literal["arc-length", "time", "sample-index"] = Field(alias="progressKind")
    unit: str = Field(min_length=1)
    values: tuple[float, ...] = Field(min_length=1)

    @field_validator("values", mode="before")
    @classmethod
    def reject_non_numeric_values(cls, value: Any) -> Any:
        if isinstance(value, list):
            for item in value:
                _require_json_number(item)
        return value

    @model_validator(mode="after")
    def require_monotone_values(self) -> "PathProgress":
        if any(right < left for left, right in zip(self.values, self.values[1:])):
            raise ValueError("PathProgress values must be monotone nondecreasing")
        return self


class NodeEvent(AxiomModel):
    node_index: int = Field(alias="nodeIndex", ge=0)
    event_type: Literal["knot", "corner", "entry", "exit", "limit"] = Field(alias="eventType")
    regularity_class: Literal["C0", "C1", "C2", "G0", "G1", "G2", "unknown"] = Field(
        alias="regularityClass"
    )
    progress_value: float = Field(alias="progressValue")

    @field_validator("progress_value", mode="before")
    @classmethod
    def reject_invalid_progress(cls, value: Any) -> Any:
        return _require_json_number(value)


class RegularityProfile(AxiomModel):
    continuity_class: Literal["C0", "C1", "C2", "G0", "G1", "G2", "unknown"] = Field(
        alias="continuityClass"
    )
    node_events: tuple[NodeEvent, ...] = Field(default_factory=tuple, alias="nodeEvents")


class StageEnvelope(AxiomModel):
    envelope_id: str = Field(alias="envelopeId", pattern=_VERSIONED_ID_PATTERN)
    stage: Literal["M0", "M1", "M2", "M3", "M4", "M5"]
    envelope_type: Literal["artifact", "profile", "policy", "certificate"] = Field(alias="envelopeType")
    schema_id: str = Field(alias="schemaId", pattern=_VERSIONED_ID_PATTERN)
    content_id: str = Field(alias="contentId", pattern=_CONTENT_HASH_PATTERN)
    coordinate_spec: CartesianCoordinateSpec | None = Field(default=None, alias="coordinateSpec")
    capability_ids: tuple[str, ...] = Field(default_factory=tuple, alias="capabilityIds")

    @field_validator("capability_ids")
    @classmethod
    def require_unique_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique_strings(value, field_name="capabilityIds")

    @model_validator(mode="after")
    def require_content_id_match(self) -> "StageEnvelope":
        expected = _stage_envelope_content_id(self)
        if self.content_id != expected:
            raise ValueError("contentId must equal the canonical content hash of the envelope payload")
        return self


class CartesianSample(AxiomModel):
    sample_index: int = Field(alias="sampleIndex", ge=0)
    position: tuple[float, float, float]

    @field_validator("position", mode="before")
    @classmethod
    def reject_non_numeric_coordinates(cls, value: Any) -> Any:
        if isinstance(value, list):
            for coordinate in value:
                _require_json_number(coordinate)
        return value


class SampledCartesianPositionView(AxiomModel):
    artifact_type: Literal["five-axis.sampled-cartesian-position-view"] = Field(alias="artifactType")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    derived_view_kind: Literal["sampled-cartesian-derived-view@1"] = Field(alias="derivedViewKind")
    source_artifact_type: str = Field(alias="sourceArtifactType", min_length=1)
    source_coordinate_mode: Literal["cartesian-xyz", "joint", "mixed"] = Field(alias="sourceCoordinateMode")
    coordinate_spec: CartesianCoordinateSpec = Field(alias="coordinateSpec")
    samples: tuple[CartesianSample, ...] = Field(min_length=2)
    path_progress: PathProgress | None = Field(default=None, alias="pathProgress")
    regularity: RegularityProfile | None = None
    envelopes: tuple[StageEnvelope, ...] = Field(default_factory=tuple)
    capability_ids: tuple[str, ...] = Field(default_factory=tuple, alias="capabilityIds")

    @field_validator("capability_ids")
    @classmethod
    def require_unique_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique_strings(value, field_name="capabilityIds")

    @model_validator(mode="after")
    def require_aligned_sample_metadata(self) -> "SampledCartesianPositionView":
        expected_indices = tuple(range(len(self.samples)))
        actual_indices = tuple(sample.sample_index for sample in self.samples)
        if actual_indices != expected_indices:
            raise ValueError("Sample indices must be contiguous and zero-based")
        if self.path_progress is not None and len(self.path_progress.values) != len(self.samples):
            raise ValueError("PathProgress length must match the number of samples")
        return self


class ToleranceSpec(AxiomModel):
    metric_id: str = Field(alias="metricId", pattern=_VERSIONED_ID_PATTERN)
    unit: str = Field(min_length=1)
    value: float

    @field_validator("value", mode="before")
    @classmethod
    def reject_invalid_value(cls, value: Any) -> Any:
        return _require_json_number(value)


class ExpectedClaim(AxiomModel):
    claim_definition_id: str = Field(alias="claimDefinitionId", pattern=_VERSIONED_ID_PATTERN)
    status: Literal["Inconclusive", "Unsupported", "Insufficient"]
    reason_code: str | None = Field(default=None, alias="reasonCode")


class MathStageManifest(AxiomModel):
    manifest_id: str = Field(alias="manifestId", pattern=_VERSIONED_ID_PATTERN)
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["F0"]
    capability_ids: tuple[str, ...] = Field(alias="capabilityIds", min_length=1)
    fixture_content_ids: tuple[str, ...] = Field(alias="fixtureContentIds", min_length=1)
    policy_versions: dict[str, str] = Field(alias="policyVersions", min_length=1)
    numeric_environment: dict[str, str] = Field(alias="numericEnvironment", min_length=1)
    expected_status: Literal["Passed", "Inconclusive", "Unsupported", "Insufficient"] = Field(
        alias="expectedStatus"
    )
    expected_claim: ExpectedClaim | None = Field(default=None, alias="expectedClaim")
    tolerances: tuple[ToleranceSpec, ...] = Field(default_factory=tuple)
    envelopes: tuple[StageEnvelope, ...] = Field(min_length=6)

    @field_validator("capability_ids")
    @classmethod
    def require_unique_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique_strings(value, field_name="capabilityIds")

    @field_validator("fixture_content_ids")
    @classmethod
    def require_unique_fixture_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique_strings(value, field_name="fixtureContentIds")

    @field_validator("policy_versions")
    @classmethod
    def require_versioned_policy_ids(cls, value: dict[str, str]) -> dict[str, str]:
        for policy_id in value.values():
            if not isinstance(policy_id, str) or re.fullmatch(_VERSIONED_ID_PATTERN, policy_id) is None:
                raise ValueError("policyVersions values must be versioned IDs")
        return value

    @model_validator(mode="after")
    def require_stage_coverage(self) -> "MathStageManifest":
        if len(self.envelopes) != 6:
            raise ValueError("MathStageManifest must contain exactly six stage envelopes")
        stages = {envelope.stage for envelope in self.envelopes}
        if stages != {"M0", "M1", "M2", "M3", "M4", "M5"}:
            raise ValueError("MathStageManifest envelopes must cover M0 through M5 exactly once")
        return self
