"""Figures for the 11/25/26 gust decks: gust_slides.html (261125_update.pdf, the full
story) and gust_plan_slides.html (261125a_update.pdf, two slides): presentation/fig_gu_*.svg.

    python presentation/make_gust_figures.py

Uses the bfl gust analysis. The gust studies take a few minutes; their results are cached
in presentation/_gust_cache.pkl, the time-step study (presentation/_make_conv.py) in
_gust_conv.pkl (delete to re-run).
"""

from __future__ import annotations

import math
import pickle
from pathlib import Path
from statistics import NormalDist

import matplotlib.pyplot as plt
import numpy as np

from bfl import load_config
from bfl.gusts import GustSettings, dryden, gust_signal, gust_study, quantile_ci, span_average

OUT = Path(__file__).resolve().parent
CACHE = OUT / "_gust_cache.pkl"
BLUE, ORANGE, GREEN, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1f9d55", "#0f1d2b", "#6b7785", "#e3e8ee"
RAMP = {"light": "#8fbbe8", "moderate": "#2a78d6", "severe": "#123f78"}  # one hue, light -> dark
KT = 1.6878098571011957  # ft/s per kt
ND = NormalDist()

plt.rcParams.update({
    "font.family": ["DejaVu Sans"], "font.size": 13, "axes.titlesize": 14.5,
    "axes.titleweight": "bold", "axes.labelsize": 13, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "xtick.color": MUTED, "ytick.color": MUTED,
    "legend.frameon": False, "svg.fonttype": "path",
})  # fmt: skip


def studies() -> dict:
    """All gust studies the slides use (seed 1), cached."""
    if CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    data: dict = {}
    for ac in ("b747_100", "sr71"):
        for inten in ("light", "moderate", "severe"):
            g = gust_study(load_config(ac), GustSettings(intensity=inten, n=1000, seed=1))
            data[(ac, inten)] = {"samples": g.samples, "calm": g.calm, "traces": g.traces,
                                 "table": g.percentiles()}  # fmt: skip
            print(ac, inten, f"{g.time_s:.0f} s")
    g = gust_study(load_config("b747_100"),
                   GustSettings(intensity="moderate", n=4000, seed=2, landing=False))  # fmt: skip
    data["pool"] = {"samples": g.samples, "calm": g.calm}
    print("pool", f"{g.time_s:.0f} s")
    CACHE.write_bytes(pickle.dumps(data))
    return data


def _ok(s):
    return s[s["error"] == ""]


# ------------------------------------------------------------------------------------
# slide 2: the answer
# ------------------------------------------------------------------------------------
def fig_margin(data: dict) -> None:
    fig, ax = plt.subplots(figsize=(7.4, 5.2), constrained_layout=True)
    ps = np.linspace(0.5, 0.995, 80)
    z = [ND.inv_cdf(p) for p in ps]
    for inten, c in RAMP.items():
        d = data[("b747_100", inten)]
        x = _ok(d["samples"])["takeoff_field_ft"].to_numpy()
        calm = d["calm"]["takeoff_field_ft"]
        q = np.array([quantile_ci(x, p) for p in ps]) - calm
        ax.fill_between(z, q[:, 1], q[:, 2], color=c, alpha=0.15, lw=0)
        ax.plot(z, q[:, 0], color=c, lw=2.6, label=inten)
        e95 = quantile_ci(x, 0.95)[0] - calm
        ax.plot(ND.inv_cdf(0.95), e95, "o", ms=8, mfc="white", mec=c, mew=2)
        ax.annotate(f"+{e95:,.0f} ft", (ND.inv_cdf(0.95), e95), (10, -14),
                    textcoords="offset points", ha="left", color=c, fontweight="bold")  # fmt: skip
    ticks = (0.5, 0.8, 0.9, 0.95, 0.99)
    ax.set_xticks([ND.inv_cdf(p) for p in ticks], [f"{100 * p:g} %" for p in ticks])
    ax.axhline(0, color=MUTED, lw=1, ls=":")
    ax.set(xlabel="share of gusty-day takeoffs covered", ylabel="extra runway over calm [ft]")
    ax.legend(title="turbulence", loc="upper left")
    fig.savefig(OUT / "fig_gu_margin.svg")
    plt.close(fig)


def table(data: dict) -> None:
    print("\nP95 / P99 extra over calm (takeoff field length; landing runway)")
    for ac in ("b747_100", "sr71"):
        for inten in RAMP:
            d = data[(ac, inten)]
            t = d["table"].set_index("output")
            to, ld = t.loc["takeoff_field_ft"], t.loc["landing_runway_ft"]
            print(f"  {ac:9s} {inten:9s} calm {to['calm']:7,.0f}  P95 {to['p95_margin']:+6,.0f} "
                  f"({100 * to['p95_margin'] / to['calm']:+.1f} %)  P99 {to['p99_margin']:+6,.0f} "
                  f"({100 * to['p99_margin'] / to['calm']:+.1f} %)   landing P95 "
                  f"{ld['p95_margin']:+.0f} ({100 * ld['p95_margin'] / ld['calm']:+.1f} %)")  # fmt: skip


