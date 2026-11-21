"""The gust analysis page through its real callbacks (no browser)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("dash")

from .test_app_builder import call  # noqa: E402


@pytest.fixture(scope="module")
def page():
    from app import main

    app = main.create_app()
    return app, app.server.test_client()


def test_gust_page_run_figures_and_downloads(page):
    app, client = page
    vals = {
        ("gu-run", "n_clicks"): 1, ("gu-aircraft", "value"): "b747_100",
        ("gu-intensity", "value"): "moderate", ("gu-vertical", "value"): ["on"],
        ("gu-ops", "value"): ["takeoff", "landing"], ("gu-n", "value"): 40,
        ("gu-weight", "value"): None, ("gu-temp", "value"): None, ("gu-elev", "value"): None,
        ("gu-wind", "value"): None, ("gu-cond", "value"): "", ("gu-method", "value"): "heun",
        ("gu-dt", "value"): 0.01, ("gu-seed", "value"): 3, ("gu-lag", "value"): 1.0,
        ("gu-additive", "value"): 0, ("current", "data"): None,
    }  # fmt: skip
    out = call(client, app, "gu-result.data", vals, ["gu-run.n_clicks"])
    d = out["gu-result"]["data"]
    assert out["gu-status"]["children"] == ""
    assert len(d["samples"]["takeoff_field_ft"]) == 40
    assert d["calm"]["takeoff_field_ft"] == pytest.approx(9523, rel=3e-3)

    page_html = json.dumps(call(client, app, "gu-results.children", {("gu-result", "data"): d},
                                ["gu-result.data"]))  # fmt: skip
    assert "To cover 95 % of gusty-day operations" in page_html
    figs = call(client, app, "gu-fig-margin.figure", {("gu-results", "children"): [],
                ("gu-result", "data"): d}, ["gu-results.children"])  # fmt: skip
    assert "covers 95 %" in json.dumps(figs["gu-fig-margin"]["figure"]["layout"]["title"])
    assert figs["gu-fig-spread"]["figure"]["data"] and figs["gu-fig-mc"]["figure"]["data"]

    ans = call(client, app, "gu-answer.children", {("gu-cover", "value"): 0.99,
               ("gu-result", "data"): d}, ["gu-cover.value"])  # fmt: skip
    assert "99 %" in json.dumps(ans)
    tr = call(client, app, "gu-fig-trace.figure", {("gu-trace-run", "value"): "1",
              ("gu-trace-op", "value"): "landing", ("gu-result", "data"): d},
              ["gu-trace-op.value"])  # fmt: skip
    assert "landing" in json.dumps(tr["gu-fig-trace"]["figure"]["layout"]["title"]).lower()
    vals_dl = {("gu-dl-csv-btn", "n_clicks"): 1, ("gu-result", "data"): d}
    csv = call(client, app, "gu-dl-csv.data", vals_dl, ["gu-dl-csv-btn.n_clicks"])
    csv = csv["gu-dl-csv"]["data"]
    assert csv["content"].count("\n") == 42 and "takeoff_field_ft" in csv["content"]

    bad = dict(vals)
    bad[("gu-ops", "value")] = []
    msg = call(client, app, "gu-result.data", bad, ["gu-run.n_clicks"])["gu-status"]["children"]
    assert "Pick takeoff, landing or both" in msg
