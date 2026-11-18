"""Build the Boeing 747-100 aero and thrust tables from digitized source data.

Every number below was read off a scanned chart; the source page is given with each
block. The scans are public on NASA NTRS:

  [H&N]  Hanke & Nordwall, "The Simulation of a Jumbo Jet Transport Aircraft,
         Vol. II: Modeling Data", NASA CR-114494 / Boeing D6-30643, Sept 1970.
         NTRS 19730001300.  Page numbers below are the report's own (e.g. 2.0-7).

Digitizing method: each page was rendered at its native 300 dpi, deskewed, the grid
was filtered out with a morphological opening, and the axes were calibrated from the
printed grid lines and labels. Curve values were then read either by scanning pixel
columns/rows (lift curve, drag upper branches) or from calibrated zoom crops (drag
"nose" region, gear increment, thrust lines). Reading accuracy is roughly
+/-0.01 in CL, +/-0.002 in CD (+/-0.003 near the drag minimum where three curves
overlap) and +/-0.3 klb in thrust. See aircraft/b747_100/README.md.

Run:  python tools/make_b747_tables.py      (rewrites the CSVs in aircraft/b747_100/)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "aircraft" / "b747_100"

ALPHA = np.arange(-2.0, 24.01, 1.0)  # alpha_W.R.P. [deg]; = fuselage-reference alpha + 2 deg

# ---------------------------------------------------------------------------------
# Basic lift, [H&N] p. 2.0-7 "Effect of angle of attack on basic CL" (low speed,
# no thrust effects, gear up, free air, stabilizer and elevators at 0).
# ---------------------------------------------------------------------------------
CL = {
    "flaps10": [-0.061, 0.042, 0.145, 0.246, 0.348, 0.453, 0.557, 0.661, 0.765, 0.874,
                0.975, 1.082, 1.183, 1.292, 1.393, 1.494, 1.594, 1.692, 1.766, 1.812,
                1.848, 1.868, 1.881, 1.888, 1.899, 1.906, 1.912],
    "flaps20": [0.131, 0.252, 0.376, 0.494, 0.606, 0.718, 0.832, 0.945, 1.055, 1.171,
                1.275, 1.374, 1.478, 1.574, 1.671, 1.763, 1.847, 1.919, 1.978, 2.029,
                2.066, 2.087, 2.087, 2.071, 2.059, 2.044, 2.033],
}

# ---------------------------------------------------------------------------------
# Basic drag, [H&N] p. 3.0-5 "Effect of angle of attack on basic CD" (gear up, free
# air). Values at alpha -2..20; 21..24 continue the last slope (outside the range a
# takeoff reaches, present only so the table matches the lift table's alpha grid).
# ---------------------------------------------------------------------------------
CD_BASIC = {
    "flaps10": [0.0610, 0.0555, 0.0500, 0.0455, 0.0430, 0.0425, 0.0435, 0.0476, 0.0535,
                0.0606, 0.0698, 0.0800, 0.0919, 0.1052, 0.1200, 0.1365, 0.1545, 0.1744,
                0.1922, 0.2141, 0.2360, 0.2621, 0.2917],
    "flaps20": [0.0676, 0.0610, 0.0580, 0.0573, 0.0581, 0.0607, 0.0651, 0.0717, 0.0809,
                0.0918, 0.1002, 0.1163, 0.1301, 0.1450, 0.1607, 0.1778, 0.1969, 0.2163,
                0.2357, 0.2556, 0.2798, 0.3036, 0.3292],
}

# ---------------------------------------------------------------------------------
# Landing-gear drag increment, [H&N] p. 3.0-15 "Effect of landing gear" (free air).
# (alpha, dCD) breakpoints read off the curves; linear in between.
# ---------------------------------------------------------------------------------
GEAR = {
    "flaps10": [(-5, 0.0253), (0, 0.0253), (5, 0.0250), (10, 0.0237), (15, 0.0212),
                (20, 0.0186), (24, 0.0174)],
    "flaps20": [(-5, 0.0244), (0, 0.0244), (5, 0.0237), (7.5, 0.0227), (10, 0.0205),
                (15, 0.0188), (20, 0.0170), (24, 0.0144)],
}

# ---------------------------------------------------------------------------------
# Thrust per engine, JT9D-3. [H&N] p. 12.2-3 "Installed corrected generalized net
# thrust", Fn/delta_ambient vs EPR for Mach 0..0.4, read at EPR = 1.42:
#   AFM takeoff EPR ([H&N] p. 15.0-17, Appendix A flight manual) at sea level,
#   15 C is 1.405 with air-conditioning packs on; the packs-off correction on the same
#   chart adds +0.0175 -> 1.42. Packs off matches the Boeing airport-planning charts.
# Sea level standard day only (delta = 1); the solver does not rescale this table.
# ---------------------------------------------------------------------------------
A0_KTS = 661.47  # speed of sound, sea level ISA
THRUST_MACH = [(0.0, 41_770), (0.1, 38_330), (0.2, 36_070), (0.3, 34_510), (0.4, 32_800)]


def _cd_full(name: str) -> np.ndarray:
    base = np.array(CD_BASIC[name])
    a_base = ALPHA[: len(base)]
    slope = base[-1] - base[-2]
    extra = base[-1] + slope * np.arange(1, len(ALPHA) - len(base) + 1)
    basic = np.concatenate([base, extra])
    assert len(a_base) + len(extra) == len(ALPHA)
    ga, gd = zip(*GEAR[name])
    return basic + np.interp(ALPHA, ga, gd)


def main() -> None:
    hdr = {
        "flaps10": "flaps 10",
        "flaps20": "flaps 20",
    }
    for name in ("flaps10", "flaps20"):
        cl = np.array(CL[name])
        cd = _cd_full(name)
        assert len(cl) == len(ALPHA)
        lines = [
            f"# Boeing 747-100, {hdr[name]}, gear DOWN, free air (no ground effect).",
            "# alpha = alpha_W.R.P. (wing reference plane = fuselage reference line + 2 deg).",
            "# CL: NASA CR-114494 p.2.0-7. CD: basic CD p.3.0-5 + gear increment p.3.0-15.",
            "# Generated by tools/make_b747_tables.py - edit that file, not this one.",
            "alpha_deg,CL,CD",
        ]
        lines += [f"{a:.1f},{c:.3f},{d:.4f}" for a, c, d in zip(ALPHA, cl, cd)]
        (OUT / f"aero_{name}.csv").write_text("\n".join(lines) + "\n")

    t_lines = [
        "# Boeing 747-100, JT9D-3, installed net thrust PER ENGINE at takeoff EPR 1.42",
        "# (sea level ISA, A/C packs off). NASA CR-114494 p.12.2-3 at Mach 0..0.4;",
        "# EPR from the AFM takeoff-EPR chart, p.15.0-17. TAS = Mach * 661.47 kt.",
        "# Generated by tools/make_b747_tables.py - edit that file, not this one.",
        "airspeed_kts,thrust_lbf",
    ]
    t_lines += [f"{m * A0_KTS:.1f},{t:.0f}" for m, t in THRUST_MACH]
    (OUT / "thrust.csv").write_text("\n".join(t_lines) + "\n")
    print(f"wrote aero_flaps10.csv, aero_flaps20.csv, thrust.csv to {OUT}")


if __name__ == "__main__":
    main()
