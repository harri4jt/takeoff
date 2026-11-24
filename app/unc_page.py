"""Uncertainty analysis page: how much runway to plan when the lift, drag and thrust
tables are only known to within some percentage (bfl.uncertainty).

A side analysis like the gust page: nothing here feeds the simulator or the trade study.
Open by default: the chance each candidate runway is enough, and the extra runway against
confidence. Collapsed: the multiplier profiler (sliders over a response surface fitted to
the draws), the feasibility map and the method checks.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict

import numpy as np
import pandas as pd
from dash import Input, Output, State, dcc, html, no_update

from bfl.uncertainty import UncertaintySettings

from . import compute, loading, unc_figures
from .gust_page import _field, _seg
from .trade import RUNWAY_PRESETS, _base_cfg, _num

RUN_COUNTS = (200, 500, 1000, 2000)


def _graph(id_: str, name: str) -> dcc.Graph:
    """A figure with a PNG button sized for slides."""
    return dcc.Graph(id=id_, config={"displaylogo": False, "toImageButtonOptions": {
        "format": "png", "scale": 3, "filename": f"data_uncertainty_{name}"}})  # fmt: skip


TABLES = (("un-cl", "Lift (CL)", "sigma_CL"), ("un-cd", "Drag (CD)", "sigma_CD"),
          ("un-t", "Thrust", "sigma_T"))  # fmt: skip


def _sigma_input(id_: str, label: str, value: float) -> html.Div:
    return html.Div(
        className="un-sig",
        children=[
            html.Label(label),
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
                className="card setup-card",
                children=[
                    html.H2("Uncertainty analysis"),
                    html.Div(id="un-base", className="trade-base"),
                    html.Div(
                        className="un-setup",
                        children=[
                            html.Div(
                                className="un-setup-col",
                                children=[
                                    _field(
                                        "Aircraft",
                                        dcc.Dropdown(
                                            id="un-aircraft", clearable=False, searchable=False
                                        ),
                                    ),  # fmt: skip
                                    _field(
                                        "Draws",
                                        _seg("un-n", 500, [(n, f"{n:,}") for n in RUN_COUNTS]),
                                    ),
                                    dcc.Checklist(
                                        id="un-landing",
                                        value=["on"],
                                        className="checks",
                                        options=[{"label": " include landing", "value": "on"}],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="un-setup-col",
                                children=[
                                    html.Label("Table error, 1σ", className="un-sig-head"),
                                    *[_sigma_input(i, lab, 5.0) for i, lab, _ in TABLES],
                                ],
                            ),
                            dcc.Graph(
                                id="un-fig-sigmas",
                                className="un-sigmas",
                                figure=unc_figures.sigma_curves(5.0, 5.0, 5.0),
                                config={"displayModeBar": False},
                            ),
                            html.Button(
                                "Run", id="un-run", n_clicks=0, className="btn btn-primary gu-run"
                            ),
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


RUNWAY_IDS = ("un-rw-1", "un-rw-2", "un-rw-3")


def default_runways(d: dict) -> list[int]:
    """Starting candidates: the nominal rounded up to 1,000 ft, then +1,000 and +2,000."""
    base = int(math.ceil(d["nominal"][d["main_output"]] / 1000) * 1000)
    return [base, base + 1000, base + 2000]


def runway_list(vals) -> list[float]:
    """The candidate runways that are filled in, shortest first, without repeats."""
    return sorted({float(v) for v in vals if v is not None and float(v) > 0})


def runway_odds(d: dict, rw) -> list:
    if rw is None or not d:
        return []
    p = unc_figures.probability_ok(d, float(rw))
    lo, hi = unc_figures.wilson(p, len(d["errors"]))
    return [html.Span(unc_figures.fmt_p(p), className="un-rw-p"),
            html.Span(f"{100 * lo:.0f}–{100 * hi:.0f} %", className="hint")]  # fmt: skip


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


def answer(d: dict) -> list:
    key = d["main_output"]
    nom = d["nominal"][key]
    level, text = verdict(d)
    icon = {"ok": "✓", "warn": "!", "bad": "⚠"}[level]
    return [
        html.Div(
            className="un-answer-grid",
            children=[
                html.Div(
                    className="un-tiles",
                    children=[
                        html.Div(
                            className="gu-card",
                            children=[
                                html.Div("Nominal", className="m-label"),
                                html.Div(f"{nom:,.0f} ft", className="m-value"),
                                html.Div("tables as they are", className="gu-delta"),
                            ],
                        ),
                        html.Div(
                            className="gu-card un-rw",
                            children=[
                                html.Div("Runways you could use", className="m-label"),
                                *[
                                    html.Div(
                                        className="un-rw-row",
                                        children=[
                                            dcc.Input(
                                                id=rid,
                                                type="number",
                                                value=v,
                                                step=100,
                                                min=0,
                                                debounce=True,
                                                className="num-input",
                                            ),
                                            html.Span("ft", className="unit"),
                                            html.Div(
                                                id=rid + "-p",
                                                className="un-rw-odds",
                                                children=runway_odds(d, v),
                                            ),
                                        ],
                                    )
                                    for rid, v in zip(RUNWAY_IDS, default_runways(d), strict=True)
                                ],
                            ],
                        ),
                    ],
                ),
                _graph("un-fig-odds", "odds"),
            ],
        ),  # fmt: skip
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


def _panel(title: str, body: list, cls: str = "", open_: bool = True, id_=None) -> html.Details:
    """A results card that folds away (open by default)."""
    kw = {"id": id_} if id_ else {}
    return html.Details(open=open_, className=f"card un-panel {cls}".strip(),
                        children=[html.Summary(title), *body], **kw)  # fmt: skip


def results(d: dict) -> list:
    return [
        _panel(unc_figures.OUT_LABEL[d["main_output"]], answer(d), id_="un-answer"),
        _panel("Extra runway vs confidence", [_graph("un-fig-margin", "confidence")]),
        _panel("Multiplier profiler", _profiler_body(d), open_=False),
        _panel("Feasibility map", [_graph("un-fig-map", "map")], open_=False),
        _panel(
            "Method checks",
            [_graph("un-fig-conv", "sampling"), _graph("un-fig-inputs", "inputs")],
            open_=False,
        ),
    ]


FACTORS = (("k_CL", "un-sl-cl", "lift"), ("k_CD", "un-sl-cd", "drag"),
           ("k_T", "un-sl-t", "thrust"))  # fmt: skip


def _profiler_body(d: dict) -> list:
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
    reset = html.Button("Reset to 1", id="un-sl-reset", n_clicks=0, className="btn")
    return [
        html.Div([*sliders, reset], className="un-sliders"),
        _graph("un-fig-prof", "profiler"),
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
        Output("un-fig-sigmas", "figure"),
        Input("un-cl", "value"),
        Input("un-cd", "value"),
        Input("un-t", "value"),
        prevent_initial_call=True,
    )
    def on_sigmas(a, b, c):
        return unc_figures.sigma_curves(float(a or 0), float(b or 0), float(c or 0))

    @app.callback(
        Output("un-result", "data"),
        Output("un-status", "children"),
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
            return no_update, "Pick an aircraft."
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
            return d, ""
        except Exception as exc:  # noqa: BLE001 - shown on the page
            return no_update, f"Could not run: {type(exc).__name__}: {exc}"

    @app.callback(Output("un-results", "children"), Input("un-result", "data"))
    def on_result(d):
        if not d:
            return html.Div("Set how far off each table might be and press Run. 500 draws take "
                            "about 10–25 s.", className="hint gu-empty")  # fmt: skip
        return results(d)

    @app.callback(
        *[Output(rid + "-p", "children") for rid in RUNWAY_IDS],
        Output("un-fig-odds", "figure"),
        Output("un-fig-map", "figure"),
        *[Input(rid, "value") for rid in RUNWAY_IDS],
        State("un-result", "data"),
    )
    def on_runways(r1, r2, r3, d):
        if not d:
            return (no_update,) * 5
        rws = runway_list([r1, r2, r3])
        return (*[runway_odds(d, r) for r in (r1, r2, r3)], unc_figures.odds_curve(d, rws),
                unc_figures.cliff_map(d, rws))  # fmt: skip

    @app.callback(
        Output("un-fig-prof", "figure"),
        Input("un-sl-cl", "value"),
        Input("un-sl-cd", "value"),
        Input("un-sl-t", "value"),
        *[Input(rid, "value") for rid in RUNWAY_IDS],
        State("un-result", "data"),
    )
    def on_profiler(kcl, kcd, kt, r1, r2, r3, d):
        if not d:
            return no_update
        sel = {"k_CL": kcl or 1.0, "k_CD": kcd or 1.0, "k_T": kt or 1.0}
        return unc_figures.profiler(d, sel, runway_list([r1, r2, r3]))

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
        Output("un-fig-margin", "figure"),
        Output("un-fig-conv", "figure"),
        Output("un-fig-inputs", "figure"),
        Input("un-results", "children"),
        State("un-result", "data"),
    )
    def on_static(_c, d):
        if not d:
            return no_update, no_update, no_update
        f = unc_figures
        return f.margin_curve(d), f.convergence(d), f.inputs(d)

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
