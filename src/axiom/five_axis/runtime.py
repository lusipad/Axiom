from __future__ import annotations

import platform
from importlib import resources
from importlib.metadata import version as package_version
from typing import Any

from pydantic import ConfigDict, Field

from ..adapters import get_artifact_adapter
from ..domain import (
    ARTIFACT_IMPORT_RUNNER_ID,
    CASE_OUTCOME_CLAIM_DEFINITION_ID,
    DomainPack,
    FailureMapping,
    MetricDefinition,
    NumericTolerance,
    register_domain_pack,
)
from ..evaluator import _content_hash
from ..models import (
    AxiomModel,
    CapabilityResolution,
    CaseOutcome,
    CoreEvaluationRequest,
    DomainFailure,
    EvaluationCase,
    EvaluationReport,
    ExecutionStatus,
    MetricResult,
    MetricStatus,
    Provenance,
)
from ..runtime import DomainRuntimeBinding, register_domain_runtime_binding
from .models import MathStageManifest, SampledCartesianPositionView, StageEnvelope


FIVE_AXIS_DOMAIN_PACK_ID = "five-axis.domain-pack@1"
F0_EVALUATOR_ID = "five-axis-f0-evaluator@1"
FIVE_AXIS_RUNNER_ID = ARTIFACT_IMPORT_RUNNER_ID
FIVE_AXIS_CONTRACT_METRIC_ID = "five-axis.contract.readiness@1"
FIVE_AXIS_ORDERED_POINT_TARGET_ARTIFACT_TYPE = "ordered-point-sequence"
FIVE_AXIS_ORDERED_POINT_ADAPTER_CAPABILITY_ID = "five-axis.adapter.ordered-point-export@1"
FIVE_AXIS_REQUIRED_ARTIFACT_CAPABILITY_IDS = (
    "five-axis.contract.manifest@1",
    "five-axis.derived.sampled-cartesian-view@1",
)
FIVE_AXIS_STAGE_CAPABILITY_IDS = {
    "M0": "five-axis.contract.envelope.m0@1",
    "M1": "five-axis.contract.envelope.m1@1",
    "M2": "five-axis.contract.envelope.m2@1",
    "M3": "five-axis.contract.envelope.m3@1",
    "M4": "five-axis.contract.envelope.m4@1",
    "M5": "five-axis.contract.envelope.m5@1",
}
FIVE_AXIS_CAPABILITY_IDS = (
    "five-axis.contract.manifest@1",
    "five-axis.contract.envelope.m0@1",
    "five-axis.contract.envelope.m1@1",
    "five-axis.contract.envelope.m2@1",
    "five-axis.contract.envelope.m3@1",
    "five-axis.contract.envelope.m4@1",
    "five-axis.contract.envelope.m5@1",
    "five-axis.derived.sampled-cartesian-view@1",
    "five-axis.adapter.ordered-point-export@1",
)
_FAILURE_MAPPINGS = (
    FailureMapping(
        code="MalformedEvaluationRequest",
        executionStatus="Skipped",
        metricStatus="InvalidObservation",
        caseOutcome="Invalid",
    ),
    FailureMapping(
        code="ArtifactTypeMismatch",
        executionStatus="Skipped",
        metricStatus="InvalidObservation",
        caseOutcome="Invalid",
    ),
    FailureMapping(
        code="ArtifactSchemaVersionMismatch",
        executionStatus="Skipped",
        metricStatus="InvalidObservation",
        caseOutcome="Invalid",
    ),
    FailureMapping(
        code="RunnerMismatch",
        executionStatus="Skipped",
        metricStatus="UnsupportedCapability",
        caseOutcome="Unsupported",
    ),
    FailureMapping(
        code="EvaluatorVersionMismatch",
        executionStatus="Skipped",
        metricStatus="UnsupportedCapability",
        caseOutcome="Unsupported",
    ),
)


