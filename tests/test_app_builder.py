"""Creating and editing aircraft in the app's builder, through the real Dash callbacks.

Each test posts to the app's callback endpoint exactly as the browser does (Flask test
client, no browser), with the aircraft folder pointed at a temporary directory
(BFL_AIRCRAFT_DIR), so nothing under aircraft/ is touched.
"""

from __future__ import annotations

import base64
import io
import json
import shutil
import zipfile

import pytest
import yaml

pytest.importorskip("dash")

from bfl import compute_bfl, load_config  # noqa: E402
from bfl.config import default_aircraft_root  # noqa: E402

REPO_AIRCRAFT = default_aircraft_root()
ALL_BF = '{"path":["ALL"],"type":"bf"}'


@pytest.fixture
def ui(tmp_path, monkeypatch):
    """(app, client, aircraft root) with the two real aircraft copied into a temp root."""
    root = tmp_path / "aircraft"
    for name in ("b747_100", "sr71"):
        shutil.copytree(REPO_AIRCRAFT / name, root / name)
    monkeypatch.setenv("BFL_AIRCRAFT_DIR", str(root))
    from app import main

    app = main.create_app()
    return app, app.server.test_client(), root


def _fields():
    from app import builder

    return builder.FIELDS


def _spec(item_id: str, prop: str, values: dict, with_value: bool):
    """One input/state/output entry; the bf ALL wildcard expands to every form field."""
    if item_id == ALL_BF:
        out = []
        for i, f in enumerate(_fields()):
            e = {"id": {"type": "bf", "path": f["path"]}, "property": prop}
            if with_value:
                v = values.get((ALL_BF, prop))
                e["value"] = (
                    {"type": "bf", "path": f["path"]} if prop == "id" else (v[i] if v else None)
                )
            out.append(e)
        return out
    e = {"id": item_id, "property": prop}
    if with_value:
        e["value"] = values.get((item_id, prop))
    return e


def call(client, app, output_part: str, values: dict, triggered: list[str]) -> dict:
    """Run the callback whose output key contains ``output_part``; returns {id: {prop: v}}."""
    keys = list(app.callback_map)
    key = output_part if output_part in keys else next(k for k in keys if output_part in k)
    cb = app.callback_map[key]
    outs = cb["output"] if isinstance(cb["output"], list) else [cb["output"]]
    outputs = [
        _spec(ALL_BF if isinstance(o.component_id, dict) else o.component_id,
              o.component_property, values, False)
        for o in outs
    ]  # fmt: skip
    payload = {
        "output": key,
        "outputs": outputs if len(outputs) > 1 else outputs[0],
        "inputs": [_spec(i["id"], i["property"], values, True) for i in cb["inputs"]],
        "state": [_spec(s["id"], s["property"], values, True) for s in cb["state"]],
        "changedPropIds": triggered,
    }
    r = client.post("/_dash-update-component", json=payload)
    if r.status_code == 204:  # PreventUpdate / no_update everywhere
        return {}
    assert r.status_code == 200, r.data[:500]
    return r.get_json()["response"]


def _form_values(resp: dict) -> list:
    """The form values (in FIELDS order) from an on_load response."""
    by = {json.loads(k)["path"]: v["value"] for k, v in resp.items() if k.startswith("{")}
    return [by[f["path"]] for f in _fields()]


def _set(values: list, path: str, v) -> list:
    out = list(values)
    out[[f["path"] for f in _fields()].index(path)] = v
    return out


def _b64(text: str, mime: str = "text/plain") -> str:
    return f"data:{mime};base64," + base64.b64encode(text.encode()).decode()


def _save(client, app, values, csvs, folder, overwrite=False):
    return call(client, app, "bf-save-msg.children", {
        ("bf-save-btn", "n_clicks"): 1,
        (ALL_BF, "value"): values,
        ("bf-csvs", "data"): csvs,
        ("bf-folder", "value"): folder,
        ("bf-overwrite", "value"): ["on"] if overwrite else [],
    }, ["bf-save-btn.n_clicks"])  # fmt: skip


