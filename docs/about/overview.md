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
* **Sensitivities:** how all of this moves with lift, drag, thrust, weight, temperature,
  elevation, wind, slope and runway friction, one case at a time or as a trade-study map.
* **Margins:** how much extra runway covers gusty days, or lift, drag and thrust tables
  that are only known to within a few percent.

It is meant for the stage where a design is a set of tables and estimates: the numbers
are physics-based and validated against real aircraft, but they are not certified
performance.

## Where to start

| I want to… | Go to |
|---|---|
| see a result now | **Simulator** (home page): pick an aircraft, press Run |
| add or edit an aircraft | **Aircraft builder**, and [Aircraft data](aircraft_data.md) for what each field means |
| map runway length over lift and drag, or over several aero / thrust tables | **Trade study** |
| know how much extra runway a gusty day needs | **Gust analysis** |
| know how much margin uncertain lift / drag / thrust data needs | **Uncertainty analysis** |
| run cases from a script | [Using it from Python](python.md) |
| know what the model assumes | the **Assumptions** page |
| check the numerics | the **Methods** page |
| see how well it matches real aircraft | ☰ › Aircraft data & validation (747-100, SR-71) |

## What goes in

* **Aircraft** (one `aircraft.yaml` plus CSV tables, made in the builder): wing area,
  weight, engine count and thrust (constant, or a table against airspeed and optionally
  temperature), lift and drag against angle of attack (one table per flap setting),
  ground and tail-strike attitudes, and optional extras: engine-out drag, spoilers, drag
  chute, minimum control speed, ground-effect geometry, fuel flow, landing settings, and
  the rule set (civil or military). See [Aircraft data](aircraft_data.md).
* **The run**: weight, temperature, elevation, wind, slope, runway friction, lift, drag
  and thrust multipliers (k_CL, k_CD, k_T) and a few procedure options: the simulator's
  input panel, or keyword arguments from Python.

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
