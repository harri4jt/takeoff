"""Reference-aircraft limits (app/reference_aircraft.yaml) -> warnings and scale strips.

The file is re-read on every run, so edits show up without restarting the app.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PATH = Path(__file__).resolve().parent / "reference_aircraft.yaml"


def load() -> dict[str, Any]:
    try:
        data = yaml.safe_load(PATH.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {"metrics": {}, "aircraft": [], "error": f"cannot read {PATH.name}"}
    data.setdefault("metrics", {})
    data.setdefault("aircraft", [])
    return data


def _own_limits(scalars: dict[str, Any], own: dict[str, Any] | None) -> list[str]:
    out = []
    if not own:
        return out
    lim = own.get("tire_speed_limit_kts")
    if lim and scalars.get("max_tire_speed_kts", 0) > lim:
        out.append(f"Tire speed {scalars['max_tire_speed_kts']:.0f} kt exceeds this aircraft's "
                   f"limit ({lim:.0f} kt)")  # fmt: skip
    lim = own.get("max_brake_energy_MJ")
    if lim and scalars.get("brake_energy_MJ", 0) > lim:
        out.append(f"Brake energy {scalars['brake_energy_MJ']:,.0f} MJ exceeds this aircraft's "
                   f"limit ({lim:,.0f} MJ)")  # fmt: skip
    return out


def warnings(scalars: dict[str, Any], own: dict[str, Any] | None = None) -> list[str]:
    """Messages like 'Tire speed 201 kt exceeds 747-100 (195 kt)'."""
    data = load()
    msgs = _own_limits(scalars, own)
    for ac in data["aircraft"]:
        if not ac.get("warn"):
            continue
        for key, meta in data["metrics"].items():
            ref, val = ac.get(key), scalars.get(key)
            if ref is None or val is None:
                continue
            if val > ref:
                label = meta.get("label", key).split(" (")[0].split(",")[0]
                unit = meta.get("unit", "")
                fmt = ",.1f" if f"{val:,.0f}" == f"{ref:,.0f}" else ",.0f"
                msgs.append(f"{label} {val:{fmt}} {unit} exceeds {ac['name']} ({ref:{fmt}} {unit})")
    return msgs


def strips(scalars: dict[str, Any]) -> list[dict[str, Any]]:
    """One strip per metric: [{label, unit, value, refs: [(name, value, warn)]}]."""
    data = load()
    out = []
    for key, meta in data["metrics"].items():
        val = scalars.get(key)
        refs = [
            (ac["name"], float(ac[key]), bool(ac.get("warn")))
            for ac in data["aircraft"]
            if ac.get(key) is not None
        ]
        if val is None or not refs:
            continue
        out.append({"key": key, "label": meta.get("label", key), "unit": meta.get("unit", ""),
                    "value": float(val), "refs": refs})  # fmt: skip
    return out