# ------------------------------------------------------------------------------------
# slide 3: random kicks -> a gust curve
# ------------------------------------------------------------------------------------
def fig_ou() -> None:
    rng = np.random.default_rng(4)
    dt, t_end, sigma = 0.01, 8.0, 5.8  # moderate: horizontal gust spread near 20 ft [kt]
    n = int(t_end / dt)
    z = rng.standard_normal(n)
    t = np.arange(n + 1) * dt
    fig, (a, b) = plt.subplots(2, 1, figsize=(7.6, 5.0), sharex=True, constrained_layout=True,
                               gridspec_kw={"height_ratios": [1, 2.2]})  # fmt: skip
    a.plot(t[1:], z, ".", ms=2.5, color=MUTED)
    a.set(ylabel="Z")
    a.text(0.0, 1.04, "① one random number Z per 0.01 s step", transform=a.transAxes,
           fontweight="bold", fontsize=12.5)
    a.set_ylim(-4, 4)
    for tc, c, lab in ((0.5, ORANGE, "T = 0.5 s (fast: 150 kt through 140-ft gusts)"),
                       (2.0, BLUE, "T = 2 s (slow: 40 kt through 140-ft gusts)")):  # fmt: skip
        g = np.zeros(n + 1)
        for k in range(n):  # the update rule on the slide, nothing else
            g[k + 1] = g[k] - g[k] / tc * dt + sigma * math.sqrt(2 / tc) * math.sqrt(dt) * z[k]
        b.plot(t, g, color=c, lw=1.8, label=lab)
    b.axhspan(-sigma, sigma, color=GRID, alpha=0.6, lw=0)
    b.text(t_end, sigma, "  ±σ = 5.8 kt", va="center", color=MUTED, fontsize=11)
    b.set(xlabel="time [s]", ylabel="gust [kt]")
    b.text(0.0, 1.02, "② the same numbers through the update rule, two memories T",
           transform=b.transAxes, fontweight="bold", fontsize=12.5)
    b.legend(loc="lower right", fontsize=10.5)
    fig.savefig(OUT / "fig_gu_ou.svg")
    plt.close(fig)


# ------------------------------------------------------------------------------------
# slide 4: what the Dryden model provides
# ------------------------------------------------------------------------------------
def fig_dryden() -> None:
    w20 = 30.0  # moderate
    h = np.linspace(10, 300, 300)
    base = 0.177 + 0.000823 * h
    sw = 0.1 * w20 * np.ones_like(h)
    su = sw / base**0.4
    lw, lu = h, h / base**1.2
    fig = plt.figure(figsize=(7.4, 5.0), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.05, 1])
    a, b, c = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])
    a.plot(su, h, color=BLUE, lw=2.4, label="σ_u (along the runway)")
    a.plot(sw, h, color=ORANGE, lw=2.4, label="σ_w (vertical)")
    a.set(xlabel="gust spread σ [kt]", ylabel="height h [ft]", xlim=(0, 7))
    a.legend(fontsize=10.5, loc="upper left")
    b.plot(lu, h, color=BLUE, lw=2.4, label="L_u")
    b.plot(lw, h, color=ORANGE, lw=2.4, label="L_w = h")
    b.set(xlabel="gust length L [ft]", xlim=(0, 1500))
    b.legend(fontsize=10.5, loc="lower right")
    for ax in (a, b):
        for hh, lab in ((10, "wheels (held at 10 ft)"), (50, "50 ft")):
            ax.axhline(hh, color=MUTED, lw=0.8, ls=":")
        ax.set_ylim(0, 300)
    a.text(0.0, 1.03, "① spread vs height (moderate)", transform=a.transAxes, fontweight="bold",
           fontsize=12)  # fmt: skip
    b.text(0.0, 1.03, "② length vs height", transform=b.transAxes, fontweight="bold",
           fontsize=12)  # fmt: skip
    # spectra at 20 ft, per unit variance, against spatial frequency
    L_u, L_w = 20 / (0.177 + 0.000823 * 20) ** 1.2, 20.0
    om = np.logspace(-4, 0.5, 300)  # rad/ft
    ou = lambda L: (2 * L / np.pi) / (1 + (L * om) ** 2)  # noqa: E731
    dry_w = (L_w / np.pi) * (1 + 3 * (L_w * om) ** 2) / (1 + (L_w * om) ** 2) ** 2
    c.loglog(om, ou(L_u), color=BLUE, lw=2.4, label="horizontal: Dryden = ours")
    c.loglog(om, dry_w, color=ORANGE, lw=2.4, label="vertical: Dryden")
    c.loglog(om, ou(L_w), color=ORANGE, lw=1.8, ls="--", label="vertical: ours (L = h)")
    c.set(xlabel="spatial frequency Ω [rad/ft]", ylabel="spectrum / σ² [ft]")
    c.legend(fontsize=10.5, loc="lower left")
    c.text(0.0, 1.03, "③ how gust energy is spread (20 ft)", transform=c.transAxes,
           fontweight="bold", fontsize=12)  # fmt: skip
    fig.savefig(OUT / "fig_gu_dryden.svg")
    plt.close(fig)
    for hh in (10, 20, 50):
        bb = 0.177 + 0.000823 * hh
        print(f"  h {hh}: sigma_u {3.0 / bb**0.4:.2f} kt, sigma_w 3.00 kt, L_u {hh / bb**1.2:.0f} ft, "
              f"L_w {hh} ft")  # fmt: skip


