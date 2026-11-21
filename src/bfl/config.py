"""Configuration models (pydantic), YAML loading and every default value.

All defaults in the project live HERE and nowhere else. Field names carry their
units. Inputs are in convenient English units (ft, kts, lbf, deg F, deg); conversion
to the internal ft-slug-s-lbf-R-rad system happens in ``bfl.model.build_model``.

Speeds: every V-speed (V_S, V_mcg, V_EF, V1, VR, V_LOF, V2) is an *equivalent
airspeed* in knots (KEAS ~= KCAS at takeoff Mach numbers), as on an airliner's
airspeed indicator. See docs/assumptions.md.
"""

from __future__ import annotations

import difflib
import hashlib
import io
import os
import shutil
import typing
import zipfile
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ------------------------------------------------------------------------------------
# aircraft
# ------------------------------------------------------------------------------------
class GeometryConfig(_Model):
    wing_area_ft2: float = Field(gt=0, description="reference wing area S_ref [ft^2]")


class WeightConfig(_Model):
    default_weight_lbf: float = Field(gt=0, description="weight used if the run gives none")


class EnginesConfig(_Model):
    n_engines: int = Field(ge=1, description="number of engines (one fails in the BFL cases)")
    thrust_mode: Literal["constant", "table"] = Field(
        default="constant", description="constant: one thrust value; table: thrust CSV(s)"
    )
    thrust_per_engine_lbf: float | None = Field(
        default=None, gt=0, description="takeoff thrust per engine [lbf] (constant mode)"
    )
    thrust_tables: dict[str, str] = Field(
        default_factory=dict,
        description="thrust tables (name -> CSV in the aircraft dir), e.g. different engines "
        "or ratings; selectable in the app and compared in the trade study",
    )
    thrust_table: str | None = Field(
        default=None, description="name of the default thrust table (a key of thrust_tables)"
    )
    idle_thrust_per_engine_lbf: float = Field(
        ge=0, description="idle thrust per engine [lbf], used in the stop and the landing"
    )
    thrust_incidence_deg: float = Field(
        default=0.0, description="thrust line angle above the aero-table alpha reference line"
    )
    tsfc_per_hr: float = Field(
        default=0.0,
        ge=0,
        description="thrust-specific fuel consumption [lbm/(lbf hr)]; 0 -> constant weight. "
        "A tsfc_per_hr column in the thrust CSV overrides it",
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_thrust_file(cls, data: Any) -> Any:
        """Older files gave ``thrust_table: thrust.csv`` (a file, not a name): register it
        under its stem so both forms load the same way."""
        if isinstance(data, dict):
            t = data.get("thrust_table")
            tables = dict(data.get("thrust_tables") or {})
            if t and t not in tables:
                if str(t).lower().endswith(".csv"):
                    name = next((k for k, v in tables.items() if v == t), Path(t).stem)
                    tables.setdefault(name, t)
                    data = {**data, "thrust_tables": tables, "thrust_table": name}
            elif not t and len(tables) >= 1:
                data = {**data, "thrust_table": next(iter(tables))}
        return data

    @model_validator(mode="after")
    def _mode_fields(self) -> EnginesConfig:
        if self.thrust_mode == "constant" and self.thrust_per_engine_lbf is None:
            raise ValueError("thrust_mode 'constant' needs thrust_per_engine_lbf")
        if self.thrust_mode == "table":
            if not self.thrust_tables:
                raise ValueError("thrust_mode 'table' needs thrust_tables (name: file.csv)")
            if self.thrust_table not in self.thrust_tables:
                raise ValueError(f"default thrust table '{self.thrust_table}' not listed")
        return self

    @property
    def thrust_file(self) -> str | None:
        """CSV of the selected thrust table (None in constant-thrust mode)."""
        if self.thrust_mode != "table":
            return None
        return self.thrust_tables[str(self.thrust_table)]

    def thrust_options(self) -> dict[str, str]:
        """All thrust tables (name -> CSV), the selected one first."""
        out = (
            {self.thrust_table: self.thrust_tables[self.thrust_table]}
            if (self.thrust_table in self.thrust_tables)
            else {}
        )
        out.update({k: v for k, v in self.thrust_tables.items() if k not in out})
        return out


class AttitudeConfig(_Model):
    theta_ground_deg: float = Field(
        default=0.0,
        description="angle of attack of the aero-table alpha reference while on the runway "
        "(wing incidence + fuselage ground pitch, in the table's alpha frame)",
    )
    theta_tailstrike_deg: float = Field(gt=0, description="rotation is held 1 deg below this")


class AeroConfig(_Model):
    configurations: dict[str, str] = Field(
        description="aero tables (name -> CSV in the aircraft dir), e.g. flap settings; "
        "selectable in the app and compared in the trade study"
    )
    takeoff_configuration: str = Field(
        default="takeoff", description="name of the default aero table (a key of configurations)"
    )
    delta_CD_engine_out: float = Field(
        default=0.0, ge=0, description="drag added when an engine fails (windmilling + trim)"
    )
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
    delta_CD: float = Field(default=0.0, ge=0, description="drag increment of the spoilers")


class ChuteConfig(_Model):
    enabled: bool = Field(default=False, description="credit the chute in the rejected takeoff")
    area_ft2: float = Field(default=0.0, ge=0, description="chute reference area [ft^2]")
    CD: float = Field(default=0.0, ge=0, description="chute drag coefficient on that area")
    deploy_delay_s: float = Field(default=1.0, ge=0, description="after V1")
    inflation_time_s: float = Field(
        default=1.0, ge=0, description="deployment to full drag (linear ramp)"
    )


class SpeedsConfig(_Model):
    V_mcg_kts: float | None = Field(default=None, gt=0, description="min control speed, ground")


class GroundEffectConfig(_Model):
    """Raymer ground effect on induced drag (drag only; lift unchanged).

    CD = CD_table - (1 - phi) * K * CL^2 with phi = 33 (h/b)^1.5 / (1 + 33 (h/b)^1.5),
    h = wing height above the runway (+ airborne height). K comes from a least-squares
    fit CD = CD0 + K CL^2 of the takeoff table unless given. See docs/ground_effect.md.
    """

    enabled: bool = Field(default=False, description="Raymer ground effect on the induced drag")
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


RuleSet = Literal["part25", "mil3013"]


class CertificationConfig(_Model):
    """Which field-length rules the aircraft is designed to (a property of the program)."""

    rules: RuleSet = Field(default="part25", description="part25 (civil) or mil3013 (military)")
    t_recog_s: float | None = Field(
        default=None,
        ge=0,
        description="engine failure -> action delay; None -> rule default (Part 25: 1 s to V1, "
        "MIL-STD-3013: 3 s to brakes). Programs may argue their own value",
    )


class LandingConfig(_Model):
    """Landing: configuration, technique and (military only) stopping devices.

    Speeds and field factors not given here come from the rule set (LANDING_RULES).
    """

    weight_lbf: float | None = Field(
        default=None,
        gt=0,
        description="landing weight (e.g. max landing weight), capped at the takeoff "
        "weight; blank -> the takeoff weight (an immediate return, the worst case)",
    )
    configuration: str | None = Field(
        default=None, description="aero table to start from; blank -> the takeoff table"
    )
    k_CL: float = Field(
        default=1.0,
        gt=0,
        description="landing flaps: CL multiplier on that table "
        "(includes CLmax, so it sets the landing stall speed)",
    )
    k_CD: float = Field(default=1.0, gt=0, description="landing flaps: CD multiplier")
    approach_speed_ratio: float | None = Field(
        default=None,
        gt=1.0,
        description="approach speed / landing stall speed; blank -> "
        "rule (Part 25: V_REF = 1.23 V_SR0; MIL: 1.2)",
    )
    approach_angle_deg: float = Field(default=3.0, gt=0, le=10, description="glide slope")
    flare_load_factor: float = Field(
        default=1.15, gt=1.0, le=2.0, description="constant-g flare: n = L/W in the flare"
    )
    touchdown_sink_rate_fps: float = Field(
        default=2.0, ge=0, description="the flare ends at this sink rate, held to touchdown"
    )
    free_roll_s: float = Field(
        default=2.0, ge=0, description="touchdown -> brakes and spoilers (and reversers)"
    )
    reverse_thrust_fraction: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="reverse thrust as a fraction of max thrust. "
        "Military only: Part 25.125 gives no reverse-thrust credit",
    )
    use_chute: bool = Field(
        default=False,
        description="military only: deploy the drag chute at touchdown (needs the chute "
        "section). Part 25 gives no credit",
    )
    field_factor: float | None = Field(
        default=None,
        gt=0,
        description="runway required / landing distance; blank -> rule "
        "(Part 25/121: 1/0.6 = 1.67; MIL: 1.0)",
    )


