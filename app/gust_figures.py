"""Figures for the gust analysis page. Each is made to be dropped into a slide as is:
a title that states the result, one axis per chart, the same colour for an output in
every chart, and direct labels only where they carry the answer (P95, P99)."""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from bfl.gusts import OUTPUTS, quantile_ci

from .figures import AEO_C, FAA_C, FONT, GO_C, GRID, INK, LAND_C, MUTED, STOP_C, empty

RUNWAY_C = INK
LANDING_C = "#9a6a00"  # the landing-runway colour used in the landing animation
COLORS = {
    "runway_required_ft": RUNWAY_C,
    "takeoff_field_ft": FAA_C,
    "landing_runway_ft": LANDING_C,
    "go_ft": GO_C,
    "stop_ft": STOP_C,
    "aeo_ft": AEO_C,
    "landing_distance_ft": LAND_C,
}
SHORT = {
    "runway_required_ft": "Runway required",
    "takeoff_field_ft": "Takeoff field length",
    "landing_runway_ft": "Landing runway",
    "go_ft": "Continued takeoff (go)",
    "stop_ft": "Rejected takeoff (stop)",
    "aeo_ft": "All engines",
    "landing_distance_ft": "Landing distance",
}
_ND = NormalDist()
COVER_TICKS = (0.5, 0.8, 0.9, 0.95, 0.99, 0.999)


def _layout(fig: go.Figure, title: str, subtitle: str, height: int) -> go.Figure:
    fig.update_layout(
        title={"text": f"<b>{title}</b><br><span style='font-size:12px;color:{MUTED}'>"
               f"{subtitle}</span>", "x": 0.0, "xanchor": "left", "font": {"size": 16}},
        height=height,
        margin={"l": 64, "r": 24, "t": 74, "b": 56},
        paper_bgcolor="white",
        plot_bgcolor="white",
        font={"family": FONT, "color": INK, "size": 12},
        legend={"orientation": "h", "y": -0.18, "x": 0, "font": {"size": 12}},
        hoverlabel={"font": {"family": FONT}},
    )  # fmt: skip
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor="#c7cfd8", ticks="outside")
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor="#c7cfd8", ticks="outside")
    return fig


# ------------------------------------------------------------------------------------
# shared with the data-uncertainty page: the chance each candidate runway is enough
# ------------------------------------------------------------------------------------
def wilson(p, n: int, z: float = 1.96):
    """95 % Wilson interval for a share p of n draws (works on arrays)."""
    p = np.asarray(p, float)
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return np.clip(mid - half, 0, 1), np.clip(mid + half, 0, 1)


def fmt_p(p: float) -> str:
    """A share as a percentage; never '100 %' or '0 %' from a finite number of draws."""
    p = float(p)
    if p >= 0.995:
        return ">99 %"
    if p <= 0.005:
        return "<1 %"
    return f"{100 * p:.0f} %"


