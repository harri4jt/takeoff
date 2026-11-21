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
    thrust_table: str | None = Field(
        default=None, description="CSV file in the aircraft dir used for this run"
    )
    thrust_tables: dict[str, str] = Field(
        default_factory=dict,
        description="optional named alternatives (name -> CSV), e.g. different engines or "
        "ratings; selectable in the app and compared in the trade study",
    )
    idle_thrust_per_engine_lbf: float = Field(ge=0)
    thrust_incidence_deg: float = Field(
        default=0.0, description="thrust line angle above the aero-table alpha reference line"
    )
    tsfc_per_hr: float = Field(
        default=0.0,
        ge=0,
        description="thrust-specific fuel consumption [lbm/(lbf hr)]; 0 -> constant weight. "
        "A tsfc_per_hr column in the thrust CSV overrides it",
    )

    @model_validator(mode="after")
    def _mode_fields(self) -> EnginesConfig:
        if self.thrust_mode == "constant" and self.thrust_per_engine_lbf is None:
            raise ValueError("thrust_mode 'constant' needs thrust_per_engine_lbf")
        if self.thrust_mode == "table" and not self.thrust_table:
            raise ValueError("thrust_mode 'table' needs thrust_table")
        return self

    def thrust_options(self) -> dict[str, str]:
        """All selectable thrust tables (name -> CSV), the run's own table first."""
        out: dict[str, str] = {}
        if self.thrust_table:
            name = next((k for k, v in self.thrust_tables.items() if v == self.thrust_table), None)
            out[name or Path(self.thrust_table).stem] = self.thrust_table
        for k, v in self.thrust_tables.items():
            if v not in out.values():
                out[k] = v
        return out


class AttitudeConfig(_Model):
    theta_ground_deg: float = Field(
        default=0.0,
        description="angle of attack of the aero-table alpha reference while on the runway "
        "(wing incidence + fuselage ground pitch, in the table's alpha frame)",
    )
    theta_tailstrike_deg: float = Field(gt=0, description="rotation is held 1 deg below this")


class AeroConfig(_Model):
    configurations: dict[str, str] = Field(description="config name -> CSV file")
    takeoff_configuration: str = "takeoff"
    delta_CD_engine_out: float = Field(default=0.0, ge=0)
    CLmax: dict[str, float] = Field(
        default_factory=dict,
        description="optional CLmax per configuration for V_S (e.g. from certified stall "
        "speeds); configurations not listed use max(CL) of their table",
    )

    @model_validator(mode="after")
    def _has_takeoff(self) -> AeroConfig:
        if self.takeoff_configuration not in self.configurations:
            raise ValueError(f"takeoff configuration '{self.takeoff_configuration}' not listed")
        unknown = set(self.CLmax) - set(self.configurations)
        if unknown:
            raise ValueError(f"CLmax given for unknown configuration(s): {sorted(unknown)}")
        if any(v <= 0 for v in self.CLmax.values()):
            raise ValueError("CLmax values must be positive")
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


class GroundEffectConfig(_Model):
    """Raymer ground effect on induced drag (drag only; lift unchanged).

    CD = CD_table - (1 - phi) * K * CL^2 with phi = 33 (h/b)^1.5 / (1 + 33 (h/b)^1.5),
    h = wing height above the runway (+ airborne height). K comes from a least-squares
    fit CD = CD0 + K CL^2 of the takeoff table unless given. See docs/ground_effect.md.
    """

    enabled: bool = False
    span_ft: float | None = Field(default=None, gt=0, description="wing span b")
    wing_height_ft: float | None = Field(
        default=None, gt=0, description="wing (quarter-chord MAC) height above the runway, on gear"
    )
    K: float | None = Field(default=None, gt=0, description="induced-drag factor; None -> fit")
    fit_CL_fraction: float = Field(
        default=0.85, gt=0, le=1, description="fit uses table points with 0 < CL <= this x CLmax"
    )

    @model_validator(mode="after")
    def _needs_geometry(self) -> GroundEffectConfig:
        if self.enabled and (self.span_ft is None or self.wing_height_ft is None):
            raise ValueError("ground_effect enabled: give span_ft and wing_height_ft")
        return self


class GearConfig(_Model):
    """Optional own limits of the design (reference aircraft live in the app)."""

    tire_speed_limit_kts: float | None = Field(default=None, gt=0, description="ground speed")
    max_brake_energy_MJ: float | None = Field(default=None, gt=0, description="whole aircraft")


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
    ground_effect: GroundEffectConfig = GroundEffectConfig()
    gear: GearConfig = GearConfig()
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
    runway_available_ft: float | None = Field(
        default=None, gt=0, description="if given, the refusal speed for this runway is reported"
    )

    @model_validator(mode="after")
    def _one_temperature(self) -> EnvironmentConfig:
        if self.temperature_F is not None and self.isa_delta_F is not None:
            raise ValueError("give temperature_F or isa_delta_F, not both")
        return self


