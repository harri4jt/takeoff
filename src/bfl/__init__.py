"""Balanced Field Length (BFL) solver - MATH 6006 numerical methods project.

Numerical core (RK4, Dormand-Prince RK45, secant root finding, event location,
interpolation) is written from scratch in this package.
"""

from .analysis import Analysis, analyze
from .bfl import BFLError, compute_bfl, sweep_v1
from .config import RunConfig, list_aircraft, load_config
from .landing import LandingError, LandingResult, compute_landing
from .results import BFLResult, Trajectory
from .takeoff import TakeoffError, TouchbackError
from .trade import trade_study

__all__ = [
    "analyze",
    "Analysis",
    "compute_bfl",
    "compute_landing",
    "LandingResult",
    "LandingError",
    "sweep_v1",
    "trade_study",
    "load_config",
    "list_aircraft",
    "RunConfig",
    "BFLResult",
    "Trajectory",
    "BFLError",
    "TakeoffError",
    "TouchbackError",
]
