"""Gust analysis page: how much extra runway to plan for gusty days.

A side analysis, kept off the simulator and the trade study: each run here is one
takeoff and one landing on the calm-day schedule in random Dryden gusts (bfl.gusts),
solved with a hand-written SDE method. The page answers with a number (the runway
that covers a chosen share of operations) and with figures made to be copied into a
presentation (camera icon: high-resolution PNG).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict

import numpy as np
import pandas as pd
from dash import Input, Output, State, dcc, html, no_update

from bfl.gusts import INTENSITY_W20_KTS, GustSettings, dryden, quantile_ci

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
                        "How much extra runway a gusty day needs. Each run is one takeoff (engine "
                        "failure at the critical moment) and one landing, flown on the **calm-day "
                        "schedule** through random gusts made from the Dryden turbulence model. "
                        "Hundreds of runs give the chance that a runway is enough.",
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
# results: the answer, how the gusts are made, one run, the margin curve, the checks
# ------------------------------------------------------------------------------------
RUNWAY_IDS = ("gu-rw-1", "gu-rw-2", "gu-rw-3")
GEN_DTS = ((0.005, "0.005 s"), (0.01, "0.01 s"), (0.05, "0.05 s"), (0.2, "0.2 s"))


def _panel(title: str, body: list, open_: bool = True, id_=None) -> html.Details:
    """A results card that folds away (open by default)."""
    kw = {"id": id_} if id_ else {}
    return html.Details(open=open_, className="card un-panel",
                        children=[html.Summary(title), *body], **kw)  # fmt: skip


def _main(d: dict) -> str:
    return gust_figures.headline_metrics(d)[0]


def _x(d: dict, key: str) -> np.ndarray:
    ok = np.asarray([e == "" for e in d["samples"]["error"]])
    return np.asarray(d["samples"][key], dtype=float)[ok]


def default_runways(d: dict) -> list[int]:
    """Starting candidates: calm rounded up to 250 ft, then +250 and +500 (gust margins are
    a few hundred feet)."""
    base = int(math.ceil(d["calm"][_main(d)] / 250) * 250)
    return [base, base + 250, base + 500]


def runway_list(vals) -> list[float]:
    return sorted({float(v) for v in vals if v is not None and float(v) > 0})


def runway_odds(d: dict, rw) -> list:
    if rw is None or not d:
        return []
    x = _x(d, _main(d))
    p = float(np.mean(x <= float(rw)))
    lo, hi = gust_figures.wilson(p, len(x))
    return [html.Span(gust_figures.fmt_p(p), className="un-rw-p"),
            html.Span(f"{100 * lo:.0f}–{100 * hi:.0f} %", className="hint")]  # fmt: skip


def plan_tile(d: dict, p: float) -> list:
    key = _main(d)
    est, lo, hi = quantile_ci(_x(d, key), p)
    calm = d["calm"][key]
    return [
        html.Div(f"Plan for {round(100 * p)} % of gusty days", className="m-label"),
        html.Div(f"{est:,.0f} ft", className="m-value"),
        html.Div(f"{est - calm:+,.0f} ft · {100 * (est / calm - 1):+.1f} %", className="gu-delta"),
        html.Div(f"sampling range {lo:,.0f}–{hi:,.0f} ft", className="hint"),
    ]


def odds_figure(d: dict, runways: list[float]):
    key = _main(d)
    return gust_figures.odds_chart(_x(d, key), d["calm"][key], runways,
                                   gust_figures.COLORS["takeoff_field_ft"]
                                   if key != "landing_runway_ft" else gust_figures.LANDING_C,
                                   gust_figures._subtitle(d), "calm", "runs")  # fmt: skip


def _governs(d: dict) -> str:
    if _main(d) != "runway_required_ft":
        return "Takeoff only." if _main(d) == "takeoff_field_ft" else "Landing only."
    to, ld = _x(d, "takeoff_field_ft"), _x(d, "landing_runway_ft")
    share = float(np.mean(ld > to))
    if share == 0:
        return "Takeoff sets the runway in every run."
    if share == 1:
        return "Landing sets the runway in every run."
    return f"Landing sets the runway in {100 * share:.0f} % of runs, takeoff in the rest."


def answer(d: dict, p: float) -> list:
    key = _main(d)
    calm = d["calm"][key]
    x = _x(d, key)
    n_all = len(d["samples"]["error"])
    errs = [e for e in d["samples"]["error"] if e]
    notes = []
    if errs:
        notes.append(f"{len(errs)} of {n_all} runs failed and are left out (first: {errs[0]}).")
    stall = d["samples"].get("stall_steps")
    if stall and sum(1 for v in stall if v and v > 0) > 0.05 * n_all:
        notes.append("Gusts pushed the angle of attack past the aero table at flying speed in "
                     "some runs (held at the table's end, a stall plateau).")  # fmt: skip
    exceed = float(np.mean(x > calm + 0.5))
    return [
        html.Div(
            className="gu-answer-head",
            children=[
                html.Div(className="spacer"),
                html.Span("Plan for", className="ctl-name"),
                _seg("gu-cover", p, [(c, f"{round(100 * c)} %") for c in COVERAGE]),
            ],
        ),
        html.Div(
            className="un-answer-grid",
            children=[
                html.Div(
                    className="un-tiles",
                    children=[
                        html.Div(
                            className="gu-card",
                            children=[
                                html.Div("Calm day", className="m-label"),
                                html.Div(f"{calm:,.0f} ft", className="m-value"),
                                html.Div(
                                    f"gusts need more in {100 * exceed:.0f} % of runs",
                                    className="gu-delta",
                                ),
                            ],
                        ),
                        html.Div(
                            id="gu-plan", className="gu-card un-plan", children=plan_tile(d, p)
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
                                                step=50,
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
                _graph("gu-fig-odds", "odds"),
            ],
        ),  # fmt: skip
        *[html.Div(n, className="hint") for n in notes],
        html.Div(
            className="dl-row",
            children=[
                html.Span(_governs(d), className="hint un-gov"),
                html.Button("⤓ Runs (CSV)", id="gu-dl-csv-btn", n_clicks=0, className="btn"),
                html.Button("⤓ Summary", id="gu-dl-txt-btn", n_clicks=0, className="btn"),
                html.Span(f"{len(x):,} runs · {d['time_s']:.0f} s", className="hint"),
            ],
        ),
    ]


def _gen_controls(d: dict) -> html.Div:
    vr = int(round(d["speeds"]["vr_kts"]))
    s = d["settings"]
    dt0 = s["dt_s"] if s["dt_s"] in [v for v, _ in GEN_DTS] else 0.01
    return html.Div(
        className="gu-gen-controls",
        children=[
            html.Div(className="un-slider", children=[
                html.Label("airspeed [kt]"),
                dcc.Slider(id="gu-gen-v", min=10, max=250, step=5, value=vr,
                           marks={v: str(v) for v in (10, 50, 100, 150, 200, 250)},
                           updatemode="mouseup", tooltip={"placement": "top"}),
            ]),
            html.Div(className="un-slider", children=[
                html.Label("height [ft]"),
                dcc.Slider(id="gu-gen-h", min=10, max=500, step=10, value=10,
                           marks={v: str(v) for v in (10, 100, 200, 300, 400, 500)},
                           updatemode="mouseup", tooltip={"placement": "top"}),
            ]),
            _field("Method", _seg("gu-gen-m", s["method"],
                                  [("heun", "Heun"), ("em", "Euler–Maruyama")])),
            _field("Time step", _seg("gu-gen-dt", dt0, list(GEN_DTS))),
        ],
    )  # fmt: skip


def gen_table(g: dict, w20: float, h: float, v: float, dt: float, span) -> html.Div:
    """The chain from the weather to the update rule, with this case's numbers."""
    rows = [html.Tr([html.Th(""), html.Th("strength σ"), html.Th("length L"),
                     html.Th("memory T = L / V"), html.Th("Δt / T")])]  # fmt: skip
    for lab, c in (("along the runway", "u"), ("vertical", "w")):
        r = dt / g[f"T_{c}"]
        flag = " warn" if r > 0.1 else ""
        rows.append(html.Tr([html.Td(lab), html.Td(f"{g[f'sigma_{c}']:.2f} kt"),
                             html.Td(f"{g[f'L_{c}']:,.0f} ft"),
                             html.Td(f"{g[f'T_{c}']:.2f} s"),
                             html.Td(f"{r:.3f}", className="num" + flag)]))  # fmt: skip
    span_txt = f", averaged over the {span:,.0f} ft wing" if span else ""
    return html.Div(
        className="gu-gen-chain",
        children=[
            html.Div(
                [html.B("Dryden"), f" at W20 {w20:g} kt, h {h:g} ft{span_txt}; ",
                 html.B("T = L / V"), f" at {v:g} kt; then every Δt = {dt:g} s:"],
                className="hint",
            ),
            html.Div(["g", html.Sub("n+1"), " = g", html.Sub("n"), " − (g", html.Sub("n"),
                      " / T) Δt + σ √(2 / T) √Δt · Z", html.Sub("n")], className="gu-eq"),
            html.Table(rows, className="dtab gu-gen-tab"),
        ],
    )  # fmt: skip


