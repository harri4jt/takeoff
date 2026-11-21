"""Rule sets (Part 25 vs MIL-STD-3013), ground effect, fuel burn, refusal speed,
gear outputs and multiple thrust tables."""

from __future__ import annotations

import math

import numpy as np
import pytest

from bfl import compute_bfl, load_config
from bfl.aero import fit_parabolic_polar, load_aero_table, raymer_phi
from bfl.config import RULE_PRESETS
from bfl.model import build_model

from .conftest import SYNTH


# ---------------------------------------------------------------------------------
# rule sets
# ---------------------------------------------------------------------------------
def test_rule_presets_resolve(base_cfg):
    p = base_cfg.procedure.resolved()
    assert p.t_recog_s == 1.0 and p.t_v1_allowance_s == 2.0 and p.screen_height_ft == 35.0
    m = base_cfg.with_updates({"procedure.rules": "mil3013"}).procedure.resolved()
    assert m.t_recog_s == 3.0 and m.t_v1_allowance_s == 0.0 and m.screen_height_ft == 50.0
    assert m.field_length_aeo_factor == 1.0 and m.chute_enabled is False
    # an explicit value beats the preset
    e = base_cfg.with_updates({"procedure.rules": "mil3013", "procedure.t_recog_s": 2.0})
    assert e.procedure.resolved().t_recog_s == 2.0
    # unresolved configs stay switchable: resolving is never stored back
    assert base_cfg.procedure.t_recog_s is None


def test_mil_equals_part25_with_matching_overrides(base_cfg):
    """The MIL preset is nothing but a set of procedure values."""
    mil = compute_bfl(base_cfg.with_updates({"procedure.rules": "mil3013"}))
    by_hand = {f"procedure.{k}": v for k, v in RULE_PRESETS["mil3013"].items()}
    by_hand.pop("procedure.v_lof_min_ratio")
    p25 = compute_bfl(base_cfg.with_updates(by_hand))
    assert mil.bfl_ft == pytest.approx(p25.bfl_ft, abs=1e-6)
    assert mil.v_ef_kts == pytest.approx(p25.v_ef_kts, abs=1e-9)
    assert mil.is_mil and not p25.is_mil
    assert mil.names["bfl_short"] == "CFL"


def test_mil_field_has_no_aeo_factor(base_cfg):
    r = compute_bfl(base_cfg.with_updates({"procedure.rules": "mil3013"}))
    assert r.field_length_ft == pytest.approx(max(r.bfl_ft, r.aeo_distance_ft))
    assert r.screen_height_ft == 50.0


def test_mil_recognition_time_is_an_input(base_cfg):
    cfg = base_cfg.with_updates({"procedure.rules": "mil3013"})
    a = compute_bfl(cfg.with_updates({"procedure.t_recog_s": 2.0}))
    b = compute_bfl(cfg.with_updates({"procedure.t_recog_s": 4.0}))
    assert b.bfl_ft > a.bfl_ft  # longer delay, longer field
    assert b.v1_kts - b.v_ef_kts > a.v1_kts - a.v_ef_kts


def test_mil_chute_optional_default_off():
    cfg = load_config("sr71", overrides={"procedure.rules": "mil3013"})
    assert not cfg.chute_active
    assert cfg.with_updates({"procedure.chute_enabled": True}).chute_active
    assert load_config("sr71").chute_active  # Part 25: aircraft default (on, flagged)


def test_sr71_mil_result_finite():
    r = compute_bfl(load_config("sr71", overrides={"procedure.rules": "mil3013"}))
    assert math.isfinite(r.bfl_ft) and r.bfl_ft > 0


# ---------------------------------------------------------------------------------
# refusal speed
# ---------------------------------------------------------------------------------
def test_refusal_speed_at_bfl_is_v1(base_cfg, base_result):
    """With the runway equal to the balanced stop distance, refusal speed = V1."""
    r = compute_bfl(base_cfg.with_updates({"environment.runway_available_ft": base_result.d_stop_ft}))
    assert r.refusal_v1_kts == pytest.approx(base_result.v1_kts, abs=0.05)
    longer = compute_bfl(
        base_cfg.with_updates({"environment.runway_available_ft": base_result.d_stop_ft + 500})
    )
    assert longer.refusal_v1_kts > r.refusal_v1_kts


# ---------------------------------------------------------------------------------
# ground effect
# ---------------------------------------------------------------------------------
def test_raymer_phi_limits():
    assert raymer_phi(0.0) == 0.0
    assert raymer_phi(10.0) > 0.99
    assert raymer_phi(0.1) == pytest.approx(33 * 0.1**1.5 / (1 + 33 * 0.1**1.5))
    assert raymer_phi(0.1) < raymer_phi(0.2)


