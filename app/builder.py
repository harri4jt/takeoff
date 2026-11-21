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
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined

from bfl import list_aircraft
from bfl.aero import load_aero_table
from bfl.config import AircraftConfig, default_aircraft_root, resolve_aircraft_dir
from bfl.propulsion import load_thrust_table

from . import figures

SKIP = {"directory"}
CSV_FIELDS = {"engines.thrust_table"}
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
    if path in CSV_FIELDS:
        return "csv"
    if typing.get_origin(ann) is Literal:
        return "choice"
    if typing.get_origin(ann) is dict:
        return "dict"
    if ann is bool:
        return "bool"
    if ann in (int, float):
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
    if k in ("text", "csv"):
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
                return {"kind": "thrust", "ok": True, "msg": msg}
            return {"kind": "?", "ok": False,
                    "msg": "unknown table: needs alpha_deg,CL,CD or airspeed_kts,thrust_lbf"}  # fmt: skip  # noqa: E501
        except Exception as exc:  # noqa: BLE001
            return {"kind": "?", "ok": False, "msg": f"{type(exc).__name__}: {exc}"}


def _csv_figure(files: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for name, text in files.items():
        info = check_csv(name, text)
        if info["kind"] == "aero" and info["ok"]:
            fig.add_scatter(x=info["x"], y=info["cl"], name=f"{name} CL")
            fig.add_scatter(x=info["x"], y=info["cd"], name=f"{name} CD", yaxis="y2",
                            line={"dash": "dot"})  # fmt: skip
    if not fig.data:
        return figures.empty("Aero tables appear here once uploaded", 260)
    figures._base_layout(fig, "Uploaded aero tables", 320)
    fig.update_layout(
        xaxis_title="alpha [deg]", yaxis_title="CL",
        yaxis2={"title": "CD", "overlaying": "y", "side": "right", "showgrid": False},
        hovermode="x unified",
    )  # fmt: skip
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
    if k == "csv":
        return dcc.Dropdown(id=fid, value=v, options=[], placeholder="pick an uploaded CSV")
    if k == "dict":
        return dcc.Textarea(id=fid, value=v, className="bf-dict", placeholder="name: value")
    if k == "number":
        return dcc.Input(id=fid, type="number", value=v, debounce=True, className="num-input")
    return dcc.Input(id=fid, type="text", value=v, debounce=True, className="num-input")


def _form() -> list:
    groups: dict[str, list] = {}
    for f in FIELDS:
        label = f["name"] + (" *" if f["required"] else "")
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
                        "`aircraft.yaml` and its CSVs back in here to load it. One takeoff "
                        "aero table is enough; list alternatives under "
                        "`aero.configurations` and `engines.thrust_tables` to compare "
                        "them in the trade study.",
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
                            dcc.Graph(
                                id="bf-plot",
                                config={"displaylogo": False},
                                figure=figures.empty("Aero tables appear here", 260),
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
        need = set(cfg.aero.configurations.values())
        if cfg.engines.thrust_mode == "table" and cfg.engines.thrust_table:
            need.add(cfg.engines.thrust_table)
        need |= set(cfg.engines.thrust_tables.values())
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

    @app.callback(
        Output({"type": "bf", "path": "engines.thrust_table"}, "options"),
        Input("bf-csvs", "data"),
    )
    def on_csv_options(csvs):
        names = [n for n, t in (csvs or {}).items() if check_csv(n, t)["kind"] == "thrust"]
        return [{"label": n, "value": n} for n in names]

    @app.callback(
        Output("bf-valid", "children"),
        Output("bf-yaml", "children"),
        Output("bf-plot", "figure"),
        Input({"type": "bf", "path": ALL}, "value"),
        Input("bf-csvs", "data"),
        State({"type": "bf", "path": ALL}, "id"),
    )
    def on_check(values, csvs, ids):
        data = _collect(values, ids)
        _, errs = _validate(data, csvs or {})
        aero_files = [n for n, t in (csvs or {}).items() if check_csv(n, t)["kind"] == "aero"]
        hint = html.Div(
            "Uploaded aero tables: " + (", ".join(aero_files) or "none")
            + " → list them under aero.configurations as  name: file.csv",
            className="hint",
        )  # fmt: skip
        if errs:
            box = html.Div(
                [html.Div(f"{len(errs)} problem(s)", className="badge badge-fail"),
                 html.Ul([html.Li(e) for e in errs]), hint])  # fmt: skip
        else:
            box = html.Div([html.Div("Valid: ready to export", className="badge badge-pass"),
                            hint])  # fmt: skip
        return (
            box,
            _yaml_text(data),
            _csv_figure({n: t for n, t in (csvs or {}).items() if n in aero_files}),
        )

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
