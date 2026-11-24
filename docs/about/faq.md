# Questions and answers

[What does "runway required" mean?](#q-runway) ·
[BFL, takeoff field length, all-engines distance: which do I use?](#q-which) ·
[Why is the field "unbalanced"?](#q-unbalanced) ·
[Why is VR higher than 1.1 V_S?](#q-vr) ·
[Is landing a concern for my design?](#q-landing) ·
[What do the warnings mean?](#q-warnings) ·
[What is the least data I need for an aircraft?](#q-minimum) ·
[What do k_CL, k_CD and k_T do?](#q-multipliers) ·
[How do I model a wet or icy runway?](#q-wet) ·
[How are elevation and temperature handled?](#q-altitude) ·
[Should I turn ground effect on?](#q-ge) ·
[How accurate is it?](#q-accuracy)

---

<a id="q-runway"></a>
### What does "runway required" mean?

The larger of the **takeoff field length** and the **landing runway required**. From
Python, `analyze(...).runway_required_ft` and `.governed_by` give the number and which
one sets it.

<a id="q-which"></a>
### BFL, takeoff field length, all-engines distance: which do I use?

* **Balanced field length (BFL):** an engine fails at the critical speed; continuing and
  stopping need the same runway. This is the engine-failure requirement.
* **All-engines distance:** the normal takeoff, from brake release to 35 ft (civil) or
  50 ft (military).
* **Takeoff field length:** what the rules require, the larger of the two (civil: the
  all-engines distance × 1.15). **This is the takeoff number to design to.**

Details: [Field-length rules](../assumptions/rules.md).

<a id="q-unbalanced"></a>
### Why is the field "unbalanced"?

There is no engine-failure speed at which going and stopping need the same distance.
Usually going on is longer even when the failure happens at VR: the remaining engines
barely overcome the drag after rotation. The tool then sets V1 = VR and the go distance
governs. Rotating later often fixes it, which is why the rotation-speed optimizer is on
by default (the SR-71 is the example). Details:
[Rotation speed](../assumptions/rotation_speed.md).

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

Every run answers it (the **Landing runway** tile). For a transport at maximum takeoff
weight it is usually not, but a design that lands near its takeoff weight, or a military
aircraft landing without its chute, can be landing-critical. The **Runway required**
trade-study metric shows where that happens. Details: [Landing](../assumptions/landing.md).

<a id="q-warnings"></a>
### What do the warnings mean?

| Warning | Meaning | What to do |
|---|---|---|
| Tire speed … exceeds … | the highest ground speed on the tires is above a reference tire rating (`app/reference_aircraft.yaml`) | different tires, or a lower rotation speed |
| VR optimized … | rotating later shortened the field | nothing; note the higher tire speed |
| VR optimization stopped … not a true optimum | the field was still getting shorter where the data ran out (usually the end of the thrust table) | extend the table to higher speed |
| UNBALANCED | see above | see above |
| touchback … raising k_VR | lift-off then settling back at the configured VR | nothing; VR was raised |
| V2/V_S < 1.2 (not enforced) | the V2 rule is turned off | — |
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

k_CL multiplies CL everywhere, **including CLmax**, so it also moves the stall speed and
every speed scaled from it. k_CD multiplies CD. They stand for "a better or worse
airframe" and do not scale the spoiler, engine-out or chute increments. The landing has
its own pair (landing flaps) that multiplies on top. k_T multiplies the takeoff thrust
(and reverse thrust), not idle thrust.

<a id="q-wet"></a>
### How do I model a wet or icy runway?

Through the friction coefficients: the runway-condition presets fill the rolling and
braking μ from MIL-STD-3013 Table II (dry, wet, wet snow, wet ice), or type your own.
Takeoff and landing both use them. There is no separate wet-runway rule (no wet screen
height or V1 reduction).

<a id="q-altitude"></a>
### How are elevation and temperature handled?

The air density comes from the ISA pressure at the field elevation and the actual
temperature. It changes lift, drag and the true airspeed of every V-speed. **Thrust is
read from the table at the actual temperature (if the table has a temperature column)
but is not reduced for altitude**: at high elevation the result is optimistic unless the
thrust table is for that altitude.

<a id="q-ge"></a>
### Should I turn ground effect on?

Yes, if the aero table is a free-air table (the usual case) and you know the span and
the wing height on the gear. It removes part of the induced drag near the runway and
shortens the field by a few percent (747: about 5 %). Leave it off if the table already
includes ground effect. Details: [Ground effect](../assumptions/ground_effect.md).

<a id="q-accuracy"></a>
### How accurate is it?

Against real aircraft: the 747-100 takeoff field length is within −5.5 % to +4.4 % of
Boeing's chart (500,000–705,000 lb, sea level); the SR-71's rotation and lift-off speeds
within about 4 kt of YF-12 flight test. Numerically, the result is converged to fractions
of a foot. In practice the accuracy is set by the input data, especially drag and the
spoiler / engine-out / landing-flap increments. Details: the aircraft pages
(☰ › Aircraft data & validation) and [Verification](../methods/verification.md).
