"""Landing distance: geometry, rules (Part 25 vs MIL-STD-3013), trends, convergence."""

from __future__ import annotations

import math
import shutil
import zipfile

import pytest

from bfl import compute_landing, load_config, trade_study
from bfl.config import default_aircraft_root
from bfl.units import DEG_TO_RAD


def _ev(r, name):
    return next(e for e in r.trajectory.events if e.name == name)


def test_glide_geometry_matches_closed_form():
    """Steady glide from 50 ft to the flare height covers (50 - h_f) / tan(gamma)."""
    r = compute_landing(load_config("b747_100"))
    lc = load_config("b747_100").aircraft.landing
    x_flare = _ev(r, "flare").x_ft
    expected = (50.0 - r.flare_height_ft) / math.tan(lc.approach_angle_deg * DEG_TO_RAD)
    assert x_flare == pytest.approx(expected, rel=1e-6)
    # the flare height is the constant-g pull-up from the glide slope to the sink rate
    assert 5.0 < r.flare_height_ft < 50.0
    # speeds: V_A = 1.23 V_S (Part 25), touchdown a little slower after the idle flare
    assert r.v_approach_kts == pytest.approx(1.23 * r.v_s_kts, rel=1e-9)
    assert r.v_s_kts < r.v_touchdown_kts < r.v_approach_kts


def test_part25_factor_and_no_reverse_credit():
    cfg = load_config("b747_100")
    r = compute_landing(cfg)
    assert r.field_factor == pytest.approx(1 / 0.6)
    assert r.runway_required_ft == pytest.approx(r.landing_distance_ft / 0.6)
    assert r.landing_distance_ft == pytest.approx(r.air_distance_ft + r.ground_roll_ft)
    rev = compute_landing(cfg.with_updates({"aircraft.landing.reverse_thrust_fraction": 0.4}))
    assert rev.landing_distance_ft == pytest.approx(r.landing_distance_ft)
    assert any("not credited" in w for w in rev.warnings)


def test_mil_credits_reversers_and_chute():
    cfg = load_config("sr71", overrides={"aircraft.landing.weight_lbf": 80_000.0})
    base = compute_landing(cfg)
    assert base.field_factor == 1.0 and base.chute_used
    no_chute = compute_landing(cfg.with_updates({"aircraft.landing.use_chute": False}))
    assert no_chute.ground_roll_ft > base.ground_roll_ft * 1.1
    rev = compute_landing(cfg.with_updates({"aircraft.landing.reverse_thrust_fraction": 0.4}))
    assert rev.ground_roll_ft < base.ground_roll_ft
    assert rev.air_distance_ft == pytest.approx(base.air_distance_ft)
    # the same aircraft under Part 25: no chute credit, the 1/0.6 factor
    p25 = compute_landing(cfg.with_updates({"aircraft.certification.rules": "part25"}))
    assert not p25.chute_used and p25.field_factor == pytest.approx(1 / 0.6)


@pytest.mark.parametrize(
    "change, longer",
    [
        ({"aircraft.landing.weight_lbf": 640_000.0}, True),
        ({"aircraft.landing.k_CL": 1.3}, False),  # more lift: slower approach
        ({"environment.headwind_kts": 15.0}, False),
        ({"environment.mu_brake": 0.15}, True),  # wet runway: through the friction
        ({"environment.elevation_ft": 5000.0}, True),
        ({"aircraft.landing.free_roll_s": 4.0}, True),
    ],
)
def test_landing_trends(change, longer):
    base = compute_landing(load_config("b747_100")).landing_distance_ft
    new = compute_landing(load_config("b747_100", overrides=change)).landing_distance_ft
    assert (new > base) == longer


def test_rk4_and_rk45_agree():
    cfg = load_config("b747_100")
    a = compute_landing(cfg).landing_distance_ft
    b = compute_landing(
        cfg.with_updates({"solver.method": "rk4", "solver.dt_s": 0.02})
    ).landing_distance_ft
    assert a == pytest.approx(b, rel=2e-4)


def test_landing_in_trade_study():
    cfg = load_config("b747_100")
    df = trade_study(
        cfg,
        {"environment.weight_lbf": [600_000.0, 710_000.0]},
        outputs=("field_length_ft", "landing_runway_required_ft", "runway_required_ft"),
        workers=1,
    )
    assert (df["runway_required_ft"] == df[["field_length_ft",
            "landing_runway_required_ft"]].max(axis=1)).all()  # fmt: skip


def test_load_aircraft_from_zip_yaml_and_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("BFL_CACHE_DIR", str(tmp_path / "cache"))
    src = default_aircraft_root() / "sr71"
    folder = tmp_path / "designs" / "blackbird"
    shutil.copytree(src, folder)
    z = tmp_path / "blackbird.zip"
    with zipfile.ZipFile(z, "w") as f:
        for p in src.iterdir():
            f.write(p, f"blackbird/{p.name}")
    ref = load_config("sr71").aircraft.model_dump(exclude={"directory"})
    for where in (folder, folder / "aircraft.yaml", z, str(z)):
        assert load_config(where).aircraft.model_dump(exclude={"directory"}) == ref
    # the same zip is unpacked once
    assert load_config(z).aircraft.directory == load_config(z).aircraft.directory
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as f:
        f.writestr("../evil/aircraft.yaml", "name: x")
    with pytest.raises(ValueError, match="unsafe"):
        load_config(bad)


def test_landing_weight_never_exceeds_takeoff_weight():
    light = compute_landing(load_config("b747_100", overrides={"weight_lbf": 500_000.0}))
    assert light.weight_lbf == 500_000.0  # the file says 564,000 lb (max landing weight)
    heavy = compute_landing(load_config("b747_100"))
    assert heavy.weight_lbf == 564_000.0


def test_analyze_one_call(tmp_path):
    from bfl import analyze

    a = analyze("b747_100", weight_lbf=650_000, temperature_F=95, elevation_ft=5000)
    assert a.config.weight_lbf == 650_000
    assert a.runway_required_ft == max(a.takeoff.field_length_ft, a.landing.runway_required_ft)
    assert a.governed_by in ("takeoff", "landing")
    s = a.scalars()
    assert s["runway_required_ft"] == a.runway_required_ft and "landing_v_approach_kts" in s
    assert "Runway required" in a.summary().splitlines()[0]
    d = a.save(tmp_path / "case")
    names = {p.name for p in d.iterdir()}
    assert {
        "summary.txt",
        "results.csv",
        "time_history_go.csv",
        "time_history_landing.csv",
    } <= names
    # dotted paths and a loaded config work too
    b = analyze(a.config, **{"aircraft.landing.free_roll_s": 4.0})
    assert b.landing.ground_roll_ft > a.landing.ground_roll_ft


def test_short_input_names_and_errors():
    from bfl.config import InputError

    cfg = load_config("b747_100", overrides={"k_CL": 1.1, "mu_brake": 0.2, "rules": "mil3013"})
    assert cfg.multipliers.k_CL == 1.1 and cfg.environment.mu_brake == 0.2
    assert cfg.resolved().procedure.is_mil
    with pytest.raises(KeyError, match="did you mean 'weight_lbf'"):
        load_config("b747_100", overrides={"wieght_lbf": 1.0})
    with pytest.raises(InputError, match="environment.weight_lbf: input should be greater than 0"):
        load_config("b747_100", overrides={"weight_lbf": -5.0})
    df = trade_study(load_config("b747_100"), {"k_CL": [1.0, 1.1]}, workers=1)
    assert list(df.columns[:1]) == ["k_CL"] and "runway_required_ft" in df.columns
