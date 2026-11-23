"""Figures for the data-uncertainty page.

Written for a conceptual designer checking the runway at the end of a design pass: what
runway, how sure, which table matters, and is the design near a cliff. Titles state the
result, labels are short, and every figure is PNG-ready (camera icon) for slides.
"""

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
FACTOR_LABEL = {"k_CL": "lift", "k_CD": "drag", "k_T": "thrust"}
WORSE = {"k_CL": -1, "k_CD": 1, "k_T": -1}  # the pessimistic direction of each table
OUT_LABEL = {
    "runway_required_ft": "Runway required",
    "takeoff_field_ft": "Takeoff",
    "landing_runway_ft": "Landing",
}
PESS_C, OPT_C = BFL_C, C1  # tornado: pessimistic data (longer runway) / optimistic
NO_GO = "rgba(215,38,61,0.16)"  # the no-takeoff region
_ND = NormalDist()


def values(d: dict, key: str) -> np.ndarray:
    """Per draw; no solution = +inf (needs more runway than any length)."""
    return np.array([math.inf if v is None else v for v in d["values"].get(key, [])], dtype=float)


def _sigmas(d: dict) -> dict[str, float]:
    s = d["settings"]
    return {"k_CL": s["sigma_CL"], "k_CD": s["sigma_CD"], "k_T": s["sigma_T"]}


def _subtitle(d: dict) -> str:
    sig = _sigmas(d)
    if len(set(sig.values())) == 1:
        unc = f"±{100 * sig['k_CL']:g} % (1σ) on lift, drag and thrust"
    else:
        unc = "1σ: " + ", ".join(f"{FACTOR_LABEL[k]} ±{100 * v:g} %" for k, v in sig.items())
    return f"{d['aircraft']} · {unc} · {len(d['errors']):,} draws"


def _surface(d: dict):
    """The response surface, shifted so it returns the exact nominal at (1, 1, 1): the fit's
    small error (a few ft) should not show as a difference at the nominal point."""
    surf = d.get("surface") or {}
    if not surf:
        return None
    nom = d["nominal"][d["main_output"]]
    off = nom - float(predict_surface(surf, 1.0, 1.0, 1.0))
    return lambda a, b, c: predict_surface(surf, a, b, c) + off


def probability_ok(d: dict, runway_ft: float) -> float:
    """Share of draws for which this runway is enough (no-solution draws never are)."""
    x = values(d, d["main_output"])
    return float(np.mean(x <= runway_ft)) if len(x) else math.nan


def curve_keys(d: dict) -> list[str]:
    """Takeoff and landing curves; plus 'runway required' only when neither always governs."""
    keys = [k for k in ("takeoff_field_ft", "landing_runway_ft") if k in d["values"]]
    if d["main_output"] == "runway_required_ft" and len(keys) == 2:
        to, ld = values(d, keys[0]), values(d, keys[1])
        if not (np.all(to >= ld) or np.all(ld > to)):
            keys.insert(0, "runway_required_ft")
    return keys