def results(d: dict, p: float) -> list:
    traces = d["traces"]
    has = {k for v in traces.values() for k in v}
    op0 = "go" if "go" in has else "landing"
    return [
        _panel(gust_figures.SHORT[_main(d)] + " on a gusty day", answer(d, p), id_="gu-answer"),
        _panel(
            "How the gusts are made",
            [
                html.Div(
                    "Pick a height and an airspeed: Dryden gives each gust's strength and length, "
                    "the airspeed turns the length into a memory, and the update rule makes the "
                    "gusts. Below: one history, and a check that the gusts have the strength and "
                    "memory Dryden asks for.",
                    className="hint",
                ),
                _gen_controls(d),
                html.Div(id="gu-gen-chain"),
                html.Div(
                    className="un-checks-row gu-gen-figs",
                    children=[
                        _graph("gu-fig-gen", "gust_history"),
                        _graph("gu-fig-gen-check", "gust_check"),
                    ],
                ),  # fmt: skip
            ],
        ),
        _panel(
            "One gusty run",
            [
                html.Div(
                    className="gu-answer-head",
                    children=[
                        html.Div(className="spacer"),
                        _seg(
                            "gu-trace-op",
                            op0,
                            [
                                (k, lab)
                                for k, lab in (
                                    ("go", "Takeoff (engine out)"),
                                    ("landing", "Landing"),
                                )
                                if k in has
                            ],
                        ),
                        _seg(
                            "gu-trace-run", "0", [(k, f"run {int(k) + 1}") for k in sorted(traces)]
                        ),
                    ],
                ),  # fmt: skip
                _graph("gu-fig-trace", "sample"),
            ],
        ),
        _panel("Extra runway vs share of gusty days", [_graph("gu-fig-margin", "margin")]),
        _panel(
            "Checks",
            [
                html.Div(_calm_check(d), className="hint"),
                html.Div(
                    className="un-checks-row",
                    children=[
                        _graph("gu-fig-var", "variance_error"),
                        _graph("gu-fig-mc", "sampling"),
                    ],
                ),  # fmt: skip
                html.Div(
                    className="gu-answer-head",
                    children=[
                        html.Div(
                            "Whole run: the same gusts at four time steps, against a "
                            "fine reference.",
                            className="hint",
                        ),
                        html.Div(className="spacer"),
                        html.Button(
                            "Check the time step (~10 s)",
                            id="gu-conv-btn",
                            n_clicks=0,
                            className="btn",
                        ),
                    ],
                ),  # fmt: skip
                loading.loading(_graph("gu-fig-dt", "timestep"), "Re-solving at four time steps…"),
            ],
        ),
    ]