def fig_dryden_simple() -> None:
    """Plan deck: strength and length against height, moderate turbulence, 0-1,000 ft."""
    h = np.linspace(10, 1000, 400)
    base = 0.177 + 0.000823 * h
    sw = 3.0 * np.ones_like(h)
    su, lu = sw / base**0.4, h / base**1.2
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.0, 4.9), sharey=True, constrained_layout=True)
    a.plot(su, h, color=BLUE, lw=2.6, label="along the runway, σ$_u$")
    a.plot(sw, h, color=ORANGE, lw=2.6, label="vertical, σ$_w$")
    a.set(xlabel="strength σ [kt]", ylabel="height above ground h [ft]", xlim=(0, 7.5))
    a.set_title("how strong", loc="left")
    b.plot(lu, h, color=BLUE, lw=2.6, label="L$_u$")
    b.plot(h, h, color=ORANGE, lw=2.6, label="L$_w$ = h")
    b.set(xlabel="length L [ft]", xlim=(0, 1100))
    b.set_title("how big", loc="left")
    for ax in (a, b):
        ax.axhspan(0, 100, color=MUTED, alpha=0.10, lw=0)
        ax.axhspan(0, 50, color=ORANGE, alpha=0.10, lw=0)
        ax.set_ylim(0, 1000)
    a.text(0.2, 108, "below ~100 ft: extrapolated", fontsize=10.5, color=MUTED, va="bottom")
    b.text(1080, 8, "takeoff & landing: 0–50 ft", fontsize=10.5, color=INK, va="bottom", ha="right")
    a.legend(fontsize=11, loc="upper right", frameon=True, framealpha=0.95, edgecolor="none")
    b.legend(fontsize=11, loc="upper left")
    fig.savefig(OUT / "fig_gu_dryden_simple.svg")
    plt.close(fig)


# ------------------------------------------------------------------------------------
# slide 4: the update rule, piece by piece
# ------------------------------------------------------------------------------------
def fig_decay() -> None:
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.6, 4.0), constrained_layout=True)
    dt, g0 = 0.1, 10.0
    tt = np.linspace(0, 6, 400)
    for tc, c in ((0.5, ORANGE), (2.0, BLUE)):
        a.plot(tt, g0 * np.exp(-tt / tc), color=c, lw=2.4, label=f"T = {tc:g} s:  g₀·e$^{{-t/T}}$")
        n = int(6 / dt)
        g = [g0]
        for _ in range(n):  # the rule without the kick, coarse steps to make them visible
            g.append(g[-1] - g[-1] / tc * dt)
        a.plot(np.arange(n + 1) * dt, g, "o", ms=3.5, color=c, alpha=0.7)
    a.axhline(g0 * math.exp(-1), color=MUTED, lw=1, ls=":")
    a.text(6, g0 * math.exp(-1) + 0.25, "37 % left after one T", ha="right", color=MUTED, fontsize=11)
    a.set(xlabel="time after the kick [s]", ylabel="gust [kt]", xlim=(-0.2, 6))
    a.text(0, 1.03, "① one kick of +10 kt, no more kicks: it fades exponentially", transform=a.transAxes,
           fontweight="bold", fontsize=12.5)  # fmt: skip
    a.legend(loc="upper right", fontsize=11.5)
    a.text(1.6, 6.5, "dots: the rule step by step (Δt = 0.1 s)", color=MUTED, fontsize=10.5)

    rng = np.random.default_rng(3)
    tc = 1.0
    times = np.array([0.4, 1.3, 1.9, 3.1, 3.6, 4.8])
    sizes = rng.normal(0, 4.5, len(times))
    tt = np.linspace(0, 6.5, 700)
    total = np.zeros_like(tt)
    for t0, k in zip(times, sizes, strict=True):
        part = np.where(tt >= t0, k * np.exp(-(tt - t0) / tc), 0.0)
        total += part
        b.plot(tt, part, color="#b8c4d1", lw=1.3)
    b.plot(tt, total, color=INK, lw=2.6, label="the gust = sum of the fading kicks")
    for t0, k in zip(times, sizes, strict=True):  # each kick: an arrow from before to after
        before = float(np.sum([kk * math.exp(-(t0 - tk) / tc) for tk, kk in
                               zip(times, sizes, strict=True) if tk < t0]))  # fmt: skip
        b.annotate("", (t0, before + k), (t0, before),
                   arrowprops={"arrowstyle": "-|>", "color": ORANGE, "lw": 2.2})  # fmt: skip
    b.plot([], [], color=ORANGE, lw=2.2, label="kicks (random size and sign)")
    b.plot([], [], color="#b8c4d1", lw=1.3, label="each kick fading on its own")
    b.axhline(0, color=MUTED, lw=1)
    b.set(xlabel="time [s]", ylabel="gust [kt]")
    b.text(0, 1.03, "② several kicks (T = 1 s) add up", transform=b.transAxes,
           fontweight="bold", fontsize=12.5)  # fmt: skip
    b.legend(loc="lower right", fontsize=10.5)
    fig.savefig(OUT / "fig_gu_decay.svg")
    plt.close(fig)


