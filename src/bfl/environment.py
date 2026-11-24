"""Runway environment: atmosphere state, wind model hook, slope, friction.

The deterministic solver uses a steady headwind (``SteadyWind``). Gusts live in
``bfl.gusts``, which integrates its own ground-frame equations.
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
