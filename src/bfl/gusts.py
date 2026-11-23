"""Takeoff and landing in gusty wind: a stochastic side analysis.

The question: on a day with gusts of a given strength, flying the normal (calm-day)
schedule, how is the runway actually used spread out, and how much more than the calm
answer covers 95 % or 99 % of takeoffs and landings?

    from bfl import load_config
    from bfl.gusts import GustSettings, gust_study
    g = gust_study(load_config("b747_100"), GustSettings(intensity="moderate", n=500))
    g.summary(); g.samples (one row per realization); g.percentiles()

Model
-----
* Wind = the steady headwind of the run + two random gust components: u_g along the
  runway (+ headwind) and w_g vertical (+ up). Each is an Ornstein-Uhlenbeck process

      du_g = -u_g / T_u dt + sigma_u sqrt(2 / T_u) dW_1,     T_u = L_u / V

  (likewise w_g), whose spread sigma and length scale L come from the Dryden
  low-altitude model (MIL-F-8785C / MIL-HDBK-1797) for the wind speed at 20 ft, W20:
      sigma_w = 0.1 W20,  sigma_u = sigma_w / (0.177 + 0.000823 h)^0.4,
      L_w = h,  L_u = h / (0.177 + 0.000823 h)^1.2     (h in ft, 10 <= h <= 1000).
  V is the airspeed relative to the turbulence (at least 10 kt, so gusts still move
  past an aircraft at rest). Intensities: light W20 = 15 kt, moderate 30, severe 45.
  The wing feels gusts averaged over its span (``span_average``): near the ground
  Dryden's vertical length scale is the height (~10 ft), far shorter than a wing.
* The aircraft is written in the ground frame, state [x, h, u, w] (ground velocities),
  so the wind enters only through the airspeed and angle of attack the wing sees:
  air-relative velocity (u + V_w + u_g, w - w_g). With no gusts this is the same physics
  as the main solver.
* The crew flies the calm-day schedule (V_EF, V1, VR, approach speed from the main
  solver) and acts on indicated airspeed, in which the gust part is lagged by a 1 s
  first-order filter (pilot and instrument response): indicated = u + V_w + filtered u_g.
* Takeoff: an all-engines roll until indicated airspeed reaches V_EF; there the go, the
  stop and the all-engines takeoff branch off, all with the same gust history.
  Landing: glide on the glide slope at the approach speed (+ optional additive), flare at
  constant load factor at idle, touchdown, free roll, braking, as in the main solver.
* Integration: Euler-Maruyama or stochastic Heun (bfl.sde) at a fixed step. Procedural
  switches take effect at the next step and crossings (screen height, stop) are located
  by linear interpolation within the step, consistent with first-order methods.

Per realization the outputs are the go, stop and all-engines distances, the takeoff
field length (as the rules define it, but from this realization), the landing distance
and landing runway required.
"""

from __future__ import annotations

import math
import multiprocessing
import os
import time
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from .bfl import compute_bfl
from .config import RunConfig
from .landing import compute_landing, landing_config
from .model import VehicleModel, build_model
from .sde import METHOD_NAMES, get_step
from .units import DEG_TO_RAD, FTPS_TO_KTS, KTS_TO_FTPS

INTENSITY_W20_KTS = {"light": 15.0, "moderate": 30.0, "severe": 45.0}
V_FLOOR = 10.0 * KTS_TO_FTPS  # turbulence moves past at least this fast
H_MIN, H_MAX = 10.0, 1000.0  # Dryden low-altitude range [ft]

OUTPUTS = {  # column: (label, unit)
    "runway_required_ft": ("Runway required (takeoff or landing)", "ft"),
    "takeoff_field_ft": ("Takeoff field length", "ft"),
    "engine_out_ft": ("Engine-out field (max of go, stop)", "ft"),
    "go_ft": ("Continued takeoff (go)", "ft"),
    "stop_ft": ("Rejected takeoff (stop)", "ft"),
    "aeo_ft": ("All-engines distance", "ft"),
    "landing_distance_ft": ("Landing distance", "ft"),
    "landing_runway_ft": ("Landing runway required", "ft"),
}

# forkserver: forking a process that has threads (the app's server) can deadlock
_MP = multiprocessing.get_context("forkserver")


@dataclass
class GustSettings:
    intensity: Literal["light", "moderate", "severe", "custom"] = "moderate"
    w20_kts: float | None = None  # only for "custom"
    vertical: bool = True
    n: int = 500
    method: Literal["em", "heun"] = "heun"
    dt_s: float = 0.01
    seed: int = 1
    filter_s: float = 1.0  # lag on the gust part of indicated airspeed
    approach_additive_kts: float = 0.0
    takeoff: bool = True
    landing: bool = True
    n_traces: int = 3  # realizations whose time histories are kept

    @property
    def w20(self) -> float:
        if self.intensity == "custom":
            if self.w20_kts is None:
                raise ValueError("custom intensity: give w20_kts")
            return float(self.w20_kts)
        return INTENSITY_W20_KTS[self.intensity]


