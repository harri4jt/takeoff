"""Result containers: Trajectory (time histories) and BFLResult."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import numpy as np
import pandas as pd

from .dynamics import forces
from .phases import SegmentResult

TRAJECTORY_COLUMNS = [
    "t_s",
    "x_ft",
    "h_ft",
    "V_ground_kts",
    "V_air_kts",
    "gamma_deg",
    "theta_deg",
    "alpha_deg",
    "CL",
    "CD",
    "L_lbf",
    "D_lbf",
    "T_total_lbf",
    "N_lbf",
    "F_friction_lbf",
    "q_bar_psf",
    "mu",
    "fuel_burned_lbf",
    "phase",
]


@dataclass
class TrajectoryEvent:
    name: str
    t_s: float
    x_ft: float


@dataclass
class Trajectory:
    """A chain of integration segments (one branch: AEO, go, or stop)."""

    name: str
    segments: list[SegmentResult]
    events: list[TrajectoryEvent] = field(default_factory=list)

    @cached_property
    def _df(self) -> pd.DataFrame:
        rows = []
        for seg in self.segments:
            p, kind = seg.params, seg.kind
            for t, y in zip(seg.sol.t, seg.sol.y, strict=True):
                r = forces(float(t), y, p, kind)
                r["phase"] = p.phase
                rows.append(r)
        df = pd.DataFrame(rows)
        extra = [c for c in df.columns if c not in TRAJECTORY_COLUMNS]
        return df[TRAJECTORY_COLUMNS + extra]

    def to_dataframe(self) -> pd.DataFrame:
        """One row per accepted step plus every event point (segment boundaries repeat)."""
        return self._df.copy()

    def events_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame([e.__dict__ for e in self.events])

    @property
    def t_end(self) -> float:
        return self.segments[-1].t_end

    @property
    def n_steps(self) -> int:
        return sum(s.sol.n_steps for s in self.segments)


@dataclass
class BFLResult:
    """Outcome of :func:`bfl.compute_bfl`. Speeds are KEAS (~KCAS); distances in ft."""

    bfl_ft: float
    balanced: bool
    v1_kts: float
    vr_kts: float
    v_ef_kts: float
    v_s_kts: float
    v_lof_kts: float
    v2_kts: float
    aeo_distance_ft: float
    field_length_ft: float
    d_go_ft: float
    d_stop_ft: float
    go: Trajectory
    stop: Trajectory
    aeo: Trajectory
    k_VR: float
    v1_min_kts: float
    v1_ground_kts: float
    density_slugft3: float
    v1_solver_history: list[dict[str, float]] = field(default_factory=list)
    vr_adjustments: list[dict[str, Any]] = field(default_factory=list)
    vr_optimization: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    aircraft_name: str = ""
    synthetic: bool = False
    chute_used: bool = False
    unbalanced_reason: str = ""
    rules: str = "part25"
    screen_height_ft: float = 35.0
    field_length_aeo_factor: float = 1.15
    t_recog_s: float = 1.0
    runway_available_ft: float | None = None
    refusal_v1_kts: float | None = None
    refusal_v_ef_kts: float | None = None
    polar_fit: dict[str, float] | None = None

    @property
    def v2_over_vs(self) -> float:
        return self.v2_kts / self.v_s_kts

    @property
    def is_mil(self) -> bool:
        return self.rules == "mil3013"

    @property
    def faa_field_length_ft(self) -> float:
        """Back-compatible name of :attr:`field_length_ft`."""
        return self.field_length_ft

    # -- gear / fuel outputs (from the reported time histories) -------------------------
    @cached_property
    def max_tire_speed_kts(self) -> float:
        """Highest ground speed while on the wheels, over all three branches."""
        best = 0.0
        for tr in (self.go, self.stop, self.aeo):
            df = tr.to_dataframe()
            on = df[df["h_ft"] <= 0.0]
            if len(on):
                best = max(best, float(on["V_ground_kts"].max()))
        return best

    @cached_property
    def brake_energy_MJ(self) -> float:
        """Energy the brakes absorb in the rejected takeoff, integral of mu N V dt."""
        df = self.stop.to_dataframe()
        b = df[df["phase"] == "braking"]
        if len(b) < 2:
            return 0.0
        power = b["F_friction_lbf"].to_numpy() * b["V_ground_kts"].to_numpy() * 1.6878098571011957
        t = b["t_s"].to_numpy()
        energy_ftlbf = float(np.sum(0.5 * (power[1:] + power[:-1]) * np.diff(t)))
        return energy_ftlbf * 1.3558179483314004e-6

    def _fuel(self, tr: Trajectory) -> float:
        return float(tr.to_dataframe()["fuel_burned_lbf"].iloc[-1])

    @cached_property
    def fuel_used_go_lbf(self) -> float:
        return self._fuel(self.go)

    @cached_property
    def fuel_used_stop_lbf(self) -> float:
        return self._fuel(self.stop)

    @cached_property
    def fuel_used_aeo_lbf(self) -> float:
        return self._fuel(self.aeo)

    # labels that depend on the rule set
    @property
    def names(self) -> dict[str, str]:
        if self.is_mil:
            return {
                "rules": "MIL-STD-3013",
                # MIL-STD-3013 calls it the critical field length; BFL here for consistency
                "bfl": "Balanced field length (BFL)",
                "bfl_short": "BFL",
                "v1": "V_brake (brakes on)",
                "v_ef": "V_CEF (critical engine failure)",
                "field": "Runway required (max of BFL, AEO to 50 ft)",
                "v2": "V_obs (at 50 ft, OEI)",
            }
        return {
            "rules": "FAA Part 25",
            "bfl": "Balanced field length (BFL)",
            "bfl_short": "BFL",
            "v1": "V1 (decision)",
            "v_ef": "V_EF (engine failure)",
            "field": "FAA takeoff field length",
            "v2": "V2 (at 35 ft, OEI)",
        }

    def scalars(self) -> dict[str, Any]:
        keys = [
            "bfl_ft",
            "balanced",
            "v1_kts",
            "vr_kts",
            "v_ef_kts",
            "v_s_kts",
            "v_lof_kts",
            "v2_kts",
            "aeo_distance_ft",
            "field_length_ft",
            "d_go_ft",
            "d_stop_ft",
            "k_VR",
            "v1_min_kts",
            "v1_ground_kts",
            "density_slugft3",
            "aircraft_name",
            "synthetic",
            "chute_used",
            "unbalanced_reason",
            "rules",
            "screen_height_ft",
            "field_length_aeo_factor",
            "t_recog_s",
            "runway_available_ft",
            "refusal_v1_kts",
            "refusal_v_ef_kts",
            "max_tire_speed_kts",
            "brake_energy_MJ",
            "fuel_used_go_lbf",
            "fuel_used_stop_lbf",
            "fuel_used_aeo_lbf",
        ]
        out = {k: getattr(self, k) for k in keys}
        out["faa_field_length_ft"] = self.field_length_ft
        out["v2_over_vs"] = self.v2_over_vs
        out["polar_fit"] = self.polar_fit
        out["vr_optimization"] = self.vr_optimization
        return out

    def summary(self) -> str:
        lines = []
        n = self.names
        h = f"{self.screen_height_ft:.0f} ft"
        title = f"{n['bfl'].split(' (')[0]} - {self.aircraft_name}  [{n['rules']}]"
        if self.synthetic:
            title += "  [SYNTHETIC DATA]"
        lines.append(title)
        lines.append("=" * len(title))

        def row(label: str, value: str) -> None:
            lines.append(f"  {label:<34s}{value:>16s}")

        status = "balanced" if self.balanced else f"UNBALANCED ({self.unbalanced_reason})"
        row("Status", status)
        row(n["bfl"], f"{self.bfl_ft:,.0f} ft")
        row("  go distance", f"{self.d_go_ft:,.1f} ft")
        row("  stop distance", f"{self.d_stop_ft:,.1f} ft")
        row(f"AEO distance to {h}", f"{self.aeo_distance_ft:,.0f} ft")
        f = self.field_length_aeo_factor
        if f != 1.0:
            row(f"{f:g} x AEO", f"{f * self.aeo_distance_ft:,.0f} ft")
        row(n["field"], f"{self.field_length_ft:,.0f} ft")
        lines.append("  Speeds (KEAS ~ KCAS)")
        row("  V_S  (stall, takeoff config)", f"{self.v_s_kts:.1f} kt")
        row(f"  {n['v_ef']}", f"{self.v_ef_kts:.1f} kt")
        row(f"  {n['v1']}", f"{self.v1_kts:.1f} kt")
        row("  VR   (rotation)", f"{self.vr_kts:.1f} kt  (k_VR={self.k_VR:.3f})")
        row("  V_LOF (liftoff, OEI)", f"{self.v_lof_kts:.1f} kt")
        row(f"  {n['v2']}", f"{self.v2_kts:.1f} kt")
        row("  V2 / V_S  (rule wants >= 1.2)", f"{self.v2_over_vs:.3f}")
        vo = self.vr_optimization
        if vo is not None:
            row(
                "  VR optimization",
                f"k_VR {vo['k_VR_old']:.3f} -> {vo['k_VR_new']:.3f}, "
                f"{vo['field_length_min_vr_ft']:,.0f} -> {vo['field_length_opt_ft']:,.0f} ft",
            )
        if self.refusal_v1_kts is not None:
            row(
                f"  refusal speed ({self.runway_available_ft:,.0f} ft)",
                f"{self.refusal_v_ef_kts:.1f} kt",
            )
        lines.append("  Gear and fuel")
        row("  max ground speed on tires", f"{self.max_tire_speed_kts:.1f} kt")
        row("  brake energy (rejected takeoff)", f"{self.brake_energy_MJ:,.0f} MJ")
        if self.fuel_used_go_lbf > 0:
            row(f"  fuel used, OEI go to {h}", f"{self.fuel_used_go_lbf:,.0f} lb")
        row("V1 solver evaluations (f calls)", f"{len(self.v1_solver_history)}")
        if self.chute_used:
            lines.append(
                "  NOTE: drag chute credited"
                + ("." if self.is_mil else " - outside FAA Part 25 rules.")
            )
        if self.warnings:
            lines.append("  Warnings:")
            lines.extend(f"   - {w}" for w in self.warnings)
        return "\n".join(lines)

    def to_json(self, include_trajectories: bool = False, indent: int = 2) -> str:
        data = self.scalars()
        data["v1_solver_history"] = self.v1_solver_history
        data["vr_adjustments"] = self.vr_adjustments
        data["warnings"] = self.warnings
        data["events"] = {
            name: [e.__dict__ for e in tr.events]
            for name, tr in (("go", self.go), ("stop", self.stop), ("aeo", self.aeo))
        }
        if include_trajectories:
            data["trajectories"] = {
                name: tr.to_dataframe().to_dict(orient="list")
                for name, tr in (("go", self.go), ("stop", self.stop), ("aeo", self.aeo))
            }
        return json.dumps(data, indent=indent, default=float)
