"""Figures for the data-uncertainty page (same style as the gust page: titles that state
the result, one axis per chart, a fixed colour per input, PNG-ready)."""

from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from bfl.uncertainty import predict_failure, predict_surface, quantile_ci_inf

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


_SCATTER_SUB = (
    "each dot is one draw · dashed: straight-line trend · tight band = that table "
    "controls the runway; vertical scatter = the other tables' errors"
)


def scatter(d: dict) -> go.Figure:
    """Runway change against each factor, with the straight-line trend."""
    key = d["main_output"]
    y = values(d, key) - d["nominal"][key]
    fin = np.isfinite(y)
    s = d["settings"]
    sig = {"k_CL": s["sigma_CL"], "k_CD": s["sigma_CD"], "k_T": s["sigma_T"]}
    per = {r["factor"]: r["per_sigma_ft"] for r in d.get("sensitivity") or []}
    titles = []
    for k in FACTOR_C:
        if k in per and sig[k] > 0:
            titles.append(f"{FACTOR_LABEL[k]}: {per[k] / (100 * sig[k]):+,.0f} ft per +1 %")
        else:
            titles.append(FACTOR_LABEL[k])
    fig = make_subplots(1, 3, shared_yaxes=True, horizontal_spacing=0.04,
                        subplot_titles=titles)  # fmt: skip
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
        fig.update_xaxes(title="how wrong that table was in this draw [%]", ticksuffix=" %",
                         tickformat="+", row=1, col=j)  # fmt: skip
    fig.update_yaxes(title=f"{OUT_LABEL[key].lower()} − nominal [ft]", tickformat="+,", col=1)
    fig.update_annotations(font={"size": 12, "color": MUTED})
    fig = _layout(fig, "Every draw, three times: once against each table's error",
                  _SCATTER_SUB, 380)  # fmt: skip
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


# ------------------------------------------------------------------------------------
# setup: the three distributions being sampled
# ------------------------------------------------------------------------------------
def sigma_curves(s_cl: float, s_cd: float, s_t: float) -> go.Figure:
    """Normal(1, sigma) for each table on one axis: what the draws will look like.

    True probability densities (area 1): the draws are cut at ±3σ, so the normal density
    is divided by the 99.73 % it keeps. A tighter table is a taller, narrower curve."""
    sig = {"k_CL": s_cl / 100, "k_CD": s_cd / 100, "k_T": s_t / 100}
    span = max([3 * v for v in sig.values() if v > 0] + [0.05]) * 1.08
    xs = np.linspace(1 - span, 1 + span, 400)
    kept = _ND.cdf(3.0) - _ND.cdf(-3.0)  # 0.9973: share of a normal within ±3σ
    peak = max([1 / (v * math.sqrt(2 * math.pi) * kept) for v in sig.values() if v > 0] + [1.0])
    fig = go.Figure()
    for k, v in sig.items():
        name = f"{FACTOR_LABEL[k]} ±{100 * v:g} %"
        if v <= 0:  # no uncertainty: all the probability at 1
            fig.add_scatter(x=[1, 1], y=[0, peak], mode="lines", name=name + " (exact)",
                            line={"color": FACTOR_C[k], "width": 2.5, "dash": "dot"})  # fmt: skip
            continue
        pdf = np.exp(-0.5 * ((xs - 1) / v) ** 2) / (v * math.sqrt(2 * math.pi) * kept)
        pdf = np.where(np.abs(xs - 1) <= 3 * v, pdf, np.nan)  # draws are cut at ±3σ
        fig.add_scatter(x=xs, y=pdf, mode="lines", name=name,
                        line={"color": FACTOR_C[k], "width": 2.5}, fill="tozeroy",
                        fillcolor=_rgba(FACTOR_C[k], 0.08),
                        hovertemplate=FACTOR_LABEL[k] + "<br>multiplier %{x:.3f}"
                        + "<extra></extra>")  # fmt: skip
    fig.add_vline(x=1, line={"color": MUTED, "width": 1, "dash": "dot"})
    fig.update_xaxes(title="multiplier on the table (1 = the table as it is)", tickformat=".2f")
    fig.update_yaxes(title="probability density", rangemode="tozero")
    fig = _layout(fig, "What will be drawn", "normal around 1, cut at ±3σ; area under each = 1",
                  250)  # fmt: skip
    fig.update_layout(margin={"t": 58, "b": 44, "l": 40, "r": 12},
                      legend={"orientation": "v", "y": 1, "x": 1.0, "xanchor": "right",
                              "bgcolor": "rgba(255,255,255,0.8)"})  # fmt: skip
    return fig


