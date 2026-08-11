from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field

from axiom import ORDERED_POINT_DOMAIN_PACK, evaluate_run, register_domain_pack
from axiom import run as run_module
from axiom.domain import ARTIFACT_IMPORT_RUNNER_ID, DomainPack, MetricDefinition
from axiom.models import (
    CapabilityResolution,
    CaseOutcome,
    EvaluationCase,
    EvaluationReport,
    ExecutionStatus,
    MetricResult,
    MetricStatus,
    Provenance,
)
from axiom.runtime import DomainRuntimeBinding, register_domain_runtime_binding


def _content_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ordered_point_request() -> dict[str, Any]:
    return {
        "artifact": {
            "artifactType": "ordered-point-sequence",
            "schemaVersion": 1,
            "points": [[0, 0], [3, 4]],
        },
        "case": {
            "caseId": "ordered-point-runtime-regression@1",
            "requiredMetrics": ["path.length.open"],
        },
    }


def _scalar_pack_id(name: str) -> str:
    return f"vendor.scalar-{name}@1"


def _scalar_domain_pack(pack_id: str, evaluator_version: str = "vendor.scalar-evaluator@7") -> DomainPack:
    return DomainPack(
        domainPackId=pack_id,
        artifactType="scalar-sample",
        artifactSchemaVersions=[1],
        evaluatorVersion=evaluator_version,
        runnerId=ARTIFACT_IMPORT_RUNNER_ID,
        runnerIds=[ARTIFACT_IMPORT_RUNNER_ID],
        capabilityIds=["vendor.scalar.parsed@1"],
        metricDefinitions=[
            MetricDefinition(
                metricId="value.count",
                metricDefinitionId="vendor.scalar.value.count@1",
            )
        ],
        claimDefinitionIds=["axiom.core.case-outcome-claim@1"],
        comparisonPolicyIds=[],
    )


def _scalar_request(values: Any, *, reference_binding: dict[str, Any] | None = None) -> dict[str, Any]:
    request: dict[str, Any] = {
        "artifact": {
            "artifactType": "scalar-sample",
            "schemaVersion": 1,
            "values": values,
            "vendorMetadata": {"calibration": "v1"},
        },
        "case": {
            "caseId": "scalar-count@1",
            "requiredMetrics": ["value.count"],
        },
        "requestEnvelope": {"preserve": True},
    }
    if reference_binding is not None:
        request["referenceBinding"] = reference_binding
    return {
        "subjectId": "scalar-subject",
        "domainPackId": "unused-placeholder",
        "request": request,
    }


def _scalar_binding(pack_id: str, evaluator_version: str = "vendor.scalar-evaluator@7") -> DomainRuntimeBinding:
    class ScalarArtifact(BaseModel):
        model_config = ConfigDict(populate_by_name=True, extra="allow")

        artifact_type: Literal["scalar-sample"] = Field(alias="artifactType")
        schema_version: Literal[1] = Field(alias="schemaVersion")
        values: list[float]

    class ScalarRequest(BaseModel):
        model_config = ConfigDict(populate_by_name=True, extra="allow")

        artifact: ScalarArtifact
        case: EvaluationCase

    def parse_request(request: Any) -> ScalarRequest:
        payload = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
        return ScalarRequest.model_validate(payload)

    def evaluate_scalar(request: ScalarRequest) -> EvaluationReport:
        artifact_payload = request.artifact.model_dump(mode="json", by_alias=True, exclude_unset=True)
        case_payload = request.case.model_dump(mode="json", by_alias=True, exclude_unset=True)
        request_payload = {
            "artifact": artifact_payload,
            "case": case_payload,
        }
        return EvaluationReport(
            executionStatus=ExecutionStatus.SUCCEEDED,
            caseOutcome=CaseOutcome.PASSED,
            metricResults=[
                MetricResult(
                    metricId="value.count",
                    metricDefinitionId="vendor.scalar.value.count@1",
                    status=MetricStatus.COMPUTED,
                    value=len(request.artifact.values),
                )
            ],
            capabilities=[
                CapabilityResolution(
                    capabilityId="vendor.scalar.parsed@1",
                    source="Adapter",
                )
            ],
            contentHash=_content_hash({"report": request_payload, "evaluatorVersion": evaluator_version}),
            evaluatorVersion=evaluator_version,
            provenance=Provenance(
                requestHash=_content_hash(request_payload),
                artifactHash=_content_hash(artifact_payload),
                caseHash=_content_hash(case_payload),
                runnerId=ARTIFACT_IMPORT_RUNNER_ID,
                evaluatorVersion=evaluator_version,
                executionOutcomePolicy=request.case.execution_outcome_policy,
                numericEnvironment={"python": "3.12-test"},
            ),
        )

    return DomainRuntimeBinding(
        domain_pack_id=pack_id,
        parse_request=parse_request,
        evaluate=evaluate_scalar,
    )


