from __future__ import annotations

from copy import deepcopy

from axiom import compare_runs, run_experiment
from axiom.domain import EXPERIMENT_COMPARISON_POLICY_ID, PYTHON_CALL_RUNNER_ID
from axiom.models import CaseOutcome, ExecutionStatus, ExperimentSpec, OrderedPointSequence, ParameterSet, SubjectDefinition
from axiom.subjects import register_subject


def _experiment_spec() -> dict:
    points = [[0.0, 0.0], [10.0, 0.0], [20.0, 0.0], [30.0, 0.0]]
    semantics = {"unit": "mm", "coordinateFrame": "G54-workpiece", "closed": False}
    reference = {
        "artifactType": "ordered-point-sequence",
        "schemaVersion": 1,
        "points": points,
        "semantics": semantics,
    }
    return {
        "experimentId": "cnc-contour-true-ab@1",
        "sharedInput": reference,
        "parameterSet": {
            "parameterSetId": "finish-pass-offset@1",
            "parameterSchemaId": "ordered-point.offset-error-parameters@1",
            "schemaVersion": 1,
            "values": {
                "errorVector": [0.0, 0.08],
                "compensationGain": 0.75,
            },
            "units": {"errorVector": "mm", "compensationGain": "ratio"},
        },
        "arms": [
            {
                "armId": "baseline",
                "subjectId": "ordered-point.offset-baseline",
                "subjectVersion": "1",
            },
            {
                "armId": "candidate",
                "subjectId": "ordered-point.offset-compensated",
                "subjectVersion": "1",
            },
        ],
        "evaluation": {
            "case": {
                "caseId": "cnc-contour-true-ab-evaluation@1",
                "requiredMetrics": [
                    "paired.euclidean.rms",
                    {
                        "metricId": "paired.euclidean.max",
                        "threshold": {"operator": "<=", "value": 0.03, "unit": "mm"},
                    },
                ],
                "scoreProfile": {
                    "profileId": "cnc-contour-score@1",
                    "applicableContext": "true Case D contour experiment",
                    "rules": [
                        {
                            "metricId": "paired.euclidean.max",
                            "direction": "lower-is-better",
                            "best": 0.0,
                            "worst": 0.1,
                            "weight": 1.0,
                            "unit": "mm",
                        }
                    ],
                    "missingValuePolicy": "reject",
                },
            },
            "referenceBinding": {
                "reference": reference,
                "alignment": "ordered-point.alignment.identity@1",
                "strategyId": "ordered-point.correspondence.index-paired@1",
                "distanceId": "ordered-point.distance.euclidean@1",
                "tolerance": {
                    "policyId": "ordered-point.tolerance.absolute@1",
                    "value": 0.001,
                    "unit": "mm",
                },
                "boundaryPolicy": "ordered-point.boundary.finite-sequence@1",
            },
        },
    }


def test_experiment_executes_two_subjects_from_one_frozen_input_and_parameter_set():
    report = run_experiment(_experiment_spec())

    assert report.execution_status is ExecutionStatus.SUCCEEDED
    assert report.case_outcome is CaseOutcome.FAILED
    assert report.comparison is not None
    assert report.comparison.policy_id == EXPERIMENT_COMPARISON_POLICY_ID
    assert report.comparison.compatibility.compatible is True
    assert len(report.arm_results) == 2

    baseline, candidate = report.arm_results
    assert baseline.run_bundle is not None
    assert candidate.run_bundle is not None
    assert baseline.run_bundle.run.runner_id == PYTHON_CALL_RUNNER_ID
    assert baseline.run_bundle.observation.source == "ExecutedSubject"
    assert baseline.run_bundle.run_spec.input_artifact_hash == report.shared_input_hash
    assert candidate.run_bundle.run_spec.input_artifact_hash == report.shared_input_hash
    assert baseline.run_bundle.run_spec.parameter_set_hash == report.parameter_set_hash
    assert candidate.run_bundle.run_spec.parameter_set_hash == report.parameter_set_hash
    assert baseline.run_bundle.report.case_outcome is CaseOutcome.FAILED
    assert candidate.run_bundle.report.case_outcome is CaseOutcome.PASSED

    maximum = next(
        item for item in report.comparison.metric_comparisons if item.metric_id == "paired.euclidean.max"
    )
    assert maximum.left_value == 0.08
    assert maximum.right_value == 0.02
    assert maximum.preferred_subject_id == "ordered-point.offset-compensated"


