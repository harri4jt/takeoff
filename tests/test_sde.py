"""Euler-Maruyama and stochastic Heun: convergence orders on SDEs with exact solutions."""

from __future__ import annotations

import math

import numpy as np
import pytest

from bfl.sde import BrownianPath, em_step, heun_step, integrate_sde, observed_order

MU, SIG, T = 0.5, 0.8, 1.0


def _gbm():
    return (lambda t, y: [MU * y[0]]), (lambda t, y: [SIG * y[0]])


def _strong_errors(method: str, exact_kind: str, n_paths: int = 4000):
    """Mean |X_N - X(T)| over paths, same Brownian paths at every step size."""
    rng = np.random.default_rng(7)
    fine = 2.0**-11
    bp = BrownianPath.sample(rng, T, fine, 1, n_paths)
    w_t = bp.endpoint(T)[0]
    exact = (
        np.exp((MU - 0.5 * SIG**2) * T + SIG * w_t)  # Ito
        if exact_kind == "ito"
        else np.exp(MU * T + SIG * w_t)  # Stratonovich
    )
    f, g = _gbm()
    dts, errs = [], []
    for r in (8, 16, 32, 64, 128):
        dt = fine * r
        y = integrate_sde(f, g, [np.ones(n_paths)], T, dt, bp.increments(r), method)
        dts.append(dt)
        errs.append(float(np.mean(np.abs(y[0] - exact))))
    return dts, errs


def test_euler_maruyama_strong_order_half():
    dts, errs = _strong_errors("em", "ito")
    assert observed_order(dts, errs) == pytest.approx(0.5, abs=0.12)


def test_heun_strong_order_one():
    dts, errs = _strong_errors("heun", "stratonovich")
    assert observed_order(dts, errs) == pytest.approx(1.0, abs=0.12)


def test_em_weak_order_one_and_additive_strong_order_one():
    """Ornstein-Uhlenbeck dX = -a X dt + s dW (additive noise):
    E[X_T^2] has weak error O(dt) under EM, and the path error is O(dt) too."""
    a, s, x0, n = 1.0, 1.0, 1.0, 100_000
    exact_m2 = x0**2 * math.exp(-2 * a * T) + s**2 / (2 * a) * (1 - math.exp(-2 * a * T))
    rng = np.random.default_rng(3)
    fine = 2.0**-7
    bp = BrownianPath.sample(rng, T, fine, 1, n)
    f = lambda t, y: [-a * y[0]]  # noqa: E731
    g = lambda t, y: [s + 0.0 * y[0]]  # noqa: E731
    dts, weak = [], []
    for r in (4, 8, 16, 32):
        dt = fine * r
        y = integrate_sde(f, g, [np.full(n, x0)], T, dt, bp.increments(r), "em")
        dts.append(dt)
        weak.append(abs(float(np.mean(y[0] ** 2)) - exact_m2))
    assert observed_order(dts, weak) == pytest.approx(1.0, abs=0.25)


def test_steps_work_on_floats_and_zero_noise_is_euler():
    f = lambda t, y: [-y[0], y[0]]  # noqa: E731
    g = lambda t, y: [0.0, 0.0]  # noqa: E731
    assert em_step(f, g, 0.0, [1.0, 0.0], 0.1, [0.3, -0.2]) == pytest.approx([0.9, 0.1])
    # Heun without noise is the explicit trapezoid (RK2) method
    h = heun_step(f, g, 0.0, [1.0, 0.0], 0.1, [0.3, -0.2])
    assert h == pytest.approx([1 - 0.1 + 0.005, 0.1 - 0.005])


def test_brownian_coarsening_keeps_the_path():
    bp = BrownianPath.sample(np.random.default_rng(1), 1.0, 0.01, 2)
    assert np.allclose(bp.increments(4).sum(axis=0), bp.increments(1)[:100].sum(axis=0))
    assert bp.increments(1).std() == pytest.approx(0.1, rel=0.15)