def _calm_check(d: dict) -> str:
    """Gusts off: the stepped simulation against the main (adaptive) solver."""
    parts = []
    for k, lab in (("takeoff_field_ft", "takeoff"), ("landing_runway_ft", "landing")):
        if k in d["calm"] and k in d.get("reference", {}):
            c, r = d["calm"][k], d["reference"][k]
            parts.append(f"{lab} {c:,.0f} vs {r:,.0f} ft ({100 * (c / r - 1):+.2f} %)")
    return ("Gusts switched off, this simulation against the main solver: " + "; ".join(parts)
            + ".") if parts else ""  # fmt: skip


def _r_now(d: dict) -> tuple[float, float]:
    """Range of dt / T in this run: heights 10–50 ft, airspeeds from half VR to 1.2 VR."""
    s = d["settings"]
    rs = []
    for h in (10.0, 50.0):
        su, sw, lu, lw = dryden(h, d["w20"], d.get("span_ft"))
        for v in (0.5, 1.2):
            vv = v * d["speeds"]["vr_kts"] * 1.6878098571011957
            rs += [s["dt_s"] * vv / lu, s["dt_s"] * vv / lw]
    return min(rs), max(rs)


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
        Output("gu-plan", "children"),
        Input("gu-cover", "value"),
        State("gu-result", "data"),
        prevent_initial_call=True,
    )
    def on_cover(p, d):
        return plan_tile(d, float(p)) if d else no_update

    @app.callback(
        *[Output(rid + "-p", "children") for rid in RUNWAY_IDS],
        Output("gu-fig-odds", "figure"),
        *[Input(rid, "value") for rid in RUNWAY_IDS],
        State("gu-result", "data"),
    )
    def on_runways(r1, r2, r3, d):
        if not d:
            return (no_update,) * 4
        return (*[runway_odds(d, r) for r in (r1, r2, r3)],
                odds_figure(d, runway_list([r1, r2, r3])))  # fmt: skip

    @app.callback(
        Output("gu-fig-margin", "figure"),
        Output("gu-fig-mc", "figure"),
        Output("gu-fig-var", "figure"),
        Input("gu-results", "children"),
        State("gu-result", "data"),
    )
    def on_figs(_children, d):
        if not d:
            return no_update, no_update, no_update
        return (gust_figures.margin_curve(d), gust_figures.mc_convergence(d),
                gust_figures.variance_error(compute.gust_variance_points(), _r_now(d)))  # fmt: skip

    @app.callback(
        Output("gu-gen-chain", "children"),
        Output("gu-fig-gen", "figure"),
        Output("gu-fig-gen-check", "figure"),
        Input("gu-gen-v", "value"),
        Input("gu-gen-h", "value"),
        Input("gu-gen-m", "value"),
        Input("gu-gen-dt", "value"),
        State("gu-result", "data"),
    )
    def on_gen(v, h, m, dt, d):
        if not d:
            return no_update, no_update, no_update
        v, h, dt = float(v or 150), float(h or 10), float(dt or 0.01)
        span = d.get("span_ft")
        g = compute.gust_generator(float(d["w20"]), h, v, dt, m or "heun", span)
        meth = "Heun" if m == "heun" else "Euler–Maruyama"
        lab = f"h {h:g} ft · {v:g} kt · W20 {d['w20']:g} kt · {meth}, Δt {dt:g} s"
        return (gen_table(g, d["w20"], h, v, dt, span), gust_figures.gust_history(g, lab),
                gust_figures.gust_checks(g, dt))  # fmt: skip

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
