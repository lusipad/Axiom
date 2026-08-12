from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..models import AxiomModel, EvaluationCase, _require_json_number

_HASH_PATTERN = r"^[0-9a-f]{64}$"
_FROZEN_F4_CLAIM_IDS = frozenset(
    {
        "five-axis.geometry-valid-claim@1",
        "five-axis.task-geometry-collision-free-claim@1",
        "five-axis.kinematically-feasible-claim@1",
        "five-axis.configuration-collision-free-claim@1",
        "five-axis.continuously-feasible-claim@1",
        "five-axis.interval-certified-claim@1",
        "five-axis.model-collision-free-claim@1",
    }
)


def _validate_aware_rfc3339(value: str, *, field_name: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include an explicit UTC offset")
    return value


class CaptureReceipt(AxiomModel):
    receipt_id: str = Field(alias="receiptId", min_length=1)
    source_id: Literal["axiom.windows-file-telemetry-source@1"] = Field(alias="sourceId")
    operation: Literal["file-import"]
    transport: Literal["windows-file-json"]
    captured_at: str = Field(alias="capturedAt", min_length=1)
    trace_content_hash: str = Field(alias="traceContentHash", pattern=_HASH_PATTERN)

    @field_validator("captured_at")
    @classmethod
    def require_aware_timestamp(cls, value: str) -> str:
        return _validate_aware_rfc3339(value, field_name="capturedAt")


class DeviceIdentity(AxiomModel):
    device_id: str = Field(alias="deviceId", min_length=1)
    controller_family: str = Field(alias="controllerFamily", min_length=1)
    machine_model: str = Field(alias="machineModel", min_length=1)


class TelemetrySample(AxiomModel):
    channel_id: str = Field(alias="channelId", min_length=1)
    value: float | str | tuple[float, ...]
    unit: str | None = None
    quality: Literal["good", "suspect", "bad"] | None = None

    @field_validator("value", mode="before")
    @classmethod
    def reject_non_json_numbers(cls, value: Any) -> Any:
        if isinstance(value, bool):
            return _require_json_number(value)
        if isinstance(value, (list, tuple)):
            for item in value:
                _require_json_number(item)
            return tuple(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return _require_json_number(value)
        return value


class TelemetryFrame(AxiomModel):
    sequence_id: int = Field(alias="sequenceId", ge=0)
    device_timestamp: str = Field(alias="deviceTimestamp", min_length=1)
    samples: tuple[TelemetrySample, ...] = Field(min_length=1)
    alarms: tuple[str, ...] = ()

    @field_validator("device_timestamp")
    @classmethod
    def require_aware_rfc3339_timestamp(cls, value: str) -> str:
        return _validate_aware_rfc3339(value, field_name="deviceTimestamp")


class MachineTelemetryTrace(AxiomModel):
    artifact_type: Literal["machine.telemetry-trace"] = Field(alias="artifactType")
    schema_version: Literal[1] = Field(alias="schemaVersion")
    trace_id: str = Field(alias="traceId", min_length=1)
    source_kind: Literal["synthetic-replay", "controller-export", "device-read"] = Field(alias="sourceKind")
    capture_receipt: CaptureReceipt = Field(alias="captureReceipt")
    device_identity: DeviceIdentity = Field(alias="deviceIdentity")
    frames: tuple[TelemetryFrame, ...] = Field(min_length=1)
    vendor_metadata: dict[str, Any] = Field(default_factory=dict, alias="vendorMetadata")


class DeviceChannel(AxiomModel):
    channel_id: str = Field(alias="channelId", min_length=1)
    kind: Literal["position-vector", "scalar", "state", "alarm"]
    unit: str | None = None
    coordinate_frame: str | None = Field(default=None, alias="coordinateFrame")

    @model_validator(mode="after")
    def require_unit_for_numeric_channels(self) -> DeviceChannel:
        if self.kind in {"position-vector", "scalar"} and self.unit is None:
            raise ValueError("position-vector and scalar channels must declare unit")
        return self


class DeviceProfile(AxiomModel):
    profile_id: str = Field(alias="profileId", pattern=r"^.+@[0-9]+$")
    device_id: str = Field(alias="deviceId", min_length=1)
    manufacturer: str = Field(min_length=1)
    machine_model: str = Field(alias="machineModel", min_length=1)
    controller_family: str = Field(alias="controllerFamily", min_length=1)
    firmware_version: str | None = Field(default=None, alias="firmwareVersion", min_length=1)
    export_version: str = Field(alias="exportVersion", min_length=1)
    allowed_read_only_operations: tuple[Literal["file-import"], ...] = Field(
        alias="allowedReadOnlyOperations", min_length=1
    )
    calibration_id: str | None = Field(default=None, alias="calibrationId", pattern=r"^.+@[0-9]+$")
    channels: tuple[DeviceChannel, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def freeze_v1_read_only_operations(self) -> DeviceProfile:
        if self.allowed_read_only_operations != ("file-import",):
            raise ValueError("R3 v1 deviceProfile allows only file-import exactly once")
        return self


class ClockMapping(AxiomModel):
    mapping_id: str = Field(alias="mappingId", pattern=r"^.+@[0-9]+$")
    device_id: str = Field(alias="deviceId", min_length=1)
    mapping_method: Literal["fixed-offset", "synchronized-export", "vendor-declared"] = Field(
        alias="mappingMethod"
    )
    device_reference_timestamp: str = Field(alias="deviceReferenceTimestamp", min_length=1)
    host_reference_timestamp: str = Field(alias="hostReferenceTimestamp", min_length=1)
    offset_milliseconds: float = Field(alias="offsetMilliseconds")
    drift_bound_milliseconds: float = Field(default=0.0, alias="driftBoundMilliseconds", ge=0)

    @field_validator("offset_milliseconds", "drift_bound_milliseconds", mode="before")
    @classmethod
    def reject_non_json_float(cls, value: Any) -> Any:
        return _require_json_number(value)

    @field_validator("device_reference_timestamp", "host_reference_timestamp")
    @classmethod
    def require_aware_reference_timestamps(cls, value: str, info: Any) -> str:
        return _validate_aware_rfc3339(value, field_name=info.field_name)


class CoordinateAlignment(AxiomModel):
    alignment_id: str = Field(alias="alignmentId", pattern=r"^.+@[0-9]+$")
    device_id: str = Field(alias="deviceId", min_length=1)
    machine_coordinate_frame: str = Field(alias="machineCoordinateFrame", min_length=1)
    work_coordinate_frame: str = Field(alias="workCoordinateFrame", min_length=1)
    source_kind: Literal["calibration-record", "vendor-declared", "synthetic-reference"] = Field(
        alias="sourceKind"
    )
    effective_at: str = Field(alias="effectiveAt", min_length=1)
    calibration_status: Literal["calibrated", "estimated"] = Field(alias="calibrationStatus")
    calibration_id: str | None = Field(default=None, alias="calibrationId", pattern=r"^.+@[0-9]+$")
    channel_ids: tuple[str, ...] = Field(alias="channelIds", min_length=1)

    @field_validator("effective_at")
    @classmethod
    def require_aware_effective_timestamp(cls, value: str) -> str:
        return _validate_aware_rfc3339(value, field_name="effectiveAt")

    @model_validator(mode="after")
    def require_calibration_id_for_calibrated_alignment(self) -> CoordinateAlignment:
        if self.calibration_status == "calibrated" and self.calibration_id is None:
            raise ValueError("calibrated coordinateAlignment requires calibrationId")
        return self


class UpstreamClaimReference(AxiomModel):
    claim_definition_id: str = Field(alias="claimDefinitionId", min_length=1)
    status: Literal["Supported", "Refuted", "Inconclusive"]
    report_content_hash: str | None = Field(default=None, alias="reportContentHash", pattern=_HASH_PATTERN)


class MachineRunLineage(AxiomModel):
    machine_run_id: str = Field(alias="machineRunId", min_length=1)
    pairing_status: Literal["paired", "unpaired"] = Field(alias="pairingStatus")
    baseline_kind: Literal["reference", "benchmark"] | None = Field(default=None, alias="baselineKind")
    baseline_run_bundle_hash: str | None = Field(default=None, alias="baselineRunBundleHash", pattern=_HASH_PATTERN)
    source_command_content_hash: str | None = Field(
        default=None, alias="sourceCommandContentHash", pattern=_HASH_PATTERN
    )
    upstream_claims: tuple[UpstreamClaimReference, ...] = Field(default_factory=tuple, alias="upstreamClaims")

    @model_validator(mode="after")
    def validate_pairing_contract(self) -> MachineRunLineage:
        if self.pairing_status == "unpaired":
            if (
                self.baseline_kind is not None
                or self.baseline_run_bundle_hash is not None
                or self.source_command_content_hash is not None
                or self.upstream_claims
            ):
                raise ValueError("unpaired lineage must not carry baseline bindings or upstream claims")
            return self

        if self.baseline_kind is None or self.baseline_run_bundle_hash is None or self.source_command_content_hash is None:
            raise ValueError("paired lineage requires baselineKind, baselineRunBundleHash and sourceCommandContentHash")
        observed_ids = {claim.claim_definition_id for claim in self.upstream_claims}
        if observed_ids != _FROZEN_F4_CLAIM_IDS or len(self.upstream_claims) != len(_FROZEN_F4_CLAIM_IDS):
            raise ValueError("paired lineage requires the seven frozen F4 claims exactly once")
        if any(claim.status != "Supported" for claim in self.upstream_claims):
            raise ValueError("paired lineage requires every upstream F4 claim to be Supported")
        return self


class MachineObservationRequest(AxiomModel):
    artifact: MachineTelemetryTrace
    device_profile: DeviceProfile = Field(alias="deviceProfile")
    clock_mapping: ClockMapping | None = Field(default=None, alias="clockMapping")
    coordinate_alignment: CoordinateAlignment | None = Field(default=None, alias="coordinateAlignment")
    lineage: MachineRunLineage
    case: EvaluationCase

    @model_validator(mode="after")
    def validate_cross_object_contract(self) -> MachineObservationRequest:
        artifact_device_id = self.artifact.device_identity.device_id
        profile = self.device_profile
        if artifact_device_id != profile.device_id:
            raise ValueError("artifact.deviceIdentity.deviceId must match deviceProfile.deviceId")
        if self.artifact.device_identity.controller_family != profile.controller_family:
            raise ValueError("artifact.deviceIdentity.controllerFamily must match deviceProfile.controllerFamily")
        if self.artifact.device_identity.machine_model != profile.machine_model:
            raise ValueError("artifact.deviceIdentity.machineModel must match deviceProfile.machineModel")
        if self.artifact.capture_receipt.operation not in profile.allowed_read_only_operations:
            raise ValueError("artifact.captureReceipt.operation must be allowed by deviceProfile")

        channels = {channel.channel_id: channel for channel in profile.channels}
        for frame in self.artifact.frames:
            for sample in frame.samples:
                channel = channels.get(sample.channel_id)
                if channel is None:
                    raise ValueError(f"sample channelId is not declared by deviceProfile: {sample.channel_id}")
                if isinstance(sample.value, (float, int, tuple)) and sample.unit is None:
                    raise ValueError(f"numeric sample requires unit for channelId={sample.channel_id}")
                if channel.unit is not None:
                    if sample.unit is None:
                        raise ValueError(f"sample unit is required by deviceProfile for channelId={sample.channel_id}")
                    if sample.unit != channel.unit:
                        raise ValueError(f"sample unit does not match deviceProfile for channelId={sample.channel_id}")
                if channel.kind == "position-vector" and sample.unit is None:
                    raise ValueError(f"position-vector sample requires a unit for channelId={sample.channel_id}")

        if self.clock_mapping is not None and self.clock_mapping.device_id != artifact_device_id:
            raise ValueError("clockMapping.deviceId must match artifact.deviceIdentity.deviceId")

        if self.coordinate_alignment is not None:
            if self.coordinate_alignment.device_id != artifact_device_id:
                raise ValueError("coordinateAlignment.deviceId must match artifact.deviceIdentity.deviceId")
            unknown_channels = set(self.coordinate_alignment.channel_ids) - set(channels)
            if unknown_channels:
                raise ValueError("coordinateAlignment.channelIds must be declared by deviceProfile")
            if self.coordinate_alignment.calibration_id is not None and self.coordinate_alignment.calibration_id != profile.calibration_id:
                raise ValueError("coordinateAlignment.calibrationId must match deviceProfile.calibrationId")
        return self


class LoadedMachineTelemetryCapture(AxiomModel):
    artifact: MachineTelemetryTrace
    source_file_path: str = Field(alias="sourceFilePath")
    source_file_hash: str = Field(alias="sourceFileHash", pattern=_HASH_PATTERN)
    source_byte_length: int = Field(alias="sourceByteLength", ge=0)

    @classmethod
    def from_loaded_file(
        cls,
        *,
        artifact: MachineTelemetryTrace,
        path: Path,
        source_file_hash: str,
        source_byte_length: int,
    ) -> LoadedMachineTelemetryCapture:
        return cls(
            artifact=artifact,
            sourceFilePath=str(path),
            sourceFileHash=source_file_hash,
            sourceByteLength=source_byte_length,
        )


__all__ = [
    "CaptureReceipt",
    "ClockMapping",
    "CoordinateAlignment",
    "DeviceChannel",
    "DeviceIdentity",
    "DeviceProfile",
    "LoadedMachineTelemetryCapture",
    "MachineObservationRequest",
    "MachineRunLineage",
    "MachineTelemetryTrace",
    "TelemetryFrame",
    "TelemetrySample",
    "UpstreamClaimReference",
]