# ------------------------------------------------------------------------------------
# 1. the answer: extra runway against confidence
# ------------------------------------------------------------------------------------
def margin_curve(d: dict, avail: float | None = None) -> go.Figure:
    keys = curve_keys(d)
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
            hovertemplate=(f"<b>{OUT_LABEL[key]}</b> · %{{customdata[0]:.1f}} %<br>"
                           "%{y:+,.0f} ft → %{customdata[1]:,.0f} ft<extra></extra>"),
        )  # fmt: skip
        for p in (0.95, 0.99):
            e = quantile_ci_inf(x, p)[0]
            if p <= p_max and math.isfinite(e):
                fig.add_scatter(x=[_ND.inv_cdf(p)], y=[e - nom], mode="markers+text",
                                marker={"size": 9, "color": "white",
                                        "line": {"color": c, "width": 2}},
                                text=[f"{e - nom:+,.0f}"], textposition="top left",
                                textfont={"color": INK, "size": 12}, hoverinfo="skip",
                                showlegend=False)  # fmt: skip
    fig.add_scatter(x=[None], y=[None], mode="markers", name="sampling 95 % CI",
                    marker={"symbol": "square", "size": 12, "color": _rgba(INK, 0.12)})  # fmt: skip
    f = d["failure_rate"]
    if f > 0 and 1 - f < p_max:
        zf = _ND.inv_cdf(max(1 - f, 0.5001))
        fig.add_vrect(x0=zf, x1=_ND.inv_cdf(p_max), fillcolor=NO_GO, line_width=0)
        fig.add_annotation(x=zf, y=1, yref="paper", xanchor="left", yanchor="top", xshift=6,
                           showarrow=False, align="left", font={"color": BFL_C, "size": 12},
                           text=f"<b>no runway is enough</b><br>{100 * f:.0f} % of draws: "
                           "no takeoff")  # fmt: skip
    nom_main = d["nominal"][d["main_output"]]
    if avail is not None and math.isfinite(avail):
        p_ok = probability_ok(d, avail)
        fig.add_hline(y=avail - nom_main, line={"color": INK, "width": 1.5, "dash": "dash"})
        if 0.5 <= p_ok <= p_max:
            fig.add_scatter(x=[_ND.inv_cdf(p_ok)], y=[avail - nom_main], mode="markers",
                            marker={"size": 13, "color": INK, "symbol": "star"},
                            showlegend=False, hoverinfo="skip")  # fmt: skip
        fig.add_annotation(x=0, xref="paper", y=avail - nom_main, xanchor="left", yanchor="bottom",
                           showarrow=False, font={"color": INK, "size": 12},
                           text=f"<b>your runway {avail:,.0f} ft</b> · enough "
                           f"{100 * p_ok:.0f} %")  # fmt: skip
    fig.add_hline(y=0, line={"color": MUTED, "width": 1, "dash": "dot"})
    ticks = [p for p in COVER_TICKS if p <= p_max + 1e-9]
    fig.update_xaxes(tickvals=[_ND.inv_cdf(p) for p in ticks],
                     ticktext=[f"{100 * p:g} %" for p in ticks], title="confidence")  # fmt: skip
    fig.update_yaxes(title="extra runway [ft]", tickformat="+,")
    x = values(d, d["main_output"])
    e95 = quantile_ci_inf(x, 0.95)[0] - nom_main
    title = (f"+{e95:,.0f} ft of runway for 95 % confidence" if math.isfinite(e95)
             else "No runway gives 95 % confidence")  # fmt: skip
    return _layout(fig, title, f"{_subtitle(d)} · nominal {nom_main:,.0f} ft", 440)


# ------------------------------------------------------------------------------------
# 2. equal error, unequal effect: the tornado (exact one-at-a-time solves)
# ------------------------------------------------------------------------------------
def _oat(d: dict, step: float) -> dict[str, tuple[float, float]]:
    """factor -> (runway change with that table `step` worse, `step` better); inf = no takeoff."""
    out: dict[str, list[float]] = {}
    for r in d.get("oat") or []:
        if abs(abs(r["change"]) - step) > 1e-9:
            continue
        v = math.inf if r["delta"] is None else r["delta"]
        slot = 0 if np.sign(r["change"]) == WORSE[r["factor"]] else 1
        out.setdefault(r["factor"], [math.nan, math.nan])[slot] = v
    return {k: (v[0], v[1]) for k, v in out.items()}


def _swing(w: float, b: float) -> float:
    return math.inf if math.isinf(w) or math.isinf(b) else (abs(w) + abs(b)) / 2


