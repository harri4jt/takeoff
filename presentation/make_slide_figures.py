"""Figures for the final presentation (presentation/fig_*.svg).

    python presentation/make_slide_figures.py

Every number plotted comes from the project code (scipy is not needed here).
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import yaml

import bfl.bfl as bfl_mod
from bfl import compute_bfl, load_config, sweep_v1
from bfl.dynamics import SegmentParams
from bfl.integrators import integrate
from bfl.model import build_model
from bfl.phases import airspeed_event, run_segment
from bfl.rootfind import safeguarded_secant, secant
from bfl.units import G0_FTPS2

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
BLUE, ORANGE, GREEN, RED, INK, MUTED, GRID = (
    "#2a78d6", "#eb6834", "#1baf7a", "#d7263d", "#0f1d2b", "#6b7785", "#e3e8ee",
)

plt.rcParams.update({
    "font.family": ["DejaVu Sans"],
    "font.size": 14,
    "axes.titlesize": 16,
    "axes.titleweight": "bold",
    "axes.labelsize": 14,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRID,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "legend.frameon": False,
    "svg.fonttype": "path",
    "mathtext.fontset": "dejavusans",
})


def save(fig, name: str) -> None:
    fig.savefig(OUT / name, bbox_inches="tight", transparent=True)
    plt.close(fig)
    print("wrote", OUT / name)


# ------------------------------------------------------------------------------------
cfg = load_config(ROOT / "tests" / "data" / "generic_widebody_synthetic")
captured = []
_orig = bfl_mod.safeguarded_secant


def _spy(*a, **k):
    r = _orig(*a, **k)
    captured.append(r)
    return r


bfl_mod.safeguarded_secant = _spy
res = compute_bfl(cfg)
bfl_mod.safeguarded_secant = _orig
v1_solve = captured[-1]  # the outer V1 solve (the k_VR solve comes first)
hist = res.v1_solver_history
sweep = sweep_v1(cfg.with_updates({"solver.method": "rk45"}), n=41, k_vr=res.k_VR)


# ---- slide 1: the BFL idea --------------------------------------------------------------
def fig_concept() -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.plot(sweep.v1_kts, sweep.d_go_ft, color=BLUE, lw=3)
    ax.plot(sweep.v1_kts, sweep.d_stop_ft, color=ORANGE, lw=3)
    ax.plot([res.v1_kts], [res.bfl_ft], "o", ms=12, color=RED, mec="white", mew=2, zorder=5)
    ax.annotate("balanced V1:\nboth need the same runway\n= balanced field length", (res.v1_kts, res.bfl_ft),
                xytext=(18, -95), textcoords="offset points", fontsize=13, color=RED,
                fontweight="bold", arrowprops={"arrowstyle": "-", "color": RED})
    ax.text(105, 12250, "continue (go)", color=BLUE, fontsize=14, fontweight="bold")
    ax.set_ylim(top=13200)
    ax.text(150, 5600, "reject (stop)", color=ORANGE, fontsize=14, fontweight="bold")
    ax.set_xlabel("decision speed V1  →")
    ax.set_ylabel("runway needed  →")
    ax.set_yticklabels([])
    ax.set_xticklabels([])
    save(fig, "fig_concept.svg")


# ---- slide 3: safeguarded secant ----------------------------------------------------------
def fig_secant_v1() -> None:
    x = np.array([h["v1_kts"] for h in hist])
    f = np.array([h["diff_ft"] for h in hist])
    fig, a = plt.subplots(figsize=(5.2, 4.3))
    a.axhline(0, color=INK, lw=1)
    a.plot(sweep.v1_kts, sweep.d_go_ft - sweep.d_stop_ft, color=MUTED, lw=2.5, alpha=0.5)
    for k in range(1, len(x) - 1):  # secant line through iterates k-1, k -> next iterate
        xs = [x[k - 1], x[k], x[k + 1]]
        t = np.linspace(min(xs), max(xs), 2)
        slope = (f[k] - f[k - 1]) / (x[k] - x[k - 1])
        a.plot(t, f[k] + slope * (t - x[k]), "--", color=BLUE, lw=1.2, alpha=0.8)
    a.plot(x, f, "o", color=BLUE, ms=9, mec="white", mew=1.5, zorder=5)
    offs = {0: (8, 4), 1: (-16, -20), 2: (-18, 8)}
    for k in range(3):
        a.annotate(str(k + 1), (x[k], f[k]), xytext=offs[k], textcoords="offset points",
                   fontsize=13, fontweight="bold", color=BLUE)
    a.annotate("4, 5, 6", (x[-1], 0), xytext=(-70, -40), textcoords="offset points",
               fontsize=13, fontweight="bold", color=BLUE,
               arrowprops={"arrowstyle": "-", "color": BLUE, "lw": 1})
    a.set(xlabel="V1 [kt]", ylabel="f(V1) = d_go − d_stop [ft]")
    a.set_yticklabels([])
    save(fig, "fig_secant_v1.svg")


def fig_secant_step() -> None:
    """One safeguarded step on arctan: the secant proposal leaves the bracket -> bisect."""
    x0, x1 = -1.0, 6.0
    f = math.atan
    x2 = x1 - f(x1) * (x1 - x0) / (f(x1) - f(x0))          # step 1: secant, accepted
    lo, hi = (x0, x2) if f(x2) > 0 else (x2, x1)               # new sign-change bracket
    prop = x2 - f(x2) * (x2 - x1) / (f(x2) - f(x1))           # step 2: secant proposal
    mid = 0.5 * (lo + hi)                                     # rejected -> bisection
    fig, ax = plt.subplots(figsize=(5.6, 4.3))
    xx = np.linspace(-10.5, 7, 400)
    ax.axhline(0, color=INK, lw=1)
    ax.axvspan(lo, hi, color=GREEN, alpha=0.15, lw=0)
    ax.text(0.5 * (lo + hi), -1.45, "bracket", ha="center", color="#137a55", fontsize=12,
            fontweight="bold")
    ax.plot(xx, np.arctan(xx), color=MUTED, lw=2.5, alpha=0.6)
    t = np.linspace(prop, x1, 2)
    ax.plot(t, f(x2) + (f(x2) - f(x1)) / (x2 - x1) * (t - x2), "--", color=ORANGE, lw=1.6)
    ax.plot([x0, x1, x2], [f(x0), f(x1), f(x2)], "o", color=BLUE, ms=9, mec="white", mew=1.5,
            zorder=5)
    for xv, lab, off in ((x0, "x₀ = a", (-58, -4)), (x1, "x₁", (-4, 10)), (x2, "x₂ = b", (-62, 6))):
        ax.annotate(lab, (xv, f(xv)), xytext=off, textcoords="offset points", fontsize=13,
                    color=BLUE, fontweight="bold")
    ax.plot([prop], [0], "X", color=ORANGE, ms=12, zorder=6)
    ax.annotate("secant step:\noutside bracket,\nrejected", (prop, 0), xytext=(4, -62),
                textcoords="offset points", fontsize=12, color="#b34f00")
    ax.plot([mid], [0], "D", color=GREEN, ms=10, mec="white", mew=1.5, zorder=6)
    ax.annotate("bisection:\nmidpoint used", (mid, 0), xytext=(14, -58), textcoords="offset points",
                fontsize=12, color="#137a55", arrowprops={"arrowstyle": "-", "color": GREEN})
    ax.set(xlabel="x", ylabel="arctan x", ylim=(-1.7, 1.7))
    save(fig, "fig_secant_step.svg")


def fig_secant_atan() -> None:
    x0, x1 = -1.0, 6.0
    plain = secant(math.atan, x0, x1, maxiter=6)
    safe = safeguarded_secant(math.atan, x0, x1, xtol=1e-14)
    fig, ax = plt.subplots(figsize=(5.4, 4.3))
    ax.semilogy(range(len(plain.x_history)), [abs(v) for v in plain.x_history], "o-",
                color=ORANGE, lw=2, ms=8, label="plain secant: diverges")
    e = [abs(v) for v in safe.x_history]
    e = [max(v, 1e-16) for v in e]
    ax.semilogy(range(len(e)), e, "s-", color=BLUE, lw=2, ms=7, label="safeguarded: converges")
    for i, step in enumerate(safe.steps):
        if step == "bisection":
            k = i + 2  # x_history = [x0, x1, step 1, step 2, ...]
            ax.annotate("bisection step\n(secant left the bracket)", (k, e[k]), xytext=(-75, -70),
                        textcoords="offset points", fontsize=12, color=BLUE,
                        arrowprops={"arrowstyle": "-", "color": BLUE})
    ax.set(xlabel="iterate k",
           ylabel="|x_k − root|")
    ax.legend(loc="lower left")
    save(fig, "fig_secant_atan.svg")
    return plain, safe


# ---- slide 4: RK4 ----------------------------------------------------------------------
def fig_rk4() -> None:
    def osc(t, y):
        return np.array([y[1], -4.0 * y[0]])

    dts = np.array([0.2 / 2**k for k in range(7)])
    errs = np.array([abs(integrate(osc, 0, [1.0, 0.0], 2.0, method="rk4", dt=d).y[-1, 0]
                         - math.cos(4.0)) for d in dts])
    slope = np.polyfit(np.log(dts), np.log(errs), 1)[0]
    fig, ax = plt.subplots(figsize=(5.4, 4.0))
    ax.loglog(dts, errs, "o-", color=BLUE, ms=8, lw=2.5, label=f"RK4, measured slope {slope:.2f}")
    ax.loglog(dts, errs[0] * (dts / dts[0]) ** 4, "--", color=MUTED, lw=1.5, label="slope 4")
    ax.set(xlabel="step size h", ylabel="error at t = 2 (y″ = −4y)")
    ax.legend(loc="upper left")
    save(fig, "fig_rk4_order.svg")
    return slope


def fig_ground_roll() -> float:
    CL, CD, T1, S, W, mu = 0.6, 0.06, 30000.0, 2000.0, 150000.0, 0.03
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "aero_takeoff.csv").write_text(f"alpha_deg,CL,CD\n-20,{CL},{CD}\n30,{CL},{CD}\n")
        (d / "aircraft.yaml").write_text(yaml.safe_dump({
            "name": "analytic", "synthetic": True, "geometry": {"wing_area_ft2": S},
            "weight": {"default_weight_lbf": W},
            "engines": {"n_engines": 2, "thrust_mode": "constant", "thrust_per_engine_lbf": T1,
                        "idle_thrust_per_engine_lbf": 0.0},
            "attitude": {"theta_tailstrike_deg": 12.0},
            "aero": {"configurations": {"takeoff": "aero_takeoff.csv"}},
        }))
        c = load_config(d, overrides={"environment.mu_roll": mu})
        vm = build_model(c)
    m = W / G0_FTPS2
    A = 2 * T1 - mu * m * G0_FTPS2
    B = 0.5 * vm.rho * S * (CD - mu * CL)
    p = SegmentParams(vm, "aeo_roll", 2, mu=mu)
    seg = run_segment("ground", p, 0.0, [0.0, 0.0], 500.0,
                      [airspeed_event("ground", p, 260.0, "v")], c.solver)
    v, xn = seg.sol.y[:, 1], seg.sol.y[:, 0]
    xe = m / (2 * B) * np.log(A / (A - B * v**2))
    rel = float(np.max(np.abs(xn[1:] - xe[1:]) / xe[1:]))
    kts = v / 1.6878098571011957
    fig, ax = plt.subplots(figsize=(5.4, 4.0))
    vv = np.linspace(0, 260, 200)
    ax.plot(m / (2 * B) * np.log(A / (A - B * vv**2)), vv / 1.6878098571011957, color=INK,
            lw=7, alpha=0.18, label="closed form")
    ax.plot(xn[::40], kts[::40], "o", color=BLUE, ms=5, label="RK4 simulation")
    ax.set(xlabel="distance [ft]", ylabel="speed [kt]")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.legend(loc="lower right")
    ax.text(0.03, 0.95, f"max relative error {rel:.0e}", transform=ax.transAxes, va="top",
            fontsize=13, color=BLUE, fontweight="bold")
    save(fig, "fig_ground_roll.svg")
    return rel


if __name__ == "__main__":
    fig_concept()
    fig_secant_v1()
    fig_secant_step()
    plain, safe = fig_secant_atan()
    s = fig_rk4()
    rel = fig_ground_roll()
    print("V1 steps:", v1_solve.steps, "| BFL", round(res.bfl_ft, 1), "V1", round(res.v1_kts, 2))
    print("atan plain:", [round(v, 3) for v in plain.x_history], plain.message)
    print("atan safe:", safe.steps, safe.iterations)
    print("rk4 slope", s, "ground roll rel", rel)