def test_experiment_replay_is_deterministic_and_parameter_order_independent():
    first_payload = _experiment_spec()
    second_payload = deepcopy(first_payload)
    second_payload["parameterSet"]["values"] = {
        "compensationGain": 0.75,
        "errorVector": [0.0, 0.08],
    }

    first = run_experiment(first_payload)
    second = run_experiment(second_payload)

    assert first.experiment_spec_hash == second.experiment_spec_hash
    assert first.parameter_set_hash == second.parameter_set_hash
    assert first.model_dump(mode="json", by_alias=True) == second.model_dump(mode="json", by_alias=True)


def test_unknown_subject_is_an_explicit_experiment_failure_without_comparison():
    payload = _experiment_spec()
    payload["arms"][1]["subjectId"] = "vendor.missing-subject"

    report = run_experiment(payload)

    assert report.execution_status is ExecutionStatus.EXECUTION_FAILED
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert report.comparison is None
    assert report.arm_results[1].execution_status is ExecutionStatus.EXECUTION_FAILED
    assert report.arm_results[1].failure.code == "UnknownSubject"


def test_subject_parameter_contract_failure_does_not_fabricate_an_observation():
    payload = _experiment_spec()
    payload["parameterSet"]["values"]["errorVector"] = [0.08]

    report = run_experiment(payload)

    assert report.execution_status is ExecutionStatus.EXECUTION_FAILED
    assert report.comparison is None
    assert all(result.run_bundle is None for result in report.arm_results)
    assert all(result.failure.code == "ParameterContractViolation" for result in report.arm_results)


def test_parameter_schema_mismatch_is_rejected_before_subject_execution():
    payload = _experiment_spec()
    payload["parameterSet"]["parameterSchemaId"] = "vendor.incompatible-parameters@1"

    report = run_experiment(payload)

    assert report.execution_status is ExecutionStatus.EXECUTION_FAILED
    assert report.comparison is None
    assert all(result.failure.code == "ParameterSchemaMismatch" for result in report.arm_results)


def test_one_subject_failure_preserves_only_the_successful_arm_observation():
    subject_id = "test.crashing-subject"

    def crash(_: OrderedPointSequence, __: ParameterSet) -> OrderedPointSequence:
        raise RuntimeError("private implementation detail")

    register_subject(
        SubjectDefinition(
            subject_id=subject_id,
            subject_version="1",
            display_name="Crashing test subject",
            description="Exercises the public Subject failure boundary.",
            parameter_schema_id="ordered-point.offset-error-parameters@1",
        ),
        crash,
    )
    payload = _experiment_spec()
    payload["arms"][1]["subjectId"] = subject_id

    report = run_experiment(payload)

    assert report.execution_status is ExecutionStatus.EXECUTION_FAILED
    assert report.case_outcome is CaseOutcome.INCONCLUSIVE
    assert report.comparison is None
    assert report.arm_results[0].run_bundle is not None
    assert report.arm_results[0].run_bundle.observation is not None
    assert report.arm_results[1].run_bundle is None
    assert report.arm_results[1].failure.code == "SubjectExecutionFailed"


def test_invalid_subject_output_is_a_contract_failure_without_an_observation():
    subject_id = "test.invalid-output-subject"

    def invalid_output(_: OrderedPointSequence, __: ParameterSet) -> OrderedPointSequence:
        return "not-an-artifact"  # type: ignore[return-value]

    register_subject(
        SubjectDefinition(
            subject_id=subject_id,
            subject_version="1",
            display_name="Invalid output test subject",
            description="Exercises the public output contract boundary.",
            parameter_schema_id="ordered-point.offset-error-parameters@1",
        ),
        invalid_output,
    )
    payload = _experiment_spec()
    payload["arms"][1]["subjectId"] = subject_id

    report = run_experiment(payload)

    assert report.execution_status is ExecutionStatus.EXECUTION_FAILED
    assert report.comparison is None
    assert report.arm_results[1].run_bundle is None
    assert report.arm_results[1].failure.code == "OutputContractViolation"


