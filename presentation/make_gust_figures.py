"""Figures for the 11/25/26 update (gust analysis): presentation/fig_gu_*.svg.

    python presentation/make_gust_figures.py

Uses the existing bfl gust analysis (no code changes). The gust studies take a few
minutes; their results are cached in presentation/_gust_cache.pkl (delete it to re-run).
"""

from __future__ import annotations

import math
import pickle
from pathlib import Path
from statistics import NormalDist

import matplotlib.pyplot as plt
import numpy as np

from bfl import load_config
from bfl.gusts import GustSettings, dryden, gust_study, quantile_ci, span_average

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
    fig, ax = plt.subplots(figsize=(7.4, 4.6), constrained_layout=True)
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
    fig, ax = plt.subplots(figsize=(7.6, 4.2), constrained_layout=True)
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


def main() -> None:
    data = studies()
    fig_margin(data)
    table(data)
    fig_ou()
    fig_decay()
    print('\nDryden, moderate:')
    fig_dryden()
    fig_run(data)
    print("\nwing averaging, moderate:")
    fig_wing()
    fig_sampling(data)
    print(f"figures in {OUT}")


if __name__ == "__main__":
    main()