def test_registered_runtime_binding_executes_a_second_domain_without_run_py_special_casing():
    pack_id = _scalar_pack_id("executes")
    pack = _scalar_domain_pack(pack_id)
    register_domain_pack(pack)
    register_domain_runtime_binding(_scalar_binding(pack_id, pack.evaluator_version))
    payload = _scalar_request([1.0, 2.0, 3.0])
    payload["domainPackId"] = pack_id

    bundle = evaluate_run(payload).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert bundle["run"]["domainPackId"] == pack_id
    assert bundle["run"]["executionStatus"] == "Succeeded"
    assert bundle["report"]["evaluatorVersion"] == pack.evaluator_version
    assert bundle["report"]["provenance"]["evaluatorVersion"] == pack.evaluator_version
    assert bundle["report"]["capabilities"] == [
        {"capabilityId": "vendor.scalar.parsed@1", "source": "Adapter"}
    ]
    assert bundle["report"]["metricResults"][0]["value"] == 3
    assert bundle["observation"]["artifact"] == {
        "artifactType": "scalar-sample",
        "schemaVersion": 1,
        "values": [1.0, 2.0, 3.0],
        "vendorMetadata": {"calibration": "v1"},
    }


def test_evaluate_run_rebinds_report_content_hash_after_provenance_binding():
    pack_id = _scalar_pack_id("content-hash")
    pack = _scalar_domain_pack(pack_id)
    register_domain_pack(pack)
    register_domain_runtime_binding(_scalar_binding(pack_id, pack.evaluator_version))
    payload = _scalar_request([1.0, 2.0, 3.0])
    payload["domainPackId"] = pack_id
    payload["subjectVersion"] = "subject-v2"
    payload["inputArtifactHash"] = "artifact-sha"
    payload["parameterSetHash"] = "params-sha"
    payload["experimentSpecHash"] = "experiment-sha"
    runtime_hash = _content_hash(
        {
            "report": {
                "artifact": payload["request"]["artifact"],
                "case": payload["request"]["case"],
            },
            "evaluatorVersion": pack.evaluator_version,
        }
    )

    bundle = evaluate_run(payload)

    assert bundle.report.provenance is not None
    assert bundle.report.provenance.subject_version == "subject-v2"
    assert bundle.report.provenance.input_artifact_hash == "artifact-sha"
    assert bundle.report.provenance.parameter_set_hash == "params-sha"
    assert bundle.report.provenance.experiment_spec_hash == "experiment-sha"
    assert bundle.report.content_hash == bundle.run.report_content_hash
    assert bundle.report.content_hash != runtime_hash
    assert {
        claim.report_content_hash for claim in bundle.claims if claim.report_content_hash is not None
    } == {bundle.report.content_hash}
    assert run_module.validate_run_bundle_integrity(bundle) == []


def test_validate_run_bundle_integrity_rejects_tampered_report_content_hash():
    pack_id = _scalar_pack_id("tampered-report")
    pack = _scalar_domain_pack(pack_id)
    register_domain_pack(pack)
    register_domain_runtime_binding(_scalar_binding(pack_id, pack.evaluator_version))
    payload = _scalar_request([1.0, 2.0])
    payload["domainPackId"] = pack_id

    bundle = evaluate_run(payload)
    tampered = bundle.model_copy(
        update={"report": bundle.report.model_copy(update={"content_hash": "tampered"})}
    )

    failures = run_module.validate_run_bundle_integrity(tampered)

    assert any(
        failure.code == "ReportContentHashMismatch" and failure.path == "report.contentHash"
        for failure in failures
    )


def test_malformed_run_spec_bundle_seals_report_content_hash():
    bundle = evaluate_run({"request": {"artifact": {"artifactType": "ordered-point-sequence"}}})

    assert bundle.report.content_hash == bundle.run.report_content_hash
    assert run_module.validate_run_bundle_integrity(bundle) == []