def tornado_title(d: dict, step: float) -> str:
    oat = _oat(d, step)
    if not oat:
        return ""
    pct = f"{100 * step:g} %"
    dead = [FACTOR_LABEL[k] for k, (w, b) in oat.items() if math.isinf(w) or math.isinf(b)]
    if dead:
        who = dead[0] if len(dead) == 1 else ", ".join(dead[:-1]) + " or " + dead[-1]
        return f"{pct} worse {who} alone: no takeoff"
    sw = sorted(((_swing(*v), k) for k, v in oat.items()), reverse=True)
    (s1, k1), (s3, k3) = sw[0], sw[-1]
    if s3 <= 0:
        return f"Same {pct} error: {FACTOR_LABEL[k1]} matters most"
    ratio = s1 / s3
    if len(sw) == 3 and sw[1][0] > 0.75 * s1:
        lead = f"{FACTOR_LABEL[k1]} and {FACTOR_LABEL[sw[1][1]]} matter"
        ratio = (s1 + sw[1][0]) / 2 / s3
    else:
        lead = f"{FACTOR_LABEL[k1]} matters"
    return f"Same {pct} error: {lead} {ratio:.0f}× more than {FACTOR_LABEL[k3]}"


def tornado(d: dict, step: float = 0.05) -> go.Figure:
    oat = _oat(d, step)
    if not oat:
        return empty("No one-at-a-time solves in this result")
    pct = f"{100 * step:g} %"
    order = sorted(oat, key=lambda k: (_swing(*oat[k]), abs(oat[k][1])))  # biggest on top
    fin = [abs(v) for k in order for v in oat[k] if math.isfinite(v)]
    edge = 1.25 * max(fin + [1.0])
    fig = go.Figure()
    for slot, name, c in ((0, f"{pct} pessimistic", PESS_C), (1, f"{pct} optimistic", OPT_C)):
        xs, txt, pat, hov = [], [], [], []
        for k in order:
            v = oat[k][slot]
            sign = WORSE[k] if slot == 0 else -WORSE[k]
            ch = f"{FACTOR_LABEL[k]} {'+' if sign > 0 else '−'}{pct}"
            if math.isinf(v):
                xs.append(edge if v > 0 else -edge)
                txt.append("<b>no takeoff</b>")
                pat.append("/")
                hov.append(f"{ch}: no engine-out takeoff")
            else:
                xs.append(v)
                txt.append(f"{v:+,.0f} ft".replace("-", "−"))
                pat.append("")
                hov.append(f"{ch}: {v:+,.0f} ft")
        fig.add_bar(y=[FACTOR_LABEL[k] for k in order], x=xs, orientation="h", name=name,
                    marker={"color": c, "pattern": {"shape": pat, "fgcolor": "white",
                                                    "solidity": 0.3},
                            "line": {"width": 0}, "cornerradius": 4},
                    text=txt, textposition="outside", cliponaxis=False,
                    textfont={"color": INK, "size": 13}, hovertext=hov,
                    hovertemplate="%{hovertext}<extra></extra>")  # fmt: skip
    fig.add_vline(x=0, line={"color": INK, "width": 1.2})
    fig.update_layout(barmode="overlay", bargap=0.38)
    fig.update_xaxes(title="runway change [ft]", tickformat="+,", range=[-edge * 1.3, edge * 1.3])
    fig.update_yaxes(tickfont={"size": 14}, gridcolor="rgba(0,0,0,0)")
    sub = (f"{d['aircraft']} · one table off by ±{pct}, the others exact · "
           "pessimistic = less lift or thrust, more drag")  # fmt: skip
    fig = _layout(fig, tornado_title(d, step), sub, 300)
    fig.update_layout(legend={"y": -0.28})
    return fig


