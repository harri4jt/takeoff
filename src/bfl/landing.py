"""Landing distance from 50 ft to a stop, and the runway that landing requires.

    from bfl import load_config, compute_landing
    r = compute_landing(load_config("b747_100"))
    r.runway_required_ft

Sequence (all integrated with the same RK45/RK4 + event location as the takeoff):

    glide : from 50 ft at the approach speed V_A = ratio x V_S(landing), steady on the
            glide slope (constant gamma and V_A)
    flare : constant load factor n (constant g), power to idle, from the height where a
            constant-n pull-up brings gamma from the glide slope to the touchdown sink
            rate, h_flare = V_A^2 / (g (n - 1)) (cos gamma_td - cos gamma_A)
    final : sink rate held to touchdown (only if the flare ended above the runway, which
            it does because the speed bleeds off in the flare)
    roll  : free roll (idle) for free_roll_s, then brakes + spoilers (+ reversers / chute
            where the rules credit them), to V = 0

Landing distance = horizontal distance from the 50 ft point to the stop. Runway required
= field factor x landing distance (Part 25/121: / 0.6).

The landing uses its own weight, aero table and multipliers (aircraft.yaml ``landing:``),
on top of the run's k_CL / k_CD, so a trade study on the aero moves both answers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .config import LANDING_RULES, RunConfig
from .dynamics import SegmentParams
from .integrators import Event
from .model import VehicleModel, build_model
from .phases import SegmentResult, run_segment, stopped_event
from .results import Trajectory, TrajectoryEvent
from .units import DEG_TO_RAD, FTPS_TO_KTS


class LandingError(RuntimeError):
    """The landing could not be completed (e.g. never comes to a stop)."""


@dataclass
class LandingResult:
    """Outcome of :func:`compute_landing`. Speeds KEAS (~KCAS), distances ft."""

    runway_required_ft: float
    landing_distance_ft: float
    air_distance_ft: float
    ground_roll_ft: float
    field_factor: float
    weight_lbf: float
    v_s_kts: float
    v_approach_kts: float
    v_touchdown_kts: float
    touchdown_ground_speed_kts: float
    flare_height_ft: float
    reverse_thrust_fraction: float
    chute_used: bool
    rules: str
    aircraft_name: str
    trajectory: Trajectory
    warnings: list[str] = field(default_factory=list)

    def scalars(self) -> dict[str, Any]:
        """Flat outputs, names prefixed ``landing_`` so they sit beside the takeoff ones."""
        return {
            "landing_runway_required_ft": self.runway_required_ft,
            "landing_distance_ft": self.landing_distance_ft,
            "landing_air_distance_ft": self.air_distance_ft,
            "landing_ground_roll_ft": self.ground_roll_ft,
            "landing_field_factor": self.field_factor,
            "landing_weight_lbf": self.weight_lbf,
            "landing_v_s_kts": self.v_s_kts,
            "landing_v_approach_kts": self.v_approach_kts,
            "landing_v_touchdown_kts": self.v_touchdown_kts,
            "landing_touchdown_ground_speed_kts": self.touchdown_ground_speed_kts,
            "landing_flare_height_ft": self.flare_height_ft,
            "landing_reverse_thrust_fraction": self.reverse_thrust_fraction,
            "landing_chute_used": self.chute_used,
        }

    def to_dataframe(self) -> pd.DataFrame:
        return self.trajectory.to_dataframe()

    def summary(self) -> str:
        mil = self.rules == "mil3013"
        factor = (
            f"x {self.field_factor:.3g} (Part 121: / 0.6)"
            if not mil
            else f"x {self.field_factor:g}"
        )
        devices = []
        if self.reverse_thrust_fraction > 0:
            devices.append(f"reversers {self.reverse_thrust_fraction:.0%} of max thrust")
        if self.chute_used:
            devices.append("drag chute")
        lines = [
            f"Landing - {self.aircraft_name}  [{'MIL-STD-3013' if mil else 'FAA Part 25'}]",
            f"  Landing runway required               {self.runway_required_ft:>9,.0f} ft",
            f"    landing distance from 50 ft          {self.landing_distance_ft:>9,.0f} ft",
            f"      air (50 ft -> touchdown)           {self.air_distance_ft:>9,.0f} ft",
            f"      ground roll                        {self.ground_roll_ft:>9,.0f} ft",
            f"    field factor                         {factor}",
            f"  Landing weight                         {self.weight_lbf:>9,.0f} lb",
            f"  V_S (landing)                          {self.v_s_kts:>9.1f} kt",
            f"  Approach speed                         {self.v_approach_kts:>9.1f} kt",
            f"  Touchdown speed                        {self.v_touchdown_kts:>9.1f} kt",
            f"  Flare starts at                        {self.flare_height_ft:>9.1f} ft",
            f"  Stopping devices                       {', '.join(devices) or 'brakes, spoilers'}",
        ]
        if self.warnings:
            lines.append("  Warnings:")
            lines += [f"   - {w}" for w in self.warnings]
        return "\n".join(lines)


def _ev(name: str, t: float, y) -> TrajectoryEvent:
    return TrajectoryEvent(name, float(t), float(y[0]))


def landing_config(config: RunConfig) -> tuple[RunConfig, dict[str, Any], list[str]]:
    """The run config the landing is flown with, the rule values, and warnings."""
    cfg = config.resolved()
    ac = cfg.aircraft
    lc = ac.landing
    rules = cfg.procedure.rules or ac.certification.rules
    rule = dict(LANDING_RULES[rules])
    warnings: list[str] = []
    if lc.approach_speed_ratio is not None:
        rule["approach_speed_ratio"] = lc.approach_speed_ratio
    if lc.field_factor is not None:
        rule["field_factor"] = lc.field_factor
    reverse = lc.reverse_thrust_fraction if rule["reverse_credit"] else 0.0
    if lc.reverse_thrust_fraction > 0 and not rule["reverse_credit"]:
        warnings.append("reverse thrust not credited (Part 25.125); set but not used")
    chute = lc.use_chute and rule["chute_credit"]
    if chute and (ac.chute.area_ft2 <= 0 or ac.chute.CD <= 0):
        raise ValueError("landing.use_chute: the aircraft has no chute (chute area / CD)")
    if lc.use_chute and not rule["chute_credit"]:
        warnings.append("drag chute not credited for landing under Part 25; set but not used")
    rule["reverse"] = reverse
    rule["chute"] = bool(chute)
    updates = {
        "environment.weight_lbf": lc.weight_lbf or cfg.weight_lbf,
        "multipliers.k_CL": cfg.multipliers.k_CL * lc.k_CL,
        "multipliers.k_CD": cfg.multipliers.k_CD * lc.k_CD,
        "aircraft.aero.takeoff_configuration": lc.configuration or ac.aero.takeoff_configuration,
        "procedure.chute_enabled": bool(chute),
    }
    return cfg.with_updates(updates), rule, warnings


def compute_landing(config: RunConfig) -> LandingResult:
    """Fly the landing: glide, constant-g flare, touchdown, free roll, braking to a stop.

    Distances come from the configured solver (RK45 by default). As for the takeoff, if
    ``solver.trajectory_dt_s`` is set the time history is re-run with RK4 at that step
    so that plots and animations have evenly spaced points.
    """
    result = _fly(config)
    s = config.solver
    if s.method == "rk45" and s.trajectory_dt_s is not None:
        try:
            even = _fly(config.with_updates({"solver.method": "rk4", "solver.dt_s":
                                             s.trajectory_dt_s}))  # fmt: skip
            result.trajectory = even.trajectory
        except Exception:  # noqa: BLE001 - display only; keep the RK45 points
            pass
    return result


def _fly(config: RunConfig) -> LandingResult:
    lcfg, rule, warnings = landing_config(config)
    lc = lcfg.aircraft.landing
    solver = lcfg.solver
    vm: VehicleModel = build_model(lcfg)
    g = vm.g
    n_eng = vm.propulsion.n_engines
    screen = rule["screen_height_ft"]

    v_s = vm.stall_speed_tas()
    v_a = rule["approach_speed_ratio"] * v_s
    gam_a = -lc.approach_angle_deg * DEG_TO_RAD
    gam_td = -math.asin(min(lc.touchdown_sink_rate_fps / v_a, 0.5))
    n = lc.flare_load_factor
    h_flare = v_a * v_a / (g * (n - 1.0)) * (math.cos(gam_td) - math.cos(gam_a))
    if h_flare >= screen:
        warnings.append(
            f"the flare needs {h_flare:.0f} ft, more than the {screen:.0f} ft screen: it starts "
            "at the screen (raise flare_load_factor or lower the glide angle)"
        )

    def params(phase: str, **kw) -> SegmentParams:
        base = dict(theta0=vm.theta_ground_rad, theta_max=vm.theta_ground_rad)
        return SegmentParams(vm, phase, n_eng, idle=True, **{**base, **kw})

    segments: list[SegmentResult] = []
    events: list[TrajectoryEvent] = []
    t, y = 0.0, [0.0, screen, v_a, gam_a]
    t_max = solver.t_max_s

    # glide to the flare height
    if h_flare < screen:
        flare_start = Event(lambda t, y: y[1] - h_flare, "flare", -1, True)
        seg = run_segment("approach", params("glide"), t, y, t + t_max, [flare_start], solver)
        segments.append(seg)
        t, y = seg.t_end, list(seg.y_end)
    events.append(_ev("flare", t, y))

    # constant-g flare to the touchdown sink rate (or to the runway)
    touchdown = Event(lambda t, y: y[1], "touchdown", -1, True)
    level = Event(lambda t, y: y[3] - gam_td, "flare_end", 1, True)
    seg = run_segment("approach", params("flare", load_factor=n), t, y, t + t_max,
                      [touchdown, level], solver)  # fmt: skip
    segments.append(seg)
    t, y = seg.t_end, list(seg.y_end)
    if seg.sol.terminal_event == "flare_end" and y[1] > 0.0:
        seg = run_segment("approach", params("final"), t, y, t + t_max, [touchdown], solver)
        segments.append(seg)
        t, y = seg.t_end, list(seg.y_end)
    if segments[-1].sol.terminal_event != "touchdown":
        raise LandingError("the aircraft did not reach the runway (check the flare settings)")
    events.append(_ev("touchdown", t, y))
    x_td, v_td_air = float(y[0]), float(y[2])
    vw = vm.env.wind(t, x_td, 0.0)
    v_td_ground = v_td_air * math.cos(float(y[3])) - vw
    cl_td = 2.0 * vm.weight_lbf / (vm.rho * v_td_air**2 * vm.S_ft2)
    if cl_td > vm.aero.cl_max:
        warnings.append(
            f"touchdown below the stall speed (CL {cl_td:.2f} > CLmax {vm.aero.cl_max:.2f}): "
            "the flare bleeds off too much speed; lower flare_load_factor"
        )

    # ground roll: free roll at idle, then brakes + spoilers (+ reversers), chute
    t_td = t
    chute_t = t_td + vm.chute.deploy_delay_s if vm.chute is not None else None
    yg = [x_td, v_td_ground]
    roll = params("free_roll", mu=vm.env.mu_roll, chute_t_deploy=chute_t)
    seg = run_segment("ground", roll, t, yg, t + lc.free_roll_s, [stopped_event()], solver)
    segments.append(seg)
    t, yg = seg.t_end, list(seg.y_end)
    if seg.sol.terminal_event != "stopped":
        events.append(_ev("brakes", t, yg))
        if rule["reverse"] > 0:
            events.append(_ev("reversers", t, yg))
        brk = roll.but(phase="braking", mu=vm.env.mu_brake, spoilers=True,
                       reverse=rule["reverse"])  # fmt: skip
        seg = run_segment("ground", brk, t, yg, t + t_max, [stopped_event()], solver)
        segments.append(seg)
        t, yg = seg.t_end, list(seg.y_end)
    if segments[-1].sol.terminal_event != "stopped":
        raise LandingError("the aircraft did not stop within t_max")
    events.append(_ev("stopped", t, yg))
    traj = Trajectory("landing", segments, events)
    if chute_t is not None and chute_t < t:
        df = traj.to_dataframe()
        x_chute = float(np.interp(chute_t, df["t_s"], df["x_ft"]))
        events.append(TrajectoryEvent("chute_deploy", chute_t, x_chute))
    traj.events = sorted(events, key=lambda e: e.t_s)

    total = float(yg[0])
    eas = vm.sqrt_sigma * FTPS_TO_KTS
    return LandingResult(
        runway_required_ft=rule["field_factor"] * total,
        landing_distance_ft=total,
        air_distance_ft=x_td,
        ground_roll_ft=total - x_td,
        field_factor=rule["field_factor"],
        weight_lbf=vm.weight_lbf,
        v_s_kts=v_s * eas,
        v_approach_kts=v_a * eas,
        v_touchdown_kts=v_td_air * eas,
        touchdown_ground_speed_kts=v_td_ground * FTPS_TO_KTS,
        flare_height_ft=min(h_flare, screen),
        reverse_thrust_fraction=rule["reverse"],
        chute_used=rule["chute"],
        rules=lcfg.procedure.rules or lcfg.aircraft.certification.rules,
        aircraft_name=lcfg.aircraft.name,
        trajectory=traj,
        warnings=warnings,
    )


__all__ = ["compute_landing", "LandingResult", "LandingError"]
