"""Aircraft data pages: where the example aircraft's data comes from, and whether the
model still matches the published numbers (status written by tests/test_validation.py)."""

from __future__ import annotations

from dash import dcc, html

from bfl.validation import data_hash, read_status

ASSET = "/assets"

DATA_PAGES = {
    "b747_100": {
        "route": "/data/b747",
        "menu": "Boeing 747-100",
        "title": "Boeing 747-100: where the data comes from",
        "intro": (
            "**NASA CR-114494** (1970), *The Simulation of a Jumbo Jet Transport Aircraft, "
            "Vol. II: Modeling Data*. This is the data package Boeing gave NASA to build its 747 "
            "flight simulator, and it includes the FAA-approved flight manual. It is free on "
            "NASA's technical reports server. "
            "The runway lengths used for validation come from **Boeing D6-58326**, "
            "*747 Airplane Characteristics for Airport Planning*, sec. 3.3.1 (FAR takeoff "
            "runway length, standard day, sea level). Full citations: `aircraft/b747_100/README.md`."  # noqa: E501
        ),
        "sources": [
            ("Lift", "data_sources/b747_100/cr114494_lift.png", "Boeing chart 2.0-7"),
            (
                "Drag",
                "data_sources/b747_100/cr114494_drag.png",
                "Boeing chart 3.0-5 (+ landing-gear drag, 3.0-15)",
            ),
            (
                "Thrust (JT9D-3)",
                "data_sources/b747_100/cr114494_thrust.png",
                "Boeing chart 12.2-3, at the flight-manual takeoff EPR",
            ),
        ],  # fmt: skip
        "differences": [
            "**No ground effect** in the baseline. With the Raymer ground-effect option on "
            "(span 195.7 ft, wing height ~16 ft, estimated), the error drops by about half "
            "(green dotted line).",
            "**Friction** is assumed (rolling 0.03, braking 0.30). Boeing's certified braking "
            "with anti-skid is not public; MIL-STD-3013 uses 0.38 for dry with anti-skid.",
            "**Engine version:** the model uses JT9D-3 thrust; Boeing's chart is for the JT9D-3A.",
            "**Estimates:** idle thrust, the spoiler lift/drag increments and the takeoff TSFC "
            "are not from a source.",
            "**Speeds and technique:** the model rotates at 3°/s to 1° below tail strike and "
            "raises VR until V2 ≥ 1.2 V_S. Boeing schedules VR/V2 from flight test, and uses "
            "flaps 10 at the heaviest weights.",
            "**The lightest point** (500 klb) is the only one where the model is shorter than "
            "Boeing. Boeing's curve flattens there, which suggests another limit (for example "
            "a minimum-control-speed limited V1) that the model does not have.",
            "**Digitizing** both the inputs and the Boeing curve adds roughly 1–2 %.",
        ],
        "not_tuned": "Nothing was tuned to match Boeing.",
    },
    "sr71": {
        "route": "/data/sr71",
        "menu": "Lockheed SR-71A",
        "title": "Lockheed SR-71A: where the data comes from",
        "intro": (
            "**USAF T.O. SR-71A-1**, *Flight Manual, SR-71A* (1989 revision, declassified), on "
            "the Internet Archive (item `0003756-lockheed-sr-71-03`). Lift and thrust are "
            "digitized from the manual. **The manual has no low-speed drag polar, so drag is an "
            "estimate.** The speeds used as a check come from Berry, Mallick & Gilyard, "
            "*Handling Qualities Aspects of NASA YF-12 Flight Experience* (NASA, 1977). Full "
            "citations: `aircraft/sr71/README.md`."
        ),
        "sources": [
            (
                "Lift",
                "data_sources/sr71/fm_fig6-2_lift.png",
                "Figure 6-2, wing lift vs angle of attack (in / out of ground effect)",
            ),
            (
                "Drag",
                None,
                "ESTIMATE, not digitized: CD = 0.028 + CL·tan(α_ind − α0). A thin, sharp-edged "
                "slender delta gets almost no leading-edge suction, so the drag due to lift is "
                "about CL·tan α. CD0 = 0.018 clean + 0.010 landing gear.",
            ),
            (
                "Thrust (J58, max A/B)",
                "data_sources/sr71/fm_fig1-3_thrust.png",
                "Figure 1-3, takeoff thrust vs indicated airspeed, five temperatures",
            ),
        ],  # fmt: skip
        "differences": [
            "Only **speeds** are checked: no SR-71 runway-length data was available.",
            "**Drag is estimated.** No published low-speed SR-71/YF-12 polar was found "
            "(NASA TM X-3532, sometimes cited, covers the XB-70).",
            "**The field never balances.** With one J58 out, the excess thrust at the 10° "
            "takeoff attitude is tiny, so the go from VR is always longer than the stop. "
            "Lowering the drag by 30 % does not change that, at any weight or under either "
            "rule set. That matches the flight manual's procedure: abort below rotation speed, "
            "continue above it.",
            "The SR-71 is military: MIL-STD-3013 is the natural rule set (chute optional).",
        ],
        "not_tuned": "Nothing was tuned to match the flight-test speeds.",
    },
}
ROUTES = {v["route"]: k for k, v in DATA_PAGES.items()}


