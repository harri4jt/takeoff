"""Figures for the data-uncertainty page (same style as the gust page: titles that state
the result, one axis per chart, a fixed colour per input, PNG-ready)."""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from bfl.uncertainty import quantile_ci_inf

from .figures import BFL_C, C1, C2, C3, INK, MUTED, empty
from .gust_figures import COLORS, COVER_TICKS, _layout, _rgba

FACTOR_C = {"k_CL": C1, "k_CD": C2, "k_T": C3}
FACTOR_LABEL = {"k_CL": "lift (CL)", "k_CD": "drag (CD)", "k_T": "thrust"}
OUT_LABEL = {
    "runway_required_ft": "Runway required",
    "takeoff_field_ft": "Takeoff field length",
    "landing_runway_ft": "Landing runway",
}
_ND = NormalDist()


def values(d: dict, key: str) -> np.ndarray:
    """Per draw; no solution = +inf (needs more runway than any length)."""
    return np.array([math.inf if v is None else v for v in d["values"].get(key, [])], dtype=float)


def _subtitle(d: dict) -> str:
    s = d["settings"]
    meth = "Latin hypercube" if s["method"] == "lhs" else "Monte Carlo"
    return (f"{d['aircraft']} · 1σ uncertainty: lift {100 * s['sigma_CL']:g} %, drag "
            f"{100 * s['sigma_CD']:g} %, thrust {100 * s['sigma_T']:g} % · "
            f"{len(d['errors']):,} draws ({meth})")  # fmt: skip


def _limit_text(f: float) -> str:
    return (f"beyond {100 * (1 - f):.0f} %: no runway is enough<br>({100 * f:.0f} % of draws "
            "cannot take off<br>with one engine out)")  # fmt: skip


def margin_curve(d: dict) -> go.Figure:
    """Extra runway over nominal (y) to be X % confident the runway is enough (x)."""
    keys = [k for k in ("takeoff_field_ft", "landing_runway_ft") if k in d["values"]]
    n = len(d["errors"])
    p_max = min(0.999, 1.0 - 5.0 / max(n, 6))
    ps = np.concatenate([np.linspace(0.5, 0.9, 17), np.linspace(0.91, p_max, 30)])
    ps = ps[ps <= p_max]
    fig = go.Figure()
    for key in keys:
        x = values(d, key)
        nom = d["nominal"][key]
        q = np.array([quantile_ci_inf(x, p) for p in ps])
        fin = np.isfinite(q[:, 0])
        if not fin.any():
            continue
        z = np.array([_ND.inv_cdf(p) for p in ps])[fin]
        est, lo, hi = q[fin, 0] - nom, q[fin, 1] - nom, q[fin, 2] - nom
        hi = np.where(np.isfinite(hi), hi, np.nanmax(np.where(np.isfinite(hi), hi, np.nan)))
        c = COLORS[key]
        fig.add_scatter(x=list(z) + list(z[::-1]), y=list(hi) + list(lo[::-1]), fill="toself",
                        fillcolor=_rgba(c, 0.12), line={"width": 0}, hoverinfo="skip",
                        showlegend=False)  # fmt: skip
        fig.add_scatter(
            x=z, y=est, mode="lines", name=OUT_LABEL[key], line={"color": c, "width": 2.5},
            customdata=np.stack([100 * ps[fin], est + nom], axis=1),
            hovertemplate=(f"<b>{OUT_LABEL[key]}</b><br>%{{customdata[0]:.1f}} % confident<br>"
                           "extra %{y:+,.0f} ft → %{customdata[1]:,.0f} ft<extra></extra>"),
        )  # fmt: skip
        for p, sym in ((0.95, "circle"), (0.99, "diamond")):
            e = quantile_ci_inf(x, p)[0]
            if p <= p_max and math.isfinite(e):
                fig.add_scatter(x=[_ND.inv_cdf(p)], y=[e - nom], mode="markers+text",
                                marker={"size": 9, "color": "white", "symbol": sym,
                                        "line": {"color": c, "width": 2}},
                                text=[f"{e - nom:+,.0f} ft"], textposition="top left",
                                textfont={"color": INK, "size": 11}, hoverinfo="skip",
                                showlegend=False)  # fmt: skip
    f = d["failure_rate"]
    if f > 0 and 1 - f < p_max:
        zf = _ND.inv_cdf(max(1 - f, 0.5001))
        fig.add_vline(x=zf, line={"color": BFL_C, "width": 2, "dash": "dash"})
        fig.add_annotation(x=zf, y=1, yref="paper", xanchor="left", yanchor="top", xshift=6,
                           showarrow=False, align="left", font={"color": BFL_C, "size": 12},
                           text=_limit_text(f))  # fmt: skip
    fig.add_hline(y=0, line={"color": MUTED, "width": 1, "dash": "dot"})
    ticks = [p for p in COVER_TICKS if p <= p_max + 1e-9]
    fig.update_xaxes(tickvals=[_ND.inv_cdf(p) for p in ticks],
                     ticktext=[f"{100 * p:g} %" for p in ticks],
                     title="confidence that the runway is enough (probability scale)")  # fmt: skip
    fig.update_yaxes(title="extra runway over the nominal answer [ft]", tickformat="+,")
    lead = keys[0] if keys else "takeoff_field_ft"
    e95 = quantile_ci_inf(values(d, lead), 0.95)[0] - d["nominal"].get(lead, math.nan)
    title = (f"{OUT_LABEL[lead]}: {e95:+,.0f} ft for 95 % confidence" if math.isfinite(e95)
             else f"{OUT_LABEL[lead]}: no runway gives 95 % confidence")  # fmt: skip
    return _layout(fig, title, _subtitle(d) + " · shaded: 95 % confidence of the estimate", 460)