def odds_chart(
    x: np.ndarray,
    nominal: float,
    runways: list[float],
    color: str,
    subtitle: str,
    nominal_label: str = "calm",
    what: str = "runs",
    fail_text: str = "cannot take off",
) -> go.Figure:
    """Chance of fitting (y) against runway length (x), candidate runways marked.

    x: one runway per run (+inf = no runway is enough). The band is a 95 % Wilson interval
    on the share; if some runs need more than any runway, the curve stops at a ceiling."""
    n = len(x)
    fin = np.sort(x[np.isfinite(x)])
    f = 1 - len(fin) / n if n else 0.0
    lo_x = min(float(fin[0]) if len(fin) else nominal, nominal)
    hi_x = max([float(fin[-1]) if len(fin) else nominal] + list(runways))
    span = max(hi_x - lo_x, 500.0)
    xs = np.linspace(lo_x - 0.04 * span, hi_x + 0.16 * span, 500)  # room for labels
    p = np.searchsorted(fin, xs, side="right") / n
    lo, hi = wilson(p, n)
    fig = go.Figure()
    fig.add_scatter(x=list(xs) + list(xs[::-1]), y=list(100 * hi) + list(100 * lo[::-1]),
                    fill="toself", fillcolor=_rgba(color, 0.14), line={"width": 0},
                    hoverinfo="skip", name="sampling 95 % CI")  # fmt: skip
    fig.add_scatter(x=xs, y=100 * p, mode="lines", line={"color": color, "width": 3},
                    showlegend=False,
                    hovertemplate=f"%{{x:,.0f}} ft: enough in %{{y:.0f}} % of {what}"
                    "<extra></extra>")  # fmt: skip
    fig.add_vline(x=nominal, line={"color": MUTED, "width": 1, "dash": "dot"})
    fig.add_annotation(x=nominal, y=1, yref="paper", text=f"{nominal_label} {nominal:,.0f}",
                       showarrow=False, xanchor="right", yanchor="top", xshift=-4,
                       font={"size": 11, "color": MUTED})  # fmt: skip
    if f > 0:
        fig.add_hline(y=100 * (1 - f), line={"color": "#d7263d", "width": 1.5, "dash": "dash"})
        fig.add_annotation(x=0, xref="paper", y=100 * (1 - f), yanchor="bottom", xanchor="left",
                           xshift=4, showarrow=False, font={"color": "#d7263d", "size": 12},
                           text=f"<b>never above {fmt_p(1 - f)}</b>: {100 * f:.0f} % of {what} "
                           f"{fail_text}")  # fmt: skip
    for r in runways:
        pr = float(np.mean(x <= r))
        fig.add_shape(type="line", x0=r, x1=r, y0=0, y1=100 * pr,
                      line={"color": INK, "width": 1.5, "dash": "dot"})  # fmt: skip
        fig.add_scatter(x=[r], y=[100 * pr], mode="markers+text", showlegend=False,
                        marker={"size": 13, "color": INK, "line": {"color": "white", "width": 2}},
                        text=[f"<b>{fmt_p(pr)}</b>  {r:,.0f} ft"], textposition="bottom right",
                        textfont={"size": 14, "color": INK}, cliponaxis=False,
                        hovertemplate=f"{r:,.0f} ft: enough in {100 * pr:.1f} % of {what}"
                        "<extra></extra>")  # fmt: skip
    fig.update_xaxes(title="runway length [ft]", tickformat=",")
    fig.update_yaxes(title="chance it is enough", ticksuffix=" %", range=[0, 104], dtick=20)
    if runways:
        title = " · ".join(f"{r:,.0f} ft: {fmt_p(np.mean(x <= r))}" for r in runways)
    else:
        title = "Chance a runway is enough"
    fig = _layout(fig, title, subtitle, 380)
    fig.update_layout(legend={"y": -0.2, "x": 1, "xanchor": "right"}, hovermode="closest")
    return fig


def _ok(d: dict) -> np.ndarray:
    return np.asarray([e == "" for e in d["samples"]["error"]])


def _col(d: dict, key: str) -> np.ndarray:
    x = np.asarray(d["samples"].get(key, []), dtype=float)
    return x[_ok(d)] if len(x) else x


def _subtitle(d: dict) -> str:
    s = d["settings"]
    n = int(_ok(d).sum())
    vert = "horizontal + vertical" if s["vertical"] else "horizontal only"
    return (f"{d['aircraft']} · {s['intensity']} turbulence (W20 {d['w20']:g} kt, {vert}) · "
            f"{n:,} runs")  # fmt: skip


def headline_metrics(d: dict) -> list[str]:
    return [k for k in ("runway_required_ft", "takeoff_field_ft", "landing_runway_ft")
            if k in d["samples"]]  # fmt: skip


