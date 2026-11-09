"""Hand-written explicit Runge-Kutta integrators with event location.

* ``rk4``  - classical fixed-step 4th-order Runge-Kutta.
* ``rk45`` - Dormand-Prince 5(4) embedded pair with adaptive step control
  (error per unit step measured in a mixed rtol/atol RMS norm, safety factor and
  min/max growth clamps, rejected steps counted). Local extrapolation: the 5th
  order solution is propagated.

Event location
--------------
Each event is a scalar function g(t, y) with a direction (+1: only - to + crossings,
-1: only + to -, 0: both) and a terminal flag. After every accepted step
[t_n, t_n + h] the sign of g is checked at both ends. On a crossing the event time
is found with the bracket-safeguarded secant method on

    s -> g(t_n + s, Phi(t_n, y_n, s)),   s in [0, h]

where Phi(t_n, y_n, s) is *a single RK step of size s re-taken from the step start*.
The located state is therefore as accurate as an ordinary step of the method
(no dense output needed). A crossing whose step *starts* exactly on g = 0 is not
counted, so an event that is already satisfied at segment start does not fire
immediately.

Phase switching (e.g. ground -> air at N = 0) is done by the caller
(``bfl.phases``), not inside the integrator.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from .rootfind import safeguarded_secant

RHS = Callable[..., np.ndarray]


# ------------------------------------------------------------------------------------
# data containers
# ------------------------------------------------------------------------------------
@dataclass
class Event:
    """A scalar event function g(t, y) = 0."""

    func: Callable[[float, np.ndarray], float]
    name: str
    direction: int = 0
    terminal: bool = True

    def __call__(self, t: float, y: np.ndarray) -> float:
        return float(self.func(t, y))


@dataclass
class EventRecord:
    """A located event."""

    name: str
    t: float
    y: np.ndarray
    index: int  # row index of the event point in Solution.t / Solution.y
    terminal: bool


@dataclass
class Solution:
    """Integration output: one row per accepted step plus every located event point."""

    t: np.ndarray
    y: np.ndarray
    events: list[EventRecord] = field(default_factory=list)
    status: str = "t_max"  # "t_max" or "event"
    terminal_event: str | None = None
    method: str = "rk4"
    n_steps: int = 0
    n_rejected: int = 0
    n_rhs: int = 0

    @property
    def t_final(self) -> float:
        return float(self.t[-1])

    @property
    def y_final(self) -> np.ndarray:
        return self.y[-1]

    def event(self, name: str) -> EventRecord | None:
        for e in self.events:
            if e.name == name:
                return e
        return None


# ------------------------------------------------------------------------------------
# single steps
# ------------------------------------------------------------------------------------
def rk4_step(
    rhs: RHS, t: float, y: np.ndarray, h: float, args: tuple = (), k1: np.ndarray | None = None
) -> tuple[np.ndarray, None, None]:
    """One classical RK4 step. Returns (y_new, None, None)."""
    if k1 is None:
        k1 = rhs(t, y, *args)
    hh = 0.5 * h
    k2 = rhs(t + hh, y + hh * k1, *args)
    k3 = rhs(t + hh, y + hh * k2, *args)
    k4 = rhs(t + h, y + h * k3, *args)
    return y + (h / 6.0) * (k1 + 2.0 * (k2 + k3) + k4), None, None


# Dormand-Prince 5(4) tableau
_C2, _C3, _C4, _C5 = 1 / 5, 3 / 10, 4 / 5, 8 / 9
_A21 = 1 / 5
_A31, _A32 = 3 / 40, 9 / 40
_A41, _A42, _A43 = 44 / 45, -56 / 15, 32 / 9
_A51, _A52, _A53, _A54 = 19372 / 6561, -25360 / 2187, 64448 / 6561, -212 / 729
_A61, _A62, _A63, _A64, _A65 = 9017 / 3168, -355 / 33, 46732 / 5247, 49 / 176, -5103 / 18656
_B1, _B3, _B4, _B5, _B6 = 35 / 384, 500 / 1113, 125 / 192, -2187 / 6784, 11 / 84
# error coefficients e = b(5th) - b(4th)
_E1, _E3, _E4, _E5, _E6, _E7 = (
    71 / 57600,
    -71 / 16695,
    71 / 1920,
    -17253 / 339200,
    22 / 525,
    -1 / 40,
)


def dp45_step(
    rhs: RHS, t: float, y: np.ndarray, h: float, args: tuple = (), k1: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One Dormand-Prince step. Returns (y5, error_estimate, k7=f(t+h, y5)) (FSAL)."""
    if k1 is None:
        k1 = rhs(t, y, *args)
    k2 = rhs(t + _C2 * h, y + h * (_A21 * k1), *args)
    k3 = rhs(t + _C3 * h, y + h * (_A31 * k1 + _A32 * k2), *args)
    k4 = rhs(t + _C4 * h, y + h * (_A41 * k1 + _A42 * k2 + _A43 * k3), *args)
    k5 = rhs(t + _C5 * h, y + h * (_A51 * k1 + _A52 * k2 + _A53 * k3 + _A54 * k4), *args)
    k6 = rhs(t + h, y + h * (_A61 * k1 + _A62 * k2 + _A63 * k3 + _A64 * k4 + _A65 * k5), *args)
    y5 = y + h * (_B1 * k1 + _B3 * k3 + _B4 * k4 + _B5 * k5 + _B6 * k6)
    k7 = rhs(t + h, y5, *args)
    err = h * (_E1 * k1 + _E3 * k3 + _E4 * k4 + _E5 * k5 + _E6 * k6 + _E7 * k7)
    return y5, err, k7


