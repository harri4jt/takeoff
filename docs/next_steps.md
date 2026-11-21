# Answers to docs/questions + plan (2026-11-20)

## Answers

**1. V_mcg.** It is used, in one place: `src/bfl/bfl.py:69`. When `speeds.V_mcg_kts` is set,
it becomes the **lowest V1 the secant search may try** (V1_min). Without it, V1_min =
0.6·VR. It changes the answer only when the balanced V1 would otherwise fall below V_mcg,
which is rare for a 747 (balanced V1 ≈ 146 kt vs V_mcg 106 kt). Then V1 is clamped to V_mcg
and the field is unbalanced. So yes: for the current aircraft it is effectively a guard rail,
not something that moves the number.

**2. t_recog = 1 s and the 2-s allowance.** These are two separate Part 25 items:
- `t_recog_s = 1 s` (V_EF → V1) is the conventional Part 25 assumption: §25.107(a)(2)
  makes the gap between V_EF and V1 the time to recognise the failure, and AC 25-7 uses
  1 s as the usual flight-test value. It is a default, not a hard rule.
- `t_v1_allowance_s = 2 s` (§25.109(a)(1), amendment 25-92) is a **distance pad**: 2 s at
  V1 ground speed is added to the accelerate-stop distance. It covers the crew being slower
  in service than in flight test. It does **not** stand in for the recognition time; that
  is already modelled. The 2 s is extra on top of it.
- MIL-STD-3013 does this differently: a single **3-s** delay from engine failure to brakes
  on, with no extra distance pad (see 3).

**3. Military (MIL-STD-3013) vs Part 25.** Feasible: about one solid work session.
Your PDF is the **original 14 Feb 2003 MIL-STD-3013** (it supersedes MIL-C-5011A), not
3013A/B. The takeoff sections we need (3.2.x) are probably very close in B. I'd build from
this version and note that. If you can find B, I'll diff those sections.

What changes under the military rules (3.2.10–3.2.14):

| | Part 25 (current) | MIL-STD-3013 CFL |
|---|---|---|
| Name | Balanced field length | Critical field length (CFL), speed V_CEF |
| Failure → action | V_EF, +1 s recognition → V1, then brakes/idle/spoilers stagger | engine fails at V_CEF, **3 s** OEI acceleration, then brakes instantly, thrust to idle, devices deploy |
| Distance pad | +2 s at V1 | none |
| Go branch ends at | **35 ft** screen height | **lift-off** (CFL is "accelerate to lift-off OEI or stop") |
| Lift-off speed | VR from k_VR·V_S, V2 ≥ 1.2 V_S | V_LO = max(1.1 V_S (out of ground effect), …); obstacle speed 1.2 V_S at **50 ft** |
| AEO takeoff distance | ×1.15 factor | to **50 ft**, no factor |
| Chute / reverse | no credit | allowed (with approval). The SR-71 chute becomes legitimate |
| Friction | user μ | defaults: roll 0.025 (bias) / 0.015 (radial), brake 0.30 (no anti-skid) / 0.38 (anti-skid) |
| Min V_CEF | — | ≥ V_mcg |

Because the military go branch stops at lift-off, it avoids the slow OEI climb-out
that kills the SR-71 case. **My guess is the SR-71 will balance under MIL rules,** chute
or not, but I need to run it to know. (The current 30,494 ft is mostly the 70-s
OEI creep from 185 to 204 kt *before* lift-off, so it may still not balance at
140 klb. Lighter weights very likely will.)

*Ground effect.* The 3013 method is the "E-ratio" blend: compute E(h/b) on the wheels and at
height, then CL = CL_OGE(1−E2/E1) + CL_IGE·E2/E1 (same for CD). It needs **both** an IGE and
an OGE table, which a conceptual-design user usually won't have. Agreed that it isn't a
good fit. The Raymer alternative (Raymer §12.6, from the Wieselsberger/McCormick
induced-drag factor) needs only the free-air polar plus span and wing height:

  K_eff/K = (33·(h/b)^1.5) / (1 + 33·(h/b)^1.5),  applied to the induced part of CD

