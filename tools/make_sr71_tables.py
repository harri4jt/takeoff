"""Build the Lockheed SR-71A aero and thrust tables from digitized flight-manual data.

Source (public, declassified):

  [FM]  USAF Technical Order SR-71A-1, "Flight Manual, SR-71A", 1989 revision.
        Scans on the Internet Archive, item "0003756-lockheed-sr-71-03"
        (DoD release), volumes 01-03. Figure and page numbers below are the manual's.

Digitizing method: native 300 dpi scans, axes calibrated from the printed ticks and
grid lines. Thrust curves were read by pixel-column scans (labels removed by
continuity). For the lift chart the dense graph-paper grid was removed by a
morphological opening with line elements at 12-76 deg, which keeps only the
diagonal curves, then read by column scans. Reading accuracy is about +/-0.01 in CL
and +/-0.1 klb in thrust. See aircraft/sr71/README.md.

Run:  python tools/make_sr71_tables.py      (rewrites the CSVs in aircraft/sr71/)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "aircraft" / "sr71"

# ---------------------------------------------------------------------------------
# Takeoff thrust per engine, maximum afterburner, sea level, [FM] Figure 1-3 (p. 1-7).
# x axis: INDICATED airspeed [kt]; one curve per ambient temperature [deg C].
# Installed thrust (the text quotes 34,000 lb uninstalled, SL static, std day).
# ---------------------------------------------------------------------------------
IAS_KT = np.array([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150,
                   160, 170, 180, 190, 200, 210], dtype=float)
THRUST_KLB = {  # deg C -> klb at IAS_KT
    -38: [27.38, 27.58, 27.79, 28.05, 28.28, 28.53, 28.83, 29.14, 29.45, 29.78, 30.11,
          30.43, 30.73, 31.03, 31.31, 31.61, 31.92, 32.20, 32.51, 32.83, 33.12, 33.44],
    -15: [26.98, 27.18, 27.38, 27.60, 27.82, 28.05, 28.33, 28.60, 28.92, 29.24, 29.55,
          29.86, 30.16, 30.46, 30.73, 31.00, 31.28, 31.57, 31.88, 32.17, 32.45, 32.77],
    15: [25.43, 25.63, 25.80, 25.97, 26.17, 26.37, 26.61, 26.85, 27.11, 27.39, 27.62,
         27.86, 28.10, 28.33, 28.53, 28.73, 28.93, 29.12, 29.32, 29.51, 29.72, 29.92],
    32: [22.55, 22.75, 22.93, 23.13, 23.34, 23.57, 23.83, 24.11, 24.41, 24.68, 24.92,
         25.17, 25.39, 25.60, 25.76, 25.93, 26.10, 26.27, 26.42, 26.59, 26.75, 26.91],
    40: [21.35, 21.51, 21.69, 21.89, 22.10, 22.31, 22.58, 22.85, 23.16, 23.43, 23.70,
         23.93, 24.16, 24.38, 24.55, 24.73, 24.88, 25.00, 25.13, 25.27, 25.42, 25.57],
}
# Output grid: TRUE airspeed (the model's thrust lookups use TAS). The chart stops at
# about 215 KIAS; beyond 210 KIAS the last 50-kt slope is continued (flagged in README).
TAS_GRID_KT = np.arange(0.0, 270.01, 10.0)

# ---------------------------------------------------------------------------------
# Lift, [FM] Figure 6-2 "Wing lift vs angle of attack" (p. 6-5): 2 deg tilt nose,
# wind tunnel, rigid airplane, "no wing stall experienced". x axis: INDICATED angle
# of attack [deg]. Two low-speed curves: in ground effect (to 12 deg) and away from
# ground effect (to 25 deg). Points below the first readable value are a straight
# continuation of the lowest-alpha slope (the ground run sits near alpha 0).
# ---------------------------------------------------------------------------------
LIFT = {
    "ground_effect": (
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        [0.031, 0.084, 0.153, 0.224, 0.299, 0.376, 0.454, 0.533, 0.612, 0.694, 0.772,
         0.851],
    ),
    "free_air": (
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
         24, 25],
        [0.020, 0.060, 0.094, 0.135, 0.187, 0.238, 0.291, 0.346, 0.401, 0.457, 0.514,
         0.571, 0.629, 0.687, 0.747, 0.808, 0.866, 0.919, 0.967, 1.012, 1.051, 1.090,
         1.119, 1.145, 1.166],
    ),
}
ALPHA0_DEG = {"ground_effect": 0.6, "free_air": 1.0}  # zero-lift indicated alpha (chart)

# Attitude frame: the model's table alpha is the BODY pitch attitude theta. The
# attitude indicator note in [FM] Section I says the gyro horizon centres at 7 deg
# nose-up pitch, which is 5.8 deg angle of attack, so alpha_ind = theta - 1.2 deg.
THETA_MINUS_ALPHA_DEG = 1.2
THETA_GRID = {"ground_effect": np.arange(-1.0, 13.01, 1.0),
              "free_air": np.arange(-1.0, 26.01, 1.0)}

# ---------------------------------------------------------------------------------
# Drag: ESTIMATE (the manual has no low-speed drag polar).
#   CD = CD0 + CL * tan(alpha_ind - alpha0)
# A thin, sharp-edged slender delta gets almost no leading-edge suction, so the
# resultant force stays nearly normal to the wing and the drag due to lift is
# CL*tan(alpha). CD0 = 0.018 clean subsonic (typical for a slender configuration of
# this wetted area) + 0.010 landing gear (~16 ft^2 of gear drag area / 1605 ft^2).
# ---------------------------------------------------------------------------------
CD0 = 0.028


def _thrust_rows() -> list[str]:
    rows = []
    for temp_c, klb in THRUST_KLB.items():
        k = np.asarray(klb) * 1000.0
        slope = (k[-1] - k[-6]) / (IAS_KT[-1] - IAS_KT[-6])
        sqrt_sigma = np.sqrt(288.15 / (temp_c + 273.15))  # sea level pressure, this OAT
        temp_f = temp_c * 9.0 / 5.0 + 32.0
        for tas in TAS_GRID_KT:
            ias = tas * sqrt_sigma  # IAS ~ EAS at these Mach numbers
            t = np.interp(ias, IAS_KT, k) if ias <= IAS_KT[-1] else k[-1] + slope * (ias - IAS_KT[-1])
            rows.append(f"{tas:.0f},{temp_f:.1f},{t:.0f}")
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (a_pts, cl_pts) in LIFT.items():
        a_pts, cl_pts = np.asarray(a_pts, float), np.asarray(cl_pts, float)
        lo = (cl_pts[1] - cl_pts[0]) / (a_pts[1] - a_pts[0])
        lines = [
            f"# Lockheed SR-71A, low speed, {name.replace('_', ' ')}. Lift: flight manual",
            "# SR-71A-1 Figure 6-2 (wind tunnel). alpha_deg is BODY PITCH ATTITUDE",
            f"# = indicated alpha + {THETA_MINUS_ALPHA_DEG} deg. Drag is an ESTIMATE:",
            f"# CD = {CD0} + CL*tan(alpha_ind - {ALPHA0_DEG[name]}) (see README).",
            "# Generated by tools/make_sr71_tables.py - edit that file, not this one.",
            "alpha_deg,CL,CD",
        ]
        for theta in THETA_GRID[name]:
            a = theta - THETA_MINUS_ALPHA_DEG
            cl = np.interp(a, a_pts, cl_pts) if a >= a_pts[0] else cl_pts[0] + lo * (a - a_pts[0])
            cd = CD0 + cl * np.tan(np.radians(a - ALPHA0_DEG[name]))
            lines.append(f"{theta:.1f},{cl:.4f},{cd:.4f}")
        (OUT / f"aero_{name}.csv").write_text("\n".join(lines) + "\n")

    t_lines = [
        "# Lockheed SR-71A, J58, takeoff thrust PER ENGINE, maximum afterburner, sea-level",
        "# pressure altitude. Flight manual SR-71A-1 Figure 1-3 (vs indicated airspeed),",
        "# converted to TRUE airspeed for each temperature. Above ~215 KIAS the chart's",
        "# last slope is extended. Temperatures -38..40 C (-36.4..104 F).",
        "# Generated by tools/make_sr71_tables.py - edit that file, not this one.",
        "airspeed_kts,temperature_F,thrust_lbf",
        *_thrust_rows(),
    ]
    (OUT / "thrust.csv").write_text("\n".join(t_lines) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
