from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime
from importlib.metadata import version as package_version
from itertools import pairwise
from pathlib import Path
from typing import Any

from ..domain import (
    CASE_OUTCOME_CLAIM_DEFINITION_ID,
    DomainPack,
    FailureMapping,
    MetricDefinition,
    register_domain_pack,
)
from ..evaluator import (
    _aggregate_outcome,
    _apply_threshold,
    _content_hash,
    _seal_evaluation_report,
)
from ..models import (
    CapabilityResolution,
    CaseOutcome,
    CoreEvaluationRequest,
    EvaluationReport,
    Evidence,
    ExecutionStatus,
    MetricResult,
    MetricStatus,
    Provenance,
)
from ..runtime import DomainRuntimeBinding, register_domain_runtime_binding
from .models import (
    LoadedMachineTelemetryCapture,
    MachineObservationRequest,
    MachineTelemetryTrace,
)

MACHINE_OBSERVATION_DOMAIN_PACK_ID = "machine-observation.domain-pack@1"
MACHINE_OBSERVATION_EVALUATOR_ID = "machine-observation-evaluator@1"
MACHINE_TRACE_IMPORT_RUNNER_ID = "machine-trace-import@1"

RAW_INTEGRITY_METRIC_ID = "machine-observation.raw-integrity@1"
READ_ONLY_CAPTURE_METRIC_ID = "machine-observation.read-only-capture@1"
LINEAGE_COMPLETE_METRIC_ID = "machine-observation.lineage-complete@1"
CLOCK_ALIGNED_METRIC_ID = "machine-observation.clock-aligned@1"
COORDINATE_CONTEXT_METRIC_ID = "machine-observation.coordinate-context@1"

RAW_INTEGRITY_CLAIM_ID = "machine-observation.raw-integrity-claim@1"
READ_ONLY_CAPTURE_CLAIM_ID = "machine-observation.read-only-capture-claim@1"
LINEAGE_COMPLETE_CLAIM_ID = "machine-observation.lineage-complete-claim@1"
CLOCK_ALIGNED_CLAIM_ID = "machine-observation.clock-aligned-claim@1"
COORDINATE_CONTEXT_CLAIM_ID = "machine-observation.coordinate-context-claim@1"

CAP_RAW_CAPTURE = "machine-observation.trace.raw@1"
CAP_READ_ONLY_CAPTURE = "machine-observation.capture.read-only@1"
CAP_LINEAGE = "machine-observation.lineage.bound@1"
CAP_CLOCK_MAPPING = "machine-observation.clock.mapping.bound@1"
CAP_COORDINATE_CONTEXT = "machine-observation.coordinate.context.bound@1"


def _metric_definition(
    metric_id: str,
    *,
    requires: tuple[str, ...],
    claim_definition_id: str | None = None,
    predicate: str | None = None,
) -> MetricDefinition:
    return MetricDefinition(
        metricId=metric_id,
        metricDefinitionId=metric_id,
        requires=requires,
        claimDefinitionId=claim_definition_id,
        claimPredicate=predicate,
    )


MACHINE_OBSERVATION_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domainPackId=MACHINE_OBSERVATION_DOMAIN_PACK_ID,
        artifactType="machine.telemetry-trace",
        artifactSchemaVersions=(1,),
        evaluatorVersion=MACHINE_OBSERVATION_EVALUATOR_ID,
        runnerId=MACHINE_TRACE_IMPORT_RUNNER_ID,
        runnerIds=(MACHINE_TRACE_IMPORT_RUNNER_ID,),
        importRunnerIds=(MACHINE_TRACE_IMPORT_RUNNER_ID,),
        capabilityIds=(
            CAP_RAW_CAPTURE,
            CAP_READ_ONLY_CAPTURE,
            CAP_LINEAGE,
            CAP_CLOCK_MAPPING,
            CAP_COORDINATE_CONTEXT,
        ),
        metricDefinitions=(
            _metric_definition(
                RAW_INTEGRITY_METRIC_ID,
                requires=(CAP_RAW_CAPTURE,),
                claim_definition_id=RAW_INTEGRITY_CLAIM_ID,
                predicate="machine-observation.raw-integrity is true",
            ),
            _metric_definition(
                READ_ONLY_CAPTURE_METRIC_ID,
                requires=(CAP_READ_ONLY_CAPTURE,),
                claim_definition_id=READ_ONLY_CAPTURE_CLAIM_ID,
                predicate="machine-observation.read-only-capture is true",
            ),
            _metric_definition(
                LINEAGE_COMPLETE_METRIC_ID,
                requires=(CAP_LINEAGE,),
                claim_definition_id=LINEAGE_COMPLETE_CLAIM_ID,
                predicate="machine-observation.lineage-complete is true",
            ),
            _metric_definition(
                CLOCK_ALIGNED_METRIC_ID,
                requires=(CAP_CLOCK_MAPPING,),
                claim_definition_id=CLOCK_ALIGNED_CLAIM_ID,
                predicate="machine-observation.clock-aligned is true",
            ),
            _metric_definition(
                COORDINATE_CONTEXT_METRIC_ID,
                requires=(CAP_COORDINATE_CONTEXT,),
                claim_definition_id=COORDINATE_CONTEXT_CLAIM_ID,
                predicate="machine-observation.coordinate-context is true",
            ),
        ),
        claimDefinitionIds=(
            CASE_OUTCOME_CLAIM_DEFINITION_ID,
            RAW_INTEGRITY_CLAIM_ID,
            READ_ONLY_CAPTURE_CLAIM_ID,
            LINEAGE_COMPLETE_CLAIM_ID,
            CLOCK_ALIGNED_CLAIM_ID,
            COORDINATE_CONTEXT_CLAIM_ID,
        ),
        comparisonPolicyIds=(),
        failureMappings=(
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
        ),
    )
)