def sensitivity(d: dict) -> go.Figure:
    """Each table's share of the runway spread (variance decomposition)."""
    sens = d.get("sensitivity") or []
    if not sens:
        return empty("No spread to split (all uncertainties zero?)")
    sens = sorted(sens, key=lambda r: r["variance_share"])
    fig = go.Figure()
    fig.add_bar(
        y=[FACTOR_LABEL[r["factor"]] for r in sens],
        x=[100 * r["variance_share"] for r in sens],
        orientation="h",
        marker={"color": [FACTOR_C[r["factor"]] for r in sens]},
        text=[
            f"{100 * r['variance_share']:.0f} %   ({r['per_sigma_ft']:+,.0f} ft per +1σ)"
            for r in sens
        ],  # fmt: skip
        textposition="outside",
        cliponaxis=False,
        hovertemplate="%{y}: %{x:.0f} % of the spread<extra></extra>",
        showlegend=False,
    )
    top = sens[-1]
    fig.update_xaxes(title="share of the runway spread [%]", range=[0, 128], ticksuffix=" %")
    sub = (f"{OUT_LABEL[d['main_output']]} · a straight-line fit explains "
           f"{100 * sens[0]['r2']:.0f} % of the spread")  # fmt: skip
    if d["failure_rate"] > 0:
        drv = ", ".join(f"{FACTOR_LABEL[k]} {v:+.1f}σ" for k, v in d["failure_drivers"].items())
        share = 100 * d["failure_rate"]
        sub += f"<br>draws with no takeoff solution ({share:.0f} %) average: {drv}"
    fig = _layout(fig, f"Which data matters: {FACTOR_LABEL[top['factor']]} drives "
                  f"{100 * top['variance_share']:.0f} % of the spread", sub, 300)  # fmt: skip
    fig.update_layout(margin={"l": 110, "t": 90 if d["failure_rate"] > 0 else 74, "b": 50})
    return fig


