"""Multi-vendor CNC controller profiles and canonical physical control quantities.

Decouples the grey-box trajectory/servo mechanics from any single CNC vendor's parameter
naming, unit system, parameter count, or supported filter topology:

1. `CanonicalControlQuantities`: vendor-neutral physical quantities in canonical units
   (`mm`, `deg`, `mm/s`, `mm/s^2`, `mm/s^3`, `s`, `Hz`, `1/s`, `ratio`).
2. `ControllerCapabilities`: explicit feature flags declaring which planning/filtering/servo
   mechanisms a given CNC controller actually implements (for example, whether a post-interp
   biquad low-pass or drive notch filter exists).
3. `ControllerParameterBinding`: declarative mapping between a vendor parameter in
   `CncParameterRegistry` and one or more canonical slots, including unit conversion
   (`linear` or `reciprocal_2pi`) and commissioning tunability (`nc-tunable`, `drive-side`,
   `read-only`).
4. Built-in profiles:
   - `generic-fir-biquad@1`: 32-parameter reference planner + FIR/biquad + P-P servo profile.
   - `beckhoff-twincat-nc@1`: 16-parameter Beckhoff TwinCAT NC I / PTP profile (`um`,
     `m/min`, `(m/min)/mm`, `%`, `s`).
   - `siemens-sinumerik-840d@1`: 15-parameter Siemens SINUMERIK 840D sl (`CYCLE832` + `MD32xxx`)
     profile without a separate biquad command low-pass (`hasCommandLowpass=False`).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from pydantic import Field, model_validator

from .models import AxiomModel
from .parameter_space import (
    CncParameterRegistry,
    DerivedFeatureDefinition,
    ParameterDefinition,
    SourceKind,
    compute_registry_content_hash,
    default_cnc_parameter_registry,
    default_parameter_values,
    verify_registry_content_hash,
)

CanonicalSlotId = Literal[
    "corner_tolerance_mm",
    "small_seg_chord_tol_mm",
    "lookahead_block_count",
    "corner_angle_threshold_deg",
    "collinear_merge_angle_deg",
    "curvature_speed_clamp_factor",
    "min_segment_length_mm",
    "spline_degree",
    "feed_override_ratio",
    "path_tangential_acc_mm_s2",
    "path_tangential_jerk_mm_s3",
    "centripetal_acc_limit_mm_s2",
    "axis_vel_limit_x_mm_s",
    "axis_vel_limit_y_mm_s",
    "axis_vel_limit_z_mm_s",
    "axis_acc_limit_x_mm_s2",
    "axis_acc_limit_y_mm_s2",
    "axis_acc_limit_z_mm_s2",
    "fir_time_s",
    "lowpass_cutoff_hz",
    "bell_acc_shape_factor",
    "servo_kp_x_1_s",
    "servo_kp_y_1_s",
    "servo_kp_z_1_s",
    "vel_feedforward_x_ratio",
    "vel_feedforward_y_ratio",
    "vel_feedforward_z_ratio",
    "acc_feedforward_x_ratio",
    "acc_feedforward_y_ratio",
    "acc_feedforward_z_ratio",
    "friction_comp_amp_x_mm",
    "friction_comp_amp_y_mm",
    "notch_freq_hz",
]

ParameterTunability = Literal["nc-tunable", "drive-side", "read-only"]
UnitTransformKind = Literal["linear", "reciprocal_2pi"]

DEFAULT_CANONICAL_SLOT_VALUES: dict[CanonicalSlotId, float] = {
    "corner_tolerance_mm": 0.020,
    "small_seg_chord_tol_mm": 0.005,
    "lookahead_block_count": 160.0,
    "corner_angle_threshold_deg": 10.0,
    "collinear_merge_angle_deg": 0.25,
    "curvature_speed_clamp_factor": 0.90,
    "min_segment_length_mm": 0.005,
    "spline_degree": 3.0,
    "feed_override_ratio": 1.00,
    "path_tangential_acc_mm_s2": 5000.0,
    "path_tangential_jerk_mm_s3": 200000.0,
    "centripetal_acc_limit_mm_s2": 3000.0,
    "axis_vel_limit_x_mm_s": 500.0,
    "axis_vel_limit_y_mm_s": 500.0,
    "axis_vel_limit_z_mm_s": 400.0,
    "axis_acc_limit_x_mm_s2": 5000.0,
    "axis_acc_limit_y_mm_s2": 5000.0,
    "axis_acc_limit_z_mm_s2": 4000.0,
    "fir_time_s": 0.012,
    "lowpass_cutoff_hz": 80.0,
    "bell_acc_shape_factor": 0.50,
    "servo_kp_x_1_s": 60.0,
    "servo_kp_y_1_s": 60.0,
    "servo_kp_z_1_s": 55.0,
    "vel_feedforward_x_ratio": 0.98,
    "vel_feedforward_y_ratio": 0.98,
    "vel_feedforward_z_ratio": 0.95,
    "acc_feedforward_x_ratio": 0.70,
    "acc_feedforward_y_ratio": 0.70,
    "acc_feedforward_z_ratio": 0.70,
    "friction_comp_amp_x_mm": 0.005,
    "friction_comp_amp_y_mm": 0.005,
    "notch_freq_hz": 180.0,
}


def _canonical_hash(payload: AxiomModel | Mapping[str, Any]) -> str:
    data = (
        payload.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(payload, AxiomModel)
        else dict(payload)
    )
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CanonicalControlQuantities:
    """Vendor-neutral physical control quantities consumed by modular grey-box mechanisms."""

    corner_tolerance_mm: float = 0.020
    small_seg_chord_tol_mm: float = 0.005
    lookahead_block_count: float = 160.0
    corner_angle_threshold_deg: float = 10.0
    collinear_merge_angle_deg: float = 0.25
    curvature_speed_clamp_factor: float = 0.90
    min_segment_length_mm: float = 0.005
    spline_degree: int = 3
    feed_override_ratio: float = 1.00
    path_tangential_acc_mm_s2: float = 5000.0
    path_tangential_jerk_mm_s3: float = 200000.0
    centripetal_acc_limit_mm_s2: float = 3000.0
    axis_vel_limit_mm_s: tuple[float, float, float] = (500.0, 500.0, 400.0)
    axis_acc_limit_mm_s2: tuple[float, float, float] = (5000.0, 5000.0, 4000.0)
    fir_time_s: float = 0.012
    lowpass_cutoff_hz: float | None = 80.0
    bell_acc_shape_factor: float = 0.50
    servo_kp_1_s: tuple[float, float, float] = (60.0, 60.0, 55.0)
    vel_feedforward_ratio: tuple[float, float, float] = (0.98, 0.98, 0.95)
    acc_feedforward_ratio: tuple[float, float, float] = (0.70, 0.70, 0.70)
    friction_comp_amp_mm: tuple[float, float] = (0.005, 0.005)
    notch_freq_hz: float | None = 180.0


class ControllerCapabilities(AxiomModel):
    """Explicit topology flags for the CNC controller's trajectory and servo architecture."""

    has_corner_blending: bool = Field(default=True, alias="hasCornerBlending")
    has_micro_spline: bool = Field(default=True, alias="hasMicroSpline")
    has_fir_filter: bool = Field(default=True, alias="hasFirFilter")
    has_command_lowpass: bool = Field(default=True, alias="hasCommandLowpass")
    has_bell_jerk_shaping: bool = Field(default=True, alias="hasBellJerkShaping")
    has_velocity_feedforward: bool = Field(default=True, alias="hasVelocityFeedforward")
    has_acceleration_feedforward: bool = Field(default=True, alias="hasAccelerationFeedforward")
    has_friction_compensation: bool = Field(default=True, alias="hasFrictionCompensation")
    has_drive_notch_filter: bool = Field(default=True, alias="hasDriveNotchFilter")


