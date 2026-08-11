from __future__ import annotations

import os
import platform
from importlib.metadata import version as package_version
from typing import Any, Literal

from pydantic import Field, model_validator

from ..domain import (
    CASE_OUTCOME_CLAIM_DEFINITION_ID,
    ArtifactTypeDescriptor,
    DomainPack,
    FailureMapping,
    MetricDefinition,
    NumericTolerance as DomainNumericTolerance,
    register_domain_pack,
)
from ..evaluator import _aggregate_outcome, _apply_threshold, _content_hash, _seal_evaluation_report
from ..models import (
    AxiomModel,
    CapabilityResolution,
    CaseOutcome,
    CoreEvaluationRequest,
    DomainFailure,
    Evidence,
    EvaluationCase,
    EvaluationReport,
    ExecutionStatus,
    MetricRequest,
    MetricResult,
    MetricStatus,
    Provenance,
)
from ..runtime import DomainRuntimeBinding, register_domain_runtime_binding
from .f1_models import AxisAlignedBoundingBox, M1ReferencePath
from .f1_runtime import (
    CAP_COLLISION_CONTEXT,
    CAP_CONTINUOUS_ERROR,
    CAP_CORRESPONDENCE,
    CAP_PATH_PROGRESS,
    CAP_PROCESS_STATE,
    CAP_REGULARITY,
    CAP_TASK_COLLISION,
    GEOMETRY_VALID_CLAIM_ID,
    GEOMETRY_VALID_METRIC_ID,
    TASK_COLLISION_FREE_CLAIM_ID,
    TASK_COLLISION_FREE_METRIC_ID,
    FiveAxisF1EvaluationBindingRequest,
    evaluate_five_axis_f1,
)
from .f2_collision import ConfigurationCollisionModel
from .f2_runtime import (
    CAP_CONFIGURATION_COLLISION,
    CAP_MACHINE_PROFILE,
    CONFIGURATION_COLLISION_FREE_CLAIM_ID,
    CONFIGURATION_COLLISION_FREE_METRIC_ID,
    KINEMATICALLY_FEASIBLE_CLAIM_ID,
    KINEMATICALLY_FEASIBLE_METRIC_ID,
    FiveAxisF2EvaluationBindingRequest,
    evaluate_five_axis_f2,
)
from .f3_runtime import (
    CAP_MOTION_CONSTRAINT_PROFILE,
    CAP_RECONSTRUCTION,
    CAP_TIME_LAW,
    CONTINUOUSLY_FEASIBLE_CLAIM_ID,
    CONTINUOUSLY_FEASIBLE_METRIC_ID,
    INTERVAL_CERTIFIED_CLAIM_ID,
    INTERVAL_CERTIFIED_METRIC_ID,
    FiveAxisF3EvaluationBindingRequest,
    evaluate_five_axis_f3,
)
from .f3_sampling import M5DiscreteCommand
from .f4_adapters import cross_validate_discrete_commands
from .f4_collision import verify_m5_configuration_collision
from .f4_models import AdapterInvocation, AdapterReceipt, CrossValidationResult, M5CollisionVerification


FIVE_AXIS_F4_DOMAIN_PACK_ID = "five-axis.domain-pack@5"
F4_EVALUATOR_ID = "five-axis-f4-evaluator@1"
F4_RUNNER_ID = "five-axis.solver-adapter@1"

MODEL_COLLISION_FREE_METRIC_ID = "five-axis.model-collision-free@1"
ADAPTER_CONTRACT_VALID_METRIC_ID = "five-axis.adapter-contract-valid@1"
REFERENCE_SUT_CROSS_VALIDATED_METRIC_ID = "five-axis.reference-sut-cross-validated@1"
REFERENCE_SUT_POSITION_GAP_MAX_METRIC_ID = "five-axis.reference-sut-position-gap.max@1"
REFERENCE_SUT_VELOCITY_GAP_MAX_METRIC_ID = "five-axis.reference-sut-velocity-gap.max@1"
REFERENCE_SUT_ACCELERATION_GAP_MAX_METRIC_ID = "five-axis.reference-sut-acceleration-gap.max@1"
REFERENCE_SUT_JERK_GAP_MAX_METRIC_ID = "five-axis.reference-sut-jerk-gap.max@1"

