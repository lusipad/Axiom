from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel, EvaluationCase, _require_json_number
from .models import AxisValidationSeries, CalibrationResult, PhysicalAxisParameter

FIVE_AXIS_REALITY_DOMAIN_PACK_ID = "five-axis.domain-pack@7"
PHYSICAL_REALITY_EVALUATOR_ID = "five-axis-physical-reality-evaluator@1"
PHYSICAL_REALITY_RUNNER_ID = "five-axis-physical-reality-import@1"
R41_DEFAULT_SCENARIO_ID = "physical-reality-evidence-open"
R41_SCENARIO_IDS = (R41_DEFAULT_SCENARIO_ID,)

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_VERSIONED_ID_PATTERN = r"^.+@[0-9]+$"
_AXIS_CONTRACT = (
    ("X", "linear-mm", "mm"),
    ("Y", "linear-mm", "mm"),
    ("Z", "linear-mm", "mm"),
    ("B", "rotary-rad", "rad"),
    ("C", "rotary-rad", "rad"),
)


def identity_hash(model: AxiomModel, *, exclude: str) -> str:
    payload = model.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={exclude}
    )
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _finite(value: Any) -> Any:
    value = _require_json_number(value)
    if not math.isfinite(float(value)):
        raise ValueError("value must be finite")
    return value


