"""Validation of the real-aircraft examples against published data.

Run by ``tests/test_validation.py`` (and ``scripts/validate_b747.py``). Each run writes
figures and a ``status.json`` into ``app/assets/validation/<aircraft>/``; the app's
data pages show them with a pass/fail badge. ``status.json`` stores a hash of the
aircraft's data files, so the app can tell when the data changed after the last run.

Nothing here is tuned to make the comparison look better: the tolerances are fixed
and the model is run with its normal defaults.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .bfl import compute_bfl
from .config import load_config, resolve_aircraft_dir

ROOT = Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "app" / "assets" / "validation"

# Boeing D6-58326 "747 Airplane Characteristics for Airport Planning", sec. 3.3.1:
# F.A.R. takeoff runway length, standard day, 747-100 (JT9D-3A), sea-level curve.
# (brake-release weight [1000 lb], runway length [ft]), digitized.
BOEING_747_SL = [
    (500, 4880), (520, 4910), (540, 5180), (560, 5520), (580, 5880), (620, 6750),
    (640, 7220), (660, 7750), (680, 8360), (690, 8720), (705, 9230),
]  # fmt: skip
B747_TOL_PCT = (-12.0, 12.0)  # +/-12 % of Boeing's FAR field length

# Berry, Mallick & Gilyard, "Handling Qualities Aspects of NASA YF-12 Flight Experience",
# NASA Dryden 1977 (NTRS 19770011063): nosewheel
# lift-off ~180 KIAS, held at 10 deg, airborne ~200 KIAS (all engines, heavy weight).
YF12_VR_KIAS, YF12_VLOF_KIAS, YF12_TOL_KT = 180.0, 200.0, 10.0
SR71_WEIGHT_LBF = 140000.0


@dataclass
class Check:
    name: str
    model: float
    reference: float
    unit: str
    low: float
    high: float
    passed: bool
    detail: str = ""


@dataclass
class Status:
    aircraft: str
    passed: bool
    checks: list[Check]
    tolerance: str
    data_hash: str
    timestamp: str
    git_hash: str
    figures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def data_hash(aircraft: str) -> str:
    """SHA-1 over the aircraft folder's yaml + csv files (names and contents)."""
    d = resolve_aircraft_dir(aircraft)
    h = hashlib.sha1()
    for p in sorted(list(d.glob("*.yaml")) + list(d.glob("*.csv"))):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _git_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        )
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def read_status(aircraft: str) -> dict[str, Any] | None:
    p = OUT_ROOT / aircraft / "status.json"
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _write(aircraft: str, status: Status) -> Path:
    out = OUT_ROOT / aircraft
    out.mkdir(parents=True, exist_ok=True)
    p = out / "status.json"
    p.write_text(json.dumps(asdict(status), indent=2, default=_jsonable))
    return p


def _jsonable(v: Any) -> Any:
    if isinstance(v, np.generic):
        return v.item()
    raise TypeError(f"not JSON serializable: {type(v).__name__}")


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------------------------
# figures (matplotlib, saved as PNG next to status.json)
# ------------------------------------------------------------------------------------
def _plt():
    from .plotting import plt, style

    style()
    return plt


def _aero_figure(aircraft: str, title: str, out: Path) -> str:
    """CL and CD vs alpha of every configuration listed in the aircraft."""
    from .tables import read_csv_table

    plt = _plt()
    cfg = load_config(aircraft)
    d = Path(cfg.aircraft.directory)
    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.6))
    for i, (name, csv) in enumerate(cfg.aircraft.aero.configurations.items()):
        df = read_csv_table(d / csv, ["alpha_deg", "CL", "CD"])
        c = f"C{i}"
        a.plot(df["alpha_deg"], df["CL"], color=c, label=name)
        b.plot(df["alpha_deg"], df["CD"], color=c, label=name)
    a.set(xlabel="alpha [deg]", ylabel="CL", title="Lift (digitized)")
    b.set(xlabel="alpha [deg]", ylabel="CD", title="Drag")
    a.legend()
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    name = "aero.png"
    fig.savefig(out / name)
    plt.close(fig)
    return name


