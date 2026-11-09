"""Build the internal (ft-slug-s-lbf-R-rad) vehicle model from a RunConfig.

This is the single boundary where configuration units are converted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from .aero import AeroModel, load_aero_table
from .atmosphere import atmosphere
from .config import RunConfig
from .environment import Environment, SteadyWind
from .propulsion import ConstantThrust, Propulsion, load_thrust_table
from .units import DEG_TO_RAD, G0_FTPS2, KTS_TO_FTPS


@dataclass(frozen=True)
class ChuteModel:
    area_ft2: float
    CD: float
    deploy_delay_s: float
    inflation_time_s: float


@dataclass(frozen=True)
class VehicleModel:
    """Everything the dynamics need, in internal units."""

    weight_lbf: float
    mass_slug: float
    g: float
    S_ft2: float
    aero: AeroModel
    propulsion: Propulsion
    env: Environment
    theta_ground_rad: float
    theta_target_rad: float
    rotation_rate_rad_s: float
    chute: ChuteModel | None  # None when not deployed in this run
    v_mcg_eas_ftps: float | None

    # -- convenience ------------------------------------------------------------
    @property
    def rho(self) -> float:
        return self.env.atmosphere.density_slugft3

    @property
    def temp_R(self) -> float:
        return self.env.atmosphere.temperature_R

    @property
    def sqrt_sigma(self) -> float:
        return math.sqrt(self.env.atmosphere.sigma)

    def tas_to_eas(self, v_tas: float) -> float:
        return v_tas * self.sqrt_sigma

    def eas_to_tas(self, v_eas: float) -> float:
        return v_eas / self.sqrt_sigma

    def stall_speed_tas(self) -> float:
        """V_S = sqrt(2 W / (rho S CLmax)), field density -> true airspeed."""
        return math.sqrt(2.0 * self.weight_lbf / (self.rho * self.S_ft2 * self.aero.cl_max))


def build_model(cfg: RunConfig) -> VehicleModel:
    ac, env, proc, sol, mult = (
        cfg.aircraft,
        cfg.environment,
        cfg.procedure,
        cfg.solver,
        cfg.multipliers,
    )
    d = Path(ac.directory)
    table = load_aero_table(
        d / ac.aero.configurations[ac.aero.takeoff_configuration],
        sol.interpolation,
        sol.out_of_range,
    )
    aero = AeroModel(
        table,
        mult.k_CL,
        mult.k_CD,
        ac.aero.delta_CD_engine_out,
        ac.spoilers.delta_CL,
        ac.spoilers.delta_CD,
    )

    eng = ac.engines
    if eng.thrust_mode == "constant":
        thrust = ConstantThrust(float(eng.thrust_per_engine_lbf))
    else:
        thrust = load_thrust_table(d / str(eng.thrust_table), sol.interpolation, sol.out_of_range)
    prop = Propulsion(
        thrust, eng.n_engines, eng.idle_thrust_per_engine_lbf, eng.thrust_incidence_deg * DEG_TO_RAD
    )

    atm = atmosphere(env.elevation_ft, env.temperature_F, env.isa_delta_F)
    environment = Environment(
        atm,
        SteadyWind(env.headwind_kts * KTS_TO_FTPS),
        env.runway_slope_deg * DEG_TO_RAD,
        env.mu_roll,
        env.mu_brake,
    )

    theta_g = ac.attitude.theta_ground_deg * DEG_TO_RAD
    theta_t = (ac.attitude.theta_tailstrike_deg - proc.tailstrike_margin_deg) * DEG_TO_RAD
    if theta_t <= theta_g:
        raise ValueError("tail-strike angle minus margin must exceed the ground attitude")

    chute = None
    if cfg.chute_active:
        c = ac.chute
        if c.area_ft2 <= 0 or c.CD <= 0:
            raise ValueError("chute enabled but area_ft2 / CD not set for this aircraft")
        chute = ChuteModel(c.area_ft2, c.CD, c.deploy_delay_s, c.inflation_time_s)

    w = cfg.weight_lbf
    vmcg = ac.speeds.V_mcg_kts
    return VehicleModel(
        weight_lbf=w,
        mass_slug=w / G0_FTPS2,
        g=G0_FTPS2,
        S_ft2=ac.geometry.wing_area_ft2,
        aero=aero,
        propulsion=prop,
        env=environment,
        theta_ground_rad=theta_g,
        theta_target_rad=theta_t,
        rotation_rate_rad_s=proc.rotation_rate_deg_s * DEG_TO_RAD,
        chute=chute,
        v_mcg_eas_ftps=None if vmcg is None else vmcg * KTS_TO_FTPS,
    )
