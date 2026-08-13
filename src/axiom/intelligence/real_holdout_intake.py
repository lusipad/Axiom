from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite
from typing import Annotated, Any, Literal

from pydantic import (
    BeforeValidator,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from ..field_evidence import FieldEvidenceAssessmentReport
from ..machine.models import (
    CaptureReceipt,
    ClockMapping,
    CoordinateAlignment,
    DeviceIdentity,
    DeviceProfile,
    MachineObservationRequest,
    MachineRunLineage,
    MachineTelemetryTrace,
    TelemetryFrame,
    TelemetrySample,
)
from ..machine.runtime import machine_trace_content_hash
from ..models import AxiomModel, EvaluationCase, RunSpec
from ..physical.models import (
    AxisChannelBinding,
    PhysicalResponseSample,
    PhysicalResponseTrace,
)
from .models import HASH_PATTERN, VERSIONED_ID_PATTERN, canonical_hash
from .r5b_models import (
    R5B_DOMAIN_PACK_ID,
    R5B_EVALUATOR_ID,
    R5B_RUNNER_ID,
    R5BIntelligenceEvaluationRequest,
    RealHoldoutCaseEvidence,
    RealHoldoutGovernance,
    RealHoldoutSelectionReceipt,
    RealPairedHoldoutSet,
)

REAL_HOLDOUT_INTAKE_REQUEST_SCHEMA_ID = (
    "axiom.intelligence.real-holdout-intake-request@1"
)
REAL_HOLDOUT_INTAKE_REPORT_SCHEMA_ID = (
    "axiom.intelligence.real-holdout-intake-report@1"
)
REAL_HOLDOUT_INTAKE_ADAPTER_ID = "axiom.adapter.r7e-to-r5b-holdout@1"
REAL_HOLDOUT_TIMESTAMP_POLICY_ID = "axiom.r7e.x-source-timestamp@1"

_AXIS_CONTRACT = (
    ("X", 0, "linear-mm", "mm"),
    ("Y", 1, "linear-mm", "mm"),
    ("Z", 2, "linear-mm", "mm"),
    ("B", 3, "rotary-rad", "rad"),
    ("C", 4, "rotary-rad", "rad"),
)
_CHECK_IDS = (
    "real-holdout-intake.contract",
    "real-holdout-intake.base-r5b-lineage",
    "real-holdout-intake.field-reality",
    "real-holdout-intake.r3-r4-projection",
    "real-holdout-intake.independence",
    "real-holdout-intake.coverage",
    "real-holdout-intake.governance",
    "real-holdout-intake.output",
)
_R3_REQUIRED_METRICS = (
    "machine-observation.raw-integrity@1",
    "machine-observation.read-only-capture@1",
    "machine-observation.lineage-complete@1",
    "machine-observation.clock-aligned@1",
    "machine-observation.coordinate-context@1",
)


def _finite_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value must be a finite JSON number")
    if not isfinite(value):
        raise ValueError("value must be a finite JSON number")
    return value


def _field_evidence_report(value: Any) -> FieldEvidenceAssessmentReport:
    return FieldEvidenceAssessmentReport.model_validate(value)


def _typed_r5b_request(run_spec: RunSpec) -> R5BIntelligenceEvaluationRequest:
    return R5BIntelligenceEvaluationRequest.model_validate(
        run_spec.request.model_dump(mode="json", by_alias=True, exclude_none=True)
    )


def _sealed(model_type: type[AxiomModel], **values: Any) -> Any:
    provisional = model_type.model_construct(content_hash="0" * 64, **values)
    payload = provisional.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
        exclude={"content_hash"},
    )
    payload["contentHash"] = canonical_hash(
        provisional,
        exclude={"content_hash"},
    )
    return model_type.model_validate(payload)