MODEL_COLLISION_FREE_CLAIM_ID = "five-axis.model-collision-free-claim@1"

CAP_SOLVER_ADAPTER = "five-axis.solver-adapter.bound@1"
CAP_CROSS_VALIDATION = "five-axis.reference-sut.cross-validated@1"
CAP_M5_COLLISION = "five-axis.m5-collision.checked@1"

_SEVEN_GATE_METRIC_IDS = frozenset(
    {
        GEOMETRY_VALID_METRIC_ID,
        TASK_COLLISION_FREE_METRIC_ID,
        KINEMATICALLY_FEASIBLE_METRIC_ID,
        CONFIGURATION_COLLISION_FREE_METRIC_ID,
        CONTINUOUSLY_FEASIBLE_METRIC_ID,
        INTERVAL_CERTIFIED_METRIC_ID,
        MODEL_COLLISION_FREE_METRIC_ID,
    }
)


class FiveAxisF4EvaluationBindingRequest(AxiomModel):
    artifact: M5DiscreteCommand
    reference_artifact: M5DiscreteCommand = Field(alias="referenceArtifact")
    reference_invocation: AdapterInvocation = Field(alias="referenceInvocation")
    sut_invocation: AdapterInvocation = Field(alias="sutInvocation")
    reference_receipt: AdapterReceipt = Field(alias="referenceReceipt")
    sut_receipt: AdapterReceipt = Field(alias="sutReceipt")
    reference_path: M1ReferencePath = Field(alias="referencePath")
    stock_state_geometries: dict[str, dict[str, tuple[AxisAlignedBoundingBox, ...]]] = Field(
        alias="stockStateGeometries"
    )
    collision_model: ConfigurationCollisionModel = Field(alias="collisionModel")
    case: EvaluationCase

    @model_validator(mode="after")
    def require_one_shared_solver_input(self) -> "FiveAxisF4EvaluationBindingRequest":
        reference_descriptor = self.reference_invocation.descriptor
        sut_descriptor = self.sut_invocation.descriptor
        if reference_descriptor.role != "reference" or sut_descriptor.role != "sut":
            raise ValueError("referenceInvocation and sutInvocation must use their frozen adapter roles")
        if reference_descriptor.subject_id == sut_descriptor.subject_id:
            raise ValueError("reference and SUT subjects must be distinct")
        if self.reference_receipt.invocation != self.reference_invocation:
            raise ValueError("referenceReceipt must bind referenceInvocation")
        if self.sut_receipt.invocation != self.sut_invocation:
            raise ValueError("sutReceipt must bind sutInvocation")

        reference_source = self.reference_artifact
        sut_source = self.artifact
        if reference_source.source_m4_id != sut_source.source_m4_id:
            raise ValueError("reference and SUT artifacts must share sourceM4Id")
        if reference_source.source_m4_content_id != sut_source.source_m4_content_id:
            raise ValueError("reference and SUT artifacts must share sourceM4ContentId")
        for name, invocation in (
            ("referenceInvocation", self.reference_invocation),
            ("sutInvocation", self.sut_invocation),
        ):
            if invocation.input_m4_id != sut_source.source_m4_id:
                raise ValueError(f"{name}.inputM4Id must match the shared M4 identity")
            if invocation.input_m4_content_hash != sut_source.source_m4_content_id:
                raise ValueError(f"{name}.inputM4ContentHash must match the shared M4 content")
        if self.reference_invocation.policy_id != self.sut_invocation.policy_id:
            raise ValueError("reference and SUT invocations must share policyId")
        if self.reference_invocation.sample_period != self.sut_invocation.sample_period:
            raise ValueError("reference and SUT invocations must share samplePeriod")
        if self.reference_invocation.final_hold != self.sut_invocation.final_hold:
            raise ValueError("reference and SUT invocations must share finalHold")
        for name, command in (("referenceArtifact", reference_source), ("artifact", sut_source)):
            if command.reconstruction_policy.policy_id != self.sut_invocation.policy_id:
                raise ValueError(f"{name}.reconstructionPolicy must match the invocation policy")
            if command.sample_period != self.sut_invocation.sample_period:
                raise ValueError(f"{name}.samplePeriod must match the invocation")
            if command.final_hold != self.sut_invocation.final_hold:
                raise ValueError(f"{name}.finalHold must match the invocation")
        if (
            self.reference_receipt.status == "Succeeded"
            and self.reference_receipt.output_content_hash != reference_source.content_id
        ):
            raise ValueError("referenceReceipt outputContentHash must identify referenceArtifact")
        if self.sut_receipt.status == "Succeeded" and self.sut_receipt.output_content_hash != sut_source.content_id:
            raise ValueError("sutReceipt outputContentHash must identify artifact")
        return self