def span_average(sigma: float, length: float, span: float | None) -> tuple[float, float]:
    """(sigma, L) of a gust as the wing feels it: averaged over its span.

    For an exponentially correlated gust (correlation length L) averaged uniformly over a
    span of r = b / L correlation lengths, the variance falls by
        f(r) = 2 (r - 1 + e^-r) / r^2
    while the spectrum at zero frequency (the slow content that moves the aircraft) is
    unchanged, so the integral length scale grows to L / f(r). Short gusts that the
    span averages out are removed; an OU process with these values keeps the rest.
    """
    if not span or span <= 0.0:
        return sigma, length
    r = span / length
    f = 2.0 * (r - 1.0 + math.exp(-r)) / (r * r) if r > 1e-6 else 1.0
    return sigma * math.sqrt(f), length / f


def dryden(
    h_ft: float, w20_kts: float, span_ft: float | None = None
) -> tuple[float, float, float, float]:
    """(sigma_u, sigma_w [ft/s], L_u, L_w [ft]) at height h (clamped to 10..1000 ft),
    span-averaged over the wing if its span is known."""
    h = min(max(h_ft, H_MIN), H_MAX)
    base = 0.177 + 0.000823 * h
    sw = 0.1 * w20_kts * KTS_TO_FTPS
    su, lu = span_average(sw / base**0.4, h / base**1.2, span_ft)
    sw, lw = span_average(sw, h, span_ft)
    return su, sw, lu, lw


def gust_signal(
    w20_kts: float,
    h_ft: float,
    v_kts: float,
    t_end_s: float = 60.0,
    dt_s: float = 0.01,
    method: str = "heun",
    seed: int = 1,
    span_ft: float | None = None,
    n_paths: int = 1,
) -> dict[str, Any]:
    """Gust histories at a fixed height and airspeed, made exactly as in a gusty run.

    Dryden gives (sigma, L) for each component at height h (span-averaged if the span is
    given); the airspeed turns the length into a memory T = L / V; the Ornstein-Uhlenbeck
    SDE  dg = -g/T dt + sigma sqrt(2/T) dW  is stepped with the same SDE step as the
    simulation (bfl.sde). Each path starts from the stationary distribution N(0, sigma^2).

    Returns t [s], u and w [kt] with shape (steps + 1, n_paths), and sigma_u, sigma_w [kt],
    L_u, L_w [ft], T_u, T_w [s]. Used to check the generator against its targets
    (variance sigma^2, correlation e^(-tau/T)) and for the figures.
    """
    su, sw, lu, lw = dryden(h_ft, w20_kts, span_ft)
    v = max(v_kts * KTS_TO_FTPS, V_FLOOR)
    tu, tw = lu / v, lw / v
    step = get_step(method)
    n = int(round(t_end_s / dt_s))
    rng = np.random.default_rng(seed)
    y = [su * rng.standard_normal(n_paths), sw * rng.standard_normal(n_paths)]
    out = np.empty((n + 1, 2, n_paths))
    out[0] = y
    dw = rng.standard_normal((n, 2, n_paths)) * math.sqrt(dt_s)
    gu, gw = su * math.sqrt(2.0 / tu), sw * math.sqrt(2.0 / tw)
    drift = lambda _t, yy: [-yy[0] / tu, -yy[1] / tw]  # noqa: E731
    diff = lambda _t, _yy: [gu, gw]  # noqa: E731
    for k in range(n):
        y = step(drift, diff, k * dt_s, y, dt_s, dw[k])
        out[k + 1] = y
    return {"t": np.arange(n + 1) * dt_s, "u": out[:, 0, :] * FTPS_TO_KTS,
            "w": out[:, 1, :] * FTPS_TO_KTS, "sigma_u": su * FTPS_TO_KTS,
            "sigma_w": sw * FTPS_TO_KTS, "L_u": lu, "L_w": lw, "T_u": tu, "T_w": tw}  # fmt: skip


# state indices
X, H, U, W, UG, WG, GF, FUEL = range(8)


@dataclass
class _Mode:
    """What is fixed over a stretch of steps."""

    kind: str  # "ground" | "air" | "glide" | "flare" | "final"
    n_op: int
    engine_out: bool = False
    idle: bool = False
    mu: float = 0.0
    spoilers: bool = False
    chute_t: float | None = None  # absolute deploy time
    t_rot: float | None = None  # rotation start
    reverse: float = 0.0
    n_load: float = 1.0  # flare load factor


