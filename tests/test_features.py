"""Rule sets (Part 25 vs MIL-STD-3013), ground effect, fuel burn, refusal speed,
gear outputs and multiple thrust tables."""

from __future__ import annotations

import math

import numpy as np
import pytest

from bfl import compute_bfl, load_config
from bfl.aero import fit_parabolic_polar, load_aero_table, raymer_phi
from bfl.config import RULE_PRESETS, EnginesConfig
from bfl.model import build_model
from bfl.optimize import brent_min, golden_section

from .conftest import SYNTH


# ---------------------------------------------------------------------------------
# rule sets
# ---------------------------------------------------------------------------------
def test_rules_come_from_the_aircraft(base_cfg):
    """certification.rules / t_recog_s are the aircraft's; procedure.* still overrides."""
    mil_ac = base_cfg.with_updates({"aircraft.certification.rules": "mil3013"})
    p = mil_ac.resolved().procedure
    assert p.is_mil and p.t_recog_s == 3.0 and p.screen_height_ft == 50.0
    own = mil_ac.with_updates({"aircraft.certification.t_recog_s": 2.5}).resolved().procedure
    assert own.t_recog_s == 2.5
    back = mil_ac.with_updates({"procedure.rules": "part25"}).resolved().procedure
    assert not back.is_mil and back.t_recog_s == 1.0
    assert load_config("sr71").resolved().procedure.is_mil
    assert not load_config("b747_100").resolved().procedure.is_mil


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
    assert mil.names["bfl_short"] == "BFL"  # MIL's CFL is labelled BFL for consistency
    assert mil.names["v_ef"].startswith("V_CEF")


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
    assert not load_config("sr71").chute_active  # the SR-71 file sets MIL rules
    p25 = load_config("sr71", overrides={"procedure.rules": "part25"})
    assert p25.chute_active  # Part 25: aircraft default (on, flagged)


def test_sr71_mil_result_finite():
    r = compute_bfl(load_config("sr71", overrides={"procedure.rules": "mil3013"}))
    assert math.isfinite(r.bfl_ft) and r.bfl_ft > 0


# ---------------------------------------------------------------------------------
# refusal speed
# ---------------------------------------------------------------------------------
def test_refusal_speed_at_bfl_is_v1(base_cfg, base_result):
    """With the runway equal to the balanced stop distance, refusal speed = V1."""
    r = compute_bfl(
        base_cfg.with_updates({"environment.runway_available_ft": base_result.d_stop_ft})
    )
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


def test_thrust_tables_are_named_like_aero_tables(base_cfg):
    """thrust_table names one of thrust_tables (as takeoff_configuration names an aero
    table); the older 'thrust_table: file.csv' form is registered under the file stem."""
    eng = base_cfg.aircraft.engines  # the synthetic YAML still uses the old form
    assert eng.thrust_tables == {"thrust": "thrust.csv"} and eng.thrust_table == "thrust"
    assert eng.thrust_file == "thrust.csv"
    two = EnginesConfig.model_validate(
        {**eng.model_dump(), "thrust_tables": {"a": "x.csv", "b": "thrust.csv"},
         "thrust_table": "b"}
    )  # fmt: skip
    assert list(two.thrust_options()) == ["b", "a"] and two.thrust_file == "thrust.csv"
    with pytest.raises(ValueError, match="not listed"):
        EnginesConfig.model_validate({**two.model_dump(), "thrust_table": "c"})
    b747 = load_config("b747_100").aircraft.engines
    assert b747.thrust_table == "JT9D-3" and b747.thrust_file == "thrust.csv"
    # selecting a table by name is what the app and the trade study do
    sel = base_cfg.with_updates({"aircraft.engines.thrust_tables": {"thrust": "thrust.csv",
                                                                     "copy": "thrust.csv"},
                                 "aircraft.engines.thrust_table": "copy"})  # fmt: skip
    assert compute_bfl(sel).bfl_ft == pytest.approx(compute_bfl(base_cfg).bfl_ft)


# ---------------------------------------------------------------------------------
# rotation speed
# ---------------------------------------------------------------------------------
def test_golden_section():
    r = golden_section(lambda x: (x - 1.3) ** 2, 0.0, 2.0, xtol=1e-6)
    assert r.x == pytest.approx(1.3, abs=1e-6)
    k = golden_section(lambda x: max(2.0 - x, 0.5 * x), 0.0, 3.0, xtol=1e-6)  # a kink
    assert k.x == pytest.approx(4.0 / 3.0, abs=1e-6)
    # one new evaluation per iteration after the first two
    assert len(k.x_history) == k.iterations + 2


def test_brent_min():
    """Brent's method: same answers as golden section, far fewer evaluations when f is
    smooth, and no worse than golden section on a kink."""
    q = brent_min(lambda x: (x - 1.3) ** 2, 0.0, 2.0, xtol=1e-6)
    g = golden_section(lambda x: (x - 1.3) ** 2, 0.0, 2.0, xtol=1e-6)
    assert q.x == pytest.approx(1.3, abs=1e-6)
    assert len(q.x_history) < len(g.x_history) / 3
    k = brent_min(lambda x: max(2.0 - x, 0.5 * x), 0.0, 3.0, xtol=1e-6)
    assert k.x == pytest.approx(4.0 / 3.0, abs=1e-6)
    s = brent_min(lambda x: math.cosh(x - 0.7) + 0.1 * x**4, -1.0, 2.0, xtol=1e-6)
    assert s.x == pytest.approx(0.6095437, abs=1e-5)
    # a known starting point is used, not re-evaluated
    calls = []
    brent_min(lambda x: calls.append(x) or (x - 1.0) ** 2, 0.0, 3.0, xtol=1e-4, x0=0.9, f0=0.01)
    assert 0.9 not in calls


