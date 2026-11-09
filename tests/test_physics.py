"""Physics verification (spec 9.3): analytic ground roll, balance, monotonicity,
directional sanity, step-size independence, touchback guard."""

from __future__ import annotations

import math

import numpy as np
import pytest

from bfl import BFLError, compute_bfl, load_config, sweep_v1
from bfl.atmosphere import atmosphere, isa_pressure_psf
from bfl.dynamics import SegmentParams
from bfl.model import build_model
from bfl.phases import airspeed_event, run_segment
from bfl.units import G0_FTPS2

from .conftest import make_simple_aircraft


# ---------------------------------------------------------------------------------
# atmosphere
# ---------------------------------------------------------------------------------
def test_isa_reference_values():
    sl = atmosphere(0.0)
    assert sl.density_slugft3 == pytest.approx(0.0023769, rel=1e-4)
    # standard tables: 5000 ft -> p = 1760.9 psf, rho = 0.0020482 slug/ft^3
    assert isa_pressure_psf(5000.0) == pytest.approx(1760.9, rel=1e-3)
    assert atmosphere(5000.0).density_slugft3 == pytest.approx(0.0020482, rel=1e-3)
    hot = atmosphere(0.0, temperature_F=100.0)
    assert hot.density_slugft3 < sl.density_slugft3


# ---------------------------------------------------------------------------------
# analytic ground roll
# ---------------------------------------------------------------------------------
@pytest.mark.parametrize("method", ["rk4", "rk45"])
def test_analytic_ground_roll(tmp_path, method):
    CL, CD, T1, S, W, mu = 0.6, 0.06, 30000.0, 2000.0, 150000.0, 0.03
    d = make_simple_aircraft(tmp_path, CL, CD, T1, S, W)
    cfg = load_config(d, overrides={"environment.mu_roll": mu, "solver.method": method})
    vm = build_model(cfg)
    m, rho = W / G0_FTPS2, vm.rho
    T = 2 * T1
    A = T - mu * m * G0_FTPS2
    B = 0.5 * rho * S * (CD - mu * CL)

    def x_exact(v):
        return m / (2 * B) * math.log(A / (A - B * v * v))

    p = SegmentParams(vm, "aeo_roll", 2, mu=mu)
    for v_target in (100.0, 200.0, 250.0):
        seg = run_segment(
            "ground",
            p,
            0.0,
            [0.0, 0.0],
            500.0,
            [airspeed_event("ground", p, v_target, "v")],
            cfg.solver,
        )
        x_num = seg.y_end[0]
        assert seg.y_end[1] == pytest.approx(v_target, abs=1e-6)
        assert x_num == pytest.approx(x_exact(v_target), rel=1e-8)


# ---------------------------------------------------------------------------------
# BFL solution properties
# ---------------------------------------------------------------------------------
def test_balance(base_result, base_cfg):
    r = base_result
    assert r.balanced
    assert abs(r.d_go_ft - r.d_stop_ft) < base_cfg.solver.v1_tol_ft
    assert r.v1_min_kts <= r.v1_kts <= r.vr_kts
    assert r.v_ef_kts < r.v1_kts
    assert r.faa_field_length_ft >= r.bfl_ft
    assert r.faa_field_length_ft >= 1.15 * r.aeo_distance_ft - 1e-6


def test_trajectory_frames(base_result):
    df = base_result.go.to_dataframe()
    assert set(df["phase"]) == {"aeo_roll", "oei_recog", "oei_roll", "rotation", "airborne"}
    assert df["h_ft"].iloc[-1] == pytest.approx(35.0, abs=1e-6)
    st = base_result.stop.to_dataframe()
    assert st["V_ground_kts"].iloc[-1] == pytest.approx(0.0, abs=1e-6)
    assert "braking" in set(st["phase"])
    assert np.all(np.diff(df["t_s"]) >= 0)


def test_sweep_monotonic(base_cfg):
    df = sweep_v1(base_cfg, n=8)
    assert np.all(np.diff(df["d_go_ft"]) < 0)
    assert np.all(np.diff(df["d_stop_ft"]) > 0)


def test_step_size_independence(base_cfg, base_result):
    fine = compute_bfl(base_cfg.with_updates({"solver.dt_s": 0.005}))
    assert abs(fine.bfl_ft - base_result.bfl_ft) / base_result.bfl_ft < 1e-3
    rk45 = compute_bfl(base_cfg.with_updates({"solver.method": "rk45"}))
    assert abs(rk45.bfl_ft - base_result.bfl_ft) / base_result.bfl_ft < 1e-3


# ---------------------------------------------------------------------------------
# directional sanity
# ---------------------------------------------------------------------------------
SHORTER = [
    {"environment.mu_brake": 0.40},
    {"procedure.chute_enabled": True},
    {"environment.headwind_kts": 15.0},
]
LONGER = [
    {"aircraft.aero.delta_CD_engine_out": 0.010},
    {"environment.temperature_F": 100.0},
    {"environment.elevation_ft": 5000.0},
    {"environment.weight_lbf": 850000.0},
]


@pytest.mark.parametrize("upd", SHORTER, ids=lambda u: next(iter(u)))
def test_changes_that_shorten_bfl(base_cfg, base_result, upd):
    assert compute_bfl(base_cfg.with_updates(upd)).bfl_ft < base_result.bfl_ft


@pytest.mark.parametrize("upd", LONGER, ids=lambda u: next(iter(u)))
def test_changes_that_lengthen_bfl(base_cfg, base_result, upd):
    assert compute_bfl(base_cfg.with_updates(upd)).bfl_ft > base_result.bfl_ft


