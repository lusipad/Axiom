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
from .models import AxiomModel, CaseOutcome, ExecutionStatus, MetricStatus


ORDERED_POINT_DOMAIN_PACK_ID = "ordered-point.domain-pack@1"
ORDERED_POINT_EVALUATOR_ID = "ordered-point-evaluator@1"
ARTIFACT_IMPORT_RUNNER_ID = "artifact-import@1"
PYTHON_CALL_RUNNER_ID = "python-call@1"
CASE_OUTCOME_CLAIM_DEFINITION_ID = "axiom.core.case-outcome-claim@1"
METRIC_THRESHOLD_CLAIM_DEFINITION_ID = "axiom.core.metric-threshold-claim@1"
STRICT_COMPARISON_POLICY_ID = "ordered-point.run-comparison.strict@1"
EXPERIMENT_COMPARISON_POLICY_ID = "ordered-point.experiment-comparison.strict@1"
FORWARD_DIFFERENCE_POLICY_ID = "ordered-point.parameter-difference.forward-adjacent@1"
INTERVAL_ONLY_ENDPOINT_POLICY_ID = "ordered-point.parameter-endpoint.interval-only@1"
FLOAT_TOLERANCE = 1e-12


class FrozenDomainModel(AxiomModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", frozen=True)


class NumericTolerance(FrozenDomainModel):
    absolute: float
    relative: float
    unit: str | None = None


class MetricDefinition(FrozenDomainModel):
    metric_id: str = Field(alias="metricId")
    metric_definition_id: str = Field(alias="metricDefinitionId")
    requires: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    direction: Literal["lower-is-better", "higher-is-better"] | None = None
    difference_policy: str | None = Field(default=None, alias="differencePolicy")
    endpoint_policy: str | None = Field(default=None, alias="endpointPolicy")
    numeric_tolerance: NumericTolerance | None = Field(default=None, alias="numericTolerance")


class FailureMapping(FrozenDomainModel):
    code: str
    execution_status: ExecutionStatus = Field(alias="executionStatus")
    metric_status: MetricStatus = Field(alias="metricStatus")
    case_outcome: CaseOutcome = Field(alias="caseOutcome")


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
    failure_mappings: tuple[FailureMapping, ...] = Field(default_factory=tuple, alias="failureMappings")

    def metric_definition(self, metric_id: str) -> MetricDefinition:
        for definition in self.metric_definitions:
            if definition.metric_id == metric_id:
                return definition
        raise KeyError(metric_id)

    def supports_runner(self, runner_id: str) -> bool:
        return runner_id == self.runner_id or runner_id in self.runner_ids

    def failure_mapping(self, code: str) -> FailureMapping | None:
        for mapping in self.failure_mappings:
            if mapping.code == code:
                return mapping
        return None


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
            difference_policy=FORWARD_DIFFERENCE_POLICY_ID if metric_id in _TIME_METRICS else None,
            endpoint_policy=INTERVAL_ONLY_ENDPOINT_POLICY_ID if metric_id in _TIME_METRICS else None,
            numeric_tolerance=_metric_numeric_tolerance(metric_id),
        )
        for metric_id in metric_ids
    ]


def _metric_numeric_tolerance(metric_id: str) -> NumericTolerance:
    result_unit = "result-unit" if _metric_uses_result_unit(metric_id) else None
    if metric_id in {"point.count", "coordinate.dimension", "duplicate.consecutive.count", "segment.zero_length.count"}:
        return NumericTolerance(absolute=0.0, relative=0.0, unit=result_unit)
    if metric_id == "coordinate.finite":
        return NumericTolerance(absolute=0.0, relative=0.0)
    return NumericTolerance(absolute=FLOAT_TOLERANCE, relative=FLOAT_TOLERANCE, unit=result_unit)


def _metric_uses_result_unit(metric_id: str) -> bool:
    if metric_id in _REFERENCE_STRATEGIES or metric_id in _TIME_METRICS:
        return True
    return metric_id in {
        "bounds.axis_aligned",
        "path.length.open",
        "closure.gap",
        "path.length.closed",
        "step.length.min",
        "step.length.max",
        "step.length.mean",
        "step.length.rms",
        "step.length.std",
    }


_DEFAULT_FAILURE_MAPPINGS = (
    FailureMapping(
        code="MalformedRunSpec",
        executionStatus="Skipped",
        metricStatus="InvalidObservation",
        caseOutcome="Invalid",
    ),
    FailureMapping(
        code="MalformedEvaluationRequest",
        executionStatus="Skipped",
        metricStatus="InvalidObservation",
        caseOutcome="Invalid",
    ),
    FailureMapping(
        code="UnknownDomainPack",
        executionStatus="Skipped",
        metricStatus="UnsupportedCapability",
        caseOutcome="Unsupported",
    ),
    FailureMapping(
        code="DomainPackEvaluatorUnavailable",
        executionStatus="Skipped",
        metricStatus="UnsupportedCapability",
        caseOutcome="Unsupported",
    ),
    FailureMapping(
        code="ArtifactTypeMismatch",
        executionStatus="Skipped",
        metricStatus="InvalidObservation",
        caseOutcome="Invalid",
    ),
    FailureMapping(
        code="ArtifactSchemaVersionMismatch",
        executionStatus="Skipped",
        metricStatus="InvalidObservation",
        caseOutcome="Invalid",
    ),
    FailureMapping(
        code="RunnerMismatch",
        executionStatus="Skipped",
        metricStatus="UnsupportedCapability",
        caseOutcome="Unsupported",
    ),
    FailureMapping(
        code="EvaluatorVersionMismatch",
        executionStatus="Skipped",
        metricStatus="UnsupportedCapability",
        caseOutcome="Unsupported",
    ),
    FailureMapping(
        code="DomainEvaluatorFailed",
        executionStatus="ExecutionFailed",
        metricStatus="NumericalFailure",
        caseOutcome="Inconclusive",
    ),
)


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
        failure_mappings=_DEFAULT_FAILURE_MAPPINGS,
    )
)
