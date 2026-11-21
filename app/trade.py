"""Trade study page: field length over a k_CL x k_CD grid, one map per aero/thrust table.

The base case is the last Run on the simulator page (same aircraft, weather, rules, ...).
A short override panel changes the common inputs; everything else is inherited.
"""

from __future__ import annotations

import io
import json
import time

import numpy as np
from dash import Input, Output, State, ctx, dcc, html, no_update

from bfl import RunConfig, load_config
from bfl.config import load_aircraft

from . import compute, figures

MAX_MAPS = 6
MAX_GRID = 21
METRICS = {
    "bfl_ft": "BFL / CFL",
    "field_length_ft": "Runway required (field length)",
    "aeo_distance_ft": "All-engines distance",
}
RUNWAY_PRESETS = {  # MIL-STD-3013 Table II, anti-skid
    "": "inherit",
    "dry": (0.025, 0.38),
    "wet": (0.050, 0.25),
    "wet_snow": (0.090, 0.18),
    "wet_ice": (0.050, 0.12),
}
GRAPH_CFG = {
    "displaylogo": False,
    "responsive": True,
    "toImageButtonOptions": {"format": "png", "filename": "trade_study", "scale": 3},
}


def _num(id_: str, label: str, value=None, step=None, placeholder="inherit", unit=""):
    return html.Div(
        className="tr-field",
        children=[
            html.Label([label, html.Span(f" {unit}", className="sym") if unit else None]),
            dcc.Input(
                id=id_,
                type="number",
                value=value,
                step=step,
                placeholder=placeholder,
                debounce=True,
                className="num-input",
            ),  # fmt: skip
        ],
    )


