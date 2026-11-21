"""Equations of motion (see docs/equations.md for derivations and sign conventions).

Ground roll, state y = [x, V]   (V = ground speed along the runway, theta = alpha):

    V_a   = V + V_w
    N     = m g cos(phi) - L - T sin(alpha + i_T)          (clamped >= 0)
    dV/dt = (T cos(alpha + i_T) - D - mu N - m g sin(phi)) / m
    dx/dt = V

Airborne, state y = [x, h, V_a, gamma]   (air-mass frame, steady wind, alpha = theta - gamma):

    dV_a/dt   = (T cos(alpha + i_T) - D) / m - g sin(gamma)
    dgamma/dt = (T sin(alpha + i_T) + L) / (m V_a) - g cos(gamma) / V_a
    dh/dt     = V_a sin(gamma)
    dx/dt     = V_a cos(gamma) - V_w

Optional last state component (both phases): fuel burned f [lbm], df/dt = TSFC*T/3600.
The weight is then W = W0 - f and m = W/g. States without it (len 2 / 4) are accepted
and treated as constant weight.

Ground effect (optional): the aero model receives the height h (0 on the runway).

Every right-hand side is a pure function of (t, y, params). ``forces`` returns the
full set of intermediate quantities for output and plotting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from .integrators import takes_lists
from .model import VehicleModel
from .units import FTPS_TO_KTS, RAD_TO_DEG


@dataclass(frozen=True)
class SegmentParams:
    """Configuration that is constant over one integration segment.

    Pitch attitude law: theta(t) = min(theta0 + rate (t - t_theta0), theta_max).
    Chute drag fraction ramps linearly from 0 at ``chute_t_deploy`` to 1 after
    ``inflation_time_s`` (absolute times; ``None`` = no chute).
    """

    vehicle: VehicleModel
    phase: str
    n_operating: int
    idle: bool = False
    engine_out: bool = False
    mu: float = 0.0
    spoilers: bool = False
    theta0: float = 0.0
    t_theta0: float = 0.0
    theta_rate: float = 0.0
    theta_max: float = math.inf
    chute_t_deploy: float | None = None
    load_factor: float | None = None  # approach kind, flare phase: n = L / W held constant
    reverse: float = 0.0  # reverse thrust as a fraction of max thrust (ground roll)

    def but(self, **kw) -> SegmentParams:
        return replace(self, **kw)


def theta_at(t: float, p: SegmentParams) -> float:
    if p.theta_rate == 0.0:
        return min(p.theta0, p.theta_max)
    return min(p.theta0 + p.theta_rate * (t - p.t_theta0), p.theta_max)


def _chute_fraction(t: float, p: SegmentParams) -> float:
    c = p.vehicle.chute
    if c is None or p.chute_t_deploy is None or t <= p.chute_t_deploy:
        return 0.0
    if c.inflation_time_s <= 0.0:
        return 1.0
    return min(1.0, (t - p.chute_t_deploy) / c.inflation_time_s)


def _aero_thrust(t: float, va: float, alpha: float, p: SegmentParams, h: float = 0.0):
    """Common aero/thrust evaluation. Returns (qbar, CL, CD, L, D, T, eps_T, D_chute)."""
    vm = p.vehicle
    qbar = 0.5 * vm.rho * va * va
    cl, cd = vm.aero.coefficients(alpha, p.engine_out, p.spoilers, h)
    lift = qbar * vm.S_ft2 * cl
    d_chute = 0.0
    frac = _chute_fraction(t, p)
    if frac > 0.0:
        d_chute = frac * qbar * vm.chute.area_ft2 * vm.chute.CD
    drag = qbar * vm.S_ft2 * cd + d_chute
    if va < 0.0:  # tailwind at very low ground speed: drag acts forward
        drag = -drag
    if p.reverse > 0.0:  # reversers deployed: a fraction of max thrust, acting rearward
        thrust = -p.reverse * vm.propulsion.total(p.n_operating, False, va, vm.temp_R)
    else:
        thrust = vm.propulsion.total(p.n_operating, p.idle, va, vm.temp_R)
    eps = alpha + vm.propulsion.incidence_rad
    return qbar, cl, cd, lift, drag, thrust, eps, d_chute


# ------------------------------------------------------------------------------------
# ground roll
# ------------------------------------------------------------------------------------
def ground_terms(t: float, y, p: SegmentParams):
    vm = p.vehicle
    x, v = y[0], y[1]
    va = v + vm.env.wind(t, x, 0.0)
    alpha = theta_at(t, p)
    qbar, cl, cd, lift, drag, thrust, eps, d_chute = _aero_thrust(t, va, alpha, p)
    w = vm.weight_lbf - (y[2] if len(y) > 2 else 0.0)
    phi = vm.env.slope_rad
    n_raw = w * math.cos(phi) - lift - thrust * math.sin(eps)
    n = n_raw if n_raw > 0.0 else 0.0
    f_fric = p.mu * n
    accel = (thrust * math.cos(eps) - drag - f_fric - w * math.sin(phi)) / (w / vm.g)
    return va, alpha, qbar, cl, cd, lift, drag, thrust, n_raw, n, f_fric, accel, d_chute


def ground_rhs(t: float, y, p: SegmentParams) -> list[float]:
    """d/dt [x, V(, fuel)] on the runway (a plain list: the integrator works in floats)."""
    r = ground_terms(t, y, p)
    if len(y) > 2:
        vm = p.vehicle
        return [y[1], r[11], vm.propulsion.fuel_flow_lbm_s(r[7], r[0], vm.temp_R)]
    return [y[1], r[11]]


def normal_force_raw(t: float, y, p: SegmentParams) -> float:
    """Unclamped normal force N; its zero crossing defines liftoff."""
    return ground_terms(t, y, p)[8]


# ------------------------------------------------------------------------------------
# airborne
# ------------------------------------------------------------------------------------
def air_terms(t: float, y, p: SegmentParams):
    vm = p.vehicle
    x, h, va, gam = y[0], y[1], y[2], y[3]
    theta = theta_at(t, p)
    alpha = theta - gam
    qbar, cl, cd, lift, drag, thrust, eps, d_chute = _aero_thrust(t, va, alpha, p, h)
    g = vm.g
    m = (vm.weight_lbf - (y[4] if len(y) > 4 else 0.0)) / g
    vw = vm.env.wind(t, x, h)
    dva = (thrust * math.cos(eps) - drag) / m - g * math.sin(gam)
    dgam = (thrust * math.sin(eps) + lift) / (m * va) - g * math.cos(gam) / va
    dh = va * math.sin(gam)
    dx = va * math.cos(gam) - vw
    return theta, alpha, qbar, cl, cd, lift, drag, thrust, vw, dx, dh, dva, dgam


def air_rhs(t: float, y, p: SegmentParams) -> list[float]:
    """d/dt [x, h, V_a, gamma(, fuel)] in the air."""
    r = air_terms(t, y, p)
    if len(y) > 4:
        vm = p.vehicle
        ff = vm.propulsion.fuel_flow_lbm_s(r[7], y[2], vm.temp_R)
        return [r[9], r[10], r[11], r[12], ff]
    return [r[9], r[10], r[11], r[12]]


# ------------------------------------------------------------------------------------
# landing approach: load-factor law instead of a pitch-attitude law
# ------------------------------------------------------------------------------------
def approach_terms(t: float, y, p: SegmentParams):
    """Approach and flare, state [x, h, V_a, gamma] (gamma < 0 descending).

    The manoeuvre sets the load factor n = L/W, and the lift coefficient follows:
        phase "glide": steady descent at constant gamma and V_a (n = cos gamma); the
                       thrust is whatever holds it (reported, not used)
        phase "flare": n = load_factor (constant g), thrust at idle
        phase "final": n = cos gamma (sink rate held to touchdown), thrust at idle
        dV_a/dt   = (T - D) / m - g sin(gamma)      (0 in the glide)
        dgamma/dt = g (n - cos gamma) / V_a          (0 except in the flare)
    alpha is the table angle giving CL = n W / (q S); CD is the table's at that alpha.
    """
    vm = p.vehicle
    x, h, va, gam = y[0], y[1], y[2], y[3]
    w = vm.weight_lbf
    m = w / vm.g
    n = p.load_factor if p.phase == "flare" else math.cos(gam)
    qbar = 0.5 * vm.rho * va * va
    cl_req = n * w / (qbar * vm.S_ft2)
    alpha = vm.aero.alpha_for_cl(cl_req)
    cl, cd = vm.aero.coefficients(alpha, False, False, h)
    lift = n * w
    drag = qbar * vm.S_ft2 * cd
    if p.phase == "glide":
        thrust = drag + w * math.sin(gam)  # needed to hold the glide
        dva = dgam = 0.0
    else:
        thrust = vm.propulsion.total(p.n_operating, True, va, vm.temp_R)
        dva = (thrust - drag) / m - vm.g * math.sin(gam)
        dgam = vm.g * (n - math.cos(gam)) / va
    vw = vm.env.wind(t, x, h)
    dh = va * math.sin(gam)
    dx = va * math.cos(gam) - vw
    return alpha + gam, alpha, qbar, cl, cd, lift, drag, thrust, vw, dx, dh, dva, dgam


def approach_rhs(t: float, y, p: SegmentParams) -> list[float]:
    r = approach_terms(t, y, p)
    return [r[9], r[10], r[11], r[12]]


def ground_to_air_state(t: float, y_ground, p: SegmentParams) -> np.ndarray:
    """State conversion at liftoff: V_a = V + V_w, gamma = 0, h = 0."""
    vw = p.vehicle.env.wind(t, y_ground[0], 0.0)
    out = [y_ground[0], 0.0, y_ground[1] + vw, 0.0]
    if len(y_ground) > 2:
        out.append(y_ground[2])
    return np.array(out)


RHS_BY_KIND = {
    kind: takes_lists(fn)
    for kind, fn in (("ground", ground_rhs), ("air", air_rhs), ("approach", approach_rhs))
}


def airspeed(kind: str, t: float, y, p: SegmentParams) -> float:
    if kind == "ground":
        return y[1] + p.vehicle.env.wind(t, y[0], 0.0)
    return y[2]


# ------------------------------------------------------------------------------------
# full force breakdown for output
# ------------------------------------------------------------------------------------
def forces(t: float, y, p: SegmentParams, kind: str) -> dict[str, float]:
    """All intermediate quantities at one point, in OUTPUT units (kts, deg, lbf, psf)."""
    if kind == "ground":
        va, alpha, qbar, cl, cd, lift, drag, thrust, n_raw, n, f_fric, accel, d_chute = (
            ground_terms(t, y, p)
        )
        return {
            "t_s": t,
            "x_ft": y[0],
            "h_ft": 0.0,
            "V_ground_kts": y[1] * FTPS_TO_KTS,
            "V_air_kts": va * FTPS_TO_KTS,
            "gamma_deg": 0.0,
            "theta_deg": alpha * RAD_TO_DEG,
            "alpha_deg": alpha * RAD_TO_DEG,
            "CL": cl,
            "CD": cd,
            "L_lbf": lift,
            "D_lbf": drag,
            "D_chute_lbf": d_chute,
            "T_total_lbf": thrust,
            "N_lbf": n,
            "F_friction_lbf": f_fric,
            "q_bar_psf": qbar,
            "mu": p.mu,
            "accel_ftps2": accel,
            "fuel_burned_lbf": y[2] if len(y) > 2 else 0.0,
        }
    terms = approach_terms if kind == "approach" else air_terms
    theta, alpha, qbar, cl, cd, lift, drag, thrust, vw, dx, dh, dva, dgam = terms(t, y, p)
    return {
        "t_s": t,
        "x_ft": y[0],
        "h_ft": y[1],
        "V_ground_kts": dx * FTPS_TO_KTS,
        "V_air_kts": y[2] * FTPS_TO_KTS,
        "gamma_deg": y[3] * RAD_TO_DEG,
        "theta_deg": theta * RAD_TO_DEG,
        "alpha_deg": alpha * RAD_TO_DEG,
        "CL": cl,
        "CD": cd,
        "L_lbf": lift,
        "D_lbf": drag,
        "D_chute_lbf": 0.0,
        "T_total_lbf": thrust,
        "N_lbf": 0.0,
        "F_friction_lbf": 0.0,
        "q_bar_psf": qbar,
        "mu": 0.0,
        "accel_ftps2": dva,
        "fuel_burned_lbf": y[4] if len(y) > 4 else 0.0,
    }
