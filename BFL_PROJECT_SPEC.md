# Balanced Field Length (BFL) Solver — Project Spec for Claude Code

## 0. How to use this document

You are building a Python package for a graduate **numerical methods** class project. The project estimates the minimum required runway length for an aircraft using **Balanced Field Length (BFL)** under FAA Part 25 rules. The numerical core (Runge–Kutta integrators, secant root finding, event location, interpolation) must be **written from scratch** — that is the point of the class. scipy is allowed **only inside the test suite** as an independent reference.

Work in phases (Section 12). **Do Phase 1 only** unless told otherwise, but design every interface so later phases slot in without rewrites. Before writing code, read this whole document, then produce a short implementation plan (file list + order of work) and wait for my go-ahead.

The user is fluent in Python and has an existing virtual environment on **Python 3.13**. Do not use Jupyter notebooks anywhere. Everything is runnable as plain scripts from the command line (`python scripts/run_example.py`), plus a Dash app.

---

## 1. Physics background

**BFL** is the runway length at which, for an engine failure near the decision speed V1, the two choices take the same distance:

- **Go (continued takeoff):** keep accelerating on the remaining engines, rotate at VR, lift off, and climb to the 35 ft screen height. *Distance = runway start → point where h = 35 ft.*
- **Stop (rejected takeoff):** at V1 the pilot aborts: brakes, throttles to idle, spoilers (and optionally a drag chute), and decelerates to v = 0. *Distance = runway start → stop point (+ FAA 2-second allowance at V1).*

Raising V1 makes the go distance shorter and the stop distance longer. **BFL is where the two curves cross.** An outer **secant method** solves `f(V1) = d_go(V1) − d_stop(V1) = 0`.

### 1.1 Equations of motion (corrected — use these)

Notation: m = mass (slug, = W/g), g = 32.174 ft/s², α = angle of attack, θ = pitch attitude, γ = flight-path angle, φ = runway slope (positive uphill), μ = friction coefficient, V = ground speed (on runway), V_a = airspeed, V_w = headwind component (positive = headwind), q̄ = ½ρV_a², S = wing reference area.

Aero forces always use **airspeed**: `L = q̄·S·CL(α)·k_CL`, `D = q̄·S·CD(α)·k_CD + ΔD_extra` where k_CL and k_CD are user multipliers (Section 4.3) and ΔD_extra covers engine-out drag, spoilers and chute (Section 5).