# ------------------------------------------------------------------------------------
# 3. the profiler: runway against each multiplier, the others held at the slider values
# ------------------------------------------------------------------------------------
def profiler(d: dict, sel: dict[str, float], avail: float | None = None) -> go.Figure:
    surf, fail = d.get("surface") or {}, d.get("failure_model") or {}
    if not surf:
        return empty("Too few draws solved to fit a response surface")
    sig = _sigmas(d)
    key = d["main_output"]
    nom = d["nominal"][key]
    order = list(FACTOR_C)
    fig = make_subplots(1, 3, shared_yaxes=True, horizontal_spacing=0.035,
                        subplot_titles=[FACTOR_LABEL[k] for k in order])  # fmt: skip
    rs = _surface(d)
    here = float(rs(sel["k_CL"], sel["k_CD"], sel["k_T"]))
    p_here = float(predict_failure(fail, sel["k_CL"], sel["k_CD"], sel["k_T"]))
    ys = []
    for j, k in enumerate(order, 1):
        v = sig[k] if sig[k] > 0 else 0.0
        xs = np.linspace(1 - 3 * v, 1 + 3 * v, 121) if v > 0 else np.array([0.999, 1.001])
        args = {kk: (xs if kk == k else np.full_like(xs, sel[kk])) for kk in order}
        y = rs(args["k_CL"], args["k_CD"], args["k_T"])
        pf = predict_failure(fail, args["k_CL"], args["k_CD"], args["k_T"])
        good = pf < 0.5
        ys.append(y[good])
        fig.add_scatter(x=xs, y=np.where(good, y, np.nan), mode="lines", row=1, col=j,
                        line={"color": FACTOR_C[k], "width": 3}, showlegend=False,
                        hovertemplate=FACTOR_LABEL[k] + " ×%{x:.3f}: %{y:,.0f} ft"
                        + "<extra></extra>")  # fmt: skip
        if (~good).any():
            xb = xs[~good]
            fig.add_vrect(x0=float(xb.min()), x1=float(xb.max()), fillcolor=NO_GO,
                          line_width=0, row=1, col=j, annotation_text="no takeoff",
                          annotation_position="bottom left",
                          annotation_font={"color": BFL_C, "size": 11})  # fmt: skip
        fig.add_vline(x=sel[k], line={"color": INK, "width": 1, "dash": "dot"}, row=1, col=j)
        if p_here < 0.5:
            fig.add_scatter(x=[sel[k]], y=[here], mode="markers", row=1, col=j,
                            marker={"size": 12, "color": "white",
                                    "line": {"color": INK, "width": 2.5}},
                            showlegend=False, hoverinfo="skip")  # fmt: skip
        fig.update_xaxes(tickformat=".2f", row=1, col=j)
    allv = np.concatenate([v for v in ys if len(v)] + [[nom]])
    lo, hi = float(allv.min()), float(allv.max())
    if avail is not None and math.isfinite(avail) and avail < hi + 0.3 * (hi - lo):
        hi = max(hi, avail)
        fig.add_hline(y=avail, line={"color": INK, "width": 1.5, "dash": "dash"})
        fig.add_annotation(x=1, xref="x3 domain", y=avail, yanchor="top", xanchor="right",
                           text="your runway", showarrow=False,
                           font={"size": 11, "color": INK})  # fmt: skip
    pad = 0.06 * (hi - lo + 1)
    fig.update_yaxes(range=[lo - pad, hi + pad], title="runway [ft]", tickformat=",", col=1)
    fig.add_hline(y=nom, line={"color": MUTED, "width": 1, "dash": "dot"})
    fig.update_annotations(font={"size": 13, "color": INK})
    fig.add_annotation(
        x=1,
        xref="x3 domain",
        y=nom,
        yanchor="top",
        xanchor="right",
        text="nominal",
        showarrow=False,
        font={"size": 11, "color": MUTED},
    )
    if p_here >= 0.5:
        title = "No takeoff at this combination"
    else:
        title = f"{here:,.0f} ft  ({here - nom:+,.0f} ft)"
    point = " · ".join(f"{FACTOR_LABEL[k]} ×{sel[k]:.3f}" for k in order)
    sub = f"{point} · fit to the draws, ±{surf['loo_rms_ft']:.0f} ft"
    fig = _layout(fig, title, sub, 330)
    fig.update_layout(margin={"t": 92}, hovermode="closest")
    return fig