# ------------------------------------------------------------------------------------
# slide 4: one gusty takeoff, fixed schedule, lagged reading
# ------------------------------------------------------------------------------------
def fig_run(data: dict) -> None:
    from bfl import compute_bfl

    r = compute_bfl(load_config("b747_100"))
    tr = data[("b747_100", "moderate")]["traces"][0]["go"]
    t, va, vi = tr["t_s"].to_numpy(), tr["V_air_kts"].to_numpy(), tr["V_ind_kts"].to_numpy()
    sel = (t > 28) & (t < 52)
    fig, ax = plt.subplots(figsize=(7.6, 5.0), constrained_layout=True)
    ax.plot(t[sel], va[sel], color="#a9b3be", lw=1.1, label="true airspeed (every gust)")
    ax.plot(t[sel], vi[sel], color=INK, lw=2.4, label="what the crew acts on (gust part lagged 1 s)")
    for v, lab, c in ((r.v_ef_kts, "engine fails (V_EF)", ORANGE), (r.vr_kts, "rotate (VR)", BLUE)):
        ax.axhline(v, color=c, lw=1.2, ls="--")
        ax.text(28.3, v + 0.6, f"{lab} {v:.0f} kt", color=c, fontsize=11, va="bottom")
        hit_i = np.argmax(vi[sel] >= v)
        ax.plot(t[sel][hit_i], v, "o", ms=8, color=c)
    i_spike = np.argmax((va >= r.vr_kts) & (t > 30))
    if va[i_spike] >= r.vr_kts and t[i_spike] < t[sel][np.argmax(vi[sel] >= r.vr_kts)] - 1:
        ax.annotate(f"gust spike touches VR at {t[i_spike]:.0f} s:\nthe crew does not rotate yet",
                    (t[i_spike], va[i_spike]), (-150, 10), textcoords="offset points",
                    fontsize=11, color=MUTED, arrowprops={"arrowstyle": "->", "color": MUTED})
    ax.set(xlabel="time since brake release [s]", ylabel="airspeed [kt]")
    ax.legend(loc="lower right", fontsize=11)
    fig.savefig(OUT / "fig_gu_run.svg")
    plt.close(fig)


# ------------------------------------------------------------------------------------
# slide 5: gust size, and the wing averaging small gusts out
# ------------------------------------------------------------------------------------
def _field(rng, length_ft: float, x: np.ndarray, sigma: float) -> np.ndarray:
    """A frozen 1-D gust pattern in space (OU in x): correlation length L."""
    g = np.zeros_like(x)
    dx = x[1] - x[0]
    a = math.exp(-dx / length_ft)
    g[0] = sigma * rng.standard_normal()
    for k in range(1, len(x)):
        g[k] = a * g[k - 1] + sigma * math.sqrt(1 - a * a) * rng.standard_normal()
    return g


def fig_wing() -> None:
    span, sigma = 196.0, 3.0  # 747 wing, moderate vertical gust spread [kt]
    x = np.linspace(-40, span + 40, 1400)
    on = (x >= 0) & (x <= span)
    for seed in range(200):  # an illustrative pair: big swings that cancel vs a coherent push
        rng = np.random.default_rng(seed)
        small, large = _field(rng, 10.0, x, sigma), _field(rng, 300.0, x, sigma)
        if abs(small[on].mean()) < 0.4 and abs(large[on].mean()) > 2.2:
            break
    fields = {10.0: small, 300.0: large}
    fig, axs = plt.subplots(2, 1, figsize=(7.6, 4.6), sharex=True, constrained_layout=True)
    for ax, L, title in ((axs[0], 10.0, "small gusts (10 ft, near the ground): they cancel out"),
                         (axs[1], 300.0, "large gusts (300 ft): the whole wing feels them")):  # fmt: skip
        g = fields[L]
        avg = g[on].mean()
        ax.plot(x, g, color=BLUE, lw=1.4)
        ax.axvspan(0, span, color=GRID, alpha=0.55, lw=0)
        ax.hlines(avg, 0, span, color=ORANGE, lw=3)
        ax.text(0.99, 0.95, f"wing feels {avg:+.1f} kt", transform=ax.transAxes, ha="right",
                va="top", color=ORANGE, fontsize=12, fontweight="bold",
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9})  # fmt: skip
        ax.text(0.0, 1.03, title, transform=ax.transAxes, fontweight="bold", fontsize=12.5)
        ax.set(ylabel="vertical gust [kt]")
        ax.set_ylim(-3.2 * sigma, 3.2 * sigma)
    axs[1].set_xlabel("position along the wingspan [ft] (shaded: the 196-ft 747 wing)")
    fig.savefig(OUT / "fig_gu_wing.svg")
    plt.close(fig)
    for h in (10, 50):
        su, sw, lu, lw = dryden(h, 30.0)
        s2, l2 = span_average(sw, lw, span)
        print(f"  h {h} ft: sigma_w {sw / KT:.1f} kt (L {lw:.0f} ft) -> wing-averaged "
              f"{s2 / KT:.1f} kt (L {l2:.0f} ft); sigma_u {su / KT:.1f} kt, L_u {lu:.0f} ft")  # fmt: skip