_FAILURE_MAPPINGS = (
    FailureMapping(
        code="MalformedEvaluationRequest",
        executionStatus=ExecutionStatus.SKIPPED,
        metricStatus=MetricStatus.INVALID_OBSERVATION,
        caseOutcome=CaseOutcome.INVALID,
    ),
    FailureMapping(
        code="ArtifactTypeMismatch",
        executionStatus=ExecutionStatus.SKIPPED,
        metricStatus=MetricStatus.INVALID_OBSERVATION,
        caseOutcome=CaseOutcome.INVALID,
    ),
    FailureMapping(
        code="ArtifactSchemaVersionMismatch",
        executionStatus=ExecutionStatus.SKIPPED,
        metricStatus=MetricStatus.INVALID_OBSERVATION,
        caseOutcome=CaseOutcome.INVALID,
    ),
    FailureMapping(
        code="DomainEvaluatorFailed",
        executionStatus=ExecutionStatus.EXECUTION_FAILED,
        metricStatus=MetricStatus.NUMERICAL_FAILURE,
        caseOutcome=CaseOutcome.INCONCLUSIVE,
    ),
)


def _metric_definition(
    metric_id: str,
    *,
    requires: tuple[str, ...],
    claim_id: str | None = None,
    predicate: str | None = None,
    direction: Literal["lower-is-better", "higher-is-better"] | None = None,
    unit: str | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        metricId=metric_id,
        metricDefinitionId=metric_id,
        requires=requires,
        claimDefinitionId=claim_id,
        claimPredicate=predicate,
        direction=direction,
        numericTolerance=(
            DomainNumericTolerance(absolute=1e-12, relative=1e-12, unit=unit)
            if direction is not None
            else None
        ),
    )