def test_experiment_comparison_rejects_different_upstream_input_identity():
    report = run_experiment(_experiment_spec())
    left = report.arm_results[0].run_bundle
    right = report.arm_results[1].run_bundle
    assert left is not None and right is not None and right.run_spec is not None

    changed_spec = right.run_spec.model_copy(update={"input_artifact_hash": "different"})
    changed_right = right.model_copy(update={"run_spec": changed_spec})
    comparison = compare_runs(
        left,
        changed_right,
        policy_id=EXPERIMENT_COMPARISON_POLICY_ID,
        experiment_spec=report.experiment_spec,
    )

    assert comparison.compatibility.compatible is False
    assert comparison.metric_comparisons == []
    assert any(issue.code == "InputArtifactMismatch" for issue in comparison.compatibility.issues)


def test_experiment_comparison_rejects_a_tampered_bundle_identity():
    report = run_experiment(_experiment_spec())
    left = report.arm_results[0].run_bundle
    right = report.arm_results[1].run_bundle
    assert left is not None and right is not None

    changed_right = right.model_copy(update={"bundle_hash": "tampered"})
    comparison = compare_runs(
        left,
        changed_right,
        policy_id=EXPERIMENT_COMPARISON_POLICY_ID,
        experiment_spec=report.experiment_spec,
    )

    assert comparison.compatibility.compatible is False
    assert comparison.metric_comparisons == []
    assert any(
        issue.code == "BundleHashMismatch" and issue.path == "right.bundleHash"
        for issue in comparison.compatibility.issues
    )


def test_experiment_comparison_requires_and_binds_the_frozen_spec():
    report = run_experiment(_experiment_spec())
    left = report.arm_results[0].run_bundle
    right = report.arm_results[1].run_bundle
    assert left is not None and right is not None

    missing = compare_runs(left, right, policy_id=EXPERIMENT_COMPARISON_POLICY_ID)
    assert missing.compatibility.compatible is False
    assert any(issue.code == "ExperimentSpecRequired" for issue in missing.compatibility.issues)

    swapped = report.experiment_spec.model_copy(
        update={"arms": list(reversed(report.experiment_spec.arms))}
    )
    mismatched = compare_runs(
        left,
        right,
        policy_id=EXPERIMENT_COMPARISON_POLICY_ID,
        experiment_spec=swapped,
    )
    assert mismatched.compatibility.compatible is False
    assert any(
        issue.code == "ExperimentArmSubjectMismatch"
        for issue in mismatched.compatibility.issues
    )


def test_experiment_comparison_rejects_tampered_provenance_lineage():
    report = run_experiment(_experiment_spec())
    left = report.arm_results[0].run_bundle
    right = report.arm_results[1].run_bundle
    assert left is not None and right is not None and right.report.provenance is not None

    provenance = right.report.provenance.model_copy(update={"input_artifact_hash": "different"})
    changed_report = right.report.model_copy(update={"provenance": provenance})
    changed_right = right.model_copy(update={"report": changed_report})
    comparison = compare_runs(
        left,
        changed_right,
        policy_id=EXPERIMENT_COMPARISON_POLICY_ID,
        experiment_spec=report.experiment_spec,
    )

    assert comparison.compatibility.compatible is False
    assert any(
        issue.code == "ExperimentProvenanceInputMismatch"
        and issue.path == "right.report.provenance.inputArtifactHash"
        for issue in comparison.compatibility.issues
    )


def test_experiment_spec_requires_exactly_two_distinct_arms():
    payload = _experiment_spec()
    payload["arms"] = payload["arms"][:1]

    try:
        ExperimentSpec.model_validate(payload)
    except ValueError as exc:
        assert "arms" in str(exc)
    else:
        raise AssertionError("one-arm ExperimentSpec must be rejected")
