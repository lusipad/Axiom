from __future__ import annotations

from typing import Iterable, Literal

from pydantic import ConfigDict, Field

from .evaluator import (
    _CAP_CLOSED,
    _CAP_CORRESPONDENCE,
    _CAP_EUCLIDEAN,
    _CAP_FRAME,
    _CAP_ORDERED,
    _CAP_PARAMETER,
    _CAP_PARSED,
    _CAP_REFERENCE,
    _CAP_TIME,
    _CAP_UNIT,
    _CAP_VALID,
    _INTRINSIC_METRICS,
    _REFERENCE_STRATEGIES,
    _TIME_METRICS,
    _metric_requirements,
)
from .models import AxiomModel


ORDERED_POINT_DOMAIN_PACK_ID = "ordered-point.domain-pack@1"
ORDERED_POINT_EVALUATOR_ID = "ordered-point-evaluator@1"
ARTIFACT_IMPORT_RUNNER_ID = "artifact-import@1"
PYTHON_CALL_RUNNER_ID = "python-call@1"
CASE_OUTCOME_CLAIM_DEFINITION_ID = "axiom.core.case-outcome-claim@1"
METRIC_THRESHOLD_CLAIM_DEFINITION_ID = "axiom.core.metric-threshold-claim@1"
STRICT_COMPARISON_POLICY_ID = "ordered-point.run-comparison.strict@1"
EXPERIMENT_COMPARISON_POLICY_ID = "ordered-point.experiment-comparison.strict@1"


class FrozenDomainModel(AxiomModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)


class MetricDefinition(FrozenDomainModel):
    metric_id: str = Field(alias="metricId")
    metric_definition_id: str = Field(alias="metricDefinitionId")
    requires: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    direction: Literal["lower-is-better", "higher-is-better"] | None = None


class DomainPack(FrozenDomainModel):
    domain_pack_id: str = Field(alias="domainPackId")
    artifact_type: str = Field(alias="artifactType")
    artifact_schema_versions: tuple[int, ...] = Field(alias="artifactSchemaVersions", min_length=1)
    evaluator_version: str = Field(alias="evaluatorVersion")
    runner_id: str = Field(alias="runnerId")
    runner_ids: tuple[str, ...] = Field(default_factory=tuple, alias="runnerIds")
    capability_ids: tuple[str, ...] = Field(default_factory=tuple, alias="capabilityIds")
    metric_definitions: tuple[MetricDefinition, ...] = Field(default_factory=tuple, alias="metricDefinitions")
    claim_definition_ids: tuple[str, ...] = Field(default_factory=tuple, alias="claimDefinitionIds")
    comparison_policy_ids: tuple[str, ...] = Field(default_factory=tuple, alias="comparisonPolicyIds")

    def metric_definition(self, metric_id: str) -> MetricDefinition:
        for definition in self.metric_definitions:
            if definition.metric_id == metric_id:
                return definition
        raise KeyError(metric_id)

    def supports_runner(self, runner_id: str) -> bool:
        return runner_id == self.runner_id or runner_id in self.runner_ids


_DOMAIN_PACKS: dict[str, DomainPack] = {}


def register_domain_pack(pack: DomainPack) -> DomainPack:
    existing = _DOMAIN_PACKS.get(pack.domain_pack_id)
    if existing is not None:
        if existing != pack:
            raise ValueError(f"domain pack ID is already registered: {pack.domain_pack_id}")
        return existing
    _DOMAIN_PACKS[pack.domain_pack_id] = pack
    return pack


def get_domain_pack(domain_pack_id: str) -> DomainPack:
    try:
        return _DOMAIN_PACKS[domain_pack_id]
    except KeyError as exc:
        raise LookupError(f"unknown domain pack: {domain_pack_id}") from exc


def find_domain_pack(domain_pack_id: str) -> DomainPack | None:
    return _DOMAIN_PACKS.get(domain_pack_id)


def list_domain_packs() -> tuple[DomainPack, ...]:
    return tuple(_DOMAIN_PACKS[domain_pack_id] for domain_pack_id in sorted(_DOMAIN_PACKS))


def _ordered_point_metric_definitions() -> list[MetricDefinition]:
    metric_ids: Iterable[str] = sorted(
        set(_INTRINSIC_METRICS) | set(_TIME_METRICS) | set(_REFERENCE_STRATEGIES)
    )
    return [
        MetricDefinition(
            metric_id=metric_id,
            metric_definition_id=f"ordered-point.{metric_id}@1",
            requires=_metric_requirements(metric_id),
            direction="lower-is-better" if metric_id in _REFERENCE_STRATEGIES else None,
        )
        for metric_id in metric_ids
    ]


ORDERED_POINT_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domain_pack_id=ORDERED_POINT_DOMAIN_PACK_ID,
        artifact_type="ordered-point-sequence",
        artifact_schema_versions=[1],
        evaluator_version=ORDERED_POINT_EVALUATOR_ID,
        runner_id=ARTIFACT_IMPORT_RUNNER_ID,
        runner_ids=[ARTIFACT_IMPORT_RUNNER_ID, PYTHON_CALL_RUNNER_ID],
        capability_ids=sorted(
            {
                _CAP_PARSED,
                _CAP_VALID,
                _CAP_ORDERED,
                _CAP_EUCLIDEAN,
                _CAP_UNIT,
                _CAP_FRAME,
                _CAP_CLOSED,
                _CAP_REFERENCE,
                _CAP_CORRESPONDENCE,
                _CAP_PARAMETER,
                _CAP_TIME,
            }
        ),
        metric_definitions=_ordered_point_metric_definitions(),
        claim_definition_ids=[
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            METRIC_THRESHOLD_CLAIM_DEFINITION_ID,
        ],
        comparison_policy_ids=[STRICT_COMPARISON_POLICY_ID, EXPERIMENT_COMPARISON_POLICY_ID],
    )
)