class _Sim:
    """One realization's machinery: dynamics, gust model and stepping."""

    def __init__(self, vm: VehicleModel, cfg: RunConfig, s: GustSettings, dw: np.ndarray,
                 trace: bool = False):  # fmt: skip
        self.vm, self.s, self.dw = vm, s, dw
        self.dt = s.dt_s
        self.step = get_step(s.method)
        self.vbar = vm.env.wind(0.0, 0.0, 0.0)
        self.w20 = s.w20
        self.vertical = s.vertical
        geo = cfg.aircraft.geometry
        self.span = geo.span_ft or cfg.aircraft.ground_effect.span_ft
        self.tau = max(s.filter_s, 1e-9)
        self.cos_phi = math.cos(vm.env.slope_rad)
        self.sin_phi = math.sin(vm.env.slope_rad)
        self.trace = trace
        self.rows: list[tuple] = []
        # TABLE-CODE: reads the aero table's alpha range to hold alpha inside it under gusts (a
        # stall plateau). Relies on AeroTable.alpha_range_rad; if the table code is re-done, this
        # will need to be addressed.
        self.a_lo, self.a_hi = vm.aero.table.alpha_range_rad
        self.v_stall_check = 0.8 * vm.stall_speed_tas()
        self.stall_steps = 0  # steps where gusts pushed alpha past the table at flying speed
        tab = getattr(vm.propulsion.model, "table", None)
        # TABLE-CODE: finds the thrust table's highest airspeed through the interpolator's .x list
        # (Interpolator1D / Interpolator2D), to hold thrust at the table's edge when a gust pushes
        # the airspeed past it; if the table code is re-done, this will need to be addressed.
        xs = getattr(tab, "x", None)
        self.v_thrust_max = max(xs) if xs else math.inf
        self.thrust_clamp_steps = 0

    def coeffs(self, alpha: float, va: float, engine_out: bool, spoilers: bool, h: float):
        """Table coefficients with alpha held inside the table (a stall plateau): gusts can
        give large flow angles at low speed, where the forces are small anyway."""
        if alpha > self.a_hi:
            if va > self.v_stall_check:
                self.stall_steps += 1
            alpha = self.a_hi
        elif alpha < self.a_lo:
            alpha = self.a_lo
        return self.vm.aero.coefficients(alpha, engine_out, spoilers, h)

    # ---- pitch law ------------------------------------------------------------------
    def theta(self, t: float, m: _Mode) -> float:
        vm = self.vm
        if m.t_rot is None:
            return vm.theta_ground_rad
        return min(vm.theta_ground_rad + vm.rotation_rate_rad_s * (t - m.t_rot),
                   vm.theta_target_rad)  # fmt: skip

    # ---- gust model -----------------------------------------------------------------
    def _gust_scales(self, y) -> tuple[float, float, float, float]:
        su, sw, lu, lw = dryden(y[H], self.w20, self.span)
        v = max(y[U] + self.vbar, V_FLOOR)
        return su, sw, lu / v, lw / v

    def _gust_drift_diff(self, y):
        su, sw, tu, tw = self._gust_scales(y)
        d_ug = -y[UG] / tu
        d_wg = -y[WG] / tw if self.vertical else 0.0
        g_ug = su * math.sqrt(2.0 / tu)
        g_wg = sw * math.sqrt(2.0 / tw) if self.vertical else 0.0
        return d_ug, d_wg, g_ug, g_wg

    # ---- forces -----------------------------------------------------------------------
    def _thrust(self, m: _Mode, va: float) -> float:
        p = self.vm.propulsion
        v = max(va, 0.0)
        # TABLE-CODE: plateau past the end of the thrust table (gust analysis only); if the table
        # code is re-done, this will need to be addressed.
        if v > self.v_thrust_max:  # a gust past the end of the thrust table: hold its edge
            self.thrust_clamp_steps += 1
            v = self.v_thrust_max
        if m.reverse > 0.0:
            return -m.reverse * p.total(m.n_op, False, v, self.vm.temp_R)
        return p.total(m.n_op, m.idle, v, self.vm.temp_R)

    def _chute_drag(self, t: float, m: _Mode, qbar: float) -> float:
        c = self.vm.chute
        if c is None or m.chute_t is None or t <= m.chute_t:
            return 0.0
        frac = 1.0 if c.inflation_time_s <= 0 else min(1.0, (t - m.chute_t) / c.inflation_time_s)
        return frac * qbar * c.area_ft2 * c.CD

    def ground_terms(self, t: float, y, m: _Mode):
        vm = self.vm
        va = y[U] + self.vbar + y[UG]
        th = self.theta(t, m)
        alpha = th + math.atan2(y[WG], max(abs(va), 1.0))
        qbar = 0.5 * vm.rho * va * va
        cl, cd = self.coeffs(alpha, va, m.engine_out, m.spoilers, 0.0)
        lift = qbar * vm.S_ft2 * cl
        drag = qbar * vm.S_ft2 * cd + self._chute_drag(t, m, qbar)
        if va < 0.0:
            drag = -drag
        thrust = self._thrust(m, va)
        eps = th + vm.propulsion.incidence_rad
        w = vm.weight_lbf - y[FUEL]
        n_raw = w * self.cos_phi - lift - thrust * math.sin(eps)
        n = n_raw if n_raw > 0.0 else 0.0
        accel = (thrust * math.cos(eps) - drag - m.mu * n - w * self.sin_phi) / (w / vm.g)
        return va, alpha, lift, drag, thrust, n_raw, accel

    def air_terms(self, t: float, y, m: _Mode):
        vm = self.vm
        vax = y[U] + self.vbar + y[UG]
        vaz = y[W] - y[WG]
        va = math.hypot(vax, vaz)
        gam = math.atan2(vaz, vax)
        w = vm.weight_lbf - y[FUEL]
        qbar = 0.5 * vm.rho * va * va
        if m.kind in ("flare", "final", "glide"):
            lift = (m.n_load if m.kind == "flare" else math.cos(gam)) * w
            alpha = vm.aero.alpha_for_cl(lift / (qbar * vm.S_ft2))
            th = alpha + gam
        else:
            th = self.theta(t, m)
            alpha = th - gam
            lift = None
        cl, cd = self.coeffs(alpha, va, m.engine_out, False, max(y[H], 0.0))
        if lift is None:
            lift = qbar * vm.S_ft2 * cl
        drag = qbar * vm.S_ft2 * cd
        thrust = self._thrust(m, va)
        eps = th + vm.propulsion.incidence_rad
        mass = w / vm.g
        du = (thrust * math.cos(eps) - drag * math.cos(gam) - lift * math.sin(gam)) / mass
        dw_ = (thrust * math.sin(eps) - drag * math.sin(gam) + lift * math.cos(gam) - w) / mass
        return va, alpha, lift, drag, thrust, du, dw_

    # ---- SDE right-hand sides ---------------------------------------------------------
    def drift(self, t: float, y, m: _Mode) -> list[float]:
        d_ug, d_wg, _, _ = self._gust_drift_diff(y)
        d_gf = (y[UG] - y[GF]) / self.tau
        if m.kind == "ground":
            va, _, _, _, thrust, _, accel = self.ground_terms(t, y, m)
            ff = self.vm.propulsion.fuel_flow_lbm_s(thrust, va, self.vm.temp_R)
            return [y[U], 0.0, accel, 0.0, d_ug, d_wg, d_gf, ff]
        if m.kind == "glide":  # held on the glide slope at constant ground speed
            return [y[U], y[W], 0.0, 0.0, d_ug, d_wg, d_gf, 0.0]
        va, _, _, _, thrust, du, dw_ = self.air_terms(t, y, m)
        if m.kind == "final":  # the pilot holds the sink rate against the ground
            dw_ = 0.0
        ff = self.vm.propulsion.fuel_flow_lbm_s(thrust, va, self.vm.temp_R)
        return [y[U], y[W], du, dw_, d_ug, d_wg, d_gf, ff]

    def diffusion(self, t: float, y, m: _Mode) -> list[float]:
        _, _, g_ug, g_wg = self._gust_drift_diff(y)
        return [0.0, 0.0, 0.0, 0.0, g_ug, g_wg, 0.0, 0.0]

    def indicated(self, y) -> float:
        return y[U] + self.vbar + y[GF]

    # ---- stepping ---------------------------------------------------------------------
    def advance(self, t: float, k: int, y: list[float], m: _Mode):
        """One step; returns (t, k, y)."""
        if k >= self.dw.shape[0]:
            raise RuntimeError("gust simulation ran past t_max")
        dw = self.dw[k]
        y = self.step(lambda tt, yy: self.drift(tt, yy, m),
                      lambda tt, yy: self.diffusion(tt, yy, m), t, y, self.dt,
                      [0.0, 0.0, 0.0, 0.0, dw[0], dw[1], 0.0, 0.0])  # fmt: skip
        if m.kind == "ground":
            y[H] = y[W] = 0.0
        t += self.dt
        if self.trace:
            self.rows.append((t, y[X], y[H], self._airspeed(y, m), self.indicated(y), y[UG],
                              y[WG], m.kind))  # fmt: skip
        return t, k + 1, y

    def _airspeed(self, y, m: _Mode) -> float:
        vax = y[U] + self.vbar + y[UG]
        return vax if m.kind == "ground" else math.hypot(vax, y[W] - y[WG])