# ------------------------------------------------------------------------------------
# slide 6: sampling error
# ------------------------------------------------------------------------------------
def fig_sampling(data: dict) -> None:
    pool = _ok(data["pool"]["samples"])["takeoff_field_ft"].to_numpy()
    calm = data["pool"]["calm"]["takeoff_field_ft"]
    x500 = np.sort(pool[:500] - calm)
    est, lo, hi = quantile_ci(x500, 0.95)
    fig, (a, b) = plt.subplots(1, 2, figsize=(11.6, 4.3), constrained_layout=True,
                               gridspec_kw={"width_ratios": [1.15, 1]})  # fmt: skip
    a.hist(x500, bins=40, color=BLUE, alpha=0.75)
    a.axvspan(lo, hi, color=ORANGE, alpha=0.18, lw=0)
    a.axvline(est, color=ORANGE, lw=2.4)
    a.text(est, a.get_ylim()[1] * 0.92, f"  P95 = 475th of 500\n  {est:+,.0f} ft", color=ORANGE,
           fontweight="bold", va="top")  # fmt: skip
    a.text(hi, a.get_ylim()[1] * 0.55, f"  465th–485th:\n  {lo:+,.0f} … {hi:+,.0f} ft",
           color=ORANGE, va="top", fontsize=11)  # fmt: skip
    a.set(xlabel="takeoff field length − calm [ft]", ylabel="runs")
    a.text(0.0, 1.03, "① one study: 500 runs", transform=a.transAxes, fontweight="bold")
    rng = np.random.default_rng(0)
    sizes = (125, 500, 2000)
    spreads = []
    for i, n in enumerate(sizes):
        p95 = np.array([np.quantile(rng.choice(pool, n), 0.95) for _ in range(400)]) - calm
        spreads.append(np.std(p95))
        parts = b.violinplot(p95, positions=[i], widths=0.8, showextrema=False)
        for pc in parts["bodies"]:
            pc.set_facecolor(BLUE)
            pc.set_alpha(0.45)
        b.text(i, np.percentile(p95, 99.5) + 8, f"±{1.96 * np.std(p95):.0f} ft", ha="center",
               color=INK, fontweight="bold")  # fmt: skip
    b.set_xticks(range(3), [f"{n:,} runs" for n in sizes])
    b.set(ylabel="P95 estimate − calm [ft]")
    b.text(0.0, 1.03, "② repeat it 400 times: how much the P95 moves", transform=b.transAxes,
           fontweight="bold")
    fig.savefig(OUT / "fig_gu_sampling.svg")
    plt.close(fig)
    print(f"  500 runs: P95 {est:+.0f}, interval {lo:+.0f}..{hi:+.0f}; "
          f"repeat spread (95 %): " + ", ".join(f"{n}: ±{1.96 * s:.0f}" for n, s in
                                                  zip(sizes, spreads, strict=True)))  # fmt: skip


# ------------------------------------------------------------------------------------
# 11/25 decks (gust_slides.html, gust_plan_slides.html): one reference case throughout
#   moderate turbulence (W20 = 30 kt), h = 20 ft, horizontal gust:
#   sigma = 5.8 kt, L = 144 ft;  T = L / V = 0.57 s at 150 kt, 2.1 s at 40 kt
# ------------------------------------------------------------------------------------
H_REF, W20_REF = 20.0, 30.0


def _ref() -> tuple[float, float]:
    su, _, lu, _ = dryden(H_REF, W20_REF)
    return su / KT, lu  # kt, ft


def _ou(z: np.ndarray, sigma: float, tc: float, dt: float, g0: float = 0.0, pull: bool = True,
        kick: bool = True) -> np.ndarray:  # fmt: skip
    """The Euler-Maruyama update rule, term by term (as on the slides)."""
    g = np.empty(len(z) + 1)
    g[0] = g0
    for k in range(len(z)):
        g[k + 1] = (g[k] - (g[k] / tc * dt if pull else 0.0)
                    + (sigma * math.sqrt(2 / tc) * math.sqrt(dt) * z[k] if kick else 0.0)
                    )  # fmt: skip
    return g


def fig_days(data: dict) -> None:
    """Three gusty takeoffs: the along-runway gust each one flew through."""
    tr = data[("b747_100", "moderate")]["traces"]
    fig, axs = plt.subplots(3, 1, figsize=(7.2, 5.6), sharex=True, sharey=True,
                            constrained_layout=True)  # fmt: skip
    for i, ax in enumerate(axs):
        df = tr[i]["go"]
        ax.plot(df["t_s"], df["u_g_kts"], color=BLUE, lw=1.0)
        ax.axhline(0, color=MUTED, lw=0.8)
        ax.text(0.01, 0.92, f"takeoff {i + 1}", transform=ax.transAxes, fontsize=12,
                fontweight="bold", va="top")  # fmt: skip
        ax.set_ylim(-16, 16)
        ax.set_yticks([-10, 0, 10])
    axs[1].set_ylabel("gust along the runway [kt]")
    axs[-1].set_xlabel("time since brake release [s]")
    fig.savefig(OUT / "fig_gu_days.svg")
    plt.close(fig)


