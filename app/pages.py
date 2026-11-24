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

A, M, D = DOCS / "about", DOCS / "methods", DOCS / "assumptions"

# Three documentation pages. Each is a list of sections: (anchor, index title, markdown file).
DOC_PAGES: dict[str, tuple[str, str, list[tuple[str, str, Path]]]] = {
    "/about": (
        "About",
        "What the tool answers, the data it needs, and how to run it from Python.",
        [
            ("overview", "Overview", A / "overview.md"),
            ("aircraft-data", "Aircraft data", A / "aircraft_data.md"),
            ("python", "Using it from Python", A / "python.md"),
            ("faq", "Questions and answers", A / "faq.md"),
        ],
    ),
    "/assumptions": (
        "Assumptions",
        "What is modelled, which rules apply, and what is left out.",
        [
            ("takeoff-model", "Takeoff model and V-speeds", D / "takeoff_model.md"),
            ("rules", "Field-length rules: Part 25 vs MIL-STD-3013", D / "rules.md"),
            ("rotation-speed", "Rotation speed", D / "rotation_speed.md"),
            ("landing", "Landing", D / "landing.md"),
            ("ground-effect", "Ground effect (Raymer)", D / "ground_effect.md"),
            ("gusts", "Gust analysis", D / "gusts.md"),
            ("uncertainty", "Uncertainty analysis", D / "uncertainty.md"),
            ("limits", "Limits: what is not modelled", D / "limits.md"),
        ],
    ),
    "/methods": (
        "Methods",
        "How the numbers are computed, and the evidence that they are right.",
        [
            ("how-it-works", "How the solver works", M / "solver.md"),
            ("equations", "Equations of motion", M / "equations.md"),
            ("runge-kutta", "Runge–Kutta integrators", M / "runge_kutta.md"),
            ("events", "Event location", M / "event_location.md"),
            ("root-finding", "Root finding (secant)", M / "root_finding.md"),
            ("optimization", "Optimization (Brent)", M / "optimization.md"),
            ("interpolation", "Interpolation & splines", M / "interpolation.md"),
            ("sde", "Stochastic methods", M / "sde.md"),
            ("sampling", "Sampling and response surfaces", M / "sampling.md"),
            ("verification", "Verification and validation", M / "verification.md"),
        ],
    ),
}  # fmt: skip
ORDER = list(DOC_PAGES)
# markdown file stem -> page#section (links between the files become app links)
ROUTE_BY_STEM = {
    path.stem: f"{route}#{anchor}"
    for route, (_, _, secs) in DOC_PAGES.items()
    for anchor, _, path in secs
}

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
    route = pathname.split("#")[0]
    if route not in DOC_PAGES:
        return html.Div(
            className="doc",
            children=[html.H1("Page not found"), dcc.Link("Back to the simulator", href="/")],
        )
    title, _, sections = DOC_PAGES[route]
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
    k = ORDER.index(route)
    prev_ = ORDER[k - 1] if k > 0 else "/"
    next_ = ORDER[k + 1] if k + 1 < len(ORDER) else "/"
    return html.Div(
        className="doc",
        children=[
            html.H1(title, id="doc-top"),
            index,
            *body,
            html.Div(
                className="doc-nav",
                children=[
                    dcc.Link(
                        f"← {DOC_PAGES[prev_][0] if prev_ != '/' else 'Simulator'}", href=prev_
                    ),
                    dcc.Link(
                        f"{DOC_PAGES[next_][0] if next_ != '/' else 'Simulator'} →", href=next_
                    ),
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
        dcc.Link("Uncertainty analysis", href="/uncertainty"),
        dcc.Link("Aircraft builder", href="/builder"),
        html.Div("Aircraft data & validation", className="nav-head"),
        *[dcc.Link(p["menu"], href=p["route"]) for p in DATA_PAGES.values()],
    ]
    out.append(html.Div("Documentation", className="nav-head"))
    out += [dcc.Link(title, href=route) for route, (title, _, _) in DOC_PAGES.items()]
    return out