_STEPPERS = {"rk4": rk4_step, "rk45": dp45_step}


def get_stepper(method: str):
    try:
        return _STEPPERS[method.lower()]
    except KeyError:
        raise ValueError(f"unknown method {method!r}; choose from {sorted(_STEPPERS)}") from None


# ------------------------------------------------------------------------------------
# event helpers
# ------------------------------------------------------------------------------------
def _crossed(g0: float, g1: float, direction: int) -> bool:
    if g0 == 0.0:
        return False  # already on the surface at step start: not a new crossing
    up = g0 < 0.0 <= g1
    down = g0 > 0.0 >= g1
    if direction > 0:
        return up
    if direction < 0:
        return down
    return up or down


def locate_in_step(
    rhs: RHS,
    stepper,
    t_n: float,
    y_n: np.ndarray,
    h: float,
    g: Callable[[float, np.ndarray], float],
    g_n: float,
    g_end: float,
    args: tuple = (),
    k1: np.ndarray | None = None,
    tol: float = 1e-9,
) -> tuple[float, np.ndarray, int]:
    """Locate g = 0 inside one step by re-taking partial RK steps from (t_n, y_n).

    Returns (t*, y*, number_of_rhs_evaluations_used).
    """
    if k1 is None:
        k1 = rhs(t_n, y_n, *args)
    cache: dict[float, np.ndarray] = {}

    def phi(s: float) -> float:
        ys = stepper(rhs, t_n, y_n, s, args, k1)[0]
        cache[s] = ys
        return g(t_n + s, ys)

    if g_end == 0.0:
        s_star = h
    else:
        res = safeguarded_secant(phi, 0.0, h, xtol=tol, fa=g_n, fb=g_end, maxiter=200)
        s_star = res.root
    y_star = cache.get(s_star)
    if y_star is None:
        y_star = stepper(rhs, t_n, y_n, s_star, args, k1)[0]
    stages = 4 if stepper is rk4_step else 7
    return t_n + s_star, y_star, stages * (len(cache) + 1)


def locate_in_solution(
    rhs: RHS,
    sol: Solution,
    g: Callable[[float, np.ndarray], float],
    args: tuple = (),
    direction: int = 0,
    tol: float = 1e-9,
) -> tuple[float, np.ndarray] | None:
    """Find the first crossing of g = 0 along a stored solution.

    Consecutive stored rows are treated as RK steps of the same method; the crossing
    is located by re-taking a partial step from the row that starts the interval.
    Returns None if g never crosses. If g is exactly zero at a stored row, that row
    is returned.
    """
    stepper = get_stepper(sol.method)
    g_prev = g(float(sol.t[0]), sol.y[0])
    if g_prev == 0.0:
        return float(sol.t[0]), sol.y[0].copy()
    for i in range(1, len(sol.t)):
        g_i = g(float(sol.t[i]), sol.y[i])
        if g_i == 0.0:
            return float(sol.t[i]), sol.y[i].copy()
        if _crossed(g_prev, g_i, direction):
            t_n = float(sol.t[i - 1])
            t_s, y_s, _ = locate_in_step(
                rhs,
                stepper,
                t_n,
                sol.y[i - 1],
                float(sol.t[i]) - t_n,
                g,
                g_prev,
                g_i,
                args,
                tol=tol,
            )
            return t_s, y_s
        g_prev = g_i
    return None


# ------------------------------------------------------------------------------------
# driver
# ------------------------------------------------------------------------------------
def _initial_step(rhs, t0, y0, f0, args, rtol, atol, order=5) -> float:
    """Hairer-Norsett-Wanner starting step heuristic."""
    sc = atol + rtol * np.abs(y0)
    d0 = float(np.sqrt(np.mean((y0 / sc) ** 2)))
    d1 = float(np.sqrt(np.mean((f0 / sc) ** 2)))
    h0 = 1e-6 if d0 < 1e-5 or d1 < 1e-5 else 0.01 * d0 / d1
    y1 = y0 + h0 * f0
    f1 = rhs(t0 + h0, y1, *args)
    d2 = float(np.sqrt(np.mean(((f1 - f0) / sc) ** 2))) / h0
    if max(d1, d2) <= 1e-15:
        h1 = max(1e-6, h0 * 1e-3)
    else:
        h1 = (0.01 / max(d1, d2)) ** (1.0 / (order + 1))
    return min(100 * h0, h1)