def fig_frozen() -> None:
    """Flying through a frozen gust pattern: the same pattern, two speeds, two memories."""
    sigma, L = _ref()
    rng = np.random.default_rng(12)
    x = np.linspace(0, 1100, 4401)
    g = _field(rng, L, x, sigma)
    t_win = 4.0
    fig, axs = plt.subplots(3, 1, figsize=(7.6, 5.6), constrained_layout=True,
                            gridspec_kw={"height_ratios": [1.2, 1, 1]})  # fmt: skip
    a = axs[0]
    a.plot(x, g, color=INK, lw=1.2)
    a.set(xlabel="distance along the runway [ft]", ylabel="gust [kt]", xlim=(0, 1100))
    a.set_ylim(-4.2 * sigma, 3.4 * sigma)
    a.annotate("", (300 + L, 2.6 * sigma), (300, 2.6 * sigma),
               arrowprops={"arrowstyle": "<->", "color": INK, "lw": 1.5})  # fmt: skip
    a.text(300 + L / 2, 2.75 * sigma, f"L = {L:.0f} ft", ha="center", va="bottom", fontsize=11.5)
    a.set_title("① the air: a gust pattern frozen in space", loc="left", fontsize=12.5)
    for i, (kts, c) in enumerate(((150.0, ORANGE), (40.0, BLUE))):
        v = kts * KT
        a.hlines(-3.0 * sigma - 0.75 * sigma * i, 0, v * t_win, color=c, lw=5)
        a.text(v * t_win + 15, -3.0 * sigma - 0.75 * sigma * i, f"{kts:.0f} kt covers this in "
               f"{t_win:.0f} s", color=c, va="center", fontsize=11)  # fmt: skip
        ax = axs[1 + i]
        t = np.linspace(0, t_win, 1600)
        ax.plot(t, np.interp(v * t, x, g), color=c, lw=1.6)
        ax.set(ylabel="gust felt [kt]", xlim=(0, t_win))
        ax.set_ylim(-3.2 * sigma, 3.2 * sigma)
        ax.annotate("", (0.4 + L / v, 2.3 * sigma), (0.4, 2.3 * sigma),
                    arrowprops={"arrowstyle": "<->", "color": c, "lw": 1.5})  # fmt: skip
        ax.text(0.4 + L / v + 0.06, 2.3 * sigma, f"T = L / V = {L / v:.2f} s", color=c,
                va="center", fontsize=11.5, fontweight="bold")  # fmt: skip
        ax.set_title(f"{'②' if i == 0 else '③'} felt at {kts:.0f} kt", loc="left", fontsize=12.5)
    axs[2].set_xlabel("time [s]")
    fig.savefig(OUT / "fig_gu_frozen.svg")
    plt.close(fig)


def fig_build() -> None:
    """Why the equation has both terms: pull only, kicks only, both."""
    sigma, L = _ref()
    tc = L / (40 * KT)  # the slow case: 2.1 s
    dt, t_end = 0.01, 30.0
    z = np.random.default_rng(13).standard_normal(int(t_end / dt))  # a typical-looking path
    t = np.arange(len(z) + 1) * dt
    cases = (
        ("pull only", r"$g_{n+1} = g_n - \frac{g_n}{T}\,\Delta t$",
         _ou(z, sigma, tc, dt, 14.0, kick=False),
         "fades like $e^{-t/T}$,\nthen nothing"),
        ("kicks only", r"$g_{n+1} = g_n + c\,\sqrt{\Delta t}\,Z_n$",
         _ou(z, sigma, tc, dt, 0.0, pull=False),
         "wanders off:\nnever settles"),
        ("both", r"$g_{n+1} = g_n - \frac{g_n}{T}\Delta t + c\sqrt{\Delta t}\,Z_n$",
         _ou(z, sigma, tc, dt, 0.0), "stays about $\\pm\\sigma$,\nchanges over ~T"),
    )  # fmt: skip
    fig, axs = plt.subplots(1, 3, figsize=(12.2, 4.3), sharey=True, constrained_layout=True)
    for ax, (name, eq, g, note), c in zip(axs, cases, (BLUE, MUTED, GREEN), strict=True):
        ax.axhspan(-sigma, sigma, color=GRID, alpha=0.9, lw=0)
        ax.plot(t, g, color=c if name != "kicks only" else INK, lw=1.6)
        ax.set_title(name, loc="left", fontsize=14)
        ax.text(0.03, 0.97, eq, transform=ax.transAxes, va="top", fontsize=12.5,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9})  # fmt: skip
        ax.text(0.97, 0.05, note, transform=ax.transAxes, ha="right", va="bottom", fontsize=12,
                color=INK,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.9})  # fmt: skip
        ax.set_xlabel("time [s]")
        ax.set_ylim(-30, 30)
    axs[0].set_ylabel("gust [kt]")
    axs[0].text(t_end, sigma + 0.6, "±σ ", ha="right", va="bottom", color=MUTED, fontsize=11)
    fig.savefig(OUT / "fig_gu_build.svg")
    plt.close(fig)
    print(f"  build: sigma {sigma:.2f} kt, T {tc:.2f} s")


def fig_sqrt() -> None:
    """Why the kick scales with sqrt(dt): the spread of the summed kicks over time."""
    rng = np.random.default_rng(2)
    fig, axs = plt.subplots(1, 2, figsize=(6.6, 2.7), sharey=True, constrained_layout=True)
    for ax, power, title in ((axs[0], 1.0, "kick ∝ Δt"), (axs[1], 0.5, "kick ∝ √Δt")):
        for dt, c in ((0.1, MUTED), (0.01, BLUE), (0.001, ORANGE)):
            n = int(round(2.0 / dt))
            paths = np.cumsum(dt**power * rng.standard_normal((n, 2000)), axis=0)
            t = np.arange(1, n + 1) * dt
            ax.plot(t, paths.std(axis=1), color=c, lw=2.2, label=f"Δt = {dt:g} s")
        ax.set_title(title, loc="left", fontsize=13)
        ax.set_xlabel("time t [s]")
    axs[0].set_ylabel("spread of the\nsum of kicks")
    axs[0].legend(fontsize=9.5, loc="upper left")
    axs[0].text(1.95, 0.62, "shrinks to 0 as Δt → 0", ha="right", fontsize=10.5, color=INK)
    axs[1].text(1.95, 0.25, "same for every Δt: √t", ha="right", fontsize=10.5, color=INK)
    fig.savefig(OUT / "fig_gu_sqrt.svg")
    plt.close(fig)


