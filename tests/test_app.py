"""Smoke tests for the app's new pages and helpers (no browser)."""

from __future__ import annotations

import pytest
import yaml

pytest.importorskip("dash")

from bfl import list_aircraft, load_config  # noqa: E402
from bfl.config import resolve_aircraft_dir  # noqa: E402


def test_app_builds_and_pages_render():
    from app import builder, datapages, main, pages, trade

    main.create_app()
    trade.layout()
    builder.layout()
    for route in datapages.ROUTES:
        datapages.render(route)
    for route, *_ in pages.PAGES:
        pages.render(route)


@pytest.mark.parametrize("name", list_aircraft())
def test_builder_roundtrips_every_aircraft(name):
    """Loading an aircraft into the builder form and collecting it back is lossless."""
    from app import builder

    d = resolve_aircraft_dir(name)
    loaded = yaml.safe_load((d / "aircraft.yaml").read_text())
    flat = builder._flatten(loaded)
    vals = [builder._to_widget(f, flat.get(f["path"], f["default"])) for f in builder.FIELDS]
    ids = [{"type": "bf", "path": f["path"]} for f in builder.FIELDS]
    data = builder._collect(vals, ids)
    csvs = {p.name: p.read_text() for p in d.glob("*.csv")}
    cfg, errs = builder._validate(data, csvs)
    assert not errs
    original = load_config(name).aircraft.model_dump(exclude={"directory"})
    assert cfg.model_dump(exclude={"directory"}) == original


def test_builder_reports_missing_tables():
    from app import builder

    d = resolve_aircraft_dir("b747_100")
    loaded = yaml.safe_load((d / "aircraft.yaml").read_text())
    flat = builder._flatten(loaded)
    vals = [builder._to_widget(f, flat.get(f["path"], f["default"])) for f in builder.FIELDS]
    ids = [{"type": "bf", "path": f["path"]} for f in builder.FIELDS]
    _, errs = builder._validate(builder._collect(vals, ids), {})
    assert any("not uploaded" in e for e in errs)


def test_limit_warnings(tmp_path, monkeypatch):
    from app import limits

    p = tmp_path / "ref.yaml"
    p.write_text(
        "metrics:\n  max_tire_speed_kts: {label: 'Tire speed', unit: kt}\n"
        "aircraft:\n  - {name: Ref, warn: true, max_tire_speed_kts: 150}\n"
        "  - {name: Info, warn: false, max_tire_speed_kts: 100}\n"
    )
    monkeypatch.setattr(limits, "PATH", p)
    w = limits.warnings({"max_tire_speed_kts": 160.0})
    assert w == ["Tire speed 160 kt exceeds Ref (150 kt)"]
    assert limits.warnings({"max_tire_speed_kts": 140.0}) == []
    assert len(limits.strips({"max_tire_speed_kts": 160.0})[0]["refs"]) == 2


def test_trade_map_and_figure():
    from app import compute, figures

    cfg = load_config("generic_widebody_synthetic")
    k = (0.9, 1.0, 1.1)
    m = compute.trade_map(cfg.model_dump_json(), k, k)
    z = m["z"]["bfl_ft"]
    assert len(z) == 3 and all(v is not None for row in z for v in row)
    assert z[2][1] < z[0][1]  # more lift, shorter field
    assert z[1][2] > z[1][0]  # more drag, longer field
    maps = [{**m, "title": "a"}, {**m, "title": "b"}]
    figures.trade(maps, "bfl_ft", "BFL", "bands", [9000, 10000])
    figures.trade(maps, "bfl_ft", "BFL", "viridis", None)
