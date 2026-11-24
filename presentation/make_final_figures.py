"""Figures for the final presentation (final_presentation.pdf) that are not in the earlier decks.

    python presentation/make_final_figures.py

fig_unc_odds.svg: the data-uncertainty side study on the 747-100 (1 sigma: lift 4 %, drag 8 %,
thrust 3 %; 500 Latin-hypercube draws). Cached in _unc_cache.pkl.
"""

from __future__ import annotations

import pickle
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from bfl import load_config
from bfl.uncertainty import UncertaintySettings, uncertainty_study

OUT = Path(__file__).resolve().parent
CACHE = OUT / "_unc_cache.pkl"
RUNWAYS = (10_000, 10_500, 11_000)
SIGMAS = {"sigma_CL": 0.04, "sigma_CD": 0.08, "sigma_T": 0.03}  # 1 sigma per table
BLUE, GREEN, INK, MUTED, GRID = "#2a78d6", "#1f9d55", "#0f1d2b", "#6b7785", "#e3e8ee"
plt.rcParams.update({
    "font.family": ["DejaVu Sans"], "font.size": 13, "axes.labelsize": 13, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "xtick.color": MUTED, "ytick.color": MUTED,
    "legend.frameon": False, "svg.fonttype": "path",
})  # fmt: skip


def study() -> dict:
    if CACHE.exists():
        d = pickle.loads(CACHE.read_bytes())
        if d.get("sigmas") == SIGMAS:
            return d
    u = uncertainty_study(load_config("b747_100"), UncertaintySettings(n=500, seed=1, **SIGMAS))
    d = {"x": u.values("runway_required_ft"), "nominal": u.nominal["runway_required_ft"],
         "oat": u.one_at_a_time("runway_required_ft"), "sigmas": SIGMAS,
         "shares": u.sensitivity("runway_required_ft")}  # fmt: skip
    CACHE.write_bytes(pickle.dumps(d))
    return d


def fig_unc_odds(d: dict) -> None:
    x = np.sort(d["x"][np.isfinite(d["x"])])
    n, nom = len(d["x"]), d["nominal"]
    xs = np.linspace(x[0] - 200, RUNWAYS[-1] + 600, 500)
    p = np.searchsorted(x, xs, side="right") / n
    fig, ax = plt.subplots(figsize=(7.2, 4.4), constrained_layout=True)
    ax.plot(xs, 100 * p, color=GREEN, lw=3)
    ax.axvline(nom, color=MUTED, lw=1, ls=":")
    ax.text(nom - 40, 98, f"nominal {nom:,.0f}", ha="right", va="top", color=MUTED, fontsize=11)
    for r in RUNWAYS:
        pr = float(np.mean(d["x"] <= r))
        lab = ">99 %" if pr > 0.99 else f"{100 * pr:.0f} %"
        ax.vlines(r, 0, 100 * pr, color=INK, lw=1.4, ls=":")
        ax.plot([r], [100 * pr], "o", color=INK, ms=9, mec="white", mew=2)
        right = r < RUNWAYS[-1]
        ax.text(r + (70 if right else 0), 100 * pr - 6 if right else 103, f"{lab}  {r:,} ft",
                fontsize=12.5, fontweight="bold", va="top" if right else "bottom",
                ha="left" if right else "center",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85,
                      "pad": 1})  # fmt: skip
    ax.set(xlabel="runway length [ft]", ylabel="chance it is enough [%]", ylim=(0, 112))
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    fig.savefig(OUT / "fig_unc_odds.svg")
    plt.close(fig)
    p95 = float(np.quantile(d["x"], 0.95))
    print(f"nominal {nom:,.0f}, P95 {p95:,.0f} ({p95 - nom:+,.0f})")
    print(d["shares"][["factor", "per_sigma_ft", "variance_share"]].round(2).to_string())
    for r in RUNWAYS:
        print(f"  {r}: {100 * np.mean(d['x'] <= r):.1f} %")
    o = d["oat"]
    print(o[np.isclose(o["change"].abs(), 0.05)].round(0).to_string())


if __name__ == "__main__":
    fig_unc_odds(study())
