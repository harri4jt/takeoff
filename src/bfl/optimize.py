"""Hand-written 1-D minimizer: golden-section search.

Used to pick the rotation speed that minimizes the field length
(``procedure.optimize_vr``). The objective there is continuous but has kinks (it is
the larger of two distances, and a field can switch from balanced to unbalanced), so a
derivative-free bracketing method is the right tool: each step keeps the sub-interval
that must contain the minimum of a unimodal function and shrinks it by the golden
ratio, 1/phi = 0.618..., whatever the shape of f.
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