def test_optimize_vr_sr71_balances():
    """The SR-71 does not balance at its lowest legal VR; a later rotation (the default)
    fixes it."""
    cfg = load_config("sr71")
    lo = compute_bfl(cfg.with_updates({"procedure.optimize_vr": False}))
    opt = compute_bfl(cfg)
    assert cfg.procedure.optimize_vr  # on by default
    assert not lo.balanced and opt.balanced
    assert not any(w.startswith("UNBALANCED") for w in opt.warnings)
    assert opt.k_VR > lo.k_VR + 0.1
    assert opt.field_length_ft < 0.5 * lo.field_length_ft
    vo = opt.vr_optimization
    assert vo["k_VR_old"] == pytest.approx(lo.k_VR) and vo["k_VR_new"] == opt.k_VR
    assert vo["evaluations"] <= 14
    # it is a minimum: nudging k_VR either way does not help
    fixed = {"procedure.enforce_v2_min": False, "procedure.optimize_vr": False}
    for dk in (-0.01, 0.01):
        nb = compute_bfl(cfg.with_updates({"procedure.k_VR": opt.k_VR + dk, **fixed}))
        assert nb.field_length_ft >= opt.field_length_ft - 1.0


def test_optimize_vr_keeps_lowest_vr_when_best(base_cfg):
    """When the field grows with VR, two extra solves (k_lo + 0.01, k_lo + 0.05) settle it."""
    lo = compute_bfl(base_cfg.with_updates({"procedure.optimize_vr": False}))
    opt = compute_bfl(base_cfg.with_updates({"procedure.optimize_vr": True}))
    assert opt.k_VR == lo.k_VR and opt.field_length_ft == lo.field_length_ft
    assert opt.vr_optimization["evaluations"] == 2


def test_optimize_vr_warm_start_agrees_with_cold():
    """A neighbouring optimum as the starting point gives the same answer, cheaper."""
    cfg = load_config("sr71")
    cold = compute_bfl(cfg)
    warm = compute_bfl(cfg, vr_hint=cold.k_VR + 0.015)
    assert warm.field_length_ft == pytest.approx(cold.field_length_ft, abs=3.0)
    assert warm.vr_optimization["evaluations"] < cold.vr_optimization["evaluations"]
    # a hint far from the optimum still walks to it
    far = compute_bfl(cfg, vr_hint=cold.k_VR + 0.12)
    assert far.field_length_ft == pytest.approx(cold.field_length_ft, abs=3.0)


def test_optimize_vr_flags_table_limited_optimum():
    """If the field length is still falling where the solves start failing (end of the
    thrust table), the result is the edge of the data, flagged as such."""
    cfg = load_config("sr71", overrides={"multipliers.k_CL": 0.8, "multipliers.k_CD": 0.75})
    r = compute_bfl(cfg)
    assert r.vr_optimization["limited_by_failed_solves"]
    assert any("not a true optimum" in w for w in r.warnings)
    w = compute_bfl(cfg, vr_hint=r.k_VR - 0.03)
    assert w.field_length_ft == pytest.approx(r.field_length_ft, abs=5.0)


# ---------------------------------------------------------------------------------
# trade studies
# ---------------------------------------------------------------------------------
def test_trade_study_grid_order_and_values():
    """Rows come back in grid order (last input fastest) even for unsorted values, and
    each row equals a single solve of that case."""
    from bfl import trade_study

    cfg = load_config("b747_100")
    vary = {"environment.weight_lbf": [700_000.0, 600_000.0], "multipliers.k_CD": [1.1, 0.9, 1.0]}
    df = trade_study(cfg, vary, outputs=("field_length_ft", "k_VR"), workers=1)
    assert list(df["environment.weight_lbf"]) == [700_000.0] * 3 + [600_000.0] * 3
    assert list(df["multipliers.k_CD"]) == [1.1, 0.9, 1.0] * 2
    assert (df["error"] == "").all()
    one = compute_bfl(cfg.with_updates({"environment.weight_lbf": 600_000.0,
                                        "multipliers.k_CD": 0.9}))  # fmt: skip
    assert df["field_length_ft"].iloc[4] == pytest.approx(one.field_length_ft, abs=1.0)


def test_trade_study_reports_failed_cases():
    from bfl import trade_study

    cfg = load_config("sr71")
    df = trade_study(cfg, {"multipliers.k_CL": [1.0, 0.75]}, workers=1)
    assert df["error"].iloc[0] == "" and df["error"].iloc[1] != ""
    assert math.isnan(df["field_length_ft"].iloc[1])
    with pytest.raises(Exception):  # noqa: B017 - a mistyped path fails before solving
        trade_study(cfg, {"multipliers.k_XX": [1.0]})
