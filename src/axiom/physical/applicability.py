from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, model_validator

from ..five_axis.f3_sampling import POLYNOMIAL_POLICY_ID
from ..five_axis.f4_adapters import (
    SUT_ADAPTER_DESCRIPTOR,
    build_adapter_invocation,
    execute_adapter,
)
from ..five_axis.f4_scenarios import load_f4_scenario
from ..models import AxiomModel
from .models import PhysicalModelDefinition

_R6_PERIODS = (0.04, 0.08)
_IMPROVEMENT_THRESHOLD = 0.35


def _content_hash(payload: Any) -> str:
    if isinstance(payload, AxiomModel):
        payload = payload.model_dump(mode="json", by_alias=True, exclude_none=True)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class PhysicalApplicabilityEndpointEvidence(AxiomModel):
    sample_period_seconds: float = Field(alias="samplePeriodSeconds", gt=0.0)
    sample_count: int = Field(alias="sampleCount", ge=2)
    math_observation_rmse_mm: float = Field(alias="mathObservationRmseMm", ge=0.0)
    simulation_observation_rmse_mm: float = Field(
        alias="simulationObservationRmseMm", ge=0.0
    )
    improvement_ratio: float = Field(alias="improvementRatio")
    required_improvement_ratio: float = Field(alias="requiredImprovementRatio", ge=0.0)
    passed: bool