# ------------------------------------------------------------------------------------
# 1. the answer: extra runway against the share of operations covered
# ------------------------------------------------------------------------------------
def margin_curve(d: dict) -> go.Figure:
    """Extra runway over calm (y) needed to cover a share of gusty operations (x, on a
    probability scale so the tail gets room), with 95 % confidence bands."""
    keys = [k for k in ("takeoff_field_ft", "landing_runway_ft") if k in d["samples"]]
    if not keys:
        return empty("No result")
    fig = go.Figure()
    n = int(_ok(d).sum())
    p_max = min(0.999, 1.0 - 5.0 / max(n, 6))  # at least 5 runs beyond the quantile
    ps = np.concatenate([np.linspace(0.5, 0.9, 17), np.linspace(0.91, p_max, 30)])
    ps = ps[ps <= p_max]
    zs = [_ND.inv_cdf(p) for p in ps]
    for key in keys:
        x = _col(d, key)
        calm = d["calm"].get(key, math.nan)
        est, lo, hi = np.array([quantile_ci(x, p) for p in ps]).T - calm
        c = COLORS[key]
        name = SHORT[key]
        fig.add_scatter(x=zs + zs[::-1], y=list(hi) + list(lo[::-1]), fill="toself",
                        fillcolor=_rgba(c, 0.12), line={"width": 0}, hoverinfo="skip",
                        showlegend=False, legendgroup=key)  # fmt: skip
        fig.add_scatter(
            x=zs, y=est, mode="lines", name=name, legendgroup=key, line={"color": c, "width": 2.5},
            customdata=np.stack([100 * ps, est + calm, lo, hi], axis=1),
            hovertemplate=(f"<b>{name}</b><br>%{{customdata[0]:.1f}} % of operations covered<br>"
                           "extra %{y:+,.0f} ft → %{customdata[1]:,.0f} ft<br>"
                           "95 % CI %{customdata[2]:+,.0f} … %{customdata[3]:+,.0f} ft"
                           "<extra></extra>"),
        )  # fmt: skip
        for p, sym in ((0.95, "circle"), (0.99, "diamond")):
            if p > p_max:
                continue
            e, _, _ = quantile_ci(x, p)
            fig.add_scatter(x=[_ND.inv_cdf(p)], y=[e - calm], mode="markers+text",
                            marker={"size": 9, "color": "white", "symbol": sym,
                                    "line": {"color": c, "width": 2}},
                            text=[f"{e - calm:+,.0f} ft"], textposition="top left",
                            textfont={"color": INK, "size": 11}, hoverinfo="skip",
                            showlegend=False, legendgroup=key)  # fmt: skip
    fig.add_hline(y=0, line={"color": MUTED, "width": 1, "dash": "dot"})
    ticks = [p for p in COVER_TICKS if p <= p_max + 1e-9]
    fig.update_xaxes(tickvals=[_ND.inv_cdf(p) for p in ticks],
                     ticktext=[f"{100 * p:g} %" for p in ticks],
                     title="share of gusty days covered")  # fmt: skip
    fig.update_yaxes(title="extra runway over calm [ft]", tickformat="+,")
    best = keys[0]
    e95 = quantile_ci(_col(d, best), 0.95)[0] - d["calm"][best]
    what = "takeoffs" if best == "takeoff_field_ft" else "landings"
    return _layout(fig, f"{e95:+,.0f} ft covers 95 % of gusty {what}",
                   _subtitle(d) + " · shaded: sampling 95 % CI", 440)  # fmt: skip


def _rgba(hex_color: str, a: float) -> str:
    r, g, b = (int(hex_color[k : k + 2], 16) for k in (1, 3, 5))
    return f"rgba({r},{g},{b},{a})"


