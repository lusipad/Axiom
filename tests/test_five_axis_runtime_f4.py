from __future__ import annotations

import pytest
from pydantic import ValidationError

from axiom.five_axis.f1_scenarios import load_f1_scenario
from axiom.five_axis.f2_scenarios import load_f2_scenario
from axiom.five_axis.f3_runtime import (
    CONTINUOUSLY_FEASIBLE_CLAIM_ID,
    CONTINUOUSLY_FEASIBLE_METRIC_ID,
    INTERVAL_CERTIFIED_CLAIM_ID,
    INTERVAL_CERTIFIED_METRIC_ID,
)
from axiom.five_axis.f3_sampling import POLYNOMIAL_POLICY_ID
from axiom.five_axis.f3_scenarios import load_f3_scenario
from axiom.five_axis.f4_adapters import (
    REFERENCE_ADAPTER_DESCRIPTOR,
    SUT_ADAPTER_DESCRIPTOR,
    build_adapter_invocation,
    execute_adapter,
)
from axiom.five_axis.f4_runtime import (
    ADAPTER_CONTRACT_VALID_METRIC_ID,
    F4_EVALUATOR_ID,
    F4_RUNNER_ID,
    FIVE_AXIS_F4_DOMAIN_PACK,
    FIVE_AXIS_F4_DOMAIN_PACK_ID,
    REFERENCE_SUT_CROSS_VALIDATED_METRIC_ID,
    FiveAxisF4EvaluationBindingRequest,
    evaluate_five_axis_f4,
)
from axiom.run import evaluate_run


def _request_payload() -> dict:
    scenario = load_f3_scenario("canonical-table-table-jerk")
    m4 = scenario.continuousTrajectory
    outputs = []
    for descriptor in (REFERENCE_ADAPTER_DESCRIPTOR, SUT_ADAPTER_DESCRIPTOR):
        invocation = build_adapter_invocation(
            descriptor,
            m4,
            sample_period=0.08,
            policy=POLYNOMIAL_POLICY_ID,
            final_hold=False,
        )
        receipt, command = execute_adapter(invocation, m4)
        assert receipt.status == "Succeeded"
        assert command is not None
        outputs.append((invocation, receipt, command))
    reference, sut = outputs
    f1 = load_f1_scenario("nominal-certified")
    f2 = load_f2_scenario("canonical-table-table")
    return {
        "artifact": sut[2].model_dump(mode="json", by_alias=True, exclude_none=True),
        "referenceArtifact": reference[2].model_dump(mode="json", by_alias=True, exclude_none=True),
        "referenceInvocation": reference[0].model_dump(mode="json", by_alias=True, exclude_none=True),
        "sutInvocation": sut[0].model_dump(mode="json", by_alias=True, exclude_none=True),
        "referenceReceipt": reference[1].model_dump(mode="json", by_alias=True, exclude_none=True),
        "sutReceipt": sut[1].model_dump(mode="json", by_alias=True, exclude_none=True),
        "referencePath": f2.referencePath.model_dump(mode="json", by_alias=True, exclude_none=True),
        "stockStateGeometries": f1.stockStateGeometries,
        "collisionModel": f2.collisionModel.model_dump(mode="json", by_alias=True, exclude_none=True),
        "case": {
            "caseId": "five-axis.f4.runtime-smoke@1",
            "requiredMetrics": [
                ADAPTER_CONTRACT_VALID_METRIC_ID,
                REFERENCE_SUT_CROSS_VALIDATED_METRIC_ID,
                CONTINUOUSLY_FEASIBLE_METRIC_ID,
                INTERVAL_CERTIFIED_METRIC_ID,
            ],
        },
    }


def test_f4_domain_pack_binds_solver_runner_and_m5_input() -> None:
    assert FIVE_AXIS_F4_DOMAIN_PACK.domain_pack_id == FIVE_AXIS_F4_DOMAIN_PACK_ID
    assert FIVE_AXIS_F4_DOMAIN_PACK.runner_id == F4_RUNNER_ID
    assert FIVE_AXIS_F4_DOMAIN_PACK.evaluator_version == F4_EVALUATOR_ID
    assert FIVE_AXIS_F4_DOMAIN_PACK.artifact_type == "five-axis.m5-discrete-command"
    assert len(FIVE_AXIS_F4_DOMAIN_PACK.claim_definition_ids) == 8


def test_f4_runtime_cross_validates_distinct_reference_and_sut_commands() -> None:
    request = FiveAxisF4EvaluationBindingRequest.model_validate(_request_payload())
    report = evaluate_five_axis_f4(request)

    assert report.case_outcome.value == "Passed"
    assert all(result.status.value == "Computed" and result.value is True for result in report.metric_results)
    assert report.provenance is not None
    assert report.provenance.runner_id == F4_RUNNER_ID
    assert report.provenance.numeric_environment["system"] == "Windows"


def test_f4_request_rejects_one_subject_masquerading_as_both_solvers() -> None:
    payload = _request_payload()
    payload["sutInvocation"]["descriptor"]["subjectId"] = payload["referenceInvocation"]["descriptor"][
        "subjectId"
    ]
    payload["sutReceipt"]["invocation"] = payload["sutInvocation"]
    payload["sutReceipt"]["descriptor"] = payload["sutInvocation"]["descriptor"]

    with pytest.raises(ValidationError, match="reference and SUT subjects must be distinct"):
        FiveAxisF4EvaluationBindingRequest.model_validate(payload)


def test_f4_run_bundle_projects_m4_and_m5_claims_from_executed_subject() -> None:
    request = _request_payload()
    bundle = evaluate_run(
        {
            "subjectId": "five-axis.f4.runtime-smoke@1",
            "domainPackId": FIVE_AXIS_F4_DOMAIN_PACK_ID,
            "runnerId": F4_RUNNER_ID,
            "evaluatorVersion": F4_EVALUATOR_ID,
            "request": request,
        }
    )

    claims = {claim.claim_definition_id: claim.status.value for claim in bundle.claims}
    assert bundle.run.execution_status.value == "Succeeded"
    assert bundle.observation is not None
    assert bundle.observation.source == "ExecutedSubject"
    assert claims[CONTINUOUSLY_FEASIBLE_CLAIM_ID] == "Supported"
    assert claims[INTERVAL_CERTIFIED_CLAIM_ID] == "Supported"
