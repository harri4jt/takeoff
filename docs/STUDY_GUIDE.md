# Study guide: understand the code well enough to defend it

A checklist for going through the implementation. Each section has **what to read**,
**what to do** (small experiments that make it stick), and **questions you should be
able to answer without notes**. Check items off as you go. A suggested order is at the
bottom.

Run everything from the project root with the `bfl` env active.

---

## 0. The big picture (do this first, ~30 min)

- [ ] Read `docs/methods/overview.md` (or "How it works" in the app).
- [ ] Run `python scripts/run_example.py` and read the printed summary line by line.
- [ ] In the app, play the animation and watch the go and stop aircraft split at V1.
- [ ] Open *Engineering details → V1 trade* and find the crossing.

**Be able to answer**
- [ ] What is a balanced field length, in one sentence?
- [ ] Why does go distance *fall* and stop distance *rise* as V1 increases?
- [ ] What is the difference between V_EF and V1? Why is there a 1 s gap?
- [ ] What is the FAA field length, and when does the 1.15 × all-engines number win?
- [ ] Why does the stopping aircraft in the animation stop ~500 ft before the red line?
      (2-second allowance: added on paper, not flown.)

---

## 1. Physics model (`dynamics.py`, `docs/equations.md` §3–5)

- [ ] Read `ground_terms` and `ground_rhs`. Match every term to equations.md §4.
- [ ] Read `air_terms` and `air_rhs`. Match them to §5.
- [ ] Read `forces()`: it is the same physics, returned in output units for plotting.
- [ ] Look at the *Forces* tab for the stop branch. Explain the jump in normal force
      when the spoilers deploy.

**Be able to answer**
- [ ] What is the state vector on the ground? In the air? Why do they differ?
- [ ] Why is N (normal force) clamped at 0, and why is lift-off detected on the
      *unclamped* N?
- [ ] Sign conventions: + headwind, + uphill slope, + nose up. What does a tailwind do
      to the airspeed at brake release?
- [ ] Where does the runway slope enter the equations? (`W·sin φ`.)
- [ ] Why do spoilers shorten the stop even though their drag is small? (They dump
      lift → more weight on the wheels → more braking force μN.)
- [ ] What is a point-mass model, and what does it ignore? (Pitch dynamics, lateral
      motion, ground effect, fuel burn.)
- [ ] Why use equivalent airspeed (KEAS) for V-speeds but true airspeed in the ODE?

## 2. Units and configuration (`units.py`, `config.py`, `model.py`)

- [ ] Find where every input is converted to ft–slug–s (only `model.build_model`).
- [ ] Open `aircraft/generic_widebody_synthetic/aircraft.yaml` and find each number in
      `build_model`.
- [ ] Try `load_config("generic_widebody_synthetic", overrides={"multipliers.k_CL": 1.1})`.

**Be able to answer**
- [ ] What is a slug and why use it? (m = W/g₀ with W in lbf.)
- [ ] What do k_CL and k_CD scale, and what do they *not* scale (the increments)? Why?
- [ ] Why is the synthetic aircraft labelled synthetic everywhere?

## 3. Atmosphere (`atmosphere.py`)

- [ ] Compute σ at 5,000 ft ISA and on a 100 °F day at sea level.

**Be able to answer**
- [ ] Why does a hot or high airport need more runway? (Lower ρ → higher true-airspeed
      stall and rotation speeds; less thrust if the table depends on temperature.)

---

## 4. Runge–Kutta integrators (`integrators.py`, `docs/methods/runge_kutta.md`)

- [ ] Read `rk4_step` and write the four stages from memory.
- [ ] Read `dp45_step`: find the 5th-order weights, the error estimate and FSAL.
- [ ] Read the step-size controller in `integrate` (accept/reject, the `en ** -0.2`).
- [ ] Run `pytest tests/test_integrators.py -v` and read each test.
- [ ] Change `dt` in `test_rk4_order_is_four` and watch the error ratio stay ~16.

**Be able to answer**
- [ ] Local vs global error order for RK4, and why they differ by one.
- [ ] Why does halving h reduce the RK4 error by ~16? How do you *measure* the order
      (log–log slope, ratio of successive errors)?
- [ ] How does RK45 estimate its own error without a reference solution?
- [ ] Why the exponent −1/5 in the step-size update? What are the safety factor and the
      0.2 / 5 limits for?
- [ ] What is FSAL and what does it save?
- [ ] What does "local extrapolation" mean (propagating the 5th-order solution)?
- [ ] Why integrate in **segments** split at every procedural switch? (Discontinuous
      RHS inside a step destroys the high order.)
- [ ] Why did we compare against scipy, and why is scipy not allowed in `src/`?

## 5. Event location (`integrators.py`, `phases.py`, `docs/methods/event_location.md`)

- [ ] Read `locate_in_step`: find φ(s) and where the partial RK step is re-taken.
- [ ] Read the event builders in `phases.py` (`airspeed_event`, `liftoff_event`,
      `screen_event`, `stopped_event`, `touchback_event`).
- [ ] Read `state_at_airspeed` (binary search on the cached roll, then locate in the step).

**Be able to answer**
- [ ] Why not linearly interpolate between steps to find an event?
- [ ] What does the `direction` of an event do? Why does a step that *starts* on g = 0
      not count as a crossing?
- [ ] Why is touchback `h + 0.01 ft` and not `h`?
- [ ] Why can the inner V_EF solve be so cheap? (The all-engines roll is cached.)

## 6. Root finding (`rootfind.py`, `docs/methods/root_finding.md`)

