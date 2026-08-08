from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MAX_SEQUENCE_POINTS = 100_000


class AxiomModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")


def _require_json_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be a JSON number")
    return value


class ExecutionStatus(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCEEDED = "Succeeded"
    EXECUTION_FAILED = "ExecutionFailed"
    CANCELLED = "Cancelled"
    SKIPPED = "Skipped"


class MetricStatus(str, Enum):
    COMPUTED = "Computed"
    NOT_APPLICABLE = "NotApplicable"
    INSUFFICIENT_CONTEXT = "InsufficientContext"
    UNSUPPORTED_CAPABILITY = "UnsupportedCapability"
    INVALID_OBSERVATION = "InvalidObservation"
    NUMERICAL_FAILURE = "NumericalFailure"


class CaseOutcome(str, Enum):
    PASSED = "Passed"
    FAILED = "Failed"
    INCONCLUSIVE = "Inconclusive"
    UNSUPPORTED = "Unsupported"
    INVALID = "Invalid"


class PointSemantics(AxiomModel):
    unit: str | None = None
    coordinate_frame: str | None = Field(default=None, alias="coordinateFrame")
    closed: bool | None = None


class SequenceParameter(AxiomModel):
    kind: Literal["time"]
    unit: str | None = None
    values: list[float] = Field(max_length=MAX_SEQUENCE_POINTS)

    @field_validator("values", mode="before")
    @classmethod
    def reject_coerced_values(cls, value: Any) -> Any:
        if isinstance(value, list):
            for item in value:
                _require_json_number(item)
        return value


class OrderedPointSequence(AxiomModel):
    artifact_type: Literal["ordered-point-sequence"] = Field(alias="artifactType")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    points: list[list[float]] = Field(max_length=MAX_SEQUENCE_POINTS)
    semantics: PointSemantics | None = None
    parameter: SequenceParameter | None = None

    @field_validator("points", mode="before")
    @classmethod
    def reject_coerced_coordinates(cls, value: Any) -> Any:
        if isinstance(value, list):
            for point in value:
                if isinstance(point, list):
                    for coordinate in point:
                        _require_json_number(coordinate)
        return value


class Threshold(AxiomModel):
    operator: Literal["<=", "<", ">=", ">"]
    value: float = Field(allow_inf_nan=False)
    unit: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def reject_coerced_value(cls, value: Any) -> Any:
        return _require_json_number(value)


class MetricRequest(AxiomModel):
    metric_id: str = Field(alias="metricId", min_length=1)
    threshold: Threshold | None = None


class ScoreRule(AxiomModel):
    metric_id: str = Field(alias="metricId", min_length=1)
    direction: Literal["lower-is-better", "higher-is-better"]
    best: float = Field(allow_inf_nan=False)
    worst: float = Field(allow_inf_nan=False)
    weight: float = Field(gt=0, allow_inf_nan=False)
    unit: str | None = None

    @field_validator("best", "worst", "weight", mode="before")
    @classmethod
    def reject_coerced_values(cls, value: Any) -> Any:
        return _require_json_number(value)

    @model_validator(mode="after")
    def validate_endpoints(self) -> "ScoreRule":
        if self.direction == "lower-is-better" and not self.best < self.worst:
            raise ValueError("lower-is-better requires best < worst")
        if self.direction == "higher-is-better" and not self.best > self.worst:
            raise ValueError("higher-is-better requires best > worst")
        return self


class ScoreProfile(AxiomModel):
    profile_id: str = Field(alias="profileId", pattern=r"^.+@[0-9]+$")
    applicable_context: str = Field(alias="applicableContext", min_length=1)
    rules: list[ScoreRule] = Field(min_length=1)
    missing_value_policy: Literal["reject"] = Field(default="reject", alias="missingValuePolicy")


class EvaluationCase(AxiomModel):
    case_id: str = Field(alias="caseId", min_length=1)
    required_metrics: list[MetricRequest] = Field(alias="requiredMetrics", min_length=1)
    optional_metrics: list[MetricRequest] = Field(default_factory=list, alias="optionalMetrics")
    score_profile: ScoreProfile | None = Field(default=None, alias="scoreProfile")
    execution_outcome_policy: Literal["axiom.core.execution-outcome.default@1"] = Field(
        default="axiom.core.execution-outcome.default@1",
        alias="executionOutcomePolicy",
    )

    @field_validator("required_metrics", "optional_metrics", mode="before")
    @classmethod
    def expand_metric_shortcuts(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        return [{"metricId": item} if isinstance(item, str) else item for item in value]


class TolerancePolicy(AxiomModel):
    policy_id: str = Field(alias="policyId", min_length=1)
    value: float = Field(ge=0, allow_inf_nan=False)
    unit: str = Field(min_length=1)

    @field_validator("value", mode="before")
    @classmethod
    def reject_coerced_value(cls, value: Any) -> Any:
        return _require_json_number(value)


class ReferenceBinding(AxiomModel):
    reference: OrderedPointSequence
    alignment: str = Field(min_length=1)
    strategy_id: str = Field(alias="strategyId", min_length=1)
    distance_id: str = Field(alias="distanceId", min_length=1)
    tolerance: TolerancePolicy
    boundary_policy: str = Field(alias="boundaryPolicy", min_length=1)


class EvaluationRequest(AxiomModel):
    artifact: OrderedPointSequence
    case: EvaluationCase
    reference_binding: ReferenceBinding | None = Field(default=None, alias="referenceBinding")


class DomainFailure(AxiomModel):
    code: str
    message: str
    path: str | None = None
    severity: Literal["error", "finding"] = "error"


class CapabilityResolution(AxiomModel):
    capability_id: str = Field(alias="capabilityId")
    source: Literal["Artifact", "ReferenceBinding", "Evaluator"]


class Evidence(AxiomModel):
    level: Literal["Exact", "Certified", "Validated", "Observed"]
    method: str


class MetricResult(AxiomModel):
    metric_id: str = Field(alias="metricId")
    metric_definition_id: str = Field(alias="metricDefinitionId")
    requires: list[str] = Field(default_factory=list)
    status: MetricStatus
    value: Any = None
    unit: str | None = None
    threshold_passed: bool | None = Field(default=None, alias="thresholdPassed")
    reason_code: str | None = Field(default=None, alias="reasonCode")
    details: dict[str, Any] = Field(default_factory=dict)
    evidence: Evidence | None = None


class ScoreComponent(AxiomModel):
    metric_id: str = Field(alias="metricId")
    normalized_value: float = Field(alias="normalizedValue")
    weight: float


class ScoreResult(AxiomModel):
    profile_id: str = Field(alias="profileId")
    status: MetricStatus
    value: float | None = None
    reason_code: str | None = Field(default=None, alias="reasonCode")
    components: list[ScoreComponent] = Field(default_factory=list)


class Provenance(AxiomModel):
    request_hash: str = Field(alias="requestHash")
    artifact_hash: str = Field(alias="artifactHash")
    case_hash: str = Field(alias="caseHash")
    reference_hash: str | None = Field(default=None, alias="referenceHash")
    reference_binding_hash: str | None = Field(default=None, alias="referenceBindingHash")
    score_profile_hash: str | None = Field(default=None, alias="scoreProfileHash")
    runner_id: Literal["artifact-import@1"] = Field(default="artifact-import@1", alias="runnerId")
    evaluator_version: Literal["ordered-point-evaluator@1"] = Field(
        default="ordered-point-evaluator@1",
        alias="evaluatorVersion",
    )
    execution_outcome_policy: str = Field(alias="executionOutcomePolicy")
    numeric_type: Literal["float64"] = Field(default="float64", alias="numericType")
    numeric_environment: dict[str, str] = Field(alias="numericEnvironment")


class EvaluationReport(AxiomModel):
    execution_status: ExecutionStatus = Field(alias="executionStatus")
    case_outcome: CaseOutcome = Field(alias="caseOutcome")
    metric_results: list[MetricResult] = Field(default_factory=list, alias="metricResults")
    capabilities: list[CapabilityResolution] = Field(default_factory=list)
    domain_failures: list[DomainFailure] = Field(default_factory=list, alias="domainFailures")
    content_hash: str = Field(alias="contentHash")
    evaluator_version: str = Field(default="ordered-point-evaluator@1", alias="evaluatorVersion")
    provenance: Provenance | None = None
    score: ScoreResult | None = None

    def metric_result(self, metric_id: str) -> MetricResult:
        for result in self.metric_results:
            if result.metric_id == metric_id:
                return result
        raise KeyError(metric_id)