class FiveAxisEvaluationBindingRequest(AxiomModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    artifact: SampledCartesianPositionView
    case: EvaluationCase
    manifest: MathStageManifest
    collision_context: dict[str, Any] | None = Field(default=None, alias="collisionContext")
    reconstruction_policy: dict[str, Any] | None = Field(default=None, alias="reconstructionPolicy")


def _missing_capabilities_message(subject: str, missing: set[str]) -> str:
    missing_list = ", ".join(sorted(missing))
    return f"{subject} is missing required capability IDs: {missing_list}."


def _envelopes_by_stage(envelopes: tuple[StageEnvelope, ...]) -> dict[str, StageEnvelope]:
    return {envelope.stage: envelope for envelope in envelopes}


def _contract_preflight(
    resolved: FiveAxisEvaluationBindingRequest,
    *,
    artifact_hash: str,
) -> tuple[list[DomainFailure], list[CapabilityResolution]]:
    failures: list[DomainFailure] = []
    capabilities: list[CapabilityResolution] = []

    manifest_capabilities = set(resolved.manifest.capability_ids)
    required_manifest_capabilities = set(FIVE_AXIS_CAPABILITY_IDS)
    missing_manifest_capabilities = required_manifest_capabilities - manifest_capabilities
    if missing_manifest_capabilities:
        failures.append(
            DomainFailure(
                code="MissingManifestCapabilities",
                message=_missing_capabilities_message("Manifest", missing_manifest_capabilities),
                path="manifest.capabilityIds",
            )
        )

    artifact_capabilities = set(resolved.artifact.capability_ids)
    required_artifact_capabilities = set(FIVE_AXIS_REQUIRED_ARTIFACT_CAPABILITY_IDS)
    if FIVE_AXIS_ORDERED_POINT_ADAPTER_CAPABILITY_ID in manifest_capabilities:
        required_artifact_capabilities.add(FIVE_AXIS_ORDERED_POINT_ADAPTER_CAPABILITY_ID)
    missing_artifact_capabilities = required_artifact_capabilities - artifact_capabilities
    if missing_artifact_capabilities:
        failures.append(
            DomainFailure(
                code="MissingArtifactCapabilities",
                message=_missing_capabilities_message("Artifact", missing_artifact_capabilities),
                path="artifact.capabilityIds",
            )
        )

    if artifact_hash not in resolved.manifest.fixture_content_ids:
        failures.append(
            DomainFailure(
                code="FixtureContentIdentityMismatch",
                message="Manifest fixtureContentIds must include the exact artifact content hash carried by the request.",
                path="manifest.fixtureContentIds",
            )
        )

    manifest_envelopes = _envelopes_by_stage(resolved.manifest.envelopes)
    artifact_envelopes = _envelopes_by_stage(resolved.artifact.envelopes)
    expected_stages = set(FIVE_AXIS_STAGE_CAPABILITY_IDS)
    artifact_stages = set(artifact_envelopes)
    if len(resolved.artifact.envelopes) != 6 or artifact_stages != expected_stages:
        failures.append(
            DomainFailure(
                code="ArtifactEnvelopeCoverageMismatch",
                message=(
                    "Artifact envelopes must cover M0 through M5 exactly once; "
                    f"observed stages: {', '.join(sorted(artifact_stages)) or 'none'}."
                ),
                path="artifact.envelopes",
            )
        )

    for stage, required_capability in FIVE_AXIS_STAGE_CAPABILITY_IDS.items():
        manifest_envelope = manifest_envelopes.get(stage)
        artifact_envelope = artifact_envelopes.get(stage)
        if manifest_envelope is None or artifact_envelope is None:
            continue
        if required_capability not in set(manifest_envelope.capability_ids):
            failures.append(
                DomainFailure(
                    code="ManifestEnvelopeCapabilityMismatch",
                    message=f"Manifest envelope {stage} must declare capability {required_capability}.",
                    path="manifest.envelopes",
                )
            )
        if required_capability not in set(artifact_envelope.capability_ids):
            failures.append(
                DomainFailure(
                    code="ArtifactEnvelopeCapabilityMismatch",
                    message=f"Artifact envelope {stage} must declare capability {required_capability}.",
                    path="artifact.envelopes",
                )
            )
        if artifact_envelope.content_id != manifest_envelope.content_id:
            failures.append(
                DomainFailure(
                    code="EnvelopeContentIdentityMismatch",
                    message=f"Artifact envelope {stage} must match the manifest envelope content identity.",
                    path="artifact.envelopes",
                )
            )

    if FIVE_AXIS_ORDERED_POINT_ADAPTER_CAPABILITY_ID in required_artifact_capabilities:
        try:
            get_artifact_adapter(
                resolved.artifact.artifact_type,
                FIVE_AXIS_ORDERED_POINT_TARGET_ARTIFACT_TYPE,
            )
        except LookupError:
            failures.append(
                DomainFailure(
                    code="MissingOrderedPointAdapterRoute",
                    message=(
                        "The request advertises ordered-point export but no registered adapter route exists for "
                        "five-axis.sampled-cartesian-position-view -> ordered-point-sequence."
                    ),
                    path="artifact.capabilityIds",
                )
            )
        else:
            capabilities.append(
                CapabilityResolution(
                    capabilityId=FIVE_AXIS_ORDERED_POINT_ADAPTER_CAPABILITY_ID,
                    source="Adapter",
                )
            )

    if failures:
        return failures, []

    capabilities.extend(
        [
            CapabilityResolution(capabilityId="five-axis.contract.manifest@1", source="Evaluator"),
            CapabilityResolution(capabilityId="five-axis.derived.sampled-cartesian-view@1", source="Artifact"),
        ]
    )
    return failures, capabilities


def current_numeric_environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "pydantic": package_version("pydantic"),
    }


