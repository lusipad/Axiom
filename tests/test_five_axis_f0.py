from __future__ import annotations

import json
from importlib import resources

import pytest
from pydantic import ValidationError

from axiom.adapters import (
    FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER,
    ArtifactAdapter,
    get_artifact_adapter,
    list_artifact_adapters,
    register_artifact_adapter,
)
from axiom.evaluator import _content_hash
from axiom.models import CoreEvaluationRequest, ExecutionStatus, MetricStatus
from axiom.run import evaluate_run
from axiom.five_axis import (
    F0_EVALUATOR_ID,
    FIVE_AXIS_DOMAIN_PACK,
    FIVE_AXIS_CONTRACT_METRIC_ID,
    FIVE_AXIS_F0_DOMAIN_PACK,
    FIVE_AXIS_RUNTIME_BINDING,
    MathStageManifest,
    SampledCartesianPositionView,
    StageEnvelope,
    evaluate_five_axis_f0,
    f0_example_run_spec,
    load_f0_manifest,
)
from axiom.five_axis import runtime as five_axis_runtime

def _load_json(relative_path: str) -> dict:
    return json.loads(
        resources.files("axiom.five_axis.fixtures").joinpath(relative_path).read_text(encoding="utf-8")
    )


def test_fixture_manifest_uses_real_content_hashes_and_no_todo_markers():
    manifest_payload = _load_json("manifest.json")
    fixture_manifest = load_f0_manifest()

    listed_files = {item["file"] for item in manifest_payload["fixtures"]}
    actual_files = {
        path.name
        for path in resources.files("axiom.five_axis.fixtures").iterdir()
        if path.name.endswith(".json") and path.name != "manifest.json"
    }

    assert listed_files == actual_files
    assert "TODO" not in json.dumps(manifest_payload, ensure_ascii=False)
    assert set(fixture_manifest.fixture_content_ids) == {
        item["contentHash"] for item in manifest_payload["fixtures"] if item["id"] != fixture_manifest.manifest_id
    }

    for item in manifest_payload["fixtures"]:
        payload = _load_json(item["file"])
        assert _content_hash(payload) == item["contentHash"]


def test_adapter_registry_is_static_and_rejects_conflicts():
    assert get_artifact_adapter(
        "five-axis.sampled-cartesian-position-view",
        "ordered-point-sequence",
    ) is FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER
    assert FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER in list_artifact_adapters()
    assert (
        register_artifact_adapter(FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER)
        is FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER
    )

    conflicting_id = ArtifactAdapter(
        adapter_id=FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER.adapter_id,
        source_artifact_type="five-axis.other-artifact",
        target_artifact_type="ordered-point-sequence",
        transform=lambda payload: payload,
    )
    with pytest.raises(ValueError, match="adapter ID is already registered"):
        register_artifact_adapter(conflicting_id)

    conflicting_route = ArtifactAdapter(
        adapter_id="five-axis.sampled-cartesian-to-ordered-point.alt@1",
        source_artifact_type="five-axis.sampled-cartesian-position-view",
        target_artifact_type="ordered-point-sequence",
        transform=lambda payload: payload,
    )
    with pytest.raises(ValueError, match="adapter route is already registered"):
        register_artifact_adapter(conflicting_route)


def test_sampled_cartesian_view_adapts_to_ordered_point_with_semantics_delta():
    view = SampledCartesianPositionView.model_validate(_load_json("sampled_cartesian_view.json"))

    result = FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER.adapt(view)
    artifact = result.artifact

    assert artifact.artifact_type == "ordered-point-sequence"
    assert artifact.points == [[0.0, 1.0, 2.0], [0.5, 1.5, 2.5], [1.0, 2.0, 3.0]]
    assert artifact.semantics is not None
    assert artifact.semantics.unit == "mm"
    assert artifact.semantics.coordinate_frame == "machine.work-envelope@1"
    assert artifact.parameter is None
    assert result.content_hash == _content_hash(artifact)
    assert result.provenance.source_content_hash == _content_hash(view)
    assert result.provenance.result_content_hash == result.content_hash
    assert result.provenance.preserved_semantics == ["coordinateFrame", "unit"]
    assert result.provenance.dropped_semantics == ["derivedViewKind", "pathProgress", "regularity"]

    second = FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER.adapt(view)
    assert second.model_dump(mode="json", by_alias=True) == result.model_dump(mode="json", by_alias=True)