# ------------------------------------------------------------------------------------
# 3. what one gusty operation looks like
# ------------------------------------------------------------------------------------
def traces(d: dict, run: str = "0", which: str = "go") -> go.Figure:
    tr = d["traces"].get(run, {}).get(which)
    if not tr:
        return empty("No sample history")
    t = tr["t_s"]
    fig = make_subplots(2, 1, shared_xaxes=True, vertical_spacing=0.12, row_heights=[0.45, 0.55],
                        subplot_titles=("gusts felt by the wing", "airspeed"))  # fmt: skip
    fig.add_scatter(x=t, y=tr["u_g_kts"], name="horizontal gust (+ headwind)", mode="lines",
                    line={"color": GO_C, "width": 1.2}, row=1, col=1)  # fmt: skip
    if d["settings"]["vertical"]:
        fig.add_scatter(x=t, y=tr["w_g_kts"], name="vertical gust (+ up)", mode="lines",
                        line={"color": STOP_C, "width": 1.2}, row=1, col=1)  # fmt: skip
    fig.add_scatter(x=t, y=tr["V_air_kts"], name="true airspeed", mode="lines",
                    line={"color": "#9aa5b1", "width": 1}, row=2, col=1)  # fmt: skip
    fig.add_scatter(x=t, y=tr["V_ind_kts"], name="what the crew acts on (gust part lagged)",
                    mode="lines", line={"color": INK, "width": 2}, row=2, col=1)  # fmt: skip
    if which == "go":
        sp = d["speeds"]
        for v, lab, pos in (
            (sp["v_ef_kts"], "engine fails", "bottom left"),
            (sp["vr_kts"], "rotate (VR)", "top left"),
        ):
            fig.add_hline(y=v, line={"color": MUTED, "width": 1, "dash": "dot"}, row=2, col=1,
                          annotation_text=f"{lab} {v:.0f} kt", annotation_position=pos,
                          annotation_font={"size": 10, "color": MUTED})  # fmt: skip
    fig.update_yaxes(title="kt", row=1, col=1)
    fig.update_yaxes(title="kt (equivalent)", row=2, col=1)
    fig.update_xaxes(title="time [s]", row=2, col=1)
    what = "engine-out takeoff" if which == "go" else "landing from 50 ft"
    fig = _layout(fig, f"One gusty {what} (run {int(run) + 1})",
                  "top: the gusts the wing feels · bottom: the airspeed it feels (grey) and "
                  "the one "
                  "the crew flies by (black)", 460)  # fmt: skip
    fig.update_annotations(selector={"text": "gusts felt by the wing"}, font={"size": 12})
    fig.update_layout(margin={"t": 100, "b": 70}, legend={"y": -0.2})
    return fig


# ------------------------------------------------------------------------------------
# 4. how the gusts are made (bfl.gusts.gust_signal at a fixed height and airspeed)
# ------------------------------------------------------------------------------------
U_C, W_C = "#2a78d6", "#eb6834"  # horizontal / vertical gust, as on the slides


def gust_history(g: dict, label: str, window_s: float = 20.0) -> go.Figure:
    """One path of each gust component with its +/- sigma band."""
    t = np.asarray(g["t"])
    k = t <= window_s
    fig = make_subplots(2, 1, shared_xaxes=True, vertical_spacing=0.1,
                        subplot_titles=(f"along the runway: σ {g['sigma_u']:.1f} kt, "
                                        f"T {g['T_u']:.2f} s",
                                        f"vertical: σ {g['sigma_w']:.1f} kt, "
                                        f"T {g['T_w']:.2f} s"))  # fmt: skip
    for row, comp, c, sig in ((1, "u", U_C, g["sigma_u"]), (2, "w", W_C, g["sigma_w"])):
        y = np.asarray(g[comp])[:, 0][k]
        fig.add_hrect(y0=-sig, y1=sig, fillcolor=_rgba(c, 0.10), line_width=0, row=row, col=1)
        fig.add_scatter(x=t[k], y=y, mode="lines", line={"color": c, "width": 1.4},
                        showlegend=False, row=row, col=1,
                        hovertemplate="%{x:.2f} s: %{y:+.1f} kt<extra></extra>")  # fmt: skip
        fig.update_yaxes(title="kt", row=row, col=1)
    lim = 3.6 * max(g["sigma_u"], g["sigma_w"])
    fig.update_yaxes(range=[-lim, lim])
    fig.update_xaxes(title="time [s]", row=2, col=1)
    fig.update_annotations(font={"size": 13, "color": INK})
    fig = _layout(fig, "One gust history", f"{label} · shaded: ±σ", 400)
    fig.update_layout(margin={"t": 92})
    return fig