FIVE_AXIS_DOMAIN_PACK = register_domain_pack(
    DomainPack(
        domain_pack_id=FIVE_AXIS_DOMAIN_PACK_ID,
        artifact_type="five-axis.sampled-cartesian-position-view",
        artifact_schema_versions=[1],
        evaluator_version=F0_EVALUATOR_ID,
        runner_id=FIVE_AXIS_RUNNER_ID,
        runner_ids=[FIVE_AXIS_RUNNER_ID],
        capability_ids=FIVE_AXIS_CAPABILITY_IDS,
        metric_definitions=[
            MetricDefinition(
                metric_id=FIVE_AXIS_CONTRACT_METRIC_ID,
                metric_definition_id=FIVE_AXIS_CONTRACT_METRIC_ID,
                requires=(
                    "five-axis.contract.manifest@1",
                    "five-axis.derived.sampled-cartesian-view@1",
                ),
                numeric_tolerance=NumericTolerance(absolute=0.0, relative=0.0),
            )
        ],
        claim_definition_ids=[CASE_OUTCOME_CLAIM_DEFINITION_ID],
        comparison_policy_ids=[],
        failure_mappings=_FAILURE_MAPPINGS,
    )
)
FIVE_AXIS_F0_DOMAIN_PACK = FIVE_AXIS_DOMAIN_PACK


def load_f0_manifest() -> MathStageManifest:
    return MathStageManifest.model_validate_json(
        resources.files("axiom.five_axis.fixtures").joinpath("math_stage_manifest.json").read_text(encoding="utf-8")
    )


def load_f0_sample_view() -> SampledCartesianPositionView:
    return SampledCartesianPositionView.model_validate_json(
        resources.files("axiom.five_axis.fixtures").joinpath("sampled_cartesian_view.json").read_text(encoding="utf-8")
    )


def f0_example_run_spec() -> dict[str, Any]:
    return {
        "subjectId": "five-axis-fixture@1",
        "domainPackId": FIVE_AXIS_DOMAIN_PACK.domain_pack_id,
        "runnerId": FIVE_AXIS_RUNNER_ID,
        "evaluatorVersion": F0_EVALUATOR_ID,
        "request": {
            "artifact": load_f0_sample_view().model_dump(mode="json", by_alias=True),
            "case": {
                "caseId": "five-axis.f0-contract@1",
                "requiredMetrics": [FIVE_AXIS_CONTRACT_METRIC_ID],
            },
            "manifest": load_f0_manifest().model_dump(mode="json", by_alias=True),
            "collisionContext": None,
            "reconstructionPolicy": None,
        },
    }


