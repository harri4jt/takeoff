"""Hand-written scalar root finders: plain secant and bracket-safeguarded secant.

Both record the complete iterate history (x_k, f(x_k)) so convergence can be
plotted and the observed order of convergence estimated.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class RootResult:
    """Outcome of a root solve.

    Attributes:
        root: best estimate of the root.
        f_root: f(root).
        converged: whether a tolerance was met.
        iterations: number of new iterates generated (excluding starting points).
        x_history / f_history: every point at which f was evaluated, in order.
        steps: for the safeguarded method, "secant" or "bisection" per iteration.
        message: human-readable reason for stopping.
    """

    root: float
    f_root: float
    converged: bool
    iterations: int
    x_history: list[float] = field(default_factory=list)
    f_history: list[float] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    message: str = ""

    @property
    def n_evals(self) -> int:
        return len(self.x_history)


class RootFindError(RuntimeError):
    """Raised when a root solve cannot proceed (e.g. no bracket)."""


def secant(
    f: Callable[[float], float],
    x0: float,
    x1: float,
    xtol: float = 1e-12,
    ftol: float = 0.0,
    maxiter: int = 50,
) -> RootResult:
    """Plain secant method.

    x_{k+1} = x_k - f(x_k) (x_k - x_{k-1}) / (f(x_k) - f(x_{k-1})).

    Stops when |x_{k+1} - x_k| <= xtol, |f(x_{k+1})| <= ftol, or f(x_k) == 0.
    Converges superlinearly with order (1 + sqrt 5)/2 ~ 1.618 near a simple root,
    but has no global convergence guarantee.
    """
    f0, f1 = f(x0), f(x1)
    xs, fs = [x0, x1], [f0, f1]
    for k in range(1, maxiter + 1):
        if f1 == 0.0:
            return RootResult(x1, f1, True, k - 1, xs, fs, ["secant"] * (k - 1), "exact zero")
        denom = f1 - f0
        if denom == 0.0 or not math.isfinite(denom):
            return RootResult(x1, f1, False, k - 1, xs, fs, ["secant"] * (k - 1), "flat secant")
        x2 = x1 - f1 * (x1 - x0) / denom
        f2 = f(x2)
        xs.append(x2)
        fs.append(f2)
        if not math.isfinite(x2) or not math.isfinite(f2):
            return RootResult(x2, f2, False, k, xs, fs, ["secant"] * k, "diverged")
        if abs(x2 - x1) <= xtol or abs(f2) <= ftol:
            return RootResult(x2, f2, True, k, xs, fs, ["secant"] * k, "tolerance met")
        x0, f0, x1, f1 = x1, f1, x2, f2
    return RootResult(x1, f1, False, maxiter, xs, fs, ["secant"] * maxiter, "maxiter reached")


def safeguarded_secant(
    f: Callable[[float], float],
    a: float,
    b: float,
    xtol: float = 1e-12,
    ftol: float = 0.0,
    maxiter: int = 100,
    fa: float | None = None,
    fb: float | None = None,
) -> RootResult:
    """Secant iteration that always keeps a sign-change bracket [lo, hi].

    Each iteration proposes the secant point from the two most recent iterates.
    The proposal is rejected in favour of a bisection step when

    * it falls outside (or on the edge of) the current bracket, or
    * the iteration is stalling: the bracket did not at least halve over the
      previous two iterations.

    The new point then replaces the bracket end with the same sign of f.
    Stops when |f| <= ftol or the bracket is narrower than xtol (the returned
    root is then the endpoint with the smaller |f|).

    ``fa``/``fb`` may be passed if f(a), f(b) are already known (saves two calls).
    """
    fa = f(a) if fa is None else fa
    fb = f(b) if fb is None else fb
    xs, fs, steps = [a, b], [fa, fb], []
    if fa == 0.0:
        return RootResult(a, fa, True, 0, xs, fs, steps, "exact zero at a")
    if fb == 0.0:
        return RootResult(b, fb, True, 0, xs, fs, steps, "exact zero at b")
    if (fa > 0) == (fb > 0):
        raise RootFindError(f"no sign change on [{a}, {b}]: f(a)={fa}, f(b)={fb}")

    lo, flo, hi, fhi = (a, fa, b, fb) if a < b else (b, fb, a, fa)
    x_prev, f_prev, x_cur, f_cur = a, fa, b, fb
    widths = [hi - lo]
    for k in range(1, maxiter + 1):
        use_bisect = False
        denom = f_cur - f_prev
        if denom != 0.0:
            x_new = x_cur - f_cur * (x_cur - x_prev) / denom
            if not (lo < x_new < hi) or not math.isfinite(x_new):
                use_bisect = True
        else:
            use_bisect = True
        # stall check: bracket should halve at least every two iterations
        if not use_bisect and len(widths) >= 3 and widths[-1] > 0.5 * widths[-3]:
            use_bisect = True
        if use_bisect:
            x_new = 0.5 * (lo + hi)
        f_new = f(x_new)
        xs.append(x_new)
        fs.append(f_new)
        steps.append("bisection" if use_bisect else "secant")

        if (f_new > 0) == (flo > 0):
            lo, flo = x_new, f_new
        else:
            hi, fhi = x_new, f_new
        widths.append(hi - lo)
        x_prev, f_prev, x_cur, f_cur = x_cur, f_cur, x_new, f_new

        if f_new == 0.0 or abs(f_new) <= ftol:
            return RootResult(x_new, f_new, True, k, xs, fs, steps, "f tolerance met")
        if hi - lo <= xtol:
            best, fbest = (lo, flo) if abs(flo) <= abs(fhi) else (hi, fhi)
            return RootResult(best, fbest, True, k, xs, fs, steps, "bracket tolerance met")
    best, fbest = (lo, flo) if abs(flo) <= abs(fhi) else (hi, fhi)
    return RootResult(best, fbest, False, maxiter, xs, fs, steps, "maxiter reached")


def observed_order(errors: list[float]) -> list[float]:
    """Estimate convergence order p_k = ln(e_{k+1}/e_k) / ln(e_k/e_{k-1}) from errors."""
    out = []
    for k in range(1, len(errors) - 1):
        e0, e1, e2 = errors[k - 1], errors[k], errors[k + 1]
        if min(e0, e1, e2) <= 0 or e0 == e1:
            continue
        out.append(math.log(e2 / e1) / math.log(e1 / e0))
    return out