# ------------------------------------------------------------------------------------
# 4. the cliff map: runway over the two tables that matter most
# ------------------------------------------------------------------------------------
def map_factors(d: dict) -> list[str]:
    """The two uncertain tables with the biggest equal-error effect."""
    sig = _sigmas(d)
    oat = _oat(d, 0.05)
    cand = [k for k in FACTOR_C if sig[k] > 0]
    cand.sort(key=lambda k: -_swing(*oat.get(k, (0.0, 0.0))))
    return sorted(cand[:2], key=list(FACTOR_C).index)


def cliff_map(d: dict, avail: float | None = None) -> go.Figure:
    surf, fail = d.get("surface") or {}, d.get("failure_model") or {}
    pair = map_factors(d)
    if not surf or len(pair) < 2:
        return empty("Needs two tables with a non-zero uncertainty")
    a, b = pair
    held = next(k for k in FACTOR_C if k not in pair)
    sig = _sigmas(d)
    ga = np.linspace(-3.3 * sig[a], 3.3 * sig[a], 121)
    gb = np.linspace(-3.3 * sig[b], 3.3 * sig[b], 121)
    A, B = np.meshgrid(ga, gb)
    k = {a: 1 + A, b: 1 + B, held: np.ones_like(A)}
    Z = _surface(d)(k["k_CL"], k["k_CD"], k["k_T"])
    PF = predict_failure(fail, k["k_CL"], k["k_CD"], k["k_T"])
    bad = PF >= 0.5
    Zm = np.where(bad, np.nan, Z)
    nom = d["nominal"][d["main_output"]]
    fig = go.Figure()
    fig.add_contour(x=100 * ga, y=100 * gb, z=Zm, colorscale="Blues", ncontours=14,
                    contours={"coloring": "heatmap", "showlabels": True, "labelformat": ",.0f",
                              "labelfont": {"size": 11, "color": "rgba(15,29,43,0.75)"}},
                    line={"width": 0.6, "color": "rgba(255,255,255,0.6)"},
                    colorbar={"title": {"text": "runway [ft]", "side": "right"},
                              "tickformat": ",", "thickness": 14, "len": 0.9},
                    hovertemplate=(f"{FACTOR_LABEL[a]} %{{x:+.1f}} %<br>{FACTOR_LABEL[b]} "
                                   "%{y:+.1f} %<br>%{z:,.0f} ft<extra></extra>"),
                    connectgaps=False, name="runway", showlegend=False)  # fmt: skip
    if bad.any():
        fig.add_heatmap(
            x=100 * ga,
            y=100 * gb,
            z=np.where(bad, 1.0, np.nan),
            colorscale=[[0, NO_GO], [1, NO_GO]],
            showscale=False,
            hoverinfo="skip",
        )
        fig.add_contour(x=100 * ga, y=100 * gb, z=PF, showscale=False, hoverinfo="skip",
                        contours={"start": 0.5, "end": 0.5, "coloring": "lines"},
                        colorscale=[[0, BFL_C], [1, BFL_C]],
                        line={"width": 2.5})  # fmt: skip
        dist = np.where(bad, np.hypot(A / sig[a], B / sig[b]), np.inf)
        ia = np.unravel_index(np.argmin(dist), A.shape)
        far = np.unravel_index(np.argmax(np.where(bad, dist, -np.inf)), A.shape)
        fig.add_annotation(x=100 * A[far], y=100 * B[far], text="<b>no takeoff</b>",
                           showarrow=False, font={"color": BFL_C, "size": 13},
                           xanchor="left" if A[far] < 0 else "right",
                           yanchor="bottom" if B[far] < 0 else "top")  # fmt: skip
        title = f"The no-takeoff cliff is {dist[ia]:.1f}σ from nominal"
    else:
        title = f"No cliff within ±3σ of {FACTOR_LABEL[a]} and {FACTOR_LABEL[b]}"
    if avail is not None and math.isfinite(avail) and np.nanmin(Zm) < avail < np.nanmax(Zm):
        fig.add_contour(x=100 * ga, y=100 * gb, z=Zm, showscale=False, hoverinfo="skip",
                        contours={"start": avail, "end": avail, "coloring": "lines",
                                  "showlabels": True, "labelformat": ",.0f",
                                  "labelfont": {"size": 12, "color": INK}},
                        colorscale=[[0, INK], [1, INK]],
                        line={"width": 3}, name="your runway",
                        showlegend=True)  # fmt: skip
    t = np.linspace(0, 2 * math.pi, 120)
    for p, dash in ((0.5, "dot"), (0.95, "dash")):
        rr = math.sqrt(-2 * math.log(1 - p))
        fig.add_scatter(x=100 * rr * sig[a] * np.cos(t), y=100 * rr * sig[b] * np.sin(t),
                        mode="lines", line={"color": INK, "width": 1.6, "dash": dash},
                        name=f"{100 * p:g} % of draws", hoverinfo="skip")  # fmt: skip
    x_fail = values(d, d["main_output"])
    if (~np.isfinite(x_fail)).any():
        fa = 100 * (np.asarray(d["factors"][a]) - 1)[~np.isfinite(x_fail)]
        fb = 100 * (np.asarray(d["factors"][b]) - 1)[~np.isfinite(x_fail)]
        fig.add_scatter(x=fa, y=fb, mode="markers", name="draws with no takeoff",
                        marker={"symbol": "x-thin", "size": 6, "opacity": 0.7,
                                "line": {"width": 1.5, "color": BFL_C}},
                        hoverinfo="skip")  # fmt: skip
    fig.add_scatter(x=[0], y=[0], mode="markers+text", text=[f"nominal {nom:,.0f} ft"],
                    textposition="bottom right", textfont={"size": 12, "color": INK},
                    marker={"size": 11, "color": "white", "line": {"color": INK, "width": 2.5}},
                    showlegend=False, hoverinfo="skip")  # fmt: skip
    fig.update_xaxes(title=f"{FACTOR_LABEL[a]} error", ticksuffix=" %", tickformat="+",
                     range=[100 * ga[0], 100 * ga[-1]], showgrid=False)  # fmt: skip
    fig.update_yaxes(title=f"{FACTOR_LABEL[b]} error", ticksuffix=" %", tickformat="+",
                     range=[100 * gb[0], 100 * gb[-1]], showgrid=False)  # fmt: skip
    sub = (f"{d['aircraft']} · the two tables that matter most; {FACTOR_LABEL[held]} exact · "
           "fit to the draws")  # fmt: skip
    fig = _layout(fig, title, sub, 470)
    fig.update_layout(legend={"y": -0.17})
    return fig


