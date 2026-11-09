"""Plotly figure builders for the Dash app. Pure functions of the data dicts from compute.run."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# categorical slots in fixed order (validated reference palette)
C1, C2, C3, C4, C5 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
GO_C, STOP_C, AEO_C = C1, C2, C3
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BASE_DASH = "dash"
BASE_NOTE = "dashed = pinned baseline"

Data = dict[str, Any]


def _base_layout(fig: go.Figure, title: str, height: int = 380) -> go.Figure:
    fig.update_layout(
        title={"text": title, "x": 0.01, "font": {"size": 15, "color": INK}},
        height=height,
        margin={"l": 60, "r": 20, "t": 50, "b": 45},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"color": INK, "size": 12},
        legend={"orientation": "h", "y": -0.18, "x": 0},
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=MUTED)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=MUTED)
    return fig


def empty(msg: str = "Press Run to compute") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font={"size": 14, "color": MUTED})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _base_layout(fig, "", 300)


# ------------------------------------------------------------------------------------
def bfl_chart(cur: Data, base: Data | None) -> go.Figure:
    fig = go.Figure()
    for d, dash, suffix, show in ((base, BASE_DASH, " (baseline)", True), (cur, None, "", True)):
        if not d or not d.get("ok"):
            continue
        sw = d["sweep"]
        fig.add_scatter(
            x=sw["v1_kts"],
            y=sw["d_go_ft"],
            name="Go" + suffix,
            mode="lines",
            line={"color": GO_C, "width": 2, "dash": dash},
            showlegend=show,
            hovertemplate="%{y:,.0f} ft",
        )
        fig.add_scatter(
            x=sw["v1_kts"],
            y=sw["d_stop_ft"],
            name="Stop" + suffix,
            mode="lines",
            line={"color": STOP_C, "width": 2, "dash": dash},
            hovertemplate="%{y:,.0f} ft",
        )
        s = d["scalars"]
        fig.add_scatter(
            x=[s["v1_kts"]],
            y=[s["bfl_ft"]],
            mode="markers",
            marker={
                "size": 11,
                "color": INK if not dash else SURFACE,
                "line": {"color": INK, "width": 2},
            },
            name=("Balanced point" if s["balanced"] else "V1 (unbalanced)") + suffix,
            hovertemplate="V1 %{x:.1f} kt<br>BFL %{y:,.0f} ft<extra></extra>",
        )
    _base_layout(fig, "Go and stop distance vs V1")
    fig.update_xaxes(title="V1 [KEAS]")
    fig.update_yaxes(title="distance [ft]", tickformat=",")
    return fig


# ------------------------------------------------------------------------------------
def sensitivity(cur: Data, base: Data | None) -> go.Figure:
    fig = go.Figure()
    for d, dash, suffix in ((base, BASE_DASH, " (baseline)"), (cur, None, "")):
        if not d or not d.get("ok"):
            continue
        s = d["sens"]
        fig.add_scatter(
            x=s["k"],
            y=s["k_CL"],
            name="vary k_CL (lift)" + suffix,
            mode="lines+markers",
            line={"color": C1, "width": 2, "dash": dash},
            marker={"size": 8},
            hovertemplate="%{y:,.0f} ft",
        )
        fig.add_scatter(
            x=s["k"],
            y=s["k_CD"],
            name="vary k_CD (drag)" + suffix,
            mode="lines+markers",
            line={"color": C2, "width": 2, "dash": dash},
            marker={"size": 8, "symbol": "square"},
            hovertemplate="%{y:,.0f} ft",
        )
    _base_layout(fig, "Sensitivity: BFL vs aero multiplier (other multiplier held at its value)")
    fig.add_vline(x=1.0, line={"color": MUTED, "width": 1, "dash": "dot"})
    fig.update_xaxes(title="multiplier value")
    fig.update_yaxes(title="BFL [ft]", tickformat=",")
    return fig


# ------------------------------------------------------------------------------------
TH_TABS = {
    "speeds": ("Airspeed vs time", "airspeed [KTAS]"),
    "forces": ("Forces vs time", "force [lbf]"),
    "angles": ("Angles vs time", "angle [deg]"),
    "positions": ("Position", ""),
}


def time_history(cur: Data, base: Data | None, tab: str, branch: str) -> go.Figure:
    runs = [(base, BASE_DASH, " (baseline)"), (cur, None, "")]
    if tab == "positions":
        fig = make_subplots(
            1, 2, subplot_titles=("distance vs time", "height vs distance"), horizontal_spacing=0.1
        )
        for d, dash, sfx in runs:
            if not d or not d.get("ok"):
                continue
            for br, c, lab in (("go", GO_C, "Go"), ("stop", STOP_C, "Stop"), ("aeo", AEO_C, "AEO")):
                tr = d[br]
                fig.add_scatter(
                    x=tr["t"],
                    y=tr["x"],
                    name=lab + sfx,
                    mode="lines",
                    line={"color": c, "width": 2, "dash": dash},
                    row=1,
                    col=1,
                    legendgroup=lab + sfx,
                )
                if br != "stop":
                    fig.add_scatter(
                        x=tr["x"],
                        y=tr["h"],
                        name=lab + sfx,
                        mode="lines",
                        line={"color": c, "width": 2, "dash": dash},
                        row=1,
                        col=2,
                        legendgroup=lab + sfx,
                        showlegend=False,
                    )
        _base_layout(fig, "Positions", 400)
        fig.update_layout(hovermode="closest")
        fig.update_xaxes(title="time [s]", row=1, col=1)
        fig.update_yaxes(title="x [ft]", tickformat=",", row=1, col=1)
        fig.update_xaxes(title="x [ft]", tickformat=",", row=1, col=2)
        fig.update_yaxes(title="h [ft]", row=1, col=2)
        return fig

    fig = go.Figure()
    for d, dash, sfx in runs:
        if not d or not d.get("ok"):
            continue
        if tab == "speeds":
            for br, c, lab in (("go", GO_C, "Go"), ("stop", STOP_C, "Stop"), ("aeo", AEO_C, "AEO")):
                tr = d[br]
                fig.add_scatter(
                    x=tr["t"],
                    y=tr["va"],
                    name=f"{lab} airspeed{sfx}",
                    mode="lines",
                    line={"color": c, "width": 2, "dash": dash},
                )
        else:
            tr = d[branch]
            series = (
                [
                    ("T", C1, "thrust"),
                    ("D", C2, "drag"),
                    ("L", C3, "lift"),
                    ("N", C4, "normal force"),
                    ("F", C5, "friction"),
                ]
                if tab == "forces"
                else [("theta", C1, "θ pitch"), ("alpha", C2, "α"), ("gamma", C3, "γ flight path")]
            )
            for key, c, lab in series:
                fig.add_scatter(
                    x=tr["t"],
                    y=tr[key],
                    name=lab + sfx,
                    mode="lines",
                    line={"color": c, "width": 2, "dash": dash},
                )
    title, ylab = TH_TABS[tab]
    if tab in ("forces", "angles"):
        title += f" ({branch} branch)"
    _base_layout(fig, title, 400)
    fig.update_xaxes(title="time [s]")
    fig.update_yaxes(title=ylab, tickformat="," if tab == "forces" else None)
    return fig


# ------------------------------------------------------------------------------------
# animation
# ------------------------------------------------------------------------------------
# side-view outline in screen pixels, origin at the main-gear contact point, nose = +u
_SHAPE_PX = np.array(
    [
        (-38, 4),
        (-40, 18),
        (-33, 18),
        (-26, 7),
        (18, 7),
        (24, 5),
        (26, 3.5),
        (24, 2),
        (-30, 2),
        (-38, 4),
    ]
)
_GEAR_PX = np.array([(0, 0), (0, 2.5)])
LANE_PX = (900, 140)  # approximate plotting area of one lane, for undistorted shapes


def _interp_state(tr: dict, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    tt = np.asarray(tr["t"])
    return (
        np.interp(t, tt, tr["x"]),
        np.interp(t, tt, tr["h"]),
        np.radians(np.interp(t, tt, tr["theta"])),
    )


def _shape(x: float, y: float, th: float, kx: float, ky: float) -> tuple[list, list]:
    c, s = math.cos(th), math.sin(th)
    u, v = 1.4 * _SHAPE_PX[:, 0], 1.4 * _SHAPE_PX[:, 1]
    return (list(x + kx * (u * c - v * s)), list(y + ky * (u * s + v * c)))


def animation(
    cur: Data, base: Data | None, exaggeration: float, fps: int = 25, max_frames: int = 360
) -> go.Figure:
    s = cur["scalars"]
    screen = 35.0
    t_end = max(cur["go"]["t"][-1], cur["stop"]["t"][-1])
    if base and base.get("ok"):
        t_end = max(t_end, base["go"]["t"][-1], base["stop"]["t"][-1])
    dt_frame = max(1.0 / fps, t_end / max_frames)
    times = np.arange(0.0, t_end + dt_frame, dt_frame)

    x_max = 1.08 * max(
        s["bfl_ft"],
        cur["aeo"]["x"][-1],
        base["scalars"]["bfl_ft"] if base and base.get("ok") else 0.0,
    )
    x_min = -0.06 * x_max
    y_top = screen * exaggeration * 1.6
    y_bot = -0.25 * y_top
    kx = (x_max - x_min) / LANE_PX[0]
    ky = (y_top - y_bot) / LANE_PX[1]

    fig = make_subplots(
        2,
        1,
        shared_xaxes=True,
        vertical_spacing=0.09,
        subplot_titles=("Continued takeoff (go, one engine out)", "Rejected takeoff (stop)"),
    )
    # static scenery
    for row in (1, 2):
        fig.add_scatter(
            x=[x_min, x_max],
            y=[0, 0],
            mode="lines",
            hoverinfo="skip",
            line={"color": MUTED, "width": 3},
            showlegend=False,
            row=row,
            col=1,
        )
        fig.add_vline(
            x=s["bfl_ft"], line={"color": INK, "width": 1.5, "dash": "dash"}, row=row, col=1
        )
    fig.add_hline(
        y=screen * exaggeration, line={"color": MUTED, "width": 1, "dash": "dot"}, row=1, col=1
    )
    fig.add_annotation(
        x=x_min,
        y=screen * exaggeration,
        text="35 ft screen",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font={"color": MUTED, "size": 11},
        row=1,
        col=1,
    )
    fig.add_annotation(
        x=s["bfl_ft"],
        y=y_top,
        text=f"BFL {s['bfl_ft']:,.0f} ft",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        font={"color": INK, "size": 11},
        row=1,
        col=1,
    )
    # static flight paths (faint)
    fig.add_scatter(
        x=cur["go"]["x"],
        y=np.asarray(cur["go"]["h"]) * exaggeration,
        mode="lines",
        line={"color": GO_C, "width": 1},
        opacity=0.35,
        hoverinfo="skip",
        showlegend=False,
        row=1,
        col=1,
    )

    runs = []
    if base and base.get("ok"):  # baseline ghosts first so they sit behind the current run
        runs += [("go", 1, "#b5b4ae", base, "baseline"), ("stop", 2, "#b5b4ae", base, "baseline")]
    runs += [("go", 1, GO_C, cur, "current"), ("stop", 2, STOP_C, cur, "current")]
    states = []
    dyn_idx = []
    for br, row, color, d, label in runs:
        x, h, th = _interp_state(d[br], times)
        states.append((x, h * exaggeration, th))
        px, py = _shape(x[0], h[0] * exaggeration, th[0], kx, ky)
        dyn_idx.append(len(fig.data))
        fig.add_scatter(
            x=px,
            y=py,
            mode="lines",
            fill="toself",
            fillcolor=color,
            line={"color": color, "width": 1},
            hoverinfo="skip",
            name=f"{br} ({label})",
            showlegend=False,
            row=row,
            col=1,
        )
    dyn_idx.append(len(fig.data))
    fig.add_scatter(
        x=[x_min + 0.01 * (x_max - x_min)],
        y=[0.85 * y_top],
        mode="text",
        text=["t = 0.0 s"],
        textposition="middle right",
        showlegend=False,
        hoverinfo="skip",
        textfont={"size": 13, "color": INK},
        row=1,
        col=1,
    )

    frames = []
    for i, t in enumerate(times):
        data = []
        for x, y, th in states:
            px, py = _shape(x[i], y[i], th[i], kx, ky)
            data.append(go.Scatter(x=px, y=py))
        data.append(go.Scatter(text=[f"t = {t:5.1f} s"]))
        frames.append(go.Frame(data=data, traces=dyn_idx, name=f"{t:.2f}"))
    fig.frames = frames

    speedup = dt_frame * fps
    frame_ms = 1000.0 / fps
    fig.update_layout(
        updatemenus=[
            {
                "type": "buttons",
                "direction": "left",
                "x": 0.0,
                "y": -0.12,
                "xanchor": "left",
                "buttons": [
                    {
                        "label": "▶ Play",
                        "method": "animate",
                        "args": [
                            None,
                            {
                                "frame": {"duration": frame_ms, "redraw": False},
                                "fromcurrent": True,
                                "transition": {"duration": 0},
                            },
                        ],
                    },
                    {
                        "label": "❚❚ Pause",
                        "method": "animate",
                        "args": [
                            [None],
                            {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"},
                        ],
                    },
                ],
            }
        ],
        sliders=[
            {
                "x": 0.17,
                "y": -0.07,
                "len": 0.83,
                "currentvalue": {"visible": False},
                "steps": [
                    {
                        "label": "",
                        "method": "animate",
                        "args": [
                            [f.name],
                            {"mode": "immediate", "frame": {"duration": 0, "redraw": False}},
                        ],
                    }
                    for f in frames[:: max(1, len(frames) // 120)]
                ],
            }
        ],
    )
    _base_layout(
        fig,
        f"Takeoff animation (vertical exaggeration ×{exaggeration:g}, "
        f"playback ×{speedup:.1f} real time"
        + (", grey = baseline)" if base and base.get("ok") else ")"),
        520,
    )
    fig.update_layout(hovermode=False, margin={"b": 90})
    fig.update_xaxes(range=[x_min, x_max], dtick=1000, tickformat=",", row=1, col=1)
    fig.update_xaxes(
        range=[x_min, x_max], dtick=1000, tickformat=",", title="runway distance [ft]", row=2, col=1
    )
    ticks = [0, 10, 20, 35] if exaggeration >= 5 else [0, 35]
    for row in (1, 2):
        fig.update_yaxes(
            range=[y_bot, y_top],
            tickvals=[v * exaggeration for v in ticks],
            ticktext=[f"{v} ft" for v in ticks],
            row=row,
            col=1,
        )
    return fig