class RealHoldoutIntakeCase(AxiomModel):
    report: Annotated[
        Any,
        BeforeValidator(_field_evidence_report),
        WithJsonSchema({"type": "object"}),
    ]
    role: Literal["in-domain", "ood-probe"]
    topology: Literal["dual-table", "head-table", "dual-head"]
    trajectory_family: str = Field(alias="trajectoryFamily", min_length=1)
    task_id: str = Field(alias="taskId", min_length=1)
    condition_id: str = Field(alias="conditionId", min_length=1)
    batch_id: str = Field(alias="batchId", min_length=1)
    maximum_time_error_seconds: float = Field(
        alias="maximumTimeErrorSeconds", ge=0
    )
    device_profile: DeviceProfile = Field(alias="deviceProfile")
    clock_mapping: ClockMapping = Field(alias="clockMapping")
    coordinate_alignment: CoordinateAlignment = Field(alias="coordinateAlignment")
    lineage: MachineRunLineage
    bindings: tuple[AxisChannelBinding, ...] = Field(min_length=5, max_length=5)

    @field_validator("maximum_time_error_seconds", mode="before")
    @classmethod
    def reject_invalid_tolerance(cls, value: Any) -> Any:
        return _finite_number(value)

    @model_validator(mode="after")
    def validate_projection_context(self) -> RealHoldoutIntakeCase:
        device_id = self.device_profile.device_id
        if self.clock_mapping.device_id != device_id:
            raise ValueError("clockMapping deviceId must match deviceProfile")
        if self.coordinate_alignment.device_id != device_id:
            raise ValueError("coordinateAlignment deviceId must match deviceProfile")
        if self.coordinate_alignment.calibration_status != "calibrated":
            raise ValueError("coordinateAlignment must be calibrated")
        if self.coordinate_alignment.source_kind == "synthetic-reference":
            raise ValueError("coordinateAlignment must not use synthetic-reference")

        observed = tuple(
            (
                binding.axis_id,
                binding.axis_index,
                binding.unit_family,
                binding.unit,
            )
            for binding in self.bindings
        )
        if observed != _AXIS_CONTRACT:
            raise ValueError("bindings must use the frozen X/Y/Z/B/C unit order")
        channel_ids = tuple(binding.channel_id for binding in self.bindings)
        if len(set(channel_ids)) != 5:
            raise ValueError("bindings channelId values must be unique")
        profile_channels = {
            channel.channel_id: channel for channel in self.device_profile.channels
        }
        for binding in self.bindings:
            channel = profile_channels.get(binding.channel_id)
            if channel is None:
                raise ValueError("binding channelId must be declared by deviceProfile")
            if channel.kind != "scalar" or channel.unit != binding.unit:
                raise ValueError(
                    "bound deviceProfile channels must be scalar and preserve axis units"
                )
        if set(self.coordinate_alignment.channel_ids) != set(channel_ids):
            raise ValueError(
                "coordinateAlignment channelIds must exactly cover the axis bindings"
            )
        return self