def _parse_binding_request(request: CoreEvaluationRequest) -> FiveAxisEvaluationBindingRequest:
    payload = request.model_dump(mode="json", by_alias=True, exclude_unset=True)
    return FiveAxisEvaluationBindingRequest.model_validate(payload)


def evaluate_five_axis_f0(
    request: FiveAxisEvaluationBindingRequest | dict[str, Any],
) -> EvaluationReport:
    resolved = (
        request
        if isinstance(request, FiveAxisEvaluationBindingRequest)
        else FiveAxisEvaluationBindingRequest.model_validate(request)
    )
    failures: list[DomainFailure] = []
    readiness_status = MetricStatus.COMPUTED
    readiness_reason_code = "F0ContractValidated"
    readiness_value: bool | None = True
    capabilities: list[CapabilityResolution] = []

    artifact_payload = resolved.artifact.model_dump(mode="json", by_alias=True, exclude_none=True)
    artifact_hash = _content_hash(artifact_payload)

    if resolved.artifact.source_coordinate_mode != "cartesian-xyz":
        readiness_status = MetricStatus.UNSUPPORTED_CAPABILITY
        readiness_reason_code = "UnsupportedCoordinateMode"
        readiness_value = None
        failures.append(
            DomainFailure(
                code="UnsupportedCoordinateMode",
                message="F0 only accepts cartesian-xyz sampled position views.",
                path="artifact.sourceCoordinateMode",
            )
        )
    elif resolved.manifest.expected_status == "Unsupported":
        readiness_status = MetricStatus.UNSUPPORTED_CAPABILITY
        readiness_reason_code = "ManifestExpectedUnsupported"
        readiness_value = None
    elif resolved.manifest.expected_status == "Insufficient":
        readiness_status = MetricStatus.INSUFFICIENT_CONTEXT
        readiness_reason_code = "ManifestExpectedInsufficient"
        readiness_value = None
    elif resolved.manifest.expected_status == "Inconclusive":
        readiness_status = MetricStatus.INSUFFICIENT_CONTEXT
        readiness_reason_code = "ManifestExpectedInconclusive"
        readiness_value = None
    else:
        preflight_failures, capabilities = _contract_preflight(resolved, artifact_hash=artifact_hash)
        failures.extend(preflight_failures)
        if preflight_failures:
            readiness_status = (
                MetricStatus.UNSUPPORTED_CAPABILITY
                if all(failure.code == "MissingOrderedPointAdapterRoute" for failure in preflight_failures)
                else MetricStatus.INVALID_OBSERVATION
            )
            readiness_reason_code = (
                "OrderedPointAdapterRouteUnavailable"
                if readiness_status is MetricStatus.UNSUPPORTED_CAPABILITY
                else "F0ContractClosureInvalid"
            )
            readiness_value = None
        else:
            runtime_environment = current_numeric_environment()
            if resolved.manifest.numeric_environment != runtime_environment:
                failures.append(
                    DomainFailure(
                        code="RuntimeEnvironmentDiffersFromManifest",
                        message=(
                            "F0 is a schema-only contract slice; the runtime environment does not match the "
                            "manifest's frozen contract environment."
                        ),
                        path="manifest.numericEnvironment",
                        severity="finding",
                    )
                )
            if resolved.collision_context is None:
                failures.append(
                    DomainFailure(
                        code="MissingCollisionContext",
                        message="F0 contract evaluation requires an explicit CollisionContext.",
                        path="collisionContext",
                        severity="finding",
                    )
                )
            if resolved.reconstruction_policy is None:
                failures.append(
                    DomainFailure(
                        code="MissingReconstructionPolicy",
                        message="F0 contract evaluation requires an explicit reconstruction policy.",
                        path="reconstructionPolicy",
                        severity="finding",
                    )
                )

    request_payload = resolved.model_dump(mode="json", by_alias=True, exclude_none=True)
    case_payload = resolved.case.model_dump(mode="json", by_alias=True, exclude_none=True)
    provenance = Provenance(
        requestHash=_content_hash(request_payload),
        artifactHash=artifact_hash,
        caseHash=_content_hash(case_payload),
        runnerId=FIVE_AXIS_RUNNER_ID,
        evaluatorVersion=F0_EVALUATOR_ID,
        executionOutcomePolicy=resolved.case.execution_outcome_policy,
        numericEnvironment=current_numeric_environment(),
    )
    readiness_definition = FIVE_AXIS_DOMAIN_PACK.metric_definition(FIVE_AXIS_CONTRACT_METRIC_ID)

    def _metric_result(metric_id: str) -> MetricResult:
        if metric_id == FIVE_AXIS_CONTRACT_METRIC_ID:
            return MetricResult(
                metricId=metric_id,
                metricDefinitionId=FIVE_AXIS_CONTRACT_METRIC_ID,
                requires=list(readiness_definition.requires),
                status=readiness_status,
                value=readiness_value,
                reasonCode=readiness_reason_code,
                details={
                    "schemaOnlyBoundary": True,
                    "contractClosureValidated": readiness_status is MetricStatus.COMPUTED,
                    "manifestNumericEnvironment": resolved.manifest.numeric_environment,
                    "runtimeNumericEnvironment": provenance.numeric_environment,
                },
                evidence={"level": "Observed", "method": "five-axis.f0.contract-validation@1"},
            )
        return MetricResult(
            metricId=metric_id,
            metricDefinitionId=metric_id,
            status=MetricStatus.UNSUPPORTED_CAPABILITY,
            value=None,
            reasonCode="MetricNotImplementedInF0",
            details={"schemaOnlyBoundary": True},
        )

    required_results = [_metric_result(metric.metric_id) for metric in resolved.case.required_metrics]
    optional_results = [_metric_result(metric.metric_id) for metric in resolved.case.optional_metrics]
    metric_results = required_results + optional_results

    preflight_statuses = {
        MetricStatus.NOT_APPLICABLE,
        MetricStatus.INSUFFICIENT_CONTEXT,
        MetricStatus.UNSUPPORTED_CAPABILITY,
        MetricStatus.INVALID_OBSERVATION,
    }
    execution_status = (
        ExecutionStatus.SKIPPED
        if any(result.status in preflight_statuses for result in required_results)
        else ExecutionStatus.SUCCEEDED
    )
    if any(result.status is MetricStatus.UNSUPPORTED_CAPABILITY for result in required_results):
        case_outcome = CaseOutcome.UNSUPPORTED
    elif any(result.status is MetricStatus.INVALID_OBSERVATION for result in required_results):
        case_outcome = CaseOutcome.INVALID
    elif any(result.status in {MetricStatus.NOT_APPLICABLE, MetricStatus.INSUFFICIENT_CONTEXT} for result in required_results):
        case_outcome = CaseOutcome.INCONCLUSIVE
    else:
        case_outcome = CaseOutcome.PASSED
    report_payload = {
        "executionStatus": execution_status.value,
        "caseOutcome": case_outcome.value,
        "metricResults": [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in metric_results],
        "capabilities": [item.model_dump(mode="json", by_alias=True) for item in capabilities],
        "domainFailures": [item.model_dump(mode="json", by_alias=True, exclude_none=True) for item in failures],
        "evaluatorVersion": F0_EVALUATOR_ID,
        "provenance": provenance.model_dump(mode="json", by_alias=True, exclude_none=True),
    }
    return EvaluationReport(
        **report_payload,
        contentHash=_content_hash(report_payload),
    )


FIVE_AXIS_RUNTIME_BINDING = register_domain_runtime_binding(
    DomainRuntimeBinding(
        domain_pack_id=FIVE_AXIS_DOMAIN_PACK.domain_pack_id,
        parse_request=_parse_binding_request,
        evaluate=evaluate_five_axis_f0,
    )
)