def _raw_trace_identity(trace: MachineTelemetryTrace) -> dict[str, Any]:
    payload = trace.model_dump(mode="json", by_alias=True, exclude_none=True)
    payload["captureReceipt"].pop("traceContentHash", None)
    return payload


def machine_trace_content_hash(trace: MachineTelemetryTrace) -> str:
    return _content_hash(_raw_trace_identity(trace))


def load_machine_telemetry_capture(path: str | Path) -> LoadedMachineTelemetryCapture:
    source_path = Path(path).resolve()
    source_bytes = source_path.read_bytes()
    source_file_hash = hashlib.sha256(source_bytes).hexdigest()
    payload = json.loads(source_bytes.decode("utf-8"))
    artifact = MachineTelemetryTrace.model_validate(payload)
    actual_trace_hash = machine_trace_content_hash(artifact)
    if actual_trace_hash != artifact.capture_receipt.trace_content_hash:
        raise ValueError("captureReceipt.traceContentHash does not match the raw telemetry trace payload")
    return LoadedMachineTelemetryCapture.from_loaded_file(
        artifact=artifact,
        path=source_path,
        source_file_hash=source_file_hash,
        source_byte_length=len(source_bytes),
    )


def _parse_request(request: CoreEvaluationRequest) -> MachineObservationRequest:
    payload = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return MachineObservationRequest.model_validate(payload)


def _observed_evidence(method: str) -> Evidence:
    return Evidence(level="Observed", method=method)