FIVE_AXIS_F4_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=FIVE_AXIS_F4_DOMAIN_PACK_ID,
        artifactType="five-axis.m5-discrete-command",
        artifactSchemaVersions=(1,),
        artifactTypeDescriptors=(
            ArtifactTypeDescriptor(
                artifactType="five-axis.m5-discrete-command",
                schemaVersion=1,
                role="run-input",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.m5-discrete-command",
                schemaVersion=1,
                role="reference",
            ),
            ArtifactTypeDescriptor(
                artifactType="five-axis.m4-continuous-trajectory",
                schemaVersion=1,
                role="context",
            ),
        ),
        evaluatorVersion=F4_EVALUATOR_ID,
        runnerId=F4_RUNNER_ID,
        runnerIds=(F4_RUNNER_ID,),
        capabilityIds=(
            CAP_PATH_PROGRESS,
            CAP_REGULARITY,
            CAP_CORRESPONDENCE,
            CAP_CONTINUOUS_ERROR,
            CAP_COLLISION_CONTEXT,
            CAP_PROCESS_STATE,
            CAP_TASK_COLLISION,
            CAP_MACHINE_PROFILE,
            CAP_CONFIGURATION_COLLISION,
            CAP_MOTION_CONSTRAINT_PROFILE,
            CAP_TIME_LAW,
            CAP_RECONSTRUCTION,
            CAP_SOLVER_ADAPTER,
            CAP_CROSS_VALIDATION,
            CAP_M5_COLLISION,
        ),
        metricDefinitions=(
            _metric_definition(
                GEOMETRY_VALID_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_CORRESPONDENCE, CAP_CONTINUOUS_ERROR),
                claim_id=GEOMETRY_VALID_CLAIM_ID,
                predicate="five-axis.GeometryValid is true",
            ),
            _metric_definition(
                TASK_COLLISION_FREE_METRIC_ID,
                requires=(CAP_COLLISION_CONTEXT, CAP_PROCESS_STATE, CAP_PATH_PROGRESS, CAP_TASK_COLLISION),
                claim_id=TASK_COLLISION_FREE_CLAIM_ID,
                predicate="five-axis.TaskGeometryCollisionFree is true",
            ),
            _metric_definition(
                KINEMATICALLY_FEASIBLE_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_MACHINE_PROFILE),
                claim_id=KINEMATICALLY_FEASIBLE_CLAIM_ID,
                predicate="five-axis.KinematicallyFeasible is true",
            ),
            _metric_definition(
                CONFIGURATION_COLLISION_FREE_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_MACHINE_PROFILE, CAP_CONFIGURATION_COLLISION),
                claim_id=CONFIGURATION_COLLISION_FREE_CLAIM_ID,
                predicate="five-axis.ConfigurationCollisionFree is true",
            ),
            _metric_definition(
                CONTINUOUSLY_FEASIBLE_METRIC_ID,
                requires=(CAP_PATH_PROGRESS, CAP_REGULARITY, CAP_MOTION_CONSTRAINT_PROFILE, CAP_TIME_LAW),
                claim_id=CONTINUOUSLY_FEASIBLE_CLAIM_ID,
                predicate="five-axis.ContinuouslyFeasible is true",
            ),
            _metric_definition(
                INTERVAL_CERTIFIED_METRIC_ID,
                requires=(CAP_TIME_LAW, CAP_RECONSTRUCTION),
                claim_id=INTERVAL_CERTIFIED_CLAIM_ID,
                predicate="five-axis.IntervalCertified is true",
            ),
            _metric_definition(
                MODEL_COLLISION_FREE_METRIC_ID,
                requires=(CAP_TASK_COLLISION, CAP_CONFIGURATION_COLLISION, CAP_M5_COLLISION),
                claim_id=MODEL_COLLISION_FREE_CLAIM_ID,
                predicate="five-axis.ModelCollisionFree is true",
            ),
            _metric_definition(ADAPTER_CONTRACT_VALID_METRIC_ID, requires=(CAP_SOLVER_ADAPTER,)),
            _metric_definition(
                REFERENCE_SUT_CROSS_VALIDATED_METRIC_ID,
                requires=(CAP_SOLVER_ADAPTER, CAP_CROSS_VALIDATION),
            ),
            _metric_definition(
                REFERENCE_SUT_POSITION_GAP_MAX_METRIC_ID,
                requires=(CAP_CROSS_VALIDATION,),
                direction="lower-is-better",
                unit="axis-unit",
            ),
            _metric_definition(
                REFERENCE_SUT_VELOCITY_GAP_MAX_METRIC_ID,
                requires=(CAP_CROSS_VALIDATION,),
                direction="lower-is-better",
                unit="axis-unit/s",
            ),
            _metric_definition(
                REFERENCE_SUT_ACCELERATION_GAP_MAX_METRIC_ID,
                requires=(CAP_CROSS_VALIDATION,),
                direction="lower-is-better",
                unit="axis-unit/s^2",
            ),
            _metric_definition(
                REFERENCE_SUT_JERK_GAP_MAX_METRIC_ID,
                requires=(CAP_CROSS_VALIDATION,),
                direction="lower-is-better",
                unit="axis-unit/s^3",
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            GEOMETRY_VALID_CLAIM_ID,
            TASK_COLLISION_FREE_CLAIM_ID,
            KINEMATICALLY_FEASIBLE_CLAIM_ID,
            CONFIGURATION_COLLISION_FREE_CLAIM_ID,
            CONTINUOUSLY_FEASIBLE_CLAIM_ID,
            INTERVAL_CERTIFIED_CLAIM_ID,
            MODEL_COLLISION_FREE_CLAIM_ID,
        ),
        comparisonPolicyIds=(),
        failureMappings=_FAILURE_MAPPINGS,
    )
)


