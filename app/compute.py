"""Bridge between the UI and the bfl package. The app ONLY calls compute_bfl / sweep_v1.

Results are cached on a hash of the full validated RunConfig, so moving a slider
back to a previous value is instant.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

import numpy as np

from bfl import RunConfig, compute_bfl, load_config, sweep_v1

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
SENS_VALUES = [0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2]
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
        "solver.method": ui.get("method", "rk4"),
    }
    return load_config(aircraft, overrides=overrides)


def _trajectory(tr) -> dict[str, list]:
    df = tr.to_dataframe()
    stride = max(1, len(df) // MAX_ROWS)
    keep = np.zeros(len(df), dtype=bool)
    keep[::stride] = True
    keep[-1] = True
    keep[np.r_[True, df["phase"].to_numpy()[1:] != df["phase"].to_numpy()[:-1]]] = True
    sub = df[keep]
    out = {k: sub[c].tolist() for k, c in TRAJ_COLS.items()}
    out["events"] = [e.__dict__ for e in tr.events]
    return out


def _sensitivity(cfg: RunConfig) -> dict[str, list]:
    """BFL vs k_CL and vs k_CD (RK45 for speed; agrees with RK4 to << 1 ft)."""
    fast = cfg.with_updates({"solver.method": "rk45"})
    out: dict[str, list] = {"k": SENS_VALUES, "k_CL": [], "k_CD": []}
    for name in ("k_CL", "k_CD"):
        for k in SENS_VALUES:
            try:
                r = compute_bfl(fast.with_updates({f"multipliers.{name}": k}))
                out[name].append(r.bfl_ft)
            except Exception:  # noqa: BLE001 - a failed point is shown as a gap
                out[name].append(None)
    return out


@lru_cache(maxsize=64)
def _run_cached(cfg_json: str) -> dict[str, Any]:
    cfg = RunConfig.model_validate_json(cfg_json)
    t0 = time.perf_counter()
    res = compute_bfl(cfg)
    t_solve = time.perf_counter() - t0
    sweep = sweep_v1(cfg.with_updates({"solver.method": "rk45"}), n=13)
    return {
        "ok": True,
        "scalars": res.scalars(),
        "warnings": res.warnings,
        "vr_adjustments": res.vr_adjustments,
        "sweep": sweep[["v1_kts", "d_go_ft", "d_stop_ft"]].to_dict(orient="list"),
        "go": _trajectory(res.go),
        "stop": _trajectory(res.stop),
        "aeo": _trajectory(res.aeo),
        "sens": _sensitivity(cfg),
        "solve_time_s": t_solve,
        "method": cfg.solver.method,
    }


def run(aircraft: str, ui: dict[str, Any]) -> dict[str, Any]:
    """Compute everything the UI shows. Errors are returned, not raised."""
    try:
        cfg = build_config(aircraft, ui)
        return _run_cached(cfg.model_dump_json())  # field order is fixed -> stable key
    except Exception as exc:  # noqa: BLE001 - show any failure in the readout
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