# ------------------------------------------------------------------------------------
# method checks (collapsed on the page)
# ------------------------------------------------------------------------------------
def convergence(d: dict, p: float = 0.95) -> go.Figure:
    """The P95 estimate as draws accumulate, with its 95 % confidence band."""
    key = d["main_output"]
    x = values(d, key)
    nom = d["nominal"][key]
    c = COLORS["takeoff_field_ft"]
    ns = np.unique(np.linspace(20, len(x), 60).astype(int))
    q = np.array([quantile_ci_inf(x[:n], p) for n in ns]) - nom
    fin = np.isfinite(q[:, 0])
    fig = go.Figure()
    fig.add_scatter(x=list(ns[fin]) + list(ns[fin][::-1]),
                    y=list(np.where(np.isfinite(q[fin, 2]), q[fin, 2], np.nan))
                    + list(q[fin, 1][::-1]),
                    fill="toself", fillcolor=_rgba(c, 0.15), line={"width": 0},
                    hoverinfo="skip", name="95 % CI")  # fmt: skip
    fig.add_scatter(x=ns[fin], y=q[fin, 0], mode="lines", name="P95 estimate",
                    line={"color": c, "width": 2.5},
                    hovertemplate="%{x} draws: %{y:+,.0f} ft<extra></extra>")  # fmt: skip
    ticks = [t for t in (20, 50, 100, 200, 500, 1000, 2000) if t <= len(d["errors"])]
    fig.update_xaxes(title="draws", type="log", tickvals=ticks,
                     ticktext=[f"{t:,}" for t in ticks])  # fmt: skip
    fig.update_yaxes(title="P95 extra runway [ft]", tickformat="+,")
    f = q[-1]
    title = (f"Sampling error ±{(f[2] - f[1]) / 2:,.0f} ft" if np.isfinite(f).all()
             else "Sampling error of the P95")  # fmt: skip
    fig = _layout(fig, title, "P95 as the draws come in", 300)
    fig.update_layout(legend={"y": -0.32})
    return fig


