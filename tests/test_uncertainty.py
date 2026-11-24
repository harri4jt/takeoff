"""Data uncertainty: sampling, statistics with failed draws, sensitivity, and the page."""

from __future__ import annotations

import json
import math
from statistics import NormalDist

import numpy as np
import pytest

from bfl import load_config
from bfl.uncertainty import (
    UncertaintySettings,
    quantile_ci_inf,
    sample_factors,
    uncertainty_study,
)

ND = NormalDist()


def test_latin_hypercube_one_draw_per_stratum():
    s = UncertaintySettings(sigma_CL=0.05, sigma_CD=0.1, sigma_T=0.03, n=200, method="lhs")
    f = sample_factors(s)
    lo, hi = ND.cdf(-3.0), ND.cdf(3.0)
    for k, sig in s.sigmas().items():
        u01 = (np.array([ND.cdf(v) for v in (f[k] - 1.0) / sig]) - lo) / (hi - lo)
        strata = np.floor(u01 * s.n).astype(int)
        assert sorted(strata) == list(range(s.n))  # every stratum exactly once
        assert np.all(np.abs(f[k] - 1.0) <= 3.0 * sig + 1e-12)  # cut at 3 sigma


def test_monte_carlo_draws_have_the_right_spread():
    s = UncertaintySettings(sigma_CL=0.05, sigma_CD=0.0, sigma_T=0.02, n=4000, method="mc")
    f = sample_factors(s)
    assert f["k_CL"].mean() == pytest.approx(1.0, abs=0.004)
    assert f["k_CL"].std() == pytest.approx(0.05 * 0.986, rel=0.05)  # truncation trims ~1.4 %
    assert (f["k_CD"] == 1.0).all()
    with pytest.raises(ValueError):
        sample_factors(UncertaintySettings(method="sobol"))


def test_quantile_ci_inf_keeps_failed_draws():
    x = np.array([1.0, 2.0, 3.0, 4.0, math.inf, math.inf])
    assert quantile_ci_inf(x, 0.5)[0] == 3.0
    assert quantile_ci_inf(x, 0.9)[0] == math.inf  # a third of the draws never solve
    y = np.arange(1, 1001, dtype=float)
    est, lo, hi = quantile_ci_inf(y, 0.95)
    assert est == 950.0 and lo < est < hi and hi - lo == pytest.approx(27, abs=3)


def test_zero_uncertainty_is_the_nominal_answer():
    cfg = load_config("b747_100")
    u = uncertainty_study(cfg, UncertaintySettings(0.0, 0.0, 0.0, n=6))
    assert (u.samples["error"] == "").all()
    assert np.allclose(u.samples["takeoff_field_ft"], u.nominal["takeoff_field_ft"])
    assert u.nominal["takeoff_field_ft"] == pytest.approx(9523, rel=1e-3)


def test_sensitivity_finds_the_uncertain_table():
    cfg = load_config("b747_100")
    u = uncertainty_study(cfg, UncertaintySettings(0.05, 0.0, 0.0, n=40, landing=False))
    sens = u.sensitivity("takeoff_field_ft")
    assert list(sens["factor"]) == ["k_CL"]
    assert sens["variance_share"].iloc[0] == pytest.approx(sens["r2"].iloc[0], rel=1e-6)
    assert sens["per_sigma_ft"].iloc[0] < 0  # more lift, shorter field
    both = uncertainty_study(cfg, UncertaintySettings(0.04, 0.08, 0.03, n=60, landing=False))
    s2 = both.sensitivity("takeoff_field_ft")
    assert s2["variance_share"].sum() == pytest.approx(s2["r2"].iloc[0], rel=1e-6)
    assert "Data uncertainty" in both.summary()


def test_response_surface_predicts_unseen_cases():
    """The profiler's quadratic surface reproduces fresh full solves within tens of feet,
    and the failure model marks where the SR-71 cannot take off."""
    from bfl import compute_bfl
    from bfl.uncertainty import predict_failure, predict_surface

    cfg = load_config("b747_100")
    u = uncertainty_study(cfg, UncertaintySettings(n=120, landing=False))
    rs = u.response_surface("takeoff_field_ft")
    assert rs["r2"] > 0.99 and rs["loo_rms_ft"] < 40
    k = (0.95, 1.05, 0.97)
    true = compute_bfl(cfg.with_updates({"k_CL": k[0], "k_CD": k[1], "k_T": k[2]})).field_length_ft
    assert float(predict_surface(rs, *k)) == pytest.approx(true, abs=60)
    sr = uncertainty_study(load_config("sr71"), UncertaintySettings(n=120, landing=False))
    fm = sr.failure_model()
    assert fm and predict_failure(fm, 0.92, 1.0, 1.0) > 0.5 > predict_failure(fm, 1.05, 1.0, 1.0)


