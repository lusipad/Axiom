from __future__ import annotations

import json
import platform
from importlib.resources import files
from typing import Any

from ..physical import (
    build_r4_multirate_physical_model,
    evaluate_canonical_parameter_point,
    physical_model_content_hash,
)
from .models import canonical_hash
from .r5c_models import (
    ConditionalEffectDatasetV2,
    ConditionalEffectModelBundleV2,
    ConditionalEffectParityReceiptV2,
    ConditionalEffectPartition,
    ConditionalEffectSplitManifestV2,
    ConditionalEffectTrainingReceiptV2,
)
from .r5c_training import train_r5c_bundle
from .r5d_models import R5DExperimentPlanRequest, SimulationExperimentPlan
from .r5d_planning import (
    build_r5d_experiment_plan_request,
    plan_r5d_simulation_experiments,
)
from .r5e_models import (
    R5E_APPROVAL_POLICY_ID,
    R5E_CANDIDATE_GATE_POLICY_ID,
    R5E_RUNNER_ID,
    R5E_SAFETY_BANNER,
    ConditionalEffectMetricDelta,
    R5EApprovalRequirements,
    R5EExamplePayload,
    R5EManifest,
    R5EModelCandidateAssessment,
    R5ESyntheticCampaignReport,
    R5ESyntheticCampaignRequest,
    SyntheticSimulationAcquisitionReceipt,
    SyntheticSimulationCampaignApproval,
    SyntheticSimulationExperimentResult,
)


def _feed_code(value: float) -> str:
    return f"{round(value * 1000):04d}"


def _period_code(value: float) -> str:
    return f"{round(value * 1000):03d}ms"


def _experiment_suffix(experiment_id: str) -> str:
    return experiment_id.split("@", 1)[0].split("r5d.", 1)[-1]


def _seal(model_type: type[Any], payload: dict[str, Any]) -> Any:
    payload["contentHash"] = canonical_hash(payload)
    return model_type.model_validate(payload)


def build_r5e_manifest() -> R5EManifest:
    return R5EManifest(
        manifestId="axiom.intelligence.r5e-manifest@1",
        schemaId="axiom.intelligence.r5e-manifest@1",
        schemaVersion=1,
        stage="R5-E",
        platform="windows",
        runnerId=R5E_RUNNER_ID,
        approvalPolicyId=R5E_APPROVAL_POLICY_ID,
        fixedBatchSize=5,
        baseSampleCount=25,
        acquiredSampleCount=5,
        candidateSampleCount=30,
        validationAndTestFrozen=True,
        automaticModelPromotionAllowed=False,
        realWorldGeneralizationStatus="Open",
        permissionLevel="Offline",
        automaticExecutionAllowed=False,
        deviceWriteAllowed=False,
        safetyBanner=R5E_SAFETY_BANNER,
    )


def r5e_example_payload() -> R5EExamplePayload:
    plan_request = build_r5d_experiment_plan_request(batch_size=5)
    plan = plan_r5d_simulation_experiments(plan_request, current_platform="Windows")
    return R5EExamplePayload(
        manifest=build_r5e_manifest(),
        planRequest=plan_request,
        plan=plan,
        approvalRequirements=R5EApprovalRequirements(
            approvalRequired=True,
            accountablePartyRequired=True,
            fullBatchOnly=True,
            syntheticOnlyAcknowledgementRequired=True,
            deviceAuthorityGranted=False,
        ),
    )


def build_r5e_campaign_request(
    *,
    accountable_party_id: str,
    plan_request: R5DExperimentPlanRequest | None = None,
    plan: SimulationExperimentPlan | None = None,
) -> R5ESyntheticCampaignRequest:
    source_request = plan_request or build_r5d_experiment_plan_request(batch_size=5)
    source_plan = plan or plan_r5d_simulation_experiments(
        source_request, current_platform="Windows"
    )
    approval = _seal(
        SyntheticSimulationCampaignApproval,
        {
            "schemaId": "axiom.intelligence.synthetic-simulation-campaign-approval@1",
            "approvalId": "axiom.intelligence.r5e.synthetic-campaign-approval@1",
            "approvalPolicyId": R5E_APPROVAL_POLICY_ID,
            "planContentHash": source_plan.content_hash,
            "approvedExperimentIds": [
                proposal.experiment_id for proposal in source_plan.proposals
            ],
            "accountablePartyId": accountable_party_id,
            "approvalMode": "explicit-offline-user-approval",
            "humanApprovalPresent": True,
            "sourceKind": "synthetic-sil",
            "permissionLevel": "Offline",
            "automaticExecutionAllowed": False,
            "deviceWriteAllowed": False,
        },
    )
    return _seal(
        R5ESyntheticCampaignRequest,
        {
            "schemaId": "axiom.intelligence.synthetic-simulation-campaign-request@1",
            "planRequest": source_request.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "plan": source_plan.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "approval": approval.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "executionMode": "local-windows-synthetic-sil",
        },
    )