def _cross(g0: float, g1: float, x0: float, x1: float) -> float:
    """x where a linearly interpolated g crosses zero between two steps."""
    s = g0 / (g0 - g1) if g1 != g0 else 1.0
    return x0 + min(max(s, 0.0), 1.0) * (x1 - x0)


@dataclass
class _Schedule:
    v_ef: float  # TAS ft/s (indicated-airspeed triggers)
    v_r: float
    t_recog: float
    t_brakes: float
    t_idle: float
    t_spoilers: float
    allowance_s: float
    screen_ft: float
    aeo_factor: float


def _schedule(cfg: RunConfig, vm: VehicleModel) -> _Schedule:
    r = compute_bfl(cfg.with_updates({"solver.trajectory_dt_s": None}))
    p = cfg.resolved().procedure
    return _Schedule(
        v_ef=vm.eas_to_tas(r.v_ef_kts * KTS_TO_FTPS),
        v_r=vm.eas_to_tas(r.vr_kts * KTS_TO_FTPS),
        t_recog=p.t_recog_s,
        t_brakes=p.t_brakes_s,
        t_idle=p.t_idle_s,
        t_spoilers=p.t_spoilers_s,
        allowance_s=p.t_v1_allowance_s,
        screen_ft=p.screen_height_ft,
        aeo_factor=p.field_length_aeo_factor,
    )


T_MAX = 400.0  # s, per realization (all branches)


