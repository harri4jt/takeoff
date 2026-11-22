"""Data uncertainty: how much runway to plan when the lift, drag and thrust tables are
only known to within some percentage.

    from bfl import load_config
    from bfl.uncertainty import UncertaintySettings, uncertainty_study
    u = uncertainty_study(load_config("b747_100"),
                          UncertaintySettings(sigma_CL=0.04, sigma_CD=0.08, sigma_T=0.03))
    u.summary(); u.percentiles(); u.sensitivity()

Model
-----
The real aircraft's coefficients are the tables times unknown factors:
    CL = k_CL · CL_table,   CD = k_CD · CD_table,   T = k_T · T_table,
each factor normal with mean 1 and standard deviation sigma (the stated 1-sigma
uncertainty of that table), drawn independently and cut off at ±3 sigma (a factor can
never be negative). Each draw is one full solve: the balanced field length (with the
rotation-speed optimizer), the takeoff field length and the landing. The spread of the
answers over N draws is the runway uncertainty that the data uncertainty causes.

Sampling (both hand-written):
* Monte Carlo: each factor drawn independently at random.
* Latin hypercube: each factor's range is cut into N equally likely strata, one draw
  per stratum, and the strata are paired at random between factors. Every input is
  then covered evenly. That makes the *mean* far steadier than plain Monte Carlo when
  the answer is close to additive in the inputs (747: about 20x), but it does little
  for a tail percentile (P95: about the same as Monte Carlo), which is set by rare
  combinations of the inputs.

The factors multiply whatever multipliers the base case already has (e.g. the
simulator's k_CL slider), so "1" means "the tables as they are".
"""

from __future__ import annotations

import math
import multiprocessing
import os
import time
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass
from statistics import NormalDist
from typing import Any, Literal

import numpy as np
import pandas as pd

from .bfl import compute_bfl
from .config import RunConfig
from .landing import compute_landing

# forkserver: forking a process that has threads (the app's server) can deadlock
_MP = multiprocessing.get_context("forkserver")
_ND = NormalDist()

PARAMS = {  # factor: (label, config path)
    "k_CL": ("lift (CL table)", "multipliers.k_CL"),
    "k_CD": ("drag (CD table)", "multipliers.k_CD"),
    "k_T": ("thrust (thrust table)", "multipliers.k_T"),
}
OUTPUTS = {  # column: (label, unit)
    "runway_required_ft": ("Runway required (takeoff or landing)", "ft"),
    "takeoff_field_ft": ("Takeoff field length", "ft"),
    "landing_runway_ft": ("Landing runway required", "ft"),
    "bfl_ft": ("Balanced field length", "ft"),
    "aeo_ft": ("All-engines distance", "ft"),
}
# Starting points for the 1-sigma uncertainty of each table. JUDGEMENT VALUES, not
# from a standard: tables matched to test data are tighter than raw CFD / cycle-deck
# output, which is tighter than early estimates. Edit them to your own confidence.
PRESETS = {
    "validated": {"label": "Validated against test", "sigma_CL": 0.02, "sigma_CD": 0.04,
                  "sigma_T": 0.015},
    "typical": {"label": "Typical CFD / NPSS", "sigma_CL": 0.04, "sigma_CD": 0.08,
                "sigma_T": 0.03},
    "early": {"label": "Early concept estimate", "sigma_CL": 0.08, "sigma_CD": 0.15,
              "sigma_T": 0.05},
}  # fmt: skip


@dataclass
class UncertaintySettings:
    sigma_CL: float = 0.04  # 1-sigma relative uncertainty of the CL table
    sigma_CD: float = 0.08
    sigma_T: float = 0.03
    n: int = 500
    method: Literal["lhs", "mc"] = "lhs"
    seed: int = 1
    truncate: float = 3.0  # draws limited to ±this many sigma
    landing: bool = True

    def sigmas(self) -> dict[str, float]:
        return {"k_CL": self.sigma_CL, "k_CD": self.sigma_CD, "k_T": self.sigma_T}


