"""Aircraft builder: a form generated from the pydantic AircraftConfig model.

* Start from scratch, from an existing aircraft, or by dropping in an aircraft.yaml.
* Drop in table CSVs (aero: alpha_deg, CL, CD; thrust: airspeed_kts[, temperature_F],
  thrust_lbf[, tsfc_per_hr]); they are checked with the solver's own loaders, plotted,
  and offered as table choices.
* Live validation with the same model the solver uses.
* Download a .zip (aircraft.yaml + CSVs) to hand to someone else, or save straight into
  aircraft/<folder> so it shows up in the simulator.
"""

from __future__ import annotations

import base64
import io
import re
import tempfile
import types
import typing
import zipfile
from pathlib import Path
from typing import Any, Literal

import plotly.graph_objects as go
import yaml
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from plotly.subplots import make_subplots
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined

from bfl import list_aircraft
from bfl.aero import load_aero_table
from bfl.config import AircraftConfig, default_aircraft_root, resolve_aircraft_dir
from bfl.propulsion import load_thrust_table
from bfl.tables import read_csv_table

from . import figures

SKIP = {"directory", "synthetic"}
# Aero and thrust tables are set up the same way: a "name: file.csv" list, and a
# dropdown that picks the default from that list (both are compared in the trade study).
TABLE_LISTS = {"aero.configurations": "aero", "engines.thrust_tables": "thrust"}
DEFAULT_KEYS = {"aero.takeoff_configuration": "aero.configurations",
                "engines.thrust_table": "engines.thrust_tables",
                "landing.configuration": "aero.configurations"}  # fmt: skip
LABELS = {
    "aero.configurations": "aero tables",
    "aero.takeoff_configuration": "default aero table",
    "engines.thrust_tables": "thrust tables",
    "engines.thrust_table": "default thrust table",
    "landing.configuration": "landing aero table",
}
GROUP_TITLES = {
    "": "General",
    "geometry": "Geometry",
    "weight": "Weight",
    "engines": "Engines",
    "attitude": "Attitude",
    "aero": "Aerodynamics",
    "spoilers": "Spoilers (increments while braking)",
    "chute": "Drag chute",
    "speeds": "Speeds",
    "ground_effect": "Ground effect (Raymer)",
    "gear": "Gear limits (optional)",
    "certification": "Certification (field-length rules)",
    "landing": "Landing (flaps, technique, stopping devices)",
}


# ------------------------------------------------------------------------------------
# model introspection
# ------------------------------------------------------------------------------------
def _strip_optional(ann):
    origin = typing.get_origin(ann)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        return (args[0] if len(args) == 1 else ann), True
    return ann, False


def _kind(path: str, ann) -> str:
    ann, _ = _strip_optional(ann)
    if path in DEFAULT_KEYS:
        return "key"
    if typing.get_origin(ann) is Literal:
        return "choice"
    if typing.get_origin(ann) is dict:
        return "dict"
    if ann is bool:
        return "bool"
    if ann is int:
        return "int"
    if ann is float:
        return "number"
    return "text"


def _default(f) -> Any:
    if f.default is not PydanticUndefined:
        return f.default
    if f.default_factory is not None:
        return f.default_factory()
    return None


def walk(model: type[BaseModel] = AircraftConfig, prefix: str = "") -> list[dict]:
    """Flat list of form fields (in model order) with their group."""
    out = []
    for name, f in model.model_fields.items():
        if name in SKIP:
            continue
        path = f"{prefix}{name}"
        ann, _ = _strip_optional(f.annotation)
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            out += walk(ann, path + ".")
            continue
        out.append(
            {
                "path": path,
                "group": prefix.rstrip("."),
                "name": name,
                "kind": _kind(path, f.annotation),
                "choices": list(typing.get_args(ann)) if typing.get_origin(ann) is Literal else [],
                "default": _default(f),
                "required": f.is_required(),
                "help": f.description or "",
            }
        )
    return out


FIELDS = walk()
PATHS = [f["path"] for f in FIELDS]