def _climb(sim: _Sim, t, k, y, m: _Mode, sch: _Schedule) -> tuple[float, dict]:
    """From the current state to the screen height; rotation at indicated VR."""
    info: dict = {"touchbacks": 0}
    while True:
        if m.kind == "ground" and m.t_rot is None and sim.indicated(y) >= sch.v_r:
            m.t_rot = t
        x0, h0 = y[X], y[H]
        t, k, y = sim.advance(t, k, y, m)
        if m.kind == "ground":
            if m.t_rot is not None and sim.ground_terms(t, y, m)[5] <= 0.0:  # N = 0: lift-off
                m.kind = "air"
                info.setdefault("v_lof_eas_kts", sim._airspeed(y, m) * sim.vm.sqrt_sigma
                                * FTPS_TO_KTS)  # fmt: skip
        else:
            if y[H] >= sch.screen_ft:
                return _cross(h0 - sch.screen_ft, y[H] - sch.screen_ft, x0, y[X]), info
            if y[H] < 0.0:  # settled back onto the runway: roll on, lift off again
                y[H] = y[W] = 0.0
                m.kind = "ground"
                info["touchbacks"] += 1
        if t > T_MAX:
            raise RuntimeError("no screen height within t_max")


def _stop(sim: _Sim, t, k, y, m: _Mode, sch: _Schedule, t_v1: float) -> float:
    """Rejected takeoff from the failure state; switches relative to V1 time."""
    vm = sim.vm
    v1_ground = None
    while True:
        rel = t - t_v1
        if rel >= 0.0 and v1_ground is None:
            v1_ground = y[U]
            if vm.chute is not None:
                m.chute_t = t_v1 + vm.chute.deploy_delay_s
        if rel >= sch.t_brakes:
            m.mu = vm.env.mu_brake
        if rel >= sch.t_idle:
            m.idle = True
        if rel >= sch.t_spoilers:
            m.spoilers = True
        x0, u0 = y[X], y[U]
        t, k, y = sim.advance(t, k, y, m)
        if y[U] <= 0.0:
            x_stop = _cross(u0, y[U], x0, y[X])
            return x_stop + sch.allowance_s * (v1_ground if v1_ground is not None else u0)
        if t > T_MAX:
            raise RuntimeError("no stop within t_max")


def _takeoff(vm: VehicleModel, cfg: RunConfig, s: GustSettings, sch: _Schedule,
             dw: np.ndarray, trace: bool) -> dict:  # fmt: skip
    """One gusty takeoff: shared all-engines roll to V_EF, then go / stop / all-engines."""
    sim = _Sim(vm, cfg, s, dw, trace)
    n = vm.propulsion.n_engines
    y = [0.0] * 8
    t, k = 0.0, 0
    m = _Mode("ground", n, mu=vm.env.mu_roll)
    while sim.indicated(y) < sch.v_ef:  # engine fails at indicated V_EF
        t, k, y = sim.advance(t, k, y, m)
        if t > T_MAX:
            raise RuntimeError("never reached V_EF")
    t_ef, k_ef, y_ef = t, k, list(y)
    x_ef = y[X]
    prefix_rows = list(sim.rows)

    # go: engine out, rotate at indicated VR, climb to the screen
    sim.rows = list(prefix_rows)
    go, info = _climb(sim, t_ef, k_ef, list(y_ef),
                      _Mode("ground", n - 1, engine_out=True, mu=vm.env.mu_roll), sch)  # fmt: skip
    go_rows = sim.rows
    # stop: engine out, brakes etc. after the recognition time
    sim.rows = []
    sim.trace = False
    stop = _stop(sim, t_ef, k_ef, list(y_ef),
                 _Mode("ground", n - 1, engine_out=True, mu=vm.env.mu_roll), sch,
                 t_ef + sch.t_recog)  # fmt: skip
    # all engines: same gusts, no failure
    aeo, _ = _climb(sim, t_ef, k_ef, list(y_ef), _Mode("ground", n, mu=vm.env.mu_roll), sch)
    eo = max(go, stop)
    out = {
        "go_ft": go,
        "stop_ft": stop,
        "aeo_ft": aeo,
        "engine_out_ft": eo,
        "takeoff_field_ft": max(eo, sch.aeo_factor * aeo),
        "x_ef_ft": x_ef,
        "t_ef_s": t_ef,
        "v_lof_go_kts": info.get("v_lof_eas_kts", math.nan),
        "touchbacks": info["touchbacks"],
        "stall_steps": sim.stall_steps,
        "thrust_clamp_steps": sim.thrust_clamp_steps,
    }
    if trace:
        out["_trace_go"] = go_rows
    return out