def current_f4_numeric_environment() -> dict[str, str]:
    return {
        "system": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "numpy": package_version("numpy"),
        "scipy": package_version("scipy"),
        "pint": package_version("pint"),
        "pydantic": package_version("pydantic"),
        "openblasCoreType": os.environ.get("OPENBLAS_CORETYPE", "auto"),
        "openblasNumThreads": os.environ.get("OPENBLAS_NUM_THREADS", "auto"),
        "ompNumThreads": os.environ.get("OMP_NUM_THREADS", "auto"),
    }


def _parse_f4_request(request: CoreEvaluationRequest) -> FiveAxisF4EvaluationBindingRequest:
    return FiveAxisF4EvaluationBindingRequest.model_validate(
        request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )


def _definition(metric_id: str) -> MetricDefinition | None:
    try:
        return FIVE_AXIS_F4_DOMAIN_PACK.metric_definition(metric_id)
    except KeyError:
        return None


def _unavailable(metric_id: str, status: MetricStatus, reason_code: str, **details: Any) -> MetricResult:
    definition = _definition(metric_id)
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id if definition else metric_id,
        requires=list(definition.requires) if definition else [],
        status=status,
        reasonCode=reason_code,
        details=details,
    )


def _computed(
    metric_id: str,
    value: Any,
    *,
    level: Literal["Exact", "Certified", "Validated", "Observed"],
    method: str,
    unit: str | None = None,
    reason_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> MetricResult:
    definition = _definition(metric_id)
    assert definition is not None
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=definition.metric_definition_id,
        requires=list(definition.requires),
        status=MetricStatus.COMPUTED,
        value=value,
        unit=unit,
        reasonCode=reason_code,
        details=details or {},
        evidence=Evidence(level=level, method=method),
    )


def _adapter_contract_valid(request: FiveAxisF4EvaluationBindingRequest) -> bool:
    return (
        request.reference_receipt.status == "Succeeded"
        and request.sut_receipt.status == "Succeeded"
        and request.reference_receipt.output_content_hash == request.reference_artifact.content_id
        and request.sut_receipt.output_content_hash == request.artifact.content_id
    )


def _subreport_metric(report: EvaluationReport, metric_id: str) -> MetricResult:
    return next(result for result in report.metric_results if result.metric_id == metric_id)


def _upstream_reports(
    request: FiveAxisF4EvaluationBindingRequest,
) -> tuple[EvaluationReport, EvaluationReport, EvaluationReport]:
    m4 = request.artifact.source_m4
    axis_path = m4.source_axis_path
    candidate = axis_path.source_candidate_geometry
    f1_case = EvaluationCase(
        caseId=f"{request.case.case_id}.m2",
        requiredMetrics=[
            MetricRequest(metricId=GEOMETRY_VALID_METRIC_ID),
            MetricRequest(metricId=TASK_COLLISION_FREE_METRIC_ID),
        ],
    )
    f2_case = EvaluationCase(
        caseId=f"{request.case.case_id}.m3",
        requiredMetrics=[
            MetricRequest(metricId=KINEMATICALLY_FEASIBLE_METRIC_ID),
            MetricRequest(metricId=CONFIGURATION_COLLISION_FREE_METRIC_ID),
        ],
    )
    f3_case = EvaluationCase(
        caseId=f"{request.case.case_id}.m4-m5",
        requiredMetrics=[
            MetricRequest(metricId=CONTINUOUSLY_FEASIBLE_METRIC_ID),
            MetricRequest(metricId=INTERVAL_CERTIFIED_METRIC_ID),
        ],
    )
    f1_report = evaluate_five_axis_f1(
        FiveAxisF1EvaluationBindingRequest(
            artifact=candidate,
            case=f1_case,
            referencePath=request.reference_path,
            stockStateGeometries=request.stock_state_geometries,
        )
    )
    f2_report = evaluate_five_axis_f2(
        FiveAxisF2EvaluationBindingRequest(
            artifact=axis_path,
            case=f2_case,
            collisionModel=request.collision_model,
        )
    )
    f3_report = evaluate_five_axis_f3(
        FiveAxisF3EvaluationBindingRequest(
            artifact=request.artifact,
            case=f3_case,
        )
    )
    return f1_report, f2_report, f3_report


