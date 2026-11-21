"""Gust analysis: model pieces, calm limit, reproducibility, statistics, convergence."""

from __future__ import annotations

import math

import numpy as np
import pytest

from bfl import compute_bfl, compute_landing, load_config
from bfl.gusts import (
    GustSettings,
    _realizations,
    convergence_study,
    dryden,
    gust_study,
    quantile_ci,
    span_average,
)
from bfl.units import KTS_TO_FTPS


def test_dryden_low_altitude_values():
    """MIL-F-8785C low altitude: sigma_w = 0.1 W20, L_w = h; at 20 ft, sigma_u ~ 1.93
    sigma_w and L_u ~ 144 ft."""
    su, sw, lu, lw = dryden(20.0, 30.0)
    assert sw == pytest.approx(3.0 * KTS_TO_FTPS)
    assert su / sw == pytest.approx(1.928, rel=1e-3) and lu == pytest.approx(143.6, rel=1e-2)
    assert lw == 20.0
    assert dryden(0.0, 30.0) == dryden(10.0, 30.0)  # clamped to 10 ft


def test_span_average():
    s, length = span_average(2.0, 10.0, None)
    assert (s, length) == (2.0, 10.0)
    s, length = span_average(2.0, 10.0, 1e-9)  # a point wing feels the whole gust
    assert s == pytest.approx(2.0) and length == pytest.approx(10.0)
    s, length = span_average(2.0, 10.0, 200.0)  # a long wing averages most of it out
    f = (s / 2.0) ** 2
    assert f == pytest.approx(2 * (20 - 1 + math.exp(-20)) / 400)
    assert s**2 * length == pytest.approx(4.0 * 10.0)  # zero-frequency content kept


def _calm(ac):
    cfg = load_config(ac).resolved()
    return cfg, _realizations((cfg.model_dump_json(), GustSettings().__dict__, [0], True))[0]


@pytest.mark.parametrize("ac", ["b747_100", "sr71"])
def test_calm_limit_matches_the_main_solver(ac):
    """No gusts: the fixed-step SDE simulator reproduces the RK45 solver."""
    cfg, calm = _calm(ac)
    r = compute_bfl(cfg)
    lr = compute_landing(cfg)
    assert calm["go_ft"] == pytest.approx(r.d_go_ft, rel=2e-3)
    assert calm["stop_ft"] == pytest.approx(r.d_stop_ft, rel=2e-3)
    assert calm["aeo_ft"] == pytest.approx(r.aeo_distance_ft, rel=2e-3)
    assert calm["takeoff_field_ft"] == pytest.approx(r.field_length_ft, rel=2e-3)
    assert calm["landing_distance_ft"] == pytest.approx(lr.landing_distance_ft, rel=1e-2)


def test_reproducible_and_stronger_gusts_spread_more():
    cfg = load_config("b747_100")
    a = gust_study(cfg, GustSettings(intensity="light", n=24, seed=5))
    b = gust_study(cfg, GustSettings(intensity="light", n=24, seed=5))
    c = gust_study(cfg, GustSettings(intensity="light", n=24, seed=6))
    col = "takeoff_field_ft"
    assert np.array_equal(a.samples[col], b.samples[col])
    assert not np.array_equal(a.samples[col], c.samples[col])
    s = gust_study(cfg, GustSettings(intensity="severe", n=24, seed=5))
    assert s.samples[col].std() > a.samples[col].std()
    assert (a.samples["error"] == "").all()
    tab = a.percentiles().set_index("output")
    assert tab.loc[col, "p95_lo"] <= tab.loc[col, "p95"] <= tab.loc[col, "p95_hi"]
    assert "Gust study" in a.summary() and 0 in a.traces and "go" in a.traces[0]


def test_quantile_confidence_interval():
    rng = np.random.default_rng(0)
    covered, widths = 0, {}
    for n in (400, 1600):
        w = []
        for _ in range(60):
            x = rng.standard_normal(n)
            est, lo, hi = quantile_ci(x, 0.95)
            covered += lo <= 1.6449 <= hi
            w.append(hi - lo)
        widths[n] = np.mean(w)
    assert covered / 120 > 0.85  # ~95 % coverage
    assert widths[1600] / widths[400] == pytest.approx(0.5, rel=0.2)  # 1/sqrt(n)


def test_gust_convergence_errors_fall_with_the_step():
    df = convergence_study(
        load_config("b747_100"), GustSettings(intensity="moderate"),
        dts=(0.04, 0.01), ref_dt=0.0025, n_paths=4, outputs=("go_ft", "aeo_ft"),
    )  # fmt: skip
    for (_, _), g in df.groupby(["method", "output"]):
        e = g.sort_values("dt").error_ft.to_numpy()
        assert e[0] < e[1]  # dt 0.01 more accurate than 0.04