def _var_ratio(r, method: str):
    r = np.asarray(r, float)
    if method == "em":
        return 1.0 / (1.0 - r / 2.0)
    return (1 - r + r * r / 4) / (1 - r + r * r / 2 - r**3 / 8)


def fig_var() -> None:
    """Gust variance error of the stepped equation: EM first order, Heun second."""
    r = np.logspace(-3, 0, 200)
    fig, ax = plt.subplots(figsize=(6.6, 5.0), constrained_layout=True)
    ax.axvspan(0.01 / 3.0, 0.01 / 0.3, color=BLUE, alpha=0.10, lw=0)
    ax.text(math.sqrt(0.01 / 3.0 * 0.01 / 0.3), 2.5e2, "our runs\nΔt = 0.01 s,\nT = 0.3–3 s",
            ha="center", va="top", fontsize=10.5, color=INK)  # fmt: skip
    for m, lab, c, ls in (("em", "Euler–Maruyama", ORANGE, "--"), ("heun", "Heun", BLUE, "-")):
        ax.loglog(r, 100 * np.abs(_var_ratio(r, m) - 1), color=c, lw=2.6, ls=ls, label=lab)
        rs, vs = [], []
        base = gust_signal(W20_REF, H_REF, 150.0, t_end_s=0.01, dt_s=0.01)
        for rr in (0.2, 0.4, 0.8):
            dt = rr * base["T_u"]
            g = gust_signal(W20_REF, H_REF, 150.0, t_end_s=150 * base["T_u"], dt_s=dt, method=m,
                            seed=11, n_paths=3000)  # fmt: skip
            rs.append(rr)
            vs.append(abs(float(np.mean(g["u"] ** 2)) / g["sigma_u"] ** 2 - 1))
        ax.loglog(rs, 100 * np.array(vs), "o", ms=8, mfc="white", mec=c, mew=2)
    ax.text(0.0025, 100 * 0.0025 / 2 * 1.9, "∝ Δt", color=ORANGE, fontsize=13, fontweight="bold",
            rotation=20)  # fmt: skip
    ax.text(0.0025, 100 * (0.0025**2 / 4) * 2.2, "∝ Δt²", color=BLUE, fontsize=13,
            fontweight="bold", rotation=36)  # fmt: skip
    ax.set(xlabel="time step / memory   Δt / T", ylabel="error in the gust variance [%]",
           ylim=(1e-5, 4e2), xlim=(1e-3, 1))  # fmt: skip
    ax.legend(loc="lower right", fontsize=11.5)
    fig.savefig(OUT / "fig_gu_var.svg")
    plt.close(fig)
    for rr in (0.0033, 0.033):
        print(f"  dt/T {rr}: EM {100 * (_var_ratio(rr, 'em') - 1):+.2f} %, "
              f"Heun {100 * (_var_ratio(rr, 'heun') - 1):+.4f} %")


def fig_check() -> None:
    """The generated gusts against what Dryden asks for: strength and memory."""
    g = gust_signal(W20_REF, H_REF, 150.0, t_end_s=40.0, dt_s=0.01, method="heun", seed=3,
                    n_paths=400)  # fmt: skip
    x = g["u"]
    sig, tc = g["sigma_u"], g["T_u"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(10.8, 4.0), constrained_layout=True)
    a.hist((x / sig).ravel(), bins=np.linspace(-4, 4, 41), density=True, color=BLUE, alpha=0.55,
           label="generated (400 runs × 40 s)")  # fmt: skip
    zz = np.linspace(-4, 4, 200)
    a.plot(zz, np.exp(-zz * zz / 2) / math.sqrt(2 * math.pi), color=INK, lw=2.2, ls="--",
           label="normal, std σ")  # fmt: skip
    a.set(xlabel="gust / σ", ylabel="share of time (density)")
    a.set_title(f"① strength: measured std = {np.std(x) / sig:.3f} σ", loc="left", fontsize=13)
    a.legend(loc="upper left", fontsize=10, frameon=True, framealpha=0.9, edgecolor="none")
    a.set_ylim(0, 0.52)
    xc = x - x.mean()
    kmax = int(3 * tc / 0.01)
    rho = [1.0] + [float(np.mean(xc[:-k] * xc[k:]) / np.mean(xc * xc)) for k in range(1, kmax + 1)]
    lag = np.arange(kmax + 1) * 0.01
    b.plot(lag, rho, color=BLUE, lw=3, label="generated")
    b.plot(lag, np.exp(-lag / tc), color=INK, lw=2.2, ls="--", label=r"$e^{-\tau/T}$")
    b.axvline(tc, color=MUTED, lw=1, ls=":")
    b.text(tc, 0.6, f"  τ = T = {tc:.2f} s:\n  37 % remembered", color=MUTED, fontsize=11)
    b.set(xlabel="time apart τ [s]", ylabel="correlation", ylim=(-0.05, 1.05))
    b.set_title("② memory: correlation τ seconds apart", loc="left", fontsize=13)
    b.legend(loc="upper right", fontsize=11)
    fig.savefig(OUT / "fig_gu_check.svg")
    plt.close(fig)
    print(f"  check: std {np.std(x) / sig:.4f} sigma, rho(T) {rho[int(round(tc / 0.01))]:.3f}")


