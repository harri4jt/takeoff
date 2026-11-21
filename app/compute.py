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
import pandas as pd

from bfl import RunConfig, compute_bfl, load_config, sweep_v1
from bfl.atmosphere import RHO0_SLUGFT3

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
        "procedure.optimize_vr": bool(ui.get("optimize_vr", True)),
    }
    for key, path in (
        ("rules", "procedure.rules"),
        ("t_recog", "procedure.t_recog_s"),
        ("runway_avail", "environment.runway_available_ft"),
    ):
        if ui.get(key) is not None:  # not on the main page any more; API callers only
            overrides[path] = ui[key]
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


@lru_cache(maxsize=16)
def _solve(cfg_json: str):
    """(BFLResult, solve time) for a config; shared by the view and the CSV download."""
    t0 = time.perf_counter()
    res = compute_bfl(RunConfig.model_validate_json(cfg_json))
    return res, time.perf_counter() - t0


def timestep_csv(cfg_json: str) -> str:
    """Every time step of the three branches (go, stop, all engines) as one CSV.

    These are the time histories the plots and animation use: RK4 at the display step
    (solver.trajectory_dt_s) at the solved V1 and VR, plus every event point. Speeds in
    knots (V_air_kts is true airspeed, V_eas_kts equivalent), distances in ft."""
    res, _ = _solve(cfg_json)
    sqrt_sigma = math.sqrt(res.density_slugft3 / RHO0_SLUGFT3)
    frames = []
    for name, label in (("go", "go (engine out)"), ("stop", "stop"), ("aeo", "all engines")):
        df = getattr(res, name).to_dataframe()
        df.insert(0, "branch", label)
        df.insert(df.columns.get_loc("V_air_kts") + 1, "V_eas_kts", df["V_air_kts"] * sqrt_sigma)
        frames.append(df)
    return pd.concat(frames, ignore_index=True).to_csv(index=False, float_format="%.6g")


@lru_cache(maxsize=64)
def _run_cached(cfg_json: str) -> dict[str, Any]:
    cfg = RunConfig.model_validate_json(cfg_json)
    res, t_solve = _solve(cfg_json)
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
        # the 2-s pad exists only under Part 25; elsewhere any difference is round-off
        # between the RK45 distance and the RK4 display re-run
        "allowance_ft": (
            res.d_stop_ft - x_rest if cfg.resolved().procedure.t_v1_allowance_s > 0 else 0.0
        ),
        "sqrt_sigma": sqrt_sigma,
        "v2_min_ratio": cfg.resolved().procedure.v2_min_ratio,
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
TRADE_METRICS = ("bfl_ft", "field_length_ft", "aeo_distance_ft", "max_tire_speed_kts")


def _trade_cells(args: tuple[str, float, tuple[float, ...], bool]) -> list[tuple | None]:
    """Solve a run of cells along k_CD at one k_CL, in order.

    Each entry is (BFL, field length, AEO distance, max tire speed, balanced), or None
    if that cell fails. With VR optimization on, each cell's optimal k_VR is the warm
    start (``vr_hint``) for the next one: neighbouring cells have nearly the same
    optimum, so a local search around it replaces the upward scan.
    """
    cfg_json, k_cl, kcds, warm = args
    cfg = RunConfig.model_validate_json(cfg_json)
    hint: float | None = None
    out: list[tuple | None] = []
    for k_cd in kcds:
        try:
            r = compute_bfl(
                cfg.with_updates({"multipliers.k_CL": k_cl, "multipliers.k_CD": k_cd}),
                vr_hint=hint if warm else None,
            )
            hint = r.k_VR
            out.append(
                (r.bfl_ft, r.field_length_ft, r.aeo_distance_ft, r.max_tire_speed_kts,
                 bool(r.balanced))
            )  # fmt: skip
        except Exception:  # noqa: BLE001 - a failed cell is shown blank
            out.append(None)
    return out


_POOL: ProcessPoolExecutor | None = None


def _pool() -> ProcessPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor(max_workers=max(1, min(8, (os.cpu_count() or 2) - 1)))
    return _POOL


@lru_cache(maxsize=16)
def trade_map(
    cfg_json: str, kcl: tuple[float, ...], kcd: tuple[float, ...], warm_start: bool = True
) -> dict[str, Any]:
    """Full solves on a k_CL x k_CD grid for one configuration (parallel, RK45, no
    display re-run). z[metric][i][j]: row i = k_CL, column j = k_CD.

    Each row is split at its middle into two runs that walk outward along k_CD, one
    parallel task each, so the VR optimizer can warm-start every cell from its
    neighbour (``warm_start``; see _trade_cells).
    """
    fast = RunConfig.model_validate_json(cfg_json).with_updates({"solver.trajectory_dt_s": None})
    fj = fast.model_dump_json()
    n = len(kcd)
    mid = n // 2
    right = tuple(range(mid, n))  # middle -> high k_CD
    left = tuple(range(mid - 1, -1, -1))  # just below the middle -> low k_CD
    runs = [(i, idx) for i in range(len(kcl)) for idx in (right, left) if idx]
    jobs = [(fj, kcl[i], tuple(kcd[j] for j in idx), warm_start) for i, idx in runs]
    t0 = time.perf_counter()
    try:
        chunks = list(_pool().map(_trade_cells, jobs))
    except Exception:  # noqa: BLE001 - e.g. no multiprocessing available: run serially
        chunks = [_trade_cells(j) for j in jobs]
    vals: list[list[tuple | None]] = [[None] * n for _ in kcl]
    for (i, idx), chunk in zip(runs, chunks, strict=True):
        for j, v in zip(idx, chunk, strict=True):
            vals[i][j] = v
    out: dict[str, Any] = {"k_CL": list(kcl), "k_CD": list(kcd), "z": {}, "balanced": []}
    for m, name in enumerate(TRADE_METRICS):
        out["z"][name] = [[None if v is None else v[m] for v in row] for row in vals]
    out["balanced"] = [[None if v is None else v[len(TRADE_METRICS)] for v in row] for row in vals]
    out["time_s"] = time.perf_counter() - t0
    return out


@lru_cache(maxsize=32)
def sweep(cfg_json: str, k_vr: float) -> dict[str, Any]:
    cfg = RunConfig.model_validate_json(cfg_json)
    df = sweep_v1(cfg, n=15, k_vr=k_vr)
    return df[["v1_kts", "d_go_ft", "d_stop_ft"]].to_dict(orient="list")
