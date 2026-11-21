"""Aircraft-assembly loading indicator for Dash apps.

A top view of an aircraft that builds itself (fuselage, then wings, tail and engines),
holds for a moment, comes apart and starts again. The whole animation is one SVG with
its own CSS inside, shown as an <img>, so this file is self-contained: copy it into any
Dash app (no assets or stylesheet needed) and use

    from loading import loading
    loading([dcc.Graph(id="plot"), dcc.Store(id="result")], "Computing…")

Viewers whose browser asks for reduced motion (e.g. Firefox ui.prefersReducedMotion)
see the finished aircraft fading in and out instead of the assembly.

``dcc.Loading`` shows the spinner while a callback is updating any component inside
it, so put the store that the slow computation writes into the wrapper too, not only
the plot drawn from it.
"""

from __future__ import annotations

import base64

from dash import dcc, html

# Planform, nose to the right, in a 120 x 80 box. Each part is a <g> with its own
# keyframes; one cycle is CYCLE seconds, and something moves from the very first frame
# (most solves finish in well under a second, so the start is what people see):
#   0-18 % fuselage slides in   0-28 % wings close in from the sides
#   10-38 % tail slides in      38-50 % engines pop onto the wings
#   50-80 % complete aircraft (gentle bob)  80-100 % everything flies apart and fades
CYCLE = 2.4

_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 80'>
<style>
 g {{ transform-box: fill-box; animation: {cycle}s ease-in-out infinite; }}
 .fus {{ transform-origin: right center; animation-name: fus; }}
 .wt {{ animation-name: wt; }}
 .wb {{ animation-name: wb; }}
 .tail {{ animation-name: tail; }}
 .eng {{ transform-origin: center; animation-name: eng; }}
 .all {{ transform-box: view-box; animation-name: bob; }}
 @keyframes fus {{
   0% {{ transform: translateX(-40px); opacity: 0.3 }}
   18%, 80% {{ transform: none; opacity: 1 }}
   100% {{ transform: translateX(30px); opacity: 0 }} }}
 @keyframes wt {{
   0% {{ transform: translateY(-30px); opacity: 0.3 }}
   28%, 80% {{ transform: none; opacity: 1 }}
   100% {{ transform: translate(-10px, -30px) rotate(-20deg); opacity: 0 }} }}
 @keyframes wb {{
   0% {{ transform: translateY(30px); opacity: 0.3 }}
   28%, 80% {{ transform: none; opacity: 1 }}
   100% {{ transform: translate(-10px, 30px) rotate(20deg); opacity: 0 }} }}
 @keyframes tail {{
   0%, 10% {{ transform: translateX(-30px); opacity: 0.2 }}
   38%, 80% {{ transform: none; opacity: 1 }}
   100% {{ transform: translateX(-30px); opacity: 0 }} }}
 @keyframes eng {{
   0%, 38% {{ transform: scale(0); opacity: 0 }}
   46% {{ transform: scale(1.3); opacity: 1 }}
   50%, 80% {{ transform: scale(1); opacity: 1 }}
   92%, 100% {{ transform: scale(0); opacity: 0 }} }}
 @keyframes bob {{
   0%, 50% {{ transform: none }}
   58% {{ transform: translateY(-2.5px) rotate(-1deg) }}
   68% {{ transform: translateY(2px) rotate(1deg) }}
   80%, 100% {{ transform: none }} }}
 @keyframes pulse {{ 0%, 100% {{ opacity: 1 }} 50% {{ opacity: 0.3 }} }}
 @media (prefers-reduced-motion: reduce) {{
   g:not(.all) {{ animation: none !important; }}
   .all {{ animation: pulse 1.6s ease-in-out infinite !important; }} }}
</style>
<g class='all'>
 <g class='wt'><path fill='{wing}' d='M58 36 L72 36 L50 7 L43 7 Z'/></g>
 <g class='wb'><path fill='{wing}' d='M58 44 L72 44 L50 73 L43 73 Z'/></g>
 <g class='tail'><path fill='{wing}'
   d='M16 37 L25 37 L16 24 L12 24 Z M16 43 L25 43 L16 56 L12 56 Z'/></g>
 <g class='fus'><path fill='{body}'
   d='M10 36 L96 36 Q112 37 114 40 Q112 43 96 44 L10 44 Q7 40 10 36 Z'/>
  <circle cx='104' cy='40' r='1.6' fill='white' opacity='0.8'/></g>
 <g class='eng'><rect x='54' y='22' width='12' height='4.5' rx='2.2' fill='{engine}'/></g>
 <g class='eng'><rect x='54' y='53.5' width='12' height='4.5' rx='2.2' fill='{engine}'/></g>
</g>
</svg>"""


def aircraft_svg(
    body: str = "#2a78d6", wing: str = "#1a5fb4", engine: str = "#0f1d2b", cycle: float = CYCLE
) -> str:
    """The animated aircraft as a data: URI (usable as an <img> src anywhere)."""
    svg = _SVG.format(body=body, wing=wing, engine=engine, cycle=cycle)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


_CARD = {
    "display": "flex",
    "flexDirection": "column",
    "alignItems": "center",
    "gap": "6px",
    "padding": "12px 22px 14px",
    "borderRadius": "12px",
    "background": "rgba(255,255,255,0.94)",
    "boxShadow": "0 6px 24px rgba(15,29,43,0.15)",
}
_IMG = {"width": "150px", "height": "100px"}
_TEXT = {"fontSize": "13px", "color": "#4a5868", "fontFamily": "inherit"}


def spinner(text: str = "Computing…", **colors: str) -> html.Div:
    """The card: assembling aircraft plus a line of text. ``colors``: body, wing, engine."""
    return html.Div(
        style=_CARD,
        className="aircraft-loader",
        children=[
            html.Img(src=aircraft_svg(**colors), alt="", style=_IMG),
            html.Div(text, style=_TEXT),
        ],
    )


def loading(children, text: str = "Computing…", min_height: int = 0, **colors: str) -> dcc.Loading:
    """``dcc.Loading`` with the aircraft spinner; the old content stays visible, dimmed.

    Args:
        min_height: px reserved for the wrapper, so the spinner has room before the
            first result exists (e.g. the plot's height).
        colors: body, wing, engine (CSS colours) to match another app's palette.
    """
    return dcc.Loading(
        children,
        custom_spinner=spinner(text, **colors),
        delay_show=120,  # results that come back faster than this never flash it
        overlay_style={"visibility": "visible", "opacity": 0.35, "filter": "blur(1px)"},
        parent_style={"minHeight": f"{min_height}px"} if min_height else None,
    )