class ControllerParameterBinding(AxiomModel):
    """Maps one vendor parameter ID in `registry` to one or more canonical physical slots."""

    vendor_parameter_id: str = Field(alias="vendorParameterId", min_length=1, max_length=200)
    canonical_targets: tuple[CanonicalSlotId, ...] = Field(alias="canonicalTargets", min_length=1)
    transform: UnitTransformKind = "linear"
    scale: float = Field(default=1.0, gt=0.0)
    offset: float = 0.0
    tunability: ParameterTunability = "nc-tunable"

    def to_canonical_scalar(self, vendor_value: float) -> float:
        v = float(vendor_value)
        if self.transform == "reciprocal_2pi":
            tau_s = max(v * self.scale + self.offset, 1e-6)
            return 1.0 / (2.0 * math.pi * tau_s)
        return v * self.scale + self.offset

    def from_canonical_scalar(self, canonical_value: float) -> float:
        c = float(canonical_value)
        if self.transform == "reciprocal_2pi":
            f_hz = max(c, 1e-3)
            tau_s = 1.0 / (2.0 * math.pi * f_hz)
            return (tau_s - self.offset) / self.scale
        return (c - self.offset) / self.scale


class ControllerProfile(AxiomModel):
    """Complete multi-vendor CNC controller profile (registry + capabilities + canonical bindings)."""

    schema_id: Literal["axiom.cnc-controller-profile@1"] = Field(
        default="axiom.cnc-controller-profile@1", alias="schemaId"
    )
    profile_id: str = Field(alias="profileId", min_length=1, max_length=200)
    vendor_name: str = Field(alias="vendorName", min_length=1, max_length=120)
    controller_family: str = Field(alias="controllerFamily", min_length=1, max_length=200)
    registry: CncParameterRegistry
    capabilities: ControllerCapabilities = Field(default_factory=ControllerCapabilities)
    bindings: tuple[ControllerParameterBinding, ...] = Field(min_length=1)
    fixed_canonical_defaults: dict[CanonicalSlotId, float] = Field(
        default_factory=dict, alias="fixedCanonicalDefaults"
    )
    profile_content_hash: str = Field(alias="profileContentHash")

    @model_validator(mode="after")
    def validate_bindings(self) -> ControllerProfile:
        verify_registry_content_hash(self.registry)
        reg_ids = {p.parameter_id for p in self.registry.parameters}
        seen_vendor: set[str] = set()
        for b in self.bindings:
            if b.vendor_parameter_id not in reg_ids:
                raise ValueError(
                    f"profile {self.profile_id} binding references unknown vendorParameterId "
                    f"{b.vendor_parameter_id} (not in registry {self.registry.registry_id})"
                )
            if b.vendor_parameter_id in seen_vendor:
                raise ValueError(f"duplicate binding for vendorParameterId {b.vendor_parameter_id}")
            seen_vendor.add(b.vendor_parameter_id)
        return self

    def parameter_id_for_slot(
        self,
        slot: CanonicalSlotId,
        *,
        require_tunable: bool = False,
        include_drive_side: bool = True,
    ) -> str | None:
        """Return the vendor parameter ID bound to `slot`, optionally filtered by tunability."""
        allowed = {"nc-tunable", "drive-side"} if include_drive_side else {"nc-tunable"}
        for b in self.bindings:
            if slot in b.canonical_targets:
                if require_tunable and b.tunability not in allowed:
                    continue
                return b.vendor_parameter_id
        return None

    def tunable_parameter_ids(self, *, include_drive_side: bool = True) -> frozenset[str]:
        """Vendor parameter IDs allowed to be adjusted during commissioning recommendations."""
        allowed = {"nc-tunable", "drive-side"} if include_drive_side else {"nc-tunable"}
        bound_map = {b.vendor_parameter_id: b.tunability for b in self.bindings}
        result: set[str] = set()
        for p in self.registry.parameters:
            tun = bound_map.get(p.parameter_id, "nc-tunable")
            if tun in allowed:
                result.add(p.parameter_id)
        return frozenset(result)

    def to_canonical(self, vendor_parameters: Mapping[str, float] | None = None) -> CanonicalControlQuantities:
        """Translate vendor parameter values into `CanonicalControlQuantities`."""
        slots: dict[CanonicalSlotId, float] = dict(DEFAULT_CANONICAL_SLOT_VALUES)
        slots.update(self.fixed_canonical_defaults)

        param_map = {p.parameter_id: p for p in self.registry.parameters}
        src = vendor_parameters or {}
        if src:
            unknown = sorted(set(src) - set(param_map))
            if unknown:
                raise ValueError(
                    f"parameters contain IDs not in controller profile {self.profile_id} "
                    f"({self.registry.registry_id}): {', '.join(unknown[:6])}"
                )
        for b in self.bindings:
            p_def = param_map[b.vendor_parameter_id]
            raw_v = float(src.get(b.vendor_parameter_id, p_def.default_value))
            can_v = b.to_canonical_scalar(raw_v)
            for target_slot in b.canonical_targets:
                slots[target_slot] = can_v

        caps = self.capabilities
        eps_cor = max(1e-5, slots["corner_tolerance_mm"]) if caps.has_corner_blending else 1e-5
        eps_chord = max(1e-5, slots["small_seg_chord_tol_mm"]) if caps.has_micro_spline else 1e-5
        fir_s = max(0.0, slots["fir_time_s"]) if caps.has_fir_filter else 0.0
        lp_hz: float | None = (
            max(2.0, slots["lowpass_cutoff_hz"]) if caps.has_command_lowpass else None
        )
        beta_bell = (
            max(0.0, min(1.0, slots["bell_acc_shape_factor"]))
            if caps.has_bell_jerk_shaping
            else 0.0
        )
        vff = (
            (
                slots["vel_feedforward_x_ratio"],
                slots["vel_feedforward_y_ratio"],
                slots["vel_feedforward_z_ratio"],
            )
            if caps.has_velocity_feedforward
            else (0.0, 0.0, 0.0)
        )
        aff = (
            (
                slots["acc_feedforward_x_ratio"],
                slots["acc_feedforward_y_ratio"],
                slots["acc_feedforward_z_ratio"],
            )
            if caps.has_acceleration_feedforward
            else (0.0, 0.0, 0.0)
        )
        fric = (
            (
                max(0.0, slots["friction_comp_amp_x_mm"]),
                max(0.0, slots["friction_comp_amp_y_mm"]),
            )
            if caps.has_friction_compensation
            else (0.0, 0.0)
        )
        notch_hz: float | None = (
            max(10.0, slots["notch_freq_hz"]) if caps.has_drive_notch_filter else None
        )

        return CanonicalControlQuantities(
            corner_tolerance_mm=eps_cor,
            small_seg_chord_tol_mm=eps_chord,
            lookahead_block_count=max(1.0, slots["lookahead_block_count"]),
            corner_angle_threshold_deg=slots["corner_angle_threshold_deg"],
            collinear_merge_angle_deg=slots["collinear_merge_angle_deg"],
            curvature_speed_clamp_factor=max(0.1, slots["curvature_speed_clamp_factor"]),
            min_segment_length_mm=max(1e-4, slots["min_segment_length_mm"]),
            spline_degree=int(round(slots["spline_degree"])),
            feed_override_ratio=max(0.05, slots["feed_override_ratio"]),
            path_tangential_acc_mm_s2=max(50.0, slots["path_tangential_acc_mm_s2"]),
            path_tangential_jerk_mm_s3=max(1000.0, slots["path_tangential_jerk_mm_s3"]),
            centripetal_acc_limit_mm_s2=max(50.0, slots["centripetal_acc_limit_mm_s2"]),
            axis_vel_limit_mm_s=(
                max(10.0, slots["axis_vel_limit_x_mm_s"]),
                max(10.0, slots["axis_vel_limit_y_mm_s"]),
                max(10.0, slots["axis_vel_limit_z_mm_s"]),
            ),
            axis_acc_limit_mm_s2=(
                max(100.0, slots["axis_acc_limit_x_mm_s2"]),
                max(100.0, slots["axis_acc_limit_y_mm_s2"]),
                max(100.0, slots["axis_acc_limit_z_mm_s2"]),
            ),
            fir_time_s=fir_s,
            lowpass_cutoff_hz=lp_hz,
            bell_acc_shape_factor=beta_bell,
            servo_kp_1_s=(
                max(5.0, slots["servo_kp_x_1_s"]),
                max(5.0, slots["servo_kp_y_1_s"]),
                max(5.0, slots["servo_kp_z_1_s"]),
            ),
            vel_feedforward_ratio=vff,
            acc_feedforward_ratio=aff,
            friction_comp_amp_mm=fric,
            notch_freq_hz=notch_hz,
        )

    def from_canonical_value(self, slot: CanonicalSlotId, canonical_value: float) -> tuple[str, float] | None:
        """Convert a canonical target value into `(vendor_parameter_id, clipped_vendor_value)`."""
        param_map = {p.parameter_id: p for p in self.registry.parameters}
        for b in self.bindings:
            if slot in b.canonical_targets:
                p_def = param_map[b.vendor_parameter_id]
                raw = b.from_canonical_scalar(canonical_value)
                lo, hi = float(p_def.bounds[0]), float(p_def.bounds[1])
                clipped = max(lo, min(hi, raw))
                val = float(round(clipped)) if p_def.value_type == "integer" else round(clipped, 6)
                return b.vendor_parameter_id, val
        return None

    def from_canonical_overrides(
        self,
        overrides: Mapping[CanonicalSlotId, float],
        *,
        base_vendor_parameters: Mapping[str, float] | None = None,
        respect_tunability: bool = False,
        include_drive_side: bool = True,
    ) -> dict[str, float]:
        """Build a vendor parameter dict by projecting canonical overrides onto exposed vendor parameters."""
        out = default_parameter_values(self.registry)
        if base_vendor_parameters:
            for k, v in base_vendor_parameters.items():
                if k in out:
                    out[k] = float(v)
        allowed = self.tunable_parameter_ids(include_drive_side=include_drive_side)
        for slot, can_val in overrides.items():
            mapped = self.from_canonical_value(slot, can_val)
            if mapped is not None:
                pid, v_val = mapped
                if (not respect_tunability) or (pid in allowed):
                    out[pid] = v_val
        return out