def test_uphill_slope_longer_go_shorter_stop(base_cfg, base_result):
    # At a fixed V1 the uphill *acceleration* to V1 is longer, so the total accelerate-stop
    # distance can grow; the effect of slope on the stop itself is in the V1 -> rest part.
    v1 = [base_result.v1_kts]
    flat = sweep_v1(base_cfg, v1).iloc[0]
    up = sweep_v1(base_cfg.with_updates({"environment.runway_slope_deg": 1.0}), v1).iloc[0]
    assert up.d_go_ft > flat.d_go_ft
    assert up.go_after_v1_ft > flat.go_after_v1_ft
    assert up.x_v1_ft > flat.x_v1_ft
    assert up.stop_after_v1_ft < flat.stop_after_v1_ft
    down = sweep_v1(base_cfg.with_updates({"environment.runway_slope_deg": -1.0}), v1).iloc[0]
    assert down.stop_after_v1_ft > flat.stop_after_v1_ft


def test_multipliers_move_bfl(base_cfg, base_result):
    more_lift = compute_bfl(base_cfg.with_updates({"multipliers.k_CL": 1.1}))
    more_drag = compute_bfl(base_cfg.with_updates({"multipliers.k_CD": 1.1}))
    assert more_lift.bfl_ft < base_result.bfl_ft
    assert more_lift.v_s_kts < base_result.v_s_kts
    assert more_drag.bfl_ft > base_result.bfl_ft


# ---------------------------------------------------------------------------------
# touchback guard and edge cases
# ---------------------------------------------------------------------------------
UNDERPOWERED = {
    "environment.weight_lbf": 850000.0,
    "aircraft.attitude.theta_tailstrike_deg": 14.0,
    "multipliers.k_CD": 1.4,
    "procedure.k_VR": 1.01,
    "procedure.enforce_v2_min": False,  # isolate the touchback mechanism
}


def test_touchback_guard_raises_vr(base_cfg):
    r = compute_bfl(base_cfg.with_updates(UNDERPOWERED))
    assert r.vr_adjustments, "expected at least one VR increase"
    assert r.k_VR > 1.01
    assert r.k_VR == pytest.approx(1.01 + 0.01 * len(r.vr_adjustments))
    assert any("touchback" in w for w in r.warnings)
    assert r.go.to_dataframe()["h_ft"].min() >= -0.01


def test_v2_min_enforced(base_cfg, base_result):
    """Part 25.107: k_VR is raised by a root solve until V2 >= 1.2 V_S (and no further)."""
    free = compute_bfl(base_cfg.with_updates({"procedure.enforce_v2_min": False}))
    assert free.v2_over_vs < 1.2  # the synthetic aircraft needs the correction
    assert any("not enforced" in w for w in free.warnings)
    assert 1.2 <= base_result.v2_over_vs < 1.2 + 2e-4
    assert base_result.k_VR > free.k_VR
    assert base_result.bfl_ft > free.bfl_ft  # rotating later costs runway
    adj = [a for a in base_result.vr_adjustments if a["reason"] == "v2_min"]
    assert len(adj) == 1 and adj[0]["converged"]
    # a k_VR that already satisfies the rule is left alone
    high = compute_bfl(base_cfg.with_updates({"procedure.k_VR": 1.2}))
    assert high.k_VR == 1.2 and not high.vr_adjustments


def test_v2_depends_on_vr_only(base_cfg, base_result):
    """The cheap rotate-and-climb V2 equals the V2 of the full go branch at the solved V1."""
    from bfl.model import build_model
    from bfl.takeoff import oei_v2_from_vr
    from bfl.units import KTS_TO_FTPS

    cfg = base_cfg.with_updates({"procedure.k_VR": base_result.k_VR})
    vm = build_model(cfg)
    v2 = oei_v2_from_vr(vm, base_result.k_VR * vm.stall_speed_tas(), cfg.procedure, cfg.solver)
    assert vm.tas_to_eas(v2) / KTS_TO_FTPS == pytest.approx(base_result.v2_kts, abs=1e-6)


def test_sweep_matches_result_k_vr(base_cfg, base_result):
    """The V1 sweep at the result's k_VR crosses at the BFL."""
    v1 = base_result.v1_kts
    row = sweep_v1(base_cfg, [v1], k_vr=base_result.k_VR).iloc[0]
    assert row.d_go_ft == pytest.approx(base_result.bfl_ft, abs=0.1)
    assert row.d_stop_ft == pytest.approx(base_result.bfl_ft, abs=0.1)


def test_v1_equal_vr_edge(base_cfg):
    """Regression: V1 = VR (unbalanced, go governs) must not step outside the cached roll."""
    cfg = base_cfg.with_updates(
        {
            "solver.method": "rk45",
            "procedure.chute_enabled": True,
            "multipliers.k_CL": 0.9,
            "multipliers.k_CD": 0.8,
        }
    )
    r = compute_bfl(cfg)
    assert r.bfl_ft > 0 and r.v2_over_vs >= 1.2


def test_touchback_retries_exhausted(base_cfg):
    with pytest.raises(BFLError):
        compute_bfl(base_cfg.with_updates({**UNDERPOWERED, "procedure.max_vr_retries": 0}))


def test_zero_recognition_time(base_cfg):
    r = compute_bfl(base_cfg.with_updates({"procedure.t_recog_s": 0.0}))
    assert r.v_ef_kts == pytest.approx(r.v1_kts, abs=1e-6)
    assert r.balanced


def test_unbalanced_reported(base_cfg):
    # huge V_mcg pins V1_min close to VR: stop is longer everywhere -> V1 = V1_min
    r = compute_bfl(base_cfg.with_updates({"aircraft.speeds.V_mcg_kts": 163.0}))
    assert not r.balanced
    assert r.v1_kts == pytest.approx(163.0, abs=1e-6)
    assert r.bfl_ft == pytest.approx(r.d_stop_ft)
