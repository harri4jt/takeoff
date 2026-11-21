# Assumptions and glossary

The tool is a **conceptual-design runway estimator**: the kind of estimate a
performance engineer makes before certified, flight-test-calibrated data exist. Each
section below says what was chosen and why. The short list of what is *not* modelled is
in [Questions and answers](faq.md#q-not).

## Glossary: the takeoff speeds

| Speed | Name | What it means here |
|---|---|---|
| **V_S** | stall speed | `sqrt(2W/(ρ S CLmax))` in the takeoff configuration. The reference that the other speeds are scaled from. CLmax is the table's maximum CL, unless `aero.CLmax` in aircraft.yaml gives one for the configuration (e.g. from certified stall speeds, as for the 747). Either way it is times k_CL. |
| **V_mcg** | minimum control speed, ground | The lowest speed at which the rudder alone can hold the aircraft straight after an engine fails. It is optional. When given, it is the lowest V1 allowed. |
| **V_EF** | engine-failure speed | The speed at which the engine **actually fails**. It is *not* the same as V1. |
| **V1** | decision speed | The speed by which the pilot has **recognised** the failure and takes the first action (brakes if stopping). Below V1 the crew stops; at or above V1 it continues. |
| **VR** | rotation speed | The pilot starts pulling the nose up at VR. Here `VR = k_VR·V_S`, default 1.10, raised automatically if needed to meet the V2 rule (below). |
| **V_LOF** | liftoff speed | The airspeed when the wheels leave the ground (N = 0). |
| **V2** | takeoff safety speed | The airspeed at the 35 ft screen height, one engine out. Part 25 requires V2 ≥ V2_min = 1.2 V_S (the classic rule; the current rule is 1.13 V_SR with a 1-g stall speed). **Enforced** by default (see below). |

**Why V_EF and V1 differ:** the pilot needs time to notice the failure. The
regulations assume that time is about one second (`t_recog`, default 1 s). The engine
fails at V_EF, the aircraft keeps accelerating on the remaining engines for t_recog,
and it reaches V1. That is why V_EF < V1 in every result. With `t_recog = 0` the two
are equal. V_EF can never fall below the speed at brake release. If V1 is so low that
the aircraft passes it within t_recog even when the engine fails at brake release, the
solver stops with an error rather than inventing a failure before the takeoff starts.

## Modelling choices

### Airspeed or ground speed for V1? → airspeed (KEAS ≈ KCAS)

On an airliner, every V-speed is read off the **airspeed indicator**. The flight
manual lists V1, VR and V2 in knots calibrated airspeed (KCAS). Stall and control are
aerodynamic, so they depend on airspeed, not ground speed. In this tool:

* The inputs and outputs are **equivalent airspeed in knots (KEAS)**. At takeoff Mach
  numbers (< 0.3), KEAS and KCAS differ by well under 1 kt, so KEAS stands in for
  KCAS. The difference would need a pitot-static position-error correction, which we
  don't model.
* Internally, the events "reach V_EF / V1 / VR" compare **true airspeed** against
  `V_EAS/√σ`. This is equivalent to evaluating the stall formula with field density.
* The Part 25 **2-second distance allowance** is a *distance*, so it uses the
  **ground speed** at V1: `2 s × V1_ground`. With no wind the two are the same.
* Consequence: a headwind lets the aircraft reach a given airspeed at a lower ground
  speed, so it needs less runway. That is the expected result.

### True or equivalent airspeed for V_S? → defined in EAS, simulated in TAS

`V_S = sqrt(2W/(ρ S CLmax))` with the *field* density gives the true-airspeed stall
speed at that field. Multiplying by `√σ` gives the equivalent-airspeed stall speed,
which is the same at every altitude. That is the number an engineer would quote. Both
views are the same physics. The code compares like with like everywhere.

### Liftoff before θ_target → keep rotating in the air

The aircraft keeps pitching up at the rotation rate after liftoff until it reaches
θ_target = θ_tailstrike − 1°, then holds that attitude.

### Do k_CL and k_CD scale the spoiler / engine-out / chute increments? → no

The multipliers represent "a better or worse **airframe**". For example, k_CL = 1.1
means 10% more lift from the wing and flaps everywhere, including CLmax. The
increments model **devices and failures**, which are separate hardware:

* **Spoilers** are panels on top of the wing that pop up during a rejected takeoff.
  They destroy lift (ΔCL < 0), which puts weight on the wheels so the brakes work
  better, and they add drag (ΔCD > 0). They matter only in the stop branch.
* **Engine-out drag (ΔCD_eo)** lumps together the windmilling dead engine and the
  rudder/aileron deflection needed to fly straight with asymmetric thrust. It is
  applied from V_EF onwards in both branches.
* **Drag chute** is a parachute. Transports don't use them and Part 25 gives them no
  credit, so a civil run that uses one is flagged. Military rules may credit it.

If you want, set the increments to 0 in `aircraft.yaml`; they are optional.

### V2 ≥ 1.2 V_S → enforced by raising VR

Part 25.107 says V2 must be at least 1.2 V_S, and VR must be chosen so that V2 is
reached by 35 ft with one engine out. An airframer meets this by **scheduling VR**.
Rotating later means lifting off faster and so arriving at 35 ft faster. So the tool
does the same thing:

1. Solve the BFL at the configured `k_VR` (default 1.10).
2. If V2/V_S < 1.2, find the smallest `k_VR` with V2/V_S = 1.2 by a safeguarded
   secant solve. From VR onwards the continued takeoff is always one-engine-out and
   starts at the same airspeed, and nothing in it depends on where along the runway it
   is or on V1. So V2 depends on VR alone, and each function evaluation only has to
   simulate rotate → lift-off → 35 ft. The BFL is then solved once at that k_VR. (A
   time-varying wind would couple them again; it is not modelled.)

For the 747-100 at 710,000 lb this moves k_VR from 1.100 to 1.154 and the BFL from
8,454 ft to 9,104 ft: the price of the safety margin. Turn it off with
`procedure.enforce_v2_min: false` (or the checkbox in the app) to see the unconstrained
result, which is then flagged with a warning. The ratio is `procedure.v2_min_ratio`
(default 1.2). On top of this, the rotation-speed optimizer may raise VR further when
that shortens the field ([Rotation speed](rotation_speed.md)).

### Other assumptions

* **No reverse thrust credit** (Part 25 dry-runway rule). The operating engines go to
  idle 1 s after V1. The failed engine stays at zero thrust and keeps its drag
  increment.
* **Weight.** Constant (`m = W/g₀`) unless the engines have a TSFC
  (`engines.tsfc_per_hr`, or a `tsfc_per_hr` column in the thrust CSV). Then the fuel
  burned is an extra state, `df/dt = TSFC·T/3600` for the operating engines, and
  `W = W₀ − f`. The V2 rule's rotate-and-climb shortcut starts at the brake-release weight,
  which is a negligible difference.
* **Point-mass, longitudinal model.** No pitch dynamics: θ is *prescribed* (constant,
  then a ramp at the rotation rate, then held). No lateral or directional dynamics.
* **Ground effect** is optional (Raymer, drag only; see `ground_effect.md`). By default the
  aero table is used as given.
* **Flat-ground airborne segment** (see `equations.md` §5).
* **Steady headwind** only. Gusts and wind shear are not modelled (the `WindModel`
  interface in `environment.py` is where they would go).
* **Thrust** is read from the table at the true airspeed and the actual temperature,
  but **not lapsed with altitude**: the tables are sea-level tables. Elevation changes
  the air density (lift, drag, true airspeeds) only, so high-elevation results are
  optimistic unless the table is for that altitude.
* **Landing** is a separate simulation with its own weight, flaps and stopping devices
  (see [Landing](landing.md)). Constant weight; reversers at a fixed fraction of maximum
  thrust until the stop.
* **Friction** is a single coefficient: μ_roll before brakes, μ_brake after. Anti-skid
  enters only through the value you choose (the app's runway-condition presets use
  MIL-STD-3013 Table II). Brake-energy and tire-speed limits are not enforced. The
  model reports the maximum ground speed on the tires and the brake energy of the
  rejected takeoff, and the app warns against the reference aircraft in
  `app/reference_aircraft.yaml`.
* **Rule set.** An aircraft setting (`certification.rules`): Part 25 for the 747,
  MIL-STD-3013 for the SR-71. MIL-STD-3013 changes only procedure values (delay, pad,
  50 ft, no 1.15 factor, chute optional). See `field_length_rules.md`.
* **Rotation speed.** The VR (at or above the lowest legal one) that minimizes the field
  length: `procedure.optimize_vr`, on by default. Set it to false for the lowest legal
  VR. See `rotation_speed.md`.
* **Thrust** lookups use `max(V_a, 0)`. With a tailwind at brake release the airspeed
  is briefly negative.
* **Uphill slope.** At a fixed V1, the slope makes the *acceleration to V1* longer, so
  the **total** accelerate-stop distance can grow even though the deceleration after
  V1 is shorter. The tests check the stop portion after V1 (`stop_after_v1_ft`), which
  is where the slope helps.

## Reading the animation

* Both outcomes of the *same* engine failure are drawn on one runway. Until the engine
  fails the two aircraft are identical (the blue one is drawn on top).
* The **orange dotted line** marks where the engine fails (V_EF). The **black dotted line**
  is V1, about 1 s later.
* The **red line** is the BFL. The go aircraft crosses 35 ft exactly there. The stop
  aircraft halts about 500 ft short because the stop distance includes the
  2-second allowance (2 s × V1), a regulatory pad that is added on paper but not flown.
  It is shown as the orange box on the runway.
* The **green line** is the FAA field length, max(BFL, 1.15 × all-engines distance).
  Switch the animation to **All engines** to see the normal takeoff and the 15 %
  margin that leads to it.
* The runway strip below is drawn to the same horizontal scale, with real-world
  distances for comparison (`app/reference_runways.yaml`; they are context only and
  should be double-checked before being quoted).
* Heights are exaggerated (×25 by default, in ⚙ settings); otherwise 35 ft would be a
  1-pixel bump over a 10,000 ft runway.
* **Landing** mode starts at 50 ft over the threshold. The runway strip marks the landing
  distance, the landing runway required (Part 121: ÷ 0.6) and, dotted, the takeoff field
  length, so you can see at a glance which one sets the runway.