and optionally a lift-slope increase. It works for any aircraft with one free-air table, so
it fits the "single aero table" philosophy. Proposal: optional `ground_effect:` block in the
YAML (`method: none | raymer`, `span_ft`, `wing_height_ft`, `CD0` or auto-split of the
polar), off by default. It would apply under **both** rule sets. Note that 3013's V_LO rule
(a) uses the *out-of-ground-effect* stall speed, which the code already does.

*SR-71 drag.* **Drag was not digitized.** The flight manual has no low-speed drag polar.
Only two things were digitized: **lift**, from Fig. 6-2 "Wing lift vs angle of attack"
(in and out of ground effect), and **thrust**, from Fig. 1-3 (max A/B, five temperatures).
Drag is an estimate: `CD = 0.028 + CL·tan(α_ind − α0)` (slender delta, no leading-edge
suction; CD0 = 0.018 clean + 0.010 gear). See `aircraft/sr71/README.md` note 5 and
`tools/make_sr71_tables.py`. The scans are on the Internet Archive (item
`0003756-lockheed-sr-71-03`) but are no longer on disk. I'd re-download them to make crops
for the SR-71 data page (item 4).

**4. Data pages.** Yes, see plan step C.

**5. ISP / fuel burn.** The thrust tables are **thrust only**: airspeed (and OAT for the
SR-71) → lbf. There is no fuel-flow or ISP column. If we add a TSFC (or fuel-flow) column, or
one scalar TSFC per aircraft, mass becomes a state: `dm/dt = −TSFC·T/g₀`. Rough size:
- 747 (4 × ~45 klb, TSFC ≈ 0.35 /hr): ~18 lb/s × ~45 s ≈ 800 lb of 710,000 (0.1%): negligible.
- SR-71 (2 × ~30 klb in max A/B, TSFC ≈ 2 /hr): ~33 lb/s. Over the ~70-s OEI creep that is
  ~1.5–2 klb (~1%). Small but not zero, and it helps exactly the marginal case.
Easy to add (one more state, or W(t) from cumulative thrust). Low priority; worth it for
afterburning or rocket-assisted concepts.

**6. "Flat-ground airborne segment."** Yes. After lift-off, height is measured above the
lift-off point as if the ground continued flat. With runway slope, "35 ft" is strictly
relative to that extended plane, not the sloped runway. With slope = 0 (your use case) there
is no approximation at all.