def test_create_new_aircraft_by_upload_save_and_fly(ui):
    """Drop an aircraft.yaml and its CSVs, check it, save it, and run it."""
    app, client, root = ui
    src = REPO_AIRCRAFT / "b747_100"
    files = [("aircraft.yaml", (src / "aircraft.yaml").read_text())]
    files += [(p.name, p.read_text()) for p in sorted(src.glob("*.csv"))]
    resp = call(client, app, "bf-csvs.data", {
        ("bf-upload", "contents"): [_b64(t) for _, t in files],
        ("bf-upload", "filename"): [n for n, _ in files],
        ("bf-csvs", "data"): {},
        (ALL_BF, "value"): [f["default"] for f in _fields()],
    }, ["bf-upload.contents"])  # fmt: skip
    csvs = resp["bf-csvs"]["data"]
    assert set(csvs) == {p.name for p in src.glob("*.csv")}
    chips = json.dumps(resp["bf-files"]["children"])
    assert "✗" not in chips and "thrust table" in chips
    values = _set(_form_values(resp), "name", "My test jet")

    check = call(client, app, "bf-yaml.children", {
        (ALL_BF, "value"): values, (ALL_BF, "id"): None, ("bf-csvs", "data"): csvs,
    }, ["bf-csvs.data"])  # fmt: skip
    assert "Valid: ready to export" in json.dumps(check["bf-valid"]["children"])
    assert "name: My test jet" in check["bf-yaml"]["children"]

    saved = _save(client, app, values, csvs, "my_test_jet")
    assert "Saved to aircraft/my_test_jet" in saved["bf-save-msg"]["children"]
    assert saved["aircraft-saved"]["data"] == "my_test_jet"
    assert (root / "my_test_jet" / "thrust.csv").is_file()

    # the simulator's aircraft list picks it up, and it flies like the original
    opts = call(client, app, "aircraft.options", {("aircraft-saved", "data"): "my_test_jet"},
                ["aircraft-saved.data"])["aircraft"]["options"]  # fmt: skip
    assert "my_test_jet" in json.dumps(opts)
    new = compute_bfl(load_config("my_test_jet"))
    ref = compute_bfl(load_config("b747_100"))
    assert new.field_length_ft == pytest.approx(ref.field_length_ft)
    assert load_config("my_test_jet").aircraft.name == "My test jet"


def test_edit_existing_aircraft_and_overwrite_rules(ui):
    """Start from the SR-71, change weight and rules, save as a copy, then overwrite."""
    app, client, root = ui
    resp = call(client, app, "bf-csvs.data", {
        ("bf-start", "value"): "sr71",
        ("bf-csvs", "data"): {},
        (ALL_BF, "value"): [f["default"] for f in _fields()],
    }, ["bf-start.value"])  # fmt: skip
    csvs = resp["bf-csvs"]["data"]
    values = _form_values(resp)
    values = _set(values, "weight.default_weight_lbf", 110000.0)
    values = _set(values, "certification.rules", "part25")

    assert "Saved" in _save(client, app, values, csvs, "sr71_light")["bf-save-msg"]["children"]
    cfg = load_config("sr71_light")
    assert cfg.aircraft.weight.default_weight_lbf == 110000.0
    assert cfg.aircraft.certification.rules == "part25"
    assert cfg.aircraft.engines.thrust_table == "J58 max A/B"  # untouched fields kept
    # the original is unchanged
    assert load_config("sr71").aircraft.weight.default_weight_lbf == 140000.0

    # saving over an existing folder needs 'overwrite'
    values2 = _set(values, "weight.default_weight_lbf", 120000.0)
    msg = _save(client, app, values2, csvs, "sr71_light")["bf-save-msg"]["children"]
    assert "tick 'overwrite'" in msg
    assert load_config("sr71_light").aircraft.weight.default_weight_lbf == 110000.0
    _save(client, app, values2, csvs, "sr71_light", overwrite=True)
    assert load_config("sr71_light").aircraft.weight.default_weight_lbf == 120000.0


def test_invalid_aircraft_is_not_saved(ui):
    app, client, root = ui
    resp = call(client, app, "bf-csvs.data", {
        ("bf-start", "value"): "b747_100",
        ("bf-csvs", "data"): {},
        (ALL_BF, "value"): [f["default"] for f in _fields()],
    }, ["bf-start.value"])  # fmt: skip
    values, csvs = _form_values(resp), resp["bf-csvs"]["data"]
    missing = {k: v for k, v in csvs.items() if k != "thrust.csv"}
    msg = _save(client, app, values, missing, "broken")["bf-save-msg"]["children"]
    assert msg == "Fix the problems first." and not (root / "broken").exists()
    bad = _set(values, "geometry.wing_area_ft2", -5.0)
    assert _save(client, app, bad, csvs, "broken")["bf-save-msg"]["children"] == (
        "Fix the problems first."
    )
    no_name = _save(client, app, values, csvs, "  ")["bf-save-msg"]["children"]
    assert "Give a folder name" in no_name


