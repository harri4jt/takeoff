"""Bridge between the UI and the bfl package. The app ONLY calls the public bfl API.

Results are cached on the JSON of the full validated RunConfig, so moving a slider
back to a previous value is instant. The expensive extras (V1 sweep, trade-study grids)
are computed only when asked for.
"""

from __future__ import annotations

import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from typing import Any

import numpy as np

from bfl import RunConfig, compute_bfl, load_config, sweep_v1
from bfl.atmosphere import RHO0_SLUGFT3
from bfl.model import build_model
from bfl.units import FTPS_TO_KTS, KTS_TO_FTPS, RAD_TO_DEG

TRAJ_COLS = {
    "t": "t_s",
    "x": "x_ft",
    "h": "h_ft",
    "va": "V_air_kts",
    "vg": "V_ground_kts",
    "theta": "theta_deg",
    "alpha": "alpha_deg",
    "gamma": "gamma_deg",
    "T": "T_total_lbf",
    "D": "D_lbf",
    "L": "L_lbf",
    "N": "N_lbf",
    "F": "F_friction_lbf",
    "phase": "phase",
}
MAX_ROWS = 1500


def build_config(aircraft: str, ui: dict[str, Any]) -> RunConfig:
    """Translate UI control values into a validated RunConfig."""
    overrides = {
        "multipliers.k_CL": ui["k_cl"],
        "multipliers.k_CD": ui["k_cd"],
        "environment.mu_roll": ui["mu_roll"],
        "environment.mu_brake": ui["mu_brake"],
        "environment.headwind_kts": ui["headwind"],
        "environment.runway_slope_deg": ui["slope"],
        "environment.temperature_F": ui["temperature"],
        "environment.elevation_ft": ui["elevation"],
        "environment.weight_lbf": ui["weight"],
        "procedure.rotation_rate_deg_s": ui["rotation_rate"],
        "procedure.chute_enabled": bool(ui["chute"]),
        "procedure.enforce_v2_min": bool(ui.get("enforce_v2", True)),
        "procedure.rules": ui.get("rules", "part25"),
        "procedure.t_recog_s": ui.get("t_recog"),
        "environment.runway_available_ft": ui.get("runway_avail"),
    }
    if ui.get("thrust_table"):
        overrides["aircraft.engines.thrust_table"] = ui["thrust_table"]
    if ui.get("aero_config"):
        overrides["aircraft.aero.takeoff_configuration"] = ui["aero_config"]
    if "ground_effect" in ui:
        overrides["aircraft.ground_effect.enabled"] = bool(ui["ground_effect"])
    return load_config(aircraft, overrides=overrides)