def layout() -> html.Div:
    return html.Div(
        className="trade-page",
        children=[
            html.Div(
                className="card",
                children=[
                    html.H2("Trade study"),
                    html.Div(
                        "Field length over lift × drag multipliers. Each cell is a full "
                        "solve (V2 rule, rule set and everything else as in the base case). "
                        "Pick several aero or thrust tables to get one map per combination "
                        "on a shared colour scale.",
                        className="hint",
                    ),
                    html.Div(id="trade-base", className="trade-base"),
                ],
            ),
            html.Div(
                className="trade-grid",
                children=[
                    html.Div(
                        className="card trade-controls",
                        children=[
                            html.H3("Setup"),
                            html.Label("Aircraft"),
                            dcc.Dropdown(id="tr-aircraft", clearable=False, searchable=False),
                            html.Label("Aero tables", className="ctl"),
                            dcc.Checklist(id="tr-aero", className="checks"),
                            html.Label("Thrust tables", className="ctl"),
                            dcc.Checklist(id="tr-thrust", className="checks"),
                            html.Div(id="tr-count", className="hint"),
                            html.Label("Grid", className="ctl"),
                            html.Div(
                                className="tr-row",
                                children=[
                                    _num("tr-kcd-lo", "k_CD from", 0.75, 0.01, ""),
                                    _num("tr-kcd-hi", "to", 1.25, 0.01, ""),
                                ],
                            ),
                            html.Div(
                                className="tr-row",
                                children=[
                                    _num("tr-kcl-lo", "k_CL from", 0.75, 0.01, ""),
                                    _num("tr-kcl-hi", "to", 1.25, 0.01, ""),
                                ],
                            ),
                            _num("tr-n", "points per axis", 11, 1, ""),
                            html.Details(
                                className="tr-over",
                                children=[
                                    html.Summary("Overrides (blank = inherit)"),
                                    _num("tr-weight", "Takeoff weight", None, 1000, unit="lbf"),
                                    html.Label("Rules", className="ctl"),
                                    dcc.Dropdown(
                                        id="tr-rules",
                                        value="",
                                        clearable=False,
                                        searchable=False,
                                        options=[
                                            {"label": "inherit", "value": ""},
                                            {"label": "FAA Part 25", "value": "part25"},
                                            {"label": "MIL-STD-3013", "value": "mil3013"},
                                        ],
                                    ),  # fmt: skip
                                    html.Label("Runway condition", className="ctl"),
                                    dcc.Dropdown(
                                        id="tr-cond",
                                        value="",
                                        clearable=False,
                                        searchable=False,
                                        options=[{"label": "inherit", "value": ""}]
                                        + [
                                            {
                                                "label": k.replace("_", " ") + " (anti-skid)",
                                                "value": k,
                                            }
                                            for k in RUNWAY_PRESETS
                                            if k
                                        ],
                                    ),  # fmt: skip
                                    _num("tr-temp", "Temperature", None, 1, unit="°F"),
                                    _num("tr-elev", "Elevation", None, 100, unit="ft"),
                                    _num("tr-wind", "Headwind (− tail)", None, 1, unit="kt"),
                                ],
                            ),
                            html.Button(
                                "Run trade study",
                                id="tr-run",
                                n_clicks=0,
                                className="btn btn-primary btn-run",
                            ),  # fmt: skip
                            html.Div(id="tr-status", className="hint"),
                        ],
                    ),
                    html.Div(
                        className="card trade-out",
                        children=[
                            html.Div(
                                className="tr-display",
                                children=[
                                    html.Div(
                                        [
                                            html.Label("Show"),
                                            dcc.Dropdown(
                                                id="tr-metric",
                                                value="bfl_ft",
                                                clearable=False,
                                                searchable=False,
                                                options=[
                                                    {"label": v, "value": k}
                                                    for k, v in METRICS.items()
                                                ],
                                            ),
                                        ],
                                        className="tr-field wide",
                                    ),  # fmt: skip
                                    html.Div(
                                        [
                                            html.Label("Colour"),
                                            dcc.RadioItems(
                                                id="tr-mode",
                                                value="bands",
                                                inline=True,
                                                className="checks",
                                                options=[
                                                    {"label": " banded  ", "value": "bands"},
                                                    {"label": " viridis", "value": "viridis"},
                                                ],
                                            ),
                                        ],
                                        className="tr-field",
                                    ),  # fmt: skip
                                    html.Div(
                                        [
                                            html.Label("Band edges [ft]"),
                                            dcc.Input(
                                                id="tr-bands",
                                                value="6000, 8000, 10000",
                                                debounce=True,
                                                className="num-input",
                                            ),
                                        ],
                                        className="tr-field wide",
                                    ),  # fmt: skip
                                    html.Button(
                                        "Download CSV", id="tr-csv-btn", n_clicks=0, className="btn"
                                    ),  # fmt: skip
                                    dcc.Download(id="tr-csv"),
                                ],
                            ),
                            html.Div(
                                "Bands: green below the first edge, then yellow, red, …, "
                                "grey above the last. Camera icon (top right of the plot) "
                                "saves a PNG. ○ = base case, × = no solution.",
                                className="hint",
                            ),
                            dcc.Loading(
                                dcc.Graph(
                                    id="tr-graph",
                                    config=GRAPH_CFG,
                                    figure=figures.empty("Set up and press Run", 420),
                                ),
                                type="circle",
                            ),  # fmt: skip
                        ],
                    ),
                ],
            ),
            dcc.Store(id="tr-result"),
            dcc.Store(id="tr-init", data=1),
        ],
    )


def _base_cfg(aircraft: str, cur: dict | None) -> tuple[RunConfig, str]:
    """The simulator's last run if it used this aircraft, else the aircraft defaults."""
    if cur and cur.get("ok"):
        cfg = RunConfig.model_validate_json(cur["cfg_json"])
        if cfg.aircraft.directory == load_aircraft(aircraft).directory:
            return cfg, "the simulator's last run"
    return load_config(aircraft), "aircraft defaults (no simulator run with this aircraft yet)"