def _flatten(d: dict, prefix: str = "") -> dict[str, Any]:
    out = {}
    for k, v in d.items():
        p = f"{prefix}{k}"
        if p in PATHS:
            out[p] = v
        elif isinstance(v, dict):
            out.update(_flatten(v, p + "."))
    return out


def _to_widget(f: dict, v: Any) -> Any:
    k = f["kind"]
    if k == "bool":
        return ["on"] if v else []
    if k == "dict":
        return "\n".join(f"{a}: {b}" for a, b in (v or {}).items())
    return v


def _from_widget(f: dict, v: Any) -> Any:
    k = f["kind"]
    if k == "bool":
        return "on" in (v or [])
    if k == "dict":
        out = {}
        for line in (v or "").splitlines():
            if ":" in line:
                a, b = line.split(":", 1)
                b = b.strip()
                try:
                    out[a.strip()] = float(b) if f["path"] == "aero.CLmax" else b
                except ValueError:
                    out[a.strip()] = b
        return out
    if k in ("text", "key"):
        return v if v not in ("", None) else None
    return v


def _unflatten(flat: dict[str, Any]) -> dict:
    out: dict = {}
    for p, v in flat.items():
        if v is None:
            continue
        node = out
        keys = p.split(".")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = v
    return out


# ------------------------------------------------------------------------------------
# CSV checks
# ------------------------------------------------------------------------------------
def _decode(contents: str) -> str:
    return base64.b64decode(contents.split(",", 1)[1]).decode("utf-8", errors="replace")


def check_csv(name: str, text: str) -> dict[str, Any]:
    """Classify and validate one CSV with the solver's own loaders."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / name
        p.write_text(text)
        header = next((ln for ln in text.splitlines() if ln and not ln.startswith("#")), "")
        cols = [c.strip() for c in header.split(",")]
        try:
            if "alpha_deg" in cols:
                t = load_aero_table(p)
                return {"kind": "aero", "ok": True, "msg": f"aero table, {len(t.cl.x)} rows",
                        "x": [a * 57.29577951308232 for a in t.cl.x], "cl": t.cl.y, "cd": t.cd.y}  # fmt: skip  # noqa: E501
            if "airspeed_kts" in cols:
                load_thrust_table(p)
                msg = "thrust table" + (" (2-D, with temperature)" if "temperature_F" in cols
                                        else "") + (", with TSFC" if "tsfc_per_hr" in cols else "")  # fmt: skip  # noqa: E501
                df = read_csv_table(p, ["airspeed_kts", "thrust_lbf"])
                curves = (
                    [(f"{t:g} °F", g.sort_values("airspeed_kts"))
                     for t, g in df.groupby("temperature_F")]
                    if "temperature_F" in df.columns
                    else [("", df.sort_values("airspeed_kts"))]
                )  # fmt: skip
                return {"kind": "thrust", "ok": True, "msg": msg,
                        "curves": [(lab, g["airspeed_kts"].tolist(), g["thrust_lbf"].tolist())
                                   for lab, g in curves]}  # fmt: skip
            return {"kind": "?", "ok": False,
                    "msg": "unknown table: needs alpha_deg,CL,CD or airspeed_kts,thrust_lbf"}  # fmt: skip  # noqa: E501
        except Exception as exc:  # noqa: BLE001
            return {"kind": "?", "ok": False, "msg": f"{type(exc).__name__}: {exc}"}


PLOT_TABS = (("aero", "Aero tables"), ("thrust", "Thrust tables"))


def _tint(hex_color: str, f: float) -> str:
    """Mix a colour with white by fraction f (0 = the colour, 1 = white)."""
    r, g, b = (int(hex_color[k : k + 2], 16) for k in (1, 3, 5))
    return "#{:02x}{:02x}{:02x}".format(*(round(x + (255 - x) * f) for x in (r, g, b)))


def _table_color(i: int) -> str:
    """One fixed colour per table (upload order), the same in both tabs' plots."""
    return figures.CATEGORICAL[i % len(figures.CATEGORICAL)]


