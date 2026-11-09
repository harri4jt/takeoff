"""Top-level API: compute_bfl (outer secant on V1) and sweep_v1, with the VR retry loop.

Speeds at this API are KEAS (equivalent airspeed in knots, ~KCAS at takeoff Mach).
Internally the dynamics use true airspeed in ft/s: V_TAS = V_EAS / sqrt(sigma).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import numpy as np
import pandas as pd

from .config import RunConfig
from .model import VehicleModel, build_model
from .results import BFLResult
from .rootfind import safeguarded_secant
from .takeoff import (
    Branch,
    Prefix,
    TakeoffError,
    TouchbackError,
    aeo_ground_roll,
    engine_failure_prefix,
    oei_v2_from_vr,
    simulate_aeo,
    simulate_go,
    simulate_stop,
)
from .units import FTPS_TO_KTS, KTS_TO_FTPS

T = TypeVar("T")


class BFLError(RuntimeError):
    """The BFL problem could not be solved (e.g. VR retries exhausted)."""


@dataclass
class _Context:
    """Per-k_VR solve context: model, reference speeds (TAS ft/s) and the cached AEO roll."""

    cfg: RunConfig
    vm: VehicleModel
    k_vr: float
    v_s: float
    v_r: float
    v1_min: float
    roll: object

    def eas_kts(self, v_tas: float) -> float:
        return self.vm.tas_to_eas(v_tas) * FTPS_TO_KTS

    def evaluate(self, v1: float) -> tuple[Branch, Branch, Prefix]:
        p, s = self.cfg.procedure, self.cfg.solver
        prefix = engine_failure_prefix(self.vm, self.roll, v1, p, s)
        go = simulate_go(self.vm, prefix, self.v_r, p, s)
        stop = simulate_stop(self.vm, prefix, p, s)
        return go, stop, prefix


def _context(cfg: RunConfig, k_vr: float) -> _Context:
    vm = build_model(cfg)
    v_s = vm.stall_speed_tas()
    v_r = k_vr * v_s
    if vm.v_mcg_eas_ftps is not None:
        v1_min = vm.eas_to_tas(vm.v_mcg_eas_ftps)
    else:
        v1_min = cfg.procedure.v1_min_fraction_of_vr * v_r
    if v1_min >= v_r:
        raise BFLError(f"V1_min ({v1_min * FTPS_TO_KTS:.1f} kt TAS) >= VR; no V1 range")
    roll = aeo_ground_roll(vm, v_r, cfg.solver)
    return _Context(cfg, vm, k_vr, v_s, v_r, v1_min, roll)


def _with_vr_retries(
    cfg: RunConfig, fn: Callable[[_Context], T]
) -> tuple[T, list[dict[str, Any]], list[str]]:
    """Run ``fn`` and, on a touchback, raise k_VR by vr_step and rerun everything."""
    proc = cfg.procedure
    k_vr = proc.k_VR
    adjustments: list[dict[str, Any]] = []
    warnings: list[str] = []
    for attempt in range(proc.max_vr_retries + 1):
        try:
            ctx = _context(cfg, k_vr)
            return fn(ctx), adjustments, warnings
        except TouchbackError as exc:
            new = round(k_vr + proc.vr_step, 10)
            adjustments.append(
                {"reason": "touchback", "attempt": attempt, "k_VR_old": k_vr, "k_VR_new": new}
            )
            warnings.append(f"touchback at k_VR={k_vr:.2f} ({exc}); raising k_VR to {new:.2f}")
            k_vr = new
    raise BFLError(
        f"touchback persists after {proc.max_vr_retries} VR increases (k_VR={k_vr:.2f}); "
        "the configuration cannot complete an OEI takeoff"
    )


# ------------------------------------------------------------------------------------
# compute_bfl
# ------------------------------------------------------------------------------------
def _solve(ctx: _Context) -> BFLResult:
    cfg = ctx.cfg
    s = cfg.solver
    warnings: list[str] = []
    aeo = simulate_aeo(ctx.vm, ctx.roll, cfg.procedure, s)

    cache: dict[float, tuple[Branch, Branch, Prefix]] = {}
    history: list[dict[str, float]] = []

    def f(v1: float) -> float:
        out = ctx.evaluate(v1)
        cache[v1] = out
        diff = out[0].distance_ft - out[1].distance_ft
        history.append(
            {
                "v1_kts": ctx.eas_kts(v1),
                "d_go_ft": out[0].distance_ft,
                "d_stop_ft": out[1].distance_ft,
                "diff_ft": diff,
            }
        )
        return diff

    f_lo = f(ctx.v1_min)
    f_hi = f(ctx.v_r)
    balanced = True
    reason = ""
    if f_lo > 0.0 > f_hi or f_lo < 0.0 < f_hi:
        res = safeguarded_secant(
            f,
            ctx.v1_min,
            ctx.v_r,
            xtol=1e-9,
            ftol=s.v1_tol_ft,
            maxiter=s.v1_maxiter,
            fa=f_lo,
            fb=f_hi,
        )
        if not res.converged:
            warnings.append(f"V1 solve did not converge ({res.message})")
        v1 = res.root
    elif f_hi >= 0.0 and f_lo >= 0.0:
        v1, balanced = ctx.v_r, False
        reason = "stop shorter than go even at V1 = VR; V1 = VR, go distance governs"
    else:
        v1, balanced = ctx.v1_min, False
        reason = "stop longer than go even at V1 = V1_min; V1 = V1_min, stop distance governs"
    if not balanced:
        warnings.append("UNBALANCED: " + reason)
    if v1 not in cache:
        f(v1)
    go, stop, prefix = cache[v1]
    warnings.extend(prefix.warnings)

    bfl = max(go.distance_ft, stop.distance_ft)
    aeo_d = aeo.distance_ft
    field = max(bfl, cfg.procedure.field_length_aeo_factor * aeo_d)
    v_s_k = ctx.eas_kts(ctx.v_s)
    v2_k = ctx.eas_kts(go.v2_tas)
    if ctx.vm.chute is not None:
        warnings.append("drag chute credited in the stop: outside FAA Part 25 rules")
    if cfg.aircraft.synthetic:
        warnings.append("aircraft data are SYNTHETIC (not a real airplane)")

    return BFLResult(
        bfl_ft=bfl,
        balanced=balanced,
        v1_kts=ctx.eas_kts(v1),
        vr_kts=ctx.eas_kts(ctx.v_r),
        v_ef_kts=ctx.eas_kts(prefix.v_ef_tas),
        v_s_kts=v_s_k,
        v_lof_kts=ctx.eas_kts(go.v_lof_tas),
        v2_kts=v2_k,
        aeo_distance_ft=aeo_d,
        faa_field_length_ft=field,
        d_go_ft=go.distance_ft,
        d_stop_ft=stop.distance_ft,
        go=go.trajectory(),
        stop=stop.trajectory(),
        aeo=aeo.trajectory(),
        k_VR=ctx.k_vr,
        v1_min_kts=ctx.eas_kts(ctx.v1_min),
        v1_ground_kts=float(prefix.y_v1[1]) * FTPS_TO_KTS,
        density_slugft3=ctx.vm.rho,
        v1_solver_history=history,
        warnings=warnings,
        aircraft_name=cfg.aircraft.name,
        synthetic=cfg.aircraft.synthetic,
        chute_used=ctx.vm.chute is not None,
        unbalanced_reason=reason,
    )


def _solve_at(cfg: RunConfig) -> BFLResult:
    """One BFL solve at cfg.procedure.k_VR (raised automatically on touchback)."""
    result, adjustments, warnings = _with_vr_retries(cfg, _solve)
    result.vr_adjustments = adjustments
    result.warnings = warnings + result.warnings
    return result


# V2 target is met with a small margin so round-off never leaves V2/V_S at 1.19999.
_V2_MARGIN = 5e-5
_K_VR_MAX = 2.0


def _k_vr_for_v2(cfg: RunConfig) -> tuple[float, float, dict[str, Any]]:
    """Smallest k_VR >= the configured one with V2/V_S >= v2_min_ratio.

    Part 25.107(c)/(e): VR must be chosen so that V2 (the speed at the screen height,
    one engine out) is at least V2_min = 1.2 V_S. A later rotation gives a faster
    liftoff and so a faster V2, so g(k_VR) = V2/V_S(k_VR) - target is increasing and
    a safeguarded secant solve finds the k_VR that just meets it.

    V2 depends on VR only (see takeoff.oei_v2_from_vr), so each evaluation of g is a
    single rotate-and-climb simulation, not a full BFL solve.

    Returns (k_VR, V2/V_S at the configured k_VR, info).
    """
    proc, solver = cfg.procedure, cfg.solver
    vm = build_model(cfg)
    v_s = vm.stall_speed_tas()
    target = proc.v2_min_ratio
    goal = target + _V2_MARGIN
    ratios: dict[float, float] = {}

    def ratio(k: float) -> float:
        try:
            r = oei_v2_from_vr(vm, k * v_s, proc, solver) / v_s
        except TouchbackError:
            r = 0.0  # settles back: VR far too low, push k_VR up
        ratios[k] = r
        return r

    k0 = proc.k_VR
    r0 = ratio(k0)
    if r0 >= target:
        return k0, r0, {"evaluations": 1, "converged": True}

    def g(k: float) -> float:
        return ratio(k) - goal

    # V2/V_S - k_VR is nearly constant (the speed gained between VR and 35 ft),
    # so a unit-slope step is a good first guess; widen until the root is bracketed.
    step = max(1.05 * (goal - r0), 1e-3) if r0 > 0 else 0.05
    k1 = k0 + step
    g1 = g(k1)
    while g1 < 0.0:
        step *= 2.0
        k1 = k0 + step
        if k1 > _K_VR_MAX:
            raise BFLError(
                f"cannot reach V2 >= {target:g} V_S even with k_VR = {_K_VR_MAX}; "
                "set procedure.enforce_v2_min = false to see the unconstrained result"
            )
        g1 = g(k1)
    res = safeguarded_secant(g, k0, k1, xtol=1e-7, ftol=_V2_MARGIN, maxiter=40, fa=r0 - goal, fb=g1)
    # the smallest evaluated k_VR that satisfies the constraint
    k_star = min(k for k, r in ratios.items() if r >= target)
    return k_star, r0, {"evaluations": len(ratios), "converged": res.converged}


def compute_bfl(config: RunConfig) -> BFLResult:
    """Solve for the balanced field length.

    1. (V2 rule, if procedure.enforce_v2_min) secant solve on k_VR so that
       V2 >= v2_min_ratio * V_S; cheap, because V2 depends on VR only.
    2. Outer loop: bracket-safeguarded secant on f(V1) = d_go(V1) - d_stop(V1) over
       [V1_min, VR]. Each f evaluation runs an inner secant solve for V_EF and
       simulates both branches.
    On a touchback the whole solve is rerun with k_VR += vr_step.
    """
    proc = config.procedure
    if not proc.enforce_v2_min:
        result = _solve_at(config)
        if result.v2_over_vs < proc.v2_min_ratio:
            result.warnings.append(
                f"V2/V_S = {result.v2_over_vs:.3f} < {proc.v2_min_ratio:g} "
                "(not enforced: procedure.enforce_v2_min = false)"
            )
        return result

    k0 = proc.k_VR
    k_star, r0, info = _k_vr_for_v2(config)
    if k_star == k0:
        return _solve_at(config)
    result = _solve_at(config.with_updates({"procedure.k_VR": k_star}))
    result.vr_adjustments = [
        {
            "reason": "v2_min",
            "k_VR_old": k0,
            "k_VR_new": k_star,
            "v2_evaluations": info["evaluations"],
            "converged": info["converged"],
        }
    ] + result.vr_adjustments
    result.warnings = [
        f"k_VR raised {k0:.3f} -> {k_star:.3f} so that V2 >= {proc.v2_min_ratio:g} V_S "
        f"(V2/V_S was {r0:.3f}; Part 25.107, {info['evaluations']} rotate-and-climb "
        "simulations)"
    ] + result.warnings
    return result


def sweep_v1(
    config: RunConfig,
    v1_values: Sequence[float] | None = None,
    n: int = 15,
    k_vr: float | None = None,
) -> pd.DataFrame:
    """Go and stop distances vs V1 (the classic crossing chart).

    The sweep runs at a fixed rotation speed. To draw the chart that belongs to a
    compute_bfl result (whose k_VR may have been raised for V2_min or touchback),
    pass ``k_vr=result.k_VR``.

    Args:
        k_vr: overrides procedure.k_VR for the sweep.
        v1_values: V1 values in KEAS; default ``n`` points evenly spaced in [V1_min, VR].
            Values outside [V1_min, VR] give NaN distances.
    Returns:
        DataFrame with v1_kts, d_go_ft, d_stop_ft, diff_ft, v_ef_kts, vr_kts, k_VR, plus the
        split x_v1_ft (brake release -> V1), go_after_v1_ft (V1 -> screen) and
        stop_after_v1_ft (V1 -> rest, excluding the 2-s allowance).
    """

    def run(ctx: _Context) -> pd.DataFrame:
        if v1_values is None:
            vals = list(np.linspace(ctx.eas_kts(ctx.v1_min), ctx.eas_kts(ctx.v_r), n))
        else:
            vals = list(v1_values)
        rows = []
        for v_k in vals:
            v1 = ctx.vm.eas_to_tas(v_k * KTS_TO_FTPS)
            row = {"v1_kts": v_k, "vr_kts": ctx.eas_kts(ctx.v_r), "k_VR": ctx.k_vr}
            if ctx.v1_min - 1e-9 <= v1 <= ctx.v_r + 1e-9:
                v1 = min(max(v1, ctx.v1_min), ctx.v_r)
                go, stop, prefix = ctx.evaluate(v1)
                x_v1 = float(prefix.y_v1[0])
                x_rest = float(stop.segments[-1].y_end[0])
                row.update(
                    d_go_ft=go.distance_ft,
                    d_stop_ft=stop.distance_ft,
                    diff_ft=go.distance_ft - stop.distance_ft,
                    v_ef_kts=ctx.eas_kts(prefix.v_ef_tas),
                    x_v1_ft=x_v1,
                    go_after_v1_ft=go.distance_ft - x_v1,
                    stop_after_v1_ft=x_rest - x_v1,
                )
            else:
                row.update(
                    d_go_ft=math.nan,
                    d_stop_ft=math.nan,
                    diff_ft=math.nan,
                    v_ef_kts=math.nan,
                    x_v1_ft=math.nan,
                    go_after_v1_ft=math.nan,
                    stop_after_v1_ft=math.nan,
                )
            rows.append(row)
        return pd.DataFrame(rows)

    if k_vr is not None:
        config = config.with_updates({"procedure.k_VR": k_vr})
    df, _, _ = _with_vr_retries(config, run)
    return df


__all__ = ["compute_bfl", "sweep_v1", "BFLError", "TakeoffError", "TouchbackError"]