**Ground roll** (state: x, V; on the runway θ = α):
```
V_a  = V + V_w
N    = m·g·cos φ − L − T·sin α          # clamp N ≥ 0; N → 0 defines liftoff
dV/dt = (T·cos α − D − μ·N − m·g·sin φ) / m
dx/dt = V
```
(Lift is perpendicular to the horizontal relative wind on the ground, so it's `L`, not `L·cos α`.)

**Airborne** (state: x, h, V_a, γ; steady wind in Phase 1, air-mass-relative frame):
```
dV_a/dt = (T·cos α − D)/m − g·sin γ
dγ/dt   = (T·sin α + L)/(m·V_a) − g·cos γ / V_a
dh/dt   = V_a·sin γ
dx/dt   = V_a·cos γ − V_w
```
with `α = θ − γ`. At liftoff: V_a = V + V_w, γ = 0, h = 0. In Phase 1, treat the runway as locally flat for the airborne segment (h is measured above the liftoff point). Write this assumption down in `docs/equations.md`.

Put every equation, sign convention and assumption in `docs/equations.md`, and keep it in sync with the code.

---

## 2. Takeoff sequences (FAA Part 25 style)

All timing parameters are configurable, with the defaults shown.

### 2.1 Common start
1. **AEO acceleration** (all engines operating) from V = 0, θ = θ_ground (ground attitude, an input, default 0°), μ = μ_roll.
2. **Engine failure at V_EF.** The failed engine's thrust goes to 0, and the engine-out drag increment ΔCD_eo is added from then on.
3. **Recognition interval** `t_recog` (default 1.0 s) of OEI acceleration from V_EF to V1. V_EF is the speed such that OEI acceleration for `t_recog` ends exactly at V1. Find it with an **inner secant solve** on V_EF (another use of the root finder). `t_recog = 0` must be supported and means the engine fails exactly at V1.

### 2.2 Go branch (continued takeoff, OEI)
4. Continue OEI acceleration to **VR**.
5. **Rotation:** pitch rate `q_rot` (default 3 °/s) from θ_ground up to `θ_target = θ_tailstrike − tailstrike_margin` (margin default 1°). θ_tailstrike is an aircraft input. If θ_target is reached while still on the ground, hold θ and keep rolling.
6. **Liftoff** is the event N = 0. Switch to the airborne equations.
7. **Airborne:** hold θ = θ_target, so α = θ − γ changes naturally as γ builds.
8. Stop at the event **h = 35 ft**. d_go = x at that event.
9. **Touchback guard:** if h drops below 0 after liftoff (a weak takeoff that settles back onto the runway), the takeoff is invalid. Increase the VR factor `k_VR` by `vr_step` (default +0.01), rerun the **whole** BFL solve (VR is an aircraft-level speed, not per-V1), and repeat up to `max_vr_retries`. Record every adjustment in the result's warnings. If retries run out, raise a clear error.

### 2.3 Stop branch (rejected takeoff)
4. At V1: **brakes on** (μ switches to μ_brake).
5. At V1 + `t_idle` (default 1 s): operating engines to **idle thrust** (aircraft input, per engine; the failed engine stays at 0 thrust plus its drag increment).
6. At V1 + `t_spoilers` (default 2 s): spoilers deploy. Apply ΔCL_spoiler (negative, dumps lift and raises N) and ΔCD_spoiler.
7. Optional **drag chute** (Section 5.2), deployed at V1 + `t_chute`.
8. Integrate to the event V = 0. Then `d_stop = x_stop + 2 s × V1` (Part 25 distance allowance, configurable `t_v1_allowance`, default 2.0).
9. No reverse-thrust credit (Part 25 dry runway). Make this a documented assumption.

### 2.4 Speeds
- **Stall speed:** `V_S = sqrt(2·m·g / (ρ·S·CLmax·k_CL))`. CLmax is the maximum CL in the takeoff-configuration aero table, so the CL multiplier affects V_S.
- **VR:** `VR = k_VR · V_S` (default k_VR = 1.10). VR is an equivalent airspeed reference, so compare it against airspeed.
- **V1 bounds:** `V1_min ≤ V1 ≤ VR`. V1_min = `V_mcg` if given (optional input), else a configurable fraction of VR (default 0.6). If `f(V1)` has no sign change in the bounds, return an **unbalanced** result: V1 = VR if the stop distance is still shorter at VR (report the go distance), otherwise V1 = V1_min (report the stop distance). Flag it clearly.
- **Report:** V_S, VR, V_EF, V1, V_LOF (liftoff airspeed), V2 (airspeed at 35 ft), and the diagnostic `V2 / V_S` (Part 25 wants ≥ 1.2). This is a diagnostic only, not enforced.

### 2.5 Also compute
- **AEO takeoff distance** to 35 ft (no failure), and the **FAA takeoff field length** = max(BFL, 1.15 × AEO distance). Boeing's published runway-length charts are field length, so this is the number to compare against them.

---

## 3. Numerical methods (written from scratch)

### 3.1 `integrators.py`
- **RK4** with a fixed step.
- **RK45 Dormand–Prince** with adaptive step: embedded error estimate, rtol/atol, step-size controller with safety factor and min/max clamps. Count rejected steps.
- Common interface, something like `integrate(rhs, t0, y0, t_max, method, events, **opts) -> Solution`.
- **Event detection:** each event is a function `g(t, y)` with direction (+1/−1/0) and a terminal flag. After each accepted step, check for a sign change. Locate the event time by running the **secant/safeguarded root finder** on `t* ↦ g(t*, y(t*))`, where `y(t*)` comes from **re-taking a single RK step from the step start with size `t* − t_n`**. This keeps the event accurate to the integrator's order with no dense output needed. Event time tolerance is configurable (default 1e-9 s).
- Events can **switch phases**, e.g. N = 0 switches from ground to air dynamics. Segment chaining belongs in `phases.py`, not inside the integrator.
- The RHS must be a pure function of `(t, y, params)`. Also provide a separate `forces(t, y, params) -> dict` that returns L, D, T, N, friction, q̄, CL, CD, α, θ, etc. This feeds the outputs and plots.

### 3.2 `rootfind.py`
- `secant(f, x0, x1, tol, maxiter) -> RootResult` (root, converged, iterations, **full history of x and f(x)**).
- `safeguarded_secant(f, a, b, ...)`: keeps a bracket. If a secant iterate leaves the bracket or stalls, it falls back to a bisection step. Use this for the V1 solve, the V_EF solve and event location.
- The history is used for convergence plots (Section 9).

### 3.3 `tables.py` (interpolation)
- **Piecewise-linear** interpolation (default) and a **hand-written natural cubic spline** (tridiagonal solve via the Thomas algorithm). Both live behind one interface.
- **Bilinear** interpolation for 2-D tables (e.g. thrust vs airspeed and temperature).
- **Out-of-range behavior** is configurable: `"error"` (default) or `"clamp"` with a warning.

---

## 4. Inputs

### 4.1 File layout per aircraft
```
aircraft/<name>/
  aircraft.yaml                 # geometry (ft, ft²), weight (lbf), engines, speeds, device settings
  aero_takeoff.csv              # takeoff flap configuration
  aero_<other_config>.csv       # optional extra configs
  thrust.csv                    # optional; omit if using constant thrust
  README.md                     # data provenance: where every number came from
```
**Every aircraft is defined by tables + YAML.** Nothing pulls live from external Python packages at run time. Someone with CFD or wind-tunnel data should be able to drop in CSVs and run.

### 4.2 Aero table CSV (one file per configuration)
Columns: `alpha_deg, CL, CD`. One row per α, monotonic increasing α. CLmax = max(CL) in the file.
Optional extra columns are ignored for now; design the loader so a later column (e.g. `h_over_b` for ground effect) can make it 2-D.

### 4.3 Multipliers (central feature for the demo)
- `k_CL` multiplies the table CL **everywhere, including CLmax** (so it moves V_S and VR).
- `k_CD` multiplies the table CD.
- Both are inputs to `compute_bfl` and adjustable in the Dash app. The goal is to show whether improving lift or reducing drag shortens the runway more.

### 4.4 Thrust (per engine)
Two modes, selected in `aircraft.yaml`:
- `constant`: `thrust_per_engine_lbf`.
- `table`: `thrust.csv` with columns `airspeed_kts, thrust_lbf` (1-D), or `airspeed_kts, temperature_F, thrust_lbf` (2-D, bilinear). Convert the airspeed to ft/s on load.

Also: `n_engines`, `idle_thrust_per_engine_lbf`, `thrust_incidence_deg` (angle of the thrust line relative to the body axis; default 0, so the thrust angle relative to the velocity is α + incidence).

### 4.5 Atmosphere (`atmosphere.py`)
ISA troposphere, hand-coded in English units: sea-level 2116.22 lbf/ft², 518.67 °R, lapse rate 0.0035662 °R/ft, R = 1716.49 ft·lbf/(slug·°R). Take the pressure at field elevation from ISA, and compute **density from the actual temperature**: `ρ = p_ISA(elev) / (R·T_actual)` in slug/ft³. Inputs: `elevation_ft`, and either `temperature_F` or `isa_delta_F`. Use °R internally. Sound speed is not needed yet.

### 4.6 Environment / run inputs
`elevation_ft`, `temperature_F`, `headwind_kts` (negative = tailwind), `runway_slope_deg`, `mu_roll` (default 0.03), `mu_brake` (default 0.30), `weight_lbf` (constant; no fuel burn; mass = W/g in slugs).
Wind goes through a `WindModel` interface (`wind(t, x, h) -> headwind_ftps`). Phase 1 implements only `SteadyWind`. This is the hook for stochastic gusts later (Section 12).

### 4.7 Config handling
- pydantic models for validation, loaded from YAML.
- One top-level `RunConfig` = aircraft + environment + procedure timings + solver settings + multipliers.
- **English units throughout.** Internally use the consistent ft–slug–s–lbf system: lengths in ft, speeds in ft/s, forces in lbf, mass in slug, density in slug/ft³, pressure in lbf/ft², temperature in °R. Inputs and outputs use convenient English units:
  - lengths, elevation and areas in ft / ft²
  - speeds in knots
  - forces and weight in lbf
  - temperature in °F
  - angles in degrees
- Every field name carries its unit suffix (`_ft`, `_ft2`, `_kts`, `_ftps`, `_lbf`, `_slug`, `_F`, `_R`, `_deg`, `_s`).
- Convert only at the boundaries (config load and result reporting), never inside the dynamics. A small `units.py` holds every conversion constant, so knots, °F and the rest are converted in exactly one place. It also offers SI→English helpers in case someone's CFD tables are in SI.
- Every default in this document lives in one place (the pydantic models) and is overridable.

---

## 5. Drag increments and devices

### 5.1 Engine-out drag
After failure, add `ΔCD_engine_out` (aircraft input) to represent windmilling/dead-engine drag plus rudder/aileron trim drag for the asymmetric thrust. It is applied in both branches after V_EF. Document it as a lumped, user-tunable term. Also apply it in the stop branch. Note in docs that the *operating* engines go to idle in the stop branch, while the failed engine produces no thrust.

### 5.2 Drag chute (optional, per aircraft)
`chute.enabled`, `chute.area_ft2`, `chute.CD`, `chute.deploy_delay_s` (after V1), `chute.inflation_time_s` (drag ramps linearly from 0 to full over this time). Chute drag = `q̄·area·CD_chute`. Stop branch only. Part 25 doesn't credit chutes for transports; the docs and the results should flag that a chute run is outside Part 25.

### 5.3 Spoilers
`spoilers.delta_CL`, `spoilers.delta_CD` (aircraft inputs), deployed at V1 + `t_spoilers` in the stop branch.

---

## 6. Outputs

### 6.1 Top-level API (`bfl.py`)
```python
result = compute_bfl(config: RunConfig) -> BFLResult
sweep  = sweep_v1(config, v1_values) -> pandas.DataFrame   # d_go, d_stop vs V1 (the classic crossing chart)
```
`BFLResult` (dataclass):
- `bfl_ft`, `balanced: bool`, `v1_kts`, `vr_kts`, `v_ef_kts`, `v_s_kts`, `v_lof_kts`, `v2_kts`, `aeo_distance_ft`, `faa_field_length_ft`
- `go: Trajectory`, `stop: Trajectory`, `aeo: Trajectory`
- `v1_solver_history` (secant iterates), `vr_adjustments`, `warnings: list[str]`
- `summary() -> str` (pretty table) and `to_json()`

`Trajectory.to_dataframe()` columns (one row per accepted step **plus every event point**): `t_s, x_ft, h_ft, V_ground_kts, V_air_kts, gamma_deg, theta_deg, alpha_deg, CL, CD, L_lbf, D_lbf, T_total_lbf, N_lbf, F_friction_lbf, q_bar_psf, mu, phase` where `phase` ∈ {`aeo_roll`, `oei_recog`, `oei_roll`, `rotation`, `airborne`, `braking`}, plus an event list with names and times.

### 6.2 Scripts (`scripts/`)
- `run_example.py`: loads an aircraft, runs `compute_bfl`, prints the summary, saves matplotlib figures (go/stop vs V1, time histories) to `output/`.
- `make_verification_figures.py`: see Section 9.
- No notebooks.

---

## 7. Example aircraft

1. **`generic_widebody_synthetic`** (Phase 1, required). A fictional 4-engine widebody with plausible order-of-magnitude numbers so everything runs on day one and the demo looks like a big jet. Its README must clearly say it is **synthetic, not real data**. Aero CSV built from a simple lift curve (CLα, CL0, smooth stall roll-off to CLmax) and a parabolic drag polar, sampled to a table.
2. **`b747_100`** (Phase 1 scaffold only). Folder, YAML and CSV **templates with headers and TODO markers**, but **do not invent values**. The user will digitize data from Hanke & Nordwall, *The Simulation of a Jumbo Jet Transport Aircraft, Vol. II: Modeling Data*, NASA CR-114494 (1970), and Hanke, NASA CR-1756 Vol. I. Its README lists exactly which quantities are needed: S, weight, tail-strike angle, takeoff-flap CL/CD vs α, spoiler increments, thrust, idle thrust, engine-out drag.
3. **`sr71`** (Phase 2). The user has the lift curve and thrust-vs-temperature curves from the manual; drag must be estimated. It supports the drag chute. Uses the 2-D thrust table.
4. **OpenAP converter** (Phase 2): `tools/openap_to_tables.py` generates `aircraft/<openap_type>/` folders (CSV + YAML) from the `openap` package (dev-only dependency, never imported by `src/`). OpenAP provides a drag polar (CD0, k, flap/gear increments) and a takeoff thrust model but **no CL(α)**, so the tool takes an assumed `CLalpha`, `CL0` and `CLmax` as arguments and records them in the README. Check the actual OpenAP API and data files; don't guess function signatures. Check whether its thrust is total or per-engine and convert to per-engine.

---

## 8. Dash app (Phase 1 minimal version — needed for a demo in about a week)

`app/` package, run with `python -m app` (or `python app/main.py`).

**Controls:**
- Aircraft dropdown (scans `aircraft/`).
- Sliders/inputs for k_CL, k_CD, μ_roll, μ_brake, headwind (kts), slope, temperature (°F), elevation (ft), weight (lbf), rotation rate.
- Chute on/off when the aircraft has one.
- "Run" button.
- "Pin as baseline" button: overlay a pinned baseline run against the current run in every plot.

**Panels:**
1. **Readout:** BFL, V1, VR, V2, field length, balanced/unbalanced, warnings.
2. **BFL chart:** d_go and d_stop vs V1 with the crossing marked.
3. **Takeoff animation:** side view of the runway with distance tick marks, the 35 ft screen and the BFL marker. Two lanes (go and stop) animate together on a shared time axis. The aircraft is drawn as a simple shape rotated by θ. Altitude has a **vertical exaggeration** control (35 ft vs. ~10,000 ft of runway is otherwise invisible). Use Plotly animation frames resampled to ~20–30 fps.
4. **Time histories:** tabs for speeds, forces, angles, positions.
5. **Sensitivity:** BFL vs multiplier (0.8 → 1.2) for k_CL and k_CD on the same axes, so lift-vs-drag impact is visible at a glance.

**Performance:** default to RK4 with dt ≈ 0.01 s. Cache results on the input hash. Each BFL solve should take well under a second for the synthetic aircraft.

Keep the computation fully separate from the UI: the app only calls `compute_bfl` / `sweep_v1`.

---

## 9. Testing and verification

The user prefers **integration-style tests** over exhaustive unit tests. Use pytest. scipy is a **test-only** dependency.

### 9.1 Integrator verification
- **Exact solutions:** exponential decay, harmonic oscillator, and logistic growth. Check RK4 and RK45 against the closed forms.
- **Against scipy:** a nonlinear system (Van der Pol with mild μ, or Lotka–Volterra). Compare against `scipy.integrate.solve_ivp(method="DOP853", rtol=1e-12)`.
- **Observed order of accuracy:** run RK4 at dt, dt/2, dt/4, … and fit the slope of log(error) vs log(dt). Assert the slope ≈ 4 (within ±0.3). Halving the step should cut the error by about 2⁴ = 16×.
- **RK45:** the global error is controlled by rtol, and the error decreases as rtol is tightened.
- **Event location:** the computed time an exact solution crosses a known level matches the analytic crossing time to tolerance, independent of step size.

### 9.2 Root finder verification
- Known roots: x² − 2, cos x − x, and a cubic.
- **Observed convergence order** from the history: estimate p from successive errors; assert ≈ 1.618 (golden ratio) for the plain secant on a smooth simple root.
- The safeguarded version converges on a case where plain secant diverges (e.g. arctan x from a poor start).

### 9.3 Physics verification
- **Analytic ground roll:** with constant T, CL, CD, μ and no slope or wind, the ground-roll ODE is linear in V², so the distance to reach speed V has a closed form: `x(V) = (m/(2B)) · ln(A / (A − B·V²))`, with `A = T − μ·m·g` and `B = ½ρS(CD − μ·CL)`. Assert the code matches. Derive this carefully in `docs/equations.md` and check the signs.
- **Balance check:** at the solved V1, |d_go − d_stop| < tolerance.
- **Monotonicity:** in `sweep_v1`, d_go decreases and d_stop increases with V1.
- **Directional sanity:** each of the following moves BFL the right way:
  - higher μ_brake → shorter
  - chute on → shorter
  - headwind → shorter
  - uphill slope → longer go and shorter stop
  - larger ΔCD_eo → longer
  - higher temperature or elevation → longer
  - higher mass → longer
- **Step-size independence:** BFL changes by < 0.1% between dt = 0.01 and dt = 0.005.
- **Touchback guard** triggers on a deliberately underpowered config and raises VR.

### 9.4 `scripts/make_verification_figures.py`
Saves PNGs to `output/verification/` for slides:
1. RK4/RK45 vs exact solution overlay.
2. Log-log error vs step size with the fitted slope annotated and a reference slope-4 line.
3. Secant error vs iteration (log scale) with the observed order annotated.
4. Our RK vs scipy on the nonlinear test system.
5. Analytic ground roll vs simulated.
6. The BFL crossing chart for the synthetic aircraft.
7. A summary image listing each check with PASS/FAIL and the measured value.

---

## 10. Repository layout
```
pyproject.toml            # package "bfl", src layout, deps: numpy, pandas, pydantic, pyyaml,
                          # matplotlib, dash, plotly. Optional groups: [test]=pytest, scipy; [dev]=openap
README.md                 # quickstart: install, run example, run app, run tests
docs/equations.md         # all equations, sign conventions, assumptions, Part 25 procedure
src/bfl/
  __init__.py             # exports compute_bfl, sweep_v1, load_config
  config.py               # pydantic models + YAML loader + defaults
  units.py
  atmosphere.py
  tables.py               # CSV loading, linear / natural cubic spline / bilinear
  aero.py                 # AeroModel: CL, CD, CLmax with multipliers and increments
  propulsion.py           # ConstantThrust, TableThrust; engines-operating aware
  environment.py          # atmosphere state, WindModel protocol, SteadyWind, slope
  dynamics.py             # ground_rhs, air_rhs, forces()
  integrators.py          # rk4, rk45 (Dormand–Prince), event handling
  rootfind.py             # secant, safeguarded_secant
  phases.py               # segment definitions + chaining via events
  takeoff.py              # simulate_go, simulate_stop, simulate_aeo
  bfl.py                  # compute_bfl, sweep_v1, VR retry logic
  results.py              # Trajectory, BFLResult
  plotting.py             # matplotlib helpers for scripts
app/                      # Dash app (layout, callbacks, animation builder)
aircraft/                 # one folder per aircraft (Section 7)
scripts/                  # run_example.py, make_verification_figures.py
tools/                    # openap_to_tables.py (Phase 2)
tests/
output/                   # gitignored
```
Use type hints throughout, docstrings on public functions, `ruff` formatting, and no global state.

---

## 11. Defaults summary
| Parameter | Default |
|---|---|
| μ_roll / μ_brake | 0.03 / 0.30 |
| k_VR (VR / V_S) | 1.10 |
| Rotation rate | 3 °/s |
| Tail-strike margin | 1° |
| Screen height | 35 ft |
| t_recog (V_EF → V1) | 1.0 s |
| Brakes / idle / spoilers after V1 | 0 / 1 / 2 s |
| V1 distance allowance | 2 s × V1 |
| VR retry step / max retries | +0.01 / 20 |
| V1_min (no V_mcg given) | 0.6 VR |
| Integrator / dt | RK4 / 0.01 s (RK45: rtol 1e-8, atol 1e-8) |
| Event time tolerance | 1e-9 s |
| V1 solve tolerance | 0.05 ft in (d_go − d_stop) |
| Units | inputs/outputs: ft, kts, lbf, °F, deg; internal: ft–slug–s–lbf, °R |
| k_CL / k_CD | 1.0 / 1.0 |

---

## 12. Phases

**Phase 1 (now; check-in in ~1 week):**
- Sections 1–6 and 9–11.
- The synthetic aircraft and the 747 template.
- The minimal Dash app (Section 8).
- `make_verification_figures.py`.

**Phase 2:**
- SR-71 aircraft with drag chute and 2-D thrust table.
- OpenAP → tables converter.
- 747 data once digitized, compared against Boeing *Airplane Characteristics for Airport Planning* takeoff runway-length charts using `faa_field_length_ft`.
- Optional ground-effect column in aero tables.

**Phase 3 (stochastics — design hooks now, don't implement):**
- **Stochastic gusts:** a `WindModel` driven by an Ornstein–Uhlenbeck process (or Dryden spectrum). Solve the resulting SDE with **Euler–Maruyama** and/or a **stochastic Heun** method written from scratch. Compare strong/weak convergence order against theory (½ and 1 for Euler–Maruyama), and show gust traces in the Dash animation. Note: time-varying wind in the airborne phase requires reformulating the airborne state in the ground frame (or adding wind-rate terms). Keep `dynamics.py` structured so that change is local.
- **Uncertainty propagation:** Monte Carlo / Latin hypercube over k_CL, k_CD, thrust, μ_brake, reaction times and wind, producing a BFL distribution and percentiles.

---

## 13. Ground rules for you (Claude Code)
- Do not fabricate real-aircraft data. Synthetic data must be labeled synthetic everywhere it appears.
- Don't import scipy (or openap) anywhere under `src/` or `app/`.
- If a physics or procedure detail here is ambiguous or seems wrong, stop and ask rather than silently choosing.
- After Phase 1, run the full test suite and the verification script, then report:
  - the pass/fail summary
  - the synthetic aircraft's BFL result
  - any assumptions you had to make