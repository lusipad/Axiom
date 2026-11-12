from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axiom.benchmark import CncAlgorithmExport
from axiom.benchmark_standard import standard_case, standard_cases
from axiom.cli import main as cli_main
from axiom.controller_profile import (
    beckhoff_twincat_nc_profile,
    default_generic_controller_profile,
    get_controller_profile,
    list_controller_profiles,
    siemens_sinumerik_840d_profile,
    verify_controller_profile_hash,
)
from axiom.greybox_model import (
    evaluate_greybox_backbone,
    simulate_realistic_cnc_controller,
)
from axiom.parameter_diagnoser import diagnose_single_run, render_diagnostic_table
from axiom.parameter_learner import (
    ParameterLearningRequest,
    learn_parameter_surrogate,
)
from axiom.parameter_recommender import (
    ParameterRecommendationRequest,
    recommend_parameters,
)
from axiom.parameter_space import default_parameter_values, generate_parameter_doe
from axiom.web import create_app


def test_controller_profile_unit_conversions_and_hash_guard() -> None:
    profiles = list_controller_profiles()
    assert {p.profile_id for p in profiles} >= {
        "generic-fir-biquad@1",
        "beckhoff-twincat-nc@1",
        "siemens-sinumerik-840d@1",
    }

    tc = beckhoff_twincat_nc_profile()
    verify_controller_profile_hash(tc)
    defaults = default_parameter_values(tc.registry)
    q = tc.to_canonical(defaults)

    # 20 um -> 0.020 mm; Kv = 3.6 (m/min)/mm -> 60.0 1/s; PT2 tc = 2.0 ms -> ~79.577 Hz
    assert q.corner_tolerance_mm == pytest.approx(0.020, rel=1e-6)
    assert q.servo_kp_1_s[0] == pytest.approx(60.0, rel=1e-6)
    assert q.vel_feedforward_ratio[0] == pytest.approx(0.98, rel=1e-6)
    assert q.lowpass_cutoff_hz == pytest.approx(1.0 / (2.0 * 3.141592653589793 * 0.002), rel=1e-5)

    # Reciprocal round-trip for PT2 time constant
    pid, pt2_ms = tc.from_canonical_value("lowpass_cutoff_hz", 50.0) or ("", 0.0)
    assert pid == "tc.setpoint_pt2_tc_ms"
    assert pt2_ms == pytest.approx(1000.0 / (2.0 * 3.141592653589793 * 50.0), rel=1e-4)

    # Siemens 840D sl has no separate command biquad lowpass (hasCommandLowpass=False)
    siemens = siemens_sinumerik_840d_profile()
    verify_controller_profile_hash(siemens)
    q_s = siemens.to_canonical(default_parameter_values(siemens.registry))
    assert q_s.lowpass_cutoff_hz is None
    assert siemens.from_canonical_value("lowpass_cutoff_hz", 80.0) is None

    # Tampered profile hash must be rejected
    tampered = tc.model_copy(update={"vendor_name": "TamperedVendor"})
    with pytest.raises(ValueError, match="profileContentHash"):
        verify_controller_profile_hash(tampered)

    # Unmapped parameter IDs must be rejected by evaluate_greybox_backbone
    cases = standard_cases()
    with pytest.raises(ValueError, match="not in controller profile"):
        evaluate_greybox_backbone(
            cases[0],
            {"g1.corner_tolerance_mm": 0.02},
            controller_profile=tc,
        )