def _model_collision_metric(
    f1_report: EvaluationReport,
    f2_report: EvaluationReport,
    collision: M5CollisionVerification,
) -> MetricResult:
    m2_result = _subreport_metric(f1_report, TASK_COLLISION_FREE_METRIC_ID)
    m3_result = _subreport_metric(f2_report, CONFIGURATION_COLLISION_FREE_METRIC_ID)
    details = {
        "m2TaskGeometryCollision": m2_result.model_dump(mode="json", by_alias=True, exclude_none=True),
        "m3ConfigurationCollision": m3_result.model_dump(mode="json", by_alias=True, exclude_none=True),
        "m5ReconstructionCollision": collision.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    if m2_result.status is not MetricStatus.COMPUTED or m3_result.status is not MetricStatus.COMPUTED:
        return _unavailable(
            MODEL_COLLISION_FREE_METRIC_ID,
            MetricStatus.UNSUPPORTED_CAPABILITY,
            "UpstreamCollisionGateNotClosed",
            **details,
        )
    if m2_result.value is not True or m3_result.value is not True or collision.status == "collision":
        return _computed(
            MODEL_COLLISION_FREE_METRIC_ID,
            False,
            level="Observed",
            method="five-axis.f4.model-collision-aggregation@1",
            reason_code="ModelCollisionRefuted",
            details=details,
        )
    if not collision.supports_model_collision_aggregation:
        return _unavailable(
            MODEL_COLLISION_FREE_METRIC_ID,
            MetricStatus.UNSUPPORTED_CAPABILITY,
            "M5CollisionCoverageNotClosed",
            **details,
        )
    return _computed(
        MODEL_COLLISION_FREE_METRIC_ID,
        True,
        level="Certified",
        method="five-axis.f4.model-collision-aggregation@1",
        details=details,
    )


def _gap_metric(metric_id: str, cross: CrossValidationResult) -> MetricResult:
    mapping = {
        REFERENCE_SUT_POSITION_GAP_MAX_METRIC_ID: (cross.max_position_gap, "axis-unit"),
        REFERENCE_SUT_VELOCITY_GAP_MAX_METRIC_ID: (cross.max_velocity_gap, "axis-unit/s"),
        REFERENCE_SUT_ACCELERATION_GAP_MAX_METRIC_ID: (cross.max_acceleration_gap, "axis-unit/s^2"),
        REFERENCE_SUT_JERK_GAP_MAX_METRIC_ID: (cross.max_jerk_gap, "axis-unit/s^3"),
    }
    value, unit = mapping[metric_id]
    return _computed(
        metric_id,
        value,
        unit=unit,
        level="Validated",
        method=cross.method,
        details={"crossValidation": cross.model_dump(mode="json", by_alias=True, exclude_none=True)},
    )


def _metric_result(
    request: FiveAxisF4EvaluationBindingRequest,
    metric_id: str,
    *,
    adapter_valid: bool,
    cross: CrossValidationResult,
    collision: M5CollisionVerification,
    upstream_by_metric: dict[str, MetricResult],
) -> MetricResult:
    if metric_id == ADAPTER_CONTRACT_VALID_METRIC_ID:
        return _computed(
            metric_id,
            adapter_valid,
            level="Exact",
            method="five-axis.f4.adapter-receipt-binding@1",
            reason_code=None if adapter_valid else "AdapterContractNotSatisfied",
            details={
                "referenceReceipt": request.reference_receipt.model_dump(mode="json", by_alias=True, exclude_none=True),
                "sutReceipt": request.sut_receipt.model_dump(mode="json", by_alias=True, exclude_none=True),
            },
        )
    if metric_id == REFERENCE_SUT_CROSS_VALIDATED_METRIC_ID:
        if not adapter_valid:
            return _unavailable(
                metric_id,
                MetricStatus.UNSUPPORTED_CAPABILITY,
                "AdapterContractNotSatisfied",
            )
        if cross.status == "Inconclusive":
            return _unavailable(
                metric_id,
                MetricStatus.UNSUPPORTED_CAPABILITY,
                "ReferenceSutCrossValidationInconclusive",
                crossValidation=cross.model_dump(mode="json", by_alias=True, exclude_none=True),
            )
        return _computed(
            metric_id,
            cross.status == "Supported",
            level="Validated",
            method=cross.method,
            reason_code=None if cross.status == "Supported" else "ReferenceSutCrossValidationRefuted",
            details={"crossValidation": cross.model_dump(mode="json", by_alias=True, exclude_none=True)},
        )
    if metric_id in {
        REFERENCE_SUT_POSITION_GAP_MAX_METRIC_ID,
        REFERENCE_SUT_VELOCITY_GAP_MAX_METRIC_ID,
        REFERENCE_SUT_ACCELERATION_GAP_MAX_METRIC_ID,
        REFERENCE_SUT_JERK_GAP_MAX_METRIC_ID,
    }:
        if not adapter_valid:
            return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "AdapterContractNotSatisfied")
        return _gap_metric(metric_id, cross)
    if metric_id in _SEVEN_GATE_METRIC_IDS:
        if not adapter_valid:
            return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "AdapterContractNotSatisfied")
        if cross.status != "Supported":
            return _unavailable(
                metric_id,
                MetricStatus.UNSUPPORTED_CAPABILITY,
                "ReferenceSutCrossValidationNotSupported",
            )
        return upstream_by_metric[metric_id]
    return _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "MetricNotImplementedInF4")


