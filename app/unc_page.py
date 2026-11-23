"""Data uncertainty page: how much runway to plan when the lift, drag and thrust tables
are only known to within some percentage (bfl.uncertainty).

A side analysis like the gust page: nothing here feeds the simulator or the trade study.
Written for a conceptual designer's end-of-pass runway check: the runway to plan for at
90/95/99 % confidence, the chance a given runway is enough, which table matters for an
equal error (exact one-at-a-time solves), how far the design is from a no-takeoff cliff,
and sliders over a response surface fitted to the draws. Method checks sit collapsed.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict

import numpy as np
import pandas as pd
from dash import Input, Output, State, dcc, html, no_update

from bfl.uncertainty import UncertaintySettings, quantile_ci_inf

from . import compute, loading, unc_figures
from .gust_page import _field, _seg
from .trade import RUNWAY_PRESETS, _base_cfg, _num

RUN_COUNTS = (200, 500, 1000, 2000)


def _graph(id_: str, name: str) -> dcc.Graph:
    """A figure with a PNG button sized for slides."""
    return dcc.Graph(id=id_, config={"displaylogo": False, "toImageButtonOptions": {
        "format": "png", "scale": 3, "filename": f"data_uncertainty_{name}"}})  # fmt: skip


COVERAGE = (0.90, 0.95, 0.99)
TABLES = (("un-cl", "Lift (CL)", "sigma_CL"), ("un-cd", "Drag (CD)", "sigma_CD"),
          ("un-t", "Thrust", "sigma_T"))  # fmt: skip


def _sigma_input(id_: str, label: str, value: float) -> html.Div:
    return html.Div(
        className="tr-field un-sig",
        children=[
            html.Label([label, html.Span(" 1σ", className="sym")]),
            html.Div(
                className="un-pm",
                children=[
                    html.Span("±"),
                    dcc.Input(
                        id=id_,
                        type="number",
                        value=value,
                        min=0,
                        step=0.5,
                        debounce=True,
                        className="num-input spin",  # +/- step buttons (0.5 %)
                    ),  # fmt: skip
                    html.Span("%"),
                ],
            ),
        ],
    )


def layout() -> html.Div:
    return html.Div(
        className="gust-page",
        children=[
            html.Div(
                className="card",
                children=[
                    html.H2("Data uncertainty"),
                    dcc.Markdown(
                        "Lift, drag and thrust data are estimates. Say how far off each might be "
                        "(1σ, %); each draw scales the tables at random and runs a full solve. "
                        "Out come the runway to plan for, which table matters, and whether the "
                        "design is near a cliff.",
                        className="hint",
                    ),
                    html.Div(id="un-base", className="trade-base"),
                ],
            ),
            html.Div(
                className="card gu-setup",
                children=[
                    html.Div(
                        className="un-setup-top",
                        children=[
                            html.Div(
                                className="gu-bar",
                                children=[
                                    _field(
                                        "Aircraft",
                                        dcc.Dropdown(
                                            id="un-aircraft", clearable=False, searchable=False
                                        ),
                                    ),  # fmt: skip
                                    *[_sigma_input(i, lab, 5.0) for i, lab, _ in TABLES],
                                    _field(
                                        "Operations",
                                        dcc.Checklist(
                                            id="un-landing",
                                            value=["on"],
                                            className="checks",
                                            options=[{"label": " include landing", "value": "on"}],
                                        ),
                                    ),  # fmt: skip
                                    _field(
                                        "Draws",
                                        _seg("un-n", 500, [(n, f"{n:,}") for n in RUN_COUNTS]),
                                    ),
                                    html.Button(
                                        "Run",
                                        id="un-run",
                                        n_clicks=0,
                                        className="btn btn-primary gu-run",
                                    ),  # fmt: skip
                                ],
                            ),
                            html.Details(
                                id="un-sig-box",
                                open=True,
                                className="un-sig-box",
                                children=[
                                    html.Summary("What will be drawn"),
                                    dcc.Graph(
                                        id="un-fig-sigmas",
                                        className="un-sigmas",
                                        figure=unc_figures.sigma_curves(5.0, 5.0, 5.0),
                                        config={"displayModeBar": False},
                                    ),
                                ],
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
            dcc.Download(id="un-dl-csv"),
            dcc.Download(id="un-dl-txt"),
        ],
    )


# ------------------------------------------------------------------------------------
# results
# ------------------------------------------------------------------------------------
STEPS = ((0.05, "±5 %"), (0.10, "±10 %"))


def default_runway(d: dict) -> int:
    """A starting value for 'your runway': nominal + 1,000 ft, rounded up to 100 ft."""
    return int(math.ceil((d["nominal"][d["main_output"]] + 1000) / 100) * 100)


def plan_tile(d: dict, p: float) -> list:
    key = d["main_output"]
    x = unc_figures.values(d, key)
    nom = d["nominal"][key]
    est, lo, hi = quantile_ci_inf(x, p)
    pct = round(100 * p)
    if not math.isfinite(est):
        return [html.Div(f"Plan for {pct} %", className="m-label"),
                html.Div("no runway", className="m-value"),
                html.Div(f"only {100 * float(np.mean(np.isfinite(x))):.0f} % of draws take off",
                         className="gu-delta")]  # fmt: skip
    ci = f"{lo:,.0f}–{hi:,.0f} ft" if math.isfinite(hi) else f"{lo:,.0f} ft – no limit"
    return [
        html.Div(f"Plan for {pct} %", className="m-label"),
        html.Div(f"{est:,.0f} ft", className="m-value"),
        html.Div(f"{est - nom:+,.0f} ft · {100 * (est / nom - 1):+.0f} %", className="gu-delta"),
        html.Div(f"sampling range {ci}", className="hint"),
    ]


def avail_out(d: dict, avail) -> list:
    if avail is None or not d:
        return [html.Div("—", className="m-value")]
    p = unc_figures.probability_ok(d, float(avail))
    nom = d["nominal"][d["main_output"]]
    return [
        html.Div(f"{100 * p:.0f} %", className="m-value"),
        html.Div(
            f"of draws fit · {float(avail) - nom:+,.0f} ft over nominal", className="gu-delta"
        ),
    ]


def verdict(d: dict) -> tuple[str, str]:
    """('ok' | 'warn' | 'bad', one sentence): is the design near a cliff?"""
    f = d["failure_rate"]
    oat10 = unc_figures._oat(d, 0.10)
    dead = [unc_figures.FACTOR_LABEL[k] for k, (w, _) in oat10.items() if math.isinf(w)]
    who = " or ".join(dead) if dead else ""
    if f > 0.01:
        tail = f"; 10 % worse {who} alone is enough." if dead else "."
        return (
            "bad",
            f"Knife-edge: {100 * f:.0f} % of draws cannot make an engine-out takeoff{tail}",
        )
    if f > 0:
        extra = f" 10 % worse {who} alone means no takeoff." if dead else ""
        return "warn", f"Near a cliff: {100 * f:.1f} % of draws cannot take off.{extra}"
    if dead:
        return "warn", f"Near a cliff: every draw took off, but 10 % worse {who} alone does not."
    return "ok", "No cliff: every draw took off, and so does 10 % worse data in any one table."


def _governs(d: dict) -> str:
    if d["main_output"] != "runway_required_ft" or "landing_runway_ft" not in d["values"]:
        return "Takeoff only (landing not included)."
    to = unc_figures.values(d, "takeoff_field_ft")
    ld = unc_figures.values(d, "landing_runway_ft")
    share = float(np.mean(ld > to))
    if share == 0:
        return "Takeoff sets the runway in every draw."
    if share == 1:
        return "Landing sets the runway in every draw."
    return f"Landing sets the runway in {100 * share:.0f} % of draws, takeoff in the rest."


def answer(d: dict, p: float) -> list:
    key = d["main_output"]
    nom = d["nominal"][key]
    level, text = verdict(d)
    icon = {"ok": "✓", "warn": "!", "bad": "⚠"}[level]
    return [
        html.Div(
            className="gu-answer-head",
            children=[
                html.H3(unc_figures.OUT_LABEL[key]),
                html.Div(className="spacer"),
                html.Span("Confidence", className="ctl-name"),
                _seg("un-cover", p, [(c, f"{round(100 * c)} %") for c in COVERAGE]),
            ],
        ),
        html.Div(
            className="gu-cards un-tiles",
            children=[
                html.Div(
                    className="gu-card",
                    children=[
                        html.Div("Nominal", className="m-label"),
                        html.Div(f"{nom:,.0f} ft", className="m-value"),
                        html.Div("tables as they are", className="gu-delta"),
                    ],
                ),  # fmt: skip
                html.Div(id="un-plan", className="gu-card un-plan", children=plan_tile(d, p)),
                html.Div(
                    className="gu-card",
                    children=[
                        html.Div(
                            [
                                "Your runway",
                                dcc.Input(
                                    id="un-avail",
                                    type="number",
                                    value=default_runway(d),
                                    step=100,
                                    debounce=True,
                                    className="num-input un-avail",
                                ),
                            ],
                            className="m-label",
                        ),
                        html.Div(id="un-avail-out", children=avail_out(d, default_runway(d))),
                    ],
                ),  # fmt: skip
            ],
        ),
        html.Div(
            className=f"un-verdict {level}",
            children=[html.Span(icon, className="icon"), html.Span(text)],
        ),  # fmt: skip
        html.Div(
            className="dl-row",
            children=[
                html.Span(_governs(d), className="hint un-gov"),
                html.Button("⤓ Draws (CSV)", id="un-dl-csv-btn", n_clicks=0, className="btn"),
                html.Button("⤓ Summary", id="un-dl-txt-btn", n_clicks=0, className="btn"),
                html.Span(f"{len(d['errors']):,} draws · {d['time_s']:.0f} s", className="hint"),
            ],
        ),
    ]


def results(d: dict, p: float) -> list:
    return [
        html.Div(id="un-answer", className="card", children=answer(d, p)),
        html.Div(className="card", children=[_graph("un-fig-margin", "confidence")]),
        html.Div(
            className="card",
            children=[
                html.Div(
                    className="gu-answer-head",
                    children=[
                        html.H3("Which table matters"),
                        html.Div(className="spacer"),
                        html.Span("Error in one table", className="ctl-name"),
                        _seg("un-step", 0.05, list(STEPS)),
                    ],
                ),
                _graph("un-fig-tornado", "tornado"),
            ],
        ),
        _profiler_card(d),
        html.Div(className="card", children=[_graph("un-fig-map", "map")]),
        html.Details(
            className="card un-checks",
            children=[
                html.Summary("Method checks"),
                html.Div(
                    "The draws follow the stated distributions, and the 95 % answer has settled "
                    "(its sampling error shrinks like 1/√N; more draws if it matters).",
                    className="hint",
                ),
                html.Div(
                    className="un-checks-row",
                    children=[_graph("un-fig-conv", "sampling"), _graph("un-fig-inputs", "inputs")],
                ),
            ],
        ),
    ]


FACTORS = (("k_CL", "un-sl-cl", "lift"), ("k_CD", "un-sl-cd", "drag"),
           ("k_T", "un-sl-t", "thrust"))  # fmt: skip


def _profiler_card(d: dict) -> html.Div:
    s = d["settings"]
    sig = {"k_CL": s["sigma_CL"], "k_CD": s["sigma_CD"], "k_T": s["sigma_T"]}
    sliders = []
    for k, sid, lab in FACTORS:
        v = sig[k]
        lo, hi = (round(1 - 3 * v, 3), round(1 + 3 * v, 3)) if v > 0 else (0.99, 1.01)
        marks = {round(x, 3): f"{x:.2f}" for x in np.linspace(lo, hi, 5)}
        sliders.append(html.Div(
            className="un-slider",
            children=[
                html.Label(f"{lab} ×"),
                dcc.Slider(id=sid, min=lo, max=hi, step=0.005, value=1.0, marks=marks,
                           updatemode="drag", disabled=v <= 0,
                           tooltip={"placement": "top", "always_visible": False}),
            ],
        ))  # fmt: skip
    return html.Div(
        className="card",
        children=[
            html.Div(
                className="gu-answer-head",
                children=[
                    html.H3("What if the tables are off by…"),
                    html.Div(className="spacer"),
                    html.Button("Reset to 1", id="un-sl-reset", n_clicks=0, className="btn"),
                ],
            ),
            html.Div(sliders, className="un-sliders"),
            _graph("un-fig-prof", "profiler"),
        ],
    )


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
        Output("un-fig-sigmas", "figure"),
        Output("un-sig-box", "open", allow_duplicate=True),
        Input("un-cl", "value"),
        Input("un-cd", "value"),
        Input("un-t", "value"),
        prevent_initial_call=True,
    )
    def on_sigmas(a, b, c):
        fig = unc_figures.sigma_curves(float(a or 0), float(b or 0), float(c or 0))
        return fig, True  # show what will be drawn again while the inputs change

    @app.callback(
        Output("un-result", "data"),
        Output("un-status", "children"),
        Output("un-sig-box", "open", allow_duplicate=True),
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
            return d, "", False
        except Exception as exc:  # noqa: BLE001 - shown on the page
            return no_update, f"Could not run: {type(exc).__name__}: {exc}", no_update

    @app.callback(Output("un-results", "children"), Input("un-result", "data"))
    def on_result(d):
        if not d:
            return html.Div("Set how far off each table might be and press Run. 500 draws take "
                            "about 10–25 s.", className="hint gu-empty")  # fmt: skip
        return results(d, 0.95)

    @app.callback(
        Output("un-plan", "children"),
        Input("un-cover", "value"),
        State("un-result", "data"),
        prevent_initial_call=True,
    )
    def on_cover(p, d):
        return plan_tile(d, float(p)) if d else no_update

    @app.callback(
        Output("un-avail-out", "children"),
        Output("un-fig-margin", "figure"),
        Output("un-fig-map", "figure"),
        Input("un-avail", "value"),
        State("un-result", "data"),
    )
    def on_avail(avail, d):
        if not d:
            return (no_update,) * 3
        a = float(avail) if avail is not None else None
        return avail_out(d, a), unc_figures.margin_curve(d, a), unc_figures.cliff_map(d, a)

    @app.callback(
        Output("un-fig-tornado", "figure"),
        Input("un-step", "value"),
        State("un-result", "data"),
    )
    def on_step(step, d):
        return unc_figures.tornado(d, float(step or 0.05)) if d else no_update

    @app.callback(
        Output("un-fig-prof", "figure"),
        Input("un-sl-cl", "value"),
        Input("un-sl-cd", "value"),
        Input("un-sl-t", "value"),
        Input("un-avail", "value"),
        State("un-result", "data"),
    )
    def on_profiler(kcl, kcd, kt, avail, d):
        if not d:
            return no_update
        sel = {"k_CL": kcl or 1.0, "k_CD": kcd or 1.0, "k_T": kt or 1.0}
        return unc_figures.profiler(d, sel, float(avail) if avail is not None else None)

    @app.callback(
        Output("un-sl-cl", "value"),
        Output("un-sl-cd", "value"),
        Output("un-sl-t", "value"),
        Input("un-sl-reset", "n_clicks"),
        prevent_initial_call=True,
    )
    def on_reset(_n):
        return 1.0, 1.0, 1.0

    @app.callback(
        Output("un-fig-conv", "figure"),
        Output("un-fig-inputs", "figure"),
        Input("un-results", "children"),
        State("un-result", "data"),
    )
    def on_checks(_c, d):
        if not d:
            return no_update, no_update
        return unc_figures.convergence(d), unc_figures.inputs(d)

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
