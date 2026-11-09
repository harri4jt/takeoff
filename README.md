# Balanced Field Length (BFL) solver

This is a MATH 6006 numerical-methods project. It estimates the runway an aircraft
needs under FAA Part 25-style rules: the **balanced field length**, where a continued
takeoff with one engine failed and a rejected takeoff need the same distance.

The numerical core is written from scratch in `src/bfl/`:

* fixed-step **RK4** and adaptive **Dormand–Prince RK45**
* **event location** by re-taking partial RK steps
* **secant** and bracket-**safeguarded secant** root finders
* **linear**, **natural cubic spline** (Thomas algorithm) and **bilinear** interpolation

scipy is used **only** in the tests and the verification script, as an independent
reference.

## Install

```bash
pip install -e ".[test]"        # into your Python 3.13 environment
```

## Run

```bash
python scripts/run_example.py                  # summary + figures in output/
python scripts/run_example.py --kcl 1.1 --headwind 10
python scripts/make_verification_figures.py    # PNGs in output/verification/
python -m app                                  # Takeoff Performance Explorer at http://127.0.0.1:8050
python -m pytest                               # test suite (~15 s)
```

From Python:

```python
from bfl import load_config, compute_bfl, sweep_v1
cfg = load_config("generic_widebody_synthetic",
                  overrides={"environment.headwind_kts": 10, "multipliers.k_CL": 1.05})
r = compute_bfl(cfg)
print(r.summary())
df = r.go.to_dataframe()          # time histories
sw = sweep_v1(cfg)                 # go/stop vs V1
```

## Layout

| Path | Contents |
|---|---|
| `src/bfl/` | the package: config, units, atmosphere, tables, aero, propulsion, dynamics, integrators, rootfind, phases, takeoff, bfl, results, plotting |
| `app/` | Dash front end ("Takeoff Performance Explorer"): animation, runway strip, details, and the docs as pages (☰ menu). It only calls the public `bfl` API. |
| `aircraft/<name>/` | `aircraft.yaml` + CSV tables + README with data provenance |
| `docs/equations.md` | every equation, sign convention and numerical method |
| `docs/assumptions.md` | modelling decisions, the V-speed glossary, assumptions |
| `docs/methods/` | one page per numerical method + verification gallery (also served by the app) |
| `docs/STUDY_GUIDE.md` | checklist for understanding the implementation |
| `scripts/` | `run_example.py`, `make_verification_figures.py` |
| `tools/` | `make_synthetic_widebody.py` (table generator) |
| `tests/` | integrator, root finder, interpolation and physics tests |

## Aircraft

* `generic_widebody_synthetic`: **synthetic, invented data** for a fictional 4-engine widebody.
* `b747_100`: **template only**. Fill it in from NASA CR-114494 / CR-1756 (see its README).
  Until then it fails validation on purpose.

To add an aircraft, make a folder with an `aircraft.yaml` (copy one of the existing
ones), `aero_takeoff.csv` (`alpha_deg,CL,CD`), and optionally `thrust.csv`
(`airspeed_kts,thrust_lbf` or `airspeed_kts,temperature_F,thrust_lbf`). All units are
English. Every default lives in `src/bfl/config.py`.
