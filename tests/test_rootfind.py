"""Verification of the hand-written root finders (spec 9.2)."""

from __future__ import annotations

import math

import pytest
from scipy.optimize import brentq

from bfl.rootfind import RootFindError, observed_order, safeguarded_secant, secant

GOLDEN = (1 + math.sqrt(5)) / 2

CASES = [
    ("x^2-2", lambda x: x * x - 2, 1.0, 2.0, math.sqrt(2)),
    ("cos x - x", lambda x: math.cos(x) - x, 0.0, 1.0, None),
    ("cubic", lambda x: x**3 - 2 * x - 5, 2.0, 3.0, None),  # Wallis' cubic
]


@pytest.mark.parametrize("name,f,a,b,exact", CASES)
def test_known_roots(name, f, a, b, exact):
    ref = exact if exact is not None else brentq(f, a, b, xtol=1e-15)
    r1 = secant(f, a, b, xtol=1e-14)
    r2 = safeguarded_secant(f, a, b, xtol=1e-14)
    assert r1.converged and r2.converged
    assert r1.root == pytest.approx(ref, abs=1e-12)
    assert r2.root == pytest.approx(ref, abs=1e-12)
    assert len(r1.x_history) == len(r1.f_history) == r1.iterations + 2


def secant_order(f, x0, x1, root):
    res = secant(f, x0, x1, xtol=0.0, maxiter=30)
    errs = [abs(x - root) for x in res.x_history]
    errs = [e for e in errs if e > 1e-13]  # drop iterates at round-off level
    return observed_order(errs), res


def test_secant_order_golden_ratio():
    p, _ = secant_order(lambda x: x * x - 2, 1.0, 2.0, math.sqrt(2))
    # asymptotic estimates (the last ones) approach the golden ratio
    assert abs(p[-1] - GOLDEN) < 0.15, p
    root = brentq(lambda x: math.cos(x) - x, 0, 1, xtol=1e-15)
    p2, _ = secant_order(lambda x: math.cos(x) - x, 0.0, 1.0, root)
    assert abs(p2[-1] - GOLDEN) < 0.15, p2


def test_safeguard_rescues_divergent_secant():
    f = math.atan
    plain = secant(f, 2.0, 3.0, maxiter=30)
    assert not (plain.converged and abs(plain.root) < 1e-6)  # plain secant runs away
    safe = safeguarded_secant(f, -3.0, 5.0, xtol=1e-14)
    assert safe.converged and abs(safe.root) < 1e-12
    assert "bisection" in safe.steps


def test_no_bracket_raises():
    with pytest.raises(RootFindError):
        safeguarded_secant(lambda x: x * x + 1, -1.0, 1.0)