def test_validate_run_bundle_integrity_rejects_tampered_claim_report_hash_even_with_rehashed_bundle():
    pack_id = _scalar_pack_id("tampered-claim")
    pack = _scalar_domain_pack(pack_id)
    register_domain_pack(pack)
    register_domain_runtime_binding(_scalar_binding(pack_id, pack.evaluator_version))
    payload = _scalar_request([1.0, 2.0])
    payload["domainPackId"] = pack_id

    bundle = evaluate_run(payload)
    tampered_claim = bundle.claims[0].model_copy(update={"report_content_hash": "tampered-report-hash"})
    tampered_claim = tampered_claim.model_copy(
        update={"content_hash": run_module._claim_content_hash(tampered_claim)}
    )
    tampered_claims = [tampered_claim, *bundle.claims[1:]]
    tampered_bundle = bundle.model_copy(update={"claims": tampered_claims})
    tampered_bundle = tampered_bundle.model_copy(
        update={
            "bundle_hash": run_module._content_hash(
                run_module._bundle_identity_payload(
                    tampered_bundle.run_spec,
                    tampered_bundle.run,
                    tampered_bundle.observation,
                    tampered_bundle.report,
                    tampered_bundle.claims,
                )
            )
        }
    )

    failures = run_module.validate_run_bundle_integrity(tampered_bundle)

    assert any(
        failure.code == "ClaimReportHashMismatch"
        and failure.path == "claims[0].reportContentHash"
        for failure in failures
    )
    assert not any(failure.code == "BundleHashMismatch" for failure in failures)
    assert not any(failure.code == "ClaimHashMismatch" for failure in failures)


def test_descriptor_only_pack_returns_structured_evaluator_unavailable():
    pack_id = _scalar_pack_id("descriptor-only")
    register_domain_pack(_scalar_domain_pack(pack_id))
    payload = _scalar_request([1.0])
    payload["domainPackId"] = pack_id

    bundle = evaluate_run(payload).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert bundle["run"]["executionStatus"] == "Skipped"
    assert bundle["report"]["caseOutcome"] == "Unsupported"
    assert bundle["report"]["domainFailures"] == [
        {
            "code": "DomainPackEvaluatorUnavailable",
            "message": "The registered DomainPack has no executable runtime binding.",
            "path": "domainPackId",
            "severity": "error",
        }
    ]


def test_runtime_binding_registration_rejects_conflicting_redefinition():
    pack_id = _scalar_pack_id("binding-conflict")
    register_domain_pack(_scalar_domain_pack(pack_id))
    binding = _scalar_binding(pack_id)

    assert register_domain_runtime_binding(binding) is binding

    conflicting = _scalar_binding(pack_id, evaluator_version="vendor.scalar-evaluator@8")
    with pytest.raises(ValueError, match=pack_id):
        register_domain_runtime_binding(conflicting)


def test_domain_pack_failure_mapping_is_machine_readable():
    mapping = ORDERED_POINT_DOMAIN_PACK.failure_mapping("ArtifactTypeMismatch")

    assert mapping is not None
    assert mapping.model_dump(mode="json", by_alias=True) == {
        "code": "ArtifactTypeMismatch",
        "executionStatus": "Skipped",
        "metricStatus": "InvalidObservation",
        "caseOutcome": "Invalid",
    }
    assert ORDERED_POINT_DOMAIN_PACK.failure_mapping("vendor.unknown-code@1") is None


def test_runtime_binding_parse_failures_are_structured():
    pack_id = _scalar_pack_id("parse-failure")
    pack = _scalar_domain_pack(pack_id)
    register_domain_pack(pack)
    register_domain_runtime_binding(_scalar_binding(pack_id, pack.evaluator_version))
    payload = _scalar_request("not-a-list")
    payload["domainPackId"] = pack_id

    bundle = evaluate_run(payload).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert bundle["run"]["executionStatus"] == "Skipped"
    assert bundle["report"]["caseOutcome"] == "Invalid"
    assert bundle["report"]["domainFailures"] == [
        {
            "code": "MalformedEvaluationRequest",
            "message": "RunSpec request does not satisfy the registered DomainPack runtime binding.",
            "path": "request.artifact.values",
            "severity": "error",
        }
    ]


def test_runtime_binding_value_errors_do_not_leak_parser_details():
    pack_id = _scalar_pack_id("parser-value-error")
    pack = _scalar_domain_pack(pack_id)
    register_domain_pack(pack)
    working_binding = _scalar_binding(pack_id, pack.evaluator_version)

    def fail_parse(request: Any) -> Any:
        raise ValueError("internal vendor parser secret")

    register_domain_runtime_binding(
        DomainRuntimeBinding(
            domain_pack_id=pack_id,
            parse_request=fail_parse,
            evaluate=working_binding.evaluate,
        )
    )
    payload = _scalar_request([1.0])
    payload["domainPackId"] = pack_id

    bundle = evaluate_run(payload).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert bundle["run"]["executionStatus"] == "Skipped"
    assert bundle["report"]["caseOutcome"] == "Invalid"
    assert bundle["report"]["domainFailures"] == [
        {
            "code": "MalformedEvaluationRequest",
            "message": "RunSpec request failed domain-specific validation.",
            "path": "request",
            "severity": "error",
        }
    ]
    assert "vendor parser secret" not in str(bundle)


