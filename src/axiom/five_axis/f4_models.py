from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..evaluator import _content_hash
from ..models import AxiomModel
from .f1_models import ExpectedMetric, StageDecision
from .f2_kinematics import normalize_numeric_identity
from .f3_models import ArtifactDescriptor, ToleranceBinding

_EPSILON = 1e-12
_CONTENT_HASH_PATTERN = r"^[0-9a-f]{64}$"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_VERSIONED_ID_PATTERN = r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+@[1-9][0-9]*$"
_CANONICAL_TOPOLOGIES = ("dual-table", "head-table", "dual-head")
_GATE_CLAIM_IDS = {
    "five-axis.geometry-valid-claim@1": "M2",
    "five-axis.task-geometry-collision-free-claim@1": "M2",
    "five-axis.kinematically-feasible-claim@1": "M3",
    "five-axis.configuration-collision-free-claim@1": "M3",
    "five-axis.continuously-feasible-claim@1": "M4",
    "five-axis.interval-certified-claim@1": "M5",
    "five-axis.model-collision-free-claim@1": "M5",
}
_FORBIDDEN_GATE_CLAIM_IDS = {
    "five-axis.device-safe-claim@1",
    "five-axis.process-safe-claim@1",
}


def _require_finite_json_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be a finite JSON number")
    if value != value or value in {float("inf"), float("-inf")}:
        raise ValueError("value must be a finite JSON number")
    return value


def _require_unique_ids(items: tuple[Any, ...], *, attr: str, field_name: str) -> tuple[Any, ...]:
    values = tuple(getattr(item, attr) for item in items)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicate IDs")
    return items


def _require_unique_versioned_ids(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} must not contain duplicates")
    for item in values:
        if re.fullmatch(_VERSIONED_ID_PATTERN, item) is None:
            raise ValueError(f"{field_name} must contain versioned identifiers")
    return values


def _normalized_content_hash(payload: Any) -> str:
    serializable = payload.model_dump(mode="json", by_alias=True, exclude_none=True) if hasattr(payload, "model_dump") else payload
    return _content_hash(normalize_numeric_identity(serializable))


def _self_content_hash(model: AxiomModel, *, exclude: set[str]) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True, exclude=exclude)
    return _content_hash(normalize_numeric_identity(payload))


class AdapterDescriptor(AxiomModel):
    adapter_id: str = Field(alias="adapterId", min_length=1, pattern=_ID_PATTERN)
    version: str = Field(min_length=1)
    role: Literal["reference", "sut"]
    subject_id: str = Field(alias="subjectId", min_length=1, pattern=_ID_PATTERN)
    subject_version: str = Field(alias="subjectVersion", min_length=1)
    input_type: Literal["five-axis.m4-continuous-trajectory"] = Field(alias="inputType")
    output_type: Literal["five-axis.m5-discrete-command"] = Field(alias="outputType")
    transport: Literal["in-process"]