def _result(
    metric_id: str,
    *,
    status: MetricStatus,
    value: Any = None,
    reason_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> MetricResult:
    return MetricResult(
        metricId=metric_id,
        metricDefinitionId=metric_id,
        requires=MACHINE_OBSERVATION_DOMAIN_PACK.metric_definition(metric_id).requires,
        status=status,
        value=value,
        reasonCode=reason_code,
        details=details or {},
        evidence=_observed_evidence(f"{metric_id}.audit@1"),
    )


def _bind_boolean_gate(result: MetricResult) -> MetricResult:
    if result.threshold_passed is not None:
        return result
    if result.status is MetricStatus.COMPUTED and isinstance(result.value, bool):
        return result.model_copy(update={"threshold_passed": result.value})
    return result


def _evaluate_raw_integrity(request: MachineObservationRequest) -> MetricResult:
    trace = request.artifact
    actual_trace_hash = machine_trace_content_hash(trace)
    if actual_trace_hash != trace.capture_receipt.trace_content_hash:
        return _result(
            RAW_INTEGRITY_METRIC_ID,
            status=MetricStatus.COMPUTED,
            value=False,
            reason_code="TraceContentHashMismatch",
            details={
                "expectedTraceContentHash": trace.capture_receipt.trace_content_hash,
                "actualTraceContentHash": actual_trace_hash,
                "interpolationApplied": False,
            },
        )
    sequence_ids = [frame.sequence_id for frame in trace.frames]
    if any(right <= left for left, right in pairwise(sequence_ids)):
        return _result(
            RAW_INTEGRITY_METRIC_ID,
            status=MetricStatus.COMPUTED,
            value=False,
            reason_code="FrameSequenceDiscontinuous",
            details={"sequenceIds": sequence_ids, "interpolationApplied": False},
        )
    if sequence_ids and any(right - left != 1 for left, right in pairwise(sequence_ids)):
        return _result(
            RAW_INTEGRITY_METRIC_ID,
            status=MetricStatus.COMPUTED,
            value=False,
            reason_code="FrameSequenceDiscontinuous",
            details={"sequenceIds": sequence_ids, "interpolationApplied": False},
        )
    timestamps = [frame.device_timestamp for frame in trace.frames]
    parsed_timestamps = [datetime.fromisoformat(value) for value in timestamps]
    if any(right < left for left, right in pairwise(parsed_timestamps)):
        return _result(
            RAW_INTEGRITY_METRIC_ID,
            status=MetricStatus.COMPUTED,
            value=False,
            reason_code="FrameTimestampReordered",
            details={"deviceTimestamps": timestamps, "interpolationApplied": False},
        )
    return _result(
        RAW_INTEGRITY_METRIC_ID,
        status=MetricStatus.COMPUTED,
        value=True,
        details={"traceContentHash": actual_trace_hash, "interpolationApplied": False},
    )


def _evaluate_read_only_capture(request: MachineObservationRequest) -> MetricResult:
    receipt = request.artifact.capture_receipt
    passed = receipt.source_id == "axiom.windows-file-telemetry-source@1" and receipt.transport == "windows-file-json"
    return _result(
        READ_ONLY_CAPTURE_METRIC_ID,
        status=MetricStatus.COMPUTED,
        value=passed,
        reason_code=None if passed else "ReadOnlySourceMismatch",
        details={"operation": receipt.operation, "transport": receipt.transport},
    )


def _evaluate_lineage(request: MachineObservationRequest) -> MetricResult:
    lineage = request.lineage
    if lineage.pairing_status == "unpaired":
        return _result(
            LINEAGE_COMPLETE_METRIC_ID,
            status=MetricStatus.INSUFFICIENT_CONTEXT,
            reason_code="UnpairedLineage",
            details={"pairingStatus": "unpaired"},
        )
    return _result(
        LINEAGE_COMPLETE_METRIC_ID,
        status=MetricStatus.COMPUTED,
        value=True,
        details={
            "pairingStatus": lineage.pairing_status,
            "baselineRunBundleHash": lineage.baseline_run_bundle_hash,
            "sourceCommandContentHash": lineage.source_command_content_hash,
        },
    )


def _evaluate_clock_alignment(request: MachineObservationRequest) -> MetricResult:
    mapping = request.clock_mapping
    if mapping is None:
        return _result(
            CLOCK_ALIGNED_METRIC_ID,
            status=MetricStatus.INSUFFICIENT_CONTEXT,
            reason_code="ClockMappingMissing",
            details={"interpolationApplied": False},
        )
    passed = (
        mapping.device_id == request.artifact.device_identity.device_id
        and mapping.device_id == request.device_profile.device_id
    )
    return _result(
        CLOCK_ALIGNED_METRIC_ID,
        status=MetricStatus.COMPUTED,
        value=passed,
        reason_code=None if passed else "DeviceIdentityMismatch",
        details={
            "mappingMethod": mapping.mapping_method,
            "offsetMilliseconds": mapping.offset_milliseconds,
            "driftBoundMilliseconds": mapping.drift_bound_milliseconds,
            "interpolationApplied": False,
        },
    )


def _evaluate_coordinate_context(request: MachineObservationRequest) -> MetricResult:
    alignment = request.coordinate_alignment
    if alignment is None:
        return _result(
            COORDINATE_CONTEXT_METRIC_ID,
            status=MetricStatus.INSUFFICIENT_CONTEXT,
            reason_code="CoordinateAlignmentMissing",
            details={"interpolationApplied": False},
        )
    if alignment.calibration_status != "calibrated" or alignment.calibration_id is None:
        return _result(
            COORDINATE_CONTEXT_METRIC_ID,
            status=MetricStatus.INSUFFICIENT_CONTEXT,
            reason_code="CalibrationUnverified",
            details={"calibrationStatus": alignment.calibration_status, "interpolationApplied": False},
        )
    profile_channel_ids = {channel.channel_id for channel in request.device_profile.channels}
    passed = (
        alignment.device_id == request.artifact.device_identity.device_id
        and set(alignment.channel_ids).issubset(profile_channel_ids)
    )
    return _result(
        COORDINATE_CONTEXT_METRIC_ID,
        status=MetricStatus.COMPUTED,
        value=passed,
        reason_code=None if passed else "UnknownCoordinateChannels",
        details={
            "machineCoordinateFrame": alignment.machine_coordinate_frame,
            "workCoordinateFrame": alignment.work_coordinate_frame,
            "sourceKind": alignment.source_kind,
            "effectiveAt": alignment.effective_at,
            "calibrationStatus": alignment.calibration_status,
            "interpolationApplied": False,
        },
    )


def _current_numeric_environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "pydantic": package_version("pydantic"),
    }