def _thrust_figure(aircraft: str, title: str, out: Path) -> str:
    from .tables import read_csv_table

    plt = _plt()
    cfg = load_config(aircraft)
    d = Path(cfg.aircraft.directory)
    df = read_csv_table(d / str(cfg.aircraft.engines.thrust_table), ["airspeed_kts", "thrust_lbf"])
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    if "temperature_F" in df.columns:
        for i, (t, g) in enumerate(df.groupby("temperature_F")):
            ax.plot(g["airspeed_kts"], g["thrust_lbf"] / 1000, color=f"C{i}", label=f"{t:.0f} °F")
        ax.legend(fontsize=8)
    else:
        ax.plot(df["airspeed_kts"], df["thrust_lbf"] / 1000, color="C0")
    ax.set(xlabel="true airspeed [kt]", ylabel="thrust per engine [1000 lbf]", title=title)
    fig.tight_layout()
    name = "thrust.png"
    fig.savefig(out / name)
    plt.close(fig)
    return name


# ------------------------------------------------------------------------------------
# Boeing 747-100
# ------------------------------------------------------------------------------------
def validate_b747(write: bool = True) -> Status:
    rows = []
    for w, ref in BOEING_747_SL:
        cfg = load_config("b747_100", overrides={"environment.weight_lbf": w * 1000.0})
        r = compute_bfl(cfg)
        g = compute_bfl(cfg.with_updates({"aircraft.ground_effect.enabled": True}))
        rows.append((w, ref, r.field_length_ft, r.bfl_ft, g.field_length_ft))
    lo, hi = B747_TOL_PCT
    checks = []
    for w, ref, far, _bfl, _ge in rows:
        err = 100.0 * (far / ref - 1.0)
        checks.append(
            Check(f"{w:.0f} klb", far, ref, "ft", lo, hi, lo <= err <= hi, f"{err:+.1f} %")
        )
    errs = [100.0 * (r[2] / r[1] - 1.0) for r in rows]
    ge_errs = [100.0 * (r[4] / r[1] - 1.0) for r in rows]
    status = Status(
        aircraft="b747_100",
        passed=all(c.passed for c in checks),
        checks=checks,
        tolerance=f"model FAA field length within {lo:+g} / {hi:+g} % of Boeing",
        data_hash=data_hash("b747_100"),
        timestamp=_now(),
        git_hash=_git_hash(),
        extra={
            "error_pct_range": [min(errs), max(errs)],
            "ground_effect_error_pct_range": [min(ge_errs), max(ge_errs)],
            "rows": [
                {"weight_klb": w, "boeing_ft": ref, "model_field_ft": far, "model_bfl_ft": bfl,
                 "model_field_ground_effect_ft": ge}
                for w, ref, far, bfl, ge in rows
            ],
        },
    )  # fmt: skip
    if write:
        out = OUT_ROOT / "b747_100"
        out.mkdir(parents=True, exist_ok=True)
        plt = _plt()
        fig, ax = plt.subplots(figsize=(7, 4.2))
        w = [r[0] for r in rows]
        band_lo = [r[1] * (1 + lo / 100) for r in rows]
        band_hi = [r[1] * (1 + hi / 100) for r in rows]
        ax.fill_between(w, band_lo, band_hi, color="#2a78d6", alpha=0.10, label="tolerance band")
        ax.plot(w, [r[1] for r in rows], "o-", color="k", label="Boeing D6-58326 (SL, std day)")
        ax.plot(w, [r[2] for r in rows], "s-", color="#2a78d6", label="model: FAA field length")
        ax.plot(w, [r[3] for r in rows], "^--", color="#eb6834", label="model: BFL")
        ax.plot(
            w, [r[4] for r in rows], ":", color="#1baf7a", label="what-if: field length + Raymer ground effect"
        )
        ax.set(
            xlabel="brake-release weight [1000 lb]",
            ylabel="runway length [ft]",
            title="747-100, flaps 20, sea level ISA",
        )
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out / "validation.png")
        plt.close(fig)
        status.figures = [
            "validation.png",
            _aero_figure("b747_100", "747-100 aero tables (CR-114494)", out),
            _thrust_figure("b747_100", "JT9D-3 at takeoff EPR, SL ISA", out),
        ]
        _write("b747_100", status)
    return status


