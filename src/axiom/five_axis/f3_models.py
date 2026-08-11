from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel
from .f1_models import ExpectedMetric, StageDecision
from .f2_models import M3CandidateAxisPath


_EPSILON = 1e-12
_CONTENT_HASH_PATTERN = r"^[0-9a-f]{64}$"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
_VERSIONED_ID_PATTERN = r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+@[1-9][0-9]*$"
_CONTINUOUSLY_FEASIBLE_CLAIM_ID = "five-axis.continuously-feasible-claim@1"
_INTERVAL_CERTIFIED_CLAIM_ID = "five-axis.interval-certified-claim@1"


def _require_finite_json_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
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


def _canonical_content_id(model: AxiomModel) -> str:
    payload = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ProvenanceRef(AxiomModel):
    source_stage: Literal["M0", "M1", "M2", "M3", "M4", "M5"] = Field(alias="sourceStage")
    source_id: str = Field(alias="sourceId", min_length=1, pattern=_ID_PATTERN)
    source_content_id: str | None = Field(default=None, alias="sourceContentId", pattern=_CONTENT_HASH_PATTERN)
    method: str | None = None


class NumericTolerance(AxiomModel):
    absolute: float = Field(ge=0.0)
    relative: float = Field(default=0.0, ge=0.0)
    unit: str = Field(min_length=1)

    @field_validator("absolute", "relative", mode="before")
    @classmethod
    def reject_invalid_tolerance(cls, value: Any) -> Any:
        return _require_finite_json_number(value)


class ToleranceBinding(AxiomModel):
    tolerance_id: str = Field(alias="toleranceId", min_length=1, pattern=_ID_PATTERN)
    target: Literal[
        "position",
        "orientation",
        "sigma",
        "collision-clearance",
        "time",
        "velocity",
        "acceleration",
        "jerk",
        "quantization",
    ]
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