def sample_factors(s: UncertaintySettings) -> pd.DataFrame:
    """N draws of (k_CL, k_CD, k_T): normal(1, sigma), cut at ±truncate sigma.

    Both methods map uniform numbers u in [Phi(-t), Phi(t)] through the inverse normal
    CDF, which gives the truncated normal exactly. Monte Carlo: u independent and
    uniform. Latin hypercube: u_i = (pi(i) + U_i) / N rescaled into that interval, with
    pi a random permutation per factor, so each of the N equally likely strata of every
    factor gets exactly one draw.
    """
    if s.n < 1:
        raise ValueError("n must be at least 1")
    rng = np.random.default_rng(s.seed)
    lo, hi = _ND.cdf(-s.truncate), _ND.cdf(s.truncate)
    cols = {}
    for name, sigma in s.sigmas().items():
        if sigma < 0:
            raise ValueError(f"{name}: sigma must be >= 0")
        if s.method == "lhs":
            u01 = (rng.permutation(s.n) + rng.random(s.n)) / s.n
        elif s.method == "mc":
            u01 = rng.random(s.n)
        else:
            raise ValueError(f"unknown sampling method {s.method!r}; use 'lhs' or 'mc'")
        u = lo + (hi - lo) * u01
        z = np.array([_ND.inv_cdf(float(v)) for v in u])
        cols[name] = 1.0 + sigma * z
    return pd.DataFrame(cols)


def quantile_ci_inf(x: np.ndarray, p: float, level: float = 0.95) -> tuple[float, float, float]:
    """Like gusts.quantile_ci but keeps +inf values (draws with no solution): the
    p-quantile is the order statistic at ceil(n p) (inverted CDF), so it is +inf when
    more than a share 1 - p of the draws have no solution."""
    x = np.sort(np.asarray(x, dtype=float))
    x = x[~np.isnan(x)]
    n = len(x)
    if n == 0:
        return math.nan, math.nan, math.nan
    z = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}.get(level, 1.96)
    k = min(n - 1, max(0, math.ceil(n * p) - 1))
    half = z * math.sqrt(n * p * (1.0 - p))
    lo = int(max(0, math.floor(n * p - half) - 1))
    hi = int(min(n - 1, math.ceil(n * p + half) - 1))
    return float(x[k]), float(x[lo]), float(x[hi])


TAKEOFF_COLS = ("takeoff_field_ft", "bfl_ft", "aeo_ft")
LANDING_COLS = ("landing_runway_ft",)


def _solve_cases(args: tuple) -> list[dict]:
    """Worker: full solves for a batch of factor draws. Takeoff and landing are solved
    (and can fail) independently; 'error' collects the messages."""
    cfg_json, rows, landing = args
    base = RunConfig.model_validate_json(cfg_json)
    m = base.multipliers
    out = []
    for i, kcl, kcd, kt in rows:
        row: dict[str, Any] = {"run": i, "k_CL": kcl, "k_CD": kcd, "k_T": kt}
        errors = []
        cfg = base.with_updates({"multipliers.k_CL": m.k_CL * kcl,
                                 "multipliers.k_CD": m.k_CD * kcd,
                                 "multipliers.k_T": m.k_T * kt})  # fmt: skip
        try:
            r = compute_bfl(cfg)
            row.update(takeoff_field_ft=r.field_length_ft, bfl_ft=r.bfl_ft,
                       aeo_ft=r.aeo_distance_ft, vr_kts=r.vr_kts, v1_kts=r.v1_kts,
                       balanced=bool(r.balanced),
                       max_tire_speed_kts=r.max_tire_speed_kts, takeoff_ok=True)  # fmt: skip
        except Exception as exc:  # noqa: BLE001 - no solution: counted, not dropped
            row["takeoff_ok"] = False
            errors.append(f"takeoff: {type(exc).__name__}: {exc}")
        if landing:
            try:
                row["landing_runway_ft"] = compute_landing(cfg).runway_required_ft
                row["landing_ok"] = True
            except Exception as exc:  # noqa: BLE001
                row["landing_ok"] = False
                errors.append(f"landing: {type(exc).__name__}: {exc}")
            if row["takeoff_ok"] and row["landing_ok"]:
                row["runway_required_ft"] = max(row["takeoff_field_ft"], row["landing_runway_ft"])
        row["error"] = "; ".join(errors)
        out.append(row)
    return out


