# Using it from Python

The intended workflow: build or edit the aircraft in the app's builder, save it (or
download the `.zip`), then run cases from a script. Everything the app computes is
available from the `bfl` package, and the app itself uses only these functions.

Templates: `scripts/analyze_example.py` (one case) and `scripts/trade_study_example.py`
(two trade studies with plots).

## One case

```python
from bfl import analyze

a = analyze("b747_100", weight_lbf=650_000, temperature_F=95, elevation_ft=5000)
a.runway_required_ft          # max(takeoff field length, landing runway required)
a.governed_by                 # "takeoff" or "landing"
print(a.summary())            # the same text as the app's Run summary
a.takeoff.v1_kts, a.takeoff.vr_kts, a.landing.v_approach_kts
a.scalars()                   # every output as one flat dict
a.time_histories()["go"]      # pandas DataFrame: every time step (also stop, aeo, landing)
a.save("output/case_1")       # summary.txt, results.csv, time_history_*.csv
```

## Inputs

Inputs are keyword arguments (or dict keys in a trade study). The common ones have short
names:

| short name | what | short name | what |
|---|---|---|---|
| `weight_lbf` | takeoff weight | `k_CL`, `k_CD`, `k_T` | lift / drag / thrust multipliers |
| `temperature_F` | outside air temperature | `isa_delta_F` | or: ISA deviation |
| `elevation_ft` | field elevation | `headwind_kts` | + headwind, − tailwind |
| `runway_slope_deg` | + uphill | `mu_brake`, `mu_roll` | runway friction |
| `rules` | `"part25"` or `"mil3013"` | `aero_table`, `thrust_table` | which table (by name) |
| `ground_effect` | True / False | `optimize_vr` | True / False |
| `chute` | drag chute in the rejected takeoff | `landing_weight_lbf` | landing weight |
| `landing_k_CL`, `landing_k_CD` | landing-flap multipliers | | |

Anything else is reachable by its dotted path, the same names as in `aircraft.yaml` and
the builder:

```python
analyze("b747_100", **{"aircraft.landing.free_roll_s": 3.0, "procedure.rotation_rate_deg_s": 2.5})
```

A mistyped name stops with a suggestion (`unknown input 'wieght_lbf' (did you mean
'weight_lbf'?)`), and an out-of-range value says which field and why.

## Trade studies

```python
import numpy as np
from bfl import load_config, trade_study
from bfl.trade import grid

cfg = load_config("b747_100", overrides={"elevation_ft": 5000})
df = trade_study(cfg, {
    "k_CL": np.linspace(0.8, 1.2, 9),
    "k_CD": np.linspace(0.8, 1.2, 9),
})
df.to_csv("kcl_kcd.csv", index=False)
grid(df, x="k_CD", y="k_CL", value="runway_required_ft")   # a k_CL x k_CD table
```

* Every combination is solved (a full grid), in parallel on all but one core.
  81 cases take about 1–3 s.
* One row per case: the varied inputs, the outputs, and `error` (empty when the case
  solved; failed cases stay in the table with NaN outputs, so a grid is never ragged).
* Default outputs: runway required, takeoff field length, landing runway required, BFL,
  all-engines distance, balanced, V1, VR, V2, k_VR, tire speed, brake energy. Ask for
  others with `outputs=(...)`: any key of `a.scalars()`.
* Cases are solved in runs along the **last** input, each starting the rotation-speed
  search from its neighbour's answer (results agree with independent solves to a few
  feet). Put the input with the most values last.
* Scripts need the `if __name__ == "__main__":` guard, because the study starts worker
  processes.

## Gust analysis

```python
from bfl import load_config
from bfl.gusts import GustSettings, gust_study

g = gust_study(load_config("b747_100"), GustSettings(intensity="moderate", n=500))
print(g.summary())
g.percentiles()        # per output: calm, P50/P90/P95/P99 with confidence intervals
g.samples              # one row per run (go, stop, all-engines, field length, landing, ...)
```

`GustSettings` holds the turbulence (`intensity`, `vertical`), the number of runs, the SDE
method and time step, the seed, the pilot lag and the approach speed additive. See
[Gust analysis](../assumptions/gusts.md).

## Uncertainty analysis

```python
from bfl.uncertainty import UncertaintySettings, uncertainty_study

u = uncertainty_study(load_config("b747_100"),
                      UncertaintySettings(sigma_CL=0.05, sigma_CD=0.05, sigma_T=0.05, n=500))
print(u.summary())
u.percentiles()       # nominal, P50/P90/P95/P99 with confidence intervals
u.sensitivity()       # each table's share of the runway spread
u.response_surface()  # the profiler's quadratic model (bfl.uncertainty.predict_surface)
u.samples             # one row per draw: k_CL, k_CD, k_T and every output
```

See [Uncertainty analysis](../assumptions/uncertainty.md).

## Aircraft that are not in `aircraft/`

`analyze`, `load_config` and `trade_study` take any of:

```python
analyze("b747_100")                            # a folder under aircraft/
analyze("~/designs/concept_a")                 # any folder with an aircraft.yaml
analyze("~/designs/concept_a/aircraft.yaml")   # the yaml file itself
analyze("~/Downloads/concept_b.zip")           # a .zip from the builder
```

A zip is unpacked once into `~/.cache/bfl/aircraft_zips/` (`BFL_CACHE_DIR` moves it) and
reused while it is unchanged. Many designs kept together:

```python
from pathlib import Path
from bfl import analyze, list_aircraft

designs = Path("~/designs").expanduser()
for name in list_aircraft(designs):
    a = analyze(designs / name, weight_lbf=None)   # None: the aircraft's default weight
    print(f"{name:20s} {a.runway_required_ft:8,.0f} ft  ({a.governed_by})")
```

To list another folder in the app, start it with `BFL_AIRCRAFT_DIR=~/designs python -m app`.

## Lower-level pieces

| | |
|---|---|
| `load_config(aircraft, overrides={...})` | the full configuration (`RunConfig`), validated |
| `compute_bfl(cfg)` | takeoff only: `BFLResult` (`.summary()`, `.scalars()`, `.go/.stop/.aeo` trajectories) |
| `compute_landing(cfg)` | landing only: `LandingResult` |
| `sweep_v1(cfg, n=21)` | go and stop distance against V1 (the crossing chart) |
| `bfl.plotting.bfl_chart`, `time_histories` | matplotlib versions of the app's plots |
| `scripts/run_example.py` | one takeoff with figures, from the command line |