def compute_controller_profile_hash(profile: ControllerProfile) -> str:
    """Canonical SHA-256 hash of a `ControllerProfile` excluding its own `profileContentHash`."""
    content = profile.model_dump(mode="json", by_alias=True, exclude_none=True)
    content.pop("profileContentHash", None)
    return _canonical_hash(content)


def verify_controller_profile_hash(profile: ControllerProfile) -> None:
    """Raise `ValueError` if `profileContentHash` does not match the profile contents."""
    expected = compute_controller_profile_hash(profile)
    if profile.profile_content_hash != expected:
        raise ValueError(
            f"controller profile {profile.profile_id} declares profileContentHash "
            f"{profile.profile_content_hash[:12]}... but its content hashes to {expected[:12]}..."
        )


def _finalize_profile(profile: ControllerProfile) -> ControllerProfile:
    return profile.model_copy(update={"profile_content_hash": compute_controller_profile_hash(profile)})


def default_generic_controller_profile() -> ControllerProfile:
    """Built-in 32-parameter reference controller profile (`generic-fir-biquad@1`)."""
    reg = default_cnc_parameter_registry()
    bindings = (
        ControllerParameterBinding(vendorParameterId="g1.corner_tolerance_mm", canonicalTargets=("corner_tolerance_mm",)),
        ControllerParameterBinding(vendorParameterId="g1.small_seg_chord_tol_mm", canonicalTargets=("small_seg_chord_tol_mm",)),
        ControllerParameterBinding(vendorParameterId="g1.lookahead_block_count", canonicalTargets=("lookahead_block_count",)),
        ControllerParameterBinding(vendorParameterId="g1.corner_angle_threshold_deg", canonicalTargets=("corner_angle_threshold_deg",)),
        ControllerParameterBinding(vendorParameterId="g1.collinear_merge_angle_deg", canonicalTargets=("collinear_merge_angle_deg",)),
        ControllerParameterBinding(vendorParameterId="g1.curvature_speed_clamp_factor", canonicalTargets=("curvature_speed_clamp_factor",)),
        ControllerParameterBinding(vendorParameterId="g1.min_segment_length_mm", canonicalTargets=("min_segment_length_mm",)),
        ControllerParameterBinding(vendorParameterId="g1.spline_degree", canonicalTargets=("spline_degree",)),
        ControllerParameterBinding(vendorParameterId="g2.path_max_feed_override", canonicalTargets=("feed_override_ratio",)),
        ControllerParameterBinding(vendorParameterId="g2.path_tangential_acc_mm_s2", canonicalTargets=("path_tangential_acc_mm_s2",)),
        ControllerParameterBinding(vendorParameterId="g2.path_tangential_jerk_mm_s3", canonicalTargets=("path_tangential_jerk_mm_s3",)),
        ControllerParameterBinding(vendorParameterId="g2.centripetal_acc_limit_mm_s2", canonicalTargets=("centripetal_acc_limit_mm_s2",)),
        ControllerParameterBinding(vendorParameterId="g2.axis_vel_limit_x", canonicalTargets=("axis_vel_limit_x_mm_s",)),
        ControllerParameterBinding(vendorParameterId="g2.axis_vel_limit_y", canonicalTargets=("axis_vel_limit_y_mm_s",)),
        ControllerParameterBinding(vendorParameterId="g2.axis_vel_limit_z", canonicalTargets=("axis_vel_limit_z_mm_s",)),
        ControllerParameterBinding(vendorParameterId="g2.axis_acc_limit_x", canonicalTargets=("axis_acc_limit_x_mm_s2",)),
        ControllerParameterBinding(vendorParameterId="g2.axis_acc_limit_y", canonicalTargets=("axis_acc_limit_y_mm_s2",)),
        ControllerParameterBinding(vendorParameterId="g2.axis_acc_limit_z", canonicalTargets=("axis_acc_limit_z_mm_s2",)),
        ControllerParameterBinding(
            vendorParameterId="g2.fir_moving_avg_time_ms",
            canonicalTargets=("fir_time_s",),
            scale=0.001,
        ),
        ControllerParameterBinding(
            vendorParameterId="g2.biquad_lowpass_freq_hz",
            canonicalTargets=("lowpass_cutoff_hz",),
        ),
        ControllerParameterBinding(
            vendorParameterId="g2.bell_acc_shape_factor",
            canonicalTargets=("bell_acc_shape_factor",),
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.servo_kp_x",
            canonicalTargets=("servo_kp_x_1_s",),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.servo_kp_y",
            canonicalTargets=("servo_kp_y_1_s",),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.servo_kp_z",
            canonicalTargets=("servo_kp_z_1_s",),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.vel_feedforward_x",
            canonicalTargets=("vel_feedforward_x_ratio",),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.vel_feedforward_y",
            canonicalTargets=("vel_feedforward_y_ratio",),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.vel_feedforward_z",
            canonicalTargets=("vel_feedforward_z_ratio",),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.acc_feedforward_x",
            canonicalTargets=("acc_feedforward_x_ratio",),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.acc_feedforward_y",
            canonicalTargets=("acc_feedforward_y_ratio",),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.friction_comp_amp_x",
            canonicalTargets=("friction_comp_amp_x_mm",),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.friction_comp_amp_y",
            canonicalTargets=("friction_comp_amp_y_mm",),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="g3.notch_filter_freq_hz",
            canonicalTargets=("notch_freq_hz",),
            tunability="drive-side",
        ),
    )
    return _finalize_profile(
        ControllerProfile(
            profileId="generic-fir-biquad@1",
            vendorName="Generic Reference CNC",
            controllerFamily="32D Spline + FIR/Biquad + P-P Cascade",
            registry=reg,
            capabilities=ControllerCapabilities(),
            bindings=bindings,
            profileContentHash="",
        )
    )


