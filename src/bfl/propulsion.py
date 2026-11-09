"""Thrust models (per engine) and the engines-operating-aware propulsion wrapper.

Table lookups use max(V_air, 0): with a tailwind the airspeed is negative at brake
release and the table is not meant to be extrapolated to "backwards" flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .tables import Interpolator1D, Interpolator2D, grid_from_long, read_csv_table
from .units import KTS_TO_FTPS, F_to_R


class ThrustModel(Protocol):
    def per_engine(self, v_air_ftps: float, temp_R: float) -> float: ...


@dataclass(frozen=True)
class ConstantThrust:
    thrust_lbf: float

    def per_engine(self, v_air_ftps: float, temp_R: float) -> float:
        return self.thrust_lbf


@dataclass(frozen=True)
class TableThrust1D:
    table: Interpolator1D  # x: airspeed ft/s

    def per_engine(self, v_air_ftps: float, temp_R: float) -> float:
        return self.table(max(v_air_ftps, 0.0))


@dataclass(frozen=True)
class TableThrust2D:
    table: Interpolator2D  # x: airspeed ft/s, y: temperature R

    def per_engine(self, v_air_ftps: float, temp_R: float) -> float:
        return self.table(max(v_air_ftps, 0.0), temp_R)


def load_thrust_table(
    path: str | Path, method: str = "linear", out_of_range: str = "error"
) -> ThrustModel:
    """``airspeed_kts, thrust_lbf`` (1-D) or ``airspeed_kts, temperature_F, thrust_lbf`` (2-D)."""
    df = read_csv_table(path, ["airspeed_kts", "thrust_lbf"])
    name = Path(path).name
    if "temperature_F" in df.columns:
        x, y, z = grid_from_long(df, "airspeed_kts", "temperature_F", "thrust_lbf")
        return TableThrust2D(
            Interpolator2D(
                [v * KTS_TO_FTPS for v in x],
                [F_to_R(t) for t in y],
                z,
                out_of_range,
                f"{name}:T(V,temp)",
            )
        )
    df = df.sort_values("airspeed_kts")
    return TableThrust1D(
        Interpolator1D(
            [v * KTS_TO_FTPS for v in df["airspeed_kts"]],
            df["thrust_lbf"],
            method,
            out_of_range,
            f"{name}:T(V)",
        )
    )


@dataclass(frozen=True)
class Propulsion:
    model: ThrustModel
    n_engines: int
    idle_per_engine_lbf: float
    incidence_rad: float = 0.0

    def total(self, n_operating: int, idle: bool, v_air_ftps: float, temp_R: float) -> float:
        """Total thrust from the operating engines (failed engines give zero)."""
        if n_operating == 0:
            return 0.0
        per = self.idle_per_engine_lbf if idle else self.model.per_engine(v_air_ftps, temp_R)
        return n_operating * per
