"""Configuration models (pydantic), YAML loading and every default value.

All defaults in the project live HERE and nowhere else. Field names carry their
units. Inputs are in convenient English units (ft, kts, lbf, deg F, deg); conversion
to the internal ft-slug-s-lbf-R-rad system happens in ``bfl.model.build_model``.

Speeds: every V-speed (V_S, V_mcg, V_EF, V1, VR, V_LOF, V2) is an *equivalent
airspeed* in knots (KEAS ~= KCAS at takeoff Mach numbers), as on an airliner's
airspeed indicator. See docs/assumptions.md.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ------------------------------------------------------------------------------------
# aircraft
# ------------------------------------------------------------------------------------
class GeometryConfig(_Model):
    wing_area_ft2: float = Field(gt=0)


class WeightConfig(_Model):
    default_weight_lbf: float = Field(gt=0, description="weight used if the run gives none")


class EnginesConfig(_Model):
    n_engines: int = Field(ge=1)
    thrust_mode: Literal["constant", "table"] = "constant"
    thrust_per_engine_lbf: float | None = Field(default=None, gt=0)
    thrust_table: str | None = Field(default=None, description="CSV file name in aircraft dir")
    idle_thrust_per_engine_lbf: float = Field(ge=0)
    thrust_incidence_deg: float = 0.0

    @model_validator(mode="after")
    def _mode_fields(self) -> EnginesConfig:
        if self.thrust_mode == "constant" and self.thrust_per_engine_lbf is None:
            raise ValueError("thrust_mode 'constant' needs thrust_per_engine_lbf")
        if self.thrust_mode == "table" and not self.thrust_table:
            raise ValueError("thrust_mode 'table' needs thrust_table")
        return self


class AttitudeConfig(_Model):
    theta_ground_deg: float = 0.0
    theta_tailstrike_deg: float = Field(gt=0)


class AeroConfig(_Model):
    configurations: dict[str, str] = Field(description="config name -> CSV file")
    takeoff_configuration: str = "takeoff"
    delta_CD_engine_out: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def _has_takeoff(self) -> AeroConfig:
        if self.takeoff_configuration not in self.configurations:
            raise ValueError(f"takeoff configuration '{self.takeoff_configuration}' not listed")
        return self


class SpoilerConfig(_Model):
    delta_CL: float = Field(default=0.0, le=0, description="lift increment (negative = dump)")
    delta_CD: float = Field(default=0.0, ge=0)


class ChuteConfig(_Model):
    enabled: bool = False
    area_ft2: float = Field(default=0.0, ge=0)
    CD: float = Field(default=0.0, ge=0)
    deploy_delay_s: float = Field(default=1.0, ge=0, description="after V1")
    inflation_time_s: float = Field(default=1.0, ge=0)


class SpeedsConfig(_Model):
    V_mcg_kts: float | None = Field(default=None, gt=0, description="min control speed, ground")


class AircraftConfig(_Model):
    name: str
    synthetic: bool = False
    description: str = ""
    geometry: GeometryConfig
    weight: WeightConfig
    engines: EnginesConfig
    attitude: AttitudeConfig
    aero: AeroConfig
    spoilers: SpoilerConfig = SpoilerConfig()
    chute: ChuteConfig = ChuteConfig()
    speeds: SpeedsConfig = SpeedsConfig()
    directory: str = Field(default="", description="filled by the loader")


# ------------------------------------------------------------------------------------
# run settings
# ------------------------------------------------------------------------------------
class EnvironmentConfig(_Model):
    elevation_ft: float = 0.0
    temperature_F: float | None = Field(default=None, description="actual OAT; None -> ISA+delta")
    isa_delta_F: float | None = None
    headwind_kts: float = Field(default=0.0, description="negative = tailwind")
    runway_slope_deg: float = Field(default=0.0, description="positive = uphill")
    mu_roll: float = Field(default=0.03, ge=0)
    mu_brake: float = Field(default=0.30, ge=0)
    weight_lbf: float | None = Field(default=None, gt=0, description="None -> aircraft default")

    @model_validator(mode="after")
    def _one_temperature(self) -> EnvironmentConfig:
        if self.temperature_F is not None and self.isa_delta_F is not None:
            raise ValueError("give temperature_F or isa_delta_F, not both")
        return self


class ProcedureConfig(_Model):
    k_VR: float = Field(default=1.10, gt=1.0, description="VR / V_S")
    rotation_rate_deg_s: float = Field(default=3.0, gt=0)
    tailstrike_margin_deg: float = Field(default=1.0, ge=0)
    screen_height_ft: float = Field(default=35.0, gt=0)
    t_recog_s: float = Field(default=1.0, ge=0, description="V_EF -> V1 (OEI)")
    t_brakes_s: float = Field(default=0.0, ge=0, description="after V1")
    t_idle_s: float = Field(default=1.0, ge=0, description="after V1")
    t_spoilers_s: float = Field(default=2.0, ge=0, description="after V1")
    t_v1_allowance_s: float = Field(default=2.0, ge=0, description="Part 25 2-s distance credit")
    enforce_v2_min: bool = Field(
        default=True, description="raise k_VR until V2 >= v2_min_ratio * V_S (Part 25.107)"
    )
    v2_min_ratio: float = Field(default=1.2, gt=1.0, description="V2_min / V_S")
    vr_step: float = Field(default=0.01, gt=0)
    max_vr_retries: int = Field(default=20, ge=0)
    v1_min_fraction_of_vr: float = Field(default=0.6, gt=0, lt=1)
    field_length_aeo_factor: float = Field(default=1.15, ge=1)
    chute_enabled: bool | None = Field(default=None, description="None -> aircraft default")


class SolverConfig(_Model):
    method: Literal["rk4", "rk45"] = "rk4"
    dt_s: float = Field(default=0.01, gt=0)
    rtol: float = Field(default=1e-8, gt=0)
    atol: float = Field(default=1e-8, gt=0)
    event_tol_s: float = Field(default=1e-9, gt=0)
    v1_tol_ft: float = Field(default=0.05, gt=0, description="|d_go - d_stop| at the V1 root")
    v1_maxiter: int = Field(default=50, ge=1)
    vef_tol_ftps: float = Field(default=1e-7, gt=0)
    t_max_s: float = Field(default=300.0, gt=0, description="hard cap per simulated branch")
    touchback_tolerance_ft: float = Field(default=0.01, gt=0)
    interpolation: Literal["linear", "cubic"] = "linear"
    out_of_range: Literal["error", "clamp"] = "error"


class Multipliers(_Model):
    k_CL: float = Field(default=1.0, gt=0, description="scales table CL everywhere (incl. CLmax)")
    k_CD: float = Field(default=1.0, gt=0, description="scales table CD")


class RunConfig(_Model):
    """Everything needed for one BFL computation."""

    aircraft: AircraftConfig
    environment: EnvironmentConfig = EnvironmentConfig()
    procedure: ProcedureConfig = ProcedureConfig()
    solver: SolverConfig = SolverConfig()
    multipliers: Multipliers = Multipliers()

    def with_updates(self, updates: dict[str, Any]) -> RunConfig:
        """Copy with dotted-path overrides, e.g. ``{"multipliers.k_CL": 1.1}`` (validated)."""
        data = self.model_dump()
        for path, value in updates.items():
            node = data
            keys = path.split(".")
            for k in keys[:-1]:
                node = node[k]
            if keys[-1] not in node:
                raise KeyError(f"unknown config field '{path}'")
            node[keys[-1]] = value
        return RunConfig.model_validate(data)

    @property
    def weight_lbf(self) -> float:
        return self.environment.weight_lbf or self.aircraft.weight.default_weight_lbf

    @property
    def chute_active(self) -> bool:
        flag = self.procedure.chute_enabled
        return self.aircraft.chute.enabled if flag is None else flag


# ------------------------------------------------------------------------------------
# loading
# ------------------------------------------------------------------------------------
def default_aircraft_root() -> Path:
    """``$BFL_AIRCRAFT_DIR`` or ``<repo>/aircraft`` (repo = two levels above src/bfl)."""
    env = os.environ.get("BFL_AIRCRAFT_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "aircraft"


def list_aircraft(root: str | Path | None = None) -> list[str]:
    """Aircraft folder names (those that contain an aircraft.yaml)."""
    root = Path(root) if root else default_aircraft_root()
    return sorted(p.name for p in root.iterdir() if (p / "aircraft.yaml").is_file())


def resolve_aircraft_dir(aircraft: str | Path) -> Path:
    p = Path(aircraft)
    if (p / "aircraft.yaml").is_file():
        return p.resolve()
    q = default_aircraft_root() / str(aircraft)
    if (q / "aircraft.yaml").is_file():
        return q.resolve()
    raise FileNotFoundError(f"no aircraft.yaml found for '{aircraft}' (looked in {p} and {q})")


def load_aircraft(aircraft: str | Path) -> AircraftConfig:
    d = resolve_aircraft_dir(aircraft)
    with open(d / "aircraft.yaml") as fh:
        data = yaml.safe_load(fh)
    data["directory"] = str(d)
    return AircraftConfig.model_validate(data)


def load_config(
    aircraft: str | Path,
    run_yaml: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> RunConfig:
    """Build a :class:`RunConfig`.

    Args:
        aircraft: aircraft folder name (under ``aircraft/``) or a path to one.
        run_yaml: optional YAML with any of the sections environment / procedure /
            solver / multipliers.
        overrides: dotted-path overrides applied last, e.g. ``{"environment.headwind_kts": 10}``.
    """
    ac = load_aircraft(aircraft)
    run: dict[str, Any] = {}
    if run_yaml is not None:
        with open(run_yaml) as fh:
            run = yaml.safe_load(fh) or {}
    cfg = RunConfig.model_validate({"aircraft": ac.model_dump(), **run})
    return cfg.with_updates(overrides) if overrides else cfg