def _autocorr(x: np.ndarray, kmax: int) -> np.ndarray:
    """Sample autocorrelation over all paths (columns), lags 0..kmax."""
    x = x - x.mean()
    v = float(np.mean(x * x))
    return np.array([1.0] + [float(np.mean(x[:-k] * x[k:])) / v for k in range(1, kmax + 1)])


def gust_checks(g: dict, dt: float) -> go.Figure:
    """Does the generator give what Dryden asks for? Strength (histogram vs normal) and
    memory (autocorrelation vs e^(-tau/T)), both components scaled to one axis."""
    fig = make_subplots(1, 2, horizontal_spacing=0.1,
                        subplot_titles=("strength: gust / σ",
                                        "memory: correlation after a lag τ"))  # fmt: skip
    z = np.linspace(-4, 4, 200)
    fig.add_scatter(x=z, y=np.exp(-z * z / 2) / math.sqrt(2 * math.pi), mode="lines",
                    line={"color": INK, "width": 2, "dash": "dash"}, name="target", row=1,
                    col=1, legendgroup="t")  # fmt: skip
    ratios = []
    for comp, c, sig, tc, lab in (("u", U_C, g["sigma_u"], g["T_u"], "along the runway"),
                                   ("w", W_C, g["sigma_w"], g["T_w"], "vertical")):  # fmt: skip
        x = np.asarray(g[comp])
        ratios.append(float(np.std(x)) / sig)
        edges = np.linspace(-4, 4, 41)
        cnt, _ = np.histogram((x / sig).ravel(), bins=edges, density=True)
        fig.add_scatter(x=np.repeat(edges, 2)[1:-1], y=np.repeat(cnt, 2), mode="lines",
                        line={"color": c, "width": 2}, fill="tozeroy",
                        fillcolor=_rgba(c, 0.08), name=lab, legendgroup=comp, row=1, col=1,
                        hoverinfo="skip")  # fmt: skip
        kmax = int(min(3.0 * tc / dt, x.shape[0] / 4))
        if kmax >= 2:
            r = _autocorr(x, kmax)
            fig.add_scatter(x=np.arange(kmax + 1) * dt / tc, y=r, mode="lines",
                            line={"color": c, "width": 2.5}, showlegend=False,
                            legendgroup=comp, row=1, col=2,
                            hovertemplate="τ/T %{x:.2f}: %{y:.2f}<extra></extra>")  # fmt: skip
    tt = np.linspace(0, 3, 100)
    fig.add_scatter(x=tt, y=np.exp(-tt), mode="lines", showlegend=False, legendgroup="t",
                    line={"color": INK, "width": 2, "dash": "dash"}, row=1, col=2)  # fmt: skip
    fig.update_xaxes(title="gust / σ", row=1, col=1)
    fig.update_xaxes(title="lag τ / T", row=1, col=2)
    fig.update_yaxes(title="density", row=1, col=1)
    fig.update_yaxes(title="correlation", range=[-0.1, 1.05], row=1, col=2)
    fig.update_annotations(font={"size": 13, "color": INK})
    worst = max(abs(r - 1) for r in ratios)
    title = (f"The generator checks out: strength within {100 * worst:.1f} %, memory e^(−τ/T)"
             if worst < 0.03 else
             f"Strength off by {100 * worst:.0f} %: the time step is too long for the "
             "memory T")  # fmt: skip
    n_paths = np.asarray(g["u"]).shape[1]
    fig = _layout(fig, title, f"{n_paths} paths × {g['t'][-1]:.0f} s · dashed: what Dryden "
                  "asks for", 340)  # fmt: skip
    fig.update_layout(margin={"t": 92}, legend={"y": -0.25})
    return fig


