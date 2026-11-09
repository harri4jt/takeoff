"""Takeoff procedures: AEO takeoff, continued (go) and rejected (stop) takeoff.

All speeds in this module are TRUE airspeeds in ft/s (internal units). The
caller (``bfl.bfl``) converts the KEAS V-speeds before calling.

Sequence (FAA Part 25 style, see docs/equations.md):

    common : AEO roll 0 -> V_EF, engine fails, OEI recognition for t_recog -> V1
    go     : OEI roll -> VR, rotate at q_rot to theta_target, N = 0 liftoff,
             climb holding theta_target to the 35 ft screen
    stop   : at V1 brakes; +t_idle operating engines to idle; +t_spoilers spoilers;
             optional chute; decelerate to V = 0; add t_allowance * V1(ground)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import ProcedureConfig, SolverConfig
from .dynamics import SegmentParams, ground_to_air_state
from .model import VehicleModel
from .phases import (
    SegmentResult,
    airspeed_event,
    liftoff_event,
    run_segment,
    screen_event,
    state_at_airspeed,
    stopped_event,
    touchback_event,
    truncate,
)
from .results import Trajectory, TrajectoryEvent
from .rootfind import RootResult, safeguarded_secant


class TakeoffError(RuntimeError):
    """A branch could not be completed (e.g. never reaches the screen height)."""


class TouchbackError(TakeoffError):
    """The aircraft lifted off and then settled back below the runway (h < 0)."""


@dataclass
class Branch:
    """Result of simulating one branch, before conversion to a Trajectory."""

    name: str
    segments: list[SegmentResult]
    distance_ft: float
    events: list[TrajectoryEvent] = field(default_factory=list)
    v_lof_tas: float = float("nan")
    v2_tas: float = float("nan")

    def trajectory(self) -> Trajectory:
        return Trajectory(self.name, self.segments, self.events)


@dataclass
class Prefix:
    """Shared AEO + engine-failure + recognition part, ending exactly at V1."""

    segments: list[SegmentResult]
    t_v1: float
    y_v1: np.ndarray
    v_ef_tas: float
    t_ef: float
    vef_solve: RootResult | None
    warnings: list[str]


def _ev(name: str, t: float, y) -> TrajectoryEvent:
    return TrajectoryEvent(name, float(t), float(y[0]))


def _base_params(vm: VehicleModel, phase: str, n_op: int, engine_out: bool) -> SegmentParams:
    th = vm.theta_ground_rad
    return SegmentParams(
        vm, phase, n_op, engine_out=engine_out, mu=vm.env.mu_roll, theta0=th, theta_max=th
    )


# ------------------------------------------------------------------------------------
# AEO ground roll (cached prefix shared by every V1 evaluation)
# ------------------------------------------------------------------------------------
def aeo_ground_roll(vm: VehicleModel, v_r: float, solver: SolverConfig) -> SegmentResult:
    """All-engines roll from brake release (V = 0) to airspeed VR."""
    p = _base_params(vm, "aeo_roll", vm.propulsion.n_engines, False)
    events = [airspeed_event("ground", p, v_r, "VR"), liftoff_event(p)]
    seg = run_segment("ground", p, 0.0, [0.0, 0.0], solver.t_max_s, events, solver)
    if seg.sol.terminal_event == "liftoff":
        raise TakeoffError("aircraft lifted off before VR at ground attitude; check aero table")
    if seg.sol.terminal_event != "VR":
        raise TakeoffError(f"AEO roll never reached VR within t_max={solver.t_max_s} s")
    return seg


# ------------------------------------------------------------------------------------
# rotation + climb (shared by go and AEO)
# ------------------------------------------------------------------------------------
def rotate_and_climb(
    vm: VehicleModel,
    t_r: float,
    y_r,
    n_op: int,
    engine_out: bool,
    proc: ProcedureConfig,
    solver: SolverConfig,
    name: str,
    segments: list[SegmentResult],
    events: list[TrajectoryEvent],
) -> Branch:
    """Rotate at VR, lift off at N = 0, climb holding theta_target to the screen height."""
    rate = vm.rotation_rate_rad_s
    th0, th_t = vm.theta_ground_rad, vm.theta_target_rad
    t_cap = t_r + (th_t - th0) / rate
    p_rot = SegmentParams(
        vm,
        "rotation",
        n_op,
        engine_out=engine_out,
        mu=vm.env.mu_roll,
        theta0=th0,
        t_theta0=t_r,
        theta_rate=rate,
        theta_max=th_t,
    )
    events.append(_ev("VR", t_r, y_r))
    t_limit = t_r + solver.t_max_s

    # ground rotation, then (if still on the ground) roll holding theta_target
    seg = run_segment("ground", p_rot, t_r, y_r, t_cap, [liftoff_event(p_rot)], solver)
    segments.append(seg)
    if seg.sol.terminal_event != "liftoff":
        events.append(_ev("theta_target", seg.t_end, seg.y_end))
        seg = run_segment(
            "ground", p_rot, seg.t_end, seg.y_end, t_limit, [liftoff_event(p_rot)], solver
        )
        segments.append(seg)
        if seg.sol.terminal_event != "liftoff":
            raise TakeoffError(f"{name}: no liftoff (N never reached 0) within t_max")
    t_lof, y_lof = seg.t_end, seg.y_end
    events.append(_ev("liftoff", t_lof, y_lof))

    # airborne
    p_air = p_rot.but(phase="airborne", mu=0.0)
    y_air = ground_to_air_state(t_lof, y_lof, p_air)
    v_lof = float(y_air[2])
    air_events = [
        screen_event(proc.screen_height_ft),
        touchback_event(solver.touchback_tolerance_ft),
    ]
    seg = run_segment(
        "air",
        p_air,
        t_lof,
        y_air,
        min(t_cap, t_limit) if t_lof < t_cap else t_limit,
        air_events,
        solver,
    )
    segments.append(seg)
    if t_lof < t_cap and seg.sol.terminal_event is None:  # pitch-up finished in the air
        events.append(_ev("theta_target", seg.t_end, seg.y_end))
        seg = run_segment("air", p_air, seg.t_end, seg.y_end, t_limit, air_events, solver)
        segments.append(seg)
    term = segments[-1].sol.terminal_event
    if term == "touchback":
        raise TouchbackError(f"{name}: aircraft settled back onto the runway after liftoff")
    if term != "screen_height":
        raise TakeoffError(f"{name}: did not reach the screen height within t_max")
    y_scr = segments[-1].y_end
    events.append(_ev("screen_height", segments[-1].t_end, y_scr))
    return Branch(name, segments, float(y_scr[0]), events, v_lof, float(y_scr[2]))


def simulate_aeo(
    vm: VehicleModel, roll: SegmentResult, proc: ProcedureConfig, solver: SolverConfig
) -> Branch:
    """All-engines takeoff to the screen height (no failure)."""
    segments = [roll]
    events = [_ev("brake_release", 0.0, roll.sol.y[0])]
    return rotate_and_climb(
        vm,
        roll.t_end,
        roll.y_end,
        vm.propulsion.n_engines,
        False,
        proc,
        solver,
        "aeo",
        segments,
        events,
    )


# ------------------------------------------------------------------------------------
# engine failure + recognition (inner secant solve for V_EF)
# ------------------------------------------------------------------------------------
def engine_failure_prefix(
    vm: VehicleModel, roll: SegmentResult, v1: float, proc: ProcedureConfig, solver: SolverConfig
) -> Prefix:
    """Find V_EF such that OEI acceleration for t_recog ends exactly at V1."""
    n_oei = vm.propulsion.n_engines - 1
    t_rec = proc.t_recog_s
    tol = solver.event_tol_s
    if t_rec == 0.0:
        loc = state_at_airspeed(roll, v1, tol)
        if loc is None:
            raise TakeoffError("V1 outside the AEO roll range")
        t1, y1 = loc
        return Prefix([truncate(roll, t1, y1)], t1, y1, v1, t1, None, [])

    p_rec = _base_params(vm, "oei_recog", n_oei, True)
    cache: dict[float, tuple[float, np.ndarray, SegmentResult]] = {}

    def recog_end(v_ef: float) -> float:
        loc = state_at_airspeed(roll, v_ef, tol)
        if loc is None:
            raise TakeoffError(f"V_EF={v_ef:.3f} ft/s outside AEO roll")
        t_ef, y_ef = loc
        seg = run_segment("ground", p_rec, t_ef, y_ef, t_ef + t_rec, [], solver)
        cache[v_ef] = (t_ef, y_ef, seg)
        return float(seg.airspeeds()[-1]) - v1

    va = roll.airspeeds()
    lo = float(va[0])  # engine fails at brake release
    f_lo = recog_end(lo)
    if f_lo >= 0.0:
        raise TakeoffError(
            f"V1 is reached within t_recog={t_rec} s even if the engine fails at brake "
            "release; V1 is too low for this recognition time (raise V1_min or V_mcg)"
        )
    f_hi = recog_end(v1)
    if f_hi <= 0.0:
        raise TakeoffError("aircraft cannot accelerate on the remaining engines at V1")
    res = safeguarded_secant(
        recog_end, lo, v1, xtol=1e-10, ftol=solver.vef_tol_ftps, fa=f_lo, fb=f_hi
    )
    v_ef = res.root
    if v_ef not in cache:
        recog_end(v_ef)
    t_ef, y_ef, seg_rec = cache[v_ef]
    segments = [truncate(roll, t_ef, y_ef), seg_rec]
    return Prefix(segments, seg_rec.t_end, seg_rec.y_end, v_ef, t_ef, res, [])


def _prefix_events(prefix: Prefix) -> list[TrajectoryEvent]:
    ev = [_ev("brake_release", 0.0, prefix.segments[0].sol.y[0])]
    ev.append(_ev("engine_failure", prefix.t_ef, prefix.segments[0].y_end))
    ev.append(_ev("V1", prefix.t_v1, prefix.y_v1))
    return ev


# ------------------------------------------------------------------------------------
# go / stop branches
# ------------------------------------------------------------------------------------
def simulate_go(
    vm: VehicleModel, prefix: Prefix, v_r: float, proc: ProcedureConfig, solver: SolverConfig
) -> Branch:
    """Continued takeoff with one engine inoperative, from V1 to the screen height."""
    n_oei = vm.propulsion.n_engines - 1
    segments = list(prefix.segments)
    events = _prefix_events(prefix)
    t, y = prefix.t_v1, prefix.y_v1
    p = _base_params(vm, "oei_roll", n_oei, True)
    va1 = float(y[1] + vm.env.wind(t, y[0], 0.0))
    if va1 < v_r - 1e-9:
        seg = run_segment(
            "ground",
            p,
            t,
            y,
            t + solver.t_max_s,
            [airspeed_event("ground", p, v_r, "VR"), liftoff_event(p)],
            solver,
        )
        segments.append(seg)
        if seg.sol.terminal_event != "VR":
            raise TakeoffError(f"go: OEI roll ended by {seg.sol.terminal_event} before VR")
        t, y = seg.t_end, seg.y_end
    return rotate_and_climb(vm, t, y, n_oei, True, proc, solver, "go", segments, events)


def simulate_stop(
    vm: VehicleModel, prefix: Prefix, proc: ProcedureConfig, solver: SolverConfig
) -> Branch:
    """Rejected takeoff from V1 to a full stop, plus the V1 distance allowance."""
    n_oei = vm.propulsion.n_engines - 1
    t1, y1 = prefix.t_v1, prefix.y_v1
    segments = list(prefix.segments)
    events = _prefix_events(prefix)

    switches = {"brakes": proc.t_brakes_s, "idle": proc.t_idle_s, "spoilers": proc.t_spoilers_s}
    if vm.chute is not None:
        switches["chute_deploy"] = vm.chute.deploy_delay_s
        switches["chute_full"] = vm.chute.deploy_delay_s + vm.chute.inflation_time_s
    bounds = sorted({0.0, *switches.values()})

    t, y = t1, y1
    for k, b in enumerate(bounds):
        rel = b
        on = {name: rel >= ts for name, ts in switches.items()}
        for name, ts in switches.items():
            if ts == b and name != "chute_full":
                events.append(_ev(name, t, y))
        p = SegmentParams(
            vm,
            "braking" if on["brakes"] else "oei_roll",
            n_oei,
            idle=on["idle"],
            engine_out=True,
            mu=vm.env.mu_brake if on["brakes"] else vm.env.mu_roll,
            spoilers=on["spoilers"],
            theta0=vm.theta_ground_rad,
            theta_max=vm.theta_ground_rad,
            chute_t_deploy=(t1 + vm.chute.deploy_delay_s) if vm.chute is not None else None,
        )
        t_end = t1 + bounds[k + 1] if k + 1 < len(bounds) else t1 + solver.t_max_s
        seg = run_segment("ground", p, t, y, t_end, [stopped_event()], solver)
        segments.append(seg)
        t, y = seg.t_end, seg.y_end
        if seg.sol.terminal_event == "stopped":
            break
    if segments[-1].sol.terminal_event != "stopped":
        raise TakeoffError("stop: aircraft did not come to rest within t_max")
    events.append(_ev("stopped", t, y))
    v1_ground = float(y1[1])
    allowance = proc.t_v1_allowance_s * v1_ground
    return Branch("stop", segments, float(y[0]) + allowance, events)
