from __future__ import annotations

import pytest
from pydantic import ValidationError

from axiom.five_axis.f3_models import ArtifactDescriptor, ExpectedClaim, MotionConstraintProfile, TimeLawDefinition


def _profile_payload() -> dict:
    return {
        "artifactType": "five-axis.motion-constraint-profile",
        "schemaId": "five-axis.motion-constraint-profile@1",
        "schemaVersion": 1,
        "profileId": "five-axis.motion-constraint.demo@1",
        "machineProfileId": "five-axis.machine-profile.demo@1",
        "machineProfileContentId": "a" * 64,
        "axisConstraints": [
            {
                "axisId": "axis.x",
                "unit": "mm",
                "maximumVelocity": 10.0,
                "maximumAcceleration": 20.0,
                "maximumJerk": 30.0,
            }
        ],
        "startBoundary": {"sigmaVelocity": 0.0, "sigmaAcceleration": 0.0},
        "endBoundary": {"sigmaVelocity": 0.0, "sigmaAcceleration": 0.0},
        "nodeConstraints": [{"nodeId": "node.1", "sigma": 0.5, "boundaryMode": "allow-continuous"}],
        "policyIds": ["five-axis.motion-constraint-profile.strict@1"],
        "provenance": [],
    }


def test_motion_constraint_profile_requires_paired_path_velocity_fields() -> None:
    payload = _profile_payload()
    payload["pathVelocityUnit"] = "dimensionless/s"

    with pytest.raises(ValidationError, match="pathVelocityUnit requires maximumPathVelocity"):
        MotionConstraintProfile.model_validate(payload)


def test_time_law_definition_rejects_nonzero_dwell_peaks() -> None:
    with pytest.raises(ValidationError, match="dwell laws must have zero peak sigma derivatives"):
        TimeLawDefinition.model_validate(
            {
                "lawKind": "dwell",
                "durationSeconds": 0.25,
                "peakSigmaVelocity": 1.0,
                "peakSigmaAcceleration": 0.0,
                "peakSigmaJerk": 0.0,
            }
        )


def test_expected_claim_supported_whitelist_rejects_non_f3_positive_claim() -> None:
    with pytest.raises(ValidationError, match="F3MathStageManifest Supported claims must use the F3 M4/M5 whitelist IDs"):
        ExpectedClaim.model_validate(
            {
                "claimId": "five-axis.device-safe-claim@1",
                "claimClass": "DeviceSafe",
                "expectedStatus": "Supported",
            }
        )


def test_motion_constraint_profile_dwell_requires_seconds() -> None:
    payload = _profile_payload()
    payload["nodeConstraints"] = [{"nodeId": "node.1", "sigma": 0.5, "boundaryMode": "dwell"}]

    with pytest.raises(ValidationError, match="dwell boundaryMode requires dwellSeconds"):
        MotionConstraintProfile.model_validate(payload)


@pytest.mark.parametrize(
    ("artifact_type", "schema_id"),
    (
        ("five-axis.m5-sampled-trajectory", "five-axis.m5-sampled-trajectory@1"),
        ("five-axis.m5-discrete-command", "five-axis.m5-discrete-command@1"),
    ),
)
def test_artifact_descriptor_accepts_both_f3_m5_contract_variants(artifact_type: str, schema_id: str) -> None:
    descriptor = ArtifactDescriptor.model_validate(
        {
            "stage": "M5",
            "artifactType": artifact_type,
            "schemaId": schema_id,
        }
    )

    assert descriptor.artifact_type == artifact_type
    assert descriptor.schema_id == schema_id


def test_artifact_descriptor_rejects_mismatched_f3_m5_contract_pair() -> None:
    with pytest.raises(ValidationError, match="ArtifactDescriptor must use the frozen F3 artifact/schema mapping"):
        ArtifactDescriptor.model_validate(
            {
                "stage": "M5",
                "artifactType": "five-axis.m5-discrete-command",
                "schemaId": "five-axis.m5-sampled-trajectory@1",
            }
        )
