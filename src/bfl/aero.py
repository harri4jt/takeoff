"""Aerodynamic model: table CL(alpha), CD(alpha) with user multipliers and increments.

    CL = k_CL * CL_table(alpha) + dCL_spoiler * [spoilers deployed]
    CD = k_CD * CD_table(alpha) + dCD_engine_out * [engine failed] + dCD_spoiler * [spoilers]

The multipliers scale only the clean table (so k_CL moves CLmax, V_S and VR); the
device/failure increments are added unscaled, keeping the lift-vs-drag comparison
about the airframe itself. CLmax = k_CL * max(CL_table), unless the aircraft gives an
explicit CLmax for the configuration (``aero.CLmax`` in aircraft.yaml), in which case
CLmax = k_CL * that value. The explicit value only sets V_S; the CL(alpha) curve the
dynamics use is unchanged.

Optional ground effect (Raymer, drag only): the induced part K*CL^2 of the drag is
multiplied by phi(h/b) = 33 (h/b)^1.5 / (1 + 33 (h/b)^1.5), i.e.

    CD -= (1 - phi) * K * CL^2,

with K from a least-squares fit CD = CD0 + K CL^2 of the (scaled) table. phi -> 1 far
from the ground; on the runway (h/b ~ 0.1-0.2) it is ~0.5-0.75. See docs/ground_effect.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .tables import Interpolator1D, read_csv_table
from .units import DEG_TO_RAD


@dataclass(frozen=True)
class AeroTable:
    """CL and CD vs alpha [rad] for one flap configuration."""

    cl: Interpolator1D
    cd: Interpolator1D
    source: str

    @property
    def cl_max(self) -> float:
        return self.cl.y_max

    @property
    def alpha_range_rad(self) -> tuple[float, float]:
        return self.cl.x_min, self.cl.x_max


def load_aero_table(
    path: str | Path, method: str = "linear", out_of_range: str = "error"
) -> AeroTable:
    """Load ``alpha_deg, CL, CD`` (extra columns ignored). Alpha must be increasing."""
    df = read_csv_table(path, ["alpha_deg", "CL", "CD"])
    alpha = [a * DEG_TO_RAD for a in df["alpha_deg"]]
    name = Path(path).name
    return AeroTable(
        cl=Interpolator1D(alpha, df["CL"], method, out_of_range, f"{name}:CL(alpha)"),
        cd=Interpolator1D(alpha, df["CD"], method, out_of_range, f"{name}:CD(alpha)"),
        source=str(path),
    )


@dataclass(frozen=True)
class PolarFit:
    """Least-squares parabolic polar CD = CD0 + K CL^2 of a table."""

    CD0: float
    K: float
    r2: float
    n_points: int
    cl_max_used: float


def fit_parabolic_polar(table: AeroTable, cl_fraction: float = 0.85) -> PolarFit:
    """Fit CD = CD0 + K CL^2 over the table points with 0 < CL <= cl_fraction * CLmax.

    Only the attached-flow part of the curve is used: near CLmax the drag rises faster
    than the parabola. Linear least squares in (1, CL^2) via the normal equations.
    """
    cl = np.asarray(table.cl.y)
    cd = np.asarray(table.cd.y)
    top = cl_fraction * cl.max()
    m = (cl > 0.0) & (cl <= top)
    if m.sum() < 3:
        raise ValueError(f"{table.source}: fewer than 3 points with 0 < CL <= {top:.3f} to fit")
    x = cl[m] ** 2
    a = np.column_stack([np.ones_like(x), x])
    (cd0, k), *_ = np.linalg.lstsq(a, cd[m], rcond=None)
    pred = cd0 + k * x
    ss_res = float(((cd[m] - pred) ** 2).sum())
    ss_tot = float(((cd[m] - cd[m].mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    if k <= 0:
        raise ValueError(f"{table.source}: fitted K = {k:.4f} <= 0; give ground_effect.K")
    return PolarFit(float(cd0), float(k), r2, int(m.sum()), float(top))


def raymer_phi(h_over_b: float) -> float:
    """Raymer's ground-effect factor on induced drag (1 = free air)."""
    if h_over_b <= 0.0:
        return 0.0
    u = 33.0 * h_over_b**1.5
    return u / (1.0 + u)


@dataclass(frozen=True)
class GroundEffect:
    span_ft: float
    wing_height_ft: float
    K: float  # induced-drag factor of the SCALED polar (k_CD applied)

    def delta_cd(self, cl: float, h_ft: float) -> float:
        phi = raymer_phi((self.wing_height_ft + max(h_ft, 0.0)) / self.span_ft)
        return -(1.0 - phi) * self.K * cl * cl


@dataclass(frozen=True)
class AeroModel:
    table: AeroTable
    k_CL: float = 1.0
    k_CD: float = 1.0
    dCD_engine_out: float = 0.0
    dCL_spoiler: float = 0.0
    dCD_spoiler: float = 0.0
    cl_max_override: float | None = None
    ground_effect: GroundEffect | None = None

    @property
    def cl_max(self) -> float:
        """CLmax for V_S (explicit value if given, else table max), times k_CL."""
        base = self.table.cl_max if self.cl_max_override is None else self.cl_max_override
        return self.k_CL * base

    def coefficients(
        self, alpha_rad: float, engine_out: bool, spoilers: bool, h_ft: float = 0.0
    ) -> tuple[float, float]:
        cl = self.k_CL * self.table.cl(alpha_rad)
        cd = self.k_CD * self.table.cd(alpha_rad)
        if engine_out:
            cd += self.dCD_engine_out
        if spoilers:
            cl += self.dCL_spoiler
            cd += self.dCD_spoiler
        if self.ground_effect is not None:
            cd += self.ground_effect.delta_cd(cl, h_ft)
        return cl, cd
