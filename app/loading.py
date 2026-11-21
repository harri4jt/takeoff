"""Loading indicator shared by the simulator and the trade study: a small aircraft rolls
down a runway and lifts off, on a loop (pure CSS, see .plane-loader in style.css)."""

from __future__ import annotations

from dash import dcc, html

# side view, nose to the right; drawn in a 64 x 24 box
_PLANE_SVG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 24'>"
    "<path fill='%232a78d6' d='M4 10 L10 10 L14 3 L19 3 L18 10 L52 10 "
    "Q62 11 62 14 Q62 17 52 17 L8 17 Q3 17 4 10 Z'/>"
    "<path fill='%231a5fb4' d='M26 13 L40 13 L32 22 L27 22 Z'/>"
    "<circle cx='54' cy='13' r='1.4' fill='white'/>"
    "</svg>"
)


def spinner(text: str) -> html.Div:
    return html.Div(
        className="plane-loader",
        children=[
            html.Div(
                className="pl-sky",
                children=[
                    html.Img(src=_PLANE_SVG, className="pl-plane", alt=""),
                    html.Div(className="pl-runway"),
                ],
            ),
            html.Div(text, className="pl-text"),
        ],
    )


def loading(children, text: str = "Computing…", min_height: int = 0) -> dcc.Loading:
    """dcc.Loading with the aircraft spinner. The old content stays visible, dimmed.

    It shows while any callback is updating a component inside ``children``, so put the
    store that the slow computation writes into it, not only the plot drawn from it.
    """
    return dcc.Loading(
        children,
        custom_spinner=spinner(text),
        delay_show=250,  # cached re-runs come back faster than this: no flash
        overlay_style={"visibility": "visible", "opacity": 0.35, "filter": "blur(1px)"},
        parent_style={"minHeight": f"{min_height}px"} if min_height else None,
    )
