"""Takeoff Performance Explorer (Dash app on top of the bfl package).

python -m app            (or: python app/main.py)   then open http://127.0.0.1:8050
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python app/main.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "app"

import json  # noqa: E402

import yaml  # noqa: E402
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update  # noqa: E402
from flask import abort, send_from_directory  # noqa: E402

from bfl import list_aircraft  # noqa: E402
from bfl.config import load_aircraft  # noqa: E402

from . import builder, compute, datapages, figures, limits, pages, trade  # noqa: E402

APP_DIR = Path(__file__).resolve().parent
DEFAULT_AIRCRAFT = "b747_100"
SYNTHETIC_AIRCRAFT = {"generic_widebody_synthetic"}

# MIL-STD-3013 Table II (dry value for bias-ply tyres): (rolling, braked, braked w/ anti-skid)
RUNWAY_CONDITIONS = {
    "dry": ("Dry (RCR 23)", 0.025, 0.30, 0.38),
    "wet": ("Wet (RCR 15)", 0.050, 0.20, 0.25),
    "wet_snow": ("Wet snow (RCR 11)", 0.090, 0.14, 0.18),
    "wet_ice": ("Wet ice (RCR 7)", 0.050, 0.09, 0.12),
}
RULE_DELAY = {"part25": 1.0, "mil3013": 3.0}
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
    "mu_roll": ("Rolling friction", "μ", 0.01, 0.10, 0.005, 0.03, None, lambda v: f"{v:.3f}"),
    "mu_brake": (
        "Braking friction",
        "μ",
        0.05,
        0.6,
        0.01,
        0.30,
        {0.05: "0.05", 0.6: "0.6"},
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
    "heavy": ("Heavy (+10 % weight)", {"weight_factor": 1.10}),
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


def aircraft_options(show_synthetic: bool) -> list[dict]:
    try:
        names = list_aircraft()
    except FileNotFoundError:
        names = []
    return [
        {"label": n, "value": n} for n in names if show_synthetic or n not in SYNTHETIC_AIRCRAFT
    ]


def labeled(label: str, child, unit: str = "", row_id: str | None = None, hint: str = ""):
    head = [html.Span(label, className="ctl-name")]
    if unit:
        head.append(html.Span(unit, className="ctl-val"))
    kids = [html.Div(className="ctl-head", children=head), child]
    if hint:
        kids.append(html.Div(hint, className="hint"))
    return html.Div(className="ctl-row", id=row_id or f"row-{id(child)}", children=kids)


def controls() -> html.Div:
    opts = aircraft_options(False)
    names = [o["value"] for o in opts]
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
                "Field-length rules",
                [
                    dcc.RadioItems(
                        id="rules",
                        value="part25",
                        className="seg rules-seg",
                        inline=True,
                        options=[
                            {"label": "FAA Part 25", "value": "part25"},
                            {"label": "MIL-STD-3013", "value": "mil3013"},
                        ],
                    ),
                    labeled(
                        "Engine failure → action delay",
                        dcc.Input(
                            id="t-recog",
                            type="number",
                            min=0,
                            step=0.1,
                            value=1.0,
                            debounce=True,
                            className="num-input",
                        ),
                        "s",
                        "row-t-recog",
                        hint="",
                    ),
                    html.Div(id="rules-note", className="hint"),
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
                                options=opts,
                                value=default,
                                clearable=False,
                                searchable=False,
                            ),
                            dcc.Checklist(
                                id="show-synthetic",
                                value=[],
                                className="checks small",
                                options=[{"label": " show synthetic test aircraft", "value": "on"}],
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
                    labeled(
                        "Thrust table",
                        dcc.Dropdown(id="thrust-table", clearable=False, searchable=False),
                        row_id="row-thrust",
                    ),
                    labeled(
                        "Aero table",
                        dcc.Dropdown(id="aero-config", clearable=False, searchable=False),
                        row_id="row-aero",
                    ),
                    slider("k_cl"),
                    slider("k_cd"),
                    dcc.Checklist(
                        id="ground-effect",
                        value=[],
                        className="checks",
                        options=[{"label": " Ground effect (Raymer)", "value": "on"}],
                    ),
                    html.Div(
                        ["Lift & drag curves: ", html.I("Engineering details › Aircraft data")],
                        className="hint",
                    ),
                ],
            ),
            section(
                "Runway & weather",
                [
                    *[slider(i) for i in ("headwind", "slope", "temperature", "elevation")],
                    labeled(
                        "Runway condition",
                        html.Div(
                            className="cond-row",
                            children=[
                                dcc.Dropdown(
                                    id="runway-cond",
                                    value="custom",
                                    clearable=False,
                                    searchable=False,
                                    options=[
                                        *[
                                            {"label": v[0], "value": k}
                                            for k, v in RUNWAY_CONDITIONS.items()
                                        ],
                                        {"label": "Custom", "value": "custom"},
                                    ],
                                ),
                                dcc.Checklist(
                                    id="antiskid",
                                    value=["on"],
                                    className="checks",
                                    options=[{"label": " anti-skid", "value": "on"}],
                                ),
                            ],
                        ),
                        row_id="row-cond",
                        hint="Presets from MIL-STD-3013 Table II; editing a slider → Custom.",
                    ),
                    slider("mu_brake"),
                    slider("mu_roll"),
                    labeled(
                        "Runway available (optional)",
                        dcc.Input(
                            id="runway-avail",
                            type="number",
                            min=0,
                            step=100,
                            debounce=True,
                            placeholder="for refusal speed",
                            className="num-input",
                        ),
                        "ft",
                        "row-avail",
                    ),
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
    ("limits", "Gear & limits"),
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
                        "balanced / critical field length · engine-out go/stop · "
                        "Part 25 & MIL-STD-3013",
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
                "Conceptual-design takeoff estimator · started as a MATH 6006 numerical "
                "analysis project: every integrator, root finder and interpolant is "
                "hand-written · not for operational use"
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
            dcc.Store(id="details-open", data=False),
            dcc.Store(id="aircraft-saved"),
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
    nm = figures.names(s)
    mil = s.get("rules") == "mil3013"
    b = base["scalars"] if base and base.get("ok") else None
    f = s["field_length_aeo_factor"]
    h = f"{s['screen_height_ft']:.0f} ft"
    aeo_f = f * s["aeo_distance_ft"]

    if s["balanced"] and mil:
        bfl_tip = (
            f"MIL-STD-3013: the critical engine fails at V_CEF = {s['v_ef_kts']:.0f} kt. "
            f"The aircraft accelerates for {s['t_recog_s']:g} s on the remaining engines "
            f"(to {s['v1_kts']:.0f} kt), then brakes are applied. At this V_CEF the stop and "
            f"the engine-out climb to {h} need the same runway: {s['bfl_ft']:,.0f} ft. "
            "No distance pad is added."
        )
    elif s["balanced"]:
        bfl_tip = (
            f"The engine fails at {s['v_ef_kts']:.0f} kt; {s['t_recog_s']:g} s later, at the "
            f"decision speed V1 = {s['v1_kts']:.0f} kt, the crew either continues or "
            f"stops. With this V1 both need the same runway: {s['bfl_ft']:,.0f} ft. "
            f"The stop includes a 2-second allowance (~{d['allowance_ft']:,.0f} ft) that "
            "is added on paper, not flown, which is why the orange aircraft stops short "
            "of the red line."
        )
    else:
        bfl_tip = (
            f"Unbalanced: {s['unbalanced_reason']}. No engine-failure speed makes go and stop "
            "equal, so the longer of the two sets the field length."
        )
    governs = (
        "The all-engines distance governs."
        if aeo_f > s["bfl_ft"]
        else f"The {nm['bfl'].lower()} governs."
    )
    if f > 1.0:
        faa_tip = (
            f"The larger of the {nm['bfl'].lower()} ({s['bfl_ft']:,.0f} ft) and {f:g} × the "
            f"all-engines distance to {h} ({f:g} × {s['aeo_distance_ft']:,.0f} = "
            f"{aeo_f:,.0f} ft). {governs} Switch the animation to 'All engines' to see the margin."
        )
    else:
        faa_tip = (
            f"The larger of the critical field length ({s['bfl_ft']:,.0f} ft) and the "
            f"all-engines total takeoff distance to {h} ({s['aeo_distance_ft']:,.0f} ft), "
            f"with no extra factor. {governs}"
        )
    aeo_tip = (
        f"Distance from brake release to {h} with every engine working: the normal "
        f"takeoff, rotating at the same VR = {s['vr_kts']:.0f} kt."
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
        chips.append("Drag chute credited" + ("" if mil else " (outside Part 25)"))
    if any(a.get("reason") == "touchback" for a in d["vr_adjustments"]):
        chips.append("VR raised: the aircraft settled back onto the runway")
    chips += [w for w in d["warnings"] if w.startswith(("V2/V_S", "V_LO", "V_CEF", "runway"))]
    try:
        own = json.loads(d["cfg_json"])["aircraft"].get("gear")
    except (KeyError, ValueError, TypeError):
        own = None
    limit_chips = limits.warnings(s, own)

    facts = [
        ("V_EF" if not mil else "V_CEF", f"{s['v_ef_kts']:.0f} kt"),
        ("V1" if not mil else "brakes", f"{s['v1_kts']:.0f} kt"),
        ("VR", f"{s['vr_kts']:.0f} kt"),
        ("V2" if not mil else "V_obs", f"{s['v2_kts']:.0f} kt"),
        ("tires max", f"{s['max_tire_speed_kts']:.0f} kt"),
        ("brake energy", f"{s['brake_energy_MJ']:,.0f} MJ"),
    ]
    if s.get("fuel_used_go_lbf", 0) > 0:
        facts.append(("fuel, OEI go", f"{s['fuel_used_go_lbf']:,.0f} lb"))
    if s.get("refusal_v_ef_kts") is not None:
        facts.append(
            (
                f"refusal speed ({s['runway_available_ft']:,.0f} ft)",
                f"{s['refusal_v_ef_kts']:.0f} kt",
            )
        )
    return [
        html.Div(
            className="results",
            children=[
                metric(nm["bfl"], "bfl_ft", bfl_tip, figures.BFL_C),
                metric(nm["field"], "faa_field_length_ft", faa_tip, figures.FAA_C),
                metric(f"All engines to {h}", "aeo_distance_ft", aeo_tip, small=True),
            ],
        ),
        html.Div(
            className="facts",
            children=[
                html.Span(
                    [html.Span(k, className="f-k"), html.Span(v, className="f-v")], className="fact"
                )
                for k, v in facts
            ],
        ),  # fmt: skip
        html.Div(
            [html.Span(c, className="chip") for c in chips]
            + [html.Span("⚠ " + c, className="chip chip-warn") for c in limit_chips],
            className="chips",
        ),
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

    trade.register(app, aircraft_options)
    builder.register(app)

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
        if path == "/trade":
            return HIDDEN, trade.layout(), HIDDEN
        if path == "/builder":
            return HIDDEN, builder.layout(), HIDDEN
        if path in datapages.ROUTES:
            return HIDDEN, datapages.render(path), HIDDEN
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
                "V1 trade · speeds · forces · angles · gear & limits · aircraft data · run summary",
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
        Output("aircraft", "options"),
        Input("show-synthetic", "value"),
        Input("aircraft-saved", "data"),
    )
    def on_show_synthetic(v, _saved):
        return aircraft_options("on" in (v or []))

    @app.callback(
        Output("weight", "value"),
        Output("aircraft-note", "children"),
        Output("thrust-table", "options"),
        Output("thrust-table", "value"),
        Output("row-thrust", "style"),
        Output("aero-config", "options"),
        Output("aero-config", "value"),
        Output("row-aero", "style"),
        Output("ground-effect", "options"),
        Output("ground-effect", "value"),
        Input("aircraft", "value"),
    )
    def on_aircraft(name):
        ge_off = [{"label": " Ground effect (Raymer)", "value": "on", "disabled": True}]
        try:
            ac = load_aircraft(name)
        except Exception as exc:  # noqa: BLE001
            return (
                None,
                f"Cannot load this aircraft (incomplete template?): {exc.__class__.__name__}",
                [], None, HIDDEN, [], None, HIDDEN, ge_off, [],
            )  # fmt: skip
        note = "SYNTHETIC data: not a real airplane" if ac.synthetic else ""
        thr = ac.engines.thrust_options()
        t_opts = [{"label": k, "value": v} for k, v in thr.items()]
        a_opts = [{"label": k, "value": k} for k in ac.aero.configurations]
        ge = ac.ground_effect
        has_geo = ge.span_ft is not None and ge.wing_height_ft is not None
        ge_opts = [
            {
                "label": " Ground effect (Raymer)"
                + ("" if has_geo else ": needs span & wing height"),
                "value": "on",
                "disabled": not has_geo,
            }
        ]
        return (
            ac.weight.default_weight_lbf,
            note,
            t_opts,
            ac.engines.thrust_table,
            {} if len(t_opts) > 1 else HIDDEN,
            a_opts,
            ac.aero.takeoff_configuration,
            {} if len(a_opts) > 1 else HIDDEN,
            ge_opts,
            ["on"] if ge.enabled else [],
        )

    @app.callback(
        Output("chute", "options"),
        Output("chute", "value"),
        Output("t-recog", "value"),
        Output("rules-note", "children"),
        Input("aircraft", "value"),
        Input("rules", "value"),
    )
    def on_rules(name, rules):
        mil = rules == "mil3013"
        try:
            ac = load_aircraft(name)
            has_chute = ac.chute.area_ft2 > 0 and ac.chute.CD > 0
            default_on = ac.chute.enabled and not mil
        except Exception:  # noqa: BLE001
            has_chute, default_on = False, False
        label = " Drag chute" + ("" if mil else " (outside Part 25)")
        opts = [{"label": label, "value": "on", "disabled": not has_chute}]
        note = (
            "Critical field length: engine fails at V_CEF, brakes after the delay, no "
            "distance pad, go to 50 ft, chute optional."
            if mil
            else "Balanced field length: V_EF → V1 after the delay, +2 s pad on the stop, "
            "go to 35 ft, field ≥ 1.15 × all-engines."
        )
        no_t = ctx.triggered_id == "aircraft"
        return (
            opts,
            (["on"] if default_on else []),
            (no_update if no_t else RULE_DELAY[rules]),
            note,
        )

    @app.callback(
        Output("runway-cond", "value"),
        Output("mu_roll", "value"),
        Output("mu_brake", "value"),
        Input("runway-cond", "value"),
        Input("antiskid", "value"),
        Input("mu_roll", "value"),
        Input("mu_brake", "value"),
        prevent_initial_call=True,
    )
    def on_friction(cond, antiskid, mu_roll, mu_brake):
        trig = ctx.triggered_id
        if trig in ("runway-cond", "antiskid"):
            if cond not in RUNWAY_CONDITIONS:
                return no_update, no_update, no_update
            _, roll, brake, brake_as = RUNWAY_CONDITIONS[cond]
            return no_update, roll, (brake_as if "on" in (antiskid or []) else brake)
        if cond in RUNWAY_CONDITIONS:  # a slider moved: does it still match the preset?
            _, roll, brake, brake_as = RUNWAY_CONDITIONS[cond]
            b = brake_as if "on" in (antiskid or []) else brake
            if abs((mu_roll or 0) - roll) > 1e-9 or abs((mu_brake or 0) - b) > 1e-9:
                return "custom", no_update, no_update
        return no_update, no_update, no_update

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
        try:
            weight = load_aircraft(aircraft).weight.default_weight_lbf
            weight *= changes.get("weight_factor", 1.0)
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
        State("rules", "value"),
        State("t-recog", "value"),
        State("runway-avail", "value"),
        State("thrust-table", "value"),
        State("aero-config", "value"),
        State("ground-effect", "value"),
    )
    def on_run(_n, aircraft, *rest):
        if not aircraft:
            return no_update
        vals = dict(zip(SLIDER_IDS, rest[: len(SLIDER_IDS)], strict=True))
        weight, chute, enforce, rules, t_recog, avail, thrust, aero, ge = rest[len(SLIDER_IDS) :]
        ui = {
            **vals,
            "weight": weight,
            "chute": "on" in (chute or []),
            "enforce_v2": "on" in (enforce or []),
            "rules": rules or "part25",
            "t_recog": t_recog,
            "runway_avail": avail or None,
            "thrust_table": thrust,
            "aero_config": aero,
            "ground_effect": "on" in (ge or []),
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
        Output("detail-content", "children"),
        Input("details-open", "data"),
        Input("current", "data"),
        Input("baseline", "data"),
        Input("detail-tab", "value"),
        Input("detail-branch", "value"),
    )
    def on_details(is_open, cur, base, tab, branch):
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
        elif tab == "limits":
            fig = figures.limit_strips(limits.strips(cur["scalars"]))
            note = [
                "Ticks: reference aircraft from ",
                html.Code("app/reference_aircraft.yaml"),
                " (edit it to add aircraft or metrics; values there are placeholders). "
                "Orange ticks raise a warning when exceeded. Diamond: this run. "
                "Tire speed is the highest ground speed on the wheels in any branch; brake "
                "energy is the integral of μ·N·V over the braking part of the rejected takeoff.",
            ]
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
