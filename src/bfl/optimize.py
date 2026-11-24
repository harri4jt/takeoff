"""1-D minimizers: golden-section search and Brent's method.

Used to pick the rotation speed that minimizes the field length
(``procedure.optimize_vr``). The objective there is continuous but has kinks (it is
the larger of two distances, and a field can switch from balanced to unbalanced), so a
derivative-free bracketing method is the right tool.

* ``golden_section``: each step keeps the sub-interval that must contain the minimum of
  a unimodal function and shrinks it by 1/phi = 0.618..., whatever the shape of f.
  Linear convergence, guaranteed.
* ``brent_min`` (Brent 1973, "localmin"): the same bracket, but where f looks smooth
  it steps to the minimum of the parabola through the last three points (superlinear,
  order ~1.32), falling back to a golden-section step whenever the parabola is not
  trusted. Never worse than golden section by more than a few evaluations; usually
  much better near a smooth minimum. This is what the VR optimizer uses.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

INV_PHI = (math.sqrt(5.0) - 1.0) / 2.0  # 0.618...


@dataclass
class MinResult:
    x: float
    f: float
    iterations: int
    x_history: list[float] = field(default_factory=list)
    f_history: list[float] = field(default_factory=list)


def golden_section(
    f: Callable[[float], float], a: float, b: float, xtol: float = 1e-3, maxiter: int = 60
) -> MinResult:
    """Minimize a unimodal ``f`` on [a, b] to an interval narrower than ``xtol``.

    One new evaluation per iteration (the other interior point is reused), so
    reaching ``xtol`` takes about log(xtol/(b-a)) / log(0.618) evaluations.
    """
    xs: list[float] = []
    fs: list[float] = []

    def ev(x: float) -> float:
        y = f(x)
        xs.append(x)
        fs.append(y)
        return y

    c = b - INV_PHI * (b - a)
    d = a + INV_PHI * (b - a)
    fc, fd = ev(c), ev(d)
    it = 0
    while b - a > xtol and it < maxiter:
        it += 1
        if fc <= fd:  # minimum in [a, d]
            b, d, fd = d, c, fc
            c = b - INV_PHI * (b - a)
            fc = ev(c)
        else:  # minimum in [c, b]
            a, c, fc = c, d, fd
            d = a + INV_PHI * (b - a)
            fd = ev(d)
    i = min(range(len(fs)), key=fs.__getitem__)
    return MinResult(xs[i], fs[i], it, xs, fs)


_CGOLD = (3.0 - math.sqrt(5.0)) / 2.0  # 0.381... = 1 - 1/phi


def brent_min(
    f: Callable[[float], float],
    a: float,
    b: float,
    xtol: float = 1e-3,
    maxiter: int = 60,
    x0: float | None = None,
    f0: float | None = None,
) -> MinResult:
    """Minimize ``f`` on [a, b] by Brent's method (golden section + parabolic steps).

    Stops when the minimum is located to within about ``xtol``. ``x0`` (with its value
    ``f0`` if already known) is the starting interior point, e.g. the best point of a
    coarse scan; the default is the golden-section point.

    Each iteration fits a parabola through the three best points (x, w, v) and steps
    to its vertex if that step is inside the bracket and smaller than half the step
    before last (otherwise the parabola is not converging and a golden-section step
    into the larger part of the bracket is taken instead). The bracket [a, b] always
    contains the best point, as in golden section.
    """
    xs: list[float] = []
    fs: list[float] = []

    def ev(x: float) -> float:
        y = f(x)
        xs.append(x)
        fs.append(y)
        return y

    tol = xtol / 3.0
    x = a + _CGOLD * (b - a) if x0 is None else min(max(x0, a), b)
    fx = ev(x) if f0 is None or x0 is None else f0
    if f0 is not None and x0 is not None:
        xs.append(x)
        fs.append(fx)
    w = v = x
    fw = fv = fx
    d = e = 0.0  # last step, step before last
    it = 0
    while it < maxiter:
        m = 0.5 * (a + b)
        t2 = 2.0 * tol
        if abs(x - m) <= t2 - 0.5 * (b - a):  # bracket narrow enough around x
            break
        it += 1
        parabolic = False
        if abs(e) > tol:
            # vertex of the parabola through (x, fx), (w, fw), (v, fv): x + p/q
            r = (x - w) * (fx - fv)
            q = (x - v) * (fx - fw)
            p = (x - v) * q - (x - w) * r
            q = 2.0 * (q - r)
            if q > 0.0:
                p = -p
            q = abs(q)
            e_old = e
            e = d
            if abs(p) < abs(0.5 * q * e_old) and q * (a - x) < p < q * (b - x):
                d = p / q
                u = x + d
                if u - a < t2 or b - u < t2:  # not too close to the bracket ends
                    d = tol if x < m else -tol
                parabolic = True
        if not parabolic:
            e = (b - x) if x < m else (a - x)  # golden step into the larger part
            d = _CGOLD * e
        u = x + (d if abs(d) >= tol else math.copysign(tol, d))
        fu = ev(u)
        if fu <= fx:
            if u < x:
                b = x
            else:
                a = x
            v, fv, w, fw, x, fx = w, fw, x, fx, u, fu
        else:
            if u < x:
                a = u
            else:
                b = u
            if fu <= fw or w == x:
                v, fv, w, fw = w, fw, u, fu
            elif fu <= fv or v == x or v == w:
                v, fv = u, fu
    return MinResult(x, fx, it, xs, fs)
