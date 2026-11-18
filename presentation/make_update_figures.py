"""Figures for the 11/20/26 update (presentation/fig_tailwind.svg).

    python presentation/make_update_figures.py

Runs the existing 747-100 model (no code changes) at no wind and a 15 kt tailwind.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from bfl import compute_bfl, load_config

OUT = Path(__file__).resolve().parent
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#0f1d2b", "#6b7785", "#e3e8ee"
KT = 1.6878098571011957  # ft/s per kt

plt.rcParams.update({
    "font.family": ["DejaVu Sans"], "font.size": 13, "axes.titlesize": 14.5,
    "axes.titleweight": "bold", "axes.labelsize": 13, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "xtick.color": MUTED, "ytick.color": MUTED,
    "legend.frameon": False, "svg.fonttype": "path",
})


def _case(headwind_kts: float):
    r = compute_bfl(load_config("b747_100", overrides={"environment.headwind_kts": headwind_kts}))
    df = r.go.to_dataframe()
    i_v1 = df.index[df.phase == "oei_roll"][0]  # V1 = end of the recognition second
    return r, df, df.loc[i_v1]


def fig_tailwind() -> None:
    (r0, d0, v0), (r1, d1, v1) = _case(0.0), _case(-15.0)
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.6, 3.9))

    # left: airspeed, which is what V1 is defined in
    a.plot(d0.t_s, d0.V_air_kts, color=BLUE, lw=2.4, label="no wind")
    a.plot(d1.t_s, d1.V_air_kts, color=ORANGE, lw=2.4, label="15 kt tailwind")
    for v, c in ((v0, BLUE), (v1, ORANGE)):
        a.plot(v.t_s, v.V_air_kts, "o", color=c, ms=8, zorder=5)
    a.annotate(f"V1 = {r0.v1_kts:.0f} kt", (v0.t_s, v0.V_air_kts), (v0.t_s - 14, 55),
               color=BLUE, fontweight="bold", arrowprops=dict(arrowstyle="-", color=BLUE))
    a.annotate(f"V1 = {r1.v1_kts:.0f} kt", (v1.t_s, v1.V_air_kts), (v1.t_s + 2, 95),
               color=ORANGE, fontweight="bold", arrowprops=dict(arrowstyle="-", color=ORANGE))
    a.set(title="Airspeed: V1 barely changes", xlabel="time from brake release [s]",
          ylabel="airspeed [kt]", ylim=(-20, 200))
    a.legend(loc="upper left", bbox_to_anchor=(0.0, 1.0))

    # right: ground speed; the area under it is the distance travelled
    b.fill_between(d1.t_s, d1.V_ground_kts, color=ORANGE, alpha=0.30, lw=0)
    b.fill_between(d0.t_s, d0.V_ground_kts, color="#cfe0f5", lw=0)
    b.plot(d0.t_s, d0.V_ground_kts, color=BLUE, lw=2.4)
    b.plot(d1.t_s, d1.V_ground_kts, color=ORANGE, lw=2.4)
    for v, c in ((v0, BLUE), (v1, ORANGE)):
        b.plot(v.t_s, v.V_ground_kts, "o", color=c, ms=8, zorder=5)
    b.text(30, 45, f"BFL {r0.bfl_ft:,.0f} ft", color="#1f5fae", fontweight="bold", ha="center")
    b.text(56, 95, f"+{round(r1.bfl_ft) - round(r0.bfl_ft):,} ft", color="#c4541f", fontweight="bold", ha="center")
    b.annotate(f"V1 at {v1.V_ground_kts:.0f} kt\nground speed", (v1.t_s, v1.V_ground_kts),
               (v1.t_s - 31, v1.V_ground_kts + 4), color="#c4541f",
               arrowprops=dict(arrowstyle="-", color=ORANGE))
    b.set(title="Ground speed: area = runway used", xlabel="time from brake release [s]",
          ylabel="ground speed [kt]", ylim=(0, 200))
    b.set_xlim(a.get_xlim())

    fig.tight_layout()
    fig.savefig(OUT / "fig_tailwind.svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    print("wrote", OUT / "fig_tailwind.svg")
    print(f"no wind: BFL {r0.bfl_ft:.0f} V1 {r0.v1_kts:.1f} | tailwind: BFL {r1.bfl_ft:.0f} "
          f"V1 {r1.v1_kts:.1f} (ground {r1.v1_ground_kts:.1f})")


if __name__ == "__main__":
    fig_tailwind()