def test_runtime_binding_evaluator_failures_are_structured_without_leaking_exception_details():
    pack_id = _scalar_pack_id("evaluator-failure")
    pack = _scalar_domain_pack(pack_id)
    register_domain_pack(pack)
    working_binding = _scalar_binding(pack_id, pack.evaluator_version)

    def fail_evaluation(request: Any) -> EvaluationReport:
        raise RuntimeError("internal vendor secret")

    register_domain_runtime_binding(
        DomainRuntimeBinding(
            domain_pack_id=pack_id,
            parse_request=working_binding.parse_request,
            evaluate=fail_evaluation,
        )
    )
    payload = _scalar_request([1.0])
    payload["domainPackId"] = pack_id

    bundle = evaluate_run(payload).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert bundle["run"]["executionStatus"] == "ExecutionFailed"
    assert bundle["report"]["caseOutcome"] == "Inconclusive"
    assert bundle["report"]["metricResults"][0]["status"] == "NumericalFailure"
    assert bundle["report"]["domainFailures"] == [
        {
            "code": "DomainEvaluatorFailed",
            "message": "The registered DomainPack evaluator failed during execution.",
            "path": "domainPackId",
            "severity": "error",
        }
    ]
    assert "vendor secret" not in str(bundle)


def test_ordered_point_missing_points_is_structured_instead_of_falling_through_generic_envelope():
    bundle = evaluate_run(
        {
            "subjectId": "imported-artifact@1",
            "domainPackId": "ordered-point.domain-pack@1",
            "runnerId": "artifact-import@1",
            "evaluatorVersion": "ordered-point-evaluator@1",
            "request": {
                "artifact": {
                    "artifactType": "ordered-point-sequence",
                    "schemaVersion": 1,
                },
                "case": {
                    "caseId": "ordered-point-missing-points@1",
                    "requiredMetrics": ["path.length.open"],
                },
            },
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert bundle["run"]["executionStatus"] == "Skipped"
    assert bundle["report"]["caseOutcome"] == "Invalid"
    assert bundle["report"]["domainFailures"] == [
        {
            "code": "MalformedEvaluationRequest",
            "message": "RunSpec request does not satisfy the registered DomainPack runtime binding.",
            "path": "request.artifact.points",
            "severity": "error",
        }
    ]


def test_generic_reference_binding_extras_round_trip_through_core_request():
    pack_id = _scalar_pack_id("reference-roundtrip")
    pack = _scalar_domain_pack(pack_id)
    register_domain_pack(pack)
    register_domain_runtime_binding(_scalar_binding(pack_id, pack.evaluator_version))
    reference_binding = {
        "reference": {
            "artifactType": "scalar-sample",
            "schemaVersion": 1,
            "values": [9.0],
            "vendorMetadata": {"origin": "fixture"},
        },
        "adapter": {"mode": "passthrough"},
        "customFlag": True,
    }
    payload = _scalar_request([1.0, 2.0], reference_binding=reference_binding)
    payload["domainPackId"] = pack_id

    bundle = evaluate_run(payload).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert bundle["runSpec"]["request"]["referenceBinding"] == reference_binding


def test_ordered_point_runtime_binding_preserves_existing_request_compatibility():
    request = _ordered_point_request()

    bare_bundle = evaluate_run(request).model_dump(mode="json", by_alias=True, exclude_none=True)
    explicit_bundle = evaluate_run(
        {
            "subjectId": "imported-artifact@1",
            "request": request,
            "domainPackId": "ordered-point.domain-pack@1",
            "runnerId": "artifact-import@1",
            "evaluatorVersion": "ordered-point-evaluator@1",
        }
    ).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert bare_bundle["runSpec"]["subjectId"] == "imported-artifact@1"
    assert bare_bundle["runSpec"]["domainPackId"] == "ordered-point.domain-pack@1"
    assert bare_bundle["runSpec"]["runnerId"] == "artifact-import@1"
    assert bare_bundle["runSpec"]["evaluatorVersion"] == "ordered-point-evaluator@1"
    assert bare_bundle["report"] == explicit_bundle["report"]
    assert bare_bundle["observation"]["artifact"]["artifactType"] == explicit_bundle["observation"]["artifact"]["artifactType"]
    assert bare_bundle["observation"]["artifact"]["schemaVersion"] == explicit_bundle["observation"]["artifact"]["schemaVersion"]


def test_run_py_has_no_ordered_point_specific_routing_branch_for_explicit_domain_packs():
    source = inspect.getsource(run_module._apply_domain_pack_defaults)

    assert "ORDERED_POINT_DOMAIN_PACK_ID" not in source