# Landing values each rule set supplies when the aircraft leaves them blank.
# Part 25.125 (landing distance from 50 ft at V_REF >= 1.23 V_SR0, no reverse thrust),
# Part 121.195 (runway required = distance / 0.6). MIL-STD-3013: from a 50 ft obstacle,
# reversers and chute may be credited; approach speed and factor to be confirmed (3013B).
LANDING_RULES: dict[str, dict[str, Any]] = {
    "part25": {"screen_height_ft": 50.0, "approach_speed_ratio": 1.23,
               "field_factor": 1.0 / 0.6, "reverse_credit": False, "chute_credit": False},
    "mil3013": {"screen_height_ft": 50.0, "approach_speed_ratio": 1.2,
                "field_factor": 1.0, "reverse_credit": True, "chute_credit": True},
}  # fmt: skip


class AircraftConfig(_Model):
    name: str = Field(description="display name, e.g. Boeing 747-100")
    synthetic: bool = False
    description: str = Field(default="", description="free text shown with the aircraft")
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
    certification: CertificationConfig = CertificationConfig()
    landing: LandingConfig = LandingConfig()
    directory: str = Field(default="", description="filled by the loader")

    @model_validator(mode="after")
    def _landing_table_listed(self) -> AircraftConfig:
        c = self.landing.configuration
        if c is not None and c not in self.aero.configurations:
            raise ValueError(f"landing configuration '{c}' is not one of the aero tables")
        return self


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

    rules: RuleSet | None = Field(
        default=None, description="part25 / mil3013; None -> aircraft.certification.rules"
    )
    k_VR: float = Field(default=1.10, gt=1.0, description="VR / V_S")
    optimize_vr: bool = Field(
        default=True,
        description="choose the k_VR (>= the legal minimum) that minimizes the field length; "
        "see docs/rotation_speed.md",
    )
    k_VR_max: float = Field(default=1.6, gt=1.0, description="upper bound of the VR search")
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

    def resolved(
        self, rules: RuleSet = "part25", t_recog_s: float | None = None
    ) -> ProcedureConfig:
        """Copy with every None filled: the rule set from ``rules`` (the aircraft's), then
        the delay from ``t_recog_s`` (the aircraft's), then the rule-set preset."""
        data = self.model_dump()
        if data["rules"] is None:
            data["rules"] = rules
        if data["t_recog_s"] is None and t_recog_s is not None:
            data["t_recog_s"] = t_recog_s
        for k, v in RULE_PRESETS[data["rules"]].items():
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
        """Copy with overrides (validated). Keys are dotted paths,
        ``{"multipliers.k_CL": 1.1}``, or the short names in INPUT_ALIASES,
        ``{"k_CL": 1.1, "weight_lbf": 650e3}``."""
        data = self.model_dump()
        for path, value in expand_inputs(updates).items():
            node = data
            keys = path.split(".")
            for i, k in enumerate(keys):
                if not isinstance(node, dict) or k not in node:
                    known = list(node) if isinstance(node, dict) else []
                    close = difflib.get_close_matches(k, known, n=1)
                    fix = ".".join(keys[:i] + close[:1] + keys[i + 1 :])
                    hint = f" (did you mean '{fix}'?)" if close else ""
                    raise KeyError(f"unknown config field '{path}'{hint}")
                if i < len(keys) - 1:
                    node = node[k]
            node[keys[-1]] = value
        try:
            return RunConfig.model_validate(data)
        except ValidationError as exc:
            lines = explain_validation_error(exc, RunConfig)
            raise InputError("invalid input:\n" + "\n".join(f"  - {x}" for x in lines)) from None

    @property
    def weight_lbf(self) -> float:
        return self.environment.weight_lbf or self.aircraft.weight.default_weight_lbf

    @property
    def chute_active(self) -> bool:
        flag = self.resolved().procedure.chute_enabled
        return self.aircraft.chute.enabled if flag is None else flag

    def resolved(self) -> RunConfig:
        """Copy with the aircraft's rule set and delay, then the rule-set defaults, filled
        into the procedure (idempotent)."""
        c = self.aircraft.certification
        return self.model_copy(update={"procedure": self.procedure.resolved(c.rules, c.t_recog_s)})