def _source_metric(result: MetricResult, report: EvaluationReport) -> MetricResult:
    details = dict(result.details)
    details["sourceReportContentHash"] = report.content_hash
    return result.model_copy(update={"details": details})


def _capabilities(
    reports: tuple[EvaluationReport, EvaluationReport, EvaluationReport],
    *,
    adapter_valid: bool,
    cross: CrossValidationResult,
    collision: M5CollisionVerification,
) -> list[CapabilityResolution]:
    resolved: list[CapabilityResolution] = []
    seen: set[str] = set()
    for report in reports:
        for item in report.capabilities:
            if item.capability_id not in seen:
                resolved.append(item)
                seen.add(item.capability_id)
    if adapter_valid:
        resolved.append(CapabilityResolution(capabilityId=CAP_SOLVER_ADAPTER, source="Evaluator"))
    if adapter_valid and cross.status != "Inconclusive":
        resolved.append(CapabilityResolution(capabilityId=CAP_CROSS_VALIDATION, source="Evaluator"))
    if collision.status in {"safe", "collision"}:
        resolved.append(CapabilityResolution(capabilityId=CAP_M5_COLLISION, source="Evaluator"))
    return resolved


def evaluate_five_axis_f4(
    request: FiveAxisF4EvaluationBindingRequest | dict[str, Any],
) -> EvaluationReport:
    resolved = (
        request
        if isinstance(request, FiveAxisF4EvaluationBindingRequest)
        else FiveAxisF4EvaluationBindingRequest.model_validate(request)
    )
    adapter_valid = _adapter_contract_valid(resolved)
    cross = cross_validate_discrete_commands(resolved.reference_artifact, resolved.artifact)
    reports = _upstream_reports(resolved)
    f1_report, f2_report, f3_report = reports
    collision = verify_m5_configuration_collision(
        resolved.artifact,
        collision_model=resolved.collision_model,
    )
    upstream_by_metric = {
        result.metric_id: _source_metric(result, report)
        for report in reports
        for result in report.metric_results
    }

    metric_ids = [item.metric_id for item in resolved.case.required_metrics + resolved.case.optional_metrics]
    raw_results: list[MetricResult] = []
    for metric_id in metric_ids:
        if metric_id == MODEL_COLLISION_FREE_METRIC_ID:
            if not adapter_valid:
                result = _unavailable(metric_id, MetricStatus.UNSUPPORTED_CAPABILITY, "AdapterContractNotSatisfied")
            elif cross.status != "Supported":
                result = _unavailable(
                    metric_id,
                    MetricStatus.UNSUPPORTED_CAPABILITY,
                    "ReferenceSutCrossValidationNotSupported",
                )
            else:
                result = _model_collision_metric(f1_report, f2_report, collision)
        else:
            result = _metric_result(
                resolved,
                metric_id,
                adapter_valid=adapter_valid,
                cross=cross,
                collision=collision,
                upstream_by_metric=upstream_by_metric,
            )
        raw_results.append(result)

    thresholds = {
        item.metric_id: item.threshold
        for item in resolved.case.required_metrics + resolved.case.optional_metrics
    }
    results = [_apply_threshold(result, thresholds.get(result.metric_id)) for result in raw_results]
    required_count = len(resolved.case.required_metrics)
    case_outcome = _aggregate_outcome(results[:required_count])
    request_payload = resolved.model_dump(mode="json", by_alias=True, exclude_none=True)
    artifact_payload = resolved.artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    case_payload = resolved.case.model_dump(mode="json", by_alias=True, exclude_none=True)
    provenance = Provenance(
        requestHash=_content_hash(request_payload),
        artifactHash=_content_hash(artifact_payload),
        caseHash=_content_hash(case_payload),
        referenceHash=resolved.reference_artifact.content_id,
        referenceBindingHash=_content_hash(
            {
                "referenceInvocation": resolved.reference_invocation,
                "sutInvocation": resolved.sut_invocation,
            }
        ),
        runnerId=F4_RUNNER_ID,
        evaluatorVersion=F4_EVALUATOR_ID,
        executionOutcomePolicy=resolved.case.execution_outcome_policy,
        numericEnvironment=current_f4_numeric_environment(),
    )
    failures = [
        DomainFailure(
            code=result.reason_code,
            message=f"F4 metric {result.metric_id} did not produce a closed result.",
            path=f"case.requiredMetrics[{index}]",
            severity="finding",
        )
        for index, result in enumerate(results[:required_count])
        if result.status is not MetricStatus.COMPUTED and result.reason_code is not None
    ]
    report = EvaluationReport(
        executionStatus=ExecutionStatus.SUCCEEDED,
        caseOutcome=case_outcome,
        metricResults=results,
        capabilities=_capabilities(
            reports,
            adapter_valid=adapter_valid,
            cross=cross,
            collision=collision,
        ),
        domainFailures=failures,
        evaluatorVersion=F4_EVALUATOR_ID,
        provenance=provenance,
        contentHash="",
    )
    return _seal_evaluation_report(report)