def _landing(cfg: RunConfig, s: GustSettings, dw: np.ndarray, trace: bool) -> dict:
    """One gusty landing from 50 ft to a stop."""
    lcfg, rule, _ = landing_config(cfg)
    vm = build_model(lcfg)
    lc = lcfg.aircraft.landing
    sim = _Sim(vm, lcfg, s, dw, trace)
    n_eng = vm.propulsion.n_engines
    g = vm.g
    v_s = vm.stall_speed_tas()
    v_a = rule["approach_speed_ratio"] * v_s + vm.eas_to_tas(s.approach_additive_kts * KTS_TO_FTPS)
    gam_a = -lc.approach_angle_deg * DEG_TO_RAD
    gam_td = -math.asin(min(lc.touchdown_sink_rate_fps / v_a, 0.5))
    n = lc.flare_load_factor
    screen = rule["screen_height_ft"]
    h_flare = min(v_a * v_a / (g * (n - 1.0)) * (math.cos(gam_td) - math.cos(gam_a)), screen)
    # on the glide slope, ground speed = airspeed - mean headwind (calm air)
    u0 = v_a * math.cos(gam_a) - sim.vbar
    y = [0.0, screen, u0, u0 * math.tan(gam_a), 0.0, 0.0, 0.0, 0.0]
    t, k = 0.0, 0
    m = _Mode("glide", n_eng, idle=True)
    while y[H] > h_flare:
        t, k, y = sim.advance(t, k, y, m)
    m = _Mode("flare", n_eng, idle=True, n_load=n)
    while True:  # flare, then hold the sink rate, to touchdown
        x0, h0 = y[X], y[H]
        t, k, y = sim.advance(t, k, y, m)
        if y[H] <= 0.0:
            x_td = _cross(h0, y[H], x0, y[X])
            break
        # the flare ends on the path over the ground (what the pilot sees), not the
        # air-relative one, which jumps with every vertical gust
        if m.kind == "flare" and math.atan2(y[W], y[U]) >= gam_td:
            m = _Mode("final", n_eng, idle=True)
        if t > T_MAX:
            raise RuntimeError("no touchdown within t_max")
    y[H] = y[W] = 0.0
    t_td = t
    chute_t = (t_td + vm.chute.deploy_delay_s) if vm.chute is not None else None
    m = _Mode("ground", n_eng, idle=True, mu=vm.env.mu_roll, chute_t=chute_t)
    while True:
        if t - t_td >= lc.free_roll_s and m.mu != vm.env.mu_brake:
            m.mu, m.spoilers, m.reverse = vm.env.mu_brake, True, rule["reverse"]
        x0, u0_ = y[X], y[U]
        t, k, y = sim.advance(t, k, y, m)
        if y[U] <= 0.0:
            dist = _cross(u0_, y[U], x0, y[X])
            break
        if t > T_MAX:
            raise RuntimeError("no stop within t_max")
    out = {
        "landing_distance_ft": dist,
        "landing_runway_ft": rule["field_factor"] * dist,
        "touchdown_x_ft": x_td,
    }
    if trace:
        out["_trace_landing"] = sim.rows
    return out


def _realizations(args: tuple) -> list[dict]:
    """Worker: a batch of realizations (indices) for one configuration."""
    cfg_json, settings, indices, calm_only = args
    cfg = RunConfig.model_validate_json(cfg_json)
    s = GustSettings(**settings)
    if calm_only:
        s.intensity, s.w20_kts = "custom", 0.0
    vm = build_model(cfg)
    sch = _schedule(cfg, vm) if s.takeoff else None
    n_steps = int(T_MAX / s.dt_s) + 2
    out = []
    for i in indices:
        rng = np.random.default_rng([s.seed, i])
        row: dict[str, Any] = {"run": i}
        trace = i < s.n_traces
        try:
            if s.takeoff:
                dw = rng.standard_normal((n_steps, 2)) * math.sqrt(s.dt_s)
                row.update(_takeoff(vm, cfg, s, sch, dw, trace))
            if s.landing:
                dw = rng.standard_normal((n_steps, 2)) * math.sqrt(s.dt_s)
                row.update(_landing(cfg, s, dw, trace))
            row["error"] = ""
        except Exception as exc:  # noqa: BLE001 - a failed realization is kept, flagged
            row["error"] = f"{type(exc).__name__}: {exc}"
        out.append(row)
    return out


def quantile_ci(x: np.ndarray, p: float, level: float = 0.95) -> tuple[float, float, float]:
    """Sample p-quantile and a distribution-free confidence interval from order statistics:
    the number of samples below the true quantile is Binomial(n, p), so the interval runs
    between the order statistics at n p -/+ z sqrt(n p (1 - p))."""
    x = np.sort(np.asarray(x, dtype=float))
    x = x[np.isfinite(x)]
    n = len(x)
    if n == 0:
        return math.nan, math.nan, math.nan
    z = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}.get(level, 1.96)
    est = float(np.quantile(x, p))
    half = z * math.sqrt(n * p * (1.0 - p))
    lo = int(max(0, math.floor(n * p - half)))
    hi = int(min(n - 1, math.ceil(n * p + half)))
    return est, float(x[lo]), float(x[hi])