class PhysicalRealityEvidencePair(AxiomModel):
    pair_id: str = Field(alias="pairId", pattern=_VERSIONED_ID_PATTERN)
    role: Literal["calibration", "validation"]
    r7e_request: dict[str, Any] = Field(alias="r7eRequest")
    command_content_hash: str = Field(alias="commandContentHash", pattern=_HASH_PATTERN)
    shadow_evidence_content_hash: str = Field(
        alias="shadowEvidenceContentHash", pattern=_HASH_PATTERN
    )
    pair_content_hash: str = Field(alias="pairContentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def bind_evidence(self) -> PhysicalRealityEvidencePair:
        request = self.parsed_r7e_request()
        command = request.command
        evidence = request.shadow_evidence
        if command is None or evidence is None:
            raise ValueError("reality evidence pair requires command and Shadow evidence")
        if self.command_content_hash != command.content_id:
            raise ValueError("commandContentHash must identify R7-E command")
        if self.shadow_evidence_content_hash != evidence.content_hash:
            raise ValueError("shadowEvidenceContentHash must identify R7-E evidence")
        if self.pair_content_hash != identity_hash(self, exclude="pair_content_hash"):
            raise ValueError("pairContentHash must match reality evidence pair")
        return self

    def parsed_r7e_request(self) -> Any:
        from ..control.r7e_models import R7EEvaluationRequest

        return R7EEvaluationRequest.model_validate(self.r7e_request)


class RealityPhysicalApplicability(AxiomModel):
    device_id: str = Field(alias="deviceId", min_length=1)
    controller_profile_content_hash: str = Field(
        alias="controllerProfileContentHash", pattern=_HASH_PATTERN
    )
    case_id: str = Field(alias="caseId", min_length=1)
    trajectory_families: tuple[str, ...] = Field(
        alias="trajectoryFamilies", min_length=1
    )
    sample_period_seconds: float = Field(alias="samplePeriodSeconds", gt=0)
    evidence_source: Literal["controller-live-read"] = Field(alias="evidenceSource")
    validation_scope: Literal["single-device-case-scoped"] = Field(
        alias="validationScope"
    )

    @field_validator("sample_period_seconds", mode="before")
    @classmethod
    def reject_invalid_period(cls, value: Any) -> Any:
        return _finite(value)


class RealityPhysicalModelDefinition(AxiomModel):
    schema_id: Literal["five-axis.physical-model-definition@2"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[2] = Field(alias="schemaVersion")
    model_id: str = Field(alias="modelId", pattern=_VERSIONED_ID_PATTERN)
    model_family_id: Literal["five-axis.independent-first-order-axis-model@1"] = Field(
        alias="modelFamilyId"
    )
    integration_method: Literal["exact-zoh"] = Field(alias="integrationMethod")
    parameter_source: Literal["deterministic-grid-search"] = Field(
        alias="parameterSource"
    )
    calibration_id: str = Field(alias="calibrationId", pattern=_VERSIONED_ID_PATTERN)
    calibration_command_content_hash: str = Field(
        alias="calibrationCommandContentHash", pattern=_HASH_PATTERN
    )
    calibration_shadow_evidence_content_hash: str = Field(
        alias="calibrationShadowEvidenceContentHash", pattern=_HASH_PATTERN
    )
    axes: tuple[PhysicalAxisParameter, ...] = Field(min_length=5, max_length=5)
    applicability: RealityPhysicalApplicability
    unmodeled_factors: tuple[str, ...] = Field(alias="unmodeledFactors", min_length=1)
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @model_validator(mode="after")
    def verify_model(self) -> RealityPhysicalModelDefinition:
        observed = tuple(
            (axis.axis_id, axis.unit_family, axis.unit) for axis in self.axes
        )
        if observed != _AXIS_CONTRACT:
            raise ValueError("axes must use the frozen X/Y/Z/B/C unit contract")
        if self.content_hash != identity_hash(self, exclude="content_hash"):
            raise ValueError("contentHash must match reality physical model")
        return self


class PhysicalRealityCheck(AxiomModel):
    check_id: str = Field(alias="checkId", min_length=1)
    title: str = Field(min_length=1)
    status: Literal["Passed", "Open", "Refuted", "Blocked"]
    reason_code: str | None = Field(default=None, alias="reasonCode")
    details: dict[str, Any] = Field(default_factory=dict)


class PhysicalRealityAnalysis(AxiomModel):
    artifact_type: Literal["five-axis.physical-reality-analysis"] = Field(
        alias="artifactType"
    )
    schema_id: Literal["five-axis.physical-reality-analysis@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    analysis_id: Literal["five-axis.r4.1.reality-analysis@1"] = Field(
        alias="analysisId"
    )
    calibration_pair_content_hash: str | None = Field(
        default=None, alias="calibrationPairContentHash", pattern=_HASH_PATTERN
    )
    validation_pair_content_hash: str | None = Field(
        default=None, alias="validationPairContentHash", pattern=_HASH_PATTERN
    )
    checks: tuple[PhysicalRealityCheck, ...] = Field(min_length=8, max_length=8)
    model: RealityPhysicalModelDefinition | None = None
    calibration: CalibrationResult | None = None
    axes: tuple[AxisValidationSeries, ...] = ()
    linear_math_observation_rmse: float | None = Field(
        default=None, alias="linearMathObservationRmse", ge=0
    )
    linear_simulation_observation_rmse: float | None = Field(
        default=None, alias="linearSimulationObservationRmse", ge=0
    )
    linear_improvement_ratio: float | None = Field(
        default=None, alias="linearImprovementRatio"
    )
    rotary_math_observation_rmse: float | None = Field(
        default=None, alias="rotaryMathObservationRmse", ge=0
    )
    rotary_simulation_observation_rmse: float | None = Field(
        default=None, alias="rotarySimulationObservationRmse", ge=0
    )
    rotary_improvement_ratio: float | None = Field(
        default=None, alias="rotaryImprovementRatio"
    )
    decomposition_closure_max: float | None = Field(
        default=None, alias="decompositionClosureMax", ge=0
    )
    alignment_coverage: float = Field(alias="alignmentCoverage", ge=0, le=1)
    fit_status: Literal["Open", "Passed", "Refuted", "Blocked"] = Field(
        alias="fitStatus"
    )
    reality_validation_status: Literal["Open", "Passed", "Refuted", "Blocked"] = Field(
        alias="realityValidationStatus"
    )
    counts_toward_reality: bool = Field(alias="countsTowardReality")
    validation_scope: Literal["single-device-case-scoped"] = Field(
        alias="validationScope"
    )
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(alias="processSafetyStatus")
    content_hash: str = Field(alias="contentHash", pattern=_HASH_PATTERN)

    @field_validator(
        "linear_math_observation_rmse",
        "linear_simulation_observation_rmse",
        "linear_improvement_ratio",
        "rotary_math_observation_rmse",
        "rotary_simulation_observation_rmse",
        "rotary_improvement_ratio",
        "decomposition_closure_max",
        "alignment_coverage",
        mode="before",
    )
    @classmethod
    def reject_invalid_numbers(cls, value: Any) -> Any:
        if value is None:
            return None
        return _finite(value)

    @model_validator(mode="after")
    def verify_analysis(self) -> PhysicalRealityAnalysis:
        expected_checks = (
            "r41.contract",
            "r41.independent-evidence",
            "r41.r7e-deployment-gates",
            "r41.calibration",
            "r41.alignment",
            "r41.holdout-fit",
            "r41.residual-decomposition",
            "r41.reality-gate",
        )
        if tuple(check.check_id for check in self.checks) != expected_checks:
            raise ValueError("checks must use the frozen R4.1 order")
        passed = self.reality_validation_status == "Passed"
        if self.counts_toward_reality != passed:
            raise ValueError("countsTowardReality must reflect realityValidationStatus")
        if passed and (
            self.model is None
            or self.calibration is None
            or len(self.axes) != 5
            or self.fit_status != "Passed"
            or self.alignment_coverage != 1.0
        ):
            raise ValueError("Passed reality analysis requires a complete model and holdout")
        if self.content_hash != identity_hash(self, exclude="content_hash"):
            raise ValueError("contentHash must match physical reality analysis")
        return self


class R41EvaluationRequest(AxiomModel):
    artifact: PhysicalRealityAnalysis
    calibration_pair: PhysicalRealityEvidencePair | None = Field(
        default=None, alias="calibrationPair"
    )
    validation_pair: PhysicalRealityEvidencePair | None = Field(
        default=None, alias="validationPair"
    )
    fit_improvement_minimum: float = Field(
        default=0.2, alias="fitImprovementMinimum", ge=0, le=1
    )
    excitation_span_minimum: float = Field(
        default=1e-6, alias="excitationSpanMinimum", gt=0
    )
    decomposition_tolerance: float = Field(
        default=1e-12, alias="decompositionTolerance", ge=0
    )
    case: EvaluationCase

    @field_validator(
        "fit_improvement_minimum",
        "excitation_span_minimum",
        "decomposition_tolerance",
        mode="before",
    )
    @classmethod
    def reject_invalid_thresholds(cls, value: Any) -> Any:
        return _finite(value)

    @model_validator(mode="after")
    def bind_pairs(self) -> R41EvaluationRequest:
        calibration_hash = (
            self.calibration_pair.pair_content_hash if self.calibration_pair else None
        )
        validation_hash = (
            self.validation_pair.pair_content_hash if self.validation_pair else None
        )
        if self.artifact.calibration_pair_content_hash != calibration_hash:
            raise ValueError("artifact calibrationPairContentHash mismatch")
        if self.artifact.validation_pair_content_hash != validation_hash:
            raise ValueError("artifact validationPairContentHash mismatch")
        if self.calibration_pair and self.calibration_pair.role != "calibration":
            raise ValueError("calibrationPair must use calibration role")
        if self.validation_pair and self.validation_pair.role != "validation":
            raise ValueError("validationPair must use validation role")
        return self


class R41Manifest(AxiomModel):
    manifest_id: Literal["physical.r4.1-manifest@1"] = Field(alias="manifestId")
    stage: Literal["R4.1"]
    domain_pack_id: Literal["five-axis.domain-pack@7"] = Field(alias="domainPackId")
    evaluator_version: Literal["five-axis-physical-reality-evaluator@1"] = Field(
        alias="evaluatorVersion"
    )
    runner_id: Literal["five-axis-physical-reality-import@1"] = Field(alias="runnerId")
    supported_platforms: tuple[Literal["Windows"], ...] = Field(
        alias="supportedPlatforms"
    )
    required_independent_runs: Literal[2] = Field(alias="requiredIndependentRuns")
    calibration_role: Literal["calibration"] = Field(alias="calibrationRole")
    validation_role: Literal["validation"] = Field(alias="validationRole")
    interpolation_allowed: Literal[False] = Field(alias="interpolationAllowed")
    default_scenario_id: str = Field(alias="defaultScenarioId")
    scenario_ids: tuple[str, ...] = Field(alias="scenarioIds")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(alias="processSafetyStatus")


class R41ScenarioSummary(AxiomModel):
    scenario_id: str = Field(alias="scenarioId")
    title: str
    description: str
    expected_outcome: Literal["Inconclusive", "Passed", "Failed"] = Field(
        alias="expectedOutcome"
    )
    reality_validation_status: Literal["Open", "Passed", "Refuted", "Blocked"] = Field(
        alias="realityValidationStatus"
    )
    counts_toward_reality: bool = Field(alias="countsTowardReality")


class R41ExamplePayload(AxiomModel):
    manifest: R41Manifest
    scenario: R41ScenarioSummary
    calibration_pair: PhysicalRealityEvidencePair | None = Field(
        default=None, alias="calibrationPair"
    )
    validation_pair: PhysicalRealityEvidencePair | None = Field(
        default=None, alias="validationPair"
    )
    analysis: PhysicalRealityAnalysis
    run_spec: dict[str, Any] = Field(alias="runSpec")


class R41AssessmentRequest(AxiomModel):
    calibration_pair: PhysicalRealityEvidencePair | None = Field(
        default=None, alias="calibrationPair"
    )
    validation_pair: PhysicalRealityEvidencePair | None = Field(
        default=None, alias="validationPair"
    )
    fit_improvement_minimum: float = Field(
        default=0.2, alias="fitImprovementMinimum", ge=0, le=1
    )
    excitation_span_minimum: float = Field(
        default=1e-6, alias="excitationSpanMinimum", gt=0
    )
    decomposition_tolerance: float = Field(
        default=1e-12, alias="decompositionTolerance", ge=0
    )


@dataclass(frozen=True, slots=True)
class R41Scenario:
    summary: R41ScenarioSummary
    calibration_pair: PhysicalRealityEvidencePair | None
    validation_pair: PhysicalRealityEvidencePair | None
    analysis: PhysicalRealityAnalysis
    run_spec: dict[str, Any]


__all__ = [
    "FIVE_AXIS_REALITY_DOMAIN_PACK_ID",
    "PHYSICAL_REALITY_EVALUATOR_ID",
    "PHYSICAL_REALITY_RUNNER_ID",
    "R41_DEFAULT_SCENARIO_ID",
    "R41_SCENARIO_IDS",
    "PhysicalRealityAnalysis",
    "PhysicalRealityCheck",
    "PhysicalRealityEvidencePair",
    "R41AssessmentRequest",
    "R41EvaluationRequest",
    "R41ExamplePayload",
    "R41Manifest",
    "R41ScenarioSummary",
    "RealityPhysicalApplicability",
    "RealityPhysicalModelDefinition",
    "identity_hash",
]