class RealHoldoutIntakeRequest(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.real-holdout-intake-request@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    intake_id: str = Field(alias="intakeId", pattern=VERSIONED_ID_PATTERN)
    holdout_set_id: str = Field(alias="holdoutSetId", pattern=VERSIONED_ID_PATTERN)
    selection_id: str = Field(alias="selectionId", pattern=VERSIONED_ID_PATTERN)
    selected_before_evaluation: Literal[True] = Field(
        alias="selectedBeforeEvaluation"
    )
    base_run_spec: RunSpec = Field(alias="baseRunSpec")
    governance: RealHoldoutGovernance
    cases: tuple[RealHoldoutIntakeCase, ...] = ()

    @model_validator(mode="after")
    def validate_base_run(self) -> RealHoldoutIntakeRequest:
        if self.base_run_spec.domain_pack_id != R5B_DOMAIN_PACK_ID:
            raise ValueError("baseRunSpec must use intelligence.domain-pack@2")
        if self.base_run_spec.runner_id != R5B_RUNNER_ID:
            raise ValueError(
                "baseRunSpec must use intelligence-real-holdout-validation@1"
            )
        if self.base_run_spec.evaluator_version != R5B_EVALUATOR_ID:
            raise ValueError(
                "baseRunSpec must use intelligence-real-holdout-evaluator@1"
            )
        request = _typed_r5b_request(self.base_run_spec)
        if request.real_holdout_set is not None:
            raise ValueError("baseRunSpec realHoldoutSet must be absent")
        return self


class RealHoldoutIntakeCheck(AxiomModel):
    check_id: str = Field(alias="checkId", min_length=1)
    title: str = Field(min_length=1)
    status: Literal["Passed", "Open", "Blocked"]
    reason_code: str | None = Field(default=None, alias="reasonCode")
    details: dict[str, Any] = Field(default_factory=dict)


class RealHoldoutProjectionReceipt(AxiomModel):
    case_id: str = Field(alias="caseId", min_length=1)
    status: Literal["Passed", "Open", "Blocked"]
    reason_code: str | None = Field(default=None, alias="reasonCode")
    source_report_content_hash: str = Field(
        alias="sourceReportContentHash", pattern=HASH_PATTERN
    )
    source_shadow_evidence_content_hash: str | None = Field(
        default=None,
        alias="sourceShadowEvidenceContentHash",
        pattern=HASH_PATTERN,
    )
    source_reality_analysis_content_hash: str = Field(
        alias="sourceRealityAnalysisContentHash", pattern=HASH_PATTERN
    )
    observation_content_hash: str | None = Field(
        default=None, alias="observationContentHash", pattern=HASH_PATTERN
    )
    response_trace_content_hash: str | None = Field(
        default=None, alias="responseTraceContentHash", pattern=HASH_PATTERN
    )
    case_evidence_content_hash: str | None = Field(
        default=None, alias="caseEvidenceContentHash", pattern=HASH_PATTERN
    )
    timestamp_policy_id: Literal[
        "axiom.r7e.x-source-timestamp@1"
    ] = Field(alias="timestampPolicyId")
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> RealHoldoutProjectionReceipt:
        outputs = (
            self.source_shadow_evidence_content_hash,
            self.observation_content_hash,
            self.response_trace_content_hash,
            self.case_evidence_content_hash,
        )
        if self.status == "Passed" and any(value is None for value in outputs):
            raise ValueError("Passed projection receipt requires all output hashes")
        if self.status != "Passed" and any(value is not None for value in outputs):
            raise ValueError("non-Passed projection receipt must not publish outputs")
        if self.status == "Passed" and self.reason_code is not None:
            raise ValueError("Passed projection receipt must not include reasonCode")
        if self.status != "Passed" and self.reason_code is None:
            raise ValueError("non-Passed projection receipt requires reasonCode")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match projection receipt")
        return self


class RealHoldoutIntakeReport(AxiomModel):
    schema_id: Literal[
        "axiom.intelligence.real-holdout-intake-report@1"
    ] = Field(alias="schemaId")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    intake_id: str = Field(alias="intakeId", pattern=VERSIONED_ID_PATTERN)
    checks: tuple[RealHoldoutIntakeCheck, ...] = Field(min_length=8, max_length=8)
    projected_cases: tuple[RealHoldoutProjectionReceipt, ...] = Field(
        alias="projectedCases"
    )
    real_holdout_set: RealPairedHoldoutSet | None = Field(
        default=None, alias="realHoldoutSet"
    )
    r5b_run_spec: RunSpec | None = Field(default=None, alias="r5bRunSpec")
    intake_status: Literal["Passed", "Open", "Blocked"] = Field(
        alias="intakeStatus"
    )
    counts_toward_reality: bool = Field(alias="countsTowardReality")
    validation_scope: Literal["submitted-cases-only"] = Field(
        alias="validationScope"
    )
    controlled_trial_status: Literal["Open"] = Field(alias="controlledTrialStatus")
    closed_loop_status: Literal["Open"] = Field(alias="closedLoopStatus")
    device_safety_status: Literal["NotAssessed"] = Field(alias="deviceSafetyStatus")
    process_safety_status: Literal["NotAssessed"] = Field(
        alias="processSafetyStatus"
    )
    content_hash: str = Field(alias="contentHash", pattern=HASH_PATTERN)

    @model_validator(mode="after")
    def verify_report(self) -> RealHoldoutIntakeReport:
        if tuple(check.check_id for check in self.checks) != _CHECK_IDS:
            raise ValueError("checks must use the frozen intake order")
        has_outputs = self.real_holdout_set is not None and self.r5b_run_spec is not None
        if (self.real_holdout_set is None) != (self.r5b_run_spec is None):
            raise ValueError("realHoldoutSet and r5bRunSpec must be present together")
        if (self.intake_status == "Passed") != has_outputs:
            raise ValueError("Passed intake requires both output artifacts")
        if self.counts_toward_reality != (self.intake_status == "Passed"):
            raise ValueError("countsTowardReality must reflect intakeStatus")
        if self.r5b_run_spec is not None and self.real_holdout_set is not None:
            typed = _typed_r5b_request(self.r5b_run_spec)
            if typed.real_holdout_set != self.real_holdout_set:
                raise ValueError("r5bRunSpec must embed realHoldoutSet exactly")
        if self.content_hash != canonical_hash(self, exclude={"content_hash"}):
            raise ValueError("contentHash must match intake report")
        return self


def _check(
    check_id: str,
    title: str,
    status: Literal["Passed", "Open", "Blocked"],
    reason_code: str | None = None,
    **details: Any,
) -> RealHoldoutIntakeCheck:
    return RealHoldoutIntakeCheck(
        checkId=check_id,
        title=title,
        status=status,
        reasonCode=reason_code,
        details=details,
    )


def _projection_receipt(
    case: RealHoldoutIntakeCase,
    *,
    status: Literal["Passed", "Open", "Blocked"],
    reason_code: str | None,
    shadow_hash: str | None = None,
    observation_hash: str | None = None,
    response_hash: str | None = None,
    case_hash: str | None = None,
) -> RealHoldoutProjectionReceipt:
    return _sealed(
        RealHoldoutProjectionReceipt,
        case_id=case.report.case_id,
        status=status,
        reason_code=reason_code,
        source_report_content_hash=case.report.content_hash,
        source_shadow_evidence_content_hash=shadow_hash,
        source_reality_analysis_content_hash=(
            case.report.reality_assessment.analysis.content_hash
        ),
        observation_content_hash=observation_hash,
        response_trace_content_hash=response_hash,
        case_evidence_content_hash=case_hash,
        timestamp_policy_id=REAL_HOLDOUT_TIMESTAMP_POLICY_ID,
    )


def _projection_source(case: RealHoldoutIntakeCase) -> tuple[Any, Any, Any, Any]:
    report = case.report
    if report.overall_status != "Passed" or not report.counts_toward_reality:
        raise RuntimeError("FieldEvidenceNotPassed")
    if report.validation_pair is None:
        raise ValueError("Passed field report requires validationPair")
    analysis = report.reality_assessment.analysis
    if (
        analysis.reality_validation_status != "Passed"
        or not analysis.counts_toward_reality
        or analysis.model is None
        or len(analysis.axes) != 5
    ):
        raise ValueError("Passed field report requires complete R4.1 validation output")
    request = report.validation_pair.parsed_r7e_request()
    if (
        request.command is None
        or request.shadow_evidence is None
        or request.controller_profile is None
    ):
        raise ValueError("validation pair requires command, Shadow evidence and controller")
    if (
        request.shadow_evidence.source_kind != "controller-live-read"
        or not request.shadow_evidence.declared_real
    ):
        raise ValueError("validation Shadow evidence must be declared controller-live-read")
    return request, request.command, request.shadow_evidence, analysis


def _machine_observation(
    case: RealHoldoutIntakeCase,
    request: Any,
    command: Any,
    evidence: Any,
    analysis: Any,
) -> MachineObservationRequest:
    controller = request.controller_profile
    if case.device_profile.device_id != controller.machine_id:
        raise ValueError("deviceProfile deviceId must match field controller machineId")
    if case.device_profile.manufacturer != controller.vendor:
        raise ValueError("deviceProfile manufacturer must match field controller vendor")
    if case.device_profile.controller_family != controller.controller_family:
        raise ValueError(
            "deviceProfile controllerFamily must match field controller family"
        )
    if case.lineage.source_command_content_hash != command.content_id:
        raise ValueError("lineage source command hash must match validation command")

    bindings = {binding.axis_id: binding for binding in case.bindings}
    frames: list[TelemetryFrame] = []
    for source_frame in evidence.frames:
        axis_samples = {sample.axis_id: sample for sample in source_frame.samples}
        x_sample = axis_samples["X"]
        frames.append(
            TelemetryFrame(
                sequenceId=source_frame.sequence,
                deviceTimestamp=x_sample.source_timestamp,
                samples=tuple(
                    TelemetrySample(
                        channelId=bindings[axis_id].channel_id,
                        value=axis_samples[axis_id].value,
                        unit=axis_samples[axis_id].unit,
                        quality=axis_samples[axis_id].quality,
                    )
                    for axis_id, *_ in _AXIS_CONTRACT
                ),
                alarms=(),
            )
        )

    trace = MachineTelemetryTrace(
        artifactType="machine.telemetry-trace",
        schemaVersion=1,
        traceId=evidence.evidence_id,
        sourceKind="device-read",
        captureReceipt=CaptureReceipt(
            receiptId=f"{case.report.assessment_id}.validation-import",
            sourceId="axiom.windows-file-telemetry-source@1",
            operation="file-import",
            transport="windows-file-json",
            capturedAt=evidence.captured_at,
            traceContentHash="0" * 64,
        ),
        deviceIdentity=DeviceIdentity(
            deviceId=controller.machine_id,
            controllerFamily=controller.controller_family,
            machineModel=case.device_profile.machine_model,
        ),
        frames=tuple(frames),
        vendorMetadata={
            "adapterId": REAL_HOLDOUT_INTAKE_ADAPTER_ID,
            "timestampPolicyId": REAL_HOLDOUT_TIMESTAMP_POLICY_ID,
            "sourceFieldEvidenceReportContentHash": case.report.content_hash,
            "sourceValidationShadowEvidenceContentHash": evidence.content_hash,
            "sourceR41AnalysisContentHash": analysis.content_hash,
            "sourceFrameBindings": [
                {
                    "sequence": frame.sequence,
                    "protocolSequenceNumber": frame.protocol_sequence_number,
                    "notifiedSampleIndex": frame.notified_sample_index,
                    "readSampleIndex": frame.read_sample_index,
                    "hostTimestamp": frame.host_timestamp,
                    "axisSourceTimestamps": {
                        sample.axis_id: sample.source_timestamp
                        for sample in frame.samples
                    },
                    "axisServerTimestamps": {
                        sample.axis_id: sample.server_timestamp
                        for sample in frame.samples
                    },
                }
                for frame in evidence.frames
            ],
        },
    )
    trace_payload = trace.model_dump(mode="json", by_alias=True)
    trace_payload["captureReceipt"]["traceContentHash"] = (
        machine_trace_content_hash(trace)
    )
    trace = MachineTelemetryTrace.model_validate(trace_payload)
    return MachineObservationRequest(
        artifact=trace,
        deviceProfile=case.device_profile,
        clockMapping=case.clock_mapping,
        coordinateAlignment=case.coordinate_alignment,
        lineage=case.lineage,
        case=EvaluationCase(
            caseId=case.report.case_id,
            requiredMetrics=tuple(
                {"metricId": metric_id} for metric_id in _R3_REQUIRED_METRICS
            ),
        ),
    )


def _response_trace(
    case: RealHoldoutIntakeCase,
    command: Any,
    analysis: Any,
) -> PhysicalResponseTrace:
    axes = tuple(analysis.axes)
    observed = tuple(
        (axis.axis_id, axis.axis_index, axis.unit_family, axis.unit) for axis in axes
    )
    if observed != _AXIS_CONTRACT:
        raise ValueError("R4.1 axes must use the frozen X/Y/Z/B/C order")
    times = tuple(axes[0].times)
    if not times or any(tuple(axis.times) != times for axis in axes):
        raise ValueError("R4.1 axes must share one non-empty validation time grid")
    if any(
        len(axis.command) != len(times) or len(axis.simulation) != len(times)
        for axis in axes
    ):
        raise ValueError("R4.1 validation series must cover every response sample")

    return _sealed(
        PhysicalResponseTrace,
        artifact_type="five-axis.physical-response-trace",
        schema_id="five-axis.physical-response-trace@1",
        schema_version=1,
        response_trace_id=f"{case.report.assessment_id}.validation-response",
        source_kind="synthetic-sil",
        source_model_id=analysis.model.model_id,
        source_model_content_hash=analysis.model.content_hash,
        source_command_id=command.discrete_command_id,
        source_command_content_id=command.content_id,
        sample_period=command.sample_period,
        axis_units=("mm", "mm", "mm", "rad", "rad"),
        integration_method="exact-zoh",
        samples=tuple(
            PhysicalResponseSample(
                sampleIndex=index,
                t=sample_time,
                command=tuple(axis.command[index] for axis in axes),
                simulated=tuple(axis.simulation[index] for axis in axes),
            )
            for index, sample_time in enumerate(times)
        ),
    )


def _case_evidence(case: RealHoldoutIntakeCase) -> tuple[
    RealHoldoutCaseEvidence,
    RealHoldoutProjectionReceipt,
]:
    request, command, evidence, analysis = _projection_source(case)
    observation = _machine_observation(case, request, command, evidence, analysis)
    response = _response_trace(case, command, analysis)
    first_axis_times = analysis.axes[0].times
    first_x_timestamp = evidence.frames[0].samples[0].source_timestamp
    anchor = datetime.fromisoformat(first_x_timestamp) - timedelta(
        seconds=float(first_axis_times[0])
    )
    evidence_case = _sealed(
        RealHoldoutCaseEvidence,
        case_id=case.report.case_id,
        role=case.role,
        topology=case.topology,
        trajectory_family=case.trajectory_family,
        task_id=case.task_id,
        condition_id=case.condition_id,
        batch_id=case.batch_id,
        pair_id=case.report.validation_pair_id,
        source_kind="device-read",
        observation=observation,
        response_trace=response,
        scalar_channel_id=case.bindings[0].channel_id,
        scalar_unit="mm",
        capture_start_time=evidence.receipt.opened_at,
        capture_end_time=evidence.receipt.closed_at,
        device_time_anchor=anchor.isoformat(),
        maximum_time_error_seconds=case.maximum_time_error_seconds,
    )
    receipt = _projection_receipt(
        case,
        status="Passed",
        reason_code=None,
        shadow_hash=evidence.content_hash,
        observation_hash=canonical_hash(observation),
        response_hash=response.content_hash,
        case_hash=evidence_case.content_hash,
    )
    return evidence_case, receipt


def _coverage_gaps(
    cases: tuple[RealHoldoutCaseEvidence, ...],
) -> tuple[str, ...]:
    gaps: list[str] = []
    in_domain = tuple(case for case in cases if case.role == "in-domain")
    if len(cases) < 3:
        gaps.append("minimum-total-cases")
    if len(in_domain) < 2:
        gaps.append("minimum-in-domain-cases")
    if not any(case.role == "ood-probe" for case in cases):
        gaps.append("missing-ood-probe")
    if len({case.observation.artifact.device_identity.device_id for case in in_domain}) < 2:
        gaps.append("minimum-distinct-devices")
    if len({case.condition_id for case in in_domain}) < 2:
        gaps.append("minimum-distinct-conditions")
    return tuple(gaps)


def _independence_reason(cases: tuple[RealHoldoutIntakeCase, ...]) -> str | None:
    report_hashes = [case.report.content_hash for case in cases]
    if len(report_hashes) != len(set(report_hashes)):
        return "FieldEvidenceReportReused"
    validation_hashes = [
        case.report.validation_pair.shadow_evidence_content_hash
        for case in cases
        if case.report.validation_pair is not None
    ]
    if len(validation_hashes) != len(set(validation_hashes)):
        return "ValidationShadowEvidenceReused"
    return None


def _governance_status(
    request: RealHoldoutIntakeRequest,
    projected: tuple[RealHoldoutCaseEvidence, ...],
) -> tuple[Literal["Passed", "Open", "Blocked"], str | None]:
    if projected:
        latest_capture_end = max(
            datetime.fromisoformat(case.capture_end_time) for case in projected
        )
        if datetime.fromisoformat(request.governance.attested_at) < latest_capture_end:
            return "Blocked", "GovernanceAttestationPrecedesCaptureCompletion"
    if len(projected) != len(request.cases) or not projected:
        return "Open", "GovernanceTimingNotFullyAssessable"
    return "Passed", None


def _run_spec_with_holdout(
    base: RunSpec,
    holdout_set: RealPairedHoldoutSet,
) -> RunSpec:
    payload = base.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["request"]["realHoldoutSet"] = holdout_set.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    typed = R5BIntelligenceEvaluationRequest.model_validate(payload["request"])
    payload["request"] = typed.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    return RunSpec.model_validate(payload)


def _report(
    request: RealHoldoutIntakeRequest,
    *,
    checks: tuple[RealHoldoutIntakeCheck, ...],
    receipts: tuple[RealHoldoutProjectionReceipt, ...],
    status: Literal["Passed", "Open", "Blocked"],
    holdout_set: RealPairedHoldoutSet | None = None,
    run_spec: RunSpec | None = None,
) -> RealHoldoutIntakeReport:
    return _sealed(
        RealHoldoutIntakeReport,
        schema_id=REAL_HOLDOUT_INTAKE_REPORT_SCHEMA_ID,
        schema_version=1,
        intake_id=request.intake_id,
        checks=checks,
        projected_cases=receipts,
        real_holdout_set=holdout_set,
        r5b_run_spec=run_spec,
        intake_status=status,
        counts_toward_reality=status == "Passed",
        validation_scope="submitted-cases-only",
        controlled_trial_status="Open",
        closed_loop_status="Open",
        device_safety_status="NotAssessed",
        process_safety_status="NotAssessed",
    )


def assess_real_holdout_intake(
    request: RealHoldoutIntakeRequest,
) -> RealHoldoutIntakeReport:
    checks: list[RealHoldoutIntakeCheck] = [
        _check(
            _CHECK_IDS[0],
            "Typed application-layer intake contract",
            "Passed",
            schemaId=request.schema_id,
            adapterId=REAL_HOLDOUT_INTAKE_ADAPTER_ID,
        ),
        _check(
            _CHECK_IDS[1],
            "Frozen R5-B base model lineage",
            "Passed",
            modelBundleHash=_typed_r5b_request(
                request.base_run_spec
            ).artifact.content_hash,
        ),
    ]

    source_statuses = tuple(case.report.overall_status for case in request.cases)
    source_missing = not source_statuses
    source_blocked = any(status in {"Blocked", "Refuted"} for status in source_statuses)
    source_open = source_missing or any(
        status != "Passed" for status in source_statuses
    )
    checks.append(
        _check(
            _CHECK_IDS[2],
            "R7-E/R4.1 source reality gates",
            "Blocked" if source_blocked else "Open" if source_open else "Passed",
            (
                "FieldEvidenceSourceBlocked"
                if source_blocked
                else "FieldEvidenceMissing"
                if source_missing
                else "FieldEvidenceSourceOpen"
                if source_open
                else None
            ),
            sourceStatuses=list(source_statuses),
        )
    )

    independence_reason = _independence_reason(request.cases)
    projected: list[RealHoldoutCaseEvidence] = []
    receipts: list[RealHoldoutProjectionReceipt] = []
    projection_error: str | None = None
    if independence_reason is None:
        for case in request.cases:
            if case.report.overall_status != "Passed":
                receipts.append(
                    _projection_receipt(
                        case,
                        status="Open"
                        if case.report.overall_status == "Open"
                        else "Blocked",
                        reason_code=f"FieldEvidence{case.report.overall_status}",
                    )
                )
                continue
            try:
                evidence_case, receipt = _case_evidence(case)
            except (ValueError, RuntimeError) as exc:
                projection_error = str(exc)
                receipts.append(
                    _projection_receipt(
                        case,
                        status="Blocked",
                        reason_code="R7EProjectionInvalid",
                    )
                )
                continue
            projected.append(evidence_case)
            receipts.append(receipt)
    else:
        for case in request.cases:
            receipts.append(
                _projection_receipt(
                    case,
                    status="Blocked",
                    reason_code=independence_reason,
                )
            )

    projection_status: Literal["Passed", "Open", "Blocked"] = (
        "Blocked"
        if independence_reason is not None or projection_error is not None
        else "Open"
        if source_open
        else "Passed"
    )
    checks.append(
        _check(
            _CHECK_IDS[3],
            "Lossless R3 observation and R4 response projection",
            projection_status,
            (
                independence_reason
                or ("R7EProjectionInvalid" if projection_error else None)
                or (
                    "FieldEvidenceMissing"
                    if source_missing
                    else "FieldEvidenceSourceOpen"
                    if source_open
                    else None
                )
            ),
            projectedCaseCount=len(projected),
            error=projection_error,
        )
    )
    checks.append(
        _check(
            _CHECK_IDS[4],
            "Independent field report and validation evidence identities",
            "Blocked" if independence_reason else "Passed",
            independence_reason,
        )
    )

    coverage_gaps = _coverage_gaps(tuple(projected))
    checks.append(
        _check(
            _CHECK_IDS[5],
            "Cross-device, cross-condition and OOD coverage",
            "Open" if coverage_gaps else "Passed",
            "RealHoldoutCoverageIncomplete" if coverage_gaps else None,
            coverageGaps=list(coverage_gaps),
        )
    )

    governance_status, governance_reason = _governance_status(
        request, tuple(projected)
    )

    if (
        source_blocked
        or independence_reason is not None
        or projection_error is not None
        or governance_status == "Blocked"
    ):
        checks.extend(
            (
                _check(
                    _CHECK_IDS[6],
                    "External owner governance and selection timing",
                    governance_status,
                    governance_reason,
                    governanceHash=request.governance.content_hash,
                ),
                _check(
                    _CHECK_IDS[7],
                    "RealPairedHoldoutSet and R5-B RunSpec",
                    "Blocked",
                    independence_reason
                    or governance_reason
                    or "UpstreamEvidenceBlocked",
                ),
            )
        )
        return _report(
            request,
            checks=tuple(checks),
            receipts=tuple(receipts),
            status="Blocked",
        )

    if source_open or coverage_gaps:
        checks.extend(
            (
                _check(
                    _CHECK_IDS[6],
                    "External owner governance and selection timing",
                    governance_status,
                    governance_reason,
                    governanceHash=request.governance.content_hash,
                ),
                _check(
                    _CHECK_IDS[7],
                    "RealPairedHoldoutSet and R5-B RunSpec",
                    "Open",
                    "RealHoldoutEvidenceIncomplete",
                ),
            )
        )
        return _report(
            request,
            checks=tuple(checks),
            receipts=tuple(receipts),
            status="Open",
        )

    base_request = _typed_r5b_request(request.base_run_spec)
    selection = _sealed(
        RealHoldoutSelectionReceipt,
        selection_id=request.selection_id,
        model_bundle_hash=base_request.artifact.content_hash,
        training_dataset_hash=base_request.dataset.content_hash,
        selected_before_evaluation=True,
        leakage_dimensions=("device", "condition", "task", "batch", "time"),
        case_ids=tuple(case.case_id for case in projected),
    )
    try:
        holdout_set = _sealed(
            RealPairedHoldoutSet,
            artifact_type="axiom.intelligence.real-paired-holdout-set",
            schema_id="axiom.intelligence.real-paired-holdout-set@1",
            schema_version=1,
            holdout_set_id=request.holdout_set_id,
            model_bundle_hash=base_request.artifact.content_hash,
            training_dataset_hash=base_request.dataset.content_hash,
            governance=request.governance,
            selection=selection,
            cases=tuple(projected),
        )
        run_spec = _run_spec_with_holdout(request.base_run_spec, holdout_set)
    except ValueError as exc:
        checks.extend(
            (
                _check(
                    _CHECK_IDS[6],
                    "External owner governance and selection timing",
                    "Blocked",
                    "RealHoldoutGovernanceOrIsolationInvalid",
                    error=str(exc),
                ),
                _check(
                    _CHECK_IDS[7],
                    "RealPairedHoldoutSet and R5-B RunSpec",
                    "Blocked",
                    "RealHoldoutSetInvalid",
                ),
            )
        )
        return _report(
            request,
            checks=tuple(checks),
            receipts=tuple(receipts),
            status="Blocked",
        )

    checks.extend(
        (
            _check(
                _CHECK_IDS[6],
                "External owner governance and selection timing",
                "Passed",
                governanceHash=request.governance.content_hash,
                selectionHash=selection.content_hash,
            ),
            _check(
                _CHECK_IDS[7],
                "RealPairedHoldoutSet and R5-B RunSpec",
                "Passed",
                holdoutSetHash=holdout_set.content_hash,
            ),
        )
    )
    return _report(
        request,
        checks=tuple(checks),
        receipts=tuple(receipts),
        status="Passed",
        holdout_set=holdout_set,
        run_spec=run_spec,
    )


__all__ = [
    "REAL_HOLDOUT_INTAKE_ADAPTER_ID",
    "REAL_HOLDOUT_INTAKE_REPORT_SCHEMA_ID",
    "REAL_HOLDOUT_INTAKE_REQUEST_SCHEMA_ID",
    "REAL_HOLDOUT_TIMESTAMP_POLICY_ID",
    "RealHoldoutIntakeCase",
    "RealHoldoutIntakeCheck",
    "RealHoldoutIntakeReport",
    "RealHoldoutIntakeRequest",
    "RealHoldoutProjectionReceipt",
    "assess_real_holdout_intake",
]
