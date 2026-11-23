"""Bridge between the UI and the bfl package. The app ONLY calls the public bfl API.

Results are cached on the JSON of the full validated RunConfig, so moving a slider
back to a previous value is instant. The expensive extras (V1 sweep, trade-study grids)
are computed only when asked for.
"""

from __future__ import annotations

import json
import math
import multiprocessing
import os
import time
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from bfl import RunConfig, compute_bfl, compute_landing, load_config, sweep_v1, trade_study
from bfl.atmosphere import RHO0_SLUGFT3
from bfl.model import build_model
from bfl.units import FTPS_TO_KTS

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

# forkserver: forking a process that has threads (the app's server) can deadlock
_MP = multiprocessing.get_context("forkserver")


def build_config(aircraft: str, ui: dict[str, Any]) -> RunConfig:
    """Translate UI control values into a validated RunConfig."""
    overrides = {
        "multipliers.k_CL": ui["k_cl"],
        "multipliers.k_CD": ui["k_cd"],
        "multipliers.k_T": ui.get("k_t", 1.0),
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


def _trajectory(tr, sqrt_sigma: float, weight_lbf: float) -> dict[str, Any]:
    df = tr.to_dataframe()
    stride = max(1, len(df) // MAX_ROWS)
    keep = np.zeros(len(df), dtype=bool)
    keep[::stride] = True
    keep[-1] = True
    keep[np.r_[True, df["phase"].to_numpy()[1:] != df["phase"].to_numpy()[:-1]]] = True
    sub = df[keep]
    out: dict[str, Any] = {k: sub[c].tolist() for k, c in TRAJ_COLS.items()}
    out["veas"] = (sub["V_air_kts"].to_numpy() * sqrt_sigma).tolist()  # KEAS, like V-speeds
    out["W"] = (weight_lbf - sub["fuel_burned_lbf"].to_numpy()).tolist()  # falls as fuel burns
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
    w0 = RunConfig.model_validate_json(cfg_json).weight_lbf
    sqrt_sigma = math.sqrt(res.density_slugft3 / RHO0_SLUGFT3)
    frames = []
    for name, label in (("go", "go (engine out)"), ("stop", "stop"), ("aeo", "all engines")):
        df = getattr(res, name).to_dataframe()
        df.insert(0, "branch", label)
        df.insert(df.columns.get_loc("V_air_kts") + 1, "V_eas_kts", df["V_air_kts"] * sqrt_sigma)
        df.insert(df.columns.get_loc("L_lbf"), "W_lbf", w0 - df["fuel_burned_lbf"])
        frames.append(df)
    return pd.concat(frames, ignore_index=True).to_csv(index=False, float_format="%.6g")


@lru_cache(maxsize=64)
def _run_cached(cfg_json: str) -> dict[str, Any]:
    cfg = RunConfig.model_validate_json(cfg_json)
    res, t_solve = _solve(cfg_json)
    sqrt_sigma = math.sqrt(res.density_slugft3 / RHO0_SLUGFT3)
    w0 = cfg.weight_lbf
    go = _trajectory(res.go, sqrt_sigma, w0)
    stop = _trajectory(res.stop, sqrt_sigma, w0)
    aeo = _trajectory(res.aeo, sqrt_sigma, w0)
    x_rest = _event(stop, "stopped")["x_ft"]
    scalars = res.scalars()
    landing: dict[str, Any] = {"ok": False}
    landing_tr = None
    try:
        lr = compute_landing(cfg)
        scalars.update(lr.scalars())
        scalars["runway_required_ft"] = max(
            scalars["field_length_ft"], scalars["landing_runway_required_ft"]
        )
        landing = {
            "ok": True,
            "summary": lr.summary(),
            "warnings": lr.warnings,
        }
        landing_tr = _trajectory(lr.trajectory, sqrt_sigma, lr.weight_lbf)
    except Exception as exc:  # noqa: BLE001 - the takeoff result stands on its own
        landing = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": True,
        "cfg_json": cfg_json,
        "scalars": scalars,
        "summary": res.summary() + (f"\n\n{landing['summary']}" if landing.get("ok") else ""),
        "landing": landing,
        "landing_tr": landing_tr,  # time history, same format as go / stop / aeo
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
TRADE_METRICS = (
    "bfl_ft",
    "field_length_ft",
    "aeo_distance_ft",
    "max_tire_speed_kts",
    "landing_runway_required_ft",
    "runway_required_ft",
)


_POOL: ProcessPoolExecutor | None = None


def _pool() -> ProcessPoolExecutor:
    global _POOL
    if _POOL is None:
        _POOL = ProcessPoolExecutor(mp_context=_MP, max_workers=max(1, (os.cpu_count() or 2) - 1))
    return _POOL


@lru_cache(maxsize=16)
def trade_map(
    cfg_json: str, kcl: tuple[float, ...], kcd: tuple[float, ...], warm_start: bool = True
) -> dict[str, Any]:
    """bfl.trade_study on a k_CL x k_CD grid, reshaped for the plots:
    z[metric][i][j] with row i = k_CL, column j = k_CD (None where a case failed)."""
    cfg = RunConfig.model_validate_json(cfg_json)
    t0 = time.perf_counter()
    try:
        df = trade_study(cfg, {"multipliers.k_CL": kcl, "multipliers.k_CD": kcd},
                         outputs=(*TRADE_METRICS, "balanced"), warm_start=warm_start,
                         executor=_pool())  # fmt: skip
    except (OSError, RuntimeError):  # e.g. no multiprocessing available: run serially
        df = trade_study(cfg, {"multipliers.k_CL": kcl, "multipliers.k_CD": kcd},
                         outputs=(*TRADE_METRICS, "balanced"), warm_start=warm_start,
                         workers=1)  # fmt: skip
    ok = df["error"] == ""

    def table(col: str) -> list[list]:
        vals = [v if good else None for v, good in zip(df[col], ok, strict=True)]
        n = len(kcd)
        return [vals[i * n : (i + 1) * n] for i in range(len(kcl))]  # grid order

    out: dict[str, Any] = {"k_CL": list(kcl), "k_CD": list(kcd), "z": {}}
    for name in TRADE_METRICS:
        out["z"][name] = [[None if v is None else float(v) for v in row] for row in table(name)]
    out["balanced"] = [[None if v is None else bool(v) for v in row] for row in table("balanced")]
    out["time_s"] = time.perf_counter() - t0
    return out


@lru_cache(maxsize=32)
def sweep(cfg_json: str, k_vr: float) -> dict[str, Any]:
    cfg = RunConfig.model_validate_json(cfg_json)
    df = sweep_v1(cfg, n=15, k_vr=k_vr)
    return df[["v1_kts", "d_go_ft", "d_stop_ft"]].to_dict(orient="list")


# ------------------------------------------------------------------------------------
# gust analysis (its own page; never part of the main run or the trade study)
# ------------------------------------------------------------------------------------
_TRACE_STRIDE = 5  # keep every 5th time step of the sample histories (plots only)


@lru_cache(maxsize=8)
def gusts(cfg_json: str, settings_json: str) -> dict[str, Any]:
    """bfl.gusts.gust_study, reshaped for the page (JSON-friendly)."""
    from bfl.gusts import GustSettings, gust_study

    cfg = RunConfig.model_validate_json(cfg_json)
    s = GustSettings(**json.loads(settings_json))
    try:
        res = gust_study(cfg, s, executor=_pool())
    except Exception:  # noqa: BLE001 - e.g. no multiprocessing: let it run serially
        res = gust_study(cfg, s)
    traces = {
        str(run): {k: df.iloc[::_TRACE_STRIDE].to_dict(orient="list") for k, df in parts.items()}
        for run, parts in res.traces.items()
    }
    vm = build_model(cfg)
    sch_ref = compute_bfl(cfg.with_updates({"solver.trajectory_dt_s": None}))
    return {
        "ok": True,
        "aircraft": res.aircraft_name,
        "rules": res.rules,
        "settings": json.loads(settings_json),
        "w20": s.w20,
        "samples": res.samples.to_dict(orient="list"),
        "calm": res.calm,
        "reference": res.reference,
        "percentiles": res.percentiles().to_dict(orient="records"),
        "traces": traces,
        "summary": res.summary(),
        "time_s": res.time_s,
        "dryden": res.dryden_at,
        "speeds": {"v_ef_kts": sch_ref.v_ef_kts, "vr_kts": sch_ref.vr_kts,
                   "v_s_kts": vm.tas_to_eas(vm.stall_speed_tas()) * FTPS_TO_KTS},
    }  # fmt: skip


@lru_cache(maxsize=8)
def gust_convergence(cfg_json: str, settings_json: str) -> dict[str, Any]:
    """Strong error vs time step for both methods (a quick version for the page)."""
    from bfl.gusts import GustSettings, convergence_study

    cfg = RunConfig.model_validate_json(cfg_json)
    s = GustSettings(**json.loads(settings_json))
    outs = ("go_ft", "stop_ft", "aeo_ft") if s.takeoff else ()
    outs += ("landing_distance_ft",) if s.landing else ()
    df = convergence_study(cfg, s, dts=(0.04, 0.02, 0.01, 0.005), ref_dt=0.00125, n_paths=8,
                           outputs=outs, executor=_pool())  # fmt: skip
    return df.to_dict(orient="list")


# ------------------------------------------------------------------------------------
# data uncertainty (its own page; never part of the main run or the trade study)
# ------------------------------------------------------------------------------------
@lru_cache(maxsize=8)
def uncertainty(cfg_json: str, settings_json: str) -> dict[str, Any]:
    """bfl.uncertainty.uncertainty_study, reshaped for the page (JSON-friendly)."""
    import numpy as np

    from bfl.uncertainty import UncertaintySettings, uncertainty_study

    cfg = RunConfig.model_validate_json(cfg_json)
    s = UncertaintySettings(**json.loads(settings_json))
    try:
        res = uncertainty_study(cfg, s, executor=_pool())
    except Exception:  # noqa: BLE001 - e.g. no multiprocessing: let it run serially
        res = uncertainty_study(cfg, s)
    main_out = "runway_required_ft" if s.landing else "takeoff_field_ft"
    sens = res.sensitivity(main_out)
    values = {c: [None if not np.isfinite(v) else float(v) for v in res.values(c)]
              for c in ("runway_required_ft", "takeoff_field_ft", "landing_runway_ft",
                        "bfl_ft", "aeo_ft") if c in res.samples}  # fmt: skip
    return {
        "ok": True,
        "aircraft": res.aircraft_name,
        "settings": json.loads(settings_json),
        "factors": res.samples[["k_CL", "k_CD", "k_T"]].to_dict(orient="list"),
        "values": values,  # None = no solution (needs more runway than any length)
        "errors": res.samples["error"].tolist(),
        "nominal": res.nominal,
        "percentiles": res.percentiles().to_dict(orient="records"),
        "sensitivity": sens.to_dict(orient="records"),
        "main_output": main_out,
        "failure_rate": res.failure_rate("takeoff_field_ft"),
        "failure_drivers": res.failure_drivers(),
        "surface": res.response_surface(main_out),
        "failure_model": res.failure_model(),
        "summary": res.summary(),
        "time_s": res.time_s,
    }  # fmt: skip