def _parse_bands(text: str | None) -> list[float]:
    out = []
    for tok in (text or "").replace(";", ",").split(","):
        try:
            out.append(float(tok.strip().replace("_", "")))
        except ValueError:
            continue
    return sorted(v for v in out if v > 0)


def register(app, aircraft_options) -> None:
    @app.callback(
        Output("tr-aircraft", "options"),
        Output("tr-aircraft", "value"),
        Input("tr-init", "data"),
        State("aircraft", "value"),
        State("show-synthetic", "value"),
    )
    def on_open(_init, sim_aircraft, show_syn):
        opts = aircraft_options("on" in (show_syn or []))
        return opts, sim_aircraft or (opts[0]["value"] if opts else None)

    @app.callback(
        Output("tr-aero", "options"),
        Output("tr-aero", "value"),
        Output("tr-thrust", "options"),
        Output("tr-thrust", "value"),
        Output("trade-base", "children"),
        Input("tr-aircraft", "value"),
        State("current", "data"),
    )
    def on_aircraft(name, cur):
        if not name:
            return [], [], [], [], ""
        cfg, src = _base_cfg(name, cur)
        ac = cfg.aircraft
        aero = [{"label": f" {k}", "value": k} for k in ac.aero.configurations]
        thr = [{"label": f" {k}", "value": v} for k, v in ac.engines.thrust_options().items()]
        p = cfg.procedure.resolved()
        e = cfg.environment
        base = (
            f"Base case: {src} · {ac.name} · {cfg.weight_lbf:,.0f} lbf · "
            f"{'MIL-STD-3013' if p.is_mil else 'Part 25'} · "
            f"{e.temperature_F if e.temperature_F is not None else 'ISA'} °F · "
            f"{e.elevation_ft:,.0f} ft · wind {e.headwind_kts:+.0f} kt · "
            f"μ {e.mu_roll:.3f}/{e.mu_brake:.2f}"
        )
        return (aero, [ac.aero.takeoff_configuration], thr,
                [ac.engines.thrust_table] if ac.engines.thrust_table else [],
                base)  # fmt: skip

    @app.callback(
        Output("tr-count", "children"),
        Input("tr-aero", "value"),
        Input("tr-thrust", "value"),
        Input("tr-n", "value"),
    )
    def on_count(aero, thrust, n):
        k = max(1, len(aero or [])) * max(1, len(thrust or []))
        n = int(n or 11)
        warn = f" (max {MAX_MAPS})" if k > MAX_MAPS else ""
        return f"{k} map(s) × {n * n} solves{warn}"

    @app.callback(
        Output("tr-result", "data"),
        Output("tr-status", "children"),
        Input("tr-run", "n_clicks"),
        State("tr-aircraft", "value"),
        State("tr-aero", "value"),
        State("tr-thrust", "value"),
        State("tr-kcd-lo", "value"),
        State("tr-kcd-hi", "value"),
        State("tr-kcl-lo", "value"),
        State("tr-kcl-hi", "value"),
        State("tr-n", "value"),
        State("tr-weight", "value"),
        State("tr-rules", "value"),
        State("tr-cond", "value"),
        State("tr-temp", "value"),
        State("tr-elev", "value"),
        State("tr-wind", "value"),
        State("current", "data"),
        prevent_initial_call=True,
    )
    def on_run(_n, name, aero, thrust, cd_lo, cd_hi, cl_lo, cl_hi, n, weight, rules, cond,
               temp, elev, wind, cur):  # fmt: skip
        if not name:
            return no_update, "Pick an aircraft."
        try:
            cfg, _ = _base_cfg(name, cur)
            upd: dict = {}
            if weight:
                upd["environment.weight_lbf"] = float(weight)
            if rules:
                upd["procedure.rules"] = rules
                upd["procedure.t_recog_s"] = None  # take the new rule set's delay
            if cond:
                upd["environment.mu_roll"], upd["environment.mu_brake"] = RUNWAY_PRESETS[cond]
            if temp is not None:
                upd["environment.temperature_F"] = float(temp)
                upd["environment.isa_delta_F"] = None
            if elev is not None:
                upd["environment.elevation_ft"] = float(elev)
            if wind is not None:
                upd["environment.headwind_kts"] = float(wind)
            if upd:
                cfg = cfg.with_updates(upd)
            n = int(min(max(int(n or 11), 2), MAX_GRID))
            kcd = tuple(np.round(np.linspace(float(cd_lo), float(cd_hi), n), 4).tolist())
            kcl = tuple(np.round(np.linspace(float(cl_lo), float(cl_hi), n), 4).tolist())
            if min(kcd + kcl) <= 0:
                return no_update, "Multipliers must be positive."
            aeros = aero or [cfg.aircraft.aero.takeoff_configuration]
            thrusts = thrust or [cfg.aircraft.engines.thrust_table]
            combos = [(a, t) for a in aeros for t in thrusts][:MAX_MAPS]
            names = {v: k for k, v in cfg.aircraft.engines.thrust_options().items()}
            t0 = time.perf_counter()
            maps = []
            for a, t in combos:
                u = {"aircraft.aero.takeoff_configuration": a}
                if t:
                    u["aircraft.engines.thrust_table"] = t
                c = cfg.with_updates(u)
                m = compute.trade_map(c.model_dump_json(), kcl, kcd)
                title = " · ".join(
                    x for x in (
                        f"aero: {a}" if len(aeros) > 1 else "",
                        f"thrust: {names.get(t, t)}" if len(thrusts) > 1 else "",
                    ) if x
                ) or f"{cfg.aircraft.name}"  # fmt: skip
                maps.append({**m, "title": title, "aero": a, "thrust": names.get(t, t)})
            p = cfg.procedure.resolved()
            result = {
                "maps": maps,
                "rules": p.rules,
                "base_k": [cfg.multipliers.k_CL, cfg.multipliers.k_CD],
                "aircraft": cfg.aircraft.name,
            }
            dt = time.perf_counter() - t0
            cells = len(maps) * n * n
            return result, f"{cells} solves in {dt:.1f} s"
        except Exception as exc:  # noqa: BLE001 - show in the status line
            return no_update, f"Failed: {type(exc).__name__}: {exc}"

    @app.callback(
        Output("tr-graph", "figure"),
        Input("tr-result", "data"),
        Input("tr-metric", "value"),
        Input("tr-mode", "value"),
        Input("tr-bands", "value"),
    )
    def on_draw(res, metric, mode, bands):
        if not res:
            return figures.empty("Set up and press Run", 420)
        label = METRICS[metric]
        if metric == "bfl_ft":
            label = "CFL" if res["rules"] == "mil3013" else "BFL"
        return figures.trade(res["maps"], metric, label, mode, _parse_bands(bands),
                             tuple(res["base_k"]))  # fmt: skip

    @app.callback(
        Output("tr-csv", "data"),
        Input("tr-csv-btn", "n_clicks"),
        State("tr-result", "data"),
        prevent_initial_call=True,
    )
    def on_csv(_n, res):
        if not res or ctx.triggered_id != "tr-csv-btn":
            return no_update
        buf = io.StringIO()
        buf.write("aircraft,rules,aero,thrust,k_CL,k_CD,bfl_ft,field_length_ft,aeo_distance_ft\n")
        for m in res["maps"]:
            for i, kcl in enumerate(m["k_CL"]):
                for j, kcd in enumerate(m["k_CD"]):
                    vals = [m["z"][k][i][j] for k in compute.TRADE_METRICS]
                    cells = ["" if v is None else f"{v:.1f}" for v in vals]
                    buf.write(f"{json.dumps(res['aircraft'])},{res['rules']},{m['aero']},"
                              f"{m['thrust']},{kcl},{kcd},{','.join(cells)}\n")  # fmt: skip
        return {"content": buf.getvalue(), "filename": "trade_study.csv"}