def test_beckhoff_twincat_end_to_end_doe_learn_and_nc_only_recommendation() -> None:
    tc = beckhoff_twincat_nc_profile()
    train_cases = (
        standard_case("corner90"),
        standard_case("circle"),
        standard_case("small-segments"),
        standard_case("line"),
    )
    train_map = {c.case_id: c for c in train_cases}
    unseen_case = standard_case("s-curve")

    doe = generate_parameter_doe(
        offline_count=16,
        controller_count=12,
        seed=101,
        controller_profile=tc,
    )
    assert doe.registry_id == tc.registry.registry_id
    all_pts = (*doe.offline_samples, *doe.controller_samples)
    # Read-only mechanical limit must stay at its default value across every DoE sample
    default_vmax = default_parameter_values(tc.registry)["tc.axis_velo_max_xy_m_min"]
    for pt in all_pts:
        assert pt.parameters["tc.axis_velo_max_xy_m_min"] == pytest.approx(default_vmax)

    exports: list[CncAlgorithmExport] = []
    for idx, pt in enumerate(all_pts):
        c = train_map.get(pt.recommended_case_id or "", train_cases[idx % len(train_cases)])
        exp = simulate_realistic_cnc_controller(
            c,
            pt.parameters,
            source_kind=pt.target_source,
            controller_profile=tc,
        )
        exports.append(exp)

    surrogate = learn_parameter_surrogate(
        ParameterLearningRequest(
            registry=tc.registry,
            controllerProfile=tc,
            cases=train_cases,
            exports=tuple(exports),
        )
    )
    assert surrogate.controller_profile is not None
    assert surrogate.controller_profile.profile_id == "beckhoff-twincat-nc@1"

    base_params = default_parameter_values(tc.registry)

    # 1. Calibrated case (corner90) with tight 50 um contour gate & NC-only commissioning mode
    rec_cal = recommend_parameters(
        surrogate,
        ParameterRecommendationRequest(
            targetCase=train_cases[0],
            baselineParameters=base_params,
            includeDriveSideParameters=False,
            maximumPathDeviationMm=0.050,
            maximumActualPathDeviationMm=0.055,
            candidatePoolSize=160,
            seed=42,
        ),
    )
    assert len(rec_cal.presets) >= 1

    # 2. Unseen toolpath (s-curve) zero-shot transfer with NC-only commissioning mode
    rec_nc_only = recommend_parameters(
        surrogate,
        ParameterRecommendationRequest(
            targetCase=unseen_case,
            baselineParameters=base_params,
            includeDriveSideParameters=False,
            maximumPathDeviationMm=0.065,
            maximumActualPathDeviationMm=0.085,
            candidatePoolSize=160,
            seed=42,
        ),
    )
    assert len(rec_nc_only.presets) >= 1
    drive_or_ro_ids = {
        b.vendor_parameter_id for b in tc.bindings if b.tunability in {"drive-side", "read-only"}
    }
    for preset in (*rec_cal.presets, *rec_nc_only.presets):
        for pid in drive_or_ro_ids:
            assert preset.full_parameters[pid] == pytest.approx(base_params[pid])


def test_siemens_sinumerik_840d_end_to_end_without_biquad_lowpass() -> None:
    siemens = siemens_sinumerik_840d_profile()
    train_case = standard_case("corner90")
    unseen_case = standard_case("small-segments")

    doe = generate_parameter_doe(
        offline_count=8,
        controller_count=6,
        seed=202,
        controller_profile=siemens,
    )
    all_pts = (*doe.offline_samples, *doe.controller_samples)
    exports: list[CncAlgorithmExport] = []
    for idx, pt in enumerate(all_pts):
        exp = simulate_realistic_cnc_controller(
            train_case,
            pt.parameters,
            source_kind=pt.target_source,
            controller_profile=siemens,
        )
        exports.append(exp)

    surrogate = learn_parameter_surrogate(
        ParameterLearningRequest(
            registry=siemens.registry,
            controllerProfile=siemens,
            case=train_case,
            exports=tuple(exports),
        )
    )
    assert surrogate.engine_mode == "greybox-physics-gp"

    rec = recommend_parameters(
        surrogate,
        ParameterRecommendationRequest(
            targetCase=unseen_case,
            maximumPathDeviationMm=0.048,
            maximumActualPathDeviationMm=0.055,
            candidatePoolSize=120,
            seed=7,
        ),
    )
    assert len(rec.presets) >= 1
    for preset in rec.presets:
        assert set(preset.full_parameters) == {
            p.parameter_id for p in siemens.registry.parameters
        }


