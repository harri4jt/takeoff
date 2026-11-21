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


def _ok(d: dict) -> np.ndarray:
    return np.asarray([e == "" for e in d["samples"]["error"]])


def _col(d: dict, key: str) -> np.ndarray:
    x = np.asarray(d["samples"].get(key, []), dtype=float)
    return x[_ok(d)] if len(x) else x


def _subtitle(d: dict) -> str:
    s = d["settings"]
    n = int(_ok(d).sum())
    vert = "horizontal + vertical" if s["vertical"] else "horizontal only"
    return (f"{d['aircraft']} · {s['intensity']} turbulence (wind at 20 ft {d['w20']:g} kt, "
            f"{vert}) · {n:,} simulated operations")  # fmt: skip


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
                     title="share of gusty-day operations covered (probability scale)")  # fmt: skip
    fig.update_yaxes(title="extra runway over the calm-day answer [ft]", tickformat="+,")
    best = keys[0]
    e95 = quantile_ci(_col(d, best), 0.95)[0] - d["calm"][best]
    return _layout(fig, f"{SHORT[best]}: {e95:+,.0f} ft covers 95 % of gusty-day operations",
                   _subtitle(d) + " · shaded: 95 % confidence of the estimate", 460)  # fmt: skip


def _rgba(hex_color: str, a: float) -> str:
    r, g, b = (int(hex_color[k : k + 2], 16) for k in (1, 3, 5))
    return f"rgba({r},{g},{b},{a})"


# ------------------------------------------------------------------------------------
# 2. where the spread comes from
# ------------------------------------------------------------------------------------
def _steps(fig, x: np.ndarray, edges: np.ndarray, name: str, color: str, col: int) -> None:
    """A histogram as a step outline with a faint fill (overlaps stay readable)."""
    counts, _ = np.histogram(x, bins=edges)
    pct = 100.0 * counts / max(len(x), 1)
    xs = np.repeat(edges, 2)[1:-1]
    ys = np.repeat(pct, 2)
    fig.add_scatter(x=xs, y=ys, mode="lines", name=name, line={"color": color, "width": 2},
                    fill="tozeroy", fillcolor=_rgba(color, 0.08), row=1, col=col,
                    hovertemplate=f"{name}<br>%{{x:+,.0f}} ft<extra></extra>")  # fmt: skip


def spread(d: dict) -> go.Figure:
    """Change against calm of each takeoff branch and of the landing (distributions)."""
    to = [k for k in ("go_ft", "stop_ft", "aeo_ft") if k in d["samples"]]
    ld = "landing_distance_ft" if "landing_distance_ft" in d["samples"] else None
    cols = (1 if to else 0) + (1 if ld else 0)
    if not cols:
        return empty("No result")
    titles = (["takeoff branches"] if to else []) + (["landing"] if ld else [])
    fig = make_subplots(1, cols, subplot_titles=titles, horizontal_spacing=0.08,
                        column_widths=[0.62, 0.38] if cols == 2 else None)  # fmt: skip
    col = 1
    if to:
        deltas = {k: _col(d, k) - d["calm"][k] for k in to}
        allx = np.concatenate(list(deltas.values()))
        edges = np.linspace(*np.percentile(allx, [0.5, 99.5]), 36)
        for k, x in deltas.items():
            _steps(fig, x, edges, SHORT[k], COLORS[k], col)
        col += 1
    if ld:
        x = _col(d, ld) - d["calm"][ld]
        edges = np.linspace(*np.percentile(x, [0.5, 99.5]), 26)
        _steps(fig, x, edges, SHORT[ld], COLORS[ld], col)
    for c in range(1, cols + 1):
        fig.add_vline(x=0, line={"color": INK, "width": 1.2, "dash": "dot"}, row=1, col=c)
    fig.update_annotations(font={"size": 12, "color": MUTED})
    fig.update_xaxes(title="change from the calm-day distance [ft]", tickformat="+,")
    fig.update_yaxes(title="share of operations [%]", col=1, rangemode="tozero")
    lead = "landing"
    if to:
        sd = {k: float(np.std(_col(d, k))) for k in to}
        lead = SHORT[max(sd, key=sd.get)].lower()
    fig = _layout(fig, f"Where the spread comes from: the {lead} varies most",
                  _subtitle(d) + " · dotted: calm day", 400)  # fmt: skip
    fig.update_layout(margin={"t": 100, "b": 70}, legend={"y": -0.26})
    return fig


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
    fig.add_scatter(x=t, y=tr["V_ind_kts"], name="what the crew acts on (gusts lagged 1 s)",
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
    what = "Continued takeoff, engine out" if which == "go" else "Landing from 50 ft"
    fig = _layout(fig, f"One gusty operation: {what.lower()} (sample {int(run) + 1})",
                  _subtitle(d), 460)  # fmt: skip
    fig.update_annotations(selector={"text": "gusts felt by the wing"}, font={"size": 12})
    fig.update_layout(margin={"t": 100, "b": 70}, legend={"y": -0.2})
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
    fig.update_xaxes(title="number of simulated operations", type="log", tickvals=ticks,
                     ticktext=[f"{t:,}" for t in ticks])  # fmt: skip
    fig.update_yaxes(title=f"P{round(100 * p)} extra runway over calm [ft]", tickformat="+,")
    return _layout(fig, f"Sampling error: ±{half:,.0f} ft at {len(x):,} runs "
                   "(4× the runs halves it)", f"{SHORT[key]} · {_subtitle(d)}", 340)  # fmt: skip


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
    fig.update_yaxes(title="mean path error [ft]", type="log")
    fig = _layout(fig, "Time-step error: about first order, a few feet at dt = 0.01 s",
                  "same gusts at every step size (8 paths), error against dt = 0.00125 s",
                  400)  # fmt: skip
    fig.update_layout(margin={"l": 90, "b": 70}, legend={"y": -0.24})
    return fig


__all__ = ["margin_curve", "spread", "traces", "mc_convergence", "dt_convergence",
           "headline_metrics", "COLORS", "SHORT", "OUTPUTS"]  # fmt: skip