def variance_ratio(r: np.ndarray, method: str) -> np.ndarray:
    """Long-run gust variance / sigma^2 of the stepped OU process, step r = dt / T.

    EM:   g+ = (1 - r) g + sigma sqrt(2r) Z           -> 1 / (1 - r/2)
    Heun: g+ = (1 - r + r^2/2) g + (1 - r/2) sigma sqrt(2r) Z
                                                       -> (1 - r + r^2/4) / (1 - r + r^2/2 - r^3/8)
    (the stationary variance of g+ = a g + b Z is b^2 / (1 - a^2))."""
    r = np.asarray(r, float)
    if method == "em":
        return 1.0 / (1.0 - r / 2.0)
    return (1 - r + r * r / 4) / (1 - r + r * r / 2 - r**3 / 8)


def variance_error(
    points: dict | None = None, r_now: tuple[float, float] | None = None
) -> go.Figure:
    """Relative error of the gust variance against dt/T: EM first order, Heun second."""
    r = np.logspace(-3, 0, 120)
    fig = go.Figure()
    for m, lab, dash in (("em", "Euler–Maruyama", "dash"), ("heun", "stochastic Heun", "solid")):
        err = np.abs(variance_ratio(r, m) - 1)
        fig.add_scatter(x=r, y=100 * err, mode="lines", name=lab,
                        line={"color": INK if m == "heun" else MUTED, "width": 2.5, "dash": dash},
                        hovertemplate="Δt/T %{x:.3f}: %{y:.3g} %<extra></extra>")  # fmt: skip
        if points and m in points:
            pr, pe = points[m]
            fig.add_scatter(x=pr, y=100 * np.abs(np.asarray(pe) - 1), mode="markers",
                            name=f"{lab}, simulated", showlegend=False,
                            marker={"size": 9, "color": "white",
                                    "line": {"color": INK if m == "heun" else MUTED, "width": 2}},
                            hovertemplate="simulated: %{y:.3g} %<extra></extra>")  # fmt: skip
    if r_now:
        fig.add_vrect(x0=r_now[0], x1=r_now[1], fillcolor="rgba(42,120,214,0.14)", line_width=0)
        fig.add_annotation(x=math.log10(math.sqrt(r_now[0] * r_now[1])), y=1, yref="paper",
                           text="this run", showarrow=False, yanchor="bottom",
                           font={"size": 11, "color": INK})  # fmt: skip
    fig.update_xaxes(title="time step / memory  Δt / T", type="log")
    fig.update_yaxes(title="error in gust variance [%]", type="log", exponentformat="power")
    fig = _layout(fig, "Gust strength error: Euler–Maruyama ∝ Δt, Heun ∝ Δt²",
                  "lines: exact formula for the stepped equation · dots: simulated",
                  340)  # fmt: skip
    fig.update_layout(legend={"y": -0.24})
    return fig


# ------------------------------------------------------------------------------------
# 4. how reliable the numbers are
# ------------------------------------------------------------------------------------
def mc_convergence(d: dict, key: str | None = None, p: float = 0.95) -> go.Figure:
    """The P95 estimate as runs accumulate, with its 95 % confidence band (~1/sqrt(n))."""
    key = key or next(k for k in ("takeoff_field_ft", "landing_runway_ft") if k in d["samples"])
    x = _col(d, key)
    if len(x) < 20:
        return empty("Too few runs")
    calm = d["calm"][key]
    ns = np.unique(np.linspace(20, len(x), 60).astype(int))
    est, lo, hi = np.array([quantile_ci(x[:n], p) for n in ns]).T - calm
    c = COLORS[key]
    fig = go.Figure()
    fig.add_scatter(x=list(ns) + list(ns[::-1]), y=list(hi) + list(lo[::-1]), fill="toself",
                    fillcolor=_rgba(c, 0.15), line={"width": 0}, hoverinfo="skip",
                    name="95 % confidence")  # fmt: skip
    fig.add_scatter(x=ns, y=est, mode="lines", line={"color": c, "width": 2.5},
                    name=f"P{round(100 * p)} estimate",
                    hovertemplate="%{x} runs: %{y:+,.0f} ft<extra></extra>")  # fmt: skip
    half = (hi[-1] - lo[-1]) / 2
    ticks = [t for t in (20, 50, 100, 200, 500, 1000, 2000, 5000) if t <= len(x)]
    fig.update_xaxes(title="runs", type="log", tickvals=ticks,
                     ticktext=[f"{t:,}" for t in ticks])  # fmt: skip
    fig.update_yaxes(title=f"P{round(100 * p)} extra runway over calm [ft]", tickformat="+,")
    fig = _layout(fig, f"Sampling error: ±{half:,.0f} ft at {len(x):,} runs",
                  f"{SHORT[key]} · 4× the runs halves it", 340)  # fmt: skip
    fig.update_layout(legend={"y": -0.3})
    return fig


