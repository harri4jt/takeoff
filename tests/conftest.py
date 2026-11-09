from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bfl import compute_bfl, load_config

SYNTH = "generic_widebody_synthetic"


@pytest.fixture(scope="session")
def base_cfg():
    return load_config(SYNTH)


@pytest.fixture(scope="session")
def base_result(base_cfg):
    return compute_bfl(base_cfg)


def make_simple_aircraft(
    tmp: Path, CL: float, CD: float, thrust: float, S: float, W: float, n_engines: int = 2
) -> Path:
    """Aircraft with constant CL, CD (alpha-independent) and constant thrust."""
    d = tmp / "simple"
    d.mkdir(parents=True, exist_ok=True)
    (d / "aero_takeoff.csv").write_text(f"alpha_deg,CL,CD\n-20,{CL},{CD}\n30,{CL},{CD}\n")
    spec = {
        "name": "analytic test aircraft",
        "synthetic": True,
        "geometry": {"wing_area_ft2": S},
        "weight": {"default_weight_lbf": W},
        "engines": {
            "n_engines": n_engines,
            "thrust_mode": "constant",
            "thrust_per_engine_lbf": thrust,
            "idle_thrust_per_engine_lbf": 0.0,
        },
        "attitude": {"theta_ground_deg": 0.0, "theta_tailstrike_deg": 12.0},
        "aero": {"configurations": {"takeoff": "aero_takeoff.csv"}},
    }
    (d / "aircraft.yaml").write_text(yaml.safe_dump(spec))
    return d