- [ ] Derive the secant update by replacing f' with a difference quotient.
- [ ] Read `safeguarded_secant`: find the bracket update, the bisection fallback and
      the stall check.
- [ ] Run `pytest tests/test_rootfind.py -v`.
- [ ] Print `result.v1_solver_history` and watch |d_go − d_stop| shrink.

**Be able to answer**
- [ ] Why the secant method and not Newton? (No derivative of "a whole simulation".)
- [ ] What is its convergence order, and where does the golden ratio come from?
      (e_{k+1} ≈ C e_k e_{k−1} → p² = p + 1.)
- [ ] When can plain secant fail, and how does the safeguard fix it?
- [ ] Name all four root solves in the code and their unknowns: event time s, V_EF,
      V1, k_VR.
- [ ] What happens if f(V1) has no sign change? (Unbalanced; which distance governs.)
- [ ] Why is the V1 tolerance 0.05 ft and not 1e-12? (Physical meaningfulness vs cost;
      each evaluation is two full simulations.)

## 7. Interpolation (`tables.py`, `docs/methods/interpolation.md`)

- [ ] Derive the natural-spline tridiagonal system (continuity of p').
- [ ] Read `thomas_solve` and count its operations (O(n)).
- [ ] Run `pytest tests/test_tables.py -v`.
- [ ] Look at *Aircraft data* in the app to see the tables the solver actually uses.

**Be able to answer**
- [ ] Linear vs natural cubic spline: accuracy, smoothness, overshoot.
- [ ] Why is linear the default? (No overshoot of CLmax; the difference here is 0.03 ft.)
- [ ] Why does the Thomas algorithm need no pivoting here? (Diagonal dominance.)
- [ ] What happens on an out-of-range query? (Error by default; optional clamp + warning.)
- [ ] How does bilinear interpolation work on the 2-D thrust table?

---

## 8. The procedure and the nested solves (`takeoff.py`, `bfl.py`)

- [ ] Read `aeo_ground_roll`, `engine_failure_prefix`, `simulate_go`, `simulate_stop`,
      `rotate_and_climb` in that order.
- [ ] Read `_solve` (outer V1 solve), `compute_bfl`, `_k_vr_for_v2` and
      `takeoff.oei_v2_from_vr`.
- [ ] Set `procedure.enforce_v2_min: false` and compare the results.

**Be able to answer**
- [ ] Draw the structure: V2 rule (k_VR, cheap) first; then V1 → V_EF → branches →
      event solves.
- [ ] Why does V2 depend on VR only, and not on V1? (From VR on, the go branch is
      one-engine-out from the same speed; the equations don't depend on x or t.)
      When would that stop being true? (Time-varying wind/gusts.)
- [ ] The stop sequence: brakes at V1, idle at +1 s, spoilers at +2 s, then +2 s × V1
      allowance. Where is each in `simulate_stop`?
- [ ] Rotation: θ ramps at 3°/s to tail-strike − 1°. What if lift-off happens before
      the target pitch? (Keeps rotating in the air.)
- [ ] Why must V2 ≥ 1.2 V_S, and why does raising VR fix it? Why does the BFL go up
      when it is enforced (9,280 → 9,930 ft)?
- [ ] What is a touchback, and what does the code do about it (k_VR += 0.01, retry)?
- [ ] Why no reverse thrust credit? (Part 25 dry-runway accelerate-stop rule.)

## 9. Verification (`tests/`, `scripts/make_verification_figures.py`)

- [ ] Run `pytest` (all should pass) and `python scripts/make_verification_figures.py`.
- [ ] Re-derive the analytic ground roll x(V) = m/(2B)·ln(A/(A − BV²)) (equations.md §7).
- [ ] For each figure in `output/verification/`, write one sentence on what it proves.

**Be able to answer**
- [ ] How do you know the simulator is right? (Exact ODE solutions, observed order,
      scipy agreement, analytic ground roll, step-size independence, physics
      direction checks.)
- [ ] What does "step-size independence" mean, and what number did we get? (~4e-10.)
- [ ] Which results would change if the data were real instead of synthetic, and which
      would not? (The numbers change; the methods and their verification do not.)

## 10. The app (`app/`), lightly

- [ ] `compute.py`: how results are cached (`lru_cache` on the config JSON) and why the
      heatmap runs in a process pool.
- [ ] `figures.scene`: frames are pre-computed by interpolating each trajectory at
      fixed times.

**Be able to answer**
- [ ] Why does the app use RK45 for the sweep and heatmap? (25 full solves; RK45
      matches RK4 to hundredths of a foot.)

---

## Likely "gotcha" questions

- [ ] "Isn't the BFL just where two lines cross, so why not plot and read it off?"
      (Each point on those lines is two full simulations. The secant method finds the
      crossing in ~6 evaluations, to 0.05 ft, without drawing the curve.)
- [ ] "Why is your aircraft's BFL ~9,900 ft? Is that realistic?" (Synthetic data with
      big-jet magnitudes; plausible order of magnitude, not a real airplane.)
- [ ] "Why does lift matter more than drag in the heatmap?" (k_CL changes CLmax → V_S →
      VR and V2: every speed in the procedure moves.)
- [ ] "What's the biggest modelling simplification?" (Point mass with prescribed pitch;
      no ground effect; constant friction coefficients; steady wind.)
- [ ] "What would you do next?" (Real aircraft data; ground effect; gusts as a
      stochastic wind model (Phase 3); wet-runway rules.)

## Suggested order

Day 1: §0, §1, §4. Day 2: §5, §6, §8. Day 3: §7, §9, the gotchas. Explain each
section out loud to someone (or to a rubber duck). If you stumble, that's the part to
re-read.