def _badge(aircraft: str) -> html.Div:
    st = read_status(aircraft)
    if st is None:
        return html.Div(
            className="badge badge-missing",
            children="Not validated yet: run `pytest tests/test_validation.py` to generate "
            "the figures and the status.",
        )
    try:
        stale = st["data_hash"] != data_hash(aircraft)
    except Exception:  # noqa: BLE001
        stale = True
    ok = st["passed"]
    cls = "badge-stale" if stale else ("badge-pass" if ok else "badge-fail")
    word = "PASS" if ok else "FAIL"
    text = f"{word} · {st['tolerance']} · last run {st['timestamp'].replace('T', ' ')}"
    text += f" · commit {st['git_hash']}"
    if stale:
        text = "STALE: aircraft data changed since the last validation run. " + text
    return html.Div(className=f"badge {cls}", children=text)


def _checks_table(aircraft: str) -> html.Table | html.Div:
    st = read_status(aircraft)
    if st is None:
        return html.Div()
    head = html.Tr([html.Th(h) for h in ("check", "model", "reference", "error", "")])
    rows = []
    for c in st["checks"]:
        err = c["detail"] or f"{c['model'] - c['reference']:+.1f} {c['unit']}"
        rows.append(
            html.Tr(
                [
                    html.Td(c["name"]),
                    html.Td(f"{c['model']:,.0f} {c['unit']}"),
                    html.Td(f"{c['reference']:,.0f} {c['unit']}"),
                    html.Td(err),
                    html.Td("✓" if c["passed"] else "✗",
                            className="ok" if c["passed"] else "bad"),
                ]
            )
        )  # fmt: skip
    return html.Table(className="checks-table", children=[html.Thead(head), html.Tbody(rows)])


def render(route: str) -> html.Div:
    ac = ROUTES[route]
    pg = DATA_PAGES[ac]
    st = read_status(ac)
    ver = st["timestamp"] if st else "0"
    gen = f"{ASSET}/validation/{ac}"

    def src_col(title, img, caption):
        kids = [html.H4(title)]
        if img:
            kids.append(html.Img(src=f"{ASSET}/{img}", className="src-img"))
        else:
            kids.append(html.Div("no chart in the source", className="src-none"))
        kids.append(html.Div(caption, className="hint"))
        return html.Div(className="src-col", children=kids)

    generated = []
    if st:
        generated = [
            html.Div("↓ digitized into the tables the solver reads", className="arrow-note"),
            html.Div(
                className="gen-row",
                children=[
                    html.Img(src=f"{gen}/aero.png?v={ver}", className="gen-img"),
                    html.Img(src=f"{gen}/thrust.png?v={ver}", className="gen-img"),
                ],
            ),
        ]
    return html.Div(
        className="doc data-page",
        children=[
            html.H1(pg["title"]),
            _badge(ac),
            dcc.Markdown(pg["intro"]),
            html.H2("Source charts"),
            html.Div(className="src-row", children=[src_col(*s) for s in pg["sources"]]),
            *generated,
            html.H2("Validation"),
            html.Img(src=f"{gen}/validation.png?v={ver}", className="val-img") if st else None,
            _checks_table(ac),
            html.H3("Why the model can differ"),
            dcc.Markdown("\n".join(f"- {d}" for d in pg["differences"])),
            html.P(pg["not_tuned"], className="hint"),
            html.Div(className="doc-nav", children=[dcc.Link("← Simulator", href="/")]),
        ],
    )