class PhysicalMultirateApplicabilityEvidence(AxiomModel):
    artifact_type: Literal["five-axis.physical-multirate-applicability-evidence"] = (
        Field(alias="artifactType")
    )
    schema_id: Literal["five-axis.physical-multirate-applicability-evidence@1"] = Field(
        alias="schemaId"
    )
    schema_version: Literal[1] = Field(alias="schemaVersion")
    evidence_id: Literal["five-axis.r4.multirate-applicability-evidence@1"] = Field(
        alias="evidenceId"
    )
    physical_model_id: Literal["five-axis.r4.multirate-physical-model@2"] = Field(
        alias="physicalModelId"
    )
    physical_model_content_hash: str = Field(
        alias="physicalModelContentHash", pattern=r"^[0-9a-f]{64}$"
    )
    oracle_id: Literal["five-axis.r4.independent-two-stage-lag-oracle@1"] = Field(
        alias="oracleId"
    )
    supported_period_min_seconds: float = Field(
        alias="supportedPeriodMinSeconds", gt=0.0
    )
    supported_period_max_seconds: float = Field(
        alias="supportedPeriodMaxSeconds", gt=0.0
    )
    endpoint_evaluations: tuple[PhysicalApplicabilityEndpointEvidence, ...] = Field(
        alias="endpointEvaluations", min_length=2, max_length=2
    )
    status: Literal["Passed"]
    evidence_source: Literal["synthetic-sil"] = Field(alias="evidenceSource")
    reality_validation_status: Literal["Open"] = Field(alias="realityValidationStatus")
    content_hash: str = Field(alias="contentHash", pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_frozen_endpoints_and_identity(
        self,
    ) -> PhysicalMultirateApplicabilityEvidence:
        periods = tuple(
            point.sample_period_seconds for point in self.endpoint_evaluations
        )
        if periods != _R6_PERIODS:
            raise ValueError(
                "endpointEvaluations must cover the frozen 0.04/0.08 second endpoints"
            )
        if (
            self.supported_period_min_seconds != periods[0]
            or self.supported_period_max_seconds != periods[-1]
        ):
            raise ValueError(
                "supported period bounds must equal the validated endpoints"
            )
        if not all(point.passed for point in self.endpoint_evaluations):
            raise ValueError(
                "Passed applicability evidence requires every endpoint to pass"
            )
        payload = self.model_dump(
            mode="json", by_alias=True, exclude_none=True, exclude={"content_hash"}
        )
        if self.content_hash != _content_hash(payload):
            raise ValueError(
                "contentHash must match physical multirate applicability evidence"
            )
        return self


def require_physical_model_sample_period(
    model: PhysicalModelDefinition, sample_period: float
) -> None:
    lower = model.applicability.sample_period_min_seconds
    upper = model.applicability.sample_period_max_seconds
    if sample_period < lower - 1e-12 or sample_period > upper + 1e-12:
        raise ValueError(
            f"sample period {sample_period} is outside physical model applicability [{lower}, {upper}]"
        )


@lru_cache(maxsize=1)
def build_r4_multirate_physical_model() -> PhysicalModelDefinition:
    from .scenarios import load_r4_scenario

    base = load_r4_scenario("in-domain-synthetic-sil").physicalModel
    payload = base.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["modelId"] = "five-axis.r4.multirate-physical-model@2"
    payload["applicability"]["samplePeriodMinSeconds"] = _R6_PERIODS[0]
    payload["applicability"]["samplePeriodMaxSeconds"] = _R6_PERIODS[-1]
    return PhysicalModelDefinition.model_validate(payload)


def _linear_rmse(
    left_by_axis: tuple[tuple[float, ...], ...],
    right_by_axis: tuple[tuple[float, ...], ...],
) -> float:
    squared = [
        (left - right) ** 2
        for axis in range(3)
        for left, right in zip(left_by_axis[axis], right_by_axis[axis], strict=True)
    ]
    return math.sqrt(sum(squared) / len(squared))


@lru_cache(maxsize=1)
def build_r4_multirate_applicability_evidence() -> (
    PhysicalMultirateApplicabilityEvidence
):
    from .scenarios import _build_observed_axes
    from .simulation import physical_model_content_hash, simulate_physical_response

    model = build_r4_multirate_physical_model()
    source = load_f4_scenario("canonical-head-table-solver")
    endpoints: list[dict[str, Any]] = []
    for period in _R6_PERIODS:
        invocation = build_adapter_invocation(
            SUT_ADAPTER_DESCRIPTOR,
            source.continuousTrajectory,
            sample_period=period,
            policy=POLYNOMIAL_POLICY_ID,
            final_hold=False,
            invocation_id=f"five-axis.r4.multirate-{period:.2f}.invoke",
        )
        receipt, command = execute_adapter(invocation, source.continuousTrajectory)
        if receipt.status != "Succeeded" or command is None:
            raise ValueError(
                f"R4 multirate endpoint adapter failed at {period} seconds"
            )
        observed = _build_observed_axes(command, variant="default")
        response = simulate_physical_response(
            model,
            command,
            response_trace_id=f"five-axis.r4.multirate-{period:.2f}.response@1",
        )
        commands = tuple(
            tuple(float(sample.q[axis]) for sample in command.samples)
            for axis in range(5)
        )
        simulations = tuple(
            tuple(float(sample.simulated[axis]) for sample in response.samples)
            for axis in range(5)
        )
        math_rmse = _linear_rmse(commands, observed)
        simulation_rmse = _linear_rmse(simulations, observed)
        improvement = 1.0 - simulation_rmse / math_rmse
        endpoints.append(
            {
                "samplePeriodSeconds": period,
                "sampleCount": len(command.samples),
                "mathObservationRmseMm": math_rmse,
                "simulationObservationRmseMm": simulation_rmse,
                "improvementRatio": improvement,
                "requiredImprovementRatio": _IMPROVEMENT_THRESHOLD,
                "passed": improvement >= _IMPROVEMENT_THRESHOLD,
            }
        )
    payload = {
        "artifactType": "five-axis.physical-multirate-applicability-evidence",
        "schemaId": "five-axis.physical-multirate-applicability-evidence@1",
        "schemaVersion": 1,
        "evidenceId": "five-axis.r4.multirate-applicability-evidence@1",
        "physicalModelId": model.model_id,
        "physicalModelContentHash": physical_model_content_hash(model),
        "oracleId": "five-axis.r4.independent-two-stage-lag-oracle@1",
        "supportedPeriodMinSeconds": _R6_PERIODS[0],
        "supportedPeriodMaxSeconds": _R6_PERIODS[-1],
        "endpointEvaluations": endpoints,
        "status": "Passed",
        "evidenceSource": "synthetic-sil",
        "realityValidationStatus": "Open",
    }
    payload["contentHash"] = _content_hash(payload)
    return PhysicalMultirateApplicabilityEvidence.model_validate(payload)


__all__ = [
    "PhysicalApplicabilityEndpointEvidence",
    "PhysicalMultirateApplicabilityEvidence",
    "build_r4_multirate_applicability_evidence",
    "build_r4_multirate_physical_model",
    "require_physical_model_sample_period",
]
