"""Matplotlib helpers used by the command-line scripts (not by the Dash app)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .results import BFLResult  # noqa: E402

# categorical slots in fixed order (validated reference palette): go, stop, aeo
GO, STOP, AEO = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 150,
            "font.size": 10,
            "axes.edgecolor": MUTED,
            "axes.labelcolor": INK,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "lines.linewidth": 2.0,
            "legend.frameon": False,
        }
    )


def bfl_chart(sweep: pd.DataFrame, result: BFLResult | None = None, ax=None):
    """d_go and d_stop vs V1 with the balanced point marked."""
    style()
    if ax is None:
        _, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(sweep["v1_kts"], sweep["d_go_ft"], color=GO, label="Go (continued takeoff)")
    ax.plot(sweep["v1_kts"], sweep["d_stop_ft"], color=STOP, label="Stop (rejected takeoff)")
    if result is not None:
        ax.plot([result.v1_kts], [result.bfl_ft], "o", ms=8, color=INK, zorder=5)
        ax.annotate(
            f"BFL {result.bfl_ft:,.0f} ft\nV1 {result.v1_kts:.1f} kt",
            (result.v1_kts, result.bfl_ft),
            xytext=(18, -45),
            textcoords="offset points",
            color=INK,
            arrowprops={"arrowstyle": "-", "color": MUTED},
        )
    ax.set_xlabel("V1 [KEAS]")
    ax.set_ylabel("Distance [ft]")
    ax.set_title("Balanced field length: go vs stop distance")
    ax.legend(loc="center left")
    return ax


def time_histories(result: BFLResult, path: Path) -> None:
    """2x2 panel: airspeed, height, forces (go), angles (go)."""
    style()
    go, stop, aeo = (t.to_dataframe() for t in (result.go, result.stop, result.aeo))
    fig, axs = plt.subplots(2, 2, figsize=(11, 7.5), constrained_layout=True)
    ax = axs[0, 0]
    for df, c, lab in ((go, GO, "Go (OEI)"), (stop, STOP, "Stop"), (aeo, AEO, "AEO")):
        ax.plot(df["x_ft"], df["V_air_kts"], color=c, label=lab)
    ax.set(xlabel="Distance [ft]", ylabel="Airspeed [KTAS]", title="Airspeed vs distance")
    ax.legend()
    ax = axs[0, 1]
    for df, c, lab in ((go, GO, "Go (OEI)"), (aeo, AEO, "AEO")):
        ax.plot(df["x_ft"], df["h_ft"], color=c, label=lab)
    ax.axhline(35, color=MUTED, lw=1, ls="--")
    ax.set(xlabel="Distance [ft]", ylabel="Height [ft]", title="Height vs distance")
    ax.legend()
    ax = axs[1, 0]
    for col, c, lab in (
        ("T_total_lbf", GO, "Thrust"),
        ("D_lbf", STOP, "Drag"),
        ("L_lbf", AEO, "Lift"),
        ("N_lbf", "#6250d6", "Normal force"),
    ):
        ax.plot(go["t_s"], go[col] / 1000, color=c, label=lab)
    ax.set(xlabel="Time [s]", ylabel="Force [1000 lbf]", title="Forces, go branch")
    ax.legend()
    ax = axs[1, 1]
    for col, c, lab in (
        ("theta_deg", GO, "θ pitch"),
        ("alpha_deg", STOP, "α"),
        ("gamma_deg", AEO, "γ flight path"),
    ):
        ax.plot(go["t_s"], go[col], color=c, label=lab)
    ax.set(xlabel="Time [s]", ylabel="Angle [deg]", title="Angles, go branch")
    ax.set_xlim(left=max(0.0, go["t_s"].iloc[-1] - 20))
    ax.legend()
    fig.suptitle(result.aircraft_name + ("  [SYNTHETIC]" if result.synthetic else ""))
    fig.savefig(path)
    plt.close(fig)
