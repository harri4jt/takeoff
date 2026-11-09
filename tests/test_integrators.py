"""Verification of the hand-written RK4 / RK45 integrators and event location (spec 9.1)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from bfl.integrators import Event, integrate

# ---- test problems with closed-form solutions -----------------------------------


def decay(t, y, lam=-0.7):
    return lam * y


def oscillator(t, y, w=2.0):
    return np.array([y[1], -w * w * y[0]])


def logistic(t, y, r=1.3, K=5.0):
    return r * y * (1 - y / K)


def logistic_exact(t, y0=0.2, r=1.3, K=5.0):
    return K / (1 + (K / y0 - 1) * np.exp(-r * t))


EXACT_CASES = [
    ("decay", decay, [1.0], 4.0, lambda t: np.exp(-0.7 * t)),
    ("oscillator", oscillator, [1.0, 0.0], 6.0, lambda t: np.cos(2.0 * t)),
    ("logistic", logistic, [0.2], 6.0, logistic_exact),
]


@pytest.mark.parametrize("name,rhs,y0,T,exact", EXACT_CASES)
@pytest.mark.parametrize("method", ["rk4", "rk45"])
def test_exact_solutions(name, rhs, y0, T, exact, method):
    sol = integrate(
        lambda t, y: np.asarray(rhs(t, y)),
        0.0,
        y0,
        T,
        method=method,
        dt=1e-3,
        rtol=1e-10,
        atol=1e-12,
    )
    assert sol.t[-1] == pytest.approx(T)
    err = np.max(np.abs(sol.y[:, 0] - exact(sol.t)))
    assert err < 1e-8, f"{name}/{method} max error {err}"


def van_der_pol(t, y, mu=0.5):
    return np.array([y[1], mu * (1 - y[0] ** 2) * y[1] - y[0]])


@pytest.mark.parametrize("method,tol", [("rk4", 1e-7), ("rk45", 1e-7)])
def test_against_scipy_vdp(method, tol):
    T = 10.0
    sol = integrate(van_der_pol, 0.0, [2.0, 0.0], T, method=method, dt=2e-3, rtol=1e-10, atol=1e-12)
    ref = solve_ivp(
        van_der_pol, (0, T), [2.0, 0.0], method="DOP853", rtol=1e-12, atol=1e-14, t_eval=sol.t
    )
    err = np.max(np.abs(sol.y - ref.y.T))
    assert err < tol


def rk4_observed_order(dts):
    errs = []
    for dt in dts:
        sol = integrate(oscillator, 0.0, [1.0, 0.0], 2.0, method="rk4", dt=dt)
        errs.append(abs(sol.y[-1, 0] - math.cos(4.0)))
    slope = np.polyfit(np.log(dts), np.log(errs), 1)[0]
    return slope, errs


def test_rk4_order_is_four():
    dts = [0.1 / 2**k for k in range(5)]
    slope, errs = rk4_observed_order(dts)
    assert abs(slope - 4.0) < 0.3, slope
    ratios = [errs[i] / errs[i + 1] for i in range(len(errs) - 1)]
    assert all(12 < r < 20 for r in ratios), ratios  # ~16x per halving


def test_rk45_error_controlled_by_rtol():
    errs = []
    for rtol in [1e-4, 1e-6, 1e-8, 1e-10]:
        sol = integrate(
            oscillator, 0.0, [1.0, 0.0], 10.0, method="rk45", rtol=rtol, atol=rtol * 1e-2
        )
        err = np.max(np.abs(sol.y[:, 0] - np.cos(2 * sol.t)))
        errs.append(err)
        assert err < 200 * rtol  # global error scales with the local tolerance
    assert all(a > b for a, b in zip(errs, errs[1:], strict=False))


def test_rk45_counts_rejections_and_adapts():
    sol = integrate(van_der_pol, 0.0, [2.0, 0.0], 20.0, method="rk45", rtol=1e-6, atol=1e-8, h0=1.0)
    assert sol.n_rejected > 0  # the oversized initial step must be rejected
    steps = np.diff(sol.t)
    assert steps.max() / steps.min() > 2  # genuinely adaptive


@pytest.mark.parametrize("method", ["rk4", "rk45"])
@pytest.mark.parametrize("dt", [0.1, 0.03, 0.0071])
def test_event_location_independent_of_step(method, dt):
    # y = exp(-0.7 t) crosses 0.3 at t* = ln(0.3)/-0.7
    t_star = math.log(0.3) / -0.7
    ev = Event(lambda t, y: y[0] - 0.3, "level", direction=-1, terminal=True)
    sol = integrate(
        decay, 0.0, [1.0], 10.0, method=method, events=[ev], dt=dt, rtol=1e-10, atol=1e-12
    )
    assert sol.status == "event" and sol.terminal_event == "level"
    tol = 1e-6 if method == "rk4" else 1e-8  # limited by the RK step accuracy, not by dt choice
    assert sol.t[-1] == pytest.approx(t_star, abs=tol)
    assert sol.y[-1, 0] == pytest.approx(0.3, abs=1e-9)


def test_nonterminal_events_recorded_and_direction():
    # cos(2t) has zeros at pi/4 + k pi/2; downward crossings at pi/4, 5pi/4
    ev = Event(lambda t, y: y[0], "zero_down", direction=-1, terminal=False)
    sol = integrate(oscillator, 0.0, [1.0, 0.0], 5.0, method="rk4", dt=0.01, events=[ev])
    times = [e.t for e in sol.events]
    assert times == pytest.approx([math.pi / 4, 5 * math.pi / 4], abs=1e-7)
    # event points appear in the output rows
    for e in sol.events:
        assert sol.t[e.index] == e.t
    assert np.all(np.diff(sol.t) > 0)
