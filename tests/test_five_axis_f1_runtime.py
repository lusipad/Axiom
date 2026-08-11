from __future__ import annotations

from axiom.five_axis.f1_parser import parse_axiom_cl_subset
from axiom.five_axis.f1_pipeline import build_m1_reference_path
from axiom.five_axis.f1_runtime import (
    F1_EVALUATOR_ID,
    F1_RUNNER_ID,
    FIVE_AXIS_F1_DOMAIN_PACK,
    FIVE_AXIS_F1_DOMAIN_PACK_ID,
    M0_VALID_METRIC_ID,
    M1_VALID_METRIC_ID,
)
from axiom.models import ClaimStatus, MetricStatus
from axiom.run import evaluate_run


_SOURCE = (
    "UNITS/MM\n"
    "FROM/0,0,20,0,0,1\n"
    "FEDRAT/1200\n"
    "GOTO/20,0,20\n"
    "GOTO/20,20,20\n"
    "END\n"
)


def _run_spec(artifact, metric_id: str) -> dict:
    return {
        "subjectId": "five-axis.f1.fixture@1",
        "domainPackId": FIVE_AXIS_F1_DOMAIN_PACK_ID,
        "runnerId": F1_RUNNER_ID,
        "evaluatorVersion": F1_EVALUATOR_ID,
        "request": {
            "artifact": artifact.model_dump(mode="json", by_alias=True, exclude_none=True),
            "case": {
                "caseId": "five-axis.f1.contract-test@1",
                "requiredMetrics": [metric_id],
            },
        },
    }


def test_f1_domain_pack_declares_m0_m1_m2_without_changing_single_artifact_runs():
    descriptors = FIVE_AXIS_F1_DOMAIN_PACK.artifact_type_descriptors

    assert [(item.artifact_type, item.schema_version, item.role) for item in descriptors] == [
        ("five-axis.normalized-program", 1, "run-input"),
        ("five-axis.m1-reference-path", 1, "run-input"),
        ("five-axis.m2-candidate-task-geometry", 1, "run-input"),
    ]
    assert FIVE_AXIS_F1_DOMAIN_PACK.artifact_type == "five-axis.m2-candidate-task-geometry"


def test_m0_normalized_program_runs_through_generic_core_binding():
    program = parse_axiom_cl_subset(_SOURCE)

    bundle = evaluate_run(_run_spec(program, M0_VALID_METRIC_ID))

    result = bundle.metric_result(M0_VALID_METRIC_ID)
    assert bundle.run.domain_pack_id == FIVE_AXIS_F1_DOMAIN_PACK_ID
    assert bundle.report.case_outcome.value == "Passed"
    assert result.status is MetricStatus.COMPUTED
    assert result.value is True
    assert all(claim.claim_definition_id != "five-axis.geometry-valid-claim@1" for claim in bundle.claims)


def test_m1_reference_path_runs_and_preserves_certified_regularities():
    reference = build_m1_reference_path(parse_axiom_cl_subset(_SOURCE))

    bundle = evaluate_run(_run_spec(reference, M1_VALID_METRIC_ID))

    result = bundle.metric_result(M1_VALID_METRIC_ID)
    assert bundle.report.case_outcome.value == "Passed"
    assert result.status is MetricStatus.COMPUTED
    assert result.evidence is not None and result.evidence.level == "Certified"
    assert bundle.claims[0].status is ClaimStatus.SUPPORTED


def test_metric_requested_for_the_wrong_f1_artifact_is_not_silently_computed():
    program = parse_axiom_cl_subset(_SOURCE)

    bundle = evaluate_run(_run_spec(program, M1_VALID_METRIC_ID))

    result = bundle.metric_result(M1_VALID_METRIC_ID)
    assert result.status is MetricStatus.NOT_APPLICABLE
    assert result.reason_code == "MetricOutsideArtifactDomain"
    assert bundle.report.case_outcome.value == "Invalid"
