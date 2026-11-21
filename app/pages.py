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

# (route, menu title, markdown file, menu section)
PAGES: list[tuple[str, str, Path, str]] = [
    ("/how-it-works", "How it works (start here)", DOCS / "methods" / "overview.md", "Guides"),
    ("/assumptions", "Assumptions & V-speed glossary", DOCS / "assumptions.md", "Guides"),
    ("/rules", "Field-length rules: Part 25 vs MIL", DOCS / "field_length_rules.md", "Guides"),
    ("/ground-effect", "Ground effect (Raymer)", DOCS / "ground_effect.md", "Guides"),
    ("/physics", "Physics & equations", DOCS / "equations.md", "Guides"),
    ("/runge-kutta", "Runge–Kutta integrators", DOCS / "methods" / "runge_kutta.md",
     "About the method"),
    ("/events", "Event location", DOCS / "methods" / "event_location.md", "About the method"),
    ("/root-finding", "Root finding (secant)", DOCS / "methods" / "root_finding.md",
     "About the method"),
    ("/interpolation", "Interpolation & splines", DOCS / "methods" / "interpolation.md",
     "About the method"),
    ("/verification", "Verification gallery", DOCS / "methods" / "verification.md",
     "About the method"),
]  # fmt: skip
ROUTE_BY_STEM = {p.stem: route for route, _, p, _ in PAGES}

_IMG = re.compile(r"\]\((?:\.\./)*output/verification/")
_MDLINK = re.compile(r"\]\((?:[\w./]*/)?([\w-]+)\.md(#[\w-]*)?\)")


def _rewrite(text: str) -> str:
    text = _IMG.sub("](/verification/", text)

    def link(m: re.Match) -> str:
        route = ROUTE_BY_STEM.get(m.group(1))
        return f"]({route}{m.group(2) or ''})" if route else m.group(0)

    return _MDLINK.sub(link, text)


def render(pathname: str) -> html.Div:
    idx = next((i for i, p in enumerate(PAGES) if p[0] == pathname), None)
    if idx is None:
        return html.Div(
            className="doc",
            children=[html.H1("Page not found"), dcc.Link("Back to the simulator", href="/")],
        )
    route, title, path, _ = PAGES[idx]
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = f"# {title}\n\n`{path.relative_to(ROOT)}` is missing."
    if route == "/verification" and not VERIFICATION_DIR.exists():
        text = (
            "> The figures are generated files. Run `python scripts/make_verification_figures.py` "
            "once, then reload this page.\n\n" + text
        )
    prev_ = PAGES[idx - 1] if idx > 0 else None
    next_ = PAGES[idx + 1] if idx + 1 < len(PAGES) else None
    return html.Div(
        className="doc",
        children=[
            dcc.Markdown(_rewrite(text), mathjax=True, link_target="_self"),
            html.Div(
                className="doc-nav",
                children=[
                    dcc.Link(f"← {prev_[1]}", href=prev_[0])
                    if prev_
                    else dcc.Link("← Simulator", href="/"),
                    dcc.Link(f"{next_[1]} →", href=next_[0])
                    if next_
                    else dcc.Link("Simulator →", href="/"),
                ],
            ),
        ],
    )


def menu_links() -> list:
    from .datapages import DATA_PAGES

    out: list = [
        html.Div("Tools", className="nav-head"),
        dcc.Link("Takeoff simulator", href="/"),
        dcc.Link("Trade study", href="/trade"),
        dcc.Link("Aircraft builder", href="/builder"),
        html.Div("Aircraft data & validation", className="nav-head"),
        *[dcc.Link(p["menu"], href=p["route"]) for p in DATA_PAGES.values()],
    ]
    section = None
    for route, title, _, sec in PAGES:
        if sec != section:
            out.append(html.Div(sec, className="nav-head"))
            section = sec
        out.append(dcc.Link(title, href=route))
    return out