def scatter(d: dict) -> go.Figure:
    """Runway change against each factor, with the straight-line trend."""
    key = d["main_output"]
    y = values(d, key) - d["nominal"][key]
    fin = np.isfinite(y)
    s = d["settings"]
    sig = {"k_CL": s["sigma_CL"], "k_CD": s["sigma_CD"], "k_T": s["sigma_T"]}
    per = {r["factor"]: r["per_sigma_ft"] for r in d.get("sensitivity") or []}
    fig = make_subplots(1, 3, shared_yaxes=True, horizontal_spacing=0.04,
                        subplot_titles=[FACTOR_LABEL[k] for k in FACTOR_C])  # fmt: skip
    top = float(np.max(y[fin])) * 1.08 if fin.any() else 1.0
    for j, k in enumerate(FACTOR_C, 1):
        xk = 100 * (np.asarray(d["factors"][k]) - 1.0)
        fig.add_scatter(x=xk[fin], y=y[fin], mode="markers", row=1, col=j, showlegend=False,
                        marker={"size": 4, "color": FACTOR_C[k], "opacity": 0.45},
                        hovertemplate=FACTOR_LABEL[k] + " %{x:+.1f} %: %{y:+,.0f} ft"
                        + "<extra></extra>")  # fmt: skip
        if (~fin).any():
            fig.add_scatter(x=xk[~fin], y=np.full((~fin).sum(), top), mode="markers", row=1,
                            col=j, marker={"size": 6, "color": BFL_C, "symbol": "x"},
                            name="no takeoff solution", showlegend=j == 1,
                            hovertemplate="no solution<extra></extra>")  # fmt: skip
        if k in per and sig[k] > 0:
            xs = np.array([xk.min(), xk.max()])
            fig.add_scatter(x=xs, y=per[k] * xs / (100 * sig[k]), mode="lines", row=1, col=j,
                            line={"color": INK, "width": 1.5, "dash": "dash"}, showlegend=False,
                            hoverinfo="skip")  # fmt: skip
        fig.update_xaxes(title="change in the table [%]", ticksuffix=" %", row=1, col=j)
    fig.update_yaxes(title=f"{OUT_LABEL[key].lower()} − nominal [ft]", tickformat="+,", col=1)
    fig.update_annotations(font={"size": 12, "color": MUTED})
    fig = _layout(fig, "Each draw against each table's error", _subtitle(d)
                  + " · dashed: straight-line trend", 380)  # fmt: skip
    fig.update_layout(margin={"t": 96}, legend={"y": -0.24})
    return fig


def _color(d: dict, key: str) -> str:
    """The colour of the operation that sets the runway when one always does."""
    if key == "runway_required_ft" and "takeoff_field_ft" in d["values"]:
        to, rr = values(d, "takeoff_field_ft"), values(d, key)
        if np.array_equal(to[np.isfinite(rr)], rr[np.isfinite(rr)]):
            return COLORS["takeoff_field_ft"]
    return COLORS[key]


def distribution(d: dict) -> go.Figure:
    key = d["main_output"]
    y = values(d, key) - d["nominal"][key]
    fin = y[np.isfinite(y)]
    if not len(fin):
        return empty("No draw solved")
    fig = go.Figure()
    fig.add_histogram(x=fin, nbinsx=40, histnorm="percent", marker={"color": _color(d, key)},
                      opacity=0.75, name=OUT_LABEL[key],
                      hovertemplate="%{x} ft: %{y:.1f} %<extra></extra>")  # fmt: skip
    fig.add_vline(x=0, line={"color": INK, "width": 1.5, "dash": "dot"},
                  annotation_text="nominal", annotation_position="top")  # fmt: skip
    e95 = quantile_ci_inf(values(d, key), 0.95)[0] - d["nominal"][key]
    if math.isfinite(e95):
        lab = f"95 %: {e95:+,.0f} ft"
        fig.add_vline(x=e95, line={"color": BFL_C, "width": 2}, annotation_text=lab,
                      annotation_position="top right")  # fmt: skip
    fig.update_xaxes(title=f"{OUT_LABEL[key].lower()} − nominal [ft]", tickformat="+,")
    fig.update_yaxes(title="share of draws [%]")
    note = (f" · {100 * d['failure_rate']:.0f} % of draws not shown: no takeoff solution"
            if d["failure_rate"] > 0 else "")  # fmt: skip
    return _layout(fig, "The spread of the answer", _subtitle(d) + note, 340)