# ------------------------------------------------------------------------------------
# the profiler: runway against each multiplier, the others held at the slider values
# ------------------------------------------------------------------------------------
def profiler(d: dict, sel: dict[str, float]) -> go.Figure:
    surf, fail = d.get("surface") or {}, d.get("failure_model") or {}
    if not surf:
        return empty("Too few draws solved to fit a response surface")
    s = d["settings"]
    sig = {"k_CL": s["sigma_CL"], "k_CD": s["sigma_CD"], "k_T": s["sigma_T"]}
    key = d["main_output"]
    nom = d["nominal"][key]
    order = list(FACTOR_C)
    fig = make_subplots(1, 3, shared_yaxes=True, horizontal_spacing=0.035,
                        subplot_titles=[f"runway vs {FACTOR_LABEL[k]}" for k in order])  # fmt: skip
    here = float(predict_surface(surf, sel["k_CL"], sel["k_CD"], sel["k_T"]))
    p_here = float(predict_failure(fail, sel["k_CL"], sel["k_CD"], sel["k_T"]))
    ys = []
    for j, k in enumerate(order, 1):
        v = sig[k] if sig[k] > 0 else 0.0
        xs = np.linspace(1 - 3 * v, 1 + 3 * v, 121) if v > 0 else np.array([0.999, 1.001])
        args = {kk: (xs if kk == k else np.full_like(xs, sel[kk])) for kk in order}
        y = predict_surface(surf, args["k_CL"], args["k_CD"], args["k_T"])
        pf = predict_failure(fail, args["k_CL"], args["k_CD"], args["k_T"])
        good = pf < 0.5
        ys.append(y[good])
        fig.add_scatter(x=xs, y=np.where(good, y, np.nan), mode="lines", row=1, col=j,
                        line={"color": FACTOR_C[k], "width": 3}, showlegend=False,
                        hovertemplate=FACTOR_LABEL[k] + " × %{x:.3f}: %{y:,.0f} ft"
                        + "<extra></extra>")  # fmt: skip
        if (~good).any():  # predicted: no engine-out takeoff
            xb = xs[~good]
            fig.add_vrect(x0=float(xb.min()), x1=float(xb.max()), fillcolor=_rgba(BFL_C, 0.12),
                          line_width=0, row=1, col=j,
                          annotation_text="no takeoff", annotation_position="top left",
                          annotation_font={"color": BFL_C, "size": 11})  # fmt: skip
        fig.add_vline(x=sel[k], line={"color": INK, "width": 1.5, "dash": "dash"}, row=1, col=j)
        if p_here < 0.5:
            fig.add_scatter(x=[sel[k]], y=[here], mode="markers", row=1, col=j,
                            marker={"size": 11, "color": "white",
                                    "line": {"color": INK, "width": 2.5}},
                            showlegend=False, hoverinfo="skip")  # fmt: skip
        fig.update_xaxes(title=f"{FACTOR_LABEL[k]} multiplier", tickformat=".2f", row=1, col=j)
    allv = np.concatenate([v for v in ys if len(v)] + [[nom]])
    pad = 0.06 * (allv.max() - allv.min() + 1)
    fig.update_yaxes(range=[allv.min() - pad, allv.max() + pad], title=OUT_LABEL[key] + " [ft]",
                     tickformat=",", col=1)  # fmt: skip
    fig.add_hline(y=nom, line={"color": MUTED, "width": 1, "dash": "dot"})
    fig.update_annotations(font={"size": 12, "color": MUTED})
    point = ", ".join(f"{FACTOR_LABEL[k]} ×{sel[k]:.3f}" for k in order)
    if p_here >= 0.5:
        title = "At this point the aircraft is not expected to make an engine-out takeoff"
    else:
        title = f"{OUT_LABEL[key]} at the selected point: {here:,.0f} ft ({here - nom:+,.0f} ft)"
    sub = (f"{point} · from a response surface fitted to the {surf['n']} draws "
           f"(accurate to about ±{surf['loo_rms_ft']:.0f} ft on draws it did not see)")  # fmt: skip
    fig = _layout(fig, title, sub, 360)
    fig.update_layout(margin={"t": 100}, hovermode="closest")
    return fig


# ------------------------------------------------------------------------------------
# where the uncertainty comes from: shares as a pie
# ------------------------------------------------------------------------------------
def shares_pie(d: dict) -> go.Figure:
    sens = d.get("sensitivity") or []
    if not sens:
        return empty("No spread to split (all uncertainties zero?)")
    sens = sorted(sens, key=lambda r: -r["variance_share"])
    labels = [FACTOR_LABEL[r["factor"]] for r in sens]
    vals = [max(r["variance_share"], 0.0) for r in sens]
    colors = [FACTOR_C[r["factor"]] for r in sens]
    rest = max(0.0, 1.0 - sum(vals))
    if rest > 0.005:
        labels.append("not a straight-line effect")
        vals.append(rest)
        colors.append("#c7cfd8")
    fig = go.Figure(go.Pie(labels=labels, values=vals, hole=0.45, sort=False, direction="clockwise",
                           marker={"colors": colors, "line": {"color": "white", "width": 2}},
                           texttemplate=[f"<b>{100 * v / sum(vals):.0f} %</b>" if v / sum(vals)
                                         > 0.04 else "" for v in vals],
                           textposition="inside", insidetextorientation="horizontal",
                           textfont={"size": 15, "color": "white"},
                           hovertemplate="%{label}: %{percent}<extra></extra>"))  # fmt: skip
    top = sens[0]
    fig = _layout(fig, f"Where the runway uncertainty comes from: mostly {labels[0]}",
                  OUT_LABEL[d["main_output"]], 340)  # fmt: skip
    fig.update_layout(showlegend=True, margin={"t": 80, "b": 20, "l": 20, "r": 20},
                      legend={"orientation": "v", "x": 1.0, "y": 0.5, "xanchor": "left",
                              "font": {"size": 13}})  # fmt: skip
    del top
    return fig


__all__ = [
    "sigma_curves", "profiler", "shares_pie", "margin_curve", "scatter",
    "distribution", "convergence", "inputs", "values", "OUT_LABEL",
]  # fmt: skip
