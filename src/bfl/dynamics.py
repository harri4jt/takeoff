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

Every right-hand side is a pure function of (t, y, params). ``forces`` returns the
full set of intermediate quantities for output and plotting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

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


def _aero_thrust(t: float, va: float, alpha: float, p: SegmentParams):
    """Common aero/thrust evaluation. Returns (qbar, CL, CD, L, D, T, eps_T, D_chute)."""
    vm = p.vehicle
    qbar = 0.5 * vm.rho * va * va
    cl, cd = vm.aero.coefficients(alpha, p.engine_out, p.spoilers)
    lift = qbar * vm.S_ft2 * cl
    d_chute = 0.0
    frac = _chute_fraction(t, p)
    if frac > 0.0:
        d_chute = frac * qbar * vm.chute.area_ft2 * vm.chute.CD
    drag = qbar * vm.S_ft2 * cd + d_chute
    if va < 0.0:  # tailwind at very low ground speed: drag acts forward
        drag = -drag
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
    w = vm.weight_lbf
    phi = vm.env.slope_rad
    n_raw = w * math.cos(phi) - lift - thrust * math.sin(eps)
    n = n_raw if n_raw > 0.0 else 0.0
    f_fric = p.mu * n
    accel = (thrust * math.cos(eps) - drag - f_fric - w * math.sin(phi)) / vm.mass_slug
    return va, alpha, qbar, cl, cd, lift, drag, thrust, n_raw, n, f_fric, accel, d_chute


def ground_rhs(t: float, y: np.ndarray, p: SegmentParams) -> np.ndarray:
    """d/dt [x, V] on the runway."""
    return np.array([y[1], ground_terms(t, y, p)[11]])


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
    qbar, cl, cd, lift, drag, thrust, eps, d_chute = _aero_thrust(t, va, alpha, p)
    m, g = vm.mass_slug, vm.g
    vw = vm.env.wind(t, x, h)
    dva = (thrust * math.cos(eps) - drag) / m - g * math.sin(gam)
    dgam = (thrust * math.sin(eps) + lift) / (m * va) - g * math.cos(gam) / va
    dh = va * math.sin(gam)
    dx = va * math.cos(gam) - vw
    return theta, alpha, qbar, cl, cd, lift, drag, thrust, vw, dx, dh, dva, dgam


def air_rhs(t: float, y: np.ndarray, p: SegmentParams) -> np.ndarray:
    """d/dt [x, h, V_a, gamma] in the air."""
    r = air_terms(t, y, p)
    return np.array([r[9], r[10], r[11], r[12]])


def ground_to_air_state(t: float, y_ground, p: SegmentParams) -> np.ndarray:
    """State conversion at liftoff: V_a = V + V_w, gamma = 0, h = 0."""
    vw = p.vehicle.env.wind(t, y_ground[0], 0.0)
    return np.array([y_ground[0], 0.0, y_ground[1] + vw, 0.0])


RHS_BY_KIND = {"ground": ground_rhs, "air": air_rhs}


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
        }
    theta, alpha, qbar, cl, cd, lift, drag, thrust, vw, dx, dh, dva, dgam = air_terms(t, y, p)
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
    }
