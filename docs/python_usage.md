# Using the tool from Python

Everything the app does is available from the `bfl` package. The app itself only calls
these functions.

## One case

```python
from bfl import load_config, compute_bfl

cfg = load_config("b747_100", overrides={"environment.temperature_F": 90,
                                         "environment.elevation_ft": 5000})
r = compute_bfl(cfg)
print(r.summary())             # the text in the app's Run summary tab
r.field_length_ft              # runway required [ft]
r.go.to_dataframe()            # every time step of the engine-out go (also .stop, .aeo)
```

`overrides` takes dotted paths into the configuration, for example
`environment.weight_lbf`, `environment.headwind_kts`, `environment.mu_brake`,
`multipliers.k_CL`, `procedure.optimize_vr`, `aircraft.aero.delta_CD_engine_out`.
A mistyped path is an error, not silently ignored.

## Landing

```python
from bfl import compute_landing
lr = compute_landing(cfg)      # same config; landing settings come from aircraft.yaml
lr.runway_required_ft, lr.landing_distance_ft
print(lr.summary())
```

## Aircraft that are not in `aircraft/`

`load_config` (and `trade_study`) take any of:

```python
load_config("b747_100")                          # a folder under aircraft/
load_config("~/designs/concept_a")               # any folder with an aircraft.yaml
load_config("~/designs/concept_a/aircraft.yaml") # the yaml file itself
load_config("~/Downloads/concept_b.zip")         # a .zip from the builder's Download
```

A zip is unpacked once into `~/.cache/bfl/aircraft_zips/` (set `BFL_CACHE_DIR` to move it)
and reused while it is unchanged. To run many designs kept together:

```python
from pathlib import Path
from bfl import list_aircraft, load_config, compute_bfl

designs = Path("~/designs").expanduser()
for name in list_aircraft(designs):
    r = compute_bfl(load_config(designs / name))
    print(f"{name:20s} {r.field_length_ft:8,.0f} ft")
```

The app lists the aircraft in `aircraft/`; start it with `BFL_AIRCRAFT_DIR=~/designs python -m
app` to list another folder instead.

## Trade studies

```python
import numpy as np
from bfl import load_config, trade_study
from bfl.trade import grid

cfg = load_config("b747_100")
df = trade_study(cfg, {
    "multipliers.k_CL": np.linspace(0.8, 1.2, 9),
    "multipliers.k_CD": np.linspace(0.8, 1.2, 9),
})
df.to_csv("kcl_kcd.csv", index=False)
grid(df, x="multipliers.k_CD", y="multipliers.k_CL", value="field_length_ft")
```

* Every combination of the varied inputs is solved (a full grid), in parallel.
  81 cases of the 747 take about 2.5 s.
* The result is a pandas DataFrame, one row per case: the varied inputs, the chosen
  outputs (`outputs=`, any key of `BFLResult.scalars()`; the default is runway required,
  BFL, all-engines distance, balanced, V1, VR, V2, k_VR, tire speed, brake energy) and
  `error` (empty when the case solved; failed cases are kept with NaN outputs).
* Cases are solved in runs along the **last** varied input, each one starting the VR
  optimizer from its neighbour's answer. Put the input with the most values last.
* Scripts that use it need the usual `if __name__ == "__main__":` guard, because the
  study starts worker processes.

`scripts/trade_study_example.py` is a complete template: an aero (k_CL × k_CD) study with a
contour plot, and a weight × temperature study at a 5,000 ft airport.

## Other building blocks

| | |
|---|---|
| `sweep_v1(cfg, n=21)` | go and stop distance vs V1 (the classic crossing chart) |
| `list_aircraft()` | the aircraft folders available |
| `bfl.plotting.bfl_chart`, `time_histories` | matplotlib versions of the app's plots |
| `scripts/run_example.py` | one case: summary, figures and CSVs |