def table_figure(files: dict[str, str], kind: str) -> go.Figure:
    """Plot the uploaded tables of one kind, exactly as written in the CSVs.

    Aero: CL(alpha), CD(alpha) and the drag polar side by side (one axis each, no
    shared second axis); every table is one colour across the three panels, markers
    are the table rows. Thrust: thrust per engine vs airspeed; a 2-D table draws one
    line per temperature in the table's colour, dark (cold) to light (hot), each
    labelled at its end.
    """
    infos = [(n, check_csv(n, t)) for n, t in files.items()]
    infos = [(n, i) for n, i in infos if i["ok"] and i["kind"] == kind]
    if not infos:
        what = "Aero" if kind == "aero" else "Thrust"
        return figures.empty(f"{what} tables appear here once uploaded or loaded", 300)
    line = {"width": 2}
    marker = {"size": 6}
    if kind == "aero":
        fig = make_subplots(
            1, 3, subplot_titles=("lift CL(α)", "drag CD(α)", "drag polar CL vs CD"),
            horizontal_spacing=0.09,
        )  # fmt: skip
        for i, (n, info) in enumerate(infos):
            c = _table_color(i)
            for col, (x, y) in enumerate(
                ((info["x"], info["cl"]), (info["x"], info["cd"]), (info["cd"], info["cl"])), 1
            ):
                fig.add_scatter(
                    x=x, y=y, mode="lines+markers", name=n, legendgroup=n,
                    showlegend=col == 1, line={**line, "color": c},
                    marker={**marker, "color": c}, row=1, col=col,
                    hovertemplate=f"{n}<br>%{{x:.3g}}, %{{y:.4g}}<extra></extra>",
                )  # fmt: skip
        figures._base_layout(fig, "", 360)
        fig.update_xaxes(title="α [deg]", row=1, col=1)
        fig.update_xaxes(title="α [deg]", row=1, col=2)
        fig.update_xaxes(title="CD", row=1, col=3)
        fig.update_yaxes(title="CL", row=1, col=1)
        fig.update_yaxes(title="CD", row=1, col=2)
        fig.update_yaxes(title="CL", row=1, col=3)
    else:
        fig = go.Figure()
        for i, (n, info) in enumerate(infos):
            c = _table_color(i)
            curves = info["curves"]
            for j, (lab, v, t) in enumerate(curves):
                # same hue per table; colder (more thrust) darker, hotter lighter
                shade = _tint(c, 0.6 * j / max(len(curves) - 1, 1)) if len(curves) > 1 else c
                name = f"{n} · {lab}" if lab else n
                fig.add_scatter(
                    x=v, y=t, mode="lines+markers", name=name, legendgroup=n,
                    line={**line, "color": shade}, marker={"size": 5, "color": shade},
                    hovertemplate=f"{name}<br>%{{x:.0f}} kt: %{{y:,.0f}} lbf<extra></extra>",
                )  # fmt: skip
                if lab:  # direct label at the end of each temperature line
                    fig.add_annotation(
                        x=v[-1], y=t[-1], text=lab, showarrow=False, xanchor="left",
                        xshift=6, font={"size": 11, "color": figures.MUTED},
                    )  # fmt: skip
        figures._base_layout(fig, "", 360)
        fig.update_xaxes(title="airspeed [kt] (true)")
        fig.update_layout(margin={"r": 60})
        fig.update_yaxes(title="thrust per engine [lbf]", tickformat=",", rangemode="tozero")
    fig.update_layout(hovermode="closest", legend={"orientation": "h", "y": -0.22, "x": 0})
    return fig


