"""Data uncertainty page: how much runway to plan when the lift, drag and thrust tables
are only known to within some percentage (bfl.uncertainty).

A side analysis like the gust page: nothing here feeds the simulator or the trade study.
The user states a 1-sigma uncertainty for each table (presets are starting points); each
draw is a full solve; the page answers with the runway that gives 90/95/99 % confidence
and shows which table's uncertainty matters.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict

import numpy as np
import pandas as pd
from dash import Input, Output, State, dcc, html, no_update

from bfl.uncertainty import PRESETS, UncertaintySettings, quantile_ci_inf

from . import compute, loading, unc_figures
from .gust_figures import COLORS
from .gust_page import _field, _graph, _seg
from .trade import RUNWAY_PRESETS, _base_cfg, _num

RUN_COUNTS = (200, 500, 1000, 2000)
COVERAGE = (0.90, 0.95, 0.99)
TABLES = (("un-cl", "Lift (CL)", "sigma_CL"), ("un-cd", "Drag (CD)", "sigma_CD"),
          ("un-t", "Thrust", "sigma_T"))  # fmt: skip


def _sigma_input(id_: str, label: str, value: float) -> html.Div:
    return html.Div(
        className="tr-field un-sig",
        children=[
            html.Label([label, html.Span(" 1σ, %", className="sym")]),
            dcc.Input(
                id=id_,
                type="number",
                value=value,
                min=0,
                step=0.5,
                debounce=True,
                className="num-input",
            ),  # fmt: skip
            html.Div(id=f"{id_}-hint", className="hint"),
        ],
    )


def layout() -> html.Div:
    p0 = PRESETS["typical"]
    return html.Div(
        className="gust-page",
        children=[
            html.Div(
                className="card",
                children=[
                    html.H2("Data uncertainty"),
                    dcc.Markdown(
                        "How much runway to plan when the **lift, drag and thrust tables are "
                        "only known to within some percentage** (e.g. CFD and NPSS output "
                        "without error bars). State how far off each table might be, as a "
                        "1σ percentage: about 68 % of the time within ±1σ, 95 % within ±2σ. "
                        "Each draw multiplies the tables by random factors with that spread and "
                        "runs a full solve. The answer: the runway that is enough with 90, 95 "
                        "or 99 % confidence, and which table's uncertainty drives it. A side "
                        "analysis: used nowhere else in the tool.",
                        className="hint",
                    ),
                    html.Div(id="un-base", className="trade-base"),
                ],
            ),
            html.Div(
                className="card gu-setup",
                children=[
                    html.Div(
                        className="gu-bar",
                        children=[
                            _field(
                                "Aircraft",
                                dcc.Dropdown(id="un-aircraft", clearable=False, searchable=False),
                            ),  # fmt: skip
                            _field(
                                "Confidence in the data",
                                dcc.Dropdown(
                                    id="un-preset",
                                    value="typical",
                                    clearable=False,
                                    searchable=False,
                                    style={"minWidth": "220px"},
                                    options=[
                                        {"label": v["label"], "value": k}
                                        for k, v in PRESETS.items()
                                    ]
                                    + [{"label": "Custom (type below)", "value": "custom"}],
                                ),
                                "starting points (judgement, not a standard)",
                            ),  # fmt: skip
                            *[_sigma_input(i, lab, 100 * p0[k]) for i, lab, k in TABLES],
                            _field(
                                "Operations",
                                dcc.Checklist(
                                    id="un-landing",
                                    value=["on"],
                                    className="checks",
                                    options=[{"label": " include landing", "value": "on"}],
                                ),
                            ),  # fmt: skip
                            _field("Draws", _seg("un-n", 500, [(n, f"{n:,}") for n in RUN_COUNTS])),
                            html.Button(
                                "Run", id="un-run", n_clicks=0, className="btn btn-primary gu-run"
                            ),  # fmt: skip
                        ],
                    ),
                    html.Details(
                        className="tr-over",
                        children=[
                            html.Summary("Conditions (blank = from the simulator)"),
                            html.Div(
                                className="gu-row",
                                children=[
                                    _num("un-weight", "Takeoff weight", None, 1000, unit="lbf"),
                                    _num("un-temp", "Temperature", None, 1, unit="°F"),
                                    _num("un-elev", "Elevation", None, 100, unit="ft"),
                                    _num("un-wind", "Headwind (− tail)", None, 1, unit="kt"),
                                    html.Div(
                                        className="tr-field",
                                        children=[
                                            html.Label("Runway condition"),
                                            dcc.Dropdown(
                                                id="un-cond",
                                                value="",
                                                clearable=False,
                                                searchable=False,
                                                options=[{"label": "inherit", "value": ""}]
                                                + [
                                                    {"label": v[0], "value": k}
                                                    for k, v in RUNWAY_PRESETS.items()
                                                ],
                                            ),
                                        ],
                                    ),  # fmt: skip
                                ],
                            ),
                        ],
                    ),
                    html.Details(
                        className="tr-over",
                        children=[
                            html.Summary("Sampling"),
                            html.Div(
                                className="gu-row",
                                children=[
                                    _field(
                                        "Method",
                                        _seg(
                                            "un-method",
                                            "lhs",
                                            [("lhs", "Latin hypercube"), ("mc", "Monte Carlo")],
                                        ),
                                    ),  # fmt: skip
                                    _num("un-seed", "Random seed", 1, 1, "", spin=True),
                                    _num("un-trunc", "Cut draws at ±", 3.0, 0.5, "", unit="σ"),
                                ],
                            ),
                            html.Div(
                                "Draws are independent normal factors on each table, centred on "
                                "1 (the tables as they are), cut at ±3σ. Latin hypercube covers "
                                "each input evenly: it makes the average answer almost exact "
                                "(about 20× steadier here), but the 95 % point depends on rare "
                                "combinations and still needs many draws.",
                                className="hint",
                            ),
                        ],
                    ),
                    html.Div(id="un-status", className="hint"),
                ],
            ),
            loading.loading(
                [html.Div(id="un-results"), dcc.Store(id="un-result")],
                "Solving the draws…",
                220,
            ),
            dcc.Store(id="un-other"),
            dcc.Download(id="un-dl-csv"),
            dcc.Download(id="un-dl-txt"),
        ],
    )


# ------------------------------------------------------------------------------------
# results
# ------------------------------------------------------------------------------------
def _card(d: dict, key: str, p: float) -> html.Div:
    x = unc_figures.values(d, key)
    nom = d["nominal"][key]
    est, lo, hi = quantile_ci_inf(x, p)
    pct = round(100 * p)
    if math.isfinite(est):
        big = f"{est:,.0f} ft"
        delta = (
            f"{est - nom:+,.0f} ft ({100 * (est / nom - 1):+.1f} %) over the nominal {nom:,.0f} ft"
        )
        ci = (f"{pct} % confident · estimate's 95 % range {lo:,.0f}–"
              + (f"{hi:,.0f} ft" if math.isfinite(hi) else "no limit"))  # fmt: skip
    else:
        big, delta = "no runway", f"too many draws cannot take off (nominal {nom:,.0f} ft)"
        ci = f"at most {100 * float(np.mean(np.isfinite(x))):.0f} % confidence is possible"
    return html.Div(
        className="gu-card",
        children=[
            html.Div(
                [
                    html.Span(className="swatch", style={"background": COLORS[key]}),
                    unc_figures.OUT_LABEL[key],
                ],
                className="m-label",
            ),  # fmt: skip
            html.Div(big, className="m-value"),
            html.Div(delta, className="gu-delta"),
            html.Div(ci, className="hint"),
        ],
    )


def answer(d: dict, p: float) -> list:
    key = d["main_output"]
    x = unc_figures.values(d, key)
    nom = d["nominal"][key]
    est = quantile_ci_inf(x, p)[0]
    f = d["failure_rate"]
    if math.isfinite(est):
        rel = 100 * (est / nom - 1)
        sentence = (f"With this confidence in the data, {est:,.0f} ft of runway is enough with "
                    f"{round(100 * p)} % confidence: {est - nom:+,.0f} ft ({rel:+.1f} %) over "
                    f"the nominal {nom:,.0f} ft.")  # fmt: skip
    else:
        sentence = (f"No runway gives {round(100 * p)} % confidence: in {100 * f:.0f} % of the "
                    "draws the aircraft cannot complete an engine-out takeoff at all (the data "
                    "would have to be this optimistic for it to work).")  # fmt: skip
    sens = d.get("sensitivity") or []
    if sens:
        top = max(sens, key=lambda r: r["variance_share"])
        sentence += (f" The {unc_figures.FACTOR_LABEL[top['factor']]} table drives "
                     f"{100 * top['variance_share']:.0f} % of the spread.")  # fmt: skip
    keys = [k for k in ("runway_required_ft", "takeoff_field_ft", "landing_runway_ft")
            if k in d["values"]]  # fmt: skip
    if "runway_required_ft" in keys:
        to = unc_figures.values(d, "takeoff_field_ft")
        ld = unc_figures.values(d, "landing_runway_ft")
        if np.all(to >= ld) or np.all(ld > to):  # one operation always governs
            keys.remove("runway_required_ft")
    notes = []
    if f > 0:
        drv = ", ".join(f"{unc_figures.FACTOR_LABEL[k]} {v:+.1f}σ"
                        for k, v in d["failure_drivers"].items())  # fmt: skip
        notes.append(f"{100 * f:.1f} % of draws have no takeoff solution (counted as needing more "
                     f"runway than any length); on average they have {drv}.")  # fmt: skip
    return [
        html.Div(
            className="gu-answer-head",
            children=[
                html.H3("Answer"),
                html.Div(className="spacer"),
                html.Span("Confidence", className="ctl-name"),
                _seg("un-cover", p, [(c, f"{round(100 * c)} %") for c in COVERAGE]),
            ],
        ),
        html.P(sentence, className="gu-sentence"),
        html.Div([_card(d, k, p) for k in keys], className="gu-cards"),
        *[html.Div(n, className="hint") for n in notes],
        html.Div(
            className="dl-row",
            children=[
                html.Button(
                    "⤓ Download draws (CSV)", id="un-dl-csv-btn", n_clicks=0, className="btn"
                ),  # fmt: skip
                html.Button(
                    "⤓ Download summary", id="un-dl-txt-btn", n_clicks=0, className="btn"
                ),  # fmt: skip
                html.Span(
                    f"{len(d['errors']):,} draws in {d['time_s']:.1f} s · camera icon on a "
                    "chart: PNG for slides",
                    className="hint",
                ),  # fmt: skip
            ],
        ),
    ]


def results(d: dict, p: float) -> list:
    other = "Monte Carlo" if d["settings"]["method"] == "lhs" else "Latin hypercube"
    return [
        html.Div(id="un-answer", className="card", children=answer(d, p)),
        html.Div(className="card", children=[_graph("un-fig-margin", "confidence")]),
        html.Div(className="card", children=[_graph("un-fig-sens", "which_data")]),
        html.Div(className="card", children=[_graph("un-fig-scatter", "draws")]),
        html.Div(className="card", children=[_graph("un-fig-dist", "spread")]),
        html.Div(
            className="card",
            children=[
                html.H3("How reliable are these numbers?"),
                dcc.Markdown(
                    "The answer is a percentile of N draws, so it carries **sampling error** "
                    "of about 1/√N (the shaded bands). The draws themselves are shown against "
                    "the intended distributions. Compare with the other sampling method: Latin "
                    "hypercube pins down the average, but for the 95 % point the two are about "
                    "equally uncertain, so more draws is what helps. Methods › Sampling: Monte "
                    "Carlo and Latin hypercube explains why.",
                    className="hint",
                ),
                _graph("un-fig-conv", "sampling"),
                html.Button(
                    f"Compare with {other} (same draws count)",
                    id="un-other-btn",
                    n_clicks=0,
                    className="btn",
                ),  # fmt: skip
                _graph("un-fig-inputs", "inputs"),
            ],
        ),
    ]


def _settings(sig_cl, sig_cd, sig_t, landing, n, method, seed, trunc) -> UncertaintySettings:
    return UncertaintySettings(
        sigma_CL=max(float(sig_cl or 0), 0) / 100, sigma_CD=max(float(sig_cd or 0), 0) / 100,
        sigma_T=max(float(sig_t or 0), 0) / 100, landing="on" in (landing or []), n=int(n),
        method=method, seed=int(seed or 1), truncate=float(trunc or 3.0),
    )  # fmt: skip


def register(app, aircraft_options) -> None:
    @app.callback(
        Output("un-aircraft", "options"),
        Output("un-aircraft", "value"),
        Input("un-aircraft", "id"),
        State("aircraft", "value"),
    )
    def on_open(_id, sim_aircraft):
        opts = aircraft_options()
        vals = [o["value"] for o in opts]
        return opts, sim_aircraft if sim_aircraft in vals else (vals[0] if vals else None)

    @app.callback(
        Output("un-base", "children"),
        Input("un-aircraft", "value"),
        State("current", "data"),
    )
    def on_base(name, cur):
        if not name:
            return ""
        cfg, src = _base_cfg(name, cur)
        e, m = cfg.environment, cfg.multipliers
        temp = f"{e.temperature_F:g} °F" if e.temperature_F is not None else "ISA"
        mult = ""
        if (m.k_CL, m.k_CD, m.k_T) != (1.0, 1.0, 1.0):
            mult = f", multipliers k_CL {m.k_CL:g} k_CD {m.k_CD:g} k_T {m.k_T:g} (the nominal)"
        return (f"Conditions from {src}: {cfg.aircraft.name}, {cfg.weight_lbf:,.0f} lb, {temp}, "
                f"{e.elevation_ft:,.0f} ft, wind {e.headwind_kts:+g} kt{mult}.")  # fmt: skip

    @app.callback(
        Output("un-cl", "value"),
        Output("un-cd", "value"),
        Output("un-t", "value"),
        Input("un-preset", "value"),
        prevent_initial_call=True,
    )
    def on_preset(key):
        if key not in PRESETS:
            return no_update, no_update, no_update
        p = PRESETS[key]
        return 100 * p["sigma_CL"], 100 * p["sigma_CD"], 100 * p["sigma_T"]

    for id_, _, _ in TABLES:

        @app.callback(Output(f"{id_}-hint", "children"), Input(id_, "value"))
        def on_hint(v):
            if v is None:
                return ""
            return f"95 % of draws within ±{2 * float(v):g} %"

    @app.callback(
        Output("un-result", "data"),
        Output("un-status", "children"),
        Output("un-other", "data", allow_duplicate=True),
        Input("un-run", "n_clicks"),
        State("un-aircraft", "value"),
        State("un-cl", "value"),
        State("un-cd", "value"),
        State("un-t", "value"),
        State("un-landing", "value"),
        State("un-n", "value"),
        State("un-weight", "value"),
        State("un-temp", "value"),
        State("un-elev", "value"),
        State("un-wind", "value"),
        State("un-cond", "value"),
        State("un-method", "value"),
        State("un-seed", "value"),
        State("un-trunc", "value"),
        State("current", "data"),
        prevent_initial_call=True,
    )
    def on_run(_n, name, s_cl, s_cd, s_t, landing, n, weight, temp, elev, wind, cond, method,
               seed, trunc, cur):  # fmt: skip
        if not name:
            return no_update, "Pick an aircraft.", no_update
        try:
            cfg, _ = _base_cfg(name, cur)
            upd: dict = {}
            if weight:
                upd["weight_lbf"] = float(weight)
            if temp is not None:
                upd["temperature_F"], upd["isa_delta_F"] = float(temp), None
            if elev is not None:
                upd["elevation_ft"] = float(elev)
            if wind is not None:
                upd["headwind_kts"] = float(wind)
            if cond:
                _, upd["mu_roll"], upd["mu_brake"] = RUNWAY_PRESETS[cond]
            if upd:
                cfg = cfg.with_updates(upd)
            s = _settings(s_cl, s_cd, s_t, landing, n, method, seed, trunc)
            d = compute.uncertainty(cfg.model_dump_json(), json.dumps(asdict(s)))
            d["cfg_json"] = cfg.model_dump_json()
            return d, "", None
        except Exception as exc:  # noqa: BLE001 - shown on the page
            return no_update, f"Could not run: {type(exc).__name__}: {exc}", no_update

    @app.callback(Output("un-results", "children"), Input("un-result", "data"))
    def on_result(d):
        if not d:
            return html.Div("Set the uncertainty of each table above and press Run. 500 draws "
                            "take about 10–25 s.", className="hint gu-empty")  # fmt: skip
        return results(d, 0.95)

    @app.callback(
        Output("un-answer", "children"),
        Input("un-cover", "value"),
        State("un-result", "data"),
        prevent_initial_call=True,
    )
    def on_cover(p, d):
        return answer(d, float(p)) if d else no_update

    @app.callback(
        Output("un-fig-margin", "figure"),
        Output("un-fig-sens", "figure"),
        Output("un-fig-scatter", "figure"),
        Output("un-fig-dist", "figure"),
        Output("un-fig-inputs", "figure"),
        Input("un-results", "children"),
        State("un-result", "data"),
    )
    def on_figs(_c, d):
        if not d:
            return (no_update,) * 5
        f = unc_figures
        return f.margin_curve(d), f.sensitivity(d), f.scatter(d), f.distribution(d), f.inputs(d)

    @app.callback(
        Output("un-other", "data"),
        Input("un-other-btn", "n_clicks"),
        State("un-result", "data"),
        prevent_initial_call=True,
    )
    def on_other(n, d):
        if not n or not d:
            return no_update
        s = dict(d["settings"])
        s["method"] = "mc" if s["method"] == "lhs" else "lhs"
        return compute.uncertainty(d["cfg_json"], json.dumps(s))

    @app.callback(
        Output("un-fig-conv", "figure"),
        Input("un-other", "data"),
        Input("un-results", "children"),
        State("un-result", "data"),
    )
    def on_conv(other, _c, d):
        if not d:
            return no_update
        return unc_figures.convergence(d, other)

    @app.callback(
        Output("un-dl-csv", "data"),
        Input("un-dl-csv-btn", "n_clicks"),
        State("un-result", "data"),
        prevent_initial_call=True,
    )
    def on_csv(n, d):
        if not n or not d:
            return no_update
        df = pd.DataFrame(d["factors"])
        for k, v in d["values"].items():
            df[k] = v
        df["error"] = d["errors"]
        head = f"# data uncertainty: {d['aircraft']}, {d['settings']} (blank = no solution)\n"
        return dcc.send_string(head + df.to_csv(index=False, float_format="%.6g"),
                               f"data_uncertainty_{len(df)}draws.csv")  # fmt: skip

    @app.callback(
        Output("un-dl-txt", "data"),
        Input("un-dl-txt-btn", "n_clicks"),
        State("un-result", "data"),
        prevent_initial_call=True,
    )
    def on_txt(n, d):
        if not n or not d:
            return no_update
        return dcc.send_string(d["summary"] + "\n", "data_uncertainty_summary.txt")
