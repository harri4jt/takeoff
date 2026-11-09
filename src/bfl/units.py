"""Unit conversion constants and helpers (the ONLY place conversions live).

Internal system: ft - slug - s - lbf, temperature in degrees Rankine, angles in radians.
Inputs/outputs: ft, ft^2, knots, lbf, deg F, degrees.

Conversions happen only at the boundaries (config load and result reporting),
never inside the dynamics.
"""

from __future__ import annotations

import math

# --- fundamental constants -------------------------------------------------------
G0_FTPS2: float = 32.174  # standard gravity [ft/s^2]

# --- speed -----------------------------------------------------------------------
FT_PER_NMI: float = 1852.0 / 0.3048  # 6076.115... ft per nautical mile (exact definition)
KTS_TO_FTPS: float = FT_PER_NMI / 3600.0  # 1 kt = 1.68781 ft/s
FTPS_TO_KTS: float = 1.0 / KTS_TO_FTPS

# --- angles ----------------------------------------------------------------------
DEG_TO_RAD: float = math.pi / 180.0
RAD_TO_DEG: float = 180.0 / math.pi

# --- temperature -----------------------------------------------------------------
RANKINE_OFFSET: float = 459.67  # T[R] = T[F] + 459.67 (F and R differences are equal)


def kts_to_ftps(v_kts: float) -> float:
    """Knots -> ft/s."""
    return v_kts * KTS_TO_FTPS


def ftps_to_kts(v_ftps: float) -> float:
    """ft/s -> knots."""
    return v_ftps * FTPS_TO_KTS


def deg_to_rad(a_deg: float) -> float:
    """Degrees -> radians."""
    return a_deg * DEG_TO_RAD


def rad_to_deg(a_rad: float) -> float:
    """Radians -> degrees."""
    return a_rad * RAD_TO_DEG


def F_to_R(t_F: float) -> float:  # noqa: N802 (unit names are case-significant)
    """Degrees Fahrenheit -> degrees Rankine."""
    return t_F + RANKINE_OFFSET


def R_to_F(t_R: float) -> float:  # noqa: N802
    """Degrees Rankine -> degrees Fahrenheit."""
    return t_R - RANKINE_OFFSET


def weight_lbf_to_mass_slug(w_lbf: float) -> float:
    """Weight [lbf] -> mass [slug] using standard gravity (m = W / g0)."""
    return w_lbf / G0_FTPS2


# --- SI -> English helpers (for users whose CFD / wind-tunnel tables are in SI) ---
M_TO_FT: float = 1.0 / 0.3048
M2_TO_FT2: float = M_TO_FT**2
N_TO_LBF: float = 1.0 / 4.4482216152605
KG_TO_SLUG: float = 1.0 / 14.593902937206364
MPS_TO_FTPS: float = M_TO_FT
KGM3_TO_SLUGFT3: float = KG_TO_SLUG / M_TO_FT**3
PA_TO_PSF: float = N_TO_LBF / M2_TO_FT2


def m_to_ft(x_m: float) -> float:
    """Metres -> feet."""
    return x_m * M_TO_FT


def m2_to_ft2(a_m2: float) -> float:
    """Square metres -> square feet."""
    return a_m2 * M2_TO_FT2


def N_to_lbf(f_N: float) -> float:  # noqa: N802
    """Newtons -> pounds-force."""
    return f_N * N_TO_LBF


def kg_to_slug(m_kg: float) -> float:
    """Kilograms -> slugs."""
    return m_kg * KG_TO_SLUG


def mps_to_kts(v_mps: float) -> float:
    """m/s -> knots."""
    return v_mps * MPS_TO_FTPS * FTPS_TO_KTS


def C_to_F(t_C: float) -> float:  # noqa: N802
    """Degrees Celsius -> degrees Fahrenheit."""
    return t_C * 1.8 + 32.0


def K_to_R(t_K: float) -> float:  # noqa: N802
    """Kelvin -> Rankine."""
    return t_K * 1.8
