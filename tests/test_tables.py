"""Interpolation checks (linear, natural cubic spline, bilinear, range handling)."""

from __future__ import annotations

import warnings

import numpy as np
import pytest
from scipy.interpolate import CubicSpline

from bfl.tables import Interpolator1D, Interpolator2D, TableRangeError, thomas_solve


def test_thomas_matches_dense_solve():
    rng = np.random.default_rng(0)
    n = 8
    sub, sup = rng.random(n), rng.random(n)
    diag = 4 + rng.random(n)
    rhs = rng.random(n)
    A = np.diag(diag) + np.diag(sub[1:], -1) + np.diag(sup[:-1], 1)
    assert np.allclose(thomas_solve(sub, diag, sup, rhs), np.linalg.solve(A, rhs))


def test_linear_exact_on_lines():
    f = Interpolator1D([0, 1, 3], [1, 3, 7])
    assert f(2.0) == pytest.approx(5.0)
    assert f(0.0) == 1.0 and f(3.0) == 7.0


def test_natural_spline_matches_scipy():
    x = np.linspace(-5, 20, 11)
    y = np.sin(x / 4) + 0.1 * x
    ours = Interpolator1D(x, y, method="cubic")
    ref = CubicSpline(x, y, bc_type="natural")
    xq = np.linspace(-5, 20, 200)
    assert np.max(np.abs(ours.evaluate(xq) - ref(xq))) < 1e-12


def test_out_of_range_modes():
    f = Interpolator1D([0, 1], [0, 1])
    with pytest.raises(TableRangeError):
        f(1.5)
    g = Interpolator1D([0, 1], [0, 2], out_of_range="clamp")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        assert g(5.0) == 2.0
        assert len(w) == 1


def test_bilinear_reproduces_bilinear_function():
    xs, ys = [0.0, 1.0, 2.0], [10.0, 20.0]
    fn = lambda x, y: 1 + 2 * x + 3 * y + 0.5 * x * y  # noqa: E731
    z = [[fn(x, y) for y in ys] for x in xs]
    f = Interpolator2D(xs, ys, z)
    for xq, yq in [(0.3, 12.0), (1.7, 19.9), (2.0, 10.0)]:
        assert f(xq, yq) == pytest.approx(fn(xq, yq))
    with pytest.raises(TableRangeError):
        f(3.0, 15.0)
