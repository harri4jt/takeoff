"""Conceptual-design takeoff and landing runway estimator.

Balanced field length (FAA Part 25 or MIL-STD-3013), all-engines takeoff, landing, trade
studies, gust and data-uncertainty analyses. Start with ``analyze`` and ``trade_study``.
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
