"""One case from a script: takeoff and landing for an aircraft built in the app.

    python scripts/analyze_example.py           # writes to output/analyze_example/

Build or edit the aircraft in the app's builder, save it (or download the .zip), then
point ``analyze`` at it: a name under aircraft/, any folder, its aircraft.yaml, or the zip.
"""

from __future__ import annotations

from pathlib import Path

from bfl import analyze

OUT = Path(__file__).resolve().parents[1] / "output" / "analyze_example"

# a hot day at a 5,000 ft airport, a bit lighter than maximum
a = analyze("b747_100", weight_lbf=650_000, temperature_F=95, elevation_ft=5000)

print(a.summary())
print(f"\nrunway required: {a.runway_required_ft:,.0f} ft, set by {a.governed_by}")
print(f"V1 {a.takeoff.v1_kts:.0f} kt, VR {a.takeoff.vr_kts:.0f} kt, "
      f"tires up to {a.takeoff.max_tire_speed_kts:.0f} kt")  # fmt: skip

# any output by name, and the full time histories as pandas DataFrames
s = a.scalars()
print(f"landing approach speed {s['landing_v_approach_kts']:.0f} kt")
go = a.time_histories()["go"]  # columns: t_s, x_ft, h_ft, V_air_kts, L_lbf, D_lbf, ...

# everything to disk: summary.txt, results.csv, time_history_*.csv
print(f"\nwritten to {a.save(OUT)}")