def _run_proposal(
    physical_model: Any,
    proposal: Any,
) -> tuple[SyntheticSimulationExperimentResult, dict[str, str]]:
    feed_code = _feed_code(proposal.feed_override)
    period_code = _period_code(proposal.sample_period)
    point = evaluate_canonical_parameter_point(
        physical_model,
        feed_override=proposal.feed_override,
        sample_period=proposal.sample_period,
        profile_id=f"five-axis.r5e.motion-profile.feed-{feed_code}@1",
        feed_source="axiom.intelligence.r5e.synthetic-campaign@1",
        trajectory_id=f"five-axis-r5e-feed-{feed_code}",
        invocation_id=f"intelligence-r5e-feed-{feed_code}-period-{period_code}",
        response_trace_id=(
            f"axiom.intelligence.r5e.feed-{feed_code}.period-{period_code}.response@1"
        ),
    )
    statuses = (
        point.continuous_verification.overall_status,
        point.adapter_receipt.status,
        point.interval_verification.status,
        point.collision_verification.status,
    )
    if statuses != ("Supported", "Succeeded", "Supported", "safe"):
        raise ValueError(f"R5-E exact replay failed its mathematical gates: {statuses}")
    result = _seal(
        SyntheticSimulationExperimentResult,
        {
            "resultId": (
                f"axiom.intelligence.r5e.feed-{feed_code}.period-{period_code}.result@1"
            ),
            "rank": proposal.rank,
            "experimentId": proposal.experiment_id,
            "feedOverride": proposal.feed_override,
            "samplePeriod": proposal.sample_period,
            "cycleTimeSeconds": (point.continuous_verification.total_duration_seconds),
            "linearFollowingErrorMaxMm": point.linear_following_error_max_mm,
            "commandSampleCount": len(point.command.samples),
            "m4ContentHash": canonical_hash(point.continuous_trajectory),
            "m5ContentHash": point.command.content_id,
            "physicalResponseContentHash": point.response.content_hash,
            "continuousFeasibilityStatus": "Supported",
            "adapterStatus": "Succeeded",
            "intervalVerificationStatus": "Supported",
            "collisionVerificationStatus": "safe",
            "executionStatus": "Succeeded",
            "sourceKind": "synthetic-sil",
            "deviceWriteAllowed": False,
        },
    )
    return result, dict(point.adapter_receipt.numeric_environment)


def _acquire(
    request: R5ESyntheticCampaignRequest,
) -> SyntheticSimulationAcquisitionReceipt:
    physical_model = build_r4_multirate_physical_model()
    executed = tuple(
        _run_proposal(physical_model, proposal) for proposal in request.plan.proposals
    )
    results = tuple(item[0] for item in executed)
    environments = tuple(item[1] for item in executed)
    if any(environment != environments[0] for environment in environments[1:]):
        raise ValueError("R5-E numeric environment changed inside one campaign")
    return _seal(
        SyntheticSimulationAcquisitionReceipt,
        {
            "schemaId": "axiom.intelligence.synthetic-simulation-acquisition-receipt@1",
            "receiptId": "axiom.intelligence.r5e.synthetic-acquisition@1",
            "campaignRequestHash": request.content_hash,
            "approvalContentHash": request.approval.content_hash,
            "sourcePlanContentHash": request.plan.content_hash,
            "sourceModelBundleHash": request.plan.model_bundle_hash,
            "sourceDatasetContentHash": request.plan.dataset_content_hash,
            "sourceSplitManifestHash": request.plan.split_manifest_content_hash,
            "runnerId": R5E_RUNNER_ID,
            "physicalModelContentHash": physical_model_content_hash(physical_model),
            "executionStatus": "Succeeded",
            "resultCount": 5,
            "results": [
                result.model_dump(mode="json", by_alias=True, exclude_none=True)
                for result in results
            ],
            "numericEnvironment": environments[0],
            "sourceKind": "synthetic-sil",
            "permissionLevel": "Offline",
            "automaticExecutionAllowed": False,
            "deviceWriteAllowed": False,
        },
    )