class AdapterInvocation(AxiomModel):
    invocation_id: str = Field(alias="invocationId", min_length=1, pattern=_ID_PATTERN)
    descriptor: AdapterDescriptor
    input_m4_id: str = Field(alias="inputM4Id", min_length=1, pattern=_ID_PATTERN)
    input_m4_content_hash: str = Field(alias="inputM4ContentHash", pattern=_CONTENT_HASH_PATTERN)
    policy_id: str = Field(alias="policyId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    sample_period: float = Field(alias="samplePeriod", gt=0.0)
    final_hold: bool = Field(alias="finalHold")

    @field_validator("sample_period", mode="before")
    @classmethod
    def reject_invalid_sample_period(cls, value: Any) -> Any:
        return _require_finite_json_number(value)


class AdapterReceipt(AxiomModel):
    invocation: AdapterInvocation
    descriptor: AdapterDescriptor
    status: Literal["Succeeded", "Failed", "Unsupported"]
    input_content_hash: str = Field(alias="inputContentHash", pattern=_CONTENT_HASH_PATTERN)
    output_content_hash: str | None = Field(default=None, alias="outputContentHash", pattern=_CONTENT_HASH_PATTERN)
    deterministic_work_units: int = Field(alias="deterministicWorkUnits", ge=0)
    failure_code: str | None = Field(default=None, alias="failureCode", min_length=1, pattern=_ID_PATTERN)
    failure_message: str | None = Field(default=None, alias="failureMessage", min_length=1)
    numeric_environment: dict[str, str] = Field(alias="numericEnvironment", min_length=1)

    @model_validator(mode="after")
    def require_consistent_identity_and_outcome(self) -> "AdapterReceipt":
        if self.descriptor != self.invocation.descriptor:
            raise ValueError("descriptor must equal invocation.descriptor")
        if any(not isinstance(key, str) or not key or not isinstance(value, str) or not value for key, value in self.numeric_environment.items()):
            raise ValueError("numericEnvironment must contain non-empty string keys and values")
        if self.status == "Succeeded":
            if self.input_content_hash != self.invocation.input_m4_content_hash:
                raise ValueError("Succeeded receipts require inputContentHash to equal invocation.inputM4ContentHash")
            if self.output_content_hash is None:
                raise ValueError("Succeeded receipts require outputContentHash")
            if self.failure_code is not None or self.failure_message is not None:
                raise ValueError("Succeeded receipts must not declare failureCode or failureMessage")
            return self
        if self.output_content_hash is not None:
            raise ValueError("Failed or Unsupported receipts must not declare outputContentHash")
        if self.failure_code is None or self.failure_message is None:
            raise ValueError("Failed or Unsupported receipts require failureCode and failureMessage")
        return self


class CrossValidationResult(AxiomModel):
    reference_content_hash: str = Field(alias="referenceContentHash", pattern=_CONTENT_HASH_PATTERN)
    sut_content_hash: str = Field(alias="sutContentHash", pattern=_CONTENT_HASH_PATTERN)
    status: Literal["Supported", "Refuted", "Inconclusive"]
    max_position_gap: float = Field(alias="maxPositionGap", ge=0.0)
    max_velocity_gap: float = Field(alias="maxVelocityGap", ge=0.0)
    max_acceleration_gap: float = Field(alias="maxAccelerationGap", ge=0.0)
    max_jerk_gap: float = Field(alias="maxJerkGap", ge=0.0)
    tolerances: tuple[ToleranceBinding, ...] = Field(min_length=4)
    evidence_level: Literal["Exact", "Validated", "Certified"] = Field(alias="evidenceLevel")
    method: str = Field(min_length=1)

    @field_validator(
        "max_position_gap",
        "max_velocity_gap",
        "max_acceleration_gap",
        "max_jerk_gap",
        mode="before",
    )
    @classmethod
    def reject_invalid_gap(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_consistent_tolerances_and_status(self) -> "CrossValidationResult":
        _require_unique_ids(self.tolerances, attr="tolerance_id", field_name="tolerances")
        targets = {item.target for item in self.tolerances}
        if targets != {"position", "velocity", "acceleration", "jerk"}:
            raise ValueError("tolerances must cover position, velocity, acceleration, and jerk exactly once")
        tolerance_by_target = {item.target: item.tolerance.absolute for item in self.tolerances}
        if self.status == "Supported":
            if self.max_position_gap > tolerance_by_target["position"] + _EPSILON:
                raise ValueError("Supported cross-validation requires maxPositionGap to satisfy tolerances")
            if self.max_velocity_gap > tolerance_by_target["velocity"] + _EPSILON:
                raise ValueError("Supported cross-validation requires maxVelocityGap to satisfy tolerances")
            if self.max_acceleration_gap > tolerance_by_target["acceleration"] + _EPSILON:
                raise ValueError("Supported cross-validation requires maxAccelerationGap to satisfy tolerances")
            if self.max_jerk_gap > tolerance_by_target["jerk"] + _EPSILON:
                raise ValueError("Supported cross-validation requires maxJerkGap to satisfy tolerances")
        return self


class M5CollisionIntervalResult(AxiomModel):
    interval_id: str = Field(alias="intervalId", min_length=1, pattern=_ID_PATTERN)
    t_start: float = Field(alias="tStart")
    t_end: float = Field(alias="tEnd")
    status: Literal["safe", "collision", "unsupported", "unresolved"]
    witness_time: float | None = Field(default=None, alias="witnessTime")
    minimum_clearance_lower_bound: float | None = Field(default=None, alias="minimumClearanceLowerBound")
    reason_code: str | None = Field(default=None, alias="reasonCode", min_length=1, pattern=_ID_PATTERN)

    @field_validator("t_start", "t_end", "witness_time", "minimum_clearance_lower_bound", mode="before")
    @classmethod
    def reject_invalid_time(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_consistent_witness(self) -> "M5CollisionIntervalResult":
        if self.t_end <= self.t_start:
            raise ValueError("tEnd must be greater than tStart")
        if self.status == "safe":
            if self.reason_code is not None:
                raise ValueError("safe interval results must not declare reasonCode")
            if self.minimum_clearance_lower_bound is not None and self.minimum_clearance_lower_bound < -_EPSILON:
                raise ValueError("safe interval results must not declare a negative minimumClearanceLowerBound")
            return self
        if self.status == "collision":
            if self.witness_time is None:
                raise ValueError("collision interval results require witnessTime")
            if not (self.t_start - _EPSILON <= self.witness_time <= self.t_end + _EPSILON):
                raise ValueError("witnessTime must lie within [tStart, tEnd]")
            return self
        if self.reason_code is None:
            raise ValueError("unsupported or unresolved interval results require reasonCode")
        return self


class M5CollisionVerification(AxiomModel):
    contributes_to_claim_id: Literal["five-axis.model-collision-free-claim@1"] = Field(
        default="five-axis.model-collision-free-claim@1",
        alias="contributesToClaimId",
    )
    command_id: str = Field(alias="commandId", min_length=1, pattern=_ID_PATTERN)
    command_content_hash: str = Field(alias="commandContentHash", pattern=_CONTENT_HASH_PATTERN)
    source_m3_id: str = Field(alias="sourceM3Id", min_length=1, pattern=_ID_PATTERN)
    source_m3_content_hash: str = Field(alias="sourceM3ContentHash", pattern=_CONTENT_HASH_PATTERN)
    collision_model_id: str = Field(alias="collisionModelId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    collision_model_content_hash: str = Field(alias="collisionModelContentHash", pattern=_CONTENT_HASH_PATTERN)
    reconstruction_policy_id: str = Field(alias="reconstructionPolicyId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    status: Literal["safe", "collision", "unsupported", "unresolved"]
    coverage_status: Literal["complete", "partial"] = Field(alias="coverageStatus")
    supports_model_collision_aggregation: bool = Field(alias="supportsModelCollisionAggregation")
    evidence_level: Literal["Certified", "Validated", "Observed"] = Field(alias="evidenceLevel")
    method: str = Field(min_length=1)
    interval_evaluations: tuple[M5CollisionIntervalResult, ...] = Field(alias="intervalEvaluations", min_length=1)

    @model_validator(mode="after")
    def require_consistent_status(self) -> "M5CollisionVerification":
        _require_unique_ids(self.interval_evaluations, attr="interval_id", field_name="intervalEvaluations")
        derived_status = "safe"
        statuses = {item.status for item in self.interval_evaluations}
        if "collision" in statuses:
            derived_status = "collision"
        elif "unresolved" in statuses:
            derived_status = "unresolved"
        elif "unsupported" in statuses:
            derived_status = "unsupported"
        if self.status != derived_status:
            raise ValueError("status must match the aggregate intervalEvaluations status")
        if self.supports_model_collision_aggregation and (
            self.status != "safe" or self.coverage_status != "complete"
        ):
            raise ValueError("supportsModelCollisionAggregation may be true only for safe results with complete coverage")
        return self


class ExpectedClaim(AxiomModel):
    claim_id: str = Field(alias="claimId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    claim_class: Literal["M0", "M1", "M2", "M3", "M4", "M5", "DeviceSafe", "ProcessSafe"] = Field(alias="claimClass")
    expected_status: Literal["Supported", "Refuted", "Inconclusive", "Unsupported", "Insufficient"] = Field(
        alias="expectedStatus"
    )
    evidence_level: str | None = Field(default=None, alias="evidenceLevel")

    @model_validator(mode="after")
    def require_gate_whitelist(self) -> "ExpectedClaim":
        if self.claim_id in _FORBIDDEN_GATE_CLAIM_IDS or self.claim_class in {"DeviceSafe", "ProcessSafe"}:
            raise ValueError("F4MathStageManifest must not publish DeviceSafe or ProcessSafe claims")
        expected_class = _GATE_CLAIM_IDS.get(self.claim_id)
        if expected_class is None:
            raise ValueError("F4MathStageManifest claims must use the frozen seven-gate whitelist")
        if self.claim_class != expected_class:
            raise ValueError("claimClass must match the frozen F4 gate whitelist")
        if self.expected_status != "Supported":
            raise ValueError("F4MathStageManifest gate claims must all be Supported")
        return self


class ExpectedEvidence(AxiomModel):
    evidence_id: str = Field(alias="evidenceId", min_length=1, pattern=_ID_PATTERN)
    evidence_kind: Literal[
        "adapter-descriptor",
        "adapter-invocation",
        "adapter-receipt",
        "cross-validation",
        "reconstruction-collision",
        "stage-acceptance",
    ] = Field(alias="evidenceKind")
    required: bool


class F4MathStageManifest(AxiomModel):
    manifest_id: Literal["five-axis.f4-math-stage-manifest@1"] = Field(alias="manifestId")
    schema_id: Literal["five-axis.f4-math-stage-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["F4"]
    artifact_descriptors: tuple[ArtifactDescriptor, ...] = Field(alias="artifactDescriptors", min_length=6)
    adapter_transport: Literal["in-process"] = Field(alias="adapterTransport")
    capability_ids: tuple[str, ...] = Field(alias="capabilityIds", min_length=1)
    fixture_content_ids: tuple[str, ...] = Field(alias="fixtureContentIds", min_length=1)
    policy_ids: tuple[str, ...] = Field(alias="policyIds", min_length=1)
    numeric_environment: dict[str, str] = Field(alias="numericEnvironment", min_length=1)
    expected_metrics: tuple[ExpectedMetric, ...] = Field(alias="expectedMetrics", min_length=1)
    expected_claims: tuple[ExpectedClaim, ...] = Field(alias="expectedClaims", min_length=7, max_length=7)
    expected_evidence: tuple[ExpectedEvidence, ...] = Field(alias="expectedEvidence", min_length=1)
    tolerances: tuple[ToleranceBinding, ...] = Field(min_length=1)
    decisions: tuple[StageDecision, ...] = Field(min_length=1)

    @field_validator("capability_ids", "policy_ids")
    @classmethod
    def require_unique_versioned_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique_versioned_ids(value, field_name="IDs")

    @field_validator("fixture_content_ids")
    @classmethod
    def require_unique_fixture_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("fixtureContentIds must not contain duplicates")
        for item in value:
            if re.fullmatch(_CONTENT_HASH_PATTERN, item) is None:
                raise ValueError("fixtureContentIds must contain content hashes")
        return value

    @model_validator(mode="after")
    def require_frozen_manifest_sets(self) -> "F4MathStageManifest":
        _require_unique_ids(self.artifact_descriptors, attr="stage", field_name="artifactDescriptors")
        _require_unique_ids(self.expected_metrics, attr="metric_id", field_name="expectedMetrics")
        _require_unique_ids(self.expected_claims, attr="claim_id", field_name="expectedClaims")
        _require_unique_ids(self.expected_evidence, attr="evidence_id", field_name="expectedEvidence")
        _require_unique_ids(self.tolerances, attr="tolerance_id", field_name="tolerances")
        _require_unique_ids(self.decisions, attr="decision_id", field_name="decisions")
        if any(not isinstance(key, str) or not key or not isinstance(value, str) or not value for key, value in self.numeric_environment.items()):
            raise ValueError("numericEnvironment must contain non-empty string keys and values")
        if tuple(descriptor.stage for descriptor in self.artifact_descriptors) != ("M0", "M1", "M2", "M3", "M4", "M5"):
            raise ValueError("artifactDescriptors must freeze M0 through M5 in order")
        m5_descriptor = self.artifact_descriptors[-1]
        if (m5_descriptor.artifact_type, m5_descriptor.schema_id) != (
            "five-axis.m5-discrete-command",
            "five-axis.m5-discrete-command@1",
        ):
            raise ValueError("F4MathStageManifest must freeze M5 as five-axis.m5-discrete-command@1")
        if {claim.claim_id for claim in self.expected_claims} != set(_GATE_CLAIM_IDS):
            raise ValueError("expectedClaims must cover the frozen seven F4 math gate claims exactly once")
        return self


class GateClaimStatus(AxiomModel):
    claim_id: str = Field(alias="claimId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    status: Literal["Supported", "Refuted", "Inconclusive", "Unsupported", "Insufficient"]
    evidence_level: str | None = Field(default=None, alias="evidenceLevel")

    @model_validator(mode="after")
    def require_f4_gate_claim(self) -> "GateClaimStatus":
        if self.claim_id in _FORBIDDEN_GATE_CLAIM_IDS:
            raise ValueError("F4 stage gate claims must not include DeviceSafe or ProcessSafe")
        if self.claim_id not in _GATE_CLAIM_IDS:
            raise ValueError("F4 stage gate claims must use the frozen seven-gate whitelist")
        return self


class F4ScenarioResult(AxiomModel):
    scenario_id: str = Field(alias="scenarioId", min_length=1, pattern=_ID_PATTERN)
    topology: Literal["dual-table", "head-table", "dual-head"]
    sut_mode: Literal["solver", "replay"] = Field(alias="sutMode")
    counts_toward_closure: bool = Field(alias="countsTowardClosure")
    outcome: Literal["Passed", "Failed"]
    reference_receipt_status: Literal["Succeeded", "Failed", "Unsupported"] = Field(alias="referenceReceiptStatus")
    sut_receipt_status: Literal["Succeeded", "Failed", "Unsupported"] = Field(alias="sutReceiptStatus")
    cross_validation_status: Literal["Supported", "Refuted", "Inconclusive"] = Field(alias="crossValidationStatus")
    collision_status: Literal["safe", "collision", "unsupported", "unresolved"] = Field(alias="collisionStatus")

    @model_validator(mode="after")
    def require_replay_to_stay_out_of_closure(self) -> "F4ScenarioResult":
        if self.sut_mode == "replay" and self.counts_toward_closure:
            raise ValueError("replay SUT scenarios must not count toward closure")
        return self


class TopologyCoverage(AxiomModel):
    topology: Literal["dual-table", "head-table", "dual-head"]
    covered: bool


class CounterexampleCoverage(AxiomModel):
    counterexample_id: str = Field(alias="counterexampleId", min_length=1, pattern=_ID_PATTERN)
    covered: bool


class F4StageAcceptanceReport(AxiomModel):
    report_id: str = Field(alias="reportId", min_length=1, pattern=_ID_PATTERN)
    stage: Literal["F4"]
    scenario_results: tuple[F4ScenarioResult, ...] = Field(alias="scenarioResults", min_length=1)
    topology_coverage: tuple[TopologyCoverage, ...] = Field(alias="topologyCoverage", min_length=3, max_length=3)
    counterexample_coverage: tuple[CounterexampleCoverage, ...] = Field(alias="counterexampleCoverage", min_length=1)
    gate_claim_statuses: tuple[GateClaimStatus, ...] = Field(alias="gateClaimStatuses", min_length=7, max_length=7)
    status: Literal["Passed", "Failed"]
    content_hash: str = Field(alias="contentHash", pattern=_CONTENT_HASH_PATTERN)

    @model_validator(mode="after")
    def require_complete_gate_coverage(self) -> "F4StageAcceptanceReport":
        _require_unique_ids(self.scenario_results, attr="scenario_id", field_name="scenarioResults")
        _require_unique_ids(self.topology_coverage, attr="topology", field_name="topologyCoverage")
        _require_unique_ids(self.counterexample_coverage, attr="counterexample_id", field_name="counterexampleCoverage")
        _require_unique_ids(self.gate_claim_statuses, attr="claim_id", field_name="gateClaimStatuses")
        if tuple(item.topology for item in self.topology_coverage) != _CANONICAL_TOPOLOGIES:
            raise ValueError("topologyCoverage must freeze dual-table, head-table, dual-head in order")
        if {item.claim_id for item in self.gate_claim_statuses} != set(_GATE_CLAIM_IDS):
            raise ValueError("gateClaimStatuses must cover the frozen seven F4 math gate claims exactly once")
        if self.status == "Passed":
            if any(not item.covered for item in self.topology_coverage):
                raise ValueError("Passed reports require complete topologyCoverage")
            if any(not item.covered for item in self.counterexample_coverage):
                raise ValueError("Passed reports require complete counterexampleCoverage")
            if any(item.status != "Supported" for item in self.gate_claim_statuses):
                raise ValueError("Passed reports require every gate claim status to be Supported")
            if any(item.outcome != "Passed" for item in self.scenario_results):
                raise ValueError("Passed reports require every scenario outcome to be Passed")
        if self.content_hash != _self_content_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must equal the canonical content hash of the report payload")
        return self


__all__ = [
    "AdapterDescriptor",
    "AdapterInvocation",
    "AdapterReceipt",
    "CounterexampleCoverage",
    "CrossValidationResult",
    "ExpectedClaim",
    "ExpectedEvidence",
    "F4MathStageManifest",
    "F4ScenarioResult",
    "F4StageAcceptanceReport",
    "GateClaimStatus",
    "M5CollisionIntervalResult",
    "M5CollisionVerification",
    "TopologyCoverage",
]