@dataclass
class UncertaintyResult:
    settings: UncertaintySettings
    aircraft_name: str
    samples: pd.DataFrame
    nominal: dict[str, float]  # the tables as they are (all factors 1)
    time_s: float = 0.0

    @property
    def ok(self) -> pd.DataFrame:
        return self.samples[self.samples["error"] == ""]

    def solved(self, col: str) -> np.ndarray:
        """Boolean per draw: did the solve behind this output succeed?"""
        d = self.samples
        if col in TAKEOFF_COLS:
            return d["takeoff_ok"].to_numpy(bool)
        if col in LANDING_COLS:
            return d["landing_ok"].to_numpy(bool)
        ok = d["takeoff_ok"].to_numpy(bool)
        return ok & d["landing_ok"].to_numpy(bool) if "landing_ok" in d else ok

    def failure_rate(self, col: str = "takeoff_field_ft") -> float:
        """Share of draws with no solution for this output (e.g. no engine-out lift-off)."""
        return float(1.0 - self.solved(col).mean()) if len(self.samples) else 0.0

    def values(self, col: str) -> np.ndarray:
        """One value per draw; draws with no solution count as +inf (they need more
        runway than any finite length), so they are never dropped from percentiles."""
        x = self.samples[col].to_numpy(float) if col in self.samples else np.array([])
        return np.where(self.solved(col), x, np.inf)

    def percentiles(self, ps=(0.05, 0.5, 0.9, 0.95, 0.99)) -> pd.DataFrame:
        rows = []
        for col, (label, _) in OUTPUTS.items():
            if col not in self.samples:
                continue
            x = self.values(col)
            fin = x[np.isfinite(x)]
            nom = self.nominal.get(col, math.nan)
            r = {"output": col, "label": label, "nominal": nom,
                 "mean_solved": float(np.mean(fin)) if len(fin) else math.nan,
                 "std_solved": float(np.std(fin, ddof=1)) if len(fin) > 1 else math.nan,
                 "p_exceed_nominal": float(np.mean(x > nom + 0.5)),
                 "no_solution": self.failure_rate(col)}  # fmt: skip
            for p in ps:
                est, lo, hi = quantile_ci_inf(x, p)
                tag = f"p{round(100 * p)}"
                r[tag], r[f"{tag}_lo"], r[f"{tag}_hi"] = est, lo, hi
                r[f"{tag}_margin"] = est - nom
            rows.append(r)
        return pd.DataFrame(rows)

    def sensitivity(self, output: str = "runway_required_ft") -> pd.DataFrame:
        """Each factor's share of the output's variance.

        Least squares fit of the output on the standardized factors,
        y ~ b0 + sum_j b_j z_j with z_j = (k_j - 1) / sigma_j, over the draws that
        solved. share_j = b_j cov(z_j, y) / var(y): the shares add up to R^2, the part of
        the spread a straight-line model explains (the rest is curvature and
        interactions). For independent factors share_j = b_j^2 var(z_j) / var(y). Also
        reported: b_j, the change in the output for a +1-sigma change of that factor.
        """
        df = self.samples[self.solved(output)] if output in self.samples else self.samples
        if output not in df or len(df) < 5:
            return pd.DataFrame()
        names = [k for k, s in self.settings.sigmas().items() if s > 0]
        y = df[output].to_numpy(float)
        if not names:
            return pd.DataFrame()
        z = np.column_stack([(df[k].to_numpy(float) - 1.0) / self.settings.sigmas()[k]
                             for k in names])  # fmt: skip
        a = np.column_stack([np.ones(len(y)), z])
        coef, *_ = np.linalg.lstsq(a, y, rcond=None)
        var_y = float(np.var(y))
        fitted = a @ coef
        r2 = 1.0 - float(np.var(y - fitted)) / var_y if var_y > 0 else math.nan
        rows = []
        for j, k in enumerate(names):
            b = float(coef[j + 1])
            cov = float(np.mean((z[:, j] - z[:, j].mean()) * (y - y.mean())))
            share = b * cov / var_y if var_y > 0 else math.nan
            rows.append({"factor": k, "label": PARAMS[k][0], "per_sigma_ft": b,
                         "variance_share": share, "r2": r2})  # fmt: skip
        return pd.DataFrame(rows).sort_values("variance_share", ascending=False)

    def failure_drivers(self, output: str = "takeoff_field_ft") -> dict[str, float]:
        """Mean standardized factor (in sigmas) among the draws with no solution: which
        way the data has to be wrong for the aircraft not to make it at all."""
        bad = self.samples[~self.solved(output)]
        out = {}
        for k, sig in self.settings.sigmas().items():
            if sig > 0 and len(bad):
                out[k] = float(((bad[k] - 1.0) / sig).mean())
        return out

    def summary(self) -> str:
        s = self.settings
        lines = [
            f"Data uncertainty - {self.aircraft_name}",
            f"  1-sigma: CL {100 * s.sigma_CL:g} %, CD {100 * s.sigma_CD:g} %, thrust "
            f"{100 * s.sigma_T:g} %; {len(self.samples)} draws "
            f"({'Latin hypercube' if s.method == 'lhs' else 'Monte Carlo'}); {self.time_s:.1f} s",
        ]
        fr = self.failure_rate("takeoff_field_ft")
        if fr > 0:
            lines.append(f"  {100 * fr:.1f} % of draws: no takeoff solution (e.g. no engine-out "
                         "lift-off), counted as needing more runway than any length")  # fmt: skip
        for _, r in self.percentiles().iterrows():
            lines.append(
                f"  {r['label']:<40s} nominal {r['nominal']:>8,.0f}   P50 {r['p50']:>8,.0f}   "
                f"P95 {r['p95']:>8,.0f} ({r['p95_margin']:+,.0f})   P99 {r['p99']:>8,.0f} "
                f"({r['p99_margin']:+,.0f})"
            )
        sens = self.sensitivity("runway_required_ft" if s.landing else "takeoff_field_ft")
        if len(sens):
            parts = ", ".join(f"{r['label']} {100 * r['variance_share']:.0f} %"
                              for _, r in sens.iterrows())  # fmt: skip
            r2 = 100 * sens["r2"].iloc[0]
            lines.append(f"  share of the runway spread: {parts} (straight-line fit: {r2:.0f} %)")
        return "\n".join(lines)


