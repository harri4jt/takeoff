"""Takeoff Performance Explorer (Dash app on top of the bfl package).

python -m app            (or: python app/main.py)   then open http://127.0.0.1:8050
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python app/main.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "app"

import yaml  # noqa: E402
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update  # noqa: E402
from flask import abort, send_from_directory  # noqa: E402

from bfl import list_aircraft  # noqa: E402
from bfl.config import load_aircraft  # noqa: E402

from . import compute, figures, pages  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
DEFAULT_AIRCRAFT = "generic_widebody_synthetic"
TITLE = "Takeoff Performance Explorer"
HIDDEN = {"display": "none"}
GRAPH_CFG = {"displaylogo": False, "responsive": True}


def load_refs() -> list[dict]:
    try:
        data = yaml.safe_load((APP_DIR / "reference_runways.yaml").read_text())
        return sorted(data.get("references", []), key=lambda r: r["length_ft"])
    except (OSError, yaml.YAMLError, KeyError, TypeError):
        return []


# ------------------------------------------------------------------------------------
# inputs: sliders with a readable label and a live value
# ------------------------------------------------------------------------------------
def _signed(v: float, pos: str, neg: str, zero: str, unit: str, fmt: str = "{:.0f}") -> str:
    if abs(v) < 1e-9:
        return zero
    return f"{fmt.format(abs(v))}{unit} {pos if v > 0 else neg}"


# id: (label, symbol, min, max, step, default, marks, value formatter)
SLIDERS = {
    "k_cl": ("Lift multiplier", "k_CL", 0.8, 1.2, 0.01, 1.0, None, lambda v: f"{v:.2f}×"),
    "k_cd": ("Drag multiplier", "k_CD", 0.8, 1.2, 0.01, 1.0, None, lambda v: f"{v:.2f}×"),
    "headwind": (
        "Wind",
        "",
        -15,
        30,
        1,
        0,
        {-15: "−15", 0: "0", 30: "30"},
        lambda v: _signed(v, "headwind", "tailwind", "calm", " kt"),
    ),
    "slope": (
        "Runway slope",
        "",
        -2,
        2,
        0.1,
        0,
        {-2: "−2", 0: "0", 2: "2"},
        lambda v: _signed(v, "uphill", "downhill", "level", "°", "{:.1f}"),
    ),
    "temperature": (
        "Temperature",
        "",
        -20,
        120,
        1,
        59,
        {-20: "−20", 59: "ISA", 120: "120"},
        lambda v: f"{v:.0f} °F",
    ),
    "elevation": (
        "Field elevation",
        "",
        0,
        10000,
        100,
        0,
        {0: "0", 10000: "10k"},
        lambda v: f"{v:,.0f} ft",
    ),
    "mu_roll": ("Rolling friction", "μ", 0.01, 0.06, 0.005, 0.03, None, lambda v: f"{v:.3f}"),
    "mu_brake": (
        "Braking friction",
        "μ",
        0.1,
        0.6,
        0.01,
        0.30,
        {0.1: "0.1", 0.6: "0.6"},
        lambda v: f"{v:.2f}",
    ),
    "rotation_rate": (
        "Rotation rate",
        "",
        1,
        6,
        0.1,
        3,
        {1: "1", 3: "3", 6: "6"},
        lambda v: f"{v:.1f} °/s",
    ),
}
SLIDER_IDS = list(SLIDERS)

# demo scenarios: only the listed inputs differ from the defaults; weight None = aircraft default
PRESETS = {
    "standard": ("Standard day, sea level", {}),
    "hot_high": ("Hot & high (5,400 ft, 95 °F)", {"elevation": 5400, "temperature": 95}),
    "heavy": ("Heavy (850,000 lbf)", {"weight": 850000}),
    "tailwind": ("10 kt tailwind", {"headwind": -10}),
    "headwind": ("20 kt headwind", {"headwind": 20}),
    "slippery": ("Slippery runway (braking μ 0.20)", {"mu_brake": 0.20}),
    "uphill": ("1° uphill runway", {"slope": 1.0}),
}


def slider(id_: str) -> html.Div:
    label, sym, lo, hi, step, value, marks, fmt = SLIDERS[id_]
    head = [html.Span(label)]
    if sym:
        head.append(html.Span(f" ({sym})", className="sym"))
    return html.Div(
        className="ctl-row",
        children=[
            html.Div(
                className="ctl-head",
                children=[
                    html.Span(head, className="ctl-name"),
                    html.Span(fmt(value), id=f"{id_}-val", className="ctl-val"),
                ],
            ),
            dcc.Slider(
                id=id_,
                min=lo,
                max=hi,
                step=step,
                value=value,
                marks=marks or {lo: f"{lo:g}", hi: f"{hi:g}"},
                tooltip=None,
            ),
        ],
    )


def section(title: str, children: list) -> html.Div:
    return html.Div(
        className="ctl-section", children=[html.Div(title, className="sec-title"), *children]
    )


def controls() -> html.Div:
    try:
        names = list_aircraft()
    except FileNotFoundError:
        names = []
    default = DEFAULT_AIRCRAFT if DEFAULT_AIRCRAFT in names else (names[0] if names else None)
    return html.Div(
        className="card sidebar",
        children=[
            html.H3("Inputs"),
            html.Div(
                className="ctl-row",
                children=[
                    html.Div(
                        className="ctl-head",
                        children=html.Span("Demo scenario", className="ctl-name"),
                    ),
                    dcc.Dropdown(
                        id="preset",
                        clearable=False,
                        value="standard",
                        searchable=False,
                        options=[{"label": lab, "value": k} for k, (lab, _) in PRESETS.items()],
                    ),
                ],
            ),
            section(
                "Aircraft",
                [
                    html.Div(
                        className="ctl-row",
                        children=[
                            dcc.Dropdown(
                                id="aircraft",
                                options=[{"label": n, "value": n} for n in names],
                                value=default,
                                clearable=False,
                                searchable=False,
                            ),
                            html.Div(id="aircraft-note", className="note-synthetic"),
                        ],
                    ),
                    html.Div(
                        className="ctl-row",
                        children=[
                            html.Div(
                                className="ctl-head",
                                children=[
                                    html.Span("Takeoff weight", className="ctl-name"),
                                    html.Span("lbf", className="ctl-val"),
                                ],
                            ),
                            dcc.Input(
                                id="weight", type="number", debounce=True, className="num-input"
                            ),
                        ],
                    ),
                    slider("k_cl"),
                    slider("k_cd"),
                    html.Div(
                        ["Lift & drag curves: ", html.I("Engineering details › Aircraft data")],
                        className="hint",
                    ),
                ],
            ),
            section(
                "Runway & weather",
                [
                    slider(i)
                    for i in (
                        "headwind",
                        "slope",
                        "temperature",
                        "elevation",
                        "mu_brake",
                        "mu_roll",
                    )
                ],
            ),
            html.Details(
                className="ctl-section adv",
                children=[
                    html.Summary("Procedure & solver", className="sec-title"),
                    slider("rotation_rate"),
                    dcc.Checklist(
                        id="chute",
                        value=[],
                        className="checks",
                        options=[
                            {
                                "label": " Drag chute (outside Part 25)",
                                "value": "on",
                                "disabled": True,
                            }
                        ],
                    ),
                    dcc.Checklist(
                        id="enforce-v2",
                        value=["on"],
                        className="checks",
                        options=[{"label": " Enforce V2 ≥ 1.2 V_S (raises VR)", "value": "on"}],
                    ),
                    html.Div(
                        className="ctl-head",
                        style={"marginTop": "10px"},
                        children=html.Span("Integrator", className="ctl-name"),
                    ),
                    dcc.RadioItems(
                        id="method",
                        value="rk4",
                        className="checks",
                        options=[
                            {"label": " RK4, fixed step 0.01 s", "value": "rk4"},
                            {"label": " RK45 adaptive (faster)", "value": "rk45"},
                        ],
                    ),
                ],
            ),
            html.Button("Run", id="run", n_clicks=0, className="btn btn-primary btn-run"),
            html.Div(
                className="btn-row",
                children=[
                    html.Button("Pin as baseline", id="pin", n_clicks=0, className="btn"),
                    html.Button("Clear baseline", id="clear", n_clicks=0, className="btn"),
                ],
            ),
            html.Div(id="baseline-note", className="hint", style={"marginTop": "6px"}),
        ],
    )


# ------------------------------------------------------------------------------------
# page layout
# ------------------------------------------------------------------------------------
DETAIL_TABS = [
    ("trade", "V1 trade"),
    ("speeds", "Speeds"),
    ("forces", "Forces"),
    ("angles", "Angles"),
    ("positions", "Positions"),
    ("sensitivity", "Aero sensitivity"),
    ("aircraft", "Aircraft data"),
    ("summary", "Run summary"),
]

SCENE_HELP = {
    "failure": (
        "An engine fails at the worst moment. Both possible outcomes are drawn on the "
        "same runway: the blue aircraft continues the takeoff on the remaining engines, "
        "the orange one rejects it and brakes to a stop. Until the failure they are the "
        "same aircraft. Press ▶ Play."
    ),
    "aeo": (
        "The normal, all-engines takeoff. Part 25 adds a 15 % margin to its distance to "
        "35 ft; the FAA field length is the larger of that and the balanced field length. "
        "Press ▶ Play."
    ),
}


def tip(children, text: str, class_name: str = "", text_id: str | None = None) -> html.Span:
    """Hover tooltip (pure CSS): `children` with an explanation bubble."""
    bubble = html.Span(text, className="tip-text", **({"id": text_id} if text_id else {}))
    return html.Span(className=f"tip {class_name}", tabIndex="0", children=[children, bubble])


def sim_page() -> html.Div:
    return html.Div(
        className="sim-grid",
        children=[
            controls(),
            html.Div(
                className="main-col",
                children=[
                    html.Div(
                        className="card scene-card",
                        children=[
                            html.Div(
                                className="card-head",
                                children=[
                                    html.H3(
                                        "Engine failure at the worst moment: go or stop?",
                                        id="scene-title",
                                    ),
                                    tip(
                                        html.Span("ⓘ", className="info"),
                                        SCENE_HELP["failure"],
                                        "tip-down",
                                        "scene-help",
                                    ),
                                    html.Div(className="spacer"),
                                    dcc.RadioItems(
                                        id="scene-mode",
                                        value="failure",
                                        className="seg",
                                        inline=True,
                                        options=[
                                            {"label": "Engine failure", "value": "failure"},
                                            {"label": "All engines", "value": "aeo"},
                                        ],
                                    ),
                                    html.Button(
                                        "⚙",
                                        id="open-settings",
                                        n_clicks=0,
                                        title="Animation settings",
                                        className="btn btn-icon",
                                    ),
                                ],
                            ),
                            dcc.Loading(
                                dcc.Graph(
                                    id="scene",
                                    config={**GRAPH_CFG, "displayModeBar": False},
                                    style={"height": "600px"},
                                ),
                                type="circle",
                            ),
                            html.Div(id="readout"),
                        ],
                    ),
                    html.Div(
                        className="card",
                        children=[
                            html.Button(
                                id="details-toggle", n_clicks=0, className="details-toggle"
                            ),
                            html.Div(
                                id="details-body",
                                style=HIDDEN,
                                children=[
                                    dcc.Tabs(
                                        id="detail-tab",
                                        value="trade",
                                        children=[
                                            dcc.Tab(label=lab, value=v) for v, lab in DETAIL_TABS
                                        ],
                                    ),
                                    dcc.RadioItems(
                                        id="detail-branch",
                                        value="go",
                                        inline=True,
                                        className="checks",
                                        options=[
                                            {"label": " continued takeoff (go)  ", "value": "go"},
                                            {
                                                "label": " rejected takeoff (stop)  ",
                                                "value": "stop",
                                            },
                                            {"label": " all engines", "value": "aeo"},
                                        ],
                                    ),
                                    dcc.Loading(html.Div(id="detail-content"), type="dot"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def settings_modal() -> html.Div:
    return html.Div(
        id="settings",
        className="modal-backdrop",
        style=HIDDEN,
        children=[
            html.Div(
                className="modal",
                children=[
                    html.H3("Animation settings"),
                    html.Div(
                        "Display only: nothing here changes the computed distances.",
                        className="hint",
                    ),
                    html.Div(
                        className="ctl-head",
                        style={"marginTop": "14px"},
                        children=[
                            html.Span("Vertical exaggeration", className="ctl-name"),
                            html.Span(
                                className="ctl-val", children="heights are tiny next to the runway"
                            ),
                        ],
                    ),
                    dcc.Slider(
                        id="exaggeration",
                        min=1,
                        max=100,
                        step=1,
                        value=25,
                        marks={1: "×1", 25: "×25", 50: "×50", 100: "×100"},
                    ),
                    html.Div(
                        className="ctl-head",
                        style={"marginTop": "14px"},
                        children=html.Span("Playback speed", className="ctl-name"),
                    ),
                    dcc.RadioItems(
                        id="playback",
                        value=4,
                        inline=True,
                        className="checks",
                        options=[
                            {"label": f" ×{v} real time   ", "value": v} for v in (1, 2, 4, 8)
                        ],
                    ),
                    dcc.Checklist(
                        id="show-ghosts",
                        value=["on"],
                        className="checks",
                        style={"marginTop": "12px"},
                        options=[
                            {"label": " Show the pinned baseline as grey aircraft", "value": "on"}
                        ],
                    ),
                    dcc.Checklist(
                        id="autoplay",
                        value=[],
                        className="checks",
                        options=[{"label": " Play automatically after each Run", "value": "on"}],
                    ),
                    html.Div(
                        style={"textAlign": "right", "marginTop": "16px"},
                        children=html.Button(
                            "Done", id="close-settings", n_clicks=0, className="btn btn-primary"
                        ),
                    ),
                ],
            ),
        ],
    )


def topbar() -> html.Div:
    return html.Div(
        className="topbar",
        children=[
            dcc.Link(
                className="brand",
                href="/",
                children=[
                    html.Span(TITLE, className="brand-title"),
                    html.Span(
                        "balanced field length · engine-out go/stop · FAA Part 25 style",
                        className="brand-sub",
                    ),
                ],
            ),
            html.Div(className="spacer"),
            html.Button("☰", id="hamburger", n_clicks=0, className="hamburger", title="Menu"),
            html.Div(
                id="nav-menu", className="nav-menu", style=HIDDEN, children=pages.menu_links()
            ),
        ],
    )


def footer() -> html.Div:
    return html.Div(
        className="footer",
        children=html.Div(
            className="footer-inner",
            children=(
                "MATH 6006 Numerical Analysis project · every integrator, root finder and "
                "interpolant is hand-written · the generic widebody's data are SYNTHETIC · "
                "a low-fidelity "
                "estimator, not for operational use"
            ),
        ),
    )


def sky() -> html.Div:
    return html.Div(
        className="sky", children=[html.Div(className=f"cloud c{i}") for i in range(1, 10)]
    )


def layout() -> html.Div:
    return html.Div(
        className="app-root",
        children=[
            dcc.Location(id="url"),
            dcc.Store(id="current"),
            dcc.Store(id="baseline"),
            dcc.Store(id="heat"),
            dcc.Store(id="details-open", data=False),
            dcc.Store(id="autoplay-sink"),
            sky(),
            topbar(),
            html.Div(
                className="content",
                children=[
                    html.Div(id="sim-page", children=sim_page()),
                    html.Div(id="doc-page"),
                ],
            ),
            footer(),
            settings_modal(),
        ],
    )


# ------------------------------------------------------------------------------------
# readout under the animation
# ------------------------------------------------------------------------------------
def readout(d: dict | None, base: dict | None) -> list:
    if not d:
        return [html.Div("Set inputs and press Run.", className="hint")]
    if not d.get("ok"):
        return [
            html.Div("Computation failed", className="error-box", style={"fontWeight": 600}),
            html.Pre(d["error"], style={"whiteSpace": "pre-wrap", "fontSize": "12px"}),
        ]
    s = d["scalars"]
    b = base["scalars"] if base and base.get("ok") else None
    aeo115 = 1.15 * s["aeo_distance_ft"]

    if s["balanced"]:
        bfl_tip = (
            f"The engine fails at {s['v_ef_kts']:.0f} kt; about a second later, at the "
            f"decision speed V1 = {s['v1_kts']:.0f} kt, the crew either continues or "
            f"stops. With this V1 both need the same runway: {s['bfl_ft']:,.0f} ft. "
            f"The stop includes a 2-second allowance (~{d['allowance_ft']:,.0f} ft) that "
            "is added on paper, not flown, which is why the orange aircraft stops short "
            "of the red line."
        )
    else:
        bfl_tip = (
            f"Unbalanced: {s['unbalanced_reason']}. No V1 makes go and stop equal, so the "
            "longer of the two sets the field length."
        )
    governs = (
        "The all-engines rule governs."
        if aeo115 > s["bfl_ft"]
        else "The balanced field length governs."
    )
    faa_tip = (
        f"Part 25 takes the larger of the balanced field length ({s['bfl_ft']:,.0f} ft) "
        f"and 1.15 × the all-engines distance to 35 ft "
        f"(1.15 × {s['aeo_distance_ft']:,.0f} = {aeo115:,.0f} ft). {governs} "
        "Switch the animation to 'All engines' to see the 15 % margin."
    )
    aeo_tip = (
        "Distance from brake release to 35 ft with every engine working: the normal "
        f"takeoff, rotating at the same VR = {s['vr_kts']:.0f} kt. Part 25 adds a 15 % "
        "margin to it."
    )

    def metric(
        label: str, key: str, text: str, color: str | None = None, small: bool = False
    ) -> html.Div:
        delta = f"{s[key] - b[key]:+,.0f} ft vs baseline" if b is not None else ""
        lab = [html.Span(className="swatch", style={"background": color})] if color else []
        return tip(
            html.Div(
                className="metric small" if small else "metric",
                children=[
                    html.Div(
                        [*lab, label, html.Span(" ⓘ", className="info-sm")], className="m-label"
                    ),
                    html.Div(
                        f"{s[key]:,.0f} ft",
                        className="m-value",
                        style={"color": color} if color else None,
                    ),
                    html.Div(delta, className="m-delta"),
                ],
            ),
            text,
            "tip-up",
        )

    chips = []
    if not s["balanced"]:
        chips.append("Unbalanced field")
    if s["chute_used"]:
        chips.append("Drag chute credited (outside Part 25)")
    if any(a.get("reason") == "touchback" for a in d["vr_adjustments"]):
        chips.append("VR raised: the aircraft settled back onto the runway")
    chips += [w for w in d["warnings"] if w.startswith("V2/V_S")]
    return [
        html.Div(
            className="results",
            children=[
                metric("Balanced field length", "bfl_ft", bfl_tip, figures.BFL_C),
                metric("FAA takeoff field length", "faa_field_length_ft", faa_tip, figures.FAA_C),
                metric("All engines to 35 ft", "aeo_distance_ft", aeo_tip, small=True),
            ],
        ),
        html.Div([html.Span(c, className="chip") for c in chips], className="chips")
        if chips
        else html.Div(),
    ]


# ------------------------------------------------------------------------------------
# app
# ------------------------------------------------------------------------------------
AUTOPLAY_JS = """
function(fig, auto) {
    if (!fig || !auto || auto.length === 0) { return window.dash_clientside.no_update; }
    var dur = 40;
    try { dur = fig.layout.updatemenus[0].buttons[0].args[1].frame.duration; } catch (e) {}
    setTimeout(function () {
        var gd = document.querySelector('#scene .js-plotly-plot');
        if (gd && window.Plotly) {
            window.Plotly.animate(gd, null, {frame: {duration: dur, redraw: false},
                                             transition: {duration: 0}, mode: 'immediate'});
        }
    }, 700);
    return window.dash_clientside.no_update;
}
"""


def create_app() -> Dash:
    app = Dash(
        __name__,
        title=TITLE,
        assets_folder=str(APP_DIR / "assets"),
        suppress_callback_exceptions=True,
        update_title=None,
    )
    app.layout = layout()
    refs = load_refs()

    @app.server.route("/verification/<path:name>")
    def verification_png(name: str):
        if not (pages.VERIFICATION_DIR / name).is_file():
            abort(404)
        return send_from_directory(pages.VERIFICATION_DIR, name)

    # ---- routing and menus -----------------------------------------------------------
    @app.callback(
        Output("sim-page", "style"),
        Output("doc-page", "children"),
        Output("nav-menu", "style", allow_duplicate=True),
        Input("url", "pathname"),
        prevent_initial_call="initial_duplicate",
    )
    def route(path):
        if path in (None, "", "/"):
            return {}, None, HIDDEN
        return HIDDEN, pages.render(path), HIDDEN

    @app.callback(
        Output("nav-menu", "style"),
        Input("hamburger", "n_clicks"),
        State("nav-menu", "style"),
        prevent_initial_call=True,
    )
    def toggle_menu(_n, style):
        return {} if style == HIDDEN else HIDDEN

    @app.callback(
        Output("settings", "style"),
        Input("open-settings", "n_clicks"),
        Input("close-settings", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_settings(_o, _c):
        return {"display": "flex"} if ctx.triggered_id == "open-settings" else HIDDEN

    @app.callback(
        Output("details-open", "data"),
        Output("details-body", "style"),
        Output("details-toggle", "children"),
        Input("details-toggle", "n_clicks"),
    )
    def toggle_details(n):
        is_open = bool(n and n % 2)
        label = [
            ("▾ " if is_open else "▸ ") + "Engineering details",
            html.Span(
                "V1 trade · speeds · forces · angles · aero sensitivity · "
                "aircraft data · run summary",
                className="sub",
            ),
        ]
        return is_open, ({} if is_open else HIDDEN), label

    # ---- inputs ------------------------------------------------------------------------
    for sid in SLIDER_IDS:
        fmt = SLIDERS[sid][7]

        @app.callback(Output(f"{sid}-val", "children"), Input(sid, "value"))
        def _show(v, fmt=fmt):
            return "" if v is None else fmt(v)

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
                [{"label": " Drag chute", "value": "on", "disabled": True}],
                [],
                f"Cannot load this aircraft (incomplete template?): {exc.__class__.__name__}",
            )
        has_chute = ac.chute.area_ft2 > 0 and ac.chute.CD > 0
        opts = [
            {"label": " Drag chute (outside Part 25)", "value": "on", "disabled": not has_chute}
        ]
        note = "SYNTHETIC data: not a real airplane" if ac.synthetic else ""
        return ac.weight.default_weight_lbf, opts, (["on"] if ac.chute.enabled else []), note

    @app.callback(
        *[Output(i, "value", allow_duplicate=True) for i in SLIDER_IDS],
        Output("weight", "value", allow_duplicate=True),
        Input("preset", "value"),
        State("aircraft", "value"),
        prevent_initial_call=True,
    )
    def on_preset(key, aircraft):
        changes = PRESETS.get(key, ("", {}))[1]
        vals = [changes.get(i, SLIDERS[i][5]) for i in SLIDER_IDS]
        weight = changes.get("weight")
        if weight is None:
            try:
                weight = load_aircraft(aircraft).weight.default_weight_lbf
            except Exception:  # noqa: BLE001
                weight = no_update
        return *vals, weight

    @app.callback(
        Output("current", "data"),
        Input("run", "n_clicks"),
        State("aircraft", "value"),
        *[State(i, "value") for i in SLIDER_IDS],
        State("weight", "value"),
        State("chute", "value"),
        State("enforce-v2", "value"),
        State("method", "value"),
    )
    def on_run(_n, aircraft, *rest):
        if not aircraft:
            return no_update
        vals = dict(zip(SLIDER_IDS, rest[: len(SLIDER_IDS)], strict=True))
        weight, chute, enforce, method = rest[len(SLIDER_IDS) :]
        ui = {
            **vals,
            "weight": weight,
            "chute": "on" in (chute or []),
            "enforce_v2": "on" in (enforce or []),
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

    # ---- main outputs ------------------------------------------------------------------
    @app.callback(
        Output("readout", "children"), Input("current", "data"), Input("baseline", "data")
    )
    def on_readout(cur, base):
        return readout(cur, base)

    @app.callback(
        Output("scene-title", "children"),
        Output("scene-help", "children"),
        Input("scene-mode", "value"),
    )
    def on_mode(mode):
        if mode == "aeo":
            return "All engines: where the FAA field length comes from", SCENE_HELP["aeo"]
        return "Engine failure at the worst moment: go or stop?", SCENE_HELP["failure"]

    @app.callback(
        Output("scene", "figure"),
        Input("current", "data"),
        Input("baseline", "data"),
        Input("exaggeration", "value"),
        Input("playback", "value"),
        Input("show-ghosts", "value"),
        Input("scene-mode", "value"),
    )
    def on_scene(cur, base, exag, speed, ghosts, mode):
        if not cur or not cur.get("ok"):
            return figures.empty("No result to animate" if cur else "Computing…", 600)
        return figures.scene(
            cur,
            base,
            refs,
            float(exag or 1),
            float(speed or 4),
            "on" in (ghosts or []),
            mode or "failure",
        )

    app.clientside_callback(
        AUTOPLAY_JS,
        Output("autoplay-sink", "data"),
        Input("scene", "figure"),
        State("autoplay", "value"),
    )

    # ---- details panel -----------------------------------------------------------------
    @app.callback(Output("detail-branch", "style"), Input("detail-tab", "value"))
    def on_branch_visible(tab):
        return {} if tab in ("forces", "angles") else HIDDEN

    @app.callback(
        Output("heat", "data"),
        Input("heat-run", "n_clicks"),
        State("current", "data"),
        prevent_initial_call=True,
    )
    def on_heat(n, cur):
        if not n or not cur or not cur.get("ok"):
            return no_update
        return {"cfg_json": cur["cfg_json"], "hm": compute.heatmap(cur["cfg_json"])}

    @app.callback(
        Output("detail-content", "children"),
        Input("details-open", "data"),
        Input("current", "data"),
        Input("baseline", "data"),
        Input("detail-tab", "value"),
        Input("detail-branch", "value"),
        Input("heat", "data"),
    )
    def on_details(is_open, cur, base, tab, branch, heat):
        if not is_open:
            return no_update
        if not cur or not cur.get("ok"):
            return html.Div("No result yet.", className="hint")
        base_ok = base if base and base.get("ok") else None
        note = None
        if tab == "trade":
            sw = compute.sweep(cur["cfg_json"], cur["scalars"]["k_VR"])
            bsw = (
                compute.sweep(base_ok["cfg_json"], base_ok["scalars"]["k_VR"]) if base_ok else None
            )
            fig = figures.v1_trade(cur, sw, base_ok, bsw)
            note = (
                "Each point is a full go + stop simulation at that V1 (RK45). The crossing "
                "is the balanced field length; the solver finds it by the secant method "
                "without drawing this curve."
            )
        elif tab == "speeds":
            fig = figures.speeds(cur, base_ok)
            note = "Equivalent airspeed (KEAS, ≈ what the cockpit airspeed indicator shows)."
        elif tab in ("forces", "angles"):
            fig = figures.forces_angles(cur, base_ok, tab, branch)
        elif tab == "positions":
            fig = figures.positions(cur, base_ok)
        elif tab == "sensitivity":
            fresh = heat and heat.get("cfg_json") == cur["cfg_json"]
            button = html.Button(
                "Recompute sensitivity map" if heat else "Compute sensitivity map",
                id="heat-run",
                n_clicks=0,
                className="btn btn-primary",
            )
            intro = html.Div(
                className="heat-intro",
                children=[
                    button,
                    html.Span(
                        "25 complete BFL solves (RK45, V2 rule applied) over k_CL × k_CD, "
                        "other inputs as in the current run. Takes a second or two.",
                        className="hint",
                    ),
                ],
            )
            if not fresh:
                stale = (
                    html.Div(
                        "Inputs changed since the last map: recompute to update it.",
                        className="chip",
                    )
                    if heat
                    else html.Div()
                )
                return [intro, stale]
            fig = figures.heatmap(heat["hm"], cur, base_ok)
            children = [
                intro,
                dcc.Graph(figure=fig, config=GRAPH_CFG),
                html.Div(
                    f"Computed in {heat['hm']['time_s']:.1f} s. Lift matters more "
                    "than drag because k_CL also moves the stall speed, and with it "
                    "VR and V2.",
                    className="hint",
                ),
            ]
            return children
        elif tab == "aircraft":
            fig = figures.aircraft(compute.aircraft_data(cur["cfg_json"]))
            note = (
                "Curves exactly as the solver sees them, multipliers included. The table is "
                "interpolated linearly by default (cubic spline available in the config)."
            )
        else:
            s = cur["scalars"]
            facts = (
                f"k_VR {s['k_VR']:.3f} · {cur['method'].upper()} solve {cur['solve_time_s']:.2f} s"
            )
            return [
                html.Div(facts, className="hint"),
                html.Pre(cur["summary"], style={"fontSize": "13px", "whiteSpace": "pre-wrap"}),
            ]
        children = [dcc.Graph(figure=fig, config=GRAPH_CFG)]
        if note:
            children.append(html.Div(note, className="hint"))
        return children

    return app


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=TITLE)
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    create_app().run(debug=a.debug, port=a.port)


if __name__ == "__main__":
    main()
