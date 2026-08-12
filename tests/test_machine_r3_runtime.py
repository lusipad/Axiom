from __future__ import annotations

from axiom import evaluate_run
from axiom.machine.runtime import (
    CLOCK_ALIGNED_METRIC_ID,
    COORDINATE_CONTEXT_METRIC_ID,
    LINEAGE_COMPLETE_METRIC_ID,
    RAW_INTEGRITY_METRIC_ID,
    READ_ONLY_CAPTURE_METRIC_ID,
)
from axiom.machine.scenarios import machine_r3_example_run_spec
from axiom.models import CaseOutcome, ExecutionStatus, MetricStatus
from axiom.run import validate_run_bundle_integrity


def _metric(bundle, metric_id: str):
    return next(result for result in bundle.report.metric_results if result.metric_id == metric_id)


def test_paired_read_only_trace_passes_and_only_emits_observed_claims() -> None:
    bundle = evaluate_run(machine_r3_example_run_spec("read-only-paired-pass"))
    assert validate_run_bundle_integrity(bundle) == []
    assert bundle.run.execution_status is ExecutionStatus.SUCCEEDED
    assert bundle.run.case_outcome is CaseOutcome.PASSED
    assert bundle.observation is not None
    assert bundle.observation.source == "ImportedArtifact"
    assert bundle.report.provenance is not None
    assert set(bundle.report.provenance.context_hashes or {}) == {
        "deviceProfile",
        "clockMapping",
        "coordinateAlignment",
        "lineage",
    }
    assert all(len(value) == 64 for value in (bundle.report.provenance.context_hashes or {}).values())
    assert _metric(bundle, RAW_INTEGRITY_METRIC_ID).value is True
    assert _metric(bundle, READ_ONLY_CAPTURE_METRIC_ID).value is True
    assert _metric(bundle, LINEAGE_COMPLETE_METRIC_ID).value is True
    assert _metric(bundle, CLOCK_ALIGNED_METRIC_ID).value is True
    assert _metric(bundle, COORDINATE_CONTEXT_METRIC_ID).value is True
    assert bundle.observation.artifact.model_dump(mode="json", by_alias=True, exclude_none=True)["vendorMetadata"][
        "programName"
    ] == "DEMO_5X_R3"
    assert bundle.claims
    assert all(claim.evidence is not None and claim.evidence.level == "Observed" for claim in bundle.claims)
    claim_ids = {claim.claim_definition_id for claim in bundle.claims}
    assert not {
        "five-axis.device-safe-claim@1",
        "five-axis.process-safe-claim@1",
    }.intersection(claim_ids)


def test_unpaired_trace_keeps_raw_claims_but_lineage_is_insufficient_context() -> None:
    bundle = evaluate_run(machine_r3_example_run_spec("read-only-unpaired-pass"))
    assert bundle.run.case_outcome is CaseOutcome.PASSED
    lineage = _metric(bundle, LINEAGE_COMPLETE_METRIC_ID)
    assert lineage.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert lineage.reason_code == "UnpairedLineage"
    assert _metric(bundle, RAW_INTEGRITY_METRIC_ID).value is True
    assert _metric(bundle, READ_ONLY_CAPTURE_METRIC_ID).value is True


def test_missing_clock_alignment_is_inconclusive_and_does_not_interpolate() -> None:
    bundle = evaluate_run(machine_r3_example_run_spec("missing-clock-alignment"))
    assert bundle.run.case_outcome is CaseOutcome.INCONCLUSIVE
    metric = _metric(bundle, CLOCK_ALIGNED_METRIC_ID)
    assert metric.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert metric.reason_code == "ClockMappingMissing"
    assert metric.details["interpolationApplied"] is False


def test_out_of_order_gap_refutes_raw_integrity() -> None:
    bundle = evaluate_run(machine_r3_example_run_spec("out-of-order-gap"))
    assert bundle.run.case_outcome is CaseOutcome.FAILED
    metric = _metric(bundle, RAW_INTEGRITY_METRIC_ID)
    assert metric.status is MetricStatus.COMPUTED
    assert metric.value is False
    assert metric.reason_code == "FrameSequenceDiscontinuous"
    assert metric.details["interpolationApplied"] is False


def test_forbidden_write_operation_is_rejected_as_invalid_observation() -> None:
    bundle = evaluate_run(machine_r3_example_run_spec("forbidden-write-operation"))
    assert bundle.run.execution_status is ExecutionStatus.SKIPPED
    assert bundle.run.case_outcome is CaseOutcome.INVALID
    assert bundle.report.domain_failures[0].code == "MalformedEvaluationRequest"


def test_missing_sample_unit_is_invalid() -> None:
    run_spec = machine_r3_example_run_spec("read-only-paired-pass")
    run_spec["request"]["artifact"]["frames"][0]["samples"][0].pop("unit")
    bundle = evaluate_run(run_spec)
    assert bundle.run.case_outcome is CaseOutcome.INVALID
    assert bundle.report.domain_failures[0].code == "MalformedEvaluationRequest"


def test_device_identity_profile_mismatch_is_invalid() -> None:
    run_spec = machine_r3_example_run_spec("read-only-paired-pass")
    run_spec["request"]["deviceProfile"]["deviceId"] = "other-device"
    bundle = evaluate_run(run_spec)
    assert bundle.run.case_outcome is CaseOutcome.INVALID
    assert bundle.report.domain_failures[0].code == "MalformedEvaluationRequest"


def test_sample_unit_profile_mismatch_is_invalid() -> None:
    run_spec = machine_r3_example_run_spec("read-only-paired-pass")
    run_spec["request"]["artifact"]["frames"][0]["samples"][0]["unit"] = "inch"
    bundle = evaluate_run(run_spec)
    assert bundle.run.case_outcome is CaseOutcome.INVALID
    assert bundle.report.domain_failures[0].code == "MalformedEvaluationRequest"


def test_coordinate_alignment_profile_mismatch_is_invalid() -> None:
    run_spec = machine_r3_example_run_spec("read-only-paired-pass")
    run_spec["request"]["coordinateAlignment"]["channelIds"] = ["pos.unknown"]
    bundle = evaluate_run(run_spec)
    assert bundle.run.case_outcome is CaseOutcome.INVALID
    assert bundle.report.domain_failures[0].code == "MalformedEvaluationRequest"


def test_trace_hash_is_recomputed_after_raw_vendor_metadata_tampering() -> None:
    run_spec = machine_r3_example_run_spec("read-only-paired-pass")
    run_spec["request"]["artifact"]["vendorMetadata"]["programName"] = "TAMPERED"
    bundle = evaluate_run(run_spec)
    metric = _metric(bundle, RAW_INTEGRITY_METRIC_ID)
    assert bundle.run.case_outcome is CaseOutcome.FAILED
    assert metric.value is False
    assert metric.reason_code == "TraceContentHashMismatch"


def test_estimated_coordinate_alignment_cannot_support_calibrated_context() -> None:
    run_spec = machine_r3_example_run_spec("read-only-paired-pass")
    alignment = run_spec["request"]["coordinateAlignment"]
    alignment["calibrationStatus"] = "estimated"
    alignment.pop("calibrationId")
    bundle = evaluate_run(run_spec)
    metric = _metric(bundle, COORDINATE_CONTEXT_METRIC_ID)
    assert bundle.run.case_outcome is CaseOutcome.INCONCLUSIVE
    assert metric.status is MetricStatus.INSUFFICIENT_CONTEXT
    assert metric.reason_code == "CalibrationUnverified"