def test_single_run_diagnoser_resonance_quadrant_mismatch_and_nc_only() -> None:
    arc_case = standard_case("circle")

    # 1. Generic profile: mistuned notch + short FIR + zero friction comp + XY Kv mismatch -> rich diagnosis
    gen = default_generic_controller_profile()
    bad_params = default_parameter_values(gen.registry)
    bad_params["g3.notch_filter_freq_hz"] = 290.0  # away from ~142 Hz structural mode
    bad_params["g2.fir_moving_avg_time_ms"] = 2.0
    bad_params["g3.friction_comp_amp_x"] = 0.0
    bad_params["g3.friction_comp_amp_y"] = 0.0
    bad_params["g3.servo_kp_x"] = 85.0
    bad_params["g3.servo_kp_y"] = 45.0

    exp = simulate_realistic_cnc_controller(
        arc_case,
        bad_params,
        source_kind="controller-trace",
        machine_resonance_hz=142.0,
        controller_profile=gen,
    )
    diag = diagnose_single_run(arc_case, exp, controller_profile=gen)
    assert diag.permission_level == "OfflineAdvisory"
    assert diag.device_write_allowed is False
    assert 1 <= len(diag.top_actions) <= 2
    finding_ids = {f.finding_id for f in diag.findings}
    assert "diag.structural-resonance" in finding_ids

    # Resonance FIR suggestion must align with 1000 / f_res (ms) with High confidence
    res_finding = next(f for f in diag.findings if f.finding_id == "diag.structural-resonance")
    fir_sug = next(s for s in res_finding.suggestions if s.parameter_id == "g2.fir_moving_avg_time_ms")
    assert fir_sug.confidence_level == "High"
    assert 6.0 <= fir_sug.suggested_value <= 8.2  # 1000 / ~142 Hz ~= 7.04 ms

    rendered = render_diagnostic_table(diag)
    assert "单刀机理诊断顾问" in rendered
    assert "g2.fir_moving_avg_time_ms" in rendered

    # 2. Same physics on Beckhoff TwinCAT with include_drive_side=False (--nc-only)
    tc = beckhoff_twincat_nc_profile()
    tc_bad = default_parameter_values(tc.registry)
    tc_bad["tc.moving_avg_filter_s"] = 0.002
    tc_bad["tc.ax5000_notch_hz"] = 300.0
    tc_bad["tc.quadrant_comp_um_xy"] = 0.0
    tc_exp = simulate_realistic_cnc_controller(
        arc_case,
        tc_bad,
        source_kind="controller-trace",
        machine_resonance_hz=142.0,
        controller_profile=tc,
    )
    diag_tc_nc = diagnose_single_run(
        arc_case,
        tc_exp,
        controller_profile=tc,
        include_drive_side=False,
    )
    assert all(act.tunability == "nc-tunable" for act in diag_tc_nc.top_actions)
    tc_fir = next(act for act in diag_tc_nc.top_actions if act.parameter_id == "tc.moving_avg_filter_s")
    assert tc_fir.unit == "s"
    assert 0.0055 <= tc_fir.suggested_value <= 0.0085


def test_cli_and_web_controller_profiles_and_single_run_diagnosis(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # CLI param-profiles
    rc = cli_main(["param-profiles"])
    assert rc == 0
    profiles_out = json.loads(capsys.readouterr().out)
    assert len(profiles_out) >= 3

    # Prepare case & single-run export for CLI param-diagnose on TwinCAT
    tc = get_controller_profile("beckhoff-twincat-nc@1")
    case = standard_case("corner90")
    tc_params = default_parameter_values(tc.registry)
    tc_params["tc.contour_blend_tol_um"] = 95.0  # deliberately exceed contour limit
    exp = simulate_realistic_cnc_controller(
        case,
        tc_params,
        source_kind="controller-trace",
        controller_profile=tc,
    )

    case_path = tmp_path / "case.json"
    exp_path = tmp_path / "export.json"
    diag_out_path = tmp_path / "diag.json"
    case_path.write_text(
        json.dumps(case.model_dump(mode="json", by_alias=True, exclude_none=True)),
        encoding="utf-8",
    )
    exp_path.write_text(
        json.dumps(exp.model_dump(mode="json", by_alias=True, exclude_none=True)),
        encoding="utf-8",
    )

    rc_diag = cli_main(
        [
            "param-diagnose",
            "--case",
            str(case_path),
            "--export",
            str(exp_path),
            "--profile",
            "beckhoff-twincat-nc@1",
            "--nc-only",
            "--out",
            str(diag_out_path),
        ]
    )
    assert rc_diag == 0
    table_text = capsys.readouterr().out
    assert "tc.contour_blend_tol_um" in table_text or "tc.moving_avg_filter_s" in table_text
    saved_diag = json.loads(diag_out_path.read_text(encoding="utf-8"))
    assert saved_diag["controllerProfileId"] == "beckhoff-twincat-nc@1"

    # Web endpoints
    client = TestClient(create_app())
    r_prof = client.get("/api/v1/benchmarks/cnc/controller-profiles")
    assert r_prof.status_code == 200
    assert any(p["profileId"] == "siemens-sinumerik-840d@1" for p in r_prof.json())

    r_doe = client.get(
        "/api/v1/benchmarks/cnc/param-doe",
        params={
            "offlineCount": 6,
            "controllerCount": 4,
            "seed": 11,
            "profileId": "siemens-sinumerik-840d@1",
        },
    )
    assert r_doe.status_code == 200
    assert r_doe.json()["registryId"] == "siemens.sinumerik-840dsl.13d@1"

    r_diag = client.post(
        "/api/v1/benchmarks/cnc/param-diagnose",
        json={
            "case": case.model_dump(mode="json", by_alias=True, exclude_none=True),
            "export": exp.model_dump(mode="json", by_alias=True, exclude_none=True),
            "profileId": "beckhoff-twincat-nc@1",
            "includeDriveSide": False,
        },
    )
    assert r_diag.status_code == 200
    assert r_diag.json()["controllerProfileId"] == "beckhoff-twincat-nc@1"