@dataclass
class GustResult:
    settings: GustSettings
    aircraft_name: str
    rules: str
    samples: pd.DataFrame  # one row per realization
    calm: dict[str, float]  # the same simulator with no gusts
    reference: dict[str, float]  # the main (RK45) solver
    traces: dict[int, dict[str, pd.DataFrame]] = field(default_factory=dict)
    time_s: float = 0.0
    dryden_at: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def ok(self) -> pd.DataFrame:
        return self.samples[self.samples["error"] == ""]

    def percentiles(self, ps=(0.5, 0.9, 0.95, 0.99)) -> pd.DataFrame:
        """For each output: calm value, then each percentile with its 95 % CI and the
        margin over calm."""
        rows = []
        for col, (label, _) in OUTPUTS.items():
            if col not in self.samples:
                continue
            x = self.ok[col].to_numpy(float)
            calm = self.calm.get(col, math.nan)
            r = {"output": col, "label": label, "calm": calm, "mean": float(np.mean(x)),
                 "std": float(np.std(x, ddof=1)) if len(x) > 1 else math.nan,
                 "p_exceed_calm": float(np.mean(x > calm + 0.5))}  # fmt: skip
            for p in ps:
                est, lo, hi = quantile_ci(x, p)
                tag = f"p{round(100 * p)}"
                r[tag], r[f"{tag}_lo"], r[f"{tag}_hi"] = est, lo, hi
                r[f"{tag}_margin"] = est - calm
            rows.append(r)
        return pd.DataFrame(rows)

    def summary(self) -> str:
        s = self.settings
        lines = [
            f"Gust study - {self.aircraft_name} [{self.rules}]",
            f"  turbulence: {s.intensity} (W20 = {s.w20:g} kt), vertical gusts "
            f"{'on' if s.vertical else 'off'}; {len(self.ok)} of {len(self.samples)} "
            f"realizations; {METHOD_NAMES[s.method]}, dt = {s.dt_s:g} s; {self.time_s:.1f} s",
        ]
        tab = self.percentiles()
        for _, r in tab.iterrows():
            lines.append(
                f"  {r['label']:<40s} calm {r['calm']:>8,.0f}   P50 {r['p50']:>8,.0f}   "
                f"P95 {r['p95']:>8,.0f} ({r['p95_margin']:+,.0f})   P99 {r['p99']:>8,.0f} "
                f"({r['p99_margin']:+,.0f})   exceeds calm {100 * r['p_exceed_calm']:.0f} %"
            )
        return "\n".join(lines)


def _trace_frame(rows: list[tuple], sqrt_sigma: float) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["t_s", "x_ft", "h_ft", "V_air", "V_ind", "u_g", "w_g",
                                     "phase"])  # fmt: skip
    for c in ("V_air", "V_ind"):
        df[c + "_kts"] = df.pop(c) * sqrt_sigma * FTPS_TO_KTS  # equivalent airspeed
    for c in ("u_g", "w_g"):
        df[c + "_kts"] = df.pop(c) * FTPS_TO_KTS
    return df


def gust_study(
    config: RunConfig, settings: GustSettings | None = None, executor: Executor | None = None
) -> GustResult:
    """Run ``settings.n`` gusty realizations of the takeoff and/or landing (parallel)."""
    s = settings or GustSettings()
    get_step(s.method)
    if s.n < 1 or s.dt_s <= 0:
        raise ValueError("need n >= 1 and dt_s > 0")
    cfg = config.resolved()
    t0 = time.perf_counter()
    cfg_json = cfg.model_dump_json()
    sd = asdict(s)
    workers = max(1, (os.cpu_count() or 2) - 1)
    chunk = max(1, math.ceil(s.n / (4 * workers)))
    jobs = [(cfg_json, sd, list(range(i, min(i + chunk, s.n))), False)
            for i in range(0, s.n, chunk)]  # fmt: skip
    calm_job = (cfg_json, {**sd, "n_traces": 0}, [0], True)
    parts = calm_rows = None
    try:
        if executor is not None:
            calm_fut = executor.submit(_realizations, calm_job)
            parts = list(executor.map(_realizations, jobs))
            calm_rows = calm_fut.result()
        elif s.n > chunk:
            with ProcessPoolExecutor(mp_context=_MP, max_workers=min(workers, len(jobs) + 1)) as ex:
                calm_fut = ex.submit(_realizations, calm_job)
                parts = list(ex.map(_realizations, jobs))
                calm_rows = calm_fut.result()
    except Exception:  # noqa: BLE001 - no usable process pool here: run serially
        parts = calm_rows = None
    if parts is None or calm_rows is None:
        calm_rows = _realizations(calm_job)
        parts = [_realizations(j) for j in jobs]
    rows = [r for p in parts for r in p]
    vm = build_model(cfg)
    traces: dict[int, dict[str, pd.DataFrame]] = {}
    for r in rows:
        for key in ("_trace_go", "_trace_landing"):
            if key in r:
                traces.setdefault(r["run"], {})[key[7:]] = _trace_frame(r.pop(key), vm.sqrt_sigma)
    samples = pd.DataFrame(rows)
    calm_row = calm_rows[0]
    if calm_row.get("error"):
        raise RuntimeError(f"the calm reference run failed: {calm_row['error']}")
    if s.takeoff and s.landing:  # per realization: what that day's operations need
        for d in (samples, calm_row):
            d["runway_required_ft"] = np.maximum(d["takeoff_field_ft"], d["landing_runway_ft"])
        calm_row["runway_required_ft"] = float(calm_row["runway_required_ft"])
    calm = {c: float(calm_row[c]) for c in OUTPUTS if c in calm_row}
    reference: dict[str, float] = {}
    if s.takeoff:
        r = compute_bfl(cfg.with_updates({"solver.trajectory_dt_s": None}))
        reference.update(go_ft=r.d_go_ft, stop_ft=r.d_stop_ft, aeo_ft=r.aeo_distance_ft,
                         engine_out_ft=r.bfl_ft, takeoff_field_ft=r.field_length_ft)  # fmt: skip
    if s.landing:
        lr = compute_landing(cfg.with_updates({"solver.trajectory_dt_s": None}))
        reference.update(landing_distance_ft=lr.landing_distance_ft,
                         landing_runway_ft=lr.runway_required_ft)  # fmt: skip
    if s.takeoff and s.landing:
        reference["runway_required_ft"] = max(reference["takeoff_field_ft"],
                                              reference["landing_runway_ft"])  # fmt: skip
    dry = {}
    span = cfg.aircraft.geometry.span_ft or cfg.aircraft.ground_effect.span_ft
    for h in (10.0, 50.0):
        su, sw, lu, lw = dryden(h, s.w20, span)
        dry[f"{h:g} ft"] = {"sigma_u_kts": su * FTPS_TO_KTS, "sigma_w_kts": sw * FTPS_TO_KTS,
                            "L_u_ft": lu, "L_w_ft": lw}  # fmt: skip
    return GustResult(
        settings=s,
        aircraft_name=cfg.aircraft.name,
        rules=cfg.procedure.rules or cfg.aircraft.certification.rules,
        samples=samples,
        calm=calm,
        reference=reference,
        traces=traces,
        time_s=time.perf_counter() - t0,
        dryden_at=dry,
    )