def test_adapter_only_reports_semantics_that_were_present_and_dropped():
    payload = _load_json("sampled_cartesian_view.json")
    payload.pop("pathProgress")
    payload.pop("regularity")

    view = SampledCartesianPositionView.model_validate(payload)
    result = FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER.adapt(view)

    assert result.provenance.dropped_semantics == ["derivedViewKind"]


@pytest.mark.parametrize("source_mode", ["joint", "mixed"])
def test_ordered_point_adapter_rejects_non_cartesian_source_modes(source_mode: str):
    payload = _load_json("sampled_cartesian_view.json")
    payload["sourceCoordinateMode"] = source_mode
    view = SampledCartesianPositionView.model_validate(payload)

    with pytest.raises(ValueError, match="only cartesian-xyz source semantics can adapt"):
        FIVE_AXIS_SAMPLED_CARTESIAN_TO_ORDERED_POINT_ADAPTER.adapt(view)


def test_five_axis_contract_models_reject_unknown_fields_and_illegal_versions():
    manifest = _load_json("math_stage_manifest.json")
    manifest["schemaVersion"] = 2
    with pytest.raises(ValidationError):
        MathStageManifest.model_validate(manifest)

    envelope = {
        "envelopeId": "five-axis.m6-artifact@1",
        "stage": "M6",
        "envelopeType": "artifact",
        "schemaId": "five-axis.envelope@1",
        "contentId": "0" * 64,
    }
    with pytest.raises(ValidationError):
        StageEnvelope.model_validate(envelope)

    payload = _load_json("sampled_cartesian_view.json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        SampledCartesianPositionView.model_validate(payload)


def test_five_axis_contract_models_reject_uppercase_ids_bad_content_hashes_and_duplicate_stages():
    envelope = _load_json("math_stage_manifest.json")["envelopes"][0]

    uppercase_envelope = dict(envelope)
    uppercase_envelope["envelopeId"] = "Five-axis.m0-artifact@1"
    with pytest.raises(ValidationError):
        StageEnvelope.model_validate(uppercase_envelope)

    wrong_hash_envelope = dict(envelope)
    wrong_hash_envelope["contentId"] = "0" * 64
    with pytest.raises(ValidationError, match="contentId must equal the canonical content hash"):
        StageEnvelope.model_validate(wrong_hash_envelope)

    manifest = _load_json("math_stage_manifest.json")
    manifest["policyVersions"]["collisionContext"] = "Five-axis.collision-context.required@1"
    with pytest.raises(ValidationError, match="policyVersions values must be versioned IDs"):
        MathStageManifest.model_validate(manifest)

    manifest = _load_json("math_stage_manifest.json")
    manifest["envelopes"][5] = dict(manifest["envelopes"][4])
    with pytest.raises(ValidationError, match="cover M0 through M5 exactly once"):
        MathStageManifest.model_validate(manifest)

    manifest = _load_json("math_stage_manifest.json")
    manifest["envelopes"].append(dict(manifest["envelopes"][0]))
    with pytest.raises(ValidationError, match="exactly six stage envelopes"):
        MathStageManifest.model_validate(manifest)


def test_f0_metric_definition_has_zero_tolerance_contract():
    metric_definition = FIVE_AXIS_DOMAIN_PACK.metric_definition(FIVE_AXIS_CONTRACT_METRIC_ID)

    assert metric_definition.numeric_tolerance is not None
    assert metric_definition.numeric_tolerance.absolute == 0.0
    assert metric_definition.numeric_tolerance.relative == 0.0
    assert metric_definition.numeric_tolerance.unit is None


def test_f0_evaluator_stays_contract_only_and_reports_schema_boundary_findings():
    fixture_manifest = load_f0_manifest()
    view = SampledCartesianPositionView.model_validate(_load_json("sampled_cartesian_view.json"))

    report = evaluate_five_axis_f0(
        {
            "artifact": view.model_dump(mode="json", by_alias=True),
            "case": {
                "caseId": "five-axis.contract.test@1",
                "requiredMetrics": [FIVE_AXIS_CONTRACT_METRIC_ID],
            },
            "manifest": fixture_manifest.model_dump(mode="json", by_alias=True),
        }
    )
    assert report.evaluator_version == F0_EVALUATOR_ID
    assert report.execution_status is ExecutionStatus.SUCCEEDED
    assert report.case_outcome.value == "Passed"
    assert report.metric_results[0].status is MetricStatus.COMPUTED
    assert report.metric_results[0].value is True
    assert report.metric_results[0].details["schemaOnlyBoundary"] is True
    assert report.metric_results[0].details["contractClosureValidated"] is True
    assert {finding.code for finding in report.domain_failures} == {
        "RuntimeEnvironmentDiffersFromManifest",
        "MissingCollisionContext",
        "MissingReconstructionPolicy",
    }
    assert {finding.severity for finding in report.domain_failures} == {"finding"}
    assert {(item.capability_id, item.source) for item in report.capabilities} == {
        ("five-axis.contract.manifest@1", "Evaluator"),
        ("five-axis.derived.sampled-cartesian-view@1", "Artifact"),
        ("five-axis.adapter.ordered-point-export@1", "Adapter"),
    }
    assert report.provenance is not None
    assert set(report.provenance.numeric_environment) == {"python", "pydantic"}


def test_f0_evaluator_keeps_required_metric_and_execution_status_consistent():
    fixture_manifest = load_f0_manifest()
    view = SampledCartesianPositionView.model_validate(_load_json("sampled_cartesian_view.json"))

    supported = evaluate_five_axis_f0(
        {
            "artifact": view.model_dump(mode="json", by_alias=True),
            "case": {
                "caseId": "five-axis.contract.test@1",
                "requiredMetrics": [FIVE_AXIS_CONTRACT_METRIC_ID],
            },
            "manifest": fixture_manifest.model_dump(mode="json", by_alias=True),
            "collisionContext": {"contextId": "fixture-collision@1"},
            "reconstructionPolicy": {"policyId": "five-axis.reconstruction.none@1"},
        }
    )
    assert supported.execution_status is ExecutionStatus.SUCCEEDED
    assert supported.case_outcome.value == "Passed"
    assert supported.metric_results[0].status is MetricStatus.COMPUTED

    manifest = fixture_manifest.model_dump(mode="json", by_alias=True)
    manifest["expectedStatus"] = "Insufficient"
    insufficient = evaluate_five_axis_f0(
        {
            "artifact": view.model_dump(mode="json", by_alias=True),
            "case": {
                "caseId": "five-axis.contract.test@1",
                "requiredMetrics": [FIVE_AXIS_CONTRACT_METRIC_ID],
            },
            "manifest": manifest,
            "collisionContext": {"contextId": "fixture-collision@1"},
            "reconstructionPolicy": {"policyId": "five-axis.reconstruction.none@1"},
        }
    )
    assert insufficient.execution_status is ExecutionStatus.SKIPPED
    assert insufficient.case_outcome.value == "Inconclusive"
    assert insufficient.metric_results[0].status is MetricStatus.INSUFFICIENT_CONTEXT

    manifest["expectedStatus"] = "Inconclusive"
    inconclusive = evaluate_five_axis_f0(
        {
            "artifact": view.model_dump(mode="json", by_alias=True),
            "case": {
                "caseId": "five-axis.contract.test@1",
                "requiredMetrics": [FIVE_AXIS_CONTRACT_METRIC_ID],
            },
            "manifest": manifest,
            "collisionContext": {"contextId": "fixture-collision@1"},
            "reconstructionPolicy": {"policyId": "five-axis.reconstruction.none@1"},
        }
    )
    assert inconclusive.execution_status is ExecutionStatus.SKIPPED
    assert inconclusive.case_outcome.value == "Inconclusive"
    assert inconclusive.metric_results[0].status is MetricStatus.INSUFFICIENT_CONTEXT


def test_f0_evaluator_rejects_unknown_required_metric_without_false_positive_readiness():
    fixture_manifest = load_f0_manifest()
    view = SampledCartesianPositionView.model_validate(_load_json("sampled_cartesian_view.json"))

    report = evaluate_five_axis_f0(
        {
            "artifact": view.model_dump(mode="json", by_alias=True),
            "case": {
                "caseId": "five-axis.contract.test@1",
                "requiredMetrics": [{"metricId": "five-axis.geometry.valid@1"}],
            },
            "manifest": fixture_manifest.model_dump(mode="json", by_alias=True),
            "collisionContext": {"contextId": "fixture-collision@1"},
            "reconstructionPolicy": {"policyId": "five-axis.reconstruction.none@1"},
        }
    )

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome.value == "Unsupported"
    assert report.metric_results[0].metric_id == "five-axis.geometry.valid@1"
    assert report.metric_results[0].status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert report.metric_results[0].value is None
    assert report.metric_results[0].reason_code == "MetricNotImplementedInF0"


@pytest.mark.parametrize(
    ("mutate_manifest", "mutate_artifact", "expected_failure_code"),
    [
        (
            None,
            lambda payload: payload.pop("capabilityIds"),
            "MissingArtifactCapabilities",
        ),
        (
            None,
            lambda payload: payload["envelopes"].pop(),
            "ArtifactEnvelopeCoverageMismatch",
        ),
        (
            None,
            lambda payload: payload["envelopes"].append(dict(payload["envelopes"][0])),
            "ArtifactEnvelopeCoverageMismatch",
        ),
        (
            lambda payload: payload.__setitem__("fixtureContentIds", ["0" * 64]),
            None,
            "FixtureContentIdentityMismatch",
        ),
    ],
)
def test_f0_evaluator_rejects_invalid_contract_closure_before_computed(
    mutate_manifest,
    mutate_artifact,
    expected_failure_code,
):
    fixture_manifest = load_f0_manifest().model_dump(mode="json", by_alias=True)
    artifact_payload = _load_json("sampled_cartesian_view.json")

    if mutate_manifest is not None:
        mutate_manifest(fixture_manifest)
    if mutate_artifact is not None:
        mutate_artifact(artifact_payload)

    report = evaluate_five_axis_f0(
        {
            "artifact": artifact_payload,
            "case": {
                "caseId": "five-axis.contract.test@1",
                "requiredMetrics": [FIVE_AXIS_CONTRACT_METRIC_ID],
            },
            "manifest": fixture_manifest,
            "collisionContext": {"contextId": "fixture-collision@1"},
            "reconstructionPolicy": {"policyId": "five-axis.reconstruction.none@1"},
        }
    )

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome.value == "Invalid"
    assert report.metric_results[0].status is MetricStatus.INVALID_OBSERVATION
    assert report.metric_results[0].value is None
    assert report.metric_results[0].reason_code == "F0ContractClosureInvalid"
    assert report.metric_results[0].details["contractClosureValidated"] is False
    assert expected_failure_code in {failure.code for failure in report.domain_failures}
    assert report.capabilities == []


def test_f0_evaluator_requires_registered_ordered_point_adapter_route():
    fixture_manifest = load_f0_manifest().model_dump(mode="json", by_alias=True)
    artifact_payload = _load_json("sampled_cartesian_view.json")

    def _missing_route(*_args, **_kwargs):
        raise LookupError("missing route")

    original = five_axis_runtime.get_artifact_adapter
    five_axis_runtime.get_artifact_adapter = _missing_route
    try:
        report = evaluate_five_axis_f0(
            {
                "artifact": artifact_payload,
                "case": {
                    "caseId": "five-axis.contract.test@1",
                    "requiredMetrics": [FIVE_AXIS_CONTRACT_METRIC_ID],
                },
                "manifest": fixture_manifest,
                "collisionContext": {"contextId": "fixture-collision@1"},
                "reconstructionPolicy": {"policyId": "five-axis.reconstruction.none@1"},
            }
        )
    finally:
        five_axis_runtime.get_artifact_adapter = original

    assert report.execution_status is ExecutionStatus.SKIPPED
    assert report.case_outcome.value == "Unsupported"
    assert report.metric_results[0].status is MetricStatus.UNSUPPORTED_CAPABILITY
    assert report.metric_results[0].value is None
    assert report.metric_results[0].reason_code == "OrderedPointAdapterRouteUnavailable"
    assert report.metric_results[0].details["contractClosureValidated"] is False
    assert {failure.code for failure in report.domain_failures} == {"MissingOrderedPointAdapterRoute"}
    assert report.capabilities == []


def test_five_axis_domain_pack_descriptor_is_explicit_and_runtime_bound():
    assert FIVE_AXIS_DOMAIN_PACK is FIVE_AXIS_F0_DOMAIN_PACK
    assert FIVE_AXIS_F0_DOMAIN_PACK.domain_pack_id == "five-axis.domain-pack@1"
    assert FIVE_AXIS_F0_DOMAIN_PACK.artifact_type == "five-axis.sampled-cartesian-position-view"
    assert FIVE_AXIS_F0_DOMAIN_PACK.artifact_schema_versions == (1,)
    assert FIVE_AXIS_F0_DOMAIN_PACK.evaluator_version == F0_EVALUATOR_ID
    assert FIVE_AXIS_F0_DOMAIN_PACK.claim_definition_ids == ("axiom.core.case-outcome-claim@1",)


def test_runtime_binding_and_example_payload_are_serializable_and_stable():
    binding = FIVE_AXIS_RUNTIME_BINDING
    payload = f0_example_run_spec()

    assert binding.domain_pack_id == FIVE_AXIS_DOMAIN_PACK.domain_pack_id
    assert payload["domainPackId"] == FIVE_AXIS_DOMAIN_PACK.domain_pack_id
    assert payload["evaluatorVersion"] == F0_EVALUATOR_ID
    assert payload["request"]["manifest"] == load_f0_manifest().model_dump(mode="json", by_alias=True)
    assert payload["request"]["artifact"]["artifactType"] == "five-axis.sampled-cartesian-position-view"
    assert payload["request"]["collisionContext"] is None
    assert payload["request"]["reconstructionPolicy"] is None

    parsed = binding.parse_request(CoreEvaluationRequest.model_validate(payload["request"]))
    first = binding.evaluate(parsed)
    second = binding.evaluate(parsed)
    bundle = evaluate_run(payload).model_dump(mode="json", by_alias=True, exclude_none=True)

    assert first.model_dump(mode="json", by_alias=True) == second.model_dump(mode="json", by_alias=True)
    assert bundle["run"]["domainPackId"] == FIVE_AXIS_DOMAIN_PACK.domain_pack_id
    assert bundle["report"]["executionStatus"] == "Succeeded"
    assert bundle["report"]["caseOutcome"] == "Passed"
    assert bundle["report"]["metricResults"][0]["status"] == "Computed"
    assert {failure["severity"] for failure in bundle["report"]["domainFailures"]} == {"finding"}
    assert bundle["claims"][0]["claimDefinitionId"] == "axiom.core.case-outcome-claim@1"
    assert bundle["claims"][0]["details"]["caseOutcome"] == "Passed"