def test_zip_export_roundtrips(ui):
    app, client, _ = ui
    resp = call(client, app, "bf-csvs.data", {
        ("bf-start", "value"): "sr71",
        ("bf-csvs", "data"): {},
        (ALL_BF, "value"): [f["default"] for f in _fields()],
    }, ["bf-start.value"])  # fmt: skip
    values, csvs = _form_values(resp), resp["bf-csvs"]["data"]
    out = call(client, app, "bf-zip.data", {
        ("bf-zip-btn", "n_clicks"): 1, (ALL_BF, "value"): values, (ALL_BF, "id"): None,
        ("bf-csvs", "data"): csvs, ("bf-folder", "value"): "blackbird",
    }, ["bf-zip-btn.n_clicks"])["bf-zip"]["data"]  # fmt: skip
    assert out["filename"] == "blackbird.zip"
    z = zipfile.ZipFile(io.BytesIO(base64.b64decode(out["content"])))
    names = set(z.namelist())
    assert {"blackbird/aircraft.yaml", "blackbird/thrust.csv"} <= names
    data = yaml.safe_load(z.read("blackbird/aircraft.yaml"))
    assert data["name"] == "Lockheed SR-71A"
    assert data["engines"]["thrust_tables"] == {"J58 max A/B": "thrust.csv"}


def test_builder_table_plots(ui):
    """Aero and thrust tabs: one colour per table, the same in every panel."""
    from app import builder

    d = REPO_AIRCRAFT / "sr71"
    csvs = {p.name: p.read_text() for p in sorted(d.glob("*.csv"))}
    aero = builder.table_figure(csvs, "aero")
    by_table: dict[str, set] = {}
    for tr in aero.data:
        by_table.setdefault(tr.legendgroup, set()).add(tr.line.color)
    assert set(by_table) == {"aero_free_air.csv", "aero_ground_effect.csv"}
    assert all(len(c) == 1 for c in by_table.values())  # same colour in all 3 panels
    assert len(aero.data) == 6
    layout = aero.to_dict()["layout"]
    assert not any("overlaying" in v for k, v in layout.items() if k.startswith("yaxis"))
    thrust = builder.table_figure(csvs, "thrust")
    assert len(thrust.data) == 5  # one line per temperature of the 2-D table
    assert len({tr.line.color for tr in thrust.data}) == 5  # dark (cold) -> light (hot)
    assert len(thrust.layout.annotations) == 5  # each temperature labelled
    assert "appear here" in json.dumps(builder.table_figure({}, "thrust").to_dict())
    # the callback serves the tab that is selected
    app, client, _ = ui
    fig = call(client, app, "bf-plot.figure", {("bf-plot-tab", "value"): "thrust",
               ("bf-csvs", "data"): csvs}, ["bf-plot-tab.value"])["bf-plot"]["figure"]  # fmt: skip
    assert "thrust per engine" in json.dumps(fig["layout"])


def test_summary_downloads(ui):
    """Run summary tab: the full time-step CSV and the summary text."""
    from app import compute

    app, client, _ = ui
    cfg = load_config("b747_100")
    cur = compute._run_cached(cfg.model_dump_json())
    vals = {("dl-csv-btn", "n_clicks"): 1, ("current", "data"): cur}
    csv = call(client, app, "dl-csv.data", vals, ["dl-csv-btn.n_clicks"])["dl-csv"]["data"]
    assert csv["filename"].endswith("_timesteps.csv")
    lines = csv["content"].splitlines()
    assert lines[0].startswith("branch,t_s,x_ft")
    branches = {ln.split(",", 1)[0] for ln in lines[1:]}
    assert branches == {"go (engine out)", "stop", "all engines"}
    res, _ = compute._solve(cfg.model_dump_json())
    assert len(lines) - 1 == sum(len(getattr(res, b).to_dataframe()) for b in ("go", "stop", "aeo"))
    vals = {("dl-summary-btn", "n_clicks"): 1, ("current", "data"): cur}
    txt = call(client, app, "dl-summary.data", vals, ["dl-summary-btn.n_clicks"])
    txt = txt["dl-summary"]["data"]
    assert txt["filename"].endswith("_summary.txt") and txt["content"] == cur["summary"]