# ------------------------------------------------------------------------------------
# layout
# ------------------------------------------------------------------------------------
def _widget(f: dict):
    fid = {"type": "bf", "path": f["path"]}
    v = _to_widget(f, f["default"])
    k = f["kind"]
    if k == "bool":
        return dcc.Checklist(id=fid, value=v, options=[{"label": "", "value": "on"}],
                             className="checks")  # fmt: skip
    if k == "choice":
        return dcc.Dropdown(id=fid, value=v, clearable=False, searchable=False,
                            options=[{"label": c, "value": c} for c in f["choices"]])  # fmt: skip
    if k == "key":
        optional = f["default"] is None and not f["required"]
        return dcc.Dropdown(id=fid, value=v, options=[], clearable=optional,
                            placeholder="blank = takeoff table" if optional
                            else "pick one of the tables above")  # fmt: skip
    if k == "dict":
        ph = "name: file.csv" if f["path"] in TABLE_LISTS else "name: value"
        return dcc.Textarea(id=fid, value=v, className="bf-dict", placeholder=ph)
    if k == "int":  # counts: steppers make sense here
        return dcc.Input(id=fid, type="number", value=v, step=1, debounce=True,
                         className="num-input spin")  # fmt: skip
    if k == "number":
        return dcc.Input(id=fid, type="number", value=v, debounce=True, className="num-input")
    return dcc.Input(id=fid, type="text", value=v, debounce=True, className="num-input")


def _form() -> list:
    groups: dict[str, list] = {}
    for f in FIELDS:
        label = LABELS.get(f["path"], f["name"]) + (" *" if f["required"] else "")
        row = html.Div(
            className="bf-row",
            title=f["help"],
            children=[
                html.Label(label, className="bf-label"),
                _widget(f),
                html.Div(f["help"], className="bf-help") if f["help"] else None,
            ],
        )
        groups.setdefault(f["group"], []).append(row)
    return [
        html.Fieldset(
            className="bf-group",
            children=[html.Legend(GROUP_TITLES.get(g, g)), *rows],
        )
        for g, rows in groups.items()
    ]


def layout() -> html.Div:
    try:
        existing = list_aircraft()
    except FileNotFoundError:
        existing = []
    return html.Div(
        className="builder-page",
        children=[
            html.Div(
                className="card",
                children=[
                    html.H2("Aircraft builder"),
                    dcc.Markdown(
                        "Fill in the form (fields marked * are required; hover a field for "
                        "help), drop in the table CSVs, and download the aircraft as a .zip "
                        "or save it into `aircraft/`. Someone else can drop that "
                        "`aircraft.yaml` and its CSVs back in here to load it. Aero and "
                        "thrust tables work the same way: list one or more as "
                        "`name: file.csv` and pick the default; the others can be "
                        "selected on the simulator and compared in the trade study.",
                        className="hint",
                    ),
                    html.Div(
                        className="bf-top",
                        children=[
                            html.Div(
                                [
                                    html.Label("Start from"),
                                    dcc.Dropdown(
                                        id="bf-start",
                                        placeholder="blank form",
                                        options=[{"label": n, "value": n} for n in existing],
                                    ),
                                ],
                                className="bf-start",
                            ),  # fmt: skip
                            dcc.Upload(
                                id="bf-upload",
                                multiple=True,
                                className="bf-drop",
                                children=html.Div(
                                    [
                                        "Drop aircraft.yaml and/or CSV tables here, or ",
                                        html.A("browse"),
                                    ]
                                ),
                            ),  # fmt: skip
                        ],
                    ),
                    html.Div(id="bf-files", className="bf-files"),
                ],
            ),
            html.Div(
                className="builder-grid",
                children=[
                    html.Div(className="card bf-form", children=_form()),
                    html.Div(
                        className="card bf-side",
                        children=[
                            html.H3("Check"),
                            html.Div(id="bf-valid"),
                            dcc.Tabs(
                                id="bf-plot-tab",
                                value="aero",
                                children=[dcc.Tab(label=lab, value=v) for v, lab in PLOT_TABS],
                            ),  # fmt: skip
                            dcc.Graph(
                                id="bf-plot",
                                config={"displaylogo": False},
                                figure=figures.empty("Aero tables appear here", 300),
                            ),  # fmt: skip
                            html.H3("Export"),
                            html.Button(
                                "Download .zip",
                                id="bf-zip-btn",
                                n_clicks=0,
                                className="btn btn-primary",
                            ),  # fmt: skip
                            dcc.Download(id="bf-zip"),
                            html.Div(
                                className="bf-save",
                                children=[
                                    dcc.Input(
                                        id="bf-folder",
                                        placeholder="folder name, e.g. my_concept",
                                        className="num-input",
                                    ),  # fmt: skip
                                    dcc.Checklist(
                                        id="bf-overwrite",
                                        value=[],
                                        className="checks",
                                        options=[{"label": " overwrite", "value": "on"}],
                                    ),  # fmt: skip
                                    html.Button(
                                        "Save to aircraft/",
                                        id="bf-save-btn",
                                        n_clicks=0,
                                        className="btn",
                                    ),  # fmt: skip
                                ],
                            ),
                            html.Div(id="bf-save-msg", className="hint"),
                            html.H3("aircraft.yaml preview"),
                            html.Pre(id="bf-yaml", className="bf-yaml"),
                        ],
                    ),
                ],
            ),
            dcc.Store(id="bf-csvs", data={}),
        ],
    )


