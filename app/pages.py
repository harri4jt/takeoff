"""Documentation pages: the markdown files in docs/ rendered inside the app.

Images in the markdown point at ``../../output/verification/<name>.png`` (so they also
work when the file is viewed on disk); here they are rewritten to the Flask route
``/verification/<name>.png``. Links between the markdown files become app routes.
"""

from __future__ import annotations

import re
from pathlib import Path

from dash import dcc, html

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
VERIFICATION_DIR = ROOT / "output" / "verification"

# Two documentation pages. Each is a list of sections: (anchor, index title, markdown file).
DOC_PAGES: dict[str, tuple[str, str, list[tuple[str, str, Path]]]] = {
    "/about": (
        "About",
        "What the tool answers, what it needs, how to use it, and what it assumes.",
        [
            ("overview", "Overview", DOCS / "overview.md"),
            ("faq", "Questions and answers", DOCS / "faq.md"),
            ("aircraft-data", "Aircraft data (files, tables, every field)",
             DOCS / "aircraft_data.md"),
            ("python", "Using it from Python (scripts, trade studies)",
             DOCS / "python_usage.md"),
            ("rules", "Field-length rules: Part 25 vs MIL-STD-3013",
             DOCS / "field_length_rules.md"),
            ("rotation-speed", "Rotation speed and VR optimization",
             DOCS / "rotation_speed.md"),
            ("landing", "Landing distance", DOCS / "landing.md"),
            ("gusts", "Gust analysis (extra runway for gusty days)", DOCS / "gusts.md"),
            ("uncertainty", "Data uncertainty (lift, drag, thrust tables)",
             DOCS / "uncertainty.md"),
            ("ground-effect", "Ground effect (Raymer)", DOCS / "ground_effect.md"),
            ("assumptions", "Assumptions & V-speed glossary", DOCS / "assumptions.md"),
        ],
    ),
    "/methods": (
        "Methods",
        "How the numbers are computed (all methods hand-written) and the evidence that "
        "they are right.",
        [
            ("how-it-works", "How the solver works", DOCS / "methods" / "overview.md"),
            ("physics", "Physics & equations", DOCS / "equations.md"),
            ("runge-kutta", "Runge–Kutta integrators", DOCS / "methods" / "runge_kutta.md"),
            ("events", "Event location", DOCS / "methods" / "event_location.md"),
            ("root-finding", "Root finding (secant)", DOCS / "methods" / "root_finding.md"),
            ("interpolation", "Interpolation & splines",
             DOCS / "methods" / "interpolation.md"),
            ("sde", "Stochastic methods (gust analysis)", DOCS / "methods" / "sde.md"),
            ("sampling", "Sampling: Monte Carlo and Latin hypercube",
             DOCS / "methods" / "sampling.md"),
            ("verification", "Verification and validation",
             DOCS / "methods" / "verification.md"),
        ],
    ),
}  # fmt: skip
# old one-page-per-file routes and markdown file stems -> page#section
SECTION_ROUTE = {
    anchor: f"{route}#{anchor}" for route, (_, _, secs) in DOC_PAGES.items() for anchor, *_ in secs
}
ROUTE_BY_STEM = {
    path.stem: f"{route}#{anchor}"
    for route, (_, _, secs) in DOC_PAGES.items()
    for anchor, _, path in secs
}
OLD_ROUTES = {f"/{a}": r for a, r in SECTION_ROUTE.items()}
ROUTES = set(DOC_PAGES) | set(OLD_ROUTES)

_IMG = re.compile(r"\]\((?:\.\./)*output/verification/")
_MDLINK = re.compile(r"\]\((?:[\w./]*/)?([\w-]+)\.md(#[\w-]*)?\)")


def _rewrite(text: str) -> str:
    text = _IMG.sub("](/verification/", text)

    def link(m: re.Match) -> str:
        route = ROUTE_BY_STEM.get(m.group(1))
        if not route:
            return m.group(0)
        return f"]({route.split('#')[0]}{m.group(2)})" if m.group(2) else f"]({route})"

    return _MDLINK.sub(link, text)


def render(pathname: str) -> html.Div:
    route = OLD_ROUTES.get(pathname, pathname).split("#")[0]
    if route not in DOC_PAGES:
        return html.Div(
            className="doc",
            children=[html.H1("Page not found"), dcc.Link("Back to the simulator", href="/")],
        )
    title, blurb, sections = DOC_PAGES[route]
    index = html.Ol(
        className="doc-index",
        children=[html.Li(html.A(t, href=f"#{a}")) for a, t, _ in sections],
    )
    body = []
    for anchor, sec_title, path in sections:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            text = f"# {sec_title}\n\n`{path.relative_to(ROOT)}` is missing."
        if anchor == "verification" and not VERIFICATION_DIR.exists():
            text = (
                "> The figures are generated files. Run "
                "`python scripts/make_verification_figures.py` once, then reload this page.\n\n"
                + text
            )
        body.append(
            html.Section(
                id=anchor,
                className="doc-section",
                children=[
                    dcc.Markdown(
                        _rewrite(text),
                        mathjax=True,
                        link_target="_self",
                        dangerously_allow_html=True,  # our own docs: <a id> anchors
                    ),
                    html.A("↑ index", href="#doc-top", className="doc-top-link"),
                ],
            )
        )
    other = "/methods" if route == "/about" else "/about"
    return html.Div(
        className="doc",
        children=[
            html.H1(title, id="doc-top"),
            html.P(blurb, className="hint"),
            index,
            *body,
            html.Div(
                className="doc-nav",
                children=[
                    dcc.Link("← Simulator", href="/"),
                    dcc.Link(f"{DOC_PAGES[other][0]} →", href=other),
                ],
            ),
        ],
    )


def menu_links() -> list:
    from .datapages import DATA_PAGES

    out: list = [
        html.Div("Tools", className="nav-head"),
        dcc.Link("Simulator", href="/"),
        dcc.Link("Trade study", href="/trade"),
        dcc.Link("Gust analysis", href="/gusts"),
        dcc.Link("Data uncertainty", href="/uncertainty"),
        dcc.Link("Aircraft builder", href="/builder"),
        html.Div("Aircraft data & validation", className="nav-head"),
        *[dcc.Link(p["menu"], href=p["route"]) for p in DATA_PAGES.values()],
    ]
    out.append(html.Div("Documentation", className="nav-head"))
    out += [dcc.Link(title, href=route) for route, (title, _, _) in DOC_PAGES.items()]
    return out
