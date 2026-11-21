"""Aircraft-assembly loading indicator for Dash apps.

A top view of an aircraft that builds itself (fuselage, then wings, tail and engines),
holds for a moment, comes apart and starts again. The whole animation is one SVG with
its own CSS inside, shown as an <img>, so this file is self-contained: copy it into any
Dash app (no assets or stylesheet needed) and use

    from loading import loading
    loading([dcc.Graph(id="plot"), dcc.Store(id="result")], "Computing…")

``dcc.Loading`` shows the spinner while a callback is updating any component inside
it, so put the store that the slow computation writes into the wrapper too, not only
the plot drawn from it.
"""

from __future__ import annotations

import base64

from dash import dcc, html

# Planform, nose to the right, in a 120 x 80 box. Each part is a <g> with its own
# keyframes; one cycle is CYCLE seconds:
#   0-12 % fuselage grows from the nose   12-30 % wings slide in from the sides
#   30-42 % tail slides in from behind    42-52 % engines drop onto the wings
#   52-78 % complete aircraft (gentle bob)  78-100 % everything flies apart and fades
CYCLE = 3.2

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
   0% {{ transform: scaleX(0); opacity: 0 }}
   12%, 80% {{ transform: scaleX(1); opacity: 1 }}
   95%, 100% {{ transform: scaleX(0.2); opacity: 0 }} }}
 @keyframes wt {{
   0%, 12% {{ transform: translateY(-34px); opacity: 0 }}
   30%, 78% {{ transform: none; opacity: 1 }}
   92%, 100% {{ transform: translate(-8px, -34px) rotate(-20deg); opacity: 0 }} }}
 @keyframes wb {{
   0%, 12% {{ transform: translateY(34px); opacity: 0 }}
   30%, 78% {{ transform: none; opacity: 1 }}
   92%, 100% {{ transform: translate(-8px, 34px) rotate(20deg); opacity: 0 }} }}
 @keyframes tail {{
   0%, 30% {{ transform: translateX(-30px); opacity: 0 }}
   42%, 78% {{ transform: none; opacity: 1 }}
   92%, 100% {{ transform: translateX(-30px); opacity: 0 }} }}
 @keyframes eng {{
   0%, 42% {{ transform: scale(0); opacity: 0 }}
   50% {{ transform: scale(1.25); opacity: 1 }}
   54%, 78% {{ transform: scale(1); opacity: 1 }}
   88%, 100% {{ transform: scale(0); opacity: 0 }} }}
 @keyframes bob {{
   0%, 52% {{ transform: none }}
   60% {{ transform: translateY(-2px) }}
   70% {{ transform: translateY(1.5px) }}
   78%, 100% {{ transform: none }} }}
 @media (prefers-reduced-motion: reduce) {{ g {{ animation: none !important; }} }}
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
        delay_show=250,  # results that come back faster than this never flash it
        overlay_style={"visibility": "visible", "opacity": 0.35, "filter": "blur(1px)"},
        parent_style={"minHeight": f"{min_height}px"} if min_height else None,
    )