def evaluate_machine_observation(request: MachineObservationRequest) -> EvaluationReport:
    request_hash = _content_hash(request)
    context_hashes = {
        "deviceProfile": _content_hash(request.device_profile),
        "lineage": _content_hash(request.lineage),
    }
    if request.clock_mapping is not None:
        context_hashes["clockMapping"] = _content_hash(request.clock_mapping)
    if request.coordinate_alignment is not None:
        context_hashes["coordinateAlignment"] = _content_hash(request.coordinate_alignment)
    provenance = Provenance(
        requestHash=request_hash,
        artifactHash=_content_hash(request.artifact),
        caseHash=_content_hash(request.case),
        runnerId=MACHINE_TRACE_IMPORT_RUNNER_ID,
        evaluatorVersion=MACHINE_OBSERVATION_EVALUATOR_ID,
        executionOutcomePolicy=request.case.execution_outcome_policy,
        numericEnvironment=_current_numeric_environment(),
        contextHashes=context_hashes,
    )

    evaluated = {
        RAW_INTEGRITY_METRIC_ID: _evaluate_raw_integrity(request),
        READ_ONLY_CAPTURE_METRIC_ID: _evaluate_read_only_capture(request),
        LINEAGE_COMPLETE_METRIC_ID: _evaluate_lineage(request),
        CLOCK_ALIGNED_METRIC_ID: _evaluate_clock_alignment(request),
        COORDINATE_CONTEXT_METRIC_ID: _evaluate_coordinate_context(request),
    }
    requested = request.case.required_metrics + request.case.optional_metrics
    results = [
        _bind_boolean_gate(_apply_threshold(evaluated[metric.metric_id], metric.threshold))
        for metric in requested
    ]
    required_count = len(request.case.required_metrics)
    case_outcome = _aggregate_outcome(results[:required_count])
    capabilities = [
        CapabilityResolution(capabilityId=CAP_RAW_CAPTURE, source="Artifact"),
        CapabilityResolution(capabilityId=CAP_READ_ONLY_CAPTURE, source="Artifact"),
        CapabilityResolution(capabilityId=CAP_LINEAGE, source="Artifact"),
    ]
    if request.clock_mapping is not None:
        capabilities.append(CapabilityResolution(capabilityId=CAP_CLOCK_MAPPING, source="Profile"))
    if request.coordinate_alignment is not None:
        capabilities.append(CapabilityResolution(capabilityId=CAP_COORDINATE_CONTEXT, source="Profile"))
    return _seal_evaluation_report(
        EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=case_outcome,
            metricResults=results,
            capabilities=capabilities,
            contentHash="",
            evaluatorVersion=MACHINE_OBSERVATION_EVALUATOR_ID,
            provenance=provenance,
        )
    )


register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=MACHINE_OBSERVATION_DOMAIN_PACK_ID,
        parse_request=_parse_request,
        evaluate=evaluate_machine_observation,
    )
)


__all__ = [
    "CLOCK_ALIGNED_CLAIM_ID",
    "CLOCK_ALIGNED_METRIC_ID",
    "COORDINATE_CONTEXT_CLAIM_ID",
    "COORDINATE_CONTEXT_METRIC_ID",
    "LINEAGE_COMPLETE_CLAIM_ID",
    "LINEAGE_COMPLETE_METRIC_ID",
    "MACHINE_OBSERVATION_DOMAIN_PACK",
    "MACHINE_OBSERVATION_DOMAIN_PACK_ID",
    "MACHINE_OBSERVATION_EVALUATOR_ID",
    "MACHINE_TRACE_IMPORT_RUNNER_ID",
    "RAW_INTEGRITY_CLAIM_ID",
    "RAW_INTEGRITY_METRIC_ID",
    "READ_ONLY_CAPTURE_CLAIM_ID",
    "READ_ONLY_CAPTURE_METRIC_ID",
    "evaluate_machine_observation",
    "load_machine_telemetry_capture",
    "machine_trace_content_hash",
]