def test_draws_without_a_solution_count_as_infinite_runway():
    """The 140,000 lb SR-71 is so marginal on one engine that a few % less lift or thrust
    means no lift-off at all; those draws must not be dropped."""
    u = uncertainty_study(load_config("sr71"), UncertaintySettings(0.04, 0.08, 0.03, n=60))
    f = u.failure_rate("takeoff_field_ft")
    assert 0.0 < f < 1.0
    x = u.values("takeoff_field_ft")
    assert np.isinf(x).sum() == round(f * len(x))
    assert np.isfinite(u.values("landing_runway_ft")).all()  # landing is solved on its own
    drivers = u.failure_drivers()
    assert drivers["k_CD"] > 0  # failures come with more drag than nominal
    tab = u.percentiles().set_index("output")
    if f > 0.05:
        assert math.isinf(tab.loc["takeoff_field_ft", "p95"])


pytest.importorskip("dash")


def test_uncertainty_page_end_to_end():
    from app import main

    from .test_app_builder import call

    app = main.create_app()
    client = app.server.test_client()
    vals = {
        ("un-run", "n_clicks"): 1, ("un-aircraft", "value"): "b747_100",
        ("un-cl", "value"): 4, ("un-cd", "value"): 8, ("un-t", "value"): 3,
        ("un-landing", "value"): ["on"], ("un-n", "value"): 30, ("un-weight", "value"): None,
        ("un-temp", "value"): None, ("un-elev", "value"): None, ("un-wind", "value"): None,
        ("un-cond", "value"): "", ("un-method", "value"): "lhs", ("un-seed", "value"): 2,
        ("un-trunc", "value"): 3, ("current", "data"): None,
    }  # fmt: skip
    out = call(client, app, "un-result.data", vals, ["un-run.n_clicks"])
    d = out["un-result"]["data"]
    assert out["un-status"]["children"] == "" and len(d["errors"]) == 30
    assert len(d["oat"]) == 12  # three tables, ±5 % and ±10 %
    page = json.dumps(call(client, app, "un-results.children", {("un-result", "data"): d},
                           ["un-result.data"]), ensure_ascii=False)  # fmt: skip
    assert "Multiplier profiler" in page and "Method checks" in page and "un-rw-3" in page
    rw = {("un-rw-1", "value"): 10_000, ("un-rw-2", "value"): None,
          ("un-rw-3", "value"): 12_000, ("un-result", "data"): d}  # fmt: skip
    o = call(client, app, "un-fig-odds.figure", rw, ["un-rw-1.value"])
    assert o["un-rw-2-p"]["children"] == [] and "%" in json.dumps(o["un-rw-1-p"]["children"])
    title = json.dumps(o["un-fig-odds"]["figure"]["layout"]["title"])
    assert "10,000 ft" in title and "12,000 ft" in title
    assert "cliff" in json.dumps(o["un-fig-map"]["figure"]["layout"]["title"])
    st = call(client, app, "un-fig-margin.figure", {("un-results", "children"): [],
              ("un-result", "data"): d}, ["un-results.children"])  # fmt: skip
    assert "95 % confidence" in json.dumps(st["un-fig-margin"]["figure"]["layout"]["title"])
    assert "Sampling error" in json.dumps(st["un-fig-conv"]["figure"]["layout"]["title"])
    prof = call(client, app, "un-fig-prof.figure", {("un-sl-cl", "value"): 1.0,
                ("un-sl-cd", "value"): 0.9, ("un-sl-t", "value"): 1.0, ("un-rw-1", "value"): 9000,
                ("un-rw-2", "value"): None, ("un-rw-3", "value"): None,
                ("un-result", "data"): d}, ["un-sl-cd.value"])["un-fig-prof"]["figure"]  # fmt: skip
    assert "drag ×0.900" in json.dumps(prof["layout"]["title"], ensure_ascii=False)
    sig = call(client, app, "un-fig-sigmas.figure", {("un-cl", "value"): 2, ("un-cd", "value"): 8,
               ("un-t", "value"): 0}, ["un-cl.value"])  # fmt: skip
    assert len(sig["un-fig-sigmas"]["figure"]["data"]) == 3


def test_one_at_a_time_is_exact_and_equal_percent():
    from bfl import load_config
    from bfl.uncertainty import UncertaintySettings, uncertainty_study

    u = uncertainty_study(load_config("b747_100"), UncertaintySettings(n=8, landing=False))
    oat = u.one_at_a_time("takeoff_field_ft")
    assert sorted(set(np.round(np.abs(oat["change"]), 6))) == [0.05, 0.10]
    row = oat[(oat["factor"] == "k_CL") & np.isclose(oat["change"], -0.05)]
    from bfl import compute_bfl

    cfg = load_config("b747_100", overrides={"k_CL": 0.95})
    assert abs(float(row["value"].iloc[0]) - compute_bfl(cfg).field_length_ft) < 1.0
    assert (oat[oat["change"] < 0].set_index("factor").loc["k_CL", "delta"] > 0).all()
