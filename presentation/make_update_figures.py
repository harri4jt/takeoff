"""Figures for the 11/20/26 update (presentation/fig_tailwind.svg, fig_b747_*.svg).

    python presentation/make_update_figures.py

Runs the existing 747-100 model (no code changes) and plots its digitized tables.
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


# Boeing D6-58326 sec. 3.3.1, 747-100 FAR takeoff field length, sea level, standard day
# (same digitized points as scripts/validate_b747.py): (weight [1000 lb], length [ft])
BOEING_SL = [
    (500, 4880), (520, 4910), (540, 5180), (560, 5520), (580, 5880), (620, 6750),
    (640, 7220), (660, 7750), (680, 8360), (690, 8720), (705, 9230),
]


def fig_b747_validation() -> None:
    w = [p[0] for p in BOEING_SL]
    runs = [compute_bfl(load_config("b747_100", overrides={"environment.weight_lbf": k * 1e3}))
            for k in w]
    far = [r.faa_field_length_ft for r in runs]
    fig, ax = plt.subplots(figsize=(7.0, 4.3))
    ax.fill_between(w, [p[1] for p in BOEING_SL], far, color=BLUE, alpha=0.10, lw=0)
    ax.plot(w, [p[1] for p in BOEING_SL], "o-", color=INK, lw=2.2, ms=6,
            label="Boeing published (airport planning doc)")
    ax.plot(w, far, "s-", color=BLUE, lw=2.4, ms=6, label="our model (FAA field length)")
    for k, b, m in zip(w, [p[1] for p in BOEING_SL], far):
        if k in (540, 620, 705):
            ax.annotate(f"{100 * (m / b - 1):+.0f}%", (k, m), (0, 10), textcoords="offset points",
                        ha="center", color=BLUE, fontweight="bold", fontsize=12)
    ax.set(xlabel="takeoff weight [1000 lb]", ylabel="runway length [ft]",
           title="747-100, flaps 20, sea level, standard day", ylim=(4400, 10600))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / "fig_b747_validation.svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    print("wrote", OUT / "fig_b747_validation.svg")
    for k, b, m in zip(w, [p[1] for p in BOEING_SL], far):
        print(f"  {k} klb  Boeing {b}  model {m:.0f}  {100 * (m / b - 1):+.1f}%")


def fig_b747_data() -> None:
    import pandas as pd

    d = OUT.parent / "aircraft" / "b747_100"
    f10 = pd.read_csv(d / "aero_flaps10.csv", comment="#")
    f20 = pd.read_csv(d / "aero_flaps20.csv", comment="#")
    th = pd.read_csv(d / "thrust.csv", comment="#")
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(11.0, 3.2))
    for df, col, lab in ((f10, ORANGE, "flaps 10"), (f20, BLUE, "flaps 20")):
        a.plot(df.alpha_deg, df.CL, "o-", color=col, ms=3.5, lw=1.8, label=lab)
        b.plot(df.alpha_deg, df.CD, "o-", color=col, ms=3.5, lw=1.8, label=lab)
    a.set(title="Lift coefficient", xlabel="α [deg]", ylabel="C$_L$")
    b.set(title="Drag coefficient (incl. gear)", xlabel="α [deg]", ylabel="C$_D$")
    a.legend(loc="lower right")
    c.plot(th.airspeed_kts, th.thrust_lbf / 1e3, "o-", color=INK, ms=5, lw=1.8)
    c.set(title="Thrust per engine", xlabel="true airspeed [kt]", ylabel="thrust [1000 lb]",
          ylim=(30, 44))
    fig.tight_layout()
    fig.savefig(OUT / "fig_b747_data.svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    print("wrote", OUT / "fig_b747_data.svg")


def fig_gust_shape() -> None:
    import numpy as np

    tg, Tg, Ug = 2.0, 6.0, -10.0  # sketch values: start [s], duration [s], size [kt]
    t = np.linspace(0, 10, 400)
    s = (t >= tg) & (t <= tg + Tg)
    u = np.where(s, 0.5 * Ug * (1 - np.cos(2 * np.pi * (t - tg) / Tg)), 0.0)
    fig, ax = plt.subplots(figsize=(4.4, 2.3))
    ax.axhline(0, color=MUTED, lw=1)
    ax.plot(t, u, color=ORANGE, lw=2.8)
    ax.annotate("", (tg + Tg / 2, Ug), (tg + Tg / 2, 0),
                arrowprops=dict(arrowstyle="<->", color=INK, lw=1.3))
    ax.text(tg + Tg / 2 + 0.25, Ug / 2, "U$_g$", fontsize=13, va="center")
    ax.annotate("", (tg, 1.6), (tg + Tg, 1.6), arrowprops=dict(arrowstyle="<->", color=INK, lw=1.3))
    ax.text(tg + Tg / 2, 2.4, "T$_g$", fontsize=13, ha="center")
    ax.plot([tg], [0], "o", color=INK, ms=5)
    ax.text(tg - 0.15, -1.2, "t$_g$", fontsize=13, ha="right")
    ax.text(9.9, -8.6, "tailwind\ngust", fontsize=11.5, color="#c4541f", ha="right")
    ax.set(xlim=(0, 10), ylim=(-11.5, 4.5), xlabel="time t", ylabel="u$_w$")
    ax.set_xticks([]), ax.set_yticks([])
    ax.grid(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_gust_shape.svg", bbox_inches="tight", transparent=True)
    plt.close(fig)
    print("wrote", OUT / "fig_gust_shape.svg")


if __name__ == "__main__":
    fig_tailwind()
    fig_b747_validation()
    fig_b747_data()
    fig_gust_shape()