# ------------------------------------------------------------------------------------
# Lockheed SR-71A
# ------------------------------------------------------------------------------------
def _aeo_liftoff_kts(r) -> float:
    """All-engines lift-off airspeed (KEAS) from the AEO time history."""
    ev = next(e for e in r.aeo.events if e.name == "liftoff")
    df = r.aeo.to_dataframe()
    va = float(np.interp(ev.t_s, df["t_s"], df["V_air_kts"]))
    return va * np.sqrt(r.density_slugft3 / 0.0023769)


def validate_sr71(write: bool = True) -> Status:
    cfg = load_config("sr71", overrides={"environment.weight_lbf": SR71_WEIGHT_LBF})
    r = compute_bfl(cfg)
    vr, vlof = r.vr_kts, _aeo_liftoff_kts(r)
    t = YF12_TOL_KT
    checks = [
        Check("rotation speed VR", vr, YF12_VR_KIAS, "kt", -t, t, abs(vr - YF12_VR_KIAS) <= t),
        Check(
            "lift-off speed, all engines",
            vlof,
            YF12_VLOF_KIAS,
            "kt",
            -t,
            t,
            abs(vlof - YF12_VLOF_KIAS) <= t,
        ),
    ]
    mil = compute_bfl(cfg.with_updates({"procedure.rules": "mil3013"}))
    status = Status(
        aircraft="sr71",
        passed=all(c.passed for c in checks),
        checks=checks,
        tolerance=f"VR and all-engines lift-off within ±{t:g} kt of YF-12 flight test",
        data_hash=data_hash("sr71"),
        timestamp=_now(),
        git_hash=_git_hash(),
        notes=[
            "No published SR-71 runway-length data was available, so only speeds are checked.",
            "Drag is an estimate; the field never balances (engine-out go governs).",
        ],
        extra={
            "weight_lbf": SR71_WEIGHT_LBF,
            "part25": {"bfl_ft": r.bfl_ft, "balanced": r.balanced, "aeo_ft": r.aeo_distance_ft},
            "mil3013": {"cfl_ft": mil.bfl_ft, "balanced": mil.balanced, "aeo_ft": mil.aeo_distance_ft},
        },
    )  # fmt: skip
    if write:
        out = OUT_ROOT / "sr71"
        out.mkdir(parents=True, exist_ok=True)
        plt = _plt()
        fig, ax = plt.subplots(figsize=(6, 3.6))
        names = ["VR", "lift-off (all engines)"]
        model = [vr, vlof]
        ref = [YF12_VR_KIAS, YF12_VLOF_KIAS]
        x = np.arange(2)
        ax.bar(x - 0.18, ref, 0.36, color="#9a9893", label="YF-12 flight test (~KIAS)")
        ax.bar(x + 0.18, model, 0.36, color="#2a78d6", label="model (KEAS)")
        ax.errorbar(x - 0.18, ref, yerr=t, fmt="none", ecolor="k", capsize=6, lw=1)
        ax.set_xticks(x, names)
        ax.set_ylim(150, 215)
        ax.set(ylabel="speed [kt]", title=f"SR-71A at {SR71_WEIGHT_LBF / 1000:.0f} klb, SL ISA")
        ax.legend(fontsize=8, loc="lower right")
        fig.tight_layout()
        fig.savefig(out / "validation.png")
        plt.close(fig)
        status.figures = [
            "validation.png",
            _aero_figure("sr71", "SR-71A: lift from Fig. 6-2, drag ESTIMATED", out),
            _thrust_figure("sr71", "J58 max afterburner, SL (Fig. 1-3, as TAS)", out),
        ]
        _write("sr71", status)
    return status


VALIDATORS = {"b747_100": validate_b747, "sr71": validate_sr71}

__all__ = ["validate_b747", "validate_sr71", "read_status", "data_hash", "VALIDATORS"]
