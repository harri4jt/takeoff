# Balanced Field Length (BFL) solver

This started as a MATH 6006 numerical-methods project and is growing into a
conceptual-design takeoff tool. It estimates the runway an aircraft needs: the
**balanced field length** under FAA Part 25, or the **critical field length** under
MIL-STD-3013. In both, a continued takeoff with one engine failed and a rejected
takeoff need the same distance.

Features: Part 25 / MIL-STD-3013 rule sets, optional Raymer ground effect, fuel burn
from TSFC, refusal speed for a given runway, tire-speed and brake-energy outputs with
reference-aircraft warnings, a trade-study page (k_CL × k_CD maps per aero/thrust table),
an aircraft builder, and validation pages for the 747-100 and SR-71 fed by the test suite.

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
python -m pytest                               # tests (~15 s); also refreshes the validation pages
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
| `app/` | Dash front end ("Takeoff Performance Explorer"): simulator with animation, trade study (`trade.py`), aircraft builder (`builder.py`), aircraft data/validation pages (`datapages.py`), docs as pages (☰ menu). It only calls the public `bfl` API. |
| `app/reference_aircraft.yaml` | reference aircraft for the tire-speed / brake-energy warnings (**placeholder values**; edit freely) |
| `aircraft/<name>/` | `aircraft.yaml` + CSV tables + README with data provenance |
| `docs/equations.md` | every equation, sign convention and numerical method |
| `docs/assumptions.md` | modelling decisions, the V-speed glossary, assumptions |
| `docs/methods/` | one page per numerical method + verification gallery (also served by the app) |
| `docs/STUDY_GUIDE.md` | checklist for understanding the implementation |
| `scripts/` | `run_example.py`, `make_verification_figures.py` |
| `tools/` | `make_synthetic_widebody.py`, `make_b747_tables.py`, `make_sr71_tables.py` (table generators) |
| `tests/` | integrator, root finder, interpolation, physics, feature and validation tests (`test_validation.py` writes the figures/status the app's data pages show) |

## Aircraft

* `generic_widebody_synthetic`: **synthetic, invented data** for a fictional 4-engine widebody.
* `b747_100`: **real data** for the Boeing 747-100 (JT9D-3), digitized from NASA
  CR-114494 and Boeing's airport-planning document. Flaps 10 and 20; sea level,
  standard day only. Validated against Boeing's runway-length chart
  (`tests/test_validation.py`, ±12 %; model 5–9% conservative). Sources in its README.
* `sr71`: **real lift and thrust** for the Lockheed SR-71A from the declassified flight
  manual (2-D thrust table vs airspeed and temperature, drag chute). Drag is
  **estimated**. Sea-level pressure altitude, −38 to 40 °C. Sources in its README.

To add an aircraft, make a folder with an `aircraft.yaml` (copy one of the existing
ones), `aero_takeoff.csv` (`alpha_deg,CL,CD`), and optionally `thrust.csv`
(`airspeed_kts,thrust_lbf` or `airspeed_kts,temperature_F,thrust_lbf`). All units are
English. Every default lives in `src/bfl/config.py`.