def beckhoff_twincat_nc_profile() -> ControllerProfile:
    """Built-in Beckhoff TwinCAT NC I / AX5000 profile using industrial German CNC units.

    Demonstrates multi-vendor adaptation:
    - Tolerance in `um` (`scale=0.001`), feed/axis velocities in `m/min` (`scale=1000/60`),
      accelerations in `m/s^2` (`scale=1000`), jerk in `m/s^3` (`scale=1000`),
      position loop `Kv` in `(m/min)/mm` (`scale=1000/60` -> `1/s`),
      feedforward in `%` (`scale=0.01`), setpoint filter time constant `s` mapped via
      `reciprocal_2pi` to equivalent low-pass cutoff frequency.
    - Axis max velocities are marked `read-only` (machine mechanical limits).
    """
    both: tuple[SourceKind, ...] = ("algorithm-export", "controller-trace")
    ctrl_only: tuple[SourceKind, ...] = ("controller-trace",)
    m_min_to_mm_s = 1000.0 / 60.0

    params = (
        ParameterDefinition(
            parameterId="tc.contour_blend_tol_um",
            displayName="TwinCAT 拐角平滑弦高容差",
            group="G1_GeometryLookahead",
            unit="um",
            bounds=(2.0, 100.0),
            defaultValue=20.0,
            appliesToSources=both,
            applicablePrimitives=("global", "corner", "micro-segment-cluster"),
        ),
        ParameterDefinition(
            parameterId="tc.micro_chord_tol_um",
            displayName="TwinCAT 小线段压缩弦差",
            group="G1_GeometryLookahead",
            unit="um",
            bounds=(1.0, 40.0),
            defaultValue=5.0,
            appliesToSources=both,
            applicablePrimitives=("global", "micro-segment-cluster"),
        ),
        ParameterDefinition(
            parameterId="tc.saf_lookahead_segments",
            displayName="SAF 前瞻扫描段数",
            group="G1_GeometryLookahead",
            unit="blocks",
            valueType="integer",
            bounds=(25, 450),
            defaultValue=160,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="tc.feed_override_pct",
            displayName="通道进给倍率上限",
            group="G2_KinematicsFilter",
            unit="%",
            bounds=(50.0, 120.0),
            defaultValue=100.0,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="tc.path_acc_m_s2",
            displayName="通道合成加速度",
            group="G2_KinematicsFilter",
            unit="m/s^2",
            bounds=(1.0, 12.0),
            defaultValue=5.0,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="tc.path_jerk_m_s3",
            displayName="通道合成加加速度 Jerk",
            group="G2_KinematicsFilter",
            unit="m/s^3",
            bounds=(25.0, 800.0),
            defaultValue=200.0,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="tc.centripetal_acc_m_s2",
            displayName="弯道向心加速度限幅",
            group="G2_KinematicsFilter",
            unit="m/s^2",
            bounds=(0.8, 8.0),
            defaultValue=3.0,
            appliesToSources=both,
            applicablePrimitives=("global", "arc", "corner"),
        ),
        ParameterDefinition(
            parameterId="tc.axis_velo_max_xy_m_min",
            displayName="XY 轴机械最大速度（只读）",
            group="G2_KinematicsFilter",
            unit="m/min",
            bounds=(6.0, 60.0),
            defaultValue=30.0,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="tc.moving_avg_filter_s",
            displayName="NC 插补滑动平均滤波时间",
            group="G2_KinematicsFilter",
            unit="s",
            bounds=(0.0, 0.050),
            defaultValue=0.012,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="tc.setpoint_pt2_tc_ms",
            displayName="指令 PT2 低通时间常数",
            group="G2_KinematicsFilter",
            unit="ms",
            bounds=(0.6, 8.0),
            defaultValue=2.0,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="tc.kv_factor_x_m_min_mm",
            displayName="X 轴位置环增益 Kv",
            group="G3_ServoControl",
            unit="(m/min)/mm",
            bounds=(1.2, 9.0),
            defaultValue=3.6,
            appliesToSources=ctrl_only,
            axisScope="X",
        ),
        ParameterDefinition(
            parameterId="tc.kv_factor_y_m_min_mm",
            displayName="Y 轴位置环增益 Kv",
            group="G3_ServoControl",
            unit="(m/min)/mm",
            bounds=(1.2, 9.0),
            defaultValue=3.6,
            appliesToSources=ctrl_only,
            axisScope="Y",
        ),
        ParameterDefinition(
            parameterId="tc.velo_ff_pct_xy",
            displayName="XY 速度前馈百分比",
            group="G3_ServoControl",
            unit="%",
            bounds=(80.0, 102.0),
            defaultValue=98.0,
            appliesToSources=ctrl_only,
        ),
        ParameterDefinition(
            parameterId="tc.torque_ff_pct_xy",
            displayName="AX5000 加速度/扭矩前馈百分比",
            group="G3_ServoControl",
            unit="%",
            bounds=(0.0, 100.0),
            defaultValue=70.0,
            appliesToSources=ctrl_only,
        ),
        ParameterDefinition(
            parameterId="tc.quadrant_comp_um_xy",
            displayName="过象限摩擦补偿幅值",
            group="G3_ServoControl",
            unit="um",
            bounds=(0.0, 20.0),
            defaultValue=5.0,
            appliesToSources=ctrl_only,
            applicablePrimitives=("global", "arc"),
        ),
        ParameterDefinition(
            parameterId="tc.ax5000_notch_hz",
            displayName="AX5000 驱动器陷波中心频率",
            group="G3_ServoControl",
            unit="Hz",
            bounds=(40.0, 400.0),
            defaultValue=180.0,
            appliesToSources=ctrl_only,
        ),
    )
    derived = (
        DerivedFeatureDefinition(
            featureId="derived.tc_kv_xy_mismatch",
            displayName="TwinCAT XY Kv 增益失配度",
            group="G3_ServoControl",
            sourceParameters=("tc.kv_factor_x_m_min_mm", "tc.kv_factor_y_m_min_mm"),
            formula="abs_diff",
        ),
    )
    reg = CncParameterRegistry(
        registryId="beckhoff.twincat-nc-ax5000.16d@1",
        parameters=params,
        derivedFeatures=derived,
        registryContentHash="",
    )
    reg = reg.model_copy(update={"registry_content_hash": compute_registry_content_hash(reg)})

    bindings = (
        ControllerParameterBinding(
            vendorParameterId="tc.contour_blend_tol_um",
            canonicalTargets=("corner_tolerance_mm",),
            scale=0.001,
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.micro_chord_tol_um",
            canonicalTargets=("small_seg_chord_tol_mm",),
            scale=0.001,
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.saf_lookahead_segments",
            canonicalTargets=("lookahead_block_count",),
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.feed_override_pct",
            canonicalTargets=("feed_override_ratio",),
            scale=0.01,
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.path_acc_m_s2",
            canonicalTargets=("path_tangential_acc_mm_s2", "axis_acc_limit_x_mm_s2", "axis_acc_limit_y_mm_s2"),
            scale=1000.0,
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.path_jerk_m_s3",
            canonicalTargets=("path_tangential_jerk_mm_s3",),
            scale=1000.0,
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.centripetal_acc_m_s2",
            canonicalTargets=("centripetal_acc_limit_mm_s2",),
            scale=1000.0,
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.axis_velo_max_xy_m_min",
            canonicalTargets=("axis_vel_limit_x_mm_s", "axis_vel_limit_y_mm_s"),
            scale=m_min_to_mm_s,
            tunability="read-only",
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.moving_avg_filter_s",
            canonicalTargets=("fir_time_s",),
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.setpoint_pt2_tc_ms",
            canonicalTargets=("lowpass_cutoff_hz",),
            transform="reciprocal_2pi",
            scale=0.001,
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.kv_factor_x_m_min_mm",
            canonicalTargets=("servo_kp_x_1_s",),
            scale=m_min_to_mm_s,
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.kv_factor_y_m_min_mm",
            canonicalTargets=("servo_kp_y_1_s",),
            scale=m_min_to_mm_s,
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.velo_ff_pct_xy",
            canonicalTargets=("vel_feedforward_x_ratio", "vel_feedforward_y_ratio"),
            scale=0.01,
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.torque_ff_pct_xy",
            canonicalTargets=("acc_feedforward_x_ratio", "acc_feedforward_y_ratio"),
            scale=0.01,
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.quadrant_comp_um_xy",
            canonicalTargets=("friction_comp_amp_x_mm", "friction_comp_amp_y_mm"),
            scale=0.001,
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="tc.ax5000_notch_hz",
            canonicalTargets=("notch_freq_hz",),
            tunability="drive-side",
        ),
    )
    return _finalize_profile(
        ControllerProfile(
            profileId="beckhoff-twincat-nc@1",
            vendorName="Beckhoff",
            controllerFamily="TwinCAT 3 NC I + AX5000",
            registry=reg,
            capabilities=ControllerCapabilities(hasBellJerkShaping=False),
            bindings=bindings,
            profileContentHash="",
        )
    )