def _build_dataset(
    request: R5ESyntheticCampaignRequest,
    receipt: SyntheticSimulationAcquisitionReceipt,
) -> ConditionalEffectDatasetV2:
    source = request.plan_request.dataset
    acquired = [
        {
            "sampleId": f"r5e-{_experiment_suffix(result.experiment_id)}",
            "feedOverride": result.feed_override,
            "samplePeriod": result.sample_period,
            "declaredSplitId": "train",
            "cycleTimeSeconds": result.cycle_time_seconds,
            "linearFollowingErrorMaxMm": result.linear_following_error_max_mm,
            "commandSampleCount": result.command_sample_count,
            "m4ContentHash": result.m4_content_hash,
            "m5ContentHash": result.m5_content_hash,
            "physicalResponseContentHash": result.physical_response_content_hash,
            "sourceKind": "synthetic-sil",
            "sourceScenarioId": "canonical-head-table-solver",
        }
        for result in receipt.results
    ]
    payload: dict[str, Any] = {
        "artifactType": "axiom.intelligence.conditional-effect-dataset",
        "schemaId": "axiom.intelligence.conditional-effect-dataset@2",
        "schemaVersion": 2,
        "datasetId": "axiom.intelligence.r5e-canonical-head-table-augmented@2",
        "domain": source.domain.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "governance": source.governance.model_dump(
            mode="json", by_alias=True, exclude_none=True
        ),
        "selectionPolicyId": "axiom.intelligence.r5e-append-train-only-policy@1",
        "lineagePolicyId": "axiom.intelligence.r5e-campaign-lineage@1",
        "sourceKind": "synthetic-sil",
        "knownBiases": list(source.known_biases),
        "coverageGaps": list(source.coverage_gaps),
        "samples": [
            sample.model_dump(mode="json", by_alias=True, exclude_none=True)
            for sample in source.samples
        ]
        + acquired,
        "baseDatasetContentHash": source.content_hash,
        "acquisitionReceiptHash": receipt.content_hash,
    }
    return _seal(ConditionalEffectDatasetV2, payload)


def _build_split_manifest(
    request: R5ESyntheticCampaignRequest,
    receipt: SyntheticSimulationAcquisitionReceipt,
    dataset: ConditionalEffectDatasetV2,
) -> ConditionalEffectSplitManifestV2:
    source = request.plan_request.split_manifest
    acquired_ids = tuple(sample.sample_id for sample in dataset.samples[25:])
    partitions = (
        ConditionalEffectPartition(
            splitId="train",
            sampleIds=source.partitions[0].sample_ids + acquired_ids,
        ),
        source.partitions[1],
        source.partitions[2],
    )
    return _seal(
        ConditionalEffectSplitManifestV2,
        {
            "artifactType": "axiom.intelligence.conditional-effect-split-manifest",
            "schemaId": "axiom.intelligence.conditional-effect-split-manifest@2",
            "schemaVersion": 2,
            "manifestId": "axiom.intelligence.r5e-spatial-split@2",
            "datasetContentHash": dataset.content_hash,
            "partitions": [
                partition.model_dump(mode="json", by_alias=True, exclude_none=True)
                for partition in partitions
            ],
            "baseSplitManifestHash": source.content_hash,
            "acquisitionReceiptHash": receipt.content_hash,
        },
    )


def _metric_deltas(
    baseline: Any,
    candidate: Any,
) -> tuple[ConditionalEffectMetricDelta, ConditionalEffectMetricDelta]:
    deltas = []
    for base, current in zip(
        baseline.head_results, candidate.head_results, strict=True
    ):
        change = current.model_rmse - base.model_rmse
        improvement = 1.0 - current.model_rmse / base.model_rmse
        status = (
            "Improved"
            if change < -1e-15
            else "Regressed"
            if change > 1e-15
            else "Unchanged"
        )
        deltas.append(
            ConditionalEffectMetricDelta(
                targetId=base.target_id,
                unit=base.unit,
                baselineModelRmse=base.model_rmse,
                candidateModelRmse=current.model_rmse,
                absoluteChange=change,
                relativeImprovement=improvement,
                status=status,
            )
        )
    return deltas[0], deltas[1]