def inputs(d: dict) -> go.Figure:
    """The drawn factors against the intended normal distributions (common y scale)."""
    sig = _sigmas(d)
    fig = make_subplots(1, 3, horizontal_spacing=0.05, shared_yaxes=True,
                        subplot_titles=[f"{FACTOR_LABEL[k]} ±{100 * sig[k]:g} %"
                                        for k in FACTOR_C])  # fmt: skip
    for j, k in enumerate(FACTOR_C, 1):
        xk = 100 * (np.asarray(d["factors"][k]) - 1.0)
        if sig[k] <= 0:
            continue
        s = 100 * sig[k]
        fig.add_histogram(x=xk, xbins={"start": -3 * s, "end": 3 * s, "size": s / 4},
                          histnorm="probability density", row=1, col=j,
                          marker={"color": FACTOR_C[k], "line": {"color": "white", "width": 1}},
                          opacity=0.7, showlegend=False)  # fmt: skip
        xs = np.linspace(-3 * s, 3 * s, 200)
        pdf = np.exp(-0.5 * (xs / s) ** 2) / (s * math.sqrt(2 * math.pi))
        fig.add_scatter(x=xs, y=pdf, mode="lines", line={"color": INK, "width": 1.6},
                        showlegend=j == 1, name="target normal", row=1, col=j)  # fmt: skip
        fig.update_xaxes(ticksuffix=" %", tickformat="+", row=1, col=j)
    fig.update_yaxes(title="density", col=1)
    fig.update_annotations(font={"size": 13, "color": INK})
    meth = "Latin hypercube" if d["settings"]["method"] == "lhs" else "Monte Carlo"
    fig = _layout(fig, "Draws vs target", f"{meth} · {len(d['errors']):,} draws", 300)
    fig.update_layout(margin={"t": 92}, legend={"y": -0.2})
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
                        hovertemplate=FACTOR_LABEL[k] + " ×%{x:.3f}<extra></extra>")  # fmt: skip
    fig.add_vline(x=1, line={"color": MUTED, "width": 1, "dash": "dot"})
    fig.update_xaxes(title="multiplier on the table", tickformat=".2f")
    fig.update_yaxes(title="density", rangemode="tozero")
    fig = _layout(fig, "", "", 230)
    fig.update_layout(title=None, margin={"t": 10, "b": 44, "l": 50, "r": 12},
                      legend={"orientation": "v", "y": 1, "x": 1.0, "xanchor": "right",
                              "bgcolor": "rgba(255,255,255,0.8)"})  # fmt: skip
    return fig


__all__ = [
    "sigma_curves", "profiler", "tornado", "tornado_title", "cliff_map", "margin_curve",
    "convergence", "inputs", "values", "probability_ok", "curve_keys", "map_factors",
    "OUT_LABEL", "FACTOR_LABEL",
]  # fmt: skip