RuleSet = Literal["part25", "mil3013"]

# Values a rule set supplies when the corresponding procedure field is left at None.
# Part 25: 14 CFR 25.107/109/113. MIL: MIL-STD-3013 (2003, 2008-A) sec. 3.2.10, with the
# go branch to the 50 ft obstacle (expected 3013B; see docs/field_length_rules.md).
RULE_PRESETS: dict[str, dict[str, Any]] = {
    "part25": {
        "screen_height_ft": 35.0,
        "t_recog_s": 1.0,
        "t_brakes_s": 0.0,
        "t_idle_s": 1.0,
        "t_spoilers_s": 2.0,
        "t_v1_allowance_s": 2.0,
        "field_length_aeo_factor": 1.15,
        "v2_min_ratio": 1.2,
        "v_lof_min_ratio": None,
        "chute_enabled": None,  # aircraft default (flagged: no Part 25 credit)
    },
    "mil3013": {
        "screen_height_ft": 50.0,
        "t_recog_s": 3.0,  # engine failure -> brakes; each program may argue its own
        "t_brakes_s": 0.0,
        "t_idle_s": 1.0,  # "sufficient time" for decay to idle after the 3 s
        "t_spoilers_s": 1.0,
        "t_v1_allowance_s": 0.0,
        "field_length_aeo_factor": 1.0,
        "v2_min_ratio": 1.2,  # V_obs >= 1.2 V_S at 50 ft (3.2.4a)
        "v_lof_min_ratio": 1.1,  # V_LO >= 1.1 V_S (3.2.3.1a), checked
        "chute_enabled": False,  # optional, off unless asked for
    },
}


class ProcedureConfig(_Model):
    """Takeoff procedure. Fields left at None take the value of the chosen rule set."""

    rules: RuleSet = Field(default="part25", description="part25 (BFL) or mil3013 (CFL)")
    k_VR: float = Field(default=1.10, gt=1.0, description="VR / V_S")
    rotation_rate_deg_s: float = Field(default=3.0, gt=0)
    tailstrike_margin_deg: float = Field(default=1.0, ge=0)
    screen_height_ft: float | None = Field(default=None, gt=0, description="35 / 50 ft")
    t_recog_s: float | None = Field(
        default=None, ge=0, description="engine failure -> V1 (Part 25) / -> brakes (MIL)"
    )
    t_brakes_s: float | None = Field(default=None, ge=0, description="after V1")
    t_idle_s: float | None = Field(default=None, ge=0, description="after V1")
    t_spoilers_s: float | None = Field(default=None, ge=0, description="after V1")
    t_v1_allowance_s: float | None = Field(
        default=None, ge=0, description="Part 25 2-s distance credit (0 under MIL)"
    )
    enforce_v2_min: bool = Field(
        default=True,
        description="raise k_VR until V2 (V_obs) >= v2_min_ratio * V_S (Part 25.107 / 3013)",
    )
    v2_min_ratio: float | None = Field(default=None, gt=1.0, description="V2_min / V_S")
    v_lof_min_ratio: float | None = Field(
        default=None, gt=1.0, description="MIL: warn if V_LO < this x V_S"
    )
    vr_step: float = Field(default=0.01, gt=0)
    max_vr_retries: int = Field(default=20, ge=0)
    v1_min_fraction_of_vr: float = Field(default=0.6, gt=0, lt=1)
    field_length_aeo_factor: float | None = Field(default=None, ge=1)
    chute_enabled: bool | None = Field(
        default=None, description="None -> rule default (Part 25: aircraft default; MIL: off)"
    )

    def resolved(self) -> ProcedureConfig:
        """Copy with every None filled from the rule-set preset."""
        preset = RULE_PRESETS[self.rules]
        data = self.model_dump()
        for k, v in preset.items():
            if data.get(k) is None:
                data[k] = v
        return ProcedureConfig.model_validate(data)

    @property
    def is_mil(self) -> bool:
        return self.rules == "mil3013"


class SolverConfig(_Model):
    method: Literal["rk4", "rk45"] = Field(
        default="rk45",
        description="rk45 (adaptive, default) or rk4 (fixed step dt_s, reference)",
    )
    dt_s: float = Field(default=0.01, gt=0, description="RK4 step when method = rk4")
    trajectory_dt_s: float | None = Field(
        default=0.05,
        gt=0,
        description="with rk45: re-simulate the reported go/stop/AEO time histories at the "
        "solved V1 with RK4 at this step, so plots and the animation are evenly sampled "
        "(distances and V-speeds still come from the rk45 solve). None -> keep rk45 points",
    )
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
        flag = self.procedure.resolved().chute_enabled
        return self.aircraft.chute.enabled if flag is None else flag

    def resolved(self) -> RunConfig:
        """Copy with the rule-set defaults filled into the procedure (idempotent)."""
        return self.model_copy(update={"procedure": self.procedure.resolved()})


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
