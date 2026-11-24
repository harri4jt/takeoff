# Uncertainty analysis

A side analysis on its own page (☰ › Uncertainty analysis, or `bfl.uncertainty` from
Python): it is used nowhere else in the tool.

## What it answers

*The lift, drag and thrust tables come from CFD and a cycle deck with no error bars. If
they are off by a few percent, how much runway should I plan, and which table matters
most?*

Each table gets a **1σ percentage**: the table is within ±1σ about 68 % of the time and
within ±2σ about 95 % of the time. Each **draw** multiplies the tables by random factors
with that spread,

> CL = k_CL · CL_table,  CD = k_CD · CD_table,  T = k_T · T_table,  k ~ normal(1, σ), cut at ±3σ,

and runs a full solve (balanced field length with the rotation-speed optimizer, takeoff
field length, landing). Over hundreds of draws this gives the spread of the answer:

> **P95 = 11,043 ft** means: with this confidence in the tables, 11,043 ft of runway is
> enough with 95 % confidence (747-100, ±5 % on all three tables: +1,520 ft, +16 % over the
> nominal 9,523 ft).

The factors multiply whatever the base case already has (e.g. the simulator's k_CL), so
the *nominal* is the base case itself.

## Setting the uncertainty

±5 % per table by default. There is no standard for the uncertainty of CFD or cycle-deck
tables, so these are judgement: drag is usually the least certain, thrust from a cycle deck
usually the most.

## What the page shows

* **Runway required**: the nominal, and the chance that each of up to three candidate
  runways is enough (with its sampling range), as a curve of chance against runway length.
* **Extra runway vs confidence**: the same answer read the other way, takeoff and landing.
* **Multiplier profiler**: runway against each multiplier, the others held at their slider
  values, from a quadratic response surface fitted through the draws
  ([Sampling](../methods/sampling.md)).
* **Feasibility map**: runway contours over the two tables that matter most for an
  equal error, with the 50 % and 95 % draw ellipses and the no-takeoff region shaded.

## When no runway is enough

Some draws have **no takeoff solution**: with less lift and thrust or more drag the aircraft
cannot lift off on one engine at all. These are not dropped (that would hide the worst
cases): they count as needing more runway than any length. If more than 5 % of draws fail,
**no runway gives 95 % confidence**, and the page says so. Example: the 140,000 lb SR-71 at
±5 %, where about 22 % of draws cannot lift off on one engine, and 10 % worse lift, drag or
thrust alone is enough.

## Limits

* The three errors are independent and normal. Real errors can be correlated (e.g. lift and
  drag from the same CFD run) or one-sided; neither is modelled.
* A factor scales a whole table uniformly; an error that grows with angle of attack or speed
  is not represented.
* Spoiler, engine-out and landing-flap increments are not varied.
