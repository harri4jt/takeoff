"""Segment definitions, event builders and segment chaining helpers.

A *segment* is one integration with fixed :class:`SegmentParams` and dynamics kind
("ground" or "air"). Segments end at a time boundary (a procedural switch such as
"idle at V1 + 1 s") or at a terminal event (V = VR, N = 0, h = 35 ft, ...). Putting
every discontinuity on a segment boundary keeps the RK steps smooth so the methods
retain their order.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field

import numpy as np

from .config import SolverConfig
from .dynamics import RHS_BY_KIND, SegmentParams, airspeed, normal_force_raw
from .integrators import Event, Solution, get_stepper, integrate, locate_in_step


@dataclass
class SegmentResult:
    kind: str  # "ground" | "air"
    params: SegmentParams
    sol: Solution
    _va: np.ndarray | None = field(default=None, repr=False)

    @property
    def phase(self) -> str:
        return self.params.phase

    @property
    def t_end(self) -> float:
        return self.sol.t_final

    @property
    def y_end(self) -> np.ndarray:
        return self.sol.y_final

    def airspeeds(self) -> np.ndarray:
        if self._va is None:
            p = self.params
            self._va = np.array(
                [airspeed(self.kind, t, y, p) for t, y in zip(self.sol.t, self.sol.y, strict=True)]
            )
        return self._va


def run_segment(
    kind: str,
    params: SegmentParams,
    t0: float,
    y0,
    t_end: float,
    events: list[Event],
    solver: SolverConfig,
) -> SegmentResult:
    sol = integrate(
        RHS_BY_KIND[kind],
        t0,
        y0,
        t_end,
        method=solver.method,
        events=events,
        args=(params,),
        dt=solver.dt_s,
        rtol=solver.rtol,
        atol=solver.atol,
        event_tol=solver.event_tol_s,
    )
    return SegmentResult(kind, params, sol)


def truncate(seg: SegmentResult, t_cut: float, y_cut) -> SegmentResult:
    """Keep rows with t < t_cut and append the (located) cut point."""
    s = seg.sol
    k = int(np.searchsorted(s.t, t_cut, side="left"))
    t = np.append(s.t[:k], t_cut)
    y = np.vstack([s.y[:k], np.asarray(y_cut)[None, :]])
    new = Solution(t, y, [e for e in s.events if e.t <= t_cut], "event", None, s.method, k, 0, 0)
    return SegmentResult(seg.kind, seg.params, new)


def state_at_airspeed(
    seg: SegmentResult, v_target: float, tol: float
) -> tuple[float, np.ndarray] | None:
    """Locate where a monotonically accelerating segment passes airspeed ``v_target``.

    Binary search over stored rows, then event location inside the bracketing step by
    re-taking a partial RK step (same accuracy as the integrator).
    """
    va = seg.airspeeds()
    if v_target < va[0] or v_target > va[-1]:
        return None
    i = bisect_left(va.tolist(), v_target)
    if va[i] == v_target:
        return float(seg.sol.t[i]), seg.sol.y[i].copy()
    p, kind = seg.params, seg.kind
    t_n, y_n = float(seg.sol.t[i - 1]), seg.sol.y[i - 1]
    h = float(seg.sol.t[i]) - t_n

    def g(t, y):
        return airspeed(kind, t, y, p) - v_target

    t_s, y_s, _ = locate_in_step(
        RHS_BY_KIND[kind],
        get_stepper(seg.sol.method),
        t_n,
        y_n,
        h,
        g,
        va[i - 1] - v_target,
        va[i] - v_target,
        (p,),
        tol=tol,
    )
    return t_s, y_s


# ------------------------------------------------------------------------------------
# event builders
# ------------------------------------------------------------------------------------
def airspeed_event(
    kind: str,
    params: SegmentParams,
    v_target: float,
    name: str,
    direction: int = 1,
    terminal: bool = True,
) -> Event:
    return Event(lambda t, y: airspeed(kind, t, y, params) - v_target, name, direction, terminal)


def liftoff_event(params: SegmentParams) -> Event:
    """N = 0 (unclamped normal force falls through zero)."""
    return Event(lambda t, y: normal_force_raw(t, y, params), "liftoff", -1, True)


def stopped_event() -> Event:
    return Event(lambda t, y: y[1], "stopped", -1, True)


def screen_event(height_ft: float) -> Event:
    return Event(lambda t, y: y[1] - height_ft, "screen_height", 1, True)


def touchback_event(tol_ft: float) -> Event:
    """h falls below -tol after liftoff (a weak takeoff settling back onto the runway)."""
    return Event(lambda t, y: y[1] + tol_ft, "touchback", -1, True)