def convergence(d: dict, other: dict | None = None, p: float = 0.95) -> go.Figure:
    """The P95 estimate as draws accumulate; optionally the other sampling method too."""
    key = d["main_output"]
    fig = go.Figure()
    runs = [(d, _color(d, key), "solid")] + ([(other, MUTED, "dash")] if other else [])
    final = None
    for dd, c, dash in runs:
        x = values(dd, key)
        nom = dd["nominal"][key]
        ns = np.unique(np.linspace(20, len(x), 60).astype(int))
        q = np.array([quantile_ci_inf(x[:n], p) for n in ns]) - nom
        meth = "Latin hypercube" if dd["settings"]["method"] == "lhs" else "Monte Carlo"
        fin = np.isfinite(q[:, 0])
        if dash == "solid":
            fig.add_scatter(x=list(ns[fin]) + list(ns[fin][::-1]),
                            y=list(np.where(np.isfinite(q[fin, 2]), q[fin, 2], np.nan))
                            + list(q[fin, 1][::-1]),
                            fill="toself", fillcolor=_rgba(c, 0.15), line={"width": 0},
                            hoverinfo="skip", name="95 % confidence")  # fmt: skip
            final = q[-1]
        fig.add_scatter(x=ns[fin], y=q[fin, 0], mode="lines", name=f"P95 estimate ({meth})",
                        line={"color": c, "width": 2.5, "dash": dash},
                        hovertemplate="%{x} draws: %{y:+,.0f} ft<extra></extra>")  # fmt: skip
    ticks = [t for t in (20, 50, 100, 200, 500, 1000, 2000) if t <= len(d["errors"])]
    fig.update_xaxes(title="number of draws", type="log", tickvals=ticks,
                     ticktext=[f"{t:,}" for t in ticks])  # fmt: skip
    fig.update_yaxes(title="P95 extra runway over nominal [ft]", tickformat="+,")
    if final is not None and np.isfinite(final).all():
        title = (
            f"Sampling error: ±{(final[2] - final[1]) / 2:,.0f} ft at {len(d['errors']):,} draws"
        )
    else:
        title = "Sampling error of the P95"
    sub = OUT_LABEL[key] + (" · dashed: the same study with the other sampling method"
                            if other else "")  # fmt: skip
    return _layout(fig, title, sub, 340)


def inputs(d: dict) -> go.Figure:
    """The drawn factors against the intended normal distributions."""
    s = d["settings"]
    sig = {"k_CL": s["sigma_CL"], "k_CD": s["sigma_CD"], "k_T": s["sigma_T"]}
    fig = make_subplots(1, 3, horizontal_spacing=0.06,
                        subplot_titles=[f"{FACTOR_LABEL[k]} (1σ {100 * sig[k]:g} %)"
                                        for k in FACTOR_C])  # fmt: skip
    for j, k in enumerate(FACTOR_C, 1):
        xk = 100 * (np.asarray(d["factors"][k]) - 1.0)
        if sig[k] <= 0:
            continue
        fig.add_histogram(x=xk, nbinsx=30, histnorm="probability density", row=1, col=j,
                          marker={"color": FACTOR_C[k]}, opacity=0.6, showlegend=False)  # fmt: skip
        xs = np.linspace(-3 * 100 * sig[k], 3 * 100 * sig[k], 200)
        pdf = np.exp(-0.5 * (xs / (100 * sig[k])) ** 2) / (100 * sig[k] * math.sqrt(2 * math.pi))
        fig.add_scatter(x=xs, y=pdf, mode="lines", line={"color": INK, "width": 1.6},
                        showlegend=j == 1, name="intended normal", row=1, col=j)  # fmt: skip
        fig.update_xaxes(title="change [%]", ticksuffix=" %", row=1, col=j)
    fig.update_annotations(font={"size": 12, "color": MUTED})
    meth = "Latin hypercube" if s["method"] == "lhs" else "Monte Carlo"
    fig = _layout(fig, f"The draws ({meth}) against the intended distributions",
                  "Latin hypercube puts exactly one draw in each equally likely slice of every "
                  "input, so the histograms follow the curve closely", 320)  # fmt: skip
    fig.update_layout(margin={"t": 96}, legend={"y": -0.3})
    return fig


__all__ = ["margin_curve", "sensitivity", "scatter", "distribution", "convergence", "inputs",
           "values", "OUT_LABEL"]  # fmt: skip