def _trajectory(tr, sqrt_sigma: float) -> dict[str, Any]:
    df = tr.to_dataframe()
    stride = max(1, len(df) // MAX_ROWS)
    keep = np.zeros(len(df), dtype=bool)
    keep[::stride] = True
    keep[-1] = True
    keep[np.r_[True, df["phase"].to_numpy()[1:] != df["phase"].to_numpy()[:-1]]] = True
    sub = df[keep]
    out: dict[str, Any] = {k: sub[c].tolist() for k, c in TRAJ_COLS.items()}
    out["veas"] = (sub["V_air_kts"].to_numpy() * sqrt_sigma).tolist()  # KEAS, like V-speeds
    out["events"] = [e.__dict__ for e in tr.events]
    return out


def _event(tr: dict, name: str) -> dict | None:
    return next((e for e in tr["events"] if e["name"] == name), None)


@lru_cache(maxsize=64)
def _run_cached(cfg_json: str) -> dict[str, Any]:
    cfg = RunConfig.model_validate_json(cfg_json)
    t0 = time.perf_counter()
    res = compute_bfl(cfg)
    t_solve = time.perf_counter() - t0
    sqrt_sigma = math.sqrt(res.density_slugft3 / RHO0_SLUGFT3)
    go = _trajectory(res.go, sqrt_sigma)
    stop = _trajectory(res.stop, sqrt_sigma)
    aeo = _trajectory(res.aeo, sqrt_sigma)
    x_rest = _event(stop, "stopped")["x_ft"]
    return {
        "ok": True,
        "cfg_json": cfg_json,
        "scalars": res.scalars(),
        "summary": res.summary(),
        "warnings": res.warnings,
        "vr_adjustments": res.vr_adjustments,
        "go": go,
        "stop": stop,
        "aeo": aeo,
        "x_rest_ft": x_rest,
        "allowance_ft": res.d_stop_ft - x_rest,
        "sqrt_sigma": sqrt_sigma,
        "v2_min_ratio": cfg.procedure.resolved().v2_min_ratio,
        "solve_time_s": t_solve,
        "method": cfg.solver.method,
        "k_CL": cfg.multipliers.k_CL,
        "k_CD": cfg.multipliers.k_CD,
    }


def run(aircraft: str, ui: dict[str, Any]) -> dict[str, Any]:
    """Compute everything the main view shows. Errors are returned, not raised."""
    try:
        cfg = build_config(aircraft, ui)
        return _run_cached(cfg.model_dump_json())  # field order is fixed -> stable key
    except Exception as exc:  # noqa: BLE001 - show any failure in the readout
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ------------------------------------------------------------------------------------
# lazy details
# ------------------------------------------------------------------------------------
TRADE_METRICS = ("bfl_ft", "field_length_ft", "aeo_distance_ft")


def _trade_cell(args: tuple[str, float, float]) -> tuple | None:
    """(BFL/CFL, field length, AEO distance) at one (k_CL, k_CD); None if it fails."""
    cfg_json, k_cl, k_cd = args
    cfg = RunConfig.model_validate_json(cfg_json)
    try:
        r = compute_bfl(cfg.with_updates({"multipliers.k_CL": k_cl, "multipliers.k_CD": k_cd}))
        return (r.bfl_ft, r.field_length_ft, r.aeo_distance_ft, bool(r.balanced))
    except Exception:  # noqa: BLE001 - a failed cell is shown blank
        return None


_POOL: ProcessPoolExecutor | None = None


def _pool() -> ProcessPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor(max_workers=max(1, min(8, (os.cpu_count() or 2) - 1)))
    return _POOL


@lru_cache(maxsize=16)
def trade_map(cfg_json: str, kcl: tuple[float, ...], kcd: tuple[float, ...]) -> dict[str, Any]:
    """Full solves on a k_CL x k_CD grid for one configuration (parallel, RK45, no
    display re-run). z[metric][i][j]: row i = k_CL, column j = k_CD."""
    fast = RunConfig.model_validate_json(cfg_json).with_updates({"solver.trajectory_dt_s": None})
    fj = fast.model_dump_json()
    jobs = [(fj, a, b) for a in kcl for b in kcd]
    t0 = time.perf_counter()
    try:
        vals = list(_pool().map(_trade_cell, jobs, chunksize=4))
    except Exception:  # noqa: BLE001 - e.g. no multiprocessing available: run serially
        vals = [_trade_cell(j) for j in jobs]
    n = len(kcd)
    out: dict[str, Any] = {"k_CL": list(kcl), "k_CD": list(kcd), "z": {}, "balanced": []}
    for m, name in enumerate(TRADE_METRICS):
        flat = [None if v is None else v[m] for v in vals]
        out["z"][name] = [flat[i * n : (i + 1) * n] for i in range(len(kcl))]
    bal = [None if v is None else v[3] for v in vals]
    out["balanced"] = [bal[i * n : (i + 1) * n] for i in range(len(kcl))]
    out["time_s"] = time.perf_counter() - t0
    return out


@lru_cache(maxsize=32)
def sweep(cfg_json: str, k_vr: float) -> dict[str, Any]:
    cfg = RunConfig.model_validate_json(cfg_json)
    df = sweep_v1(cfg, n=15, k_vr=k_vr)
    return df[["v1_kts", "d_go_ft", "d_stop_ft"]].to_dict(orient="list")


@lru_cache(maxsize=32)
def aircraft_data(cfg_json: str) -> dict[str, Any]:
    """Aero tables (raw and with the multipliers) and the thrust curve, for display."""
    cfg = RunConfig.model_validate_json(cfg_json)
    vm = build_model(cfg)
    aero = vm.aero
    a0, a1 = aero.table.alpha_range_rad
    alpha = np.linspace(a0, a1, 241)
    cl_raw = aero.table.cl.evaluate(alpha)
    cd_raw = aero.table.cd.evaluate(alpha)
    knots = list(np.linspace(0.0, 200.0, 81))
    per = [vm.propulsion.model.per_engine(v * KTS_TO_FTPS, vm.temp_R) for v in knots]
    return {
        "alpha_deg": (alpha * RAD_TO_DEG).tolist(),
        "cl_raw": cl_raw.tolist(),
        "cd_raw": cd_raw.tolist(),
        "cl": (aero.k_CL * cl_raw).tolist(),
        "cd": (aero.k_CD * cd_raw).tolist(),
        "k_CL": aero.k_CL,
        "k_CD": aero.k_CD,
        "cl_max": aero.cl_max,
        "theta_ground_deg": vm.theta_ground_rad * RAD_TO_DEG,
        "theta_target_deg": vm.theta_target_rad * RAD_TO_DEG,
        "dCD_eo": aero.dCD_engine_out,
        "dCL_spoiler": aero.dCL_spoiler,
        "dCD_spoiler": aero.dCD_spoiler,
        "v_kts": knots,
        "thrust_per_engine": per,
        "idle_per_engine": vm.propulsion.idle_per_engine_lbf,
        "n_engines": vm.propulsion.n_engines,
        "temperature_F": vm.temp_R - 459.67,
        "weight_lbf": vm.weight_lbf,
        "S_ft2": vm.S_ft2,
        "v_s_kts": vm.tas_to_eas(vm.stall_speed_tas()) * FTPS_TO_KTS,
    }
