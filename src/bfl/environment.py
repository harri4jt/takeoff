"""Runway environment: atmosphere state, wind model hook, slope, friction.

``WindModel`` is the Phase-3 hook for stochastic gusts. Phase 1 only implements a
steady headwind. (A time-varying wind in the airborne phase needs the air-relative
state equations reformulated - see docs/equations.md.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .atmosphere import AtmosphereState


class WindModel(Protocol):
    """Headwind component [ft/s] (positive = headwind) at time t, position x, height h."""

    is_steady: bool

    def __call__(self, t: float, x: float, h: float) -> float: ...


@dataclass(frozen=True)
class SteadyWind:
    headwind_ftps: float = 0.0
    is_steady: bool = True

    def __call__(self, t: float, x: float, h: float) -> float:
        return self.headwind_ftps


@dataclass(frozen=True)
class Environment:
    atmosphere: AtmosphereState
    wind: WindModel
    slope_rad: float
    mu_roll: float
    mu_brake: float
