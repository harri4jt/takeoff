"""Result containers: Trajectory (time histories) and BFLResult."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

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
    faa_field_length_ft: float
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
    vr_adjustments: list[dict[str, float]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    aircraft_name: str = ""
    synthetic: bool = False
    chute_used: bool = False
    unbalanced_reason: str = ""

    @property
    def v2_over_vs(self) -> float:
        return self.v2_kts / self.v_s_kts

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
            "faa_field_length_ft",
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
        ]
        out = {k: getattr(self, k) for k in keys}
        out["v2_over_vs"] = self.v2_over_vs
        return out

    def summary(self) -> str:
        lines = []
        title = f"Balanced Field Length - {self.aircraft_name}"
        if self.synthetic:
            title += "  [SYNTHETIC DATA]"
        lines.append(title)
        lines.append("=" * len(title))

        def row(label: str, value: str) -> None:
            lines.append(f"  {label:<34s}{value:>16s}")

        status = "balanced" if self.balanced else f"UNBALANCED ({self.unbalanced_reason})"
        row("Status", status)
        row("Balanced field length (BFL)", f"{self.bfl_ft:,.0f} ft")
        row("  go distance at V1", f"{self.d_go_ft:,.1f} ft")
        row("  stop distance at V1", f"{self.d_stop_ft:,.1f} ft")
        row("AEO distance to 35 ft", f"{self.aeo_distance_ft:,.0f} ft")
        row("1.15 x AEO", f"{1.15 * self.aeo_distance_ft:,.0f} ft")
        row("FAA takeoff field length", f"{self.faa_field_length_ft:,.0f} ft")
        lines.append("  Speeds (KEAS ~ KCAS)")
        row("  V_S  (stall, takeoff config)", f"{self.v_s_kts:.1f} kt")
        row("  V_EF (engine failure)", f"{self.v_ef_kts:.1f} kt")
        row("  V1   (decision)", f"{self.v1_kts:.1f} kt")
        row("  VR   (rotation)", f"{self.vr_kts:.1f} kt  (k_VR={self.k_VR:.2f})")
        row("  V_LOF (liftoff, OEI)", f"{self.v_lof_kts:.1f} kt")
        row("  V2   (at 35 ft, OEI)", f"{self.v2_kts:.1f} kt")
        row("  V2 / V_S  (Part 25 wants >= 1.2)", f"{self.v2_over_vs:.3f}")
        row("V1 solver evaluations (f calls)", f"{len(self.v1_solver_history)}")
        if self.chute_used:
            lines.append("  NOTE: drag chute credited - outside FAA Part 25 rules.")
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
