"""Aerodynamic model: table CL(alpha), CD(alpha) with user multipliers and increments.

    CL = k_CL * CL_table(alpha) + dCL_spoiler * [spoilers deployed]
    CD = k_CD * CD_table(alpha) + dCD_engine_out * [engine failed] + dCD_spoiler * [spoilers]

The multipliers scale only the clean table (so k_CL moves CLmax, V_S and VR); the
device/failure increments are added unscaled, keeping the lift-vs-drag comparison
about the airframe itself. CLmax = k_CL * max(CL_table).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
class AeroModel:
    table: AeroTable
    k_CL: float = 1.0
    k_CD: float = 1.0
    dCD_engine_out: float = 0.0
    dCL_spoiler: float = 0.0
    dCD_spoiler: float = 0.0

    @property
    def cl_max(self) -> float:
        """Maximum CL of the takeoff configuration, including the k_CL multiplier."""
        return self.k_CL * self.table.cl_max

    def coefficients(
        self, alpha_rad: float, engine_out: bool, spoilers: bool
    ) -> tuple[float, float]:
        cl = self.k_CL * self.table.cl(alpha_rad)
        cd = self.k_CD * self.table.cd(alpha_rad)
        if engine_out:
            cd += self.dCD_engine_out
        if spoilers:
            cl += self.dCL_spoiler
            cd += self.dCD_spoiler
        return cl, cd
