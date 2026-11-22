# Overview

A conceptual-design tool for **runway requirements**. Given an aircraft's lift and drag
tables, thrust, weights and a runway, it simulates the takeoff and the landing and
answers:

* **How much runway does this design need?** The larger of the takeoff field length and
  the landing runway required.
* **Takeoff:** the balanced field length (an engine fails at the worst moment: going on
  and stopping need the same runway), the all-engines takeoff distance, and the field
  length the rules require. Civil (FAA Part 25) or military (MIL-STD-3013).
* **Landing:** the distance from 50 ft to a stop and the runway the rules require.
* **The speeds:** V1 (or V_CEF), VR, V_LOF, V2, stall, approach and touchdown speeds, and
  the highest ground speed on the tires.
* **Sensitivities:** how all of this moves with lift, drag, weight, temperature,
  elevation, wind, slope and runway friction, one case at a time or as a trade-study map.

It is meant for the stage where a design is a set of tables and estimates: the numbers
are physics-based and validated, but they are not certified performance.

## Where to start

| I want to… | Go to |
|---|---|
| see a result now | **Simulator** (home page): pick an aircraft, press Run |
| add or edit an aircraft | **Aircraft builder** (☰ menu), then [Aircraft data](aircraft_data.md) for what each field means |
| map runway length over lift and drag (or engine/aero tables) | **Trade study** (☰ menu) |
| know how much extra runway a gusty day needs | **Gust analysis** (☰ menu) |
| know how much margin uncertain lift / drag / thrust data needs | **Data uncertainty** (☰ menu) |
| run cases from a script | [Using it from Python](python_usage.md) |
| know what a number means or why it changed | [Questions and answers](faq.md) |
| check the method or the numerics | the **Methods** page (☰ menu) |
| see how well it matches real aircraft | ☰ › Aircraft data & validation (747-100, SR-71) |

## What goes in

* **Aircraft** (one `aircraft.yaml` plus CSV tables, made in the builder): wing area,
  weight, engine count and thrust (constant, or a table against airspeed and optionally
  temperature), lift and drag against angle of attack (one table per flap setting),
  ground and tail-strike attitudes, and optional extras: engine-out drag, spoilers, drag
  chute, minimum control speed, ground-effect geometry, fuel flow, landing settings, and
  the rule set (civil or military). See [Aircraft data](aircraft_data.md).
* **The run**: weight, temperature, elevation, wind, slope, runway friction, lift and
  drag multipliers (k_CL, k_CD) and a few procedure options. These are the panels on the
  left of the simulator, or keyword arguments from Python.

## What comes out

| Output | Meaning |
|---|---|
| **Balanced field length (BFL)** | engine failure at the critical speed; go and stop need the same runway |
| **Takeoff field length** | Part 25: max(BFL, 1.15 × all-engines distance to 35 ft). MIL-STD-3013: max(BFL, all-engines distance to 50 ft) |
| **All-engines distance** | the normal takeoff to the screen height |
| **Landing runway required** | landing distance from 50 ft × the rule's factor (Part 121: ÷ 0.6) |
| **Runway required** | max(takeoff field length, landing runway required) |
| V-speeds, tire speed, brake energy, fuel used | in the readout, Run summary and downloads |
| time histories | every time step of the four runs (CSV download, or DataFrames from Python) |

## How good is it?

* **Boeing 747-100**, real data, sea level: the takeoff field length is within −5.5 % to
  +4.4 % of Boeing's chart from 500,000 to 705,000 lb.
* **Lockheed SR-71**, real lift and thrust, estimated drag: rotation and lift-off speeds
  within about 4 kt of YF-12 flight test (184 vs 180 kt, 204 vs 200 kt).
* **Numerics**: the two integrators agree to hundredths of a foot; the ground roll matches
  its closed-form solution to 10⁻⁸ relative. See Methods › Verification.

The main limits for design work (all listed under [Assumptions](assumptions.md)):
thrust tables are not lapsed with altitude, the model is a point mass with a prescribed
pitch attitude, and drag/lift increments for spoilers, engine-out and landing flaps are
the user's estimates.

## Speed

One run (takeoff with the rotation-speed optimizer, plus landing) takes about 0.1–0.4 s.
An 11 × 11 trade-study map takes 2–4 s on 15 cores.