FIVE_AXIS_F4_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=FIVE_AXIS_F4_DOMAIN_PACK_ID,
        parse_request=_parse_f4_request,
        evaluate=evaluate_five_axis_f4,
    )
)


__all__ = [
    "ADAPTER_CONTRACT_VALID_METRIC_ID",
    "CAP_CROSS_VALIDATION",
    "CAP_M5_COLLISION",
    "CAP_SOLVER_ADAPTER",
    "F4_EVALUATOR_ID",
    "F4_RUNNER_ID",
    "FIVE_AXIS_F4_DOMAIN_PACK",
    "FIVE_AXIS_F4_DOMAIN_PACK_ID",
    "FIVE_AXIS_F4_RUNTIME_BINDING",
    "FiveAxisF4EvaluationBindingRequest",
    "MODEL_COLLISION_FREE_CLAIM_ID",
    "MODEL_COLLISION_FREE_METRIC_ID",
    "REFERENCE_SUT_ACCELERATION_GAP_MAX_METRIC_ID",
    "REFERENCE_SUT_CROSS_VALIDATED_METRIC_ID",
    "REFERENCE_SUT_JERK_GAP_MAX_METRIC_ID",
    "REFERENCE_SUT_POSITION_GAP_MAX_METRIC_ID",
    "REFERENCE_SUT_VELOCITY_GAP_MAX_METRIC_ID",
    "current_f4_numeric_environment",
    "evaluate_five_axis_f4",
]
