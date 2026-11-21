"""Gust analysis page: how much extra runway to plan for gusty days.

A side analysis, kept off the simulator and the trade study: each run here is one
takeoff and one landing on the calm-day schedule in random Dryden gusts (bfl.gusts),
solved with a hand-written SDE method. The page answers with a number (the runway
that covers a chosen share of operations) and with figures made to be copied into a
presentation (camera icon: high-resolution PNG).
"""

from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pandas as pd
from dash import Input, Output, State, dcc, html, no_update

from bfl.gusts import INTENSITY_W20_KTS, GustSettings, quantile_ci

from . import compute, gust_figures, loading
from .trade import RUNWAY_PRESETS, _base_cfg, _num

RUN_COUNTS = (200, 500, 1000, 2000)
COVERAGE = (0.90, 0.95, 0.99)


def _graph(id_: str, name: str) -> dcc.Graph:
    return dcc.Graph(
        id=id_,
        config={
            "displaylogo": False,
            "toImageButtonOptions": {"format": "png", "scale": 3, "filename": f"gusts_{name}"},
        },
    )


def _seg(id_: str, value, options: list[tuple]) -> dcc.RadioItems:
    return dcc.RadioItems(
        id=id_, value=value, inline=True, className="seg",
        options=[{"label": lab, "value": v} for v, lab in options],
    )  # fmt: skip


def _field(label: str, child, hint: str | None = None) -> html.Div:
    return html.Div(
        className="gu-field",
        children=[html.Label(label), child] + ([html.Div(hint, className="hint")] if hint else []),
    )


