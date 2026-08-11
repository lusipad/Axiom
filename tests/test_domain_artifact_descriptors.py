from __future__ import annotations

import pytest

from axiom.domain import ARTIFACT_IMPORT_RUNNER_ID, ArtifactTypeDescriptor, DomainPack, MetricDefinition


def _pack_kwargs() -> dict[str, object]:
    return {
        "domainPackId": "vendor.descriptor-pack@1",
        "evaluatorVersion": "vendor.descriptor-evaluator@1",
        "runnerId": ARTIFACT_IMPORT_RUNNER_ID,
        "runnerIds": [ARTIFACT_IMPORT_RUNNER_ID],
        "metricDefinitions": [
            MetricDefinition(
                metricId="value.count",
                metricDefinitionId="vendor.descriptor.value.count@1",
            )
        ],
        "claimDefinitionIds": ["axiom.core.case-outcome-claim@1"],
        "comparisonPolicyIds": [],
    }


def test_legacy_artifact_type_fields_expand_to_run_input_descriptors():
    pack = DomainPack(
        artifactType="scalar-sample",
        artifactSchemaVersions=[1, 2],
        **_pack_kwargs(),
    )

    assert pack.artifact_type == "scalar-sample"
    assert pack.artifact_schema_versions == (1, 2)
    assert pack.artifact_type_descriptors == (
        ArtifactTypeDescriptor(artifactType="scalar-sample", schemaVersion=1, role="run-input"),
        ArtifactTypeDescriptor(artifactType="scalar-sample", schemaVersion=2, role="run-input"),
    )
    assert pack.model_dump(mode="json", by_alias=True)["artifactType"] == "scalar-sample"


def test_descriptor_only_pack_derives_legacy_default_descriptor_without_hiding_other_run_input_types():
    pack = DomainPack(
        artifactTypeDescriptors=[
            {"artifactType": "scalar-sample", "schemaVersion": 1, "role": "run-input"},
            {"artifactType": "vector-sample", "schemaVersion": 1, "role": "run-input"},
            {"artifactType": "vector-sample", "schemaVersion": 2, "role": "run-input"},
            {"artifactType": "vector-annotation", "schemaVersion": 1, "role": "reference"},
        ],
        **_pack_kwargs(),
    )

    assert pack.artifact_type == "scalar-sample"
    assert pack.artifact_schema_versions == (1,)
    assert pack.supports_artifact("scalar-sample", 1, role="run-input")
    assert pack.supports_artifact("vector-sample", 1, role="run-input")
    assert pack.supports_artifact("vector-sample", 2, role="run-input")
    assert not pack.supports_artifact("vector-annotation", 1, role="run-input")


def test_metric_projection_claim_definition_must_be_declared_by_the_pack():
    kwargs = _pack_kwargs()
    kwargs["metricDefinitions"] = [
        MetricDefinition(
            metricId="boolean.pass",
            metricDefinitionId="vendor.descriptor.boolean.pass@1",
            claimDefinitionId="vendor.boolean.pass-claim@1",
            claimPredicate="boolean.pass is true",
        )
    ]
    with pytest.raises(ValueError, match="undeclared claimDefinitionIds"):
        DomainPack(
            artifactType="scalar-sample",
            artifactSchemaVersions=[1],
            **kwargs,
        )


@pytest.mark.parametrize(
    "metric_kwargs",
    [
        {"claimDefinitionId": "vendor.boolean.pass-claim@1"},
        {"claimPredicate": "boolean.pass is true"},
    ],
)
def test_metric_projection_requires_claim_id_and_predicate_together(metric_kwargs: dict[str, str]):
    with pytest.raises(ValueError, match="must be declared together"):
        MetricDefinition(
            metricId="boolean.pass",
            metricDefinitionId="vendor.descriptor.boolean.pass@1",
            **metric_kwargs,
        )


def test_artifact_descriptor_rejects_unknown_roles():
    with pytest.raises(ValueError):
        ArtifactTypeDescriptor(
            artifactType="scalar-sample",
            schemaVersion=1,
            role="implicit",
        )
