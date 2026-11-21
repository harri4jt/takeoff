# Questions and answers

**Results**
[What does "runway required" mean?](#q-runway) ·
[BFL, takeoff field length, all-engines distance: which do I use?](#q-which) ·
[Why is the field "unbalanced"?](#q-unbalanced) ·
[Why is VR higher than 1.1 V_S?](#q-vr) ·
[Is landing a concern for my design?](#q-landing) ·
[What do the warnings mean?](#q-warnings)

**Inputs**
[What is the least data I need for an aircraft?](#q-minimum) ·
[What do k_CL, k_CD and k_T do?](#q-multipliers) ·
[How do I model a wet or icy runway?](#q-wet) ·
[How are elevation and temperature handled?](#q-altitude) ·
[Civil or military rules?](#q-rules) ·
[Should I turn ground effect on?](#q-ge) ·
[Which airspeed are the V-speeds?](#q-airspeed)

**Using it**
[How do I run many cases?](#q-many) ·
[How do I use an aircraft that is not in the list?](#q-files) ·
[What happens if my aircraft file is incomplete or wrong?](#q-errors) ·
[How accurate is it?](#q-accuracy) ·
[What is not modelled?](#q-not)

---

<a id="q-runway"></a>
### What does "runway required" mean?

The larger of the **takeoff field length** and the **landing runway required**. The
simulator shows both; from Python, `analyze(...).runway_required_ft` and
`.governed_by` tell you the number and which one sets it.

<a id="q-which"></a>
### BFL, takeoff field length, all-engines distance: which do I use?

* **Balanced field length (BFL):** an engine fails at the critical speed; continuing and
  stopping need the same runway. This is the engine-failure requirement.
* **All-engines distance:** the normal takeoff, from brake release to 35 ft (civil) or
  50 ft (military).
* **Takeoff field length:** what the rules require, the larger of the two (civil: the
  all-engines distance × 1.15). **This is the takeoff number to design to.** The
  readout's hover text says which one governs.

Details: [Field-length rules](field_length_rules.md).

<a id="q-unbalanced"></a>
### Why is the field "unbalanced"?

There is no engine-failure speed at which going and stopping need the same distance.
Usually going on is longer even when the failure happens at VR: the remaining engines
barely overcome the drag after rotation. The tool then sets V1 = VR and the go distance
governs. Rotating later often fixes it, which is why the rotation-speed optimizer is on
by default (the SR-71 is the example). Details: [Rotation speed](rotation_speed.md).

<a id="q-vr"></a>
### Why is VR higher than 1.1 V_S?

Three things can raise it, and the Run summary lists each:

1. **The V2 rule:** the speed at 35 ft with one engine out must be at least 1.2 V_S
   (civil and military). VR is raised until it is.
2. **Touchback:** if the aircraft would lift off and settle back, VR goes up in steps.
3. **The optimizer:** if rotating later shortens the field, VR goes up to the best
   value. It costs tire speed and brake energy, both reported.

<a id="q-landing"></a>
### Is landing a concern for my design?

Every run answers it: the **Landing runway** tile, and Engineering details › Landing.
For a transport at maximum takeoff weight the answer is usually no, but a design that
lands near its takeoff weight, or a military aircraft landing without its chute, can be
landing-critical. The **Runway required (takeoff or landing)** trade-study metric shows
where that happens. Details: [Landing](landing.md).

<a id="q-warnings"></a>
### What do the warnings mean?

| Warning | Meaning | What to do |
|---|---|---|
| Tire speed … exceeds … | the highest ground speed on the tires is above a reference tire rating (`app/reference_aircraft.yaml`) | different tires, or a lower rotation speed |
| VR optimized … | rotating later shortened the field | nothing; note the higher tire speed |
| VR optimization stopped … not a true optimum | the field was still getting shorter where the data ran out (usually the end of the thrust table) | extend the table to higher speed |
| UNBALANCED | see above | see above |
| touchback … raising k_VR | lift-off then settling back at the configured VR | nothing; VR was raised |
| V2/V_S < 1.2 (not enforced) | you turned the V2 rule off | — |
| drag chute credited … outside Part 25 | a civil run uses the chute | use military rules, or turn the chute off |
| … not credited … set but not used | reversers / landing chute under civil rules | expected: Part 25 gives no credit |
| the flare needs … ft | the constant-g flare cannot fit under 50 ft | raise the flare load factor or lower the glide angle |
| touchdown below the stall speed | the flare bleeds off too much speed | lower the flare load factor |
| …query … outside [table range] | a table was read outside its range (error, not extrapolated) | extend the table |

<a id="q-minimum"></a>
### What is the least data I need for an aircraft?

Name, wing area, a default weight, the number of engines and their thrust (one number,
or a CSV of thrust against airspeed), idle thrust, the tail-strike attitude, and one
aero table (`alpha_deg, CL, CD`). Everything else has a default or is optional. The
builder marks required fields with *. Details: [Aircraft data](aircraft_data.md).

<a id="q-multipliers"></a>
### What do k_CL, k_CD and k_T do?

They scale the whole aero table: k_CL multiplies CL everywhere, **including CLmax**, so
it also moves the stall speed and every speed scaled from it. k_CD multiplies CD. They
stand for "a better or worse airframe" and do not scale the spoiler, engine-out or chute
increments. The landing has its own pair (landing flaps) that multiplies on top.
k_T multiplies the takeoff thrust (and reverse thrust), not idle thrust: "a more powerful
engine" without a new thrust table.

<a id="q-wet"></a>
### How do I model a wet or icy runway?

Through the friction coefficients, as everywhere else: Runway & weather › runway
condition fills the rolling and braking μ from MIL-STD-3013 Table II (dry, wet, wet
snow, wet ice), or type your own values. Takeoff and landing both use them. There is no
separate "wet" rule (no wet-runway screen height or V1 reduction).

<a id="q-altitude"></a>
### How are elevation and temperature handled?

The air density comes from the ISA pressure at the field elevation and the actual
temperature. It changes lift, drag and the true airspeed of every V-speed. **Thrust is
read from the table at the actual temperature (if the table has a temperature column)
but is not reduced for altitude**: the tables are sea-level tables. At high elevation
the result is therefore optimistic unless the thrust table is for that altitude.

<a id="q-rules"></a>
### Civil or military rules?

An aircraft setting (`certification.rules`, builder › Certification). Part 25: 1 s
recognition, 2-s distance pad on the stop, 35 ft, all-engines × 1.15, no chute or
reverser credit. MIL-STD-3013: 3 s from failure to brakes, no pad, 50 ft, no factor,
chute and reversers allowed. Details: [Field-length rules](field_length_rules.md).

<a id="q-ge"></a>
### Should I turn ground effect on?

Yes, if the aero table is a free-air table (the usual case) and you know the span and
the wing height on the gear. It removes part of the induced drag near the runway and
shortens the field by a few percent (747: about 5 %). Leave it off if the table already
includes ground effect. Details: [Ground effect](ground_effect.md).

<a id="q-airspeed"></a>
### Which airspeed are the V-speeds?

Equivalent airspeed in knots (KEAS), which equals calibrated airspeed (KCAS) to well
under a knot at takeoff speeds. Distances are along the runway; the tire speed is ground
speed.

<a id="q-many"></a>
### How do I run many cases?

In the app, the **Trade study** page maps any result over k_CL × k_CD for several aero
and thrust tables at once, with overrides for every simulator input. From Python,
`trade_study(cfg, {"weight_lbf": [...], "temperature_F": [...]})` solves any grid of any
inputs in parallel and returns a table. See [Using it from Python](python_usage.md).

<a id="q-files"></a>
### How do I use an aircraft that is not in the list?

From Python, pass a folder, an `aircraft.yaml` path, or the builder's `.zip` to
`load_config` or `analyze`. For the app, save it from the builder into `aircraft/`, or
start the app with `BFL_AIRCRAFT_DIR` pointing at your folder of designs.

<a id="q-errors"></a>
### What happens if my aircraft file is incomplete or wrong?

Loading stops with **every** problem listed in plain words: missing required fields
(with what they mean), empty sections, settings that do not exist (with a "did you
mean" suggestion for typos), wrong types, and table files that are listed but missing.
The builder shows the same checks live while you edit. A mistyped input name in a
script gets the same "did you mean" treatment.

<a id="q-accuracy"></a>
### How accurate is it?

Against real aircraft: the 747-100 takeoff field length is within −5.5 % to +4.4 % of
Boeing's chart; the SR-71's rotation and lift-off speeds within about 4 kt of flight
test. Numerically, the result is converged to fractions of a foot. In practice the
accuracy is set by the input data, especially drag and the spoiler / engine-out /
landing-flap increments. Details: the aircraft pages (☰ › Aircraft data & validation)
and Methods › Verification.

<a id="q-not"></a>
### What is not modelled?

Thrust lapse with altitude; pitch dynamics (the attitude is prescribed: hold, rotate at a
set rate, hold); lateral-directional motion (only V_mcg as a lower limit on V1); gusts
and time-varying wind; brake temperature and tire limits (reported, not enforced);
climb-gradient requirements after the screen height; wet-runway rule changes; reverser
stowing at low speed. See [Assumptions](assumptions.md).