def fig_history() -> None:
    """Plan deck: what the generator produces at the reference case."""
    g = gust_signal(W20_REF, H_REF, 150.0, t_end_s=10.0, dt_s=0.01, method="heun", seed=21)
    sig, tc = g["sigma_u"], g["T_u"]
    fig, ax = plt.subplots(figsize=(11.6, 2.9), constrained_layout=True)
    ax.axhspan(-sig, sig, color=GRID, alpha=0.9, lw=0)
    ax.plot(g["t"], g["u"][:, 0], color=BLUE, lw=1.6)
    ax.text(10.05, sig, f"+σ = {sig:.1f} kt", va="center", color=MUTED, fontsize=11)
    ax.text(10.05, -sig, "−σ", va="center", color=MUTED, fontsize=11)
    ax.set(xlabel="time [s]", ylabel="gust [kt]", xlim=(0, 10))
    ax.set_title(f"output: one gust history, a number every 0.01 s  (moderate, 20 ft, 150 kt: "
                 f"σ = {sig:.1f} kt, T = {tc:.2f} s)", loc="left", fontsize=12.5)  # fmt: skip
    fig.savefig(OUT / "fig_gu_history.svg")
    plt.close(fig)


def fig_sketch(data: dict) -> None:
    """Plan deck: N runs -> a distribution -> the runway that covers 95 %."""
    x = _ok(data[("b747_100", "moderate")]["samples"])["takeoff_field_ft"].to_numpy()
    fig, ax = plt.subplots(figsize=(4.6, 3.3), constrained_layout=True)
    ax.hist(x, bins=30, color=BLUE, alpha=0.7)
    p95 = np.quantile(x, 0.95)
    ax.axvline(p95, color=ORANGE, lw=2.4)
    ax.text(p95, ax.get_ylim()[1] * 0.95, " P95", color=ORANGE, fontweight="bold", va="top")
    ax.set(xlabel="runway length", ylabel="number of runs")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("N runs → a spread of runway lengths", loc="left", fontsize=12)
    fig.savefig(OUT / "fig_gu_sketch.svg")
    plt.close(fig)


def fig_budget(data: dict) -> dict:
    """Error budget of the moderate-turbulence 747 answer: the effect measured, the sampling
    error at 500 runs, and the time-step error at dt = 0.01 s (cached convergence study)."""
    path = OUT / "_gust_conv.pkl"
    if not path.exists():
        print("  (no _gust_conv.pkl yet: run presentation/_make_conv.py)")
        return {}
    conv = pickle.loads(path.read_bytes())
    heun = conv[(conv["method"] == "heun") & (conv["output"] != "landing_distance_ft")]
    e_dt = float(heun[heun["dt"] == 0.01]["error_ft"].max())
    pool = _ok(data["pool"]["samples"])["takeoff_field_ft"].to_numpy()
    calm = data["pool"]["calm"]["takeoff_field_ft"]
    rng = np.random.default_rng(0)
    p95 = np.array([np.quantile(rng.choice(pool, 500), 0.95) for _ in range(400)]) - calm
    e_samp = 1.96 * float(np.std(p95))
    x = _ok(data[("b747_100", "moderate")]["samples"])["takeoff_field_ft"].to_numpy()
    calm_mod = data[("b747_100", "moderate")]["calm"]["takeoff_field_ft"]
    effect = float(np.quantile(x, 0.95)) - calm_mod
    rows = [("the effect we measure:\nextra runway for 95 %", effect, GREEN),
            ("sampling error of that\nnumber (500 runs)", e_samp, ORANGE),
            ("time-step error\n(Heun, Δt = 0.01 s)", e_dt, BLUE)]  # fmt: skip
    fig, ax = plt.subplots(figsize=(7.0, 4.0), constrained_layout=True)
    for i, (_lab, v, c) in enumerate(rows):
        ax.barh(i, v, color=c, height=0.6)
        sign = "+" if i == 0 else "±"
        ax.text(v + 6, i, f"{sign}{v:,.0f} ft", va="center", fontsize=14, fontweight="bold",
                color=INK)  # fmt: skip
    ax.set_yticks(range(3), [r[0] for r in rows], fontsize=12, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, effect * 1.25)
    ax.set_xlabel("feet of runway")
    ax.grid(axis="y", visible=False)
    fig.savefig(OUT / "fig_gu_budget.svg")
    plt.close(fig)
    tab = conv[conv["method"] == "heun"].pivot_table(index="dt", columns="output",
                                                     values="error_ft")  # fmt: skip
    print(f"  budget: effect {effect:+.0f}, sampling ±{e_samp:.0f}, dt ±{e_dt:.1f}")
    print(tab.round(1))
    return {"effect": effect, "sampling": e_samp, "dt": e_dt, "table": tab}

def main() -> None:
    data = studies()
    fig_margin(data)
    table(data)
    fig_ou()
    fig_decay()
    print('\nDryden, moderate:')
    fig_dryden()
    fig_dryden_simple()
    fig_run(data)
    print("\nwing averaging, moderate:")
    fig_wing()
    fig_sampling(data)
    fig_days(data)
    fig_frozen()
    fig_build()
    fig_sqrt()
    fig_var()
    fig_check()
    fig_history()
    fig_sketch(data)
    fig_budget(data)
    print(f"figures in {OUT}")


if __name__ == "__main__":
    main()
