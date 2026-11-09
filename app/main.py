"""Dash app for the BFL solver.

python -m app            (or: python app/main.py)   then open http://127.0.0.1:8050
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python app/main.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "app"

from dash import Dash, Input, Output, State, ctx, dcc, html, no_update  # noqa: E402

from bfl import list_aircraft  # noqa: E402
from bfl.config import load_aircraft  # noqa: E402

from . import compute, figures  # noqa: E402

DEFAULT_AIRCRAFT = "generic_widebody_synthetic"

CSS = {
    "page": {
        "fontFamily": "system-ui, -apple-system, Segoe UI, sans-serif",
        "color": "#0b0b0b",
        "background": "#f4f3f0",
        "minHeight": "100vh",
        "padding": "16px",
    },
    "card": {
        "background": "#fcfcfb",
        "borderRadius": "8px",
        "padding": "14px",
        "boxShadow": "0 1px 3px rgba(0,0,0,.08)",
        "marginBottom": "14px",
    },
    "label": {"fontSize": "12px", "color": "#52514e", "marginTop": "10px", "display": "block"},
    "button": {
        "padding": "8px 14px",
        "marginRight": "8px",
        "borderRadius": "6px",
        "border": "1px solid #52514e",
        "background": "#fcfcfb",
        "cursor": "pointer",
    },
    "primary": {
        "padding": "8px 18px",
        "marginRight": "8px",
        "borderRadius": "6px",
        "border": "none",
        "background": "#2a78d6",
        "color": "white",
        "cursor": "pointer",
        "fontWeight": "600",
    },
}


def slider(
    id_: str, label: str, lo: float, hi: float, step: float, value: float, marks: dict | None = None
) -> html.Div:
    return html.Div(
        [
            html.Label(label, style=CSS["label"]),
            dcc.Slider(
                id=id_,
                min=lo,
                max=hi,
                step=step,
                value=value,
                marks=marks or {lo: str(lo), hi: str(hi)},
                tooltip={"placement": "bottom", "always_visible": False},
            ),
        ]
    )


def controls() -> html.Div:
    try:
        names = list_aircraft()
    except FileNotFoundError:
        names = []
    return html.Div(
        style={**CSS["card"], "width": "300px", "flexShrink": 0},
        children=[
            html.H3("Inputs", style={"marginTop": 0}),
            html.Label("Aircraft", style=CSS["label"]),
            dcc.Dropdown(
                id="aircraft",
                options=[{"label": n, "value": n} for n in names],
                value=DEFAULT_AIRCRAFT
                if DEFAULT_AIRCRAFT in names
                else (names[0] if names else None),
                clearable=False,
            ),
            html.Div(
                id="aircraft-note",
                style={"fontSize": "12px", "color": "#b54600", "marginTop": "4px"},
            ),
            slider("k_cl", "k_CL - lift multiplier", 0.8, 1.2, 0.01, 1.0),
            slider("k_cd", "k_CD - drag multiplier", 0.8, 1.2, 0.01, 1.0),
            slider("mu_roll", "μ rolling", 0.01, 0.06, 0.005, 0.03),
            slider("mu_brake", "μ braking", 0.1, 0.6, 0.01, 0.30),
            slider(
                "headwind",
                "headwind [kt] (negative = tailwind)",
                -15,
                30,
                1,
                0,
                {-15: "-15", 0: "0", 30: "30"},
            ),
            slider(
                "slope",
                "runway slope [deg] (+ = uphill)",
                -2,
                2,
                0.1,
                0,
                {-2: "-2", 0: "0", 2: "2"},
            ),
            slider(
                "temperature",
                "temperature [°F]",
                -20,
                120,
                1,
                59,
                {-20: "-20", 59: "ISA", 120: "120"},
            ),
            slider(
                "elevation", "field elevation [ft]", 0, 10000, 100, 0, {0: "0", 10000: "10,000"}
            ),
            slider(
                "rotation_rate", "rotation rate [deg/s]", 1, 6, 0.1, 3, {1: "1", 3: "3", 6: "6"}
            ),
            html.Label("weight [lbf]", style=CSS["label"]),
            dcc.Input(id="weight", type="number", debounce=True, style={"width": "100%"}),
            dcc.Checklist(
                id="chute",
                options=[
                    {"label": " drag chute (outside Part 25)", "value": "on", "disabled": True}
                ],
                value=[],
                style={"marginTop": "10px", "fontSize": "13px"},
            ),
            html.Label("integrator", style=CSS["label"]),
            dcc.RadioItems(
                id="method",
                options=[
                    {"label": " RK4 (dt 0.01 s)", "value": "rk4"},
                    {"label": " RK45 adaptive", "value": "rk45"},
                ],
                value="rk4",
                inline=False,
                style={"fontSize": "13px"},
            ),
            html.Div(
                style={"marginTop": "16px"},
                children=[
                    html.Button("Run", id="run", n_clicks=0, style=CSS["primary"]),
                    html.Button("Pin as baseline", id="pin", n_clicks=0, style=CSS["button"]),
                ],
            ),
            html.Button(
                "Clear baseline",
                id="clear",
                n_clicks=0,
                style={**CSS["button"], "marginTop": "8px"},
            ),
            html.Div(
                id="baseline-note",
                style={"fontSize": "12px", "color": "#52514e", "marginTop": "6px"},
            ),
        ],
    )


def layout() -> html.Div:
    return html.Div(
        style=CSS["page"],
        children=[
            dcc.Store(id="current"),
            dcc.Store(id="baseline"),
            html.H2("Balanced Field Length solver", style={"margin": "0 0 4px 0"}),
            html.Div(
                "FAA Part 25-style BFL with hand-written RK4/RK45, secant and interpolation. "
                "Speeds in KEAS (≈KCAS) unless marked KTAS.",
                style={"color": "#52514e", "fontSize": "13px", "marginBottom": "12px"},
            ),
            html.Div(
                style={
                    "display": "flex",
                    "gap": "14px",
                    "alignItems": "flex-start",
                    "flexWrap": "wrap",
                },
                children=[
                    controls(),
                    html.Div(
                        style={"flex": "1 1 700px", "minWidth": "0"},
                        children=[
                            dcc.Loading(html.Div(id="readout", style=CSS["card"]), type="dot"),
                            html.Div(style=CSS["card"], children=[dcc.Graph(id="bfl-chart")]),
                            html.Div(
                                style=CSS["card"],
                                children=[
                                    html.Label("vertical exaggeration", style=CSS["label"]),
                                    dcc.Slider(
                                        id="exaggeration",
                                        min=1,
                                        max=100,
                                        step=1,
                                        value=25,
                                        marks={1: "×1", 25: "×25", 50: "×50", 100: "×100"},
                                    ),
                                    dcc.Graph(id="animation"),
                                ],
                            ),
                            html.Div(
                                style=CSS["card"],
                                children=[
                                    dcc.Tabs(
                                        id="th-tab",
                                        value="speeds",
                                        children=[
                                            dcc.Tab(label="Speeds", value="speeds"),
                                            dcc.Tab(label="Forces", value="forces"),
                                            dcc.Tab(label="Angles", value="angles"),
                                            dcc.Tab(label="Positions", value="positions"),
                                        ],
                                    ),
                                    dcc.RadioItems(
                                        id="th-branch",
                                        value="go",
                                        inline=True,
                                        options=[
                                            {"label": " go  ", "value": "go"},
                                            {"label": " stop  ", "value": "stop"},
                                            {"label": " AEO", "value": "aeo"},
                                        ],
                                        style={"fontSize": "13px", "margin": "8px 0"},
                                    ),
                                    dcc.Graph(id="time-history"),
                                ],
                            ),
                            html.Div(
                                style=CSS["card"],
                                children=[
                                    dcc.Graph(id="sensitivity"),
                                    html.Div(
                                        "Sensitivity points and the V1 sweep use RK45 for speed "
                                        "(agrees with RK4 to well under 1 ft).",
                                        style={"fontSize": "12px", "color": "#52514e"},
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def _fmt(v: float, unit: str, digits: int = 0) -> str:
    return f"{v:,.{digits}f} {unit}"


def readout(d: dict | None, base: dict | None) -> list:
    if not d:
        return [html.Div("Set inputs and press Run.", style={"color": "#52514e"})]
    if not d.get("ok"):
        return [
            html.Div("Computation failed", style={"fontWeight": 600, "color": "#c0392b"}),
            html.Pre(d["error"], style={"whiteSpace": "pre-wrap", "fontSize": "12px"}),
        ]
    s = d["scalars"]
    b = base["scalars"] if base and base.get("ok") else None

    def tile(label: str, key: str, unit: str, digits: int = 0, big: bool = False):
        val = s[key]
        delta = ""
        if b is not None:
            dv = val - b[key]
            delta = f"{dv:+,.{digits}f} vs baseline"
        return html.Div(
            style={"minWidth": "130px"},
            children=[
                html.Div(label, style={"fontSize": "12px", "color": "#52514e"}),
                html.Div(
                    _fmt(val, unit, digits),
                    style={"fontSize": "26px" if big else "19px", "fontWeight": 600},
                ),
                html.Div(delta, style={"fontSize": "11px", "color": "#52514e"}),
            ],
        )

    status = "Balanced" if s["balanced"] else "UNBALANCED: " + s["unbalanced_reason"]
    warn_items = [html.Li(w) for w in d["warnings"]]
    return [
        html.Div(
            style={"display": "flex", "gap": "22px", "flexWrap": "wrap"},
            children=[
                tile("Balanced field length", "bfl_ft", "ft", big=True),
                tile("FAA field length", "faa_field_length_ft", "ft", big=True),
                tile("V1", "v1_kts", "kt", 1),
                tile("VR", "vr_kts", "kt", 1),
                tile("V2", "v2_kts", "kt", 1),
                tile("V_EF", "v_ef_kts", "kt", 1),
                tile("AEO to 35 ft", "aeo_distance_ft", "ft"),
            ],
        ),
        html.Div(
            f"{status} · V_S {s['v_s_kts']:.1f} kt · V_LOF {s['v_lof_kts']:.1f} kt · "
            f"V2/V_S {s['v2_over_vs']:.3f} · k_VR {s['k_VR']:.2f} · "
            f"solve {d['solve_time_s']:.2f} s ({d['method'].upper()})",
            style={
                "fontSize": "13px",
                "marginTop": "8px",
                "color": "#0b0b0b" if s["balanced"] else "#b54600",
            },
        ),
        html.Ul(warn_items, style={"fontSize": "12px", "color": "#b54600", "margin": "6px 0 0"})
        if warn_items
        else html.Div(),
    ]


def create_app() -> Dash:
    app = Dash(__name__, title="BFL solver")
    app.layout = layout()

    @app.callback(
        Output("weight", "value"),
        Output("chute", "options"),
        Output("chute", "value"),
        Output("aircraft-note", "children"),
        Input("aircraft", "value"),
    )
    def on_aircraft(name):
        try:
            ac = load_aircraft(name)
        except Exception as exc:  # noqa: BLE001
            return (
                None,
                [{"label": " drag chute", "value": "on", "disabled": True}],
                [],
                f"Cannot load this aircraft (incomplete template?): {exc.__class__.__name__}",
            )
        has_chute = ac.chute.area_ft2 > 0 and ac.chute.CD > 0
        opts = [
            {"label": " drag chute (outside Part 25)", "value": "on", "disabled": not has_chute}
        ]
        note = "SYNTHETIC data - not a real airplane" if ac.synthetic else ""
        return ac.weight.default_weight_lbf, opts, (["on"] if ac.chute.enabled else []), note

    @app.callback(
        Output("current", "data"),
        Input("run", "n_clicks"),
        State("aircraft", "value"),
        State("k_cl", "value"),
        State("k_cd", "value"),
        State("mu_roll", "value"),
        State("mu_brake", "value"),
        State("headwind", "value"),
        State("slope", "value"),
        State("temperature", "value"),
        State("elevation", "value"),
        State("weight", "value"),
        State("rotation_rate", "value"),
        State("chute", "value"),
        State("method", "value"),
    )
    def on_run(
        _n,
        aircraft,
        k_cl,
        k_cd,
        mu_roll,
        mu_brake,
        headwind,
        slope,
        temp,
        elev,
        weight,
        q,
        chute,
        method,
    ):
        if not aircraft:
            return no_update
        ui = {
            "k_cl": k_cl,
            "k_cd": k_cd,
            "mu_roll": mu_roll,
            "mu_brake": mu_brake,
            "headwind": headwind,
            "slope": slope,
            "temperature": temp,
            "elevation": elev,
            "weight": weight,
            "rotation_rate": q,
            "chute": "on" in (chute or []),
            "method": method,
        }
        return compute.run(aircraft, ui)

    @app.callback(
        Output("baseline", "data"),
        Output("baseline-note", "children"),
        Input("pin", "n_clicks"),
        Input("clear", "n_clicks"),
        State("current", "data"),
        prevent_initial_call=True,
    )
    def on_pin(_p, _c, cur):
        if ctx.triggered_id == "clear" or not cur or not cur.get("ok"):
            return None, ""
        return cur, f"Baseline pinned: BFL {cur['scalars']['bfl_ft']:,.0f} ft"

    @app.callback(
        Output("readout", "children"),
        Output("bfl-chart", "figure"),
        Output("sensitivity", "figure"),
        Input("current", "data"),
        Input("baseline", "data"),
    )
    def on_result(cur, base):
        if not cur or not cur.get("ok"):
            e = figures.empty()
            return readout(cur, base), e, e
        return readout(cur, base), figures.bfl_chart(cur, base), figures.sensitivity(cur, base)

    @app.callback(
        Output("animation", "figure"),
        Input("current", "data"),
        Input("baseline", "data"),
        Input("exaggeration", "value"),
    )
    def on_anim(cur, base, exag):
        if not cur or not cur.get("ok"):
            return figures.empty()
        return figures.animation(cur, base, float(exag or 1))

    @app.callback(
        Output("time-history", "figure"),
        Input("current", "data"),
        Input("baseline", "data"),
        Input("th-tab", "value"),
        Input("th-branch", "value"),
    )
    def on_th(cur, base, tab, branch):
        if not cur or not cur.get("ok"):
            return figures.empty()
        return figures.time_history(cur, base, tab, branch)

    return app


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="BFL Dash app")
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    create_app().run(debug=a.debug, port=a.port)


if __name__ == "__main__":
    main()