# Short names for the inputs scripts change most. Any dotted path works as well.
INPUT_ALIASES: dict[str, str] = {
    "weight_lbf": "environment.weight_lbf",
    "temperature_F": "environment.temperature_F",
    "isa_delta_F": "environment.isa_delta_F",
    "elevation_ft": "environment.elevation_ft",
    "headwind_kts": "environment.headwind_kts",
    "runway_slope_deg": "environment.runway_slope_deg",
    "mu_brake": "environment.mu_brake",
    "mu_roll": "environment.mu_roll",
    "k_CL": "multipliers.k_CL",
    "k_CD": "multipliers.k_CD",
    "rules": "aircraft.certification.rules",
    "aero_table": "aircraft.aero.takeoff_configuration",
    "thrust_table": "aircraft.engines.thrust_table",
    "ground_effect": "aircraft.ground_effect.enabled",
    "optimize_vr": "procedure.optimize_vr",
    "chute": "procedure.chute_enabled",
    "landing_weight_lbf": "aircraft.landing.weight_lbf",
    "landing_k_CL": "aircraft.landing.k_CL",
    "landing_k_CD": "aircraft.landing.k_CD",
}


class InputError(ValueError):
    """An input value that is out of range or of the wrong type."""


def expand_inputs(updates: dict[str, Any] | None) -> dict[str, Any]:
    """Short names -> dotted paths (dotted paths pass through unchanged)."""
    out: dict[str, Any] = {}
    for k, v in (updates or {}).items():
        if "." in k:
            out[k] = v
        elif k in INPUT_ALIASES:
            out[INPUT_ALIASES[k]] = v
        else:
            close = difflib.get_close_matches(k, list(INPUT_ALIASES), n=1)
            hint = f" (did you mean '{close[0]}'?)" if close else ""
            raise KeyError(
                f"unknown input '{k}'{hint}; short names: {', '.join(INPUT_ALIASES)}, "
                "or use a dotted path such as 'environment.weight_lbf'"
            )
    return out


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


