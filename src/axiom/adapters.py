from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import Field, field_validator

from .evaluator import _content_hash
from .models import AxiomModel, OrderedPointSequence
from .five_axis.models import SampledCartesianPositionView


_VERSIONED_ID_PATTERN = r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+@[1-9][0-9]*$"
_CONTENT_HASH_PATTERN = r"^[0-9a-f]{64}$"


class ArtifactAdapterProvenance(AxiomModel):
    adapter_id: str = Field(alias="adapterId", pattern=_VERSIONED_ID_PATTERN)
    source_artifact_type: str = Field(alias="sourceArtifactType", min_length=1)
    target_artifact_type: str = Field(alias="targetArtifactType", min_length=1)
    source_content_hash: str = Field(alias="sourceContentHash", pattern=_CONTENT_HASH_PATTERN)
    result_content_hash: str = Field(alias="resultContentHash", pattern=_CONTENT_HASH_PATTERN)
    preserved_semantics: list[str] = Field(default_factory=list, alias="preservedSemantics")
    dropped_semantics: list[str] = Field(default_factory=list, alias="droppedSemantics")

    @field_validator("preserved_semantics", "dropped_semantics")
    @classmethod
    def require_unique_semantics(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("semantics lists must not contain duplicates")
        return value


class ArtifactTransformationResult(AxiomModel):
    artifact: OrderedPointSequence | SampledCartesianPositionView
    content_hash: str = Field(alias="contentHash", pattern=_CONTENT_HASH_PATTERN)
    provenance: ArtifactAdapterProvenance


@dataclass(frozen=True)
class ArtifactAdapter:
    adapter_id: str
    source_artifact_type: str
    target_artifact_type: str
    transform: Callable[[object], ArtifactTransformationResult]

    def adapt(self, payload: object) -> ArtifactTransformationResult:
        return self.transform(payload)


_ADAPTERS_BY_ID: dict[str, ArtifactAdapter] = {}
_ADAPTERS_BY_ROUTE: dict[tuple[str, str], ArtifactAdapter] = {}


def register_artifact_adapter(adapter: ArtifactAdapter) -> ArtifactAdapter:
    existing = _ADAPTERS_BY_ID.get(adapter.adapter_id)
    if existing is not None:
        if existing != adapter:
            raise ValueError(f"adapter ID is already registered: {adapter.adapter_id}")
        return existing

    route = (adapter.source_artifact_type, adapter.target_artifact_type)
    conflicting_route = _ADAPTERS_BY_ROUTE.get(route)
    if conflicting_route is not None and conflicting_route != adapter:
        raise ValueError(
            "adapter route is already registered: "
            f"{adapter.source_artifact_type} -> {adapter.target_artifact_type}"
        )

    _ADAPTERS_BY_ID[adapter.adapter_id] = adapter
    _ADAPTERS_BY_ROUTE[route] = adapter
    return adapter


def get_artifact_adapter(source_artifact_type: str, target_artifact_type: str) -> ArtifactAdapter:
    route = (source_artifact_type, target_artifact_type)
    try:
        return _ADAPTERS_BY_ROUTE[route]
    except KeyError as exc:
        raise LookupError(f"unknown artifact adapter: {source_artifact_type} -> {target_artifact_type}") from exc


def list_artifact_adapters() -> tuple[ArtifactAdapter, ...]:
    return tuple(_ADAPTERS_BY_ID[adapter_id] for adapter_id in sorted(_ADAPTERS_BY_ID))


def _adapt_sampled_cartesian_view(payload: SampledCartesianPositionView) -> ArtifactTransformationResult:
    if payload.source_coordinate_mode != "cartesian-xyz":
        raise ValueError("only cartesian-xyz source semantics can adapt to ordered-point-sequence")

    artifact = OrderedPointSequence.model_validate(
        {
            "artifactType": "ordered-point-sequence",
            "schemaVersion": 1,
            "points": [list(sample.position) for sample in payload.samples],
            "semantics": {
                "unit": payload.coordinate_spec.unit,
                "coordinateFrame": payload.coordinate_spec.coordinate_frame,
            },
        }
    )
    result_hash = _content_hash(artifact)
    dropped_semantics = ["derivedViewKind"]
    if payload.path_progress is not None:
        dropped_semantics.append("pathProgress")
    if payload.regularity is not None:
        dropped_semantics.append("regularity")

    return ArtifactTransformationResult(
        artifact=artifact,
        content_hash=result_hash,
        provenance=ArtifactAdapterProvenance(
            adapter_id="five-axis.sampled-cartesian-to-ordered-point@1",
            source_artifact_type=payload.artifact_type,
            target_artifact_type=artifact.artifact_type,
            source_content_hash=_content_hash(payload),
            result_content_hash=result_hash,
            preserved_semantics=["coordinateFrame", "unit"],
            dropped_semantics=dropped_semantics,
        ),
    )


FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER = register_artifact_adapter(
    ArtifactAdapter(
        adapter_id="five-axis.sampled-cartesian-to-ordered-point@1",
        source_artifact_type="five-axis.sampled-cartesian-position-view",
        target_artifact_type="ordered-point-sequence",
        transform=_adapt_sampled_cartesian_view,
    )
)