def _candidate_assessment(
    request: R5ESyntheticCampaignRequest,
    candidate_bundle: ConditionalEffectModelBundleV2,
    parity: ConditionalEffectParityReceiptV2,
    baseline_evaluation: Any,
    candidate_evaluation: Any,
) -> R5EModelCandidateAssessment:
    deltas = _metric_deltas(baseline_evaluation, candidate_evaluation)
    passed = (
        candidate_evaluation.synthetic_conditional_effect_contract_status == "Passed"
        and parity.status == "Passed"
        and all(item.absolute_change <= 1e-15 for item in deltas)
    )
    return _seal(
        R5EModelCandidateAssessment,
        {
            "assessmentId": "axiom.intelligence.r5e.candidate-assessment@1",
            "policyId": R5E_CANDIDATE_GATE_POLICY_ID,
            "sourceModelBundleHash": request.plan.model_bundle_hash,
            "candidateModelBundleHash": candidate_bundle.content_hash,
            "metricDeltas": [
                item.model_dump(mode="json", by_alias=True, exclude_none=True)
                for item in deltas
            ],
            "candidateGateStatus": "Passed" if passed else "Failed",
            "eligibleForManualPromotion": passed,
            "modelPromotionStatus": "NotPerformed",
            "generalImprovementGuarantee": "NotClaimed",
        },
    )


def execute_r5e_synthetic_campaign(
    request: R5ESyntheticCampaignRequest,
    *,
    current_platform: str | None = None,
) -> R5ESyntheticCampaignReport:
    runtime_platform = current_platform or platform.system()
    if runtime_platform.casefold() != "windows":
        raise ValueError("R5-E synthetic campaign only supports Windows")

    source_bundle, _, _, baseline_evaluation = train_r5c_bundle(
        request.plan_request.dataset,
        request.plan_request.split_manifest,
    )
    if source_bundle.content_hash != request.plan_request.model_bundle.content_hash:
        raise ValueError(
            "R5-E source model cannot be reproduced from its frozen inputs"
        )

    receipt = _acquire(request)
    dataset = _build_dataset(request, receipt)
    split_manifest = _build_split_manifest(request, receipt, dataset)
    bundle, training, parity, candidate_evaluation = train_r5c_bundle(
        dataset,
        split_manifest,
        parent_model_bundle_hash=request.plan.model_bundle_hash,
    )
    if not isinstance(bundle, ConditionalEffectModelBundleV2):
        raise AssertionError("R5-E training must produce a v2 model bundle")
    if not isinstance(training, ConditionalEffectTrainingReceiptV2):
        raise AssertionError("R5-E training must produce a v2 training receipt")
    if not isinstance(parity, ConditionalEffectParityReceiptV2):
        raise AssertionError("R5-E training must produce a v2 parity receipt")
    assessment = _candidate_assessment(
        request,
        bundle,
        parity,
        baseline_evaluation,
        candidate_evaluation,
    )
    next_request = R5DExperimentPlanRequest(
        modelBundle=bundle,
        dataset=dataset,
        splitManifest=split_manifest,
        batchSize=5,
    )
    next_plan = plan_r5d_simulation_experiments(
        next_request, current_platform="Windows"
    )
    return _seal(
        R5ESyntheticCampaignReport,
        {
            "schemaId": "axiom.intelligence.synthetic-simulation-campaign-report@1",
            "reportId": "axiom.intelligence.r5e.synthetic-campaign-report@1",
            "campaignRequest": request.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "acquisitionReceipt": receipt.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "dataset": dataset.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "splitManifest": split_manifest.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "modelBundle": bundle.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "trainingReceipt": training.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "parityReceipt": parity.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "baselineEvaluation": baseline_evaluation.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "candidateEvaluation": candidate_evaluation.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "candidateAssessment": assessment.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "nextPlanRequest": next_request.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "nextPlan": next_plan.model_dump(
                mode="json", by_alias=True, exclude_none=True
            ),
            "campaignExecutionStatus": "Succeeded",
            "modelPromotionStatus": "NotPerformed",
            "realWorldGeneralizationStatus": "Open",
            "permissionLevel": "Offline",
            "automaticExecutionAllowed": False,
            "deviceWriteAllowed": False,
            "safetyBanner": R5E_SAFETY_BANNER,
        },
    )


def load_r5e_fixture_manifest() -> dict[str, Any]:
    resource = files("axiom.intelligence").joinpath("fixtures", "r5e-manifest.json")
    return json.loads(resource.read_text(encoding="utf-8"))


__all__ = [
    "build_r5e_campaign_request",
    "build_r5e_manifest",
    "execute_r5e_synthetic_campaign",
    "load_r5e_fixture_manifest",
    "r5e_example_payload",
]