**7. Anti-skid / brake-energy limits.** That note means the model applies μ_brake·N with no
upper bound from the hardware:
- **Anti-skid** (μ 0.38 vs 0.30 in 3013's table) lets brakes run near the friction peak
  without locking wheels. Today it is folded into the single μ_brake you choose.
- **Brake energy:** brakes can only absorb so many megajoules (the "max brake-energy speed"
  V_MBE in airliner AFMs). A high-weight, high-V1 rejected takeoff can exceed it, which
  limits V1. Distinct from:
- **Tire speed limit** (e.g. 225 mph / 195 kt ground speed for many transport tires).
  Your idea fits: report max ground speed (and the brake energy absorbed in the stop, which
  is easy to integrate) and warn if it passes a user limit. Parked for later, as you said.

**8. RK45.** Benchmarked today (full BFL solve, this laptop):

| aircraft | RK4 dt 0.01 | RK4 dt 0.05 | RK4 dt 0.1 | RK45 rtol 1e-8 |
|---|---|---|---|---|
| synthetic | 0.97 s | 0.14 s (Δ 0.000 ft) | 0.08 s (Δ 0.001 ft) | 0.06 s (Δ 0.02 ft) |
| 747-100 | 0.66 s | 0.14 s (Δ 0.000 ft) | 0.07 s (Δ 0.002 ft) | 0.07 s (Δ 0.003 ft) |
| SR-71 | 0.71 s | 0.15 s (Δ 0.000 ft) | 0.08 s (Δ 0.000 ft) | 0.04 s (Δ 0.03 ft) |

Both are far more accurate than the data (hundredths of a foot on a ~10,000 ft answer).
RK45 at rtol 1e-8 is ~10–15× faster than today's default and about as fast as RK4 at
dt 0.1. Loosening RK45 to 1e-6 starts to cost ~1.5 ft, so keep 1e-8.
**Recommendation:** make **RK45 (rtol 1e-8) the default**, and keep RK4 as the selectable
"reference" method (it's what the verification figures and class narrative use). One catch:
RK45 takes big steps, so the animation, which linearly interpolates the trajectory,
could look coarser. Fix by sampling the trajectory on a fixed time grid with the
integrator's own step interpolation, or by re-running the displayed case with RK4 dt 0.05.

**9. YAML inputs.**
- `theta_ground_deg`: the angle of attack **of the aero table's α reference line** while
  sitting on the runway (wheels down, no wind). It is not wing incidence by itself. It is
  incidence *plus* any nose-up tilt of the fuselage on its gear, measured in the table's α frame. For the
  747 the fuselage sits level and the tables use the wing reference plane, which is 2°
  above the fuselage line, so 2° there *is* the wing incidence. For a conceptual-design
  table referenced to the wing, it reduces to "wing incidence + fuselage ground pitch".
- `thrust_incidence_deg`: angle of the thrust line **relative to the same body/table
  reference line** (not the ground, not the wing specifically). The model uses ε = α + incidence
  for the thrust angle to the flight path, so on the runway the thrust points
  theta_ground + incidence above horizontal.
- Aircraft builder page: yes, see plan step D. Upload a YAML → form fills in; drop CSVs → they
  become selectable tables; validate live with the same pydantic model; download a zip
  (yaml + csvs) to hand to someone else.
- Spoilers: noted, unchanged.

**10. Aero tables.** There is effectively **one table in use**. `aero.configurations` can
list several, but the solver only ever reads `takeoff_configuration`, for the whole run:
ground roll, rotation, climb-out *and* the rejected-takeoff stop. Braking-phase changes are
**increments** added on top of that one table (spoiler ΔCL/ΔCD, engine-out ΔCD, chute
drag). The 747 lists flaps 10 and 20 and the SR-71 lists IGE and free air only so you can
switch which one is "the" takeoff table. That matches your conceptual-design picture:
one takeoff table, tuned with k_CL/k_CD. In the builder I'd present it as
"one takeoff table (+ optional alternates)".

**11. Class demo → design tool.** Noted. Plan step E lists what I'd strip or move behind
an "education" toggle. Nothing is removed until you say so.

## Round 2 findings (2026-11-20)

**CFL end point: lift-off or 50 ft?** Both public revisions I can read say **lift-off**:
- MIL-STD-3013 (14 Feb 2003) §3.2.10 and **MIL-STD-3013A (9 Sep 2008)** §3.2.10 have identical
  text: "...plus the distance to accelerate to **liftoff speed** with the critical engine
  inoperative or to decelerate to a stop..." §3.2.11 (V_CEF): "the same distance is required
  to either **liftoff** or stop". The 3-s rule (§3.2.10.1) is also unchanged in 3013A.
- The **50 ft** in 3013 is the *total takeoff distance* (§3.2.8, all engines, gear down, to
  clear 50 ft at V_obs). That is probably where the "50 ft" you remember comes from. It is
  also the Part 23/military AEO convention.
- **3013B is dated 1 Sep 2022** (DLA ASSIST, active, AFLCMC lead). It is not on everyspec,
  and I couldn't get the text. A 2025 MDPI paper describes 3013B's CFL as the *maximum* of
  AEO takeoff, accelerate-stop and accelerate-go distances. That hints B may have changed
  the definition, so we need the document itself. **Please grab 3013B** (ASSIST QuickSearch,
  distribution A) and drop it in `~/Downloads`.
- Either way the code is the same: `procedure.go_end: liftoff | obstacle` and
  `procedure.screen_height_ft` (35 for Part 25, 50 for MIL). The 3013B preset follows whatever
  B says.

**Zero increments.** Yes: `delta_CD_engine_out`, `spoilers.delta_CL/delta_CD` all default to
0 and 0 is valid. They are aircraft properties, so they apply under either rule set. Under
3013 spoilers are just another "deceleration device" (they deploy after the delay). Zero
engine-out ΔCD is slightly optimistic for the go case; zero spoilers is conservative for
the stop.

**SR-71 drag source to try first:** NASA TM X-3532 (Arnaiz, 1977) has flight-derived YF-12
drag polars. If it has low-Mach points, use it to anchor CD0/K. Otherwise adjust the estimate
modestly and label it as an assumption.

## To-do list (round 3, agreed scope)

Decisions since round 2: YF-12 data is an acceptable SR-71 substitute. The MIL go branch
ends at the **50 ft** obstacle for now (revisit when 3013B arrives). Friction stays a user input
with 3013 presets. Raymer ground effect changes drag only. Fuel burn, tire/brake warnings and
the design-tool cleanup move into scope. A new k_CL × k_CD trade-study page is added.

**A. RK45 default** (small)
- [x] `solver.method` default `rk45` (rtol/atol 1e-8); remove the UI toggle.
- [x] Animation: re-run the displayed branches at the solved V1 with RK4 (fixed dt) for
      evenly spaced frames. RK4 stays for this and for the verification tests/figures.
- [x] Test: RK45 vs RK4 dt 0.01 BFL within 0.5 ft for all three aircraft.

**C. Validation data pages** (medium)
- [x] `tests/test_validation.py` writes figures + `status.json` (pass/fail, max error,
      tolerance, date, git hash) to `app/assets/validation/<aircraft>/`.
- [x] 747: field length within +0/+12% of Boeing D6-58326. Page lists likely reasons for
      the gap. No tuning.
- [x] SR-71: VR/V_LOF within ±10 kt of YF-12's ~180/200 KIAS.
- [x] Pages `/data/b747`, `/data/sr71`: citation, source crop → digitized curve
      (lift / drag / thrust), validation plot, status badge (flags missing/stale).
- [x] SR-71: re-download the manual scans for crops. Use YF-12 drag (NASA TM X-3532 or
      similar) if a low-speed polar exists; otherwise adjust the estimate and label it.

**B. Rule set: Part 25 vs MIL-STD-3013B** (large)
- [x] `procedure.rules: part25 | mil3013`. Each preset value stays overridable:

      | | part25 | mil3013 |
      |---|---|---|
      | recognition delay | 1 s (V_EF→V1) | 3 s (V_CEF→brakes), editable |
      | distance pad | 2 s at V1 | none |
      | go branch ends at | 35 ft | 50 ft (`go_end`/`screen_height_ft`) |
      | AEO factor on field length | 1.15 | 1.0 |
      | chute / decel devices | no credit | optional, **default off** (checkbox) |
      | speed minimums | V2 ≥ 1.2 V_S | V_LO ≥ 1.1 V_S, V_obs ≥ 1.2 V_S |

- [x] Labels BFL/V1/V_EF ↔ CFL/V_CEF; report refusal speed.
- [x] Runway condition dropdown (Dry / Wet / Wet snow / Wet ice + anti-skid checkbox) fills
      μ_roll / μ_brake from 3013 Table II. The fields stay editable; editing one shows "Custom".
      Available under both rule sets.
- [x] In-app page "Field-length rules: Part 25 vs MIL-STD-3013" with section citations.
- [x] SR-71 under MIL rules, with and without chute; update its README.
- [x] Tests: MIL preset ≡ Part 25 with matching manual overrides; SR-71 MIL result finite.

**B2. Raymer ground effect, drag only** (medium)
- [x] YAML `ground_effect: {enabled, span_ft, wing_height_ft, CD0?, K?}`. If CD0/K are not
      given, fit `CD = CD0 + K·CL²` to the takeoff table (fit + R² shown).
- [x] `CD = CD_table − (1 − φ)·K·CL²`, φ = 33(h/b)^1.5/(1+33(h/b)^1.5) (Raymer Eq. 12.61),
      h = wing height + airborne height. Both rule sets. Off by default; 747 what-if on its page.
- [x] In-app explainer page (the fit, the factor, φ vs h/b plot).

**F. Fuel burn** (small–medium)
- [x] Optional `engines.tsfc_per_hr` (scalar) or a `tsfc_per_hr` column in the thrust CSV
      (overrides the scalar; lets afterburner tables carry their own). Mass becomes a state:
      `dW/dt = −TSFC·T/3600` (operating engines only; idle uses the same TSFC).
- [x] Report fuel used to lift-off / 35-50 ft / stop. Not set → constant weight, as today.
- [x] SR-71 and 747 TSFC values, cited (or flagged as estimates).

**G. Reference-aircraft limits and warnings** (medium)
- [x] Placeholder values for ~3 aircraft (marked as placeholders). Editable file `app/reference_aircraft.yaml` (like `reference_runways.yaml`), one entry per
      aircraft, any subset of: `tire_speed_limit_kts`, `max_brake_energy_MJ`,
      `field_length_ft`, … Example: `747-100: {tire_speed_limit_kts: 195, …}`.
- [x] New outputs: max ground speed (on the ground, either branch) and brake energy absorbed in
      the rejected takeoff (∫ μN·V dt, plus the per-wheel figure if the wheel count is given).
- [x] Warnings generated from the file: "Tire speed 201 kt exceeds 747-100 (195 kt)". You choose
      which entries act as warnings; the rest are comparison only.
- [x] "Scale" strip per metric: reference aircraft as ticks, your design as a marker.

**H. Trade-study page (replaces the "Aero sensitivity" tab)** (medium)
- [x] Separate page, run with its own button: k_CD on x, k_CL on y, user-set range and grid
      (default 0.75–1.25, 11×11). Parallel RK45, ~1–2 s per map.
- [x] Filled contour, either viridis or **banded levels** with user-editable thresholds
      (e.g. green < 6,000 ft, yellow 6,000–8,000, red 8,000–10,000, grey above). Hover shows exact
      value; baseline (1,1) marked; cells with no solution hatched.
- [x] Metric dropdown: BFL / CFL, field length (with AEO factor), AEO distance.
- [x] **Multiple thrust tables:** `engines.thrust_tables: {name: csv}` (the current single
      `thrust_table` still works). The main page gets a thrust-table selector; the trade
      study draws one map per table, side by side, on a shared colour scale.
- [x] **Multiple aero and/or thrust tables:** one map per (aero, thrust) combination, capped
      at 6 maps, on a shared colour scale. Tables come from the aircraft's lists or uploads.
- [x] Base case = main page settings. A short "Trade-study overrides" panel changes only the
      common inputs (TOGW, runway condition/friction, temperature, elevation, wind, rule set).
      Everything else is inherited, which keeps the page simple.
- [x] Save image via the Plotly modebar (PNG, high-res set in config); export the grid as CSV.

**E. Design-tool cleanup** (with G/H)
- [x] Move numerical-methods pages under an "About the method" section. Keep them, but take
      them out of the main nav.
- [x] Remove the method toggle (A) and the old sensitivity tab (H); keep V1-trade and
      forces/speeds plots behind "details".
- [x] Synthetic aircraft stays as a test fixture but is hidden from the selector unless
      a "show examples" option is on. 747 / SR-71 stay as validated examples.
- [x] Final pass for clutter once everything above is in.

**D. Aircraft builder page** (medium–large; last because B2/F/G/H add YAML fields)
- [x] Form generated from the pydantic models (units/descriptions from Field metadata).
- [x] Upload YAML → populate. Upload CSVs (aero, one or more thrust) → validate, plot,
      offer as selections.
- [x] Live validation; download .zip; save to `aircraft/` (appears in the selector).

**Order:** A → C → B → B2 → F → G → H (+E) → D.

## Status (2026-11-20, all of the above implemented)

Everything in the round-3 list is in, except as noted:

- **MIL go end point** is 50 ft (`screen_height_ft`), pending the 3013B text. The
  2003/2008 text says lift-off; see `docs/field_length_rules.md`.
- **SR-71 drag** was *not* adjusted. It cannot balance for structural reasons (tiny
  engine-out excess thrust), even with 30 % less drag, and no YF-12 low-speed polar was
  found (TM X-3532 is the XB-70). Documented in its README and data page.
- **747 tolerance** is ±12 %, not +0/+12 %: the 500 klb point is −4.3 % (Boeing's curve
  flattens there). This was already true before these changes; not tuned.
- **Reference aircraft limits** are placeholders (`app/reference_aircraft.yaml`).
- **E cleanup:** sensitivity tab and integrator toggle removed, methods pages grouped under
  "About the method", synthetic aircraft hidden behind a checkbox, 747 is the default.
  Further stripping is still open for discussion.