def integrate(
    rhs: RHS,
    t0: float,
    y0: Sequence[float] | np.ndarray,
    t_max: float,
    method: str = "rk4",
    events: Sequence[Event] = (),
    args: tuple = (),
    dt: float = 0.01,
    rtol: float = 1e-8,
    atol: float = 1e-8,
    h0: float | None = None,
    h_min: float = 1e-12,
    h_max: float = math.inf,
    safety: float = 0.9,
    fac_min: float = 0.2,
    fac_max: float = 5.0,
    event_tol: float = 1e-9,
    max_steps: int = 10_000_000,
) -> Solution:
    """Integrate y' = rhs(t, y, *args) from t0 until t_max or a terminal event.

    Args:
        rhs: right-hand side, pure function of (t, y, *args) returning an ndarray.
        method: "rk4" (fixed step ``dt``) or "rk45" (adaptive Dormand-Prince).
        events: event functions; see module docstring.
        dt: RK4 step size.
        rtol, atol, h0, h_min, h_max, safety, fac_min, fac_max: RK45 controller.
        event_tol: tolerance on event time [s].

    Returns:
        Solution with one row per accepted step plus every event point.
    """
    method = method.lower()
    stepper = get_stepper(method)
    adaptive = method == "rk45"
    y = np.asarray(y0, dtype=float).copy()
    t = float(t0)
    if t_max <= t:
        raise ValueError("t_max must exceed t0")

    ts: list[float] = [t]
    ys: list[np.ndarray] = [y.copy()]
    records: list[EventRecord] = []
    g_vals = [ev(t, y) for ev in events]
    n_rhs = 0
    n_rej = 0
    n_steps = 0

    k1 = rhs(t, y, *args)
    n_rhs += 1
    if adaptive:
        h = h0 if h0 is not None else _initial_step(rhs, t, y, k1, args, rtol, atol)
        n_rhs += 1
        h = min(max(h, h_min), h_max)
    else:
        if dt <= 0:
            raise ValueError("dt must be positive")
        h = dt
    span_eps = 1e-12 * max(1.0, abs(t_max))

    while t < t_max - span_eps:
        if n_steps >= max_steps:
            raise RuntimeError("max_steps exceeded")
        h_try = min(h, t_max - t)
        y_new, err, k_last = stepper(rhs, t, y, h_try, args, k1)
        if adaptive:
            n_rhs += 6
            scale = atol + rtol * np.maximum(np.abs(y), np.abs(y_new))
            en = float(np.sqrt(np.mean((err / scale) ** 2)))
            if not math.isfinite(en):
                en = 1e10
            if en > 1.0:
                n_rej += 1
                h = h_try * max(fac_min, safety * en ** (-0.2))
                if h < h_min:
                    raise RuntimeError(f"step size underflow at t={t}")
                continue
        else:
            n_rhs += 3
        t_new = t + h_try
        n_steps += 1

        # ---- event detection on [t, t_new] --------------------------------------
        g_new = [ev(t_new, y_new) for ev in events]
        hits = []
        for j, ev in enumerate(events):
            if _crossed(g_vals[j], g_new[j], ev.direction):
                t_s, y_s, used = locate_in_step(
                    rhs, stepper, t, y, h_try, ev, g_vals[j], g_new[j], args, k1, event_tol
                )
                n_rhs += used
                hits.append((t_s, j, y_s))
        terminal_hit = None
        if hits:
            hits.sort(key=lambda h_: h_[0])
            for t_s, j, y_s in hits:
                ts.append(t_s)
                ys.append(y_s)
                records.append(
                    EventRecord(events[j].name, t_s, y_s, len(ts) - 1, events[j].terminal)
                )
                if events[j].terminal:
                    terminal_hit = events[j].name
                    break
        if terminal_hit is not None:
            return Solution(
                np.array(ts),
                np.array(ys),
                records,
                "event",
                terminal_hit,
                method,
                n_steps,
                n_rej,
                n_rhs,
            )

        if not (hits and ts[-1] == t_new):
            ts.append(t_new)
            ys.append(y_new)
        t, y, g_vals = t_new, y_new, g_new

        if adaptive:
            k1 = k_last  # FSAL
            fac = fac_max if en == 0.0 else min(fac_max, max(fac_min, safety * en ** (-0.2)))
            h = min(h_max, h_try * fac) if h_try >= h else min(h_max, h * fac)
        else:
            k1 = rhs(t, y, *args)
            n_rhs += 1
            h = dt

    return Solution(
        np.array(ts), np.array(ys), records, "t_max", None, method, n_steps, n_rej, n_rhs
    )