def siemens_sinumerik_840d_profile() -> ControllerProfile:
    """Built-in Siemens SINUMERIK 840D sl (`CYCLE832` + `MD32xxx`) profile.

    Demonstrates structural topology differences:
    - Uses `SC` / `G645` contour tolerance + `MD32402` axial jerk FIR filter, WITHOUT a
      separate post-interpolation biquad command low-pass (`hasCommandLowpass=False`).
    """
    both: tuple[SourceKind, ...] = ("algorithm-export", "controller-trace")
    ctrl_only: tuple[SourceKind, ...] = ("controller-trace",)
    m_min_to_mm_s = 1000.0 / 60.0

    params = (
        ParameterDefinition(
            parameterId="sinumerik.cycle832_contour_tol_mm",
            displayName="CYCLE832 轮廓平滑公差 (CTOL)",
            group="G1_GeometryLookahead",
            unit="mm",
            bounds=(0.002, 0.100),
            defaultValue=0.020,
            appliesToSources=both,
            applicablePrimitives=("global", "corner", "micro-segment-cluster"),
        ),
        ParameterDefinition(
            parameterId="sinumerik.md20443_compress_tol_mm",
            displayName="COMPON/COMPCAD 小线段压缩公差",
            group="G1_GeometryLookahead",
            unit="mm",
            bounds=(0.001, 0.040),
            defaultValue=0.005,
            appliesToSources=both,
            applicablePrimitives=("global", "micro-segment-cluster"),
        ),
        ParameterDefinition(
            parameterId="sinumerik.md28060_ipo_buffer_blocks",
            displayName="IPO 前瞻缓冲段数",
            group="G1_GeometryLookahead",
            unit="blocks",
            valueType="integer",
            bounds=(30, 400),
            defaultValue=150,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="sinumerik.md32300_max_ax_acc_m_s2",
            displayName="MD32300 路径/轴最大加速度",
            group="G2_KinematicsFilter",
            unit="m/s^2",
            bounds=(1.0, 12.0),
            defaultValue=5.0,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="sinumerik.md32431_max_ax_jerk_m_s3",
            displayName="MD32431 路径最大跃度 Jerk",
            group="G2_KinematicsFilter",
            unit="m/s^3",
            bounds=(25.0, 800.0),
            defaultValue=200.0,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="sinumerik.md20602_curv_acc_m_s2",
            displayName="MD20602 弯道向心加速度上限",
            group="G2_KinematicsFilter",
            unit="m/s^2",
            bounds=(0.8, 8.0),
            defaultValue=3.0,
            appliesToSources=both,
            applicablePrimitives=("global", "arc", "corner"),
        ),
        ParameterDefinition(
            parameterId="sinumerik.md32410_ax_jerk_time_s",
            displayName="MD32410 轴跃度滑动滤波时间",
            group="G2_KinematicsFilter",
            unit="s",
            bounds=(0.0, 0.050),
            defaultValue=0.012,
            appliesToSources=both,
        ),
        ParameterDefinition(
            parameterId="sinumerik.md32200_posctrl_gain_x",
            displayName="MD32200 X 轴位置环增益 Kv",
            group="G3_ServoControl",
            unit="(m/min)/mm",
            bounds=(1.2, 9.0),
            defaultValue=3.6,
            appliesToSources=ctrl_only,
            axisScope="X",
        ),
        ParameterDefinition(
            parameterId="sinumerik.md32200_posctrl_gain_y",
            displayName="MD32200 Y 轴位置环增益 Kv",
            group="G3_ServoControl",
            unit="(m/min)/mm",
            bounds=(1.2, 9.0),
            defaultValue=3.6,
            appliesToSources=ctrl_only,
            axisScope="Y",
        ),
        ParameterDefinition(
            parameterId="sinumerik.md32610_velo_ffw_factor",
            displayName="MD32610 FFWOF/FFWON 速度前馈系数",
            group="G3_ServoControl",
            unit="ratio",
            bounds=(0.80, 1.02),
            defaultValue=0.98,
            appliesToSources=ctrl_only,
        ),
        ParameterDefinition(
            parameterId="sinumerik.md32650_inertia_ffw_ratio",
            displayName="扭矩/惯量前馈均衡比例",
            group="G3_ServoControl",
            unit="ratio",
            bounds=(0.0, 1.00),
            defaultValue=0.70,
            appliesToSources=ctrl_only,
        ),
        ParameterDefinition(
            parameterId="sinumerik.md32520_quad_fric_mm",
            displayName="MD32520 QEC 过象限摩擦补偿量",
            group="G3_ServoControl",
            unit="mm",
            bounds=(0.0, 0.020),
            defaultValue=0.005,
            appliesToSources=ctrl_only,
            applicablePrimitives=("global", "arc"),
        ),
        ParameterDefinition(
            parameterId="sinumerik.sinamics_p1417_notch_hz",
            displayName="SINAMICS p1417 电流环陷波频率",
            group="G3_ServoControl",
            unit="Hz",
            bounds=(40.0, 400.0),
            defaultValue=180.0,
            appliesToSources=ctrl_only,
        ),
    )
    reg = CncParameterRegistry(
        registryId="siemens.sinumerik-840dsl.13d@1",
        parameters=params,
        derivedFeatures=(
            DerivedFeatureDefinition(
                featureId="derived.sinumerik_kv_xy_mismatch",
                displayName="SINUMERIK XY Kv 失配度",
                group="G3_ServoControl",
                sourceParameters=("sinumerik.md32200_posctrl_gain_x", "sinumerik.md32200_posctrl_gain_y"),
                formula="abs_diff",
            ),
        ),
        registryContentHash="",
    )
    reg = reg.model_copy(update={"registry_content_hash": compute_registry_content_hash(reg)})

    bindings = (
        ControllerParameterBinding(
            vendorParameterId="sinumerik.cycle832_contour_tol_mm",
            canonicalTargets=("corner_tolerance_mm",),
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md20443_compress_tol_mm",
            canonicalTargets=("small_seg_chord_tol_mm",),
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md28060_ipo_buffer_blocks",
            canonicalTargets=("lookahead_block_count",),
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md32300_max_ax_acc_m_s2",
            canonicalTargets=("path_tangential_acc_mm_s2", "axis_acc_limit_x_mm_s2", "axis_acc_limit_y_mm_s2"),
            scale=1000.0,
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md32431_max_ax_jerk_m_s3",
            canonicalTargets=("path_tangential_jerk_mm_s3",),
            scale=1000.0,
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md20602_curv_acc_m_s2",
            canonicalTargets=("centripetal_acc_limit_mm_s2",),
            scale=1000.0,
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md32410_ax_jerk_time_s",
            canonicalTargets=("fir_time_s",),
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md32200_posctrl_gain_x",
            canonicalTargets=("servo_kp_x_1_s",),
            scale=m_min_to_mm_s,
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md32200_posctrl_gain_y",
            canonicalTargets=("servo_kp_y_1_s",),
            scale=m_min_to_mm_s,
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md32610_velo_ffw_factor",
            canonicalTargets=("vel_feedforward_x_ratio", "vel_feedforward_y_ratio"),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md32650_inertia_ffw_ratio",
            canonicalTargets=("acc_feedforward_x_ratio", "acc_feedforward_y_ratio"),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.md32520_quad_fric_mm",
            canonicalTargets=("friction_comp_amp_x_mm", "friction_comp_amp_y_mm"),
            tunability="drive-side",
        ),
        ControllerParameterBinding(
            vendorParameterId="sinumerik.sinamics_p1417_notch_hz",
            canonicalTargets=("notch_freq_hz",),
            tunability="drive-side",
        ),
    )
    return _finalize_profile(
        ControllerProfile(
            profileId="siemens-sinumerik-840d@1",
            vendorName="Siemens",
            controllerFamily="SINUMERIK 840D sl (CYCLE832 + SINAMICS S120)",
            registry=reg,
            capabilities=ControllerCapabilities(
                hasCommandLowpass=False,
                hasBellJerkShaping=False,
            ),
            bindings=bindings,
            profileContentHash="",
        )
    )


BUILTIN_CONTROLLER_PROFILES: dict[str, Any] = {
    "generic-fir-biquad@1": default_generic_controller_profile,
    "beckhoff-twincat-nc@1": beckhoff_twincat_nc_profile,
    "siemens-sinumerik-840d@1": siemens_sinumerik_840d_profile,
}


def list_controller_profiles() -> tuple[ControllerProfile, ...]:
    """Return all built-in CNC controller profiles."""
    return tuple(factory() for factory in BUILTIN_CONTROLLER_PROFILES.values())


def get_controller_profile(profile_id: str) -> ControllerProfile:
    """Look up a built-in `ControllerProfile` by `profile_id`."""
    factory = BUILTIN_CONTROLLER_PROFILES.get(profile_id)
    if factory is None:
        known = ", ".join(sorted(BUILTIN_CONTROLLER_PROFILES))
        raise KeyError(f"unknown controller profile '{profile_id}'; known profiles: {known}")
    return factory()