def uncertainty_study(
    config: RunConfig,
    settings: UncertaintySettings | None = None,
    executor: Executor | None = None,
) -> UncertaintyResult:
    """Solve ``settings.n`` draws of the table factors (parallel)."""
    s = settings or UncertaintySettings()
    cfg = config.resolved().with_updates({"solver.trajectory_dt_s": None})
    t0 = time.perf_counter()
    factors = sample_factors(s)
    rows = [(i, *map(float, r)) for i, r in enumerate(factors[["k_CL", "k_CD", "k_T"]].to_numpy())]
    cfg_json = cfg.model_dump_json()
    workers = max(1, (os.cpu_count() or 2) - 1)
    chunk = max(1, math.ceil(len(rows) / (4 * workers)))
    jobs = [(cfg_json, rows[i : i + chunk], s.landing) for i in range(0, len(rows), chunk)]
    nominal_job = (cfg_json, [(-1, 1.0, 1.0, 1.0)], s.landing)
    parts = nom = None
    try:
        if executor is not None:
            nf = executor.submit(_solve_cases, nominal_job)
            parts = list(executor.map(_solve_cases, jobs))
            nom = nf.result()
        elif len(jobs) > 1:
            with ProcessPoolExecutor(mp_context=_MP, max_workers=min(workers, len(jobs) + 1)) as ex:
                nf = ex.submit(_solve_cases, nominal_job)
                parts = list(ex.map(_solve_cases, jobs))
                nom = nf.result()
    except Exception:  # noqa: BLE001 - no usable process pool here: run serially
        parts = nom = None
    if parts is None or nom is None:
        nom = _solve_cases(nominal_job)
        parts = [_solve_cases(j) for j in jobs]
    if nom[0]["error"]:
        raise RuntimeError(f"the nominal case failed: {nom[0]['error']}")
    nominal = {k: float(v) for k, v in nom[0].items() if k in OUTPUTS}
    samples = pd.DataFrame([r for p in parts for r in p])
    return UncertaintyResult(s, cfg.aircraft.name, samples, nominal, time.perf_counter() - t0)


__all__ = ["UncertaintySettings", "UncertaintyResult", "uncertainty_study", "sample_factors",
           "quantile_ci_inf",
           "PARAMS", "PRESETS", "OUTPUTS"]  # fmt: skip