def _zip_cache_root() -> Path:
    """Where zipped aircraft are unpacked: ``$BFL_CACHE_DIR`` or ~/.cache/bfl/aircraft_zips."""
    env = os.environ.get("BFL_CACHE_DIR")
    base = Path(env) if env else Path.home() / ".cache" / "bfl"
    return base / "aircraft_zips"


def _unzip_aircraft(zip_path: Path) -> Path:
    """Unpack a zipped aircraft (as the builder exports it) once, keyed by its content.

    The tables are read from disk while solving, so the files must stay on disk: they go
    to a cache folder named after the zip's hash, and the same zip is never unpacked
    twice. ``aircraft.yaml`` may be at the top of the zip or in one folder inside it.
    """
    data = zip_path.read_bytes()
    dest = _zip_cache_root() / hashlib.sha256(data).hexdigest()[:16]
    if not dest.is_dir():
        tmp = dest.with_name(dest.name + f".tmp{os.getpid()}")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                target = (tmp / name).resolve()
                if not str(target).startswith(str(tmp.resolve())):
                    raise ValueError(f"{zip_path.name}: unsafe path in zip: {name}")
            z.extractall(tmp)
        if dest.exists():  # another process got there first
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            tmp.replace(dest)
    if (dest / "aircraft.yaml").is_file():
        return dest
    inner = [p.parent for p in dest.glob("*/aircraft.yaml")]
    if len(inner) != 1:
        raise FileNotFoundError(f"{zip_path.name}: expected one aircraft.yaml in the zip")
    return inner[0]


def resolve_aircraft_dir(aircraft: str | Path) -> Path:
    """Folder of an aircraft, from any of:

    * a name under the aircraft root (``aircraft/`` or ``$BFL_AIRCRAFT_DIR``): "b747_100"
    * a path to a folder that holds ``aircraft.yaml``: "~/designs/concept_a"
    * a path to the ``aircraft.yaml`` file itself
    * a path to a ``.zip`` exported by the builder (unpacked once into a cache)
    """
    p = Path(aircraft).expanduser()
    if p.suffix.lower() == ".zip" and p.is_file():
        return _unzip_aircraft(p).resolve()
    if p.is_file() and p.name.lower().endswith((".yaml", ".yml")):
        return p.parent.resolve()
    if (p / "aircraft.yaml").is_file():
        return p.resolve()
    q = default_aircraft_root() / str(aircraft)
    if (q / "aircraft.yaml").is_file():
        return q.resolve()
    raise FileNotFoundError(f"no aircraft.yaml found for '{aircraft}' (looked in {p} and {q})")


