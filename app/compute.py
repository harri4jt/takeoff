"""Bridge between the UI and the bfl package. The app ONLY calls the public bfl API.

Results are cached on the JSON of the full validated RunConfig, so moving a slider
back to a previous value is instant. The expensive "details" (V1 sweep, the k_CL x k_CD
heatmap) are computed lazily, only when the details panel is opened.
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
HEAT_VALUES = [0.8, 0.9, 1.0, 1.1, 1.2]
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
        "solver.method": ui.get("method", "rk4"),
    }
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
        "v2_min_ratio": cfg.procedure.v2_min_ratio,
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
def _heat_cell(args: tuple[str, float, float]) -> float | None:
    cfg_json, k_cl, k_cd = args
    cfg = RunConfig.model_validate_json(cfg_json)
    try:
        r = compute_bfl(cfg.with_updates({"multipliers.k_CL": k_cl, "multipliers.k_CD": k_cd}))
        return r.bfl_ft
    except Exception:  # noqa: BLE001 - a failed cell is shown blank
        return None


_POOL: ProcessPoolExecutor | None = None


def _pool() -> ProcessPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor(max_workers=max(1, min(8, (os.cpu_count() or 2) - 1)))
    return _POOL


@lru_cache(maxsize=32)
def heatmap(cfg_json: str) -> dict[str, Any]:
    """BFL on a k_CL x k_CD grid (RK45 for speed: agrees with RK4 to << 1 ft)."""
    fast = RunConfig.model_validate_json(cfg_json).with_updates({"solver.method": "rk45"})
    fj = fast.model_dump_json()
    jobs = [(fj, kcl, kcd) for kcl in HEAT_VALUES for kcd in HEAT_VALUES]
    t0 = time.perf_counter()
    try:
        vals = list(_pool().map(_heat_cell, jobs))
    except Exception:  # noqa: BLE001 - e.g. no multiprocessing available: run serially
        vals = [_heat_cell(j) for j in jobs]
    n = len(HEAT_VALUES)
    z = [vals[i * n : (i + 1) * n] for i in range(n)]  # rows = k_CL, cols = k_CD
    return {"k": HEAT_VALUES, "z": z, "time_s": time.perf_counter() - t0}


@lru_cache(maxsize=32)
def sweep(cfg_json: str, k_vr: float) -> dict[str, Any]:
    cfg = RunConfig.model_validate_json(cfg_json).with_updates({"solver.method": "rk45"})
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
