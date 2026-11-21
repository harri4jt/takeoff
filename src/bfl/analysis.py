"""One call for one case: takeoff and landing, and the runway the design needs.

    from bfl import analyze
    a = analyze("b747_100", weight_lbf=650e3, temperature_F=90, elevation_ft=5000)
    a.runway_required_ft          # max(takeoff field length, landing runway required)
    print(a.summary())
    a.save("output/case_1")       # summary.txt, results.csv, time histories

The aircraft can be a name under aircraft/, a folder, an aircraft.yaml path, a builder
.zip, or a RunConfig already loaded. Inputs are the short names of
``bfl.config.INPUT_ALIASES`` (weight_lbf, temperature_F, k_CL, mu_brake, rules, ...)
or any dotted path ("aircraft.landing.free_roll_s").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .bfl import compute_bfl
from .config import RunConfig, load_config
from .landing import LandingResult, compute_landing
from .results import BFLResult


@dataclass
class Analysis:
    """Takeoff and landing for one case."""

    config: RunConfig
    takeoff: BFLResult
    landing: LandingResult | None
    landing_error: str = ""

    @property
    def takeoff_field_length_ft(self) -> float:
        return self.takeoff.field_length_ft

    @property
    def landing_runway_required_ft(self) -> float | None:
        return None if self.landing is None else self.landing.runway_required_ft

    @property
    def runway_required_ft(self) -> float:
        """max(takeoff field length, landing runway required)."""
        land = self.landing_runway_required_ft
        return (
            self.takeoff_field_length_ft
            if land is None
            else max(self.takeoff_field_length_ft, land)
        )

    @property
    def governed_by(self) -> str:
        land = self.landing_runway_required_ft
        return "landing" if land is not None and land > self.takeoff_field_length_ft else "takeoff"

    def scalars(self) -> dict[str, Any]:
        out = {**self.takeoff.scalars()}
        if self.landing is not None:
            out.update(self.landing.scalars())
        out["runway_required_ft"] = self.runway_required_ft
        out["runway_governed_by"] = self.governed_by
        return out

    def time_histories(self) -> dict[str, pd.DataFrame]:
        """Every time step: engine-out go, rejected stop, all-engines takeoff, landing."""
        out = {
            "go": self.takeoff.go.to_dataframe(),
            "stop": self.takeoff.stop.to_dataframe(),
            "aeo": self.takeoff.aeo.to_dataframe(),
        }
        if self.landing is not None:
            out["landing"] = self.landing.to_dataframe()
        return out

    def summary(self) -> str:
        head = f"Runway required: {self.runway_required_ft:,.0f} ft (set by {self.governed_by})"
        parts = [head, "", self.takeoff.summary()]
        if self.landing is not None:
            parts += ["", self.landing.summary()]
        elif self.landing_error:
            parts += ["", f"Landing not computed: {self.landing_error}"]
        return "\n".join(parts)

    def save(self, folder: str | Path) -> Path:
        """Write summary.txt, results.csv (one row of every output) and one CSV per time
        history into ``folder`` (created if needed). Returns the folder."""
        d = Path(folder)
        d.mkdir(parents=True, exist_ok=True)
        (d / "summary.txt").write_text(self.summary() + "\n")
        flat = {k: v for k, v in self.scalars().items() if not isinstance(v, (dict, list))}
        pd.DataFrame([flat]).to_csv(d / "results.csv", index=False)
        for name, df in self.time_histories().items():
            df.to_csv(d / f"time_history_{name}.csv", index=False)
        return d


def analyze(aircraft: str | Path | RunConfig, **inputs: Any) -> Analysis:
    """Solve takeoff (balanced field, all-engines, field length) and landing for one case.

    Args:
        aircraft: name, folder, aircraft.yaml, builder .zip, or a RunConfig.
        inputs: short names (``weight_lbf=650e3, k_CL=1.05``) or dotted paths, applied on
            top of the aircraft's defaults. Dotted paths can be passed with
            ``**{"aircraft.landing.free_roll_s": 3.0}``.
    """
    cfg = aircraft if isinstance(aircraft, RunConfig) else load_config(aircraft)
    if inputs:
        cfg = cfg.with_updates(inputs)
    takeoff = compute_bfl(cfg)
    try:
        landing, err = compute_landing(cfg), ""
    except Exception as exc:  # noqa: BLE001 - the takeoff answer stands on its own
        landing, err = None, f"{type(exc).__name__}: {exc}"
    return Analysis(cfg, takeoff, landing, err)


__all__ = ["analyze", "Analysis"]