class AxisMotionConstraint(AxiomModel):
    axis_id: str = Field(alias="axisId", min_length=1, pattern=_ID_PATTERN)
    unit: Literal["mm", "rad"]
    maximum_velocity: float = Field(alias="maximumVelocity", gt=0.0)
    maximum_acceleration: float = Field(alias="maximumAcceleration", gt=0.0)
    maximum_jerk: float | None = Field(default=None, alias="maximumJerk", gt=0.0)

    @field_validator("maximum_velocity", "maximum_acceleration", "maximum_jerk", mode="before")
    @classmethod
    def reject_invalid_limits(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_json_number(value)


class NodeMotionConstraint(AxiomModel):
    node_id: str = Field(alias="nodeId", min_length=1, pattern=_ID_PATTERN)
    sigma: float
    boundary_mode: Literal["allow-continuous", "mandatory-stop", "dwell"] = Field(alias="boundaryMode")
    dwell_seconds: float | None = Field(default=None, alias="dwellSeconds", gt=0.0)
    rationale: str | None = Field(default=None, min_length=1)

    @field_validator("sigma", "dwell_seconds", mode="before")
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_consistent_dwell(self) -> "NodeMotionConstraint":
        if self.sigma < -_EPSILON or self.sigma > 1.0 + _EPSILON:
            raise ValueError("sigma must stay within [0, 1]")
        if self.boundary_mode == "dwell" and self.dwell_seconds is None:
            raise ValueError("dwell boundaryMode requires dwellSeconds")
        if self.boundary_mode != "dwell" and self.dwell_seconds is not None:
            raise ValueError("only dwell boundaryMode may declare dwellSeconds")
        return self


class BoundaryState(AxiomModel):
    sigma_velocity: float = Field(alias="sigmaVelocity", ge=0.0)
    sigma_acceleration: float = Field(alias="sigmaAcceleration", ge=0.0)

    @field_validator("sigma_velocity", "sigma_acceleration", mode="before")
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        return _require_finite_json_number(value)


class MotionConstraintProfile(AxiomModel):
    artifact_type: Literal["five-axis.motion-constraint-profile"] = Field(alias="artifactType")
    schema_id: Literal["five-axis.motion-constraint-profile@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    profile_id: str = Field(alias="profileId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    machine_profile_id: str = Field(alias="machineProfileId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    machine_profile_content_id: str = Field(alias="machineProfileContentId", pattern=_CONTENT_HASH_PATTERN)
    axis_constraints: tuple[AxisMotionConstraint, ...] = Field(alias="axisConstraints", min_length=1)
    start_boundary: BoundaryState = Field(alias="startBoundary")
    end_boundary: BoundaryState = Field(alias="endBoundary")
    maximum_path_velocity: float | None = Field(default=None, alias="maximumPathVelocity", gt=0.0)
    path_velocity_unit: str | None = Field(default=None, alias="pathVelocityUnit", min_length=1)
    feed_source: str | None = Field(default=None, alias="feedSource", min_length=1)
    node_constraints: tuple[NodeMotionConstraint, ...] = Field(alias="nodeConstraints", default_factory=tuple)
    policy_ids: tuple[str, ...] = Field(alias="policyIds", min_length=1)
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @field_validator("maximum_path_velocity", mode="before")
    @classmethod
    def reject_invalid_maximum_path_velocity(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_json_number(value)

    @field_validator("policy_ids")
    @classmethod
    def require_unique_policy_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique_versioned_ids(value, field_name="policyIds")

    @model_validator(mode="after")
    def require_unique_targets(self) -> "MotionConstraintProfile":
        _require_unique_ids(self.axis_constraints, attr="axis_id", field_name="axisConstraints")
        _require_unique_ids(self.node_constraints, attr="node_id", field_name="nodeConstraints")
        if not any(item.maximum_velocity > 0.0 and item.maximum_acceleration > 0.0 for item in self.axis_constraints):
            raise ValueError("axisConstraints must declare at least one positive velocity/acceleration pair")
        if self.maximum_path_velocity is None:
            if self.path_velocity_unit is not None:
                raise ValueError("pathVelocityUnit requires maximumPathVelocity")
        elif self.path_velocity_unit is None:
            raise ValueError("maximumPathVelocity requires pathVelocityUnit")
        return self


class TrajectoryErrorLedgerEntry(AxiomModel):
    entry_id: str = Field(alias="entryId", min_length=1, pattern=_ID_PATTERN)
    quantity: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    source: str = Field(min_length=1)
    bound: float = Field(ge=0.0)
    method: str = Field(min_length=1)
    code: str = Field(min_length=1, pattern=_ID_PATTERN)
    severity: Literal["warning", "error"]
    message: str = Field(min_length=1)
    related_node_id: str | None = Field(default=None, alias="relatedNodeId", pattern=_ID_PATTERN)
    related_segment_id: str | None = Field(default=None, alias="relatedSegmentId", pattern=_ID_PATTERN)

    @field_validator("bound", mode="before")
    @classmethod
    def reject_invalid_bound(cls, value: Any) -> Any:
        return _require_finite_json_number(value)


class RealizedNodeContract(AxiomModel):
    node_id: str = Field(alias="nodeId", min_length=1, pattern=_ID_PATTERN)
    sigma: float
    event_type: str = Field(alias="eventType", min_length=1)
    boundary_mode: Literal["allow-continuous", "mandatory-stop", "dwell"] = Field(alias="boundaryMode")
    dwell_seconds: float | None = Field(default=None, alias="dwellSeconds", ge=0.0)
    source: Literal["regularity", "event-type", "profile"] = Field(min_length=1)

    @field_validator("sigma", "dwell_seconds", mode="before")
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_json_number(value)


class AxisConstraintUsage(AxiomModel):
    axis_id: str = Field(alias="axisId", min_length=1, pattern=_ID_PATTERN)
    unit: Literal["mm", "rad"]
    maximum_velocity: float = Field(alias="maximumVelocity", ge=0.0)
    velocity_limit: float = Field(alias="velocityLimit", gt=0.0)
    maximum_acceleration: float = Field(alias="maximumAcceleration", ge=0.0)
    acceleration_limit: float = Field(alias="accelerationLimit", gt=0.0)
    maximum_jerk: float | None = Field(default=None, alias="maximumJerk", ge=0.0)
    jerk_limit: float | None = Field(default=None, alias="jerkLimit", gt=0.0)

    @field_validator(
        "maximum_velocity",
        "velocity_limit",
        "maximum_acceleration",
        "acceleration_limit",
        "maximum_jerk",
        "jerk_limit",
        mode="before",
    )
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_json_number(value)


class TrajectoryOptimality(AxiomModel):
    classification: Literal["ProvenOptimal", "Bounded", "FeasibleOnly", "NotApplicable"]
    proof_gap_seconds: float | None = Field(default=None, alias="proofGapSeconds", ge=0.0)
    rationale: str = Field(min_length=1)

    @field_validator("proof_gap_seconds", mode="before")
    @classmethod
    def reject_invalid_gap(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_gap_for_proven_optimal(self) -> "TrajectoryOptimality":
        if self.classification == "ProvenOptimal":
            if self.proof_gap_seconds is None or not math.isclose(self.proof_gap_seconds, 0.0, abs_tol=_EPSILON):
                raise ValueError("ProvenOptimal requires proofGapSeconds=0")
        if self.classification == "Bounded" and self.proof_gap_seconds is None:
            raise ValueError("Bounded requires proofGapSeconds")
        if self.classification in {"FeasibleOnly", "NotApplicable"} and self.proof_gap_seconds is not None:
            raise ValueError("only ProvenOptimal and Bounded may declare proofGapSeconds")
        return self


class TimeLawDefinition(AxiomModel):
    law_kind: Literal["triangular", "trapezoidal", "smoothstep7", "dwell"] = Field(alias="lawKind")
    duration_seconds: float = Field(alias="durationSeconds", ge=0.0)
    acceleration_duration_seconds: float | None = Field(default=None, alias="accelerationDurationSeconds", ge=0.0)
    cruise_duration_seconds: float | None = Field(default=None, alias="cruiseDurationSeconds", ge=0.0)
    deceleration_duration_seconds: float | None = Field(default=None, alias="decelerationDurationSeconds", ge=0.0)
    sigma_velocity_limit: float | None = Field(default=None, alias="sigmaVelocityLimit", gt=0.0)
    sigma_acceleration_limit: float | None = Field(default=None, alias="sigmaAccelerationLimit", gt=0.0)
    sigma_jerk_limit: float | None = Field(default=None, alias="sigmaJerkLimit", gt=0.0)
    peak_sigma_velocity: float = Field(alias="peakSigmaVelocity", ge=0.0)
    peak_sigma_acceleration: float = Field(alias="peakSigmaAcceleration", ge=0.0)
    peak_sigma_jerk: float = Field(alias="peakSigmaJerk", ge=0.0)

    @field_validator(
        "duration_seconds",
        "acceleration_duration_seconds",
        "cruise_duration_seconds",
        "deceleration_duration_seconds",
        "sigma_velocity_limit",
        "sigma_acceleration_limit",
        "sigma_jerk_limit",
        "peak_sigma_velocity",
        "peak_sigma_acceleration",
        "peak_sigma_jerk",
        mode="before",
    )
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        if value is None:
            return value
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_law_consistency(self) -> "TimeLawDefinition":
        if self.law_kind == "dwell":
            if any(
                item is not None
                for item in (
                    self.acceleration_duration_seconds,
                    self.cruise_duration_seconds,
                    self.deceleration_duration_seconds,
                    self.sigma_velocity_limit,
                    self.sigma_acceleration_limit,
                    self.sigma_jerk_limit,
                )
            ):
                raise ValueError("dwell laws must not declare motion subphase or sigma limit fields")
            if self.peak_sigma_velocity != 0.0 or self.peak_sigma_acceleration != 0.0 or self.peak_sigma_jerk != 0.0:
                raise ValueError("dwell laws must have zero peak sigma derivatives")
            return self
        if self.duration_seconds <= 0.0:
            raise ValueError("motion laws must have positive durationSeconds")
        if self.sigma_velocity_limit is None or self.sigma_acceleration_limit is None:
            raise ValueError("motion laws must declare sigmaVelocityLimit and sigmaAccelerationLimit")
        if self.law_kind in {"triangular", "trapezoidal"}:
            if self.acceleration_duration_seconds is None or self.deceleration_duration_seconds is None:
                raise ValueError("second-order laws must declare acceleration/deceleration durations")
        if self.law_kind == "smoothstep7" and self.sigma_jerk_limit is None:
            raise ValueError("smoothstep7 laws must declare sigmaJerkLimit")
        return self


class ContinuousTrajectorySpan(AxiomModel):
    span_id: str = Field(alias="spanId", min_length=1, pattern=_ID_PATTERN)
    span_kind: Literal["move", "dwell"] = Field(alias="spanKind")
    segment_ids: tuple[str, ...] = Field(alias="segmentIds", default_factory=tuple)
    start_time_seconds: float = Field(alias="startTimeSeconds", ge=0.0)
    end_time_seconds: float = Field(alias="endTimeSeconds", ge=0.0)
    sigma_start: float = Field(alias="sigmaStart")
    sigma_end: float = Field(alias="sigmaEnd")
    time_law: TimeLawDefinition = Field(alias="timeLaw")

    @field_validator("start_time_seconds", "end_time_seconds", "sigma_start", "sigma_end", mode="before")
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_valid_intervals(self) -> "ContinuousTrajectorySpan":
        if self.end_time_seconds < self.start_time_seconds - _EPSILON:
            raise ValueError("span time bounds must be monotone nondecreasing")
        if self.sigma_start < -_EPSILON or self.sigma_end > 1.0 + _EPSILON or self.sigma_end < self.sigma_start - _EPSILON:
            raise ValueError("span sigma bounds must stay within [0, 1] and be monotone nondecreasing")
        if self.span_kind == "move":
            if not self.segment_ids:
                raise ValueError("move spans must reference at least one segmentId")
            if math.isclose(self.sigma_start, self.sigma_end, abs_tol=_EPSILON):
                raise ValueError("move spans must cover positive sigma extent")
        else:
            if not math.isclose(self.sigma_start, self.sigma_end, abs_tol=_EPSILON):
                raise ValueError("dwell spans must keep sigma constant")
            if self.time_law.law_kind != "dwell":
                raise ValueError("dwell spans must use a dwell timeLaw")
        return self


class ContinuousTrajectoryState(AxiomModel):
    time_seconds: float = Field(alias="timeSeconds", ge=0.0)
    span_id: str = Field(alias="spanId", min_length=1, pattern=_ID_PATTERN)
    sigma: float
    sigma_velocity: float = Field(alias="sigmaVelocity")
    sigma_acceleration: float = Field(alias="sigmaAcceleration")
    sigma_jerk: float = Field(alias="sigmaJerk")
    joint_position: tuple[float, ...] = Field(alias="jointPosition", min_length=1)
    joint_velocity: tuple[float, ...] = Field(alias="jointVelocity", min_length=1)
    joint_acceleration: tuple[float, ...] = Field(alias="jointAcceleration", min_length=1)
    joint_jerk: tuple[float, ...] = Field(alias="jointJerk", min_length=1)

    @field_validator(
        "time_seconds",
        "sigma",
        "sigma_velocity",
        "sigma_acceleration",
        "sigma_jerk",
        mode="before",
    )
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @field_validator("joint_position", "joint_velocity", "joint_acceleration", "joint_jerk", mode="before")
    @classmethod
    def reject_invalid_vectors(cls, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            for item in value:
                _require_finite_json_number(item)
        return value


class ContinuousTrajectoryVerification(AxiomModel):
    verification_id: str = Field(alias="verificationId", min_length=1, pattern=_ID_PATTERN)
    solver_id: str = Field(alias="solverId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    evidence_level: Literal["Certified", "Validated", "Observed"] = Field(alias="evidenceLevel")
    claim_id: Literal["five-axis.continuously-feasible-claim@1"] = Field(alias="claimId")
    overall_status: Literal["Supported", "Unsupported", "Refuted"] = Field(alias="overallStatus")
    total_duration_seconds: float = Field(alias="totalDurationSeconds", ge=0.0)
    optimality: TrajectoryOptimality
    node_contracts: tuple[RealizedNodeContract, ...] = Field(alias="nodeContracts", default_factory=tuple)
    axis_constraint_usage: tuple[AxisConstraintUsage, ...] = Field(alias="axisConstraintUsage", default_factory=tuple)
    error_ledger: tuple[TrajectoryErrorLedgerEntry, ...] = Field(alias="errorLedger", default_factory=tuple)

    @field_validator("total_duration_seconds", mode="before")
    @classmethod
    def reject_invalid_duration(cls, value: Any) -> Any:
        return _require_finite_json_number(value)

    @model_validator(mode="after")
    def require_unique_targets(self) -> "ContinuousTrajectoryVerification":
        _require_unique_ids(self.node_contracts, attr="node_id", field_name="nodeContracts")
        _require_unique_ids(self.axis_constraint_usage, attr="axis_id", field_name="axisConstraintUsage")
        _require_unique_ids(self.error_ledger, attr="entry_id", field_name="errorLedger")
        if self.overall_status == "Supported" and any(item.severity == "error" for item in self.error_ledger):
            raise ValueError("Supported verification must not carry error-severity ledger entries")
        return self


class M4ContinuousTrajectory(AxiomModel):
    artifact_type: Literal["five-axis.m4-continuous-trajectory"] = Field(alias="artifactType")
    schema_id: Literal["five-axis.m4-continuous-trajectory@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    trajectory_id: str = Field(alias="trajectoryId", min_length=1, pattern=_ID_PATTERN)
    source_axis_path: M3CandidateAxisPath = Field(alias="sourceAxisPath")
    source_axis_path_content_id: str = Field(alias="sourceAxisPathContentId", pattern=_CONTENT_HASH_PATTERN)
    motion_constraint_profile: MotionConstraintProfile = Field(alias="motionConstraintProfile")
    motion_constraint_profile_content_id: str = Field(alias="motionConstraintProfileContentId", pattern=_CONTENT_HASH_PATTERN)
    solver_id: str = Field(alias="solverId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    timing_mode: Literal["second-order-optimal", "smoothstep7-feasible"] = Field(alias="timingMode")
    spans: tuple[ContinuousTrajectorySpan, ...] = Field(min_length=0)
    verification: ContinuousTrajectoryVerification
    provenance: tuple[ProvenanceRef, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def require_bound_inputs(self) -> "M4ContinuousTrajectory":
        if self.motion_constraint_profile.machine_profile_id != self.source_axis_path.machine_profile.profile_id:
            raise ValueError("motionConstraintProfile machineProfileId must match sourceAxisPath machineProfile profileId")
        if self.motion_constraint_profile.machine_profile_content_id != self.source_axis_path.machine_profile_content_id:
            raise ValueError(
                "motionConstraintProfile machineProfileContentId must match sourceAxisPath machineProfileContentId"
            )
        if self.source_axis_path_content_id != _canonical_content_id(self.source_axis_path):
            raise ValueError("sourceAxisPathContentId must equal the canonical content hash of sourceAxisPath")
        if self.motion_constraint_profile_content_id != _canonical_content_id(self.motion_constraint_profile):
            raise ValueError(
                "motionConstraintProfileContentId must equal the canonical content hash of motionConstraintProfile"
            )
        cursor = 0.0
        for span in self.spans:
            if span.start_time_seconds < cursor - _EPSILON:
                raise ValueError("spans must be serialized in nondecreasing time order")
            if span.start_time_seconds > cursor + _EPSILON:
                raise ValueError("spans must not contain time gaps")
            cursor = span.end_time_seconds
        if self.spans and not math.isclose(cursor, self.verification.total_duration_seconds, abs_tol=1e-9):
            raise ValueError("verification totalDurationSeconds must equal the end of the final span")
        if not self.spans and not math.isclose(self.verification.total_duration_seconds, 0.0, abs_tol=_EPSILON):
            raise ValueError("empty trajectories must use totalDurationSeconds=0")
        return self


class ArtifactDescriptor(AxiomModel):
    stage: Literal["M0", "M1", "M2", "M3", "M4", "M5"]
    artifact_type: str = Field(alias="artifactType", min_length=1)
    schema_id: str = Field(alias="schemaId", min_length=1, pattern=_VERSIONED_ID_PATTERN)

    @model_validator(mode="after")
    def require_frozen_descriptor(self) -> "ArtifactDescriptor":
        expected_pairs = {
            "M0": ("five-axis.normalized-program", "five-axis.normalized-program@1"),
            "M1": ("five-axis.m1-reference-path", "five-axis.m1-reference-path@1"),
            "M2": ("five-axis.m2-candidate-task-geometry", "five-axis.m2-candidate-task-geometry@1"),
            "M3": ("five-axis.m3-candidate-axis-path", "five-axis.m3-candidate-axis-path@1"),
            "M4": ("five-axis.m4-continuous-trajectory", "five-axis.m4-continuous-trajectory@1"),
            "M5": (
                ("five-axis.m5-sampled-trajectory", "five-axis.m5-sampled-trajectory@1"),
                ("five-axis.m5-discrete-command", "five-axis.m5-discrete-command@1"),
            ),
        }
        allowed = expected_pairs[self.stage]
        if self.stage != "M5":
            allowed = (allowed,)
        if (self.artifact_type, self.schema_id) not in allowed:
            raise ValueError("ArtifactDescriptor must use the frozen F3 artifact/schema mapping")
        return self


class ExpectedClaim(AxiomModel):
    claim_id: str = Field(alias="claimId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    claim_class: Literal["M0", "M1", "M2", "M3", "M4", "M5", "DeviceSafe"] = Field(alias="claimClass")
    expected_status: Literal["Supported", "Refuted", "Inconclusive", "Unsupported", "Insufficient"] = Field(
        alias="expectedStatus"
    )
    evidence_level: str | None = Field(default=None, alias="evidenceLevel")

    @model_validator(mode="after")
    def reject_forbidden_positive_claims(self) -> "ExpectedClaim":
        if self.expected_status != "Supported":
            return self
        if (self.claim_class, self.claim_id) not in {
            ("M4", _CONTINUOUSLY_FEASIBLE_CLAIM_ID),
            ("M5", _INTERVAL_CERTIFIED_CLAIM_ID),
        }:
            raise ValueError("F3MathStageManifest Supported claims must use the F3 M4/M5 whitelist IDs")
        return self


class ExpectedEvidence(AxiomModel):
    evidence_id: str = Field(alias="evidenceId", min_length=1, pattern=_ID_PATTERN)
    evidence_kind: Literal[
        "lineage",
        "regularity",
        "correspondence",
        "ik-branch",
        "wrap",
        "kinematics",
        "configuration-collision",
        "singularity",
        "time-law",
        "node-contract",
        "reconstruction",
        "error-ledger",
    ] = Field(alias="evidenceKind")
    required: bool


class F3MathStageManifest(AxiomModel):
    manifest_id: Literal["five-axis.f3-math-stage-manifest@1"] = Field(alias="manifestId")
    schema_id: Literal["five-axis.f3-math-stage-manifest@1"] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    stage: Literal["F3"]
    artifact_descriptors: tuple[ArtifactDescriptor, ...] = Field(alias="artifactDescriptors", min_length=6)
    motion_constraint_profile_schema_id: Literal["five-axis.motion-constraint-profile@1"] = Field(
        alias="motionConstraintProfileSchemaId"
    )
    motion_constraint_profile_id: str = Field(alias="motionConstraintProfileId", min_length=1, pattern=_VERSIONED_ID_PATTERN)
    motion_constraint_profile_content_id: str = Field(alias="motionConstraintProfileContentId", pattern=_CONTENT_HASH_PATTERN)
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
    def require_frozen_manifest_sets(self) -> "F3MathStageManifest":
        _require_unique_ids(self.artifact_descriptors, attr="stage", field_name="artifactDescriptors")
        _require_unique_ids(self.expected_metrics, attr="metric_id", field_name="expectedMetrics")
        _require_unique_ids(self.expected_claims, attr="claim_id", field_name="expectedClaims")
        _require_unique_ids(self.expected_evidence, attr="evidence_id", field_name="expectedEvidence")
        _require_unique_ids(self.tolerances, attr="tolerance_id", field_name="tolerances")
        _require_unique_ids(self.decisions, attr="decision_id", field_name="decisions")
        if tuple(descriptor.stage for descriptor in self.artifact_descriptors) != ("M0", "M1", "M2", "M3", "M4", "M5"):
            raise ValueError("artifactDescriptors must freeze M0 through M5 in order")
        return self


__all__ = [
    "ArtifactDescriptor",
    "AxisConstraintUsage",
    "AxisMotionConstraint",
    "BoundaryState",
    "ContinuousTrajectorySpan",
    "ContinuousTrajectoryState",
    "ContinuousTrajectoryVerification",
    "ExpectedClaim",
    "ExpectedEvidence",
    "F3MathStageManifest",
    "M4ContinuousTrajectory",
    "MotionConstraintProfile",
    "NodeMotionConstraint",
    "NumericTolerance",
    "ProvenanceRef",
    "RealizedNodeContract",
    "TimeLawDefinition",
    "ToleranceBinding",
    "TrajectoryErrorLedgerEntry",
    "TrajectoryOptimality",
]