# ------------------------------------------------------------------------------------
# callbacks
# ------------------------------------------------------------------------------------
def _collect(values: list, ids: list) -> dict:
    by = {f["path"]: f for f in FIELDS}
    flat = {i["path"]: _from_widget(by[i["path"]], v) for v, i in zip(values, ids, strict=True)}
    return _unflatten(flat)


def _validate(data: dict, csvs: dict) -> tuple[AircraftConfig | None, list[str]]:
    errs: list[str] = []
    cfg = None
    try:
        cfg = AircraftConfig.model_validate(data)
    except ValidationError as e:
        for er in e.errors():
            loc = ".".join(str(x) for x in er["loc"])
            errs.append(f"{loc}: {er['msg']}")
    if cfg is not None:
        need = set(cfg.aero.configurations.values()) | set(cfg.engines.thrust_tables.values())
        missing = sorted(n for n in need if n not in csvs)
        errs += [f"table file '{m}' not uploaded" for m in missing]
        for n, text in csvs.items():
            info = check_csv(n, text)
            if not info["ok"]:
                errs.append(f"{n}: {info['msg']}")
    return cfg, errs


def _yaml_text(data: dict) -> str:
    return "# generated by the aircraft builder\n" + yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False
    )


def register(app) -> None:
    @app.callback(
        Output({"type": "bf", "path": ALL}, "value"),
        Output("bf-csvs", "data"),
        Output("bf-files", "children"),
        Input("bf-start", "value"),
        Input("bf-upload", "contents"),
        State("bf-upload", "filename"),
        State("bf-csvs", "data"),
        State({"type": "bf", "path": ALL}, "value"),
        prevent_initial_call=True,
    )
    def on_load(start, contents, filenames, csvs, current):
        csvs = dict(csvs or {})
        values = list(current)
        loaded = None
        if ctx.triggered_id == "bf-start" and start:
            d = resolve_aircraft_dir(start)
            loaded = yaml.safe_load((d / "aircraft.yaml").read_text())
            csvs = {p.name: p.read_text() for p in sorted(d.glob("*.csv"))}
        elif ctx.triggered_id == "bf-upload" and contents:
            for c, n in zip(contents, filenames, strict=True):
                text = _decode(c)
                if n.lower().endswith((".yaml", ".yml")):
                    loaded = yaml.safe_load(text) or {}
                elif n.lower().endswith(".csv"):
                    csvs[n] = text
        if loaded is not None:
            flat = _flatten(loaded)
            values = [_to_widget(f, flat.get(f["path"], f["default"])) for f in FIELDS]
        chips = [
            html.Span(
                f"{'✓' if (i := check_csv(n, t))['ok'] else '✗'} {n}: {i['msg']}",
                className="chip" + ("" if i["ok"] else " chip-warn"),
            )
            for n, t in csvs.items()
        ]
        return values, csvs, chips

    for key_path, list_path in DEFAULT_KEYS.items():

        @app.callback(
            Output({"type": "bf", "path": key_path}, "options"),
            Input({"type": "bf", "path": list_path}, "value"),
        )
        def on_table_names(text):
            names = [ln.split(":", 1)[0].strip() for ln in (text or "").splitlines()
                     if ":" in ln and ln.split(":", 1)[0].strip()]  # fmt: skip
            return [{"label": n, "value": n} for n in names]

    @app.callback(
        Output("bf-valid", "children"),
        Output("bf-yaml", "children"),
        Input({"type": "bf", "path": ALL}, "value"),
        Input("bf-csvs", "data"),
        State({"type": "bf", "path": ALL}, "id"),
    )
    def on_check(values, csvs, ids):
        data = _collect(values, ids)
        _, errs = _validate(data, csvs or {})
        kinds = {n: check_csv(n, t)["kind"] for n, t in (csvs or {}).items()}
        aero_files = [n for n, k in kinds.items() if k == "aero"]
        thrust_files = [n for n, k in kinds.items() if k == "thrust"]
        hint = html.Div(
            f"Uploaded aero tables: {', '.join(aero_files) or 'none'} · thrust tables: "
            f"{', '.join(thrust_files) or 'none'}. List them under 'aero tables' / 'thrust "
            "tables' as  name: file.csv, then pick the default of each.",
            className="hint",
        )  # fmt: skip
        if errs:
            box = html.Div(
                [html.Div(f"{len(errs)} problem(s)", className="badge badge-fail"),
                 html.Ul([html.Li(e) for e in errs]), hint])  # fmt: skip
        else:
            box = html.Div([html.Div("Valid: ready to export", className="badge badge-pass"),
                            hint])  # fmt: skip
        return box, _yaml_text(data)

    @app.callback(
        Output("bf-plot", "figure"),
        Input("bf-plot-tab", "value"),
        Input("bf-csvs", "data"),
    )
    def on_plot(tab, csvs):
        return table_figure(csvs or {}, tab or "aero")

    @app.callback(
        Output("bf-zip", "data"),
        Input("bf-zip-btn", "n_clicks"),
        State({"type": "bf", "path": ALL}, "value"),
        State({"type": "bf", "path": ALL}, "id"),
        State("bf-csvs", "data"),
        State("bf-folder", "value"),
        prevent_initial_call=True,
    )
    def on_zip(_n, values, ids, csvs, folder):
        data = _collect(values, ids)
        name = _safe(folder) or _safe(data.get("name", "")) or "aircraft"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(f"{name}/aircraft.yaml", _yaml_text(data))
            for n, t in (csvs or {}).items():
                z.writestr(f"{name}/{n}", t)
        return dcc.send_bytes(buf.getvalue(), f"{name}.zip")

    @app.callback(
        Output("bf-save-msg", "children"),
        Output("aircraft-saved", "data"),
        Input("bf-save-btn", "n_clicks"),
        State({"type": "bf", "path": ALL}, "value"),
        State({"type": "bf", "path": ALL}, "id"),
        State("bf-csvs", "data"),
        State("bf-folder", "value"),
        State("bf-overwrite", "value"),
        prevent_initial_call=True,
    )
    def on_save(_n, values, ids, csvs, folder, overwrite):
        data = _collect(values, ids)
        _, errs = _validate(data, csvs or {})
        if errs:
            return "Fix the problems first.", no_update
        name = _safe(folder)
        if not name:
            return "Give a folder name (letters, digits, _ and -).", no_update
        d = default_aircraft_root() / name
        if d.exists() and "on" not in (overwrite or []):
            return f"aircraft/{name} exists; tick 'overwrite' to replace it.", no_update
        d.mkdir(parents=True, exist_ok=True)
        (d / "aircraft.yaml").write_text(_yaml_text(data))
        for n, t in (csvs or {}).items():
            (d / n).write_text(t)
        return f"Saved to aircraft/{name}: it is now in the simulator's aircraft list.", name


def _safe(s: str | None) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", (s or "").strip()).strip("_")