def test_polar_fit_recovers_parabola(tmp_path):
    rows = ["alpha_deg,CL,CD"]
    for a in range(-4, 16):
        cl = 0.1 * a + 0.3
        rows.append(f"{a},{cl:.6f},{0.02 + 0.05 * cl * cl:.8f}")
    p = tmp_path / "polar.csv"
    p.write_text("\n".join(rows) + "\n")
    fit = fit_parabolic_polar(load_aero_table(p), 0.85)
    assert fit.CD0 == pytest.approx(0.02, abs=1e-6)
    assert fit.K == pytest.approx(0.05, abs=1e-6)
    assert fit.r2 == pytest.approx(1.0, abs=1e-9)


def test_ground_effect_shortens_and_fades(base_cfg, base_result):
    ge = {
        "aircraft.ground_effect.enabled": True,
        "aircraft.ground_effect.span_ft": 200.0,
        "aircraft.ground_effect.wing_height_ft": 15.0,
    }
    r = compute_bfl(base_cfg.with_updates(ge))
    assert r.aeo_distance_ft < base_result.aeo_distance_ft
    assert r.polar_fit is not None and r.polar_fit["K"] > 0
    vm = build_model(base_cfg.with_updates(ge))
    _, cd_ground = vm.aero.coefficients(0.1, False, False, 0.0)
    _, cd_high = vm.aero.coefficients(0.1, False, False, 5000.0)
    _, cd_free = build_model(base_cfg).aero.coefficients(0.1, False, False, 0.0)
    assert cd_ground < cd_high < cd_free + 1e-12
    assert cd_high == pytest.approx(cd_free, rel=1e-3)


def test_ground_effect_needs_geometry(base_cfg):
    with pytest.raises(ValueError):
        base_cfg.with_updates({"aircraft.ground_effect.enabled": True})


# ---------------------------------------------------------------------------------
# fuel burn
# ---------------------------------------------------------------------------------
def test_fuel_burn_matches_tsfc_times_thrust(base_cfg):
    """Fuel burned = integral of TSFC * T dt / 3600, and burning fuel shortens the run."""
    r = compute_bfl(base_cfg.with_updates({"aircraft.engines.tsfc_per_hr": 2.0}))
    df = r.aeo.to_dataframe()
    t, thrust = df["t_s"].to_numpy(), df["T_total_lbf"].to_numpy()
    integral = float(np.sum(0.5 * (thrust[1:] + thrust[:-1]) * np.diff(t))) * 2.0 / 3600.0
    assert r.fuel_used_aeo_lbf == pytest.approx(integral, rel=1e-3)
    assert base_cfg.aircraft.engines.tsfc_per_hr == 0.0
    no_burn = compute_bfl(base_cfg)
    assert no_burn.fuel_used_aeo_lbf == 0.0
    assert r.aeo_distance_ft < no_burn.aeo_distance_ft


def test_tsfc_column_overrides_scalar(tmp_path, base_cfg):
    d = tmp_path / "ac"
    src = load_config(SYNTH).aircraft
    import shutil

    shutil.copytree(src.directory, d)
    lines = (d / "thrust.csv").read_text().splitlines()
    out = []
    for ln in lines:
        if ln.startswith("#"):
            out.append(ln)
        elif ln.startswith("airspeed_kts"):
            out.append(ln + ",tsfc_per_hr")
        else:
            out.append(ln + ",0.5")
    (d / "thrust.csv").write_text("\n".join(out) + "\n")
    cfg = load_config(d, overrides={"aircraft.engines.tsfc_per_hr": 5.0})
    vm = build_model(cfg)
    assert vm.propulsion.tsfc(100.0, 518.67) == pytest.approx(0.5)


# ---------------------------------------------------------------------------------
# gear outputs, thrust-table options
# ---------------------------------------------------------------------------------
def test_gear_outputs(base_result):
    assert base_result.max_tire_speed_kts >= base_result.v1_ground_kts
    s = base_result.scalars()
    assert s["brake_energy_MJ"] > 0 and s["max_tire_speed_kts"] > 0
    # brake energy is at most the kinetic energy at the start of braking
    m = load_config(SYNTH).weight_lbf / 32.174
    v = base_result.max_tire_speed_kts * 1.6878
    assert base_result.brake_energy_MJ < 0.5 * m * v * v * 1.3558e-6


def test_thrust_options(base_cfg):
    eng = base_cfg.aircraft.engines
    assert list(eng.thrust_options().values())[0] == eng.thrust_table
    two = eng.model_copy(update={"thrust_tables": {"derated": "thrust.csv", "other": "x.csv"}})
    opts = two.thrust_options()
    assert opts["derated"] == "thrust.csv" and opts["other"] == "x.csv" and len(opts) == 2