def layout() -> html.Div:
    return html.Div(
        className="gust-page",
        children=[
            html.Div(
                className="card",
                children=[
                    html.H2("Gust analysis"),
                    dcc.Markdown(
                        "How much extra runway to plan for a gusty day. Each run is one "
                        "takeoff (with the engine failure at the critical moment) and one "
                        "landing, flown on the **calm-day schedule** (same V1, VR and approach "
                        "speed) through random gusts. The result is not a worst case: it is "
                        "how often a given runway is enough. A side analysis: gusts are not "
                        "used anywhere else in the tool.",
                        className="hint",
                    ),
                    html.Div(id="gu-base", className="trade-base"),
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
                                dcc.Dropdown(id="gu-aircraft", clearable=False, searchable=False),
                            ),  # fmt: skip
                            _field(
                                "Turbulence",
                                _seg(
                                    "gu-intensity",
                                    "moderate",
                                    [(k, k.capitalize()) for k in INTENSITY_W20_KTS],
                                ),
                                "wind at 20 ft: 15 / 30 / 45 kt",
                            ),  # fmt: skip
                            _field(
                                "Gusts",
                                dcc.Checklist(
                                    id="gu-vertical",
                                    value=["on"],
                                    className="checks",
                                    options=[{"label": " vertical too", "value": "on"}],
                                ),
                            ),  # fmt: skip
                            _field(
                                "Operations",
                                dcc.Checklist(
                                    id="gu-ops",
                                    value=["takeoff", "landing"],
                                    className="checks",
                                    inline=True,
                                    options=[
                                        {"label": " takeoff  ", "value": "takeoff"},
                                        {"label": " landing", "value": "landing"},
                                    ],
                                ),
                            ),  # fmt: skip
                            _field(
                                "Runs",
                                _seg("gu-n", 500, [(n, f"{n:,}") for n in RUN_COUNTS]),
                                "more runs: tighter estimates, longer wait",
                            ),  # fmt: skip
                            html.Button(
                                "Run", id="gu-run", n_clicks=0, className="btn btn-primary gu-run"
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
                                    _num("gu-weight", "Takeoff weight", None, 1000, unit="lbf"),
                                    _num("gu-temp", "Temperature", None, 1, unit="°F"),
                                    _num("gu-elev", "Elevation", None, 100, unit="ft"),
                                    _num("gu-wind", "Mean headwind (− tail)", None, 1, unit="kt"),
                                    html.Div(
                                        className="tr-field",
                                        children=[
                                            html.Label("Runway condition"),
                                            dcc.Dropdown(
                                                id="gu-cond",
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
                            html.Summary("Method and pilot model"),
                            html.Div(
                                className="gu-row",
                                children=[
                                    _field(
                                        "SDE method",
                                        _seg(
                                            "gu-method",
                                            "heun",
                                            [("heun", "Stochastic Heun"), ("em", "Euler–Maruyama")],
                                        ),
                                    ),  # fmt: skip
                                    _field(
                                        "Time step",
                                        _seg(
                                            "gu-dt",
                                            0.01,
                                            [
                                                (0.005, "0.005 s"),
                                                (0.01, "0.01 s"),
                                                (0.02, "0.02 s"),
                                            ],
                                        ),
                                    ),  # fmt: skip
                                    _num("gu-seed", "Random seed", 1, 1, "", spin=True),
                                    _num("gu-lag", "Pilot lag on gusts", 1.0, 0.1, "", unit="s"),
                                    _num(
                                        "gu-additive",
                                        "Approach speed additive",
                                        0,
                                        1,
                                        "",
                                        unit="kt",
                                    ),  # fmt: skip
                                ],
                            ),
                            html.Div(
                                "The crew acts on airspeed with the gust part lagged (pilot and "
                                "instrument response). Pilots often add speed on a gusty approach "
                                "(e.g. half the gust increment); that additive lengthens the "
                                "landing.",
                                className="hint",
                            ),
                        ],
                    ),
                    html.Div(id="gu-status", className="hint"),
                ],
            ),
            loading.loading(
                [
                    html.Div(id="gu-results"),
                    dcc.Store(id="gu-result"),
                ],
                "Simulating gusty takeoffs and landings…",
                220,
            ),
            dcc.Store(id="gu-conv"),
            dcc.Download(id="gu-dl-csv"),
            dcc.Download(id="gu-dl-txt"),
        ],
    )


# ------------------------------------------------------------------------------------
# results
# ------------------------------------------------------------------------------------
def _card(d: dict, key: str, p: float) -> html.Div:
    ok = np.asarray([e == "" for e in d["samples"]["error"]])
    x = np.asarray(d["samples"][key], dtype=float)[ok]
    calm = d["calm"][key]
    est, lo, hi = quantile_ci(x, p)
    exceed = float(np.mean(x > calm + 0.5))
    pct = round(100 * p)
    color = gust_figures.COLORS[key]
    return html.Div(
        className="gu-card",
        children=[
            html.Div(
                [
                    html.Span(className="swatch", style={"background": color}),
                    gust_figures.SHORT[key],
                ],
                className="m-label",
            ),  # fmt: skip
            html.Div(f"{est:,.0f} ft", className="m-value"),
            html.Div(
                f"{est - calm:+,.0f} ft ({100 * (est / calm - 1):+.1f} %) over the calm "
                f"day's {calm:,.0f} ft",
                className="gu-delta",
            ),  # fmt: skip
            html.Div(
                f"covers {pct} % of runs · 95 % confidence {lo:,.0f}–{hi:,.0f} ft · "
                f"{100 * exceed:.0f} % of runs need more than calm",
                className="hint",
            ),  # fmt: skip
        ],
    )


def _card_keys(d: dict, keys: list[str]) -> list[str]:
    """Drop the combined card when one operation sets the runway in every run (it would
    repeat that card); the answer sentence says which one."""
    if "runway_required_ft" not in keys:
        return keys
    ok = np.asarray([e == "" for e in d["samples"]["error"]])
    to = np.asarray(d["samples"]["takeoff_field_ft"], dtype=float)[ok]
    ld = np.asarray(d["samples"]["landing_runway_ft"], dtype=float)[ok]
    if np.all(to >= ld) or np.all(ld > to):
        return [k for k in keys if k != "runway_required_ft"]
    return keys


def answer(d: dict, p: float) -> list:
    """The answer card's contents for coverage p (re-drawn alone when p changes)."""
    keys = gust_figures.headline_metrics(d)
    first = keys[0]
    ok = np.asarray([e == "" for e in d["samples"]["error"]])
    est = quantile_ci(np.asarray(d["samples"][first], dtype=float)[ok], p)[0]
    calm = d["calm"][first]
    gov = ""
    if first == "runway_required_ft":
        to = np.asarray(d["samples"]["takeoff_field_ft"], dtype=float)[ok]
        ld = np.asarray(d["samples"]["landing_runway_ft"], dtype=float)[ok]
        share = float(np.mean(to >= ld))
        gov = f" Takeoff sets the runway in {100 * share:.0f} % of runs."
    sentence = (
        f"To cover {round(100 * p)} % of gusty-day operations, plan {est:,.0f} ft of runway: "
        f"{est - calm:+,.0f} ft ({100 * (est / calm - 1):+.1f} %) over the calm-day "
        f"{calm:,.0f} ft.{gov}"
    )
    n_ok, n_all = int(ok.sum()), len(ok)
    errs = [e for e in d["samples"]["error"] if e]
    notes = []
    if errs:
        notes.append(f"{n_all - n_ok} of {n_all} runs failed and are left out "
                     f"(first: {errs[0]}).")  # fmt: skip
    stall = d["samples"].get("stall_steps")
    if stall and sum(1 for v in stall if v and v > 0) > 0.05 * n_all:
        notes.append("Gusts pushed the angle of attack past the aero table at flying speed in "
                     "some runs (held at the table's end, a stall plateau).")  # fmt: skip
    return [
        html.Div(
            className="gu-answer-head",
            children=[
                html.H3("Answer"),
                html.Div(className="spacer"),
                html.Span("Coverage", className="ctl-name"),
                _seg("gu-cover", p, [(c, f"{round(100 * c)} %") for c in COVERAGE]),
            ],
        ),
        html.P(sentence, className="gu-sentence"),
        html.Div([_card(d, k, p) for k in _card_keys(d, keys)], className="gu-cards"),
        *[html.Div(n, className="hint") for n in notes],
        html.Div(
            className="dl-row",
            children=[
                html.Button(
                    "⤓ Download runs (CSV)", id="gu-dl-csv-btn", n_clicks=0, className="btn"
                ),  # fmt: skip
                html.Button(
                    "⤓ Download summary", id="gu-dl-txt-btn", n_clicks=0, className="btn"
                ),  # fmt: skip
                html.Span(
                    f"{n_ok:,} runs in {d['time_s']:.1f} s · camera icon on a "
                    "chart: PNG for slides",
                    className="hint",
                ),  # fmt: skip
            ],
        ),
    ]


def results(d: dict, p: float) -> list:
    return [
        html.Div(id="gu-answer", className="card", children=answer(d, p)),
        html.Div(className="card", children=[_graph("gu-fig-margin", "margin")]),
        html.Div(className="card", children=[_graph("gu-fig-spread", "spread")]),
        html.Div(
            className="card",
            children=[
                html.Div(
                    className="gu-answer-head",
                    children=[
                        html.H3("What the gusts look like"),
                        html.Div(className="spacer"),
                        _seg(
                            "gu-trace-op",
                            "go" if "go" in next(iter(d["traces"].values()), {}) else "landing",
                            [
                                (k, lab)
                                for k, lab in (
                                    ("go", "Takeoff (engine out)"),
                                    ("landing", "Landing"),
                                )
                                if any(k in v for v in d["traces"].values())
                            ],
                        ),
                        _seg(
                            "gu-trace-run",
                            "0",
                            [(k, f"sample {int(k) + 1}") for k in sorted(d["traces"])],
                        ),
                    ],
                ),  # fmt: skip
                _graph("gu-fig-trace", "sample"),
            ],
        ),
        html.Div(
            className="card",
            children=[
                html.H3("How reliable are these numbers?"),
                dcc.Markdown(
                    "Two kinds of error. **Sampling**: a percentile from N runs is uncertain "
                    "by about 1/√N (the shaded bands; below, the estimate settling as runs "
                    "accumulate). **Time step**: each run integrates a stochastic "
                    "differential equation with a fixed step; *Check the time step* re-solves "
                    "a few runs with the same gusts at four step sizes. Methods › "
                    "Stochastic methods explains both.",
                    className="hint",
                ),
                _graph("gu-fig-mc", "sampling"),
                html.Button(
                    "Check the time step (~10 s)", id="gu-conv-btn", n_clicks=0, className="btn"
                ),  # fmt: skip
                loading.loading(_graph("gu-fig-dt", "timestep"), "Re-solving at four time steps…"),
            ],
        ),
    ]


def register(app, aircraft_options) -> None:
    @app.callback(
        Output("gu-aircraft", "options"),
        Output("gu-aircraft", "value"),
        Input("gu-aircraft", "id"),
        State("aircraft", "value"),
    )
    def on_open(_id, sim_aircraft):
        opts = aircraft_options()
        values = [o["value"] for o in opts]
        return opts, sim_aircraft if sim_aircraft in values else (values[0] if values else None)

    @app.callback(
        Output("gu-base", "children"),
        Input("gu-aircraft", "value"),
        State("current", "data"),
    )
    def on_base(name, cur):
        if not name:
            return ""
        cfg, src = _base_cfg(name, cur)
        e = cfg.environment
        temp = f"{e.temperature_F:g} °F" if e.temperature_F is not None else "ISA"
        return (f"Conditions from {src}: {cfg.aircraft.name}, {cfg.weight_lbf:,.0f} lb, {temp}, "
                f"{e.elevation_ft:,.0f} ft, wind {e.headwind_kts:+g} kt, μ brake "
                f"{e.mu_brake:g}.")  # fmt: skip

    @app.callback(
        Output("gu-result", "data"),
        Output("gu-status", "children"),
        Output("gu-conv", "data", allow_duplicate=True),
        Input("gu-run", "n_clicks"),
        State("gu-aircraft", "value"),
        State("gu-intensity", "value"),
        State("gu-vertical", "value"),
        State("gu-ops", "value"),
        State("gu-n", "value"),
        State("gu-weight", "value"),
        State("gu-temp", "value"),
        State("gu-elev", "value"),
        State("gu-wind", "value"),
        State("gu-cond", "value"),
        State("gu-method", "value"),
        State("gu-dt", "value"),
        State("gu-seed", "value"),
        State("gu-lag", "value"),
        State("gu-additive", "value"),
        State("current", "data"),
        prevent_initial_call=True,
    )
    def on_run(_n, name, intensity, vertical, ops, n, weight, temp, elev, wind, cond, method,
               dt, seed, lag, additive, cur):  # fmt: skip
        if not name:
            return no_update, "Pick an aircraft.", no_update
        ops = ops or []
        if not ops:
            return no_update, "Pick takeoff, landing or both.", no_update
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
            s = GustSettings(
                intensity=intensity, vertical="on" in (vertical or []), n=int(n),
                method=method, dt_s=float(dt), seed=int(seed or 1),
                filter_s=float(lag if lag is not None else 1.0),
                approach_additive_kts=float(additive or 0.0),
                takeoff="takeoff" in ops, landing="landing" in ops,
            )  # fmt: skip
            d = compute.gusts(cfg.model_dump_json(), json.dumps(asdict(s)))
            d["cfg_json"] = cfg.model_dump_json()
            return d, "", None  # a new result: the old time-step check no longer applies
        except Exception as exc:  # noqa: BLE001 - shown on the page
            return no_update, f"Could not run: {type(exc).__name__}: {exc}", no_update

    @app.callback(
        Output("gu-results", "children"),
        Input("gu-result", "data"),
    )
    def on_result(d):
        if not d:
            return html.Div(
                "Set up the question above and press Run. 500 runs take about 10–20 s.",
                className="hint gu-empty",
            )
        return results(d, 0.95)

    @app.callback(
        Output("gu-answer", "children"),
        Input("gu-cover", "value"),
        State("gu-result", "data"),
        prevent_initial_call=True,
    )
    def on_cover(p, d):
        return answer(d, float(p)) if d else no_update

    @app.callback(
        Output("gu-fig-margin", "figure"),
        Output("gu-fig-spread", "figure"),
        Output("gu-fig-mc", "figure"),
        Input("gu-results", "children"),
        State("gu-result", "data"),
    )
    def on_figs(_children, d):
        if not d:
            return no_update, no_update, no_update
        return (gust_figures.margin_curve(d), gust_figures.spread(d),
                gust_figures.mc_convergence(d))  # fmt: skip

    @app.callback(
        Output("gu-fig-trace", "figure"),
        Input("gu-trace-run", "value"),
        Input("gu-trace-op", "value"),
        State("gu-result", "data"),
    )
    def on_trace(run, op, d):
        if not d:
            return no_update
        return gust_figures.traces(d, run or "0", op or "go")

    @app.callback(
        Output("gu-conv", "data"),
        Input("gu-conv-btn", "n_clicks"),
        State("gu-result", "data"),
        prevent_initial_call=True,
    )
    def on_conv(n, d):
        if not n or not d:
            return no_update
        return compute.gust_convergence(d["cfg_json"], json.dumps(d["settings"]))

    @app.callback(
        Output("gu-fig-dt", "figure"),
        Input("gu-conv", "data"),
        Input("gu-results", "children"),
    )
    def on_dt(conv, _children):
        return gust_figures.dt_convergence(conv or {})

    @app.callback(
        Output("gu-dl-csv", "data"),
        Input("gu-dl-csv-btn", "n_clicks"),
        State("gu-result", "data"),
        prevent_initial_call=True,
    )
    def on_csv(n, d):
        if not n or not d:
            return no_update
        df = pd.DataFrame(d["samples"])
        head = f"# gust analysis: {d['aircraft']}, {d['settings']}\n"
        name = f"gusts_{d['settings']['intensity']}_{len(df)}runs.csv"
        return dcc.send_string(head + df.to_csv(index=False, float_format="%.6g"), name)

    @app.callback(
        Output("gu-dl-txt", "data"),
        Input("gu-dl-txt-btn", "n_clicks"),
        State("gu-result", "data"),
        prevent_initial_call=True,
    )
    def on_txt(n, d):
        if not n or not d:
            return no_update
        return dcc.send_string(d["summary"] + "\n", "gusts_summary.txt")