def _convergence_path(args: tuple) -> dict:
    """Worker: one Brownian path, solved at every step size (strong error study)."""
    cfg_json, settings, i, dts, ref_dt = args
    cfg = RunConfig.model_validate_json(cfg_json)
    base = GustSettings(**settings)
    vm = build_model(cfg)
    sch = _schedule(cfg, vm)
    rng = np.random.default_rng([base.seed, 10_000 + i])
    n_fine = int(T_MAX / ref_dt) + 2
    z_to, z_ld = rng.standard_normal((n_fine, 2)), rng.standard_normal((n_fine, 2))
    out: dict[str, Any] = {}
    for dt in (*dts, ref_dt):
        r = int(round(dt / ref_dt))
        n = n_fine // r
        s = GustSettings(**{**settings, "dt_s": dt, "n_traces": 0})
        key = "ref" if dt == ref_dt else dt
        res: dict[str, float] = {}
        for z, fn in ((z_to, "takeoff"), (z_ld, "landing")):
            dw = math.sqrt(ref_dt) * z[: n * r].reshape(n, r, 2).sum(axis=1)
            try:
                res.update(_takeoff(vm, cfg, s, sch, dw, False) if fn == "takeoff"
                           else _landing(cfg, s, dw, False))  # fmt: skip
            except Exception:  # noqa: BLE001
                pass
        out[key] = res
    return out


def convergence_study(
    config: RunConfig,
    settings: GustSettings | None = None,
    dts: tuple[float, ...] = (0.04, 0.02, 0.01, 0.005),
    ref_dt: float = 0.00125,
    n_paths: int = 16,
    outputs: tuple[str, ...] = ("go_ft", "stop_ft", "aeo_ft", "landing_distance_ft"),
    executor: Executor | None = None,
) -> pd.DataFrame:
    """Strong (path-wise) error of each output against step size, for both methods.

    Every path's Brownian increments are drawn once on the reference grid and summed
    for the coarser steps, so each step size sees the same gusts. Error = mean over
    paths of |d(dt) - d(ref_dt)|. Returns rows (method, dt, output, error).
    """
    s0 = settings or GustSettings()
    cfg = config.resolved()
    rows = []
    for method in ("em", "heun"):
        sd = {**asdict(s0), "method": method}
        jobs = [(cfg.model_dump_json(), sd, i, dts, ref_dt) for i in range(n_paths)]
        if executor is not None:
            paths = list(executor.map(_convergence_path, jobs))
        else:
            n_workers = max(1, (os.cpu_count() or 2) - 1)
            with ProcessPoolExecutor(mp_context=_MP, max_workers=n_workers) as ex:
                paths = list(ex.map(_convergence_path, jobs))
        for dt in dts:
            for o in outputs:
                errs = [abs(p[dt][o] - p["ref"][o]) for p in paths
                        if o in p.get(dt, {}) and o in p.get("ref", {})]  # fmt: skip
                if errs:
                    rows.append({"method": method, "dt": dt, "output": o,
                                 "error_ft": float(np.mean(errs)), "paths": len(errs)})  # fmt: skip
    return pd.DataFrame(rows)


__all__ = ["GustSettings", "GustResult", "gust_study", "convergence_study", "dryden", "gust_signal",
           "quantile_ci", "OUTPUTS", "INTENSITY_W20_KTS"]  # fmt: skip