def dt_convergence(conv: dict) -> go.Figure:
    """Strong (path-wise) error against time step for both SDE methods."""
    if not conv or not conv.get("dt"):
        return empty("Press 'Check the time step' to re-solve a few runs at four step sizes", 120)
    fig = go.Figure()
    styles = {
        "em": ("Euler–Maruyama", "dash", "circle-open"),
        "heun": ("stochastic Heun", "solid", "circle"),
    }
    outs = [o for o in ("go_ft", "landing_distance_ft") if o in conv["output"]]
    rows = list(zip(conv["method"], conv["output"], conv["dt"], conv["error_ft"], strict=True))
    for o in outs:
        for m, (lab, dash, sym) in styles.items():
            pts = sorted((dt, e) for mm, oo, dt, e in rows if mm == m and oo == o)
            if not pts:
                continue
            fig.add_scatter(x=[p[0] for p in pts], y=[p[1] for p in pts], mode="lines+markers",
                            name=f"{SHORT[o]} · {lab}",
                            line={"color": COLORS[o], "width": 2, "dash": dash},
                            marker={"size": 8, "symbol": sym},
                            hovertemplate="dt %{x} s: %{y:.2f} ft<extra></extra>")  # fmt: skip
    dts = np.array(sorted(set(conv["dt"])))
    e0 = float(np.median([e for _, oo, dt, e in rows if dt == dts.max() and oo in outs]))
    for order, lab in ((1.0, "slope 1"), (0.5, "slope ½")):
        ref = e0 * (dts / dts.max()) ** order
        fig.add_scatter(x=dts, y=ref, mode="lines", showlegend=False, hoverinfo="skip",
                        line={"color": "#b0b8c2", "width": 1, "dash": "dot"})  # fmt: skip
        fig.add_annotation(x=math.log10(dts.min()), y=math.log10(ref[0]), text=lab,
                           showarrow=False, xanchor="right", xshift=-6,
                           font={"size": 11, "color": MUTED})  # fmt: skip
    fig.update_xaxes(title="time step dt [s]", type="log", tickvals=list(dts),
                     ticktext=[f"{v:g}" for v in dts])  # fmt: skip
    ticks = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200]
    fig.update_yaxes(title="mean path error [ft]", type="log", tickvals=ticks,
                     ticktext=[f"{v:g}" for v in ticks])  # fmt: skip
    fig = _layout(fig, "Time-step error: about first order, a few feet at dt = 0.01 s",
                  "same gusts at every step size (8 paths), error against dt = 0.00125 s",
                  400)  # fmt: skip
    fig.update_layout(margin={"l": 90, "b": 70}, legend={"y": -0.24})
    return fig


__all__ = ["margin_curve", "traces", "gust_history", "gust_checks", "variance_error",
           "odds_chart", "wilson", "fmt_p", "mc_convergence", "dt_convergence",
           "headline_metrics", "COLORS", "SHORT", "OUTPUTS"]  # fmt: skip
