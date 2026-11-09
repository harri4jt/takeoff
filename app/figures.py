"""Plotly figure builders for the Dash app. Pure functions of the dicts from app.compute."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# categorical slots in fixed order (validated reference palette)
C1, C2, C3, C4, C5 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
GO_C, STOP_C, AEO_C = C1, C2, C3
BFL_C, FAA_C = "#d7263d", "#1f9d55"
INK, MUTED, GRID = "#0f1d2b", "#4a5868", "#dfe4ea"
SURFACE = "rgba(0,0,0,0)"
GHOST = "#8d97a3"
FIRE_OUT, FIRE_IN = "#ff7b00", "#ffd23f"
GRASS, ASPHALT = "#a7c98a", "#3b3f46"
FONT = "Inter, system-ui, -apple-system, Segoe UI, sans-serif"

Data = dict[str, Any]

EVENT_LABELS = {
    "engine_failure": "engine fails",
    "V1": "V1",
    "VR": "rotate (VR)",
    "liftoff": "lift-off",
    "theta_target": "pitch hold",
    "screen_height": "35 ft",
    "brakes": "brakes",
    "idle": "idle",
    "spoilers": "spoilers",
    "chute_deploy": "chute",
    "stopped": "stopped",
}


def _ok(d: Data | None) -> bool:
    return bool(d and d.get("ok"))


def _base_layout(fig: go.Figure, title: str = "", height: int = 400) -> go.Figure:
    fig.update_layout(
        title={"text": title, "x": 0.01, "font": {"size": 15, "color": INK}} if title else None,
        height=height,
        margin={"l": 64, "r": 24, "t": 48 if title else 20, "b": 48},
        paper_bgcolor="white",
        plot_bgcolor="white",
        font={"color": INK, "size": 12, "family": FONT},
        legend={"orientation": "h", "y": -0.2, "x": 0},
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=MUTED)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=MUTED)
    return fig


def empty(msg: str = "Press Run to compute", height: int = 320) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font={"size": 14, "color": MUTED})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    _base_layout(fig, "", height)
    fig.update_layout(paper_bgcolor=SURFACE, plot_bgcolor=SURFACE)
    return fig


def _merged_events(tr: dict, skip: tuple[str, ...] = ("brake_release",)) -> list[tuple[float, str]]:
    """Events of one branch with coincident times merged into one label."""
    out: list[tuple[float, list[str]]] = []
    for e in tr["events"]:
        if e["name"] in skip:
            continue
        lab = EVENT_LABELS.get(e["name"], e["name"])
        if out and abs(out[-1][0] - e["t_s"]) < 1e-6:
            out[-1][1].append(lab)
        else:
            out.append((e["t_s"], [lab]))
    return [(t, " / ".join(labs)) for t, labs in out]


def _at(tr: dict, key: str, t: float) -> float:
    return float(np.interp(t, tr["t"], tr[key]))


# ====================================================================================
# the scene: animation (side view) over a runway strip (plan view), shared x axis
# ====================================================================================
# side-view outline in screen pixels; origin at the main-gear contact point, nose = +u
_PARTS_PX = [
    [  # fuselage + fin
        (-38, 4),
        (-41, 19),
        (-35, 19),
        (-27, 8.2),
        (13, 8.2),
        (19, 7.4),
        (23.5, 5.8),
        (25, 4.4),
        (24, 3.2),
        (20, 2.3),
        (-28, 2.3),
    ],
    [(-34, 9.0), (-44, 10.4), (-43, 11.6), (-31, 10.4)],  # horizontal tail
    [(-7, 1.0), (3, 1.0), (4.5, 2.3), (3, 3.6), (-7, 3.6)],  # engine nacelle
    [(-1, 0), (1, 0), (1, 2.4), (-1, 2.4)],  # main gear
    [(17, 0), (18.4, 0), (18.4, 2.4), (17, 2.4)],  # nose gear
]
_SCALE = 1.6
_ENGINE_PX = (-1.5, 2.3)
_TAIL_PX = (-40.0, 9.0)
SCENE_PX = (1050.0, 365.0)  # approx. plotting area of the scene row, for undistorted shapes
MAX_FRAMES = 450
FPS = 25


class _Px:
    """Pixel-to-data scale for the scene row."""

    def __init__(self, kx: float, ky: float):
        self.kx, self.ky = kx, ky

    def place(self, pts, x: float, y: float, th: float = 0.0, s: float = _SCALE):
        c, sn = math.cos(th), math.sin(th)
        xs = [round(x + self.kx * s * (u * c - v * sn), 1) for u, v in pts]
        ys = [round(y + self.ky * s * (u * sn + v * c), 2) for u, v in pts]
        return xs, ys


def _aircraft(px: _Px, x: float, y: float, th: float) -> tuple[list, list]:
    xs: list = []
    ys: list = []
    for part in _PARTS_PX:
        a, b = px.place(part, x, y, th)
        xs += a + [a[0], None]
        ys += b + [b[0], None]
    return xs, ys


def _star(px: _Px, x: float, y: float, r_px: float, n: int = 9) -> tuple[list, list]:
    if r_px <= 0:
        return [], []
    pts = []
    for k in range(2 * n + 1):
        r = r_px if k % 2 == 0 else 0.45 * r_px
        a = math.pi * k / n + 0.3
        pts.append((r * math.cos(a), r * math.sin(a)))
    return px.place(pts, x, y, 0.0, 1.0)


def _chute(px: _Px, x: float, y: float) -> tuple[tuple[list, list], tuple[list, list]]:
    uc, vc, rx, ry = -100.0, 12.0, 8.0, 14.0
    arc = [
        (uc + rx * math.cos(a), vc + ry * math.sin(a))
        for a in np.linspace(0.5 * math.pi, 1.5 * math.pi, 15)
    ]
    canopy = px.place(arc + [arc[0]], x, y, 0.0, 1.0)
    tu, tv = _TAIL_PX[0] * _SCALE, _TAIL_PX[1] * _SCALE
    lines: list = []
    for end in (arc[0], (uc, vc), arc[-1]):
        lines += [(tu, tv), end, None]
    xs, ys = [], []
    for p in lines:
        if p is None:
            xs.append(None)
            ys.append(None)
        else:
            a, b = px.place([p], x, y, 0.0, 1.0)
            xs += a
            ys += b
    return canopy, (xs, ys)


def _event_t(tr: dict, name: str) -> float | None:
    e = next((e for e in tr["events"] if e["name"] == name), None)
    return None if e is None else e["t_s"]


def _event_x(tr: dict, name: str) -> float | None:
    e = next((e for e in tr["events"] if e["name"] == name), None)
    return None if e is None else e["x_ft"]


def _states(tr: dict, times: np.ndarray, exag: float):
    tt = np.asarray(tr["t"])
    return (
        np.interp(times, tt, tr["x"]),
        np.interp(times, tt, tr["h"]) * exag,
        np.radians(np.interp(times, tt, tr["theta"])),
    )


def scene(
    cur: Data,
    base: Data | None,
    refs: list[dict],
    exaggeration: float = 25.0,
    speed: float = 4.0,
    show_base: bool = True,
    mode: str = "failure",
    height: int = 600,
) -> go.Figure:
    """Animated side view over a plan-view runway strip (shared x axis).

    mode "failure": go and stop after the same engine failure, on one runway.
    mode "aeo":     the all-engines takeoff and the 15 % margin that gives the FAA length.
    """
    s = cur["scalars"]
    aeo_mode = mode == "aeo"
    has_base = show_base and _ok(base)
    screen = 35.0
    exag = float(exaggeration)

    # ---- geometry ------------------------------------------------------------------
    far = max(s["faa_field_length_ft"], s["bfl_ft"])
    if _ok(base):
        far = max(far, base["scalars"]["faa_field_length_ft"])
    x_hi = 1.2 * far
    x_lo = -0.085 * x_hi  # room for the tail behind brake release
    y_top = screen * exag * 1.45
    y_bot = -0.14 * y_top
    px = _Px((x_hi - x_lo) / SCENE_PX[0], (y_top - y_bot) / SCENE_PX[1])

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.0
    )

    def shape(row: int = 1, **kw) -> None:
        fig.add_shape(row=row, col=1, **kw)

    def note(x: float, y: float, text: str, row: int = 1, **kw) -> None:
        kw.setdefault("showarrow", False)
        fig.add_annotation(x=x, y=y, text=text, row=row, col=1, **kw)

    # ---- scene backdrop (row 1) --------------------------------------------------------
    shape(
        type="rect", x0=x_lo, x1=x_hi, y0=y_bot, y1=0, fillcolor=GRASS, line_width=0, layer="below"
    )
    shape(
        type="rect",
        x0=0,
        x1=x_hi,
        y0=-0.025 * y_top,
        y1=0,
        fillcolor=ASPHALT,
        line_width=0,
        layer="below",
    )
    shape(
        type="line",
        x0=x_lo,
        x1=x_hi,
        y0=screen * exag,
        y1=screen * exag,
        line={"color": MUTED, "width": 1, "dash": "dot"},
    )
    note(
        x_lo,
        screen * exag,
        "35 ft screen height",
        xanchor="left",
        yanchor="bottom",
        font={"color": MUTED, "size": 11},
    )

    go_tr, stop_tr, aeo_tr = cur["go"], cur["stop"], cur["aeo"]
    lead = aeo_tr if aeo_mode else go_tr  # the branch that climbs to 35 ft
    lead_c = AEO_C if aeo_mode else GO_C
    t_ef = None if aeo_mode else _event_t(go_tr, "engine_failure")

    if not aeo_mode:
        x_ef, x_v1 = _event_x(go_tr, "engine_failure"), _event_x(go_tr, "V1")
        if x_ef is not None:
            shape(
                type="line",
                x0=x_ef,
                x1=x_ef,
                y0=0,
                y1=0.97 * y_top,
                line={"color": FIRE_OUT, "width": 2, "dash": "dot"},
            )
            note(
                x_ef,
                0.97 * y_top,
                f"<b>engine fails</b> · {s['v_ef_kts']:.0f} kt",
                xanchor="right",
                yanchor="top",
                xshift=-4,
                font={"color": "#b34f00", "size": 12},
            )
        if x_v1 is not None:
            shape(
                type="line",
                x0=x_v1,
                x1=x_v1,
                y0=0,
                y1=0.97 * y_top,
                line={"color": INK, "width": 1, "dash": "dot"},
            )
            note(
                x_v1,
                0.97 * y_top,
                f"<b>V1</b> decision · {s['v1_kts']:.0f} kt",
                xanchor="left",
                yanchor="top",
                xshift=4,
                font={"color": INK, "size": 12},
            )
        # 2-second allowance: regulatory distance that is added, not flown
        x_rest, allow = cur["x_rest_ft"], cur["allowance_ft"]
        if allow > 0:
            shape(
                type="rect",
                x0=x_rest,
                x1=x_rest + allow,
                y0=-0.025 * y_top,
                y1=0.012 * y_top,
                fillcolor=STOP_C,
                opacity=0.55,
                line_width=0,
            )
            note(  # right-aligned to the end of the allowance, clear of the red line
                x_rest + allow,
                0.72 * y_bot,
                "2-s allowance (added, not flown)",
                xanchor="right",
                xshift=-4,
                font={"size": 10, "color": "#7a2e0b"},
            )
    else:
        x_aeo = s["aeo_distance_ft"]
        x_115 = 1.15 * x_aeo
        y_b = 0.82 * y_top  # above the climb-out, clear of the aircraft
        shape(type="line", x0=x_aeo, x1=x_115, y0=y_b, y1=y_b, line={"color": FAA_C, "width": 2})
        for xx in (x_aeo, x_115):
            shape(
                type="line",
                x0=xx,
                x1=xx,
                y0=y_b - 0.04 * y_top,
                y1=y_b + 0.04 * y_top,
                line={"color": FAA_C, "width": 2},
            )
        shape(
            type="line",
            x0=x_aeo,
            x1=x_aeo,
            y0=screen * exag,
            y1=y_b,
            line={"color": FAA_C, "width": 1, "dash": "dot"},
        )
        governs = "" if x_115 >= s["bfl_ft"] else "<br>(BFL is longer and governs)"
        note(
            0.5 * (x_aeo + x_115),
            y_b + 0.05 * y_top,
            f"<b>+15 % margin</b> · {x_115 - x_aeo:,.0f} ft{governs}",
            yanchor="bottom",
            font={"color": "#14663a", "size": 12},
        )
        note(
            x_aeo,
            y_b,
            f"all engines at 35 ft<br><b>{x_aeo:,.0f} ft</b>",
            xanchor="right",
            xshift=-6,
            font={"color": "#14663a", "size": 11},
            align="right",
        )

    # faint flight path + rotation / lift-off markers (labels sit on the grass)
    fig.add_scatter(
        x=lead["x"],
        y=np.asarray(lead["h"]) * exag,
        mode="lines",
        line={"color": lead_c, "width": 1.2, "dash": "dot"},
        opacity=0.6,
        hoverinfo="skip",
        showlegend=False,
        row=1,
        col=1,
    )
    marks = [
        (n, lab, _event_x(lead, n), _event_t(lead, n))
        for n, lab in (("VR", "rotate"), ("liftoff", "lift-off"))
    ]
    marks = [m for m in marks if m[2] is not None]
    d_lead = s["aeo_distance_ft"] if aeo_mode else s["d_go_ft"]
    fig.add_scatter(
        x=[m[2] for m in marks] + [d_lead],
        y=[_at(lead, "h", m[3]) * exag for m in marks] + [screen * exag],
        mode="markers",
        marker={"size": 6, "color": "white", "line": {"color": lead_c, "width": 2}},
        hoverinfo="skip",
        showlegend=False,
        row=1,
        col=1,
    )
    for _, lab, x, _ in marks:
        note(x, 0.3 * y_bot, lab, font={"size": 10, "color": "#1d3f1a"})

    # ---- runway strip (row 2, plan view) ---------------------------------------------
    shape(
        2, type="rect", x0=x_lo, x1=x_hi, y0=-1, y1=1, fillcolor=GRASS, line_width=0, layer="below"
    )
    shape(
        2,
        type="rect",
        x0=0,
        x1=x_hi * 1.5,
        y0=-0.42,
        y1=0.42,
        fillcolor=ASPHALT,
        line_width=0,
        layer="below",
    )
    for j in range(6):  # threshold "piano keys"
        y0 = -0.36 + j * 0.125
        shape(
            2,
            type="rect",
            x0=0.004 * x_hi,
            x1=0.022 * x_hi,
            y0=y0,
            y1=y0 + 0.07,
            fillcolor="white",
            line_width=0,
            layer="below",
        )
    shape(
        2,
        type="line",
        x0=0.035 * x_hi,
        x1=x_hi * 1.5,
        y0=0,
        y1=0,
        line={"color": "white", "width": 2, "dash": "dash"},
        layer="below",
    )

    beyond = []
    for r in refs:
        L = float(r["length_ft"])
        tag = f"{r.get('short', r['label'])} · {L:,.0f} ft"
        if L <= x_hi:
            right = L > 0.7 * x_hi  # labels near the right edge go on the left of their line
            shape(
                2,
                type="line",
                x0=L,
                x1=L,
                y0=-0.42,
                y1=0.42,
                line={"color": "white", "width": 2},
                opacity=0.75,
            )
            note(
                L,
                -0.71,
                tag,
                row=2,
                xanchor="right" if right else "left",
                xshift=-3 if right else 3,
                font={"size": 10, "color": "#243b20"},
            )
        else:
            beyond.append(f"{tag} ›")
    if beyond:  # the runway "continues" off the right edge
        note(
            x_hi,
            -0.2,
            "   ".join(beyond),
            row=2,
            xanchor="right",
            xshift=-6,
            font={"size": 10, "color": "#e6e9ee"},
        )

    def vline(x: float, color: str, width: float, dash: str | None, opacity: float) -> None:
        fig.add_shape(
            type="line",
            xref="x",
            yref="paper",
            x0=x,
            x1=x,
            y0=0,
            y1=1,
            line={"color": color, "width": width, "dash": dash},
            opacity=opacity,
        )

    bfl_op = 0.3 if aeo_mode else 1.0
    if _ok(base):
        b = base["scalars"]
        vline(b["bfl_ft"], BFL_C, 2, "dash", 0.55 * bfl_op)
        vline(b["faa_field_length_ft"], FAA_C, 2, "dash", 0.55)
        note(
            x_lo,
            0.72,
            "dashed = pinned baseline",
            row=2,
            xanchor="left",
            xshift=4,
            font={"size": 10, "color": "white"},
        )
    vline(s["bfl_ft"], BFL_C, 3.5, None, bfl_op)
    vline(s["faa_field_length_ft"], FAA_C, 3.5, None, 1.0)
    note(
        s["bfl_ft"],
        0.72,
        f"<b>BFL {s['bfl_ft']:,.0f} ft</b>",
        row=2,
        xanchor="right",
        xshift=-5,
        bgcolor=BFL_C,
        opacity=0.45 if aeo_mode else 1.0,
        font={"color": "white", "size": 12},
        borderpad=3,
    )
    note(
        s["faa_field_length_ft"],
        0.72,
        f"<b>FAA field {s['faa_field_length_ft']:,.0f} ft</b>",
        row=2,
        xanchor="left",
        xshift=5,
        bgcolor=FAA_C,
        font={"color": "white", "size": 12},
        borderpad=3,
    )

    # ---- animated traces --------------------------------------------------------------
    branches = ["aeo"] if aeo_mode else ["stop", "go"]
    t_end = max(cur[b]["t"][-1] for b in branches)
    if has_base:
        t_end = max(t_end, *(base[b]["t"][-1] for b in branches))
    dt_frame = speed / FPS
    if t_end / dt_frame > MAX_FRAMES:
        dt_frame = t_end / MAX_FRAMES
    frame_ms = 1000.0 * dt_frame / speed
    times = np.arange(0.0, t_end + dt_frame, dt_frame)

    names = {"aeo": "All engines", "stop": "Reject (stop)", "go": "Continue (go, 1 engine out)"}
    colors = {"aeo": AEO_C, "stop": STOP_C, "go": GO_C}
    movers = []  # (states, color, name, show legend)
    if has_base:
        movers += [
            (_states(base[b], times, exag), GHOST, "baseline", i == 0)
            for i, b in enumerate(branches)
        ]
    movers += [(_states(cur[b], times, exag), colors[b], names[b], True) for b in branches]

    dyn: list[int] = []
    for (x, y, th), color, name, legend in movers:
        ax, ay = _aircraft(px, x[0], y[0], th[0])
        dyn.append(len(fig.data))
        fig.add_scatter(
            x=ax,
            y=ay,
            mode="lines",
            fill="toself",
            fillcolor=color,
            line={"color": color, "width": 1},
            opacity=0.55 if color == GHOST else 1.0,
            hoverinfo="skip",
            name=name,
            showlegend=legend,
            legendgroup=name,
            row=1,
            col=1,
        )

    t_chute = None if aeo_mode else _event_t(stop_tr, "chute_deploy")
    if t_chute is not None:
        stop_states = movers[-2][0]
        dyn += [len(fig.data), len(fig.data) + 1]
        fig.add_scatter(
            x=[],
            y=[],
            mode="lines",
            line={"color": "#6b7280", "width": 1},
            hoverinfo="skip",
            showlegend=False,
            row=1,
            col=1,
        )
        fig.add_scatter(
            x=[],
            y=[],
            mode="lines",
            fill="toself",
            fillcolor="#f2f2f2",
            line={"color": STOP_C, "width": 1.5},
            hoverinfo="skip",
            name="drag chute",
            showlegend=True,
            row=1,
            col=1,
        )

    burst = t_ef is not None
    if burst:
        i_ef = int(np.searchsorted(times, t_ef))
        bx = float(np.interp(t_ef, go_tr["t"], go_tr["x"])) + px.kx * _SCALE * _ENGINE_PX[0]
        by = float(np.interp(t_ef, go_tr["t"], go_tr["h"])) * exag + px.ky * _SCALE * _ENGINE_PX[1]
        dyn += [len(fig.data), len(fig.data) + 1]
        for c in (FIRE_OUT, FIRE_IN):
            fig.add_scatter(
                x=[],
                y=[],
                mode="lines",
                fill="toself",
                fillcolor=c,
                line={"color": c, "width": 1},
                hoverinfo="skip",
                showlegend=False,
                row=1,
                col=1,
            )

    dyn.append(len(fig.data))
    fig.add_scatter(
        x=[x_lo + 0.012 * (x_hi - x_lo)],
        y=[0.86 * y_top],
        mode="text",
        text=[""],
        textposition="middle right",
        hoverinfo="skip",
        showlegend=False,
        textfont={"size": 13, "color": INK, "family": FONT},
        row=1,
        col=1,
    )

    burst_frames = 14

    def caption(t: float) -> str:
        def v(tr: dict) -> float:
            return _at(tr, "veas", min(t, tr["t"][-1]))

        if aeo_mode:
            return f"t = {t:4.1f} s     all engines {v(aeo_tr):3.0f} kt"
        return f"t = {t:4.1f} s     go {v(go_tr):3.0f} kt     stop {v(stop_tr):3.0f} kt"

    def frame_data(i: int, t: float) -> list:
        data = []
        for (x, y, th), *_ in movers:
            ax, ay = _aircraft(px, x[i], y[i], th[i])
            data.append(go.Scatter(x=ax, y=ay))
        if t_chute is not None:
            if t >= t_chute:
                (cx, cy), (lx, ly) = _chute(px, stop_states[0][i], stop_states[1][i])
            else:
                cx = cy = lx = ly = []
            data += [go.Scatter(x=lx, y=ly), go.Scatter(x=cx, y=cy)]
        if burst:
            k = i - i_ef
            if 0 <= k < burst_frames:
                g = math.sin(math.pi * (k + 1) / (burst_frames + 1))
                for r in (26 * g, 13 * g):
                    sx, sy = _star(px, bx, by, r)
                    data.append(go.Scatter(x=sx, y=sy))
            else:
                data += [go.Scatter(x=[], y=[]), go.Scatter(x=[], y=[])]
        data.append(go.Scatter(text=[caption(t)]))
        return data

    frames = [
        go.Frame(data=frame_data(i, t), traces=dyn, name=f"{t:.2f}") for i, t in enumerate(times)
    ]
    fig.frames = frames
    for idx, tr in zip(dyn, frames[0].data, strict=True):  # initial state = frame 0
        if tr.x is not None:
            fig.data[idx].x = tr.x
            fig.data[idx].y = tr.y
        if tr.text is not None:
            fig.data[idx].text = tr.text

    fig.update_layout(
        height=height,
        margin={"l": 52, "r": 16, "t": 36, "b": 78},
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font={"color": INK, "size": 12, "family": FONT},
        hovermode=False,
        legend={
            "orientation": "h",
            "x": 1,
            "xanchor": "right",
            "y": 1.0,
            "yanchor": "bottom",
            "bgcolor": "rgba(255,255,255,0.6)",
            "font": {"size": 12},
        },
        updatemenus=[
            {
                "type": "buttons",
                "direction": "left",
                "x": 0.0,
                "y": -0.075,
                "xanchor": "left",
                "yanchor": "top",
                "pad": {"t": 0, "r": 6},
                "showactive": False,
                "bgcolor": "white",
                "bordercolor": "#c7cfd8",
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
                "x": 0.16,
                "y": -0.04,
                "len": 0.84,
                "yanchor": "top",
                "pad": {"t": 0},
                "currentvalue": {"visible": False},
                "tickcolor": "rgba(0,0,0,0)",
                "font": {"color": "rgba(0,0,0,0)"},
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
    fig.update_xaxes(range=[x_lo, x_hi], showgrid=False, zeroline=False, row=1, col=1)
    fig.update_xaxes(
        range=[x_lo, x_hi],
        showgrid=False,
        zeroline=False,
        dtick=1000,
        tickformat=",",
        ticksuffix=" ft",
        ticks="outside",
        row=2,
        col=1,
    )
    ticks = [0, 10, 20, 35] if exag >= 6 else [0, 35]
    fig.update_yaxes(
        range=[y_bot, y_top],
        tickvals=[v * exag for v in ticks],
        ticktext=[f"{v} ft" for v in ticks],
        showgrid=True,
        gridcolor="rgba(255,255,255,0.5)",
        zeroline=False,
        fixedrange=True,
        row=1,
        col=1,
    )
    fig.update_yaxes(range=[-1, 1], visible=False, fixedrange=True, row=2, col=1)
    return fig


# ====================================================================================
# detail charts
# ====================================================================================
def _runs(cur: Data, base: Data | None):
    out = []
    if _ok(base):
        out.append((base, "dash", " (baseline)"))
    out.append((cur, None, ""))
    return out


# per-event label offsets (pixels) on the speed chart: keeps neighbouring labels apart
_SPEED_LABELS = {
    ("go", "engine_failure"): ("V_EF", 30, 38),
    ("go", "V1"): ("V1", -60, -34),
    ("go", "VR"): ("VR", -48, -52),
    ("go", "liftoff"): ("V_LOF", -20, -70),
    ("go", "screen_height"): ("V2 (35 ft)", 40, -40),
    ("stop", "idle"): ("idle", 50, 6),
    ("stop", "spoilers"): ("spoilers", 60, 24),
    ("stop", "chute_deploy"): ("chute", 55, -14),
    ("stop", "stopped"): ("stopped", -10, -36),
    ("aeo", "screen_height"): ("AEO at 35 ft", 50, 20),
}


def speeds(cur: Data, base: Data | None) -> go.Figure:
    fig = go.Figure()
    for d, dash, sfx in _runs(cur, base):
        for br, c, lab in (
            ("go", GO_C, "Go (1 engine out)"),
            ("stop", STOP_C, "Stop"),
            ("aeo", AEO_C, "All engines"),
        ):
            tr = d[br]
            fig.add_scatter(
                x=tr["t"],
                y=tr["veas"],
                name=lab + sfx,
                mode="lines",
                line={"color": c, "width": 2, "dash": dash},
                opacity=0.55 if dash else 1.0,
                hovertemplate="%{y:.1f} kt",
            )
    s = cur["scalars"]
    v_s = s["v_s_kts"]
    v2min = cur.get("v2_min_ratio", 1.2) * v_s
    fig.add_hline(
        y=v_s,
        line={"color": MUTED, "width": 1, "dash": "dot"},
        annotation_text=f"V_S stall {v_s:.0f} kt",
        annotation_position="bottom left",
        annotation_font={"size": 11, "color": MUTED},
    )
    fig.add_hline(
        y=v2min,
        line={"color": MUTED, "width": 1, "dash": "dash"},
        annotation_text=f"V2 min = {cur.get('v2_min_ratio', 1.2):g} V_S",
        annotation_position="top left",
        annotation_font={"size": 11, "color": MUTED},
    )
    for br, color in (("go", GO_C), ("stop", STOP_C), ("aeo", AEO_C)):
        tr = cur[br]
        for e in tr["events"]:
            key = (br, e["name"])
            if key not in _SPEED_LABELS:
                continue
            lab, axo, ayo = _SPEED_LABELS[key]
            v = _at(tr, "veas", e["t_s"])
            fig.add_annotation(
                x=e["t_s"],
                y=v,
                text=f"<b>{lab}</b> {v:.0f} kt" if br == "go" else lab,
                ax=axo,
                ay=ayo,
                showarrow=True,
                arrowhead=0,
                arrowwidth=1,
                arrowcolor=color,
                font={"size": 11, "color": INK},
                bgcolor="rgba(255,255,255,0.85)",
            )
            fig.add_scatter(
                x=[e["t_s"]],
                y=[v],
                mode="markers",
                showlegend=False,
                hoverinfo="skip",
                marker={"size": 7, "color": "white", "line": {"color": color, "width": 2}},
            )
    _base_layout(fig, "Airspeed vs time, with the V-speeds (KEAS)", 460)
    fig.update_xaxes(title="time since brake release [s]")
    fig.update_yaxes(title="equivalent airspeed [kt]")
    return fig


def _event_lines(fig: go.Figure, tr: dict, row: int | None = None, col: int | None = None) -> None:
    for t, lab in _merged_events(tr):
        kw = {"row": row, "col": col} if row else {}
        fig.add_vline(
            x=t,
            line={"color": "#9aa5b1", "width": 1, "dash": "dot"},
            annotation_text=lab,
            annotation_position="top",
            annotation_textangle=-90,
            annotation_font={"size": 10, "color": MUTED},
            **kw,
        )


def forces_angles(cur: Data, base: Data | None, tab: str, branch: str) -> go.Figure:
    fig = go.Figure()
    series = (
        [
            ("T", C1, "thrust"),
            ("D", C2, "drag"),
            ("L", C3, "lift"),
            ("N", C4, "normal force"),
            ("F", C5, "friction"),
        ]
        if tab == "forces"
        else [
            ("theta", C1, "θ pitch"),
            ("alpha", C2, "α angle of attack"),
            ("gamma", C3, "γ flight path"),
        ]
    )
    for d, dash, sfx in _runs(cur, base):
        tr = d[branch]
        for key, c, lab in series:
            fig.add_scatter(
                x=tr["t"],
                y=tr[key],
                name=lab + sfx,
                mode="lines",
                line={"color": c, "width": 2, "dash": dash},
                opacity=0.55 if dash else 1.0,
            )
    _event_lines(fig, cur[branch])
    names = {"go": "continued takeoff", "stop": "rejected takeoff", "aeo": "all-engines takeoff"}
    title = ("Forces" if tab == "forces" else "Angles") + f" vs time ({names[branch]})"
    _base_layout(fig, title, 460)
    fig.update_layout(margin={"t": 90})
    fig.update_xaxes(title="time since brake release [s]")
    fig.update_yaxes(
        title="force [lbf]" if tab == "forces" else "angle [deg]",
        tickformat="," if tab == "forces" else None,
    )
    return fig


def positions(cur: Data, base: Data | None) -> go.Figure:
    fig = make_subplots(
        1, 2, subplot_titles=("distance vs time", "height vs distance"), horizontal_spacing=0.1
    )
    for d, dash, sfx in _runs(cur, base):
        for br, c, lab in (
            ("go", GO_C, "Go"),
            ("stop", STOP_C, "Stop"),
            ("aeo", AEO_C, "All engines"),
        ):
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
    for br, color in (("go", GO_C), ("stop", STOP_C)):
        tr = cur[br]
        ev = [
            e
            for e in tr["events"]
            if e["name"] in ("engine_failure", "V1", "VR", "liftoff", "screen_height", "stopped")
        ]
        fig.add_scatter(
            x=[e["t_s"] for e in ev],
            y=[e["x_ft"] for e in ev],
            mode="markers+text",
            text=[EVENT_LABELS[e["name"]] for e in ev],
            textposition="middle right",
            textfont={"size": 10},
            marker={"size": 7, "color": "white", "line": {"color": color, "width": 2}},
            showlegend=False,
            hoverinfo="skip",
            row=1,
            col=1,
        )
    tr = cur["go"]
    ev = [
        e for e in tr["events"] if e["name"] in ("VR", "liftoff", "theta_target", "screen_height")
    ]
    fig.add_scatter(
        x=[e["x_ft"] for e in ev],
        y=[_at(tr, "h", e["t_s"]) for e in ev],
        mode="markers+text",
        text=[EVENT_LABELS[e["name"]] for e in ev],
        textposition="top left",
        textfont={"size": 10},
        marker={"size": 7, "color": "white", "line": {"color": GO_C, "width": 2}},
        showlegend=False,
        hoverinfo="skip",
        row=1,
        col=2,
    )
    _base_layout(fig, "", 440)
    fig.update_layout(hovermode="closest")
    fig.update_xaxes(title="time [s]", row=1, col=1)
    fig.update_yaxes(title="x [ft]", tickformat=",", row=1, col=1)
    fig.update_xaxes(title="x [ft]", tickformat=",", row=1, col=2)
    fig.update_yaxes(title="h [ft]", row=1, col=2)
    return fig


def v1_trade(
    cur: Data, sweep: dict, base: Data | None = None, base_sweep: dict | None = None
) -> go.Figure:
    fig = go.Figure()
    for d, sw, dash, sfx in ((base, base_sweep, "dash", " (baseline)"), (cur, sweep, None, "")):
        if not _ok(d) or not sw:
            continue
        fig.add_scatter(
            x=sw["v1_kts"],
            y=sw["d_go_ft"],
            name="Go: continue to 35 ft" + sfx,
            mode="lines",
            line={"color": GO_C, "width": 2.5, "dash": dash},
            hovertemplate="%{y:,.0f} ft",
        )
        fig.add_scatter(
            x=sw["v1_kts"],
            y=sw["d_stop_ft"],
            name="Stop: brake to rest + 2 s" + sfx,
            mode="lines",
            line={"color": STOP_C, "width": 2.5, "dash": dash},
            hovertemplate="%{y:,.0f} ft",
        )
    s = cur["scalars"]
    fig.add_scatter(
        x=[s["v1_kts"]],
        y=[s["bfl_ft"]],
        mode="markers",
        showlegend=False,
        marker={"size": 13, "color": BFL_C, "line": {"color": "white", "width": 2}},
        hovertemplate="V1 %{x:.1f} kt<br>BFL %{y:,.0f} ft<extra></extra>",
    )
    fig.add_annotation(
        x=s["v1_kts"],
        y=s["bfl_ft"],
        ax=60,
        ay=-50,
        text=(
            f"<b>balanced</b><br>V1 {s['v1_kts']:.1f} kt<br>BFL {s['bfl_ft']:,.0f} ft"
            if s["balanced"]
            else f"<b>unbalanced</b><br>{s['unbalanced_reason']}"
        ),
        showarrow=True,
        arrowhead=0,
        arrowcolor=BFL_C,
        align="left",
        bgcolor="rgba(255,255,255,0.9)",
        bordercolor=BFL_C,
    )
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.01,
        y=0.98,
        showarrow=False,
        align="left",
        xanchor="left",
        yanchor="top",
        font={"size": 11, "color": MUTED},
        text="later V1 → less runway left to stop, more speed to go",
    )
    _base_layout(fig, "The V1 trade: go and stop distance vs decision speed", 440)
    fig.update_xaxes(title="V1 [KEAS]")
    fig.update_yaxes(title="distance from brake release [ft]", tickformat=",")
    return fig


def heatmap(hm: dict, cur: Data, base: Data | None = None) -> go.Figure:
    k = hm["k"]
    z = np.array([[np.nan if v is None else v for v in row] for row in hm["z"]], dtype=float)
    fig = go.Figure()
    fig.add_heatmap(
        x=k,
        y=k,
        z=z,
        colorscale="Viridis",
        reversescale=False,
        colorbar={"title": {"text": "BFL [ft]"}, "tickformat": ","},
        hovertemplate="k_CD %{x}<br>k_CL %{y}<br>BFL %{z:,.0f} ft<extra></extra>",
        xgap=2,
        ygap=2,
    )
    lo, hi = np.nanmin(z), np.nanmax(z)
    for i, kcl in enumerate(k):
        for j, kcd in enumerate(k):
            v = z[i, j]
            txt = "—" if np.isnan(v) else f"{v / 1000:.1f}k"
            frac = 0.5 if np.isnan(v) or hi == lo else (v - lo) / (hi - lo)
            fig.add_annotation(
                x=kcd,
                y=kcl,
                text=txt,
                showarrow=False,
                font={"size": 12, "color": INK if frac > 0.62 else "white"},
            )
    pts = [(cur, "current", "circle-open", "white")]
    if _ok(base):
        pts.insert(0, (base, "baseline", "x-thin-open", "#ffb3b3"))
    for d, name, sym, col in pts:
        fig.add_scatter(
            x=[d["k_CD"]],
            y=[d["k_CL"]],
            mode="markers",
            name=name,
            marker={"symbol": sym, "size": 22, "line": {"color": col, "width": 3}},
            hovertemplate=f"{name}: k_CD %{{x}}, k_CL %{{y}}<extra></extra>",
        )
    _base_layout(fig, "Aero sensitivity: BFL over lift × drag multipliers", 480)
    fig.update_layout(hovermode="closest", legend={"y": -0.16})
    fig.update_xaxes(title="k_CD (drag multiplier)", tickvals=k, gridcolor="rgba(0,0,0,0)")
    fig.update_yaxes(title="k_CL (lift multiplier)", tickvals=k, gridcolor="rgba(0,0,0,0)")
    return fig


def aircraft(ad: dict) -> go.Figure:
    fig = make_subplots(
        2,
        2,
        subplot_titles=(
            "lift curve CL(α)",
            "drag CD(α)",
            "drag polar",
            f"thrust per engine at {ad['temperature_F']:.0f} °F",
        ),
        horizontal_spacing=0.11,
        vertical_spacing=0.16,
    )
    scaled = abs(ad["k_CL"] - 1) > 1e-9 or abs(ad["k_CD"] - 1) > 1e-9
    a = ad["alpha_deg"]
    if scaled:
        for (r, c), x, y in (
            ((1, 1), a, ad["cl_raw"]),
            ((1, 2), a, ad["cd_raw"]),
            ((2, 1), ad["cd_raw"], ad["cl_raw"]),
        ):
            fig.add_scatter(
                x=x,
                y=y,
                mode="lines",
                line={"color": "#9aa5b1", "width": 1.5, "dash": "dash"},
                name="table (k = 1)",
                legendgroup="raw",
                showlegend=(r, c) == (1, 1),
                row=r,
                col=c,
            )
    lab = f"used (k_CL {ad['k_CL']:g}, k_CD {ad['k_CD']:g})"
    fig.add_scatter(
        x=a,
        y=ad["cl"],
        mode="lines",
        line={"color": C1, "width": 2.5},
        name=lab,
        legendgroup="used",
        row=1,
        col=1,
    )
    fig.add_scatter(
        x=a,
        y=ad["cd"],
        mode="lines",
        line={"color": C1, "width": 2.5},
        showlegend=False,
        legendgroup="used",
        row=1,
        col=2,
    )
    fig.add_scatter(
        x=ad["cd"],
        y=ad["cl"],
        mode="lines",
        line={"color": C1, "width": 2.5},
        showlegend=False,
        legendgroup="used",
        row=2,
        col=1,
    )
    fig.add_hline(
        y=ad["cl_max"],
        line={"color": MUTED, "dash": "dot", "width": 1},
        row=1,
        col=1,
        annotation_text=f"CLmax {ad['cl_max']:.2f}",
        annotation_position="bottom right",
        annotation_font={"size": 10, "color": MUTED},
    )
    for th, txt in ((ad["theta_ground_deg"], "ground roll"), (ad["theta_target_deg"], "max pitch")):
        fig.add_vline(
            x=th,
            line={"color": MUTED, "dash": "dot", "width": 1},
            row=1,
            col=1,
            annotation_text=txt,
            annotation_position="top left",
            annotation_textangle=-90,
            annotation_font={"size": 10, "color": MUTED},
        )
    fig.add_scatter(
        x=ad["v_kts"],
        y=ad["thrust_per_engine"],
        mode="lines",
        line={"color": C2, "width": 2.5},
        name="takeoff thrust",
        row=2,
        col=2,
    )
    fig.add_hline(
        y=ad["idle_per_engine"],
        line={"color": MUTED, "dash": "dot", "width": 1},
        row=2,
        col=2,
        annotation_text=f"idle {ad['idle_per_engine']:,.0f} lbf",
        annotation_position="top right",
        annotation_font={"size": 10, "color": MUTED},
    )
    fig.add_vline(
        x=ad["v_s_kts"],
        line={"color": MUTED, "dash": "dot", "width": 1},
        row=2,
        col=2,
        annotation_text="V_S",
        annotation_position="bottom left",
        annotation_font={"size": 10, "color": MUTED},
    )
    _base_layout(fig, "", 640)
    fig.update_layout(hovermode="closest", legend={"y": -0.1})
    fig.update_xaxes(title="α [deg]", row=1, col=1)
    fig.update_xaxes(title="α [deg]", row=1, col=2)
    fig.update_xaxes(title="CD", row=2, col=1)
    fig.update_xaxes(title="true airspeed [kt]", row=2, col=2)
    fig.update_yaxes(title="CL", row=1, col=1)
    fig.update_yaxes(title="CD", row=1, col=2)
    fig.update_yaxes(title="CL", row=2, col=1)
    fig.update_yaxes(title="lbf", tickformat=",", rangemode="tozero", row=2, col=2)
    return fig
