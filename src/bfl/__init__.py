"""Balanced Field Length (BFL) solver - MATH 6006 numerical methods project.

Numerical core (RK4, Dormand-Prince RK45, secant root finding, event location,
interpolation) is written from scratch in this package.
"""

from .bfl import BFLError, compute_bfl, sweep_v1
from .config import RunConfig, list_aircraft, load_config
from .results import BFLResult, Trajectory
from .takeoff import TakeoffError, TouchbackError

__all__ = [
    "compute_bfl",
    "sweep_v1",
    "load_config",
    "list_aircraft",
    "RunConfig",
    "BFLResult",
    "Trajectory",
    "BFLError",
    "TakeoffError",
    "TouchbackError",
]
