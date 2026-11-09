"""ISA troposphere in English units (hand-coded).

Pressure at field elevation comes from the ISA model; density is computed from the
*actual* temperature via the ideal-gas law, rho = p_ISA(elev) / (R * T_actual).
"""

from __future__ import annotations

from dataclasses import dataclass

from .units import G0_FTPS2, F_to_R

P0_PSF: float = 2116.22  # sea-level standard pressure [lbf/ft^2]
T0_R: float = 518.67  # sea-level standard temperature [deg R]
LAPSE_R_PER_FT: float = 0.0035662  # troposphere lapse rate [deg R / ft]
R_AIR: float = 1716.49  # gas constant for air [ft lbf / (slug deg R)]
RHO0_SLUGFT3: float = P0_PSF / (R_AIR * T0_R)  # sea-level standard density (~0.0023769)
TROPOPAUSE_FT: float = 36089.0


@dataclass(frozen=True)
class AtmosphereState:
    """Ambient conditions at the runway."""

    elevation_ft: float
    pressure_psf: float
    temperature_R: float
    isa_temperature_R: float
    density_slugft3: float

    @property
    def sigma(self) -> float:
        """Density ratio rho / rho0 (used to convert TAS <-> EAS)."""
        return self.density_slugft3 / RHO0_SLUGFT3


def isa_temperature_R(elevation_ft: float) -> float:  # noqa: N802
    """ISA temperature [R] at geopotential altitude [ft] (troposphere only)."""
    _check_alt(elevation_ft)
    return T0_R - LAPSE_R_PER_FT * elevation_ft


def isa_pressure_psf(elevation_ft: float) -> float:
    """ISA pressure [lbf/ft^2] at altitude [ft]: p = p0 (T/T0)^(g0 / (L R))."""
    t = isa_temperature_R(elevation_ft)
    return P0_PSF * (t / T0_R) ** (G0_FTPS2 / (LAPSE_R_PER_FT * R_AIR))


def atmosphere(
    elevation_ft: float,
    temperature_F: float | None = None,
    isa_delta_F: float | None = None,
) -> AtmosphereState:
    """Ambient state at a field.

    Give either the actual temperature ``temperature_F`` or a deviation from ISA
    ``isa_delta_F`` (default: ISA standard day).
    """
    if temperature_F is not None and isa_delta_F is not None:
        raise ValueError("give temperature_F or isa_delta_F, not both")
    t_isa = isa_temperature_R(elevation_ft)
    if temperature_F is not None:
        t_act = F_to_R(temperature_F)
    else:
        t_act = t_isa + (isa_delta_F or 0.0)  # an F difference equals an R difference
    if t_act <= 0.0:
        raise ValueError(f"non-physical temperature {t_act} R")
    p = isa_pressure_psf(elevation_ft)
    return AtmosphereState(
        elevation_ft=elevation_ft,
        pressure_psf=p,
        temperature_R=t_act,
        isa_temperature_R=t_isa,
        density_slugft3=p / (R_AIR * t_act),
    )


def _check_alt(h_ft: float) -> None:
    if not (-2000.0 <= h_ft <= TROPOPAUSE_FT):
        raise ValueError(f"elevation {h_ft} ft outside troposphere model range")
