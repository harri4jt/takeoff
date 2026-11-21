"""Trade studies from Python: a template to copy.

    python scripts/trade_study_example.py            # writes to output/trade_study/

Two studies on the Boeing 747-100:
  1. Aerodynamics: lift and drag multipliers (k_CL x k_CD), like the app's trade page.
  2. Operations: takeoff weight x outside air temperature at a 5,000 ft airport.

``trade_study`` solves every combination (in parallel) and returns a pandas DataFrame,
one row per case. Anything ``load_config(overrides=...)`` accepts can be varied.
"""

from __future__ import annotations

import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from bfl import load_config, trade_study
from bfl.trade import grid

OUT = Path(__file__).resolve().parents[1] / "output" / "trade_study"


def aero_study() -> None:
    cfg = load_config("b747_100")
    t0 = time.perf_counter()
    df = trade_study(
        cfg,
        {
            "multipliers.k_CL": np.linspace(0.8, 1.2, 9),
            "multipliers.k_CD": np.linspace(0.8, 1.2, 9),
        },
    )
    print(f"aero study: {len(df)} cases in {time.perf_counter() - t0:.1f} s")
    df.to_csv(OUT / "aero_kcl_kcd.csv", index=False)

    # the field length as a k_CL x k_CD table
    fl = grid(df, x="multipliers.k_CD", y="multipliers.k_CL", value="field_length_ft")
    print("\nrunway required [ft]  (rows: k_CL, columns: k_CD)")
    print(fl.round(-1).to_string(float_format=lambda v: f"{v:,.0f}"))

    # contour plot
    fig, ax = plt.subplots(figsize=(6.5, 5))
    cs = ax.contourf(fl.columns, fl.index, fl.values, levels=12, cmap="viridis")
    ax.contour(fl.columns, fl.index, fl.values, levels=cs.levels, colors="white",
               linewidths=0.5)  # fmt: skip
    fig.colorbar(cs, ax=ax, label="runway required [ft]")
    ax.plot(1.0, 1.0, "o", mfc="none", mec="white", ms=10)  # the baseline aircraft
    ax.set(xlabel="drag multiplier k_CD", ylabel="lift multiplier k_CL",
           title="747-100: runway required vs aero changes")  # fmt: skip
    fig.savefig(OUT / "aero_kcl_kcd.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def ops_study() -> None:
    cfg = load_config("b747_100", overrides={"environment.elevation_ft": 5000.0})
    df = trade_study(
        cfg,
        {
            "environment.temperature_F": [30, 59, 80, 100],
            "environment.weight_lbf": np.arange(550_000, 710_001, 40_000),
        },
        outputs=("field_length_ft", "v1_kts", "vr_kts", "max_tire_speed_kts", "balanced"),
    )
    df.to_csv(OUT / "ops_weight_temperature.csv", index=False)
    failed = df[df["error"] != ""]
    if len(failed):
        print(f"\n{len(failed)} case(s) did not solve, e.g.: {failed['error'].iloc[0]}")

    fl = grid(df, x="environment.weight_lbf", y="environment.temperature_F",
              value="field_length_ft")  # fmt: skip
    print("\nrunway required [ft] at 5,000 ft elevation (rows: OAT [F], columns: weight [lb])")
    print(fl.to_string(float_format=lambda v: f"{v:,.0f}"))

    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    colors = plt.cm.plasma(np.linspace(0.1, 0.8, len(fl)))  # ordered values: one ramp
    for (temp, row), c in zip(fl.iterrows(), colors, strict=True):
        ax.plot(row.index / 1000, row.values, "o-", color=c, label=f"{temp:.0f} °F")
    ax.set(xlabel="takeoff weight [klb]", ylabel="runway required [ft]",
           title="747-100 at a 5,000 ft airport")  # fmt: skip
    ax.legend(title="OAT")
    ax.grid(alpha=0.3)
    fig.savefig(OUT / "ops_weight_temperature.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    aero_study()
    ops_study()
    print(f"\nCSVs and figures written to {OUT}")


if __name__ == "__main__":  # needed: the study starts worker processes
    main()