class AircraftFileError(ValueError):
    """An aircraft file that cannot be used, with every problem listed in plain words."""


def _field_info(model: type[BaseModel], loc: tuple) -> tuple[Any, type[BaseModel] | None]:
    """(pydantic FieldInfo or None, model that owns the last key) for an error location."""
    owner: type[BaseModel] | None = model
    info = None
    for key in loc:
        if owner is None or not isinstance(key, str) or key not in owner.model_fields:
            return None, owner
        info = owner.model_fields[key]
        ann = info.annotation
        args = [a for a in typing.get_args(ann) if a is not type(None)] or [ann]
        nxt = args[0]
        owner_prev = owner
        owner = nxt if isinstance(nxt, type) and issubclass(nxt, BaseModel) else None
        if key == loc[-1]:
            return info, owner_prev
    return info, owner


def explain_validation_error(exc: ValidationError, model: type[BaseModel] = None) -> list[str]:
    """One plain-English line per problem in a pydantic ValidationError."""
    model = model or AircraftConfig
    lines = []
    for e in exc.errors():
        loc = tuple(x for x in e["loc"] if not isinstance(x, int))
        path = ".".join(str(x) for x in loc) or "(top level)"
        info, owner = _field_info(model, loc)
        kind = e["type"]
        what = f" ({info.description})" if info is not None and info.description else ""
        if kind == "missing":
            lines.append(f"{path}: missing, and it is required{what}")
        elif kind == "model_type" and e.get("input") is None:
            sub = typing.get_args(info.annotation) if info is not None else ()
            sub_model = next(
                (a for a in sub if isinstance(a, type)), getattr(info, "annotation", None)
            )
            need = []
            if isinstance(sub_model, type) and issubclass(sub_model, BaseModel):
                need = [k for k, f in sub_model.model_fields.items() if f.is_required()]
            lines.append(
                f"{path}: the section is empty" + (f"; it needs {', '.join(need)}" if need else "")
            )
        elif kind == "extra_forbidden":
            known = list(owner.model_fields) if owner is not None else []
            close = difflib.get_close_matches(str(loc[-1]), known, n=1)
            hint = f" (did you mean '{close[0]}'?)" if close else ""
            lines.append(f"{path}: not a known setting{hint}")
        else:
            got = e.get("input")
            shown = f", got {got!r}" if got is not None and not isinstance(got, dict) else ""
            lines.append(f"{path}: {e['msg'][0].lower() + e['msg'][1:]}{shown}{what}")
    return lines


def _check_tables(ac: AircraftConfig, d: Path) -> list[str]:
    """Every CSV the aircraft lists must exist next to its aircraft.yaml."""
    need = [("aero.configurations", f) for f in ac.aero.configurations.values()]
    if ac.engines.thrust_mode == "table":
        need += [("engines.thrust_tables", f) for f in ac.engines.thrust_tables.values()]
    return [
        f"{where}: table file '{f}' not found in {d}" for where, f in need if not (d / f).is_file()
    ]


def load_aircraft(aircraft: str | Path) -> AircraftConfig:
    d = resolve_aircraft_dir(aircraft)
    p = Path(aircraft).expanduser()
    yaml_file = p if p.is_file() and p.suffix.lower() in (".yaml", ".yml") else d / "aircraft.yaml"
    try:
        with open(yaml_file) as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise AircraftFileError(f"{yaml_file} is not valid YAML:\n  {exc}") from None
    if not isinstance(data, dict):
        raise AircraftFileError(f"{yaml_file} is empty or not a mapping of settings")
    data["directory"] = str(d)
    try:
        ac = AircraftConfig.model_validate(data)
    except ValidationError as exc:
        problems = explain_validation_error(exc)
    else:
        problems = _check_tables(ac, d)
        if not problems:
            return ac
    n = len(problems)
    raise AircraftFileError(
        f"{yaml_file} has {n} problem{'s' if n > 1 else ''}:\n"
        + "\n".join(f"  {i}. {p}" for i, p in enumerate(problems, 1))
    )


def load_config(
    aircraft: str | Path,
    run_yaml: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> RunConfig:
    """Build a :class:`RunConfig`.

    Args:
        aircraft: aircraft folder name (under ``aircraft/``), or a path to a folder with
            an ``aircraft.yaml``, to the yaml file itself, or to a builder ``.zip``.
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
