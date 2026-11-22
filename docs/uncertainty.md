# Data uncertainty

**☰ › Data uncertainty.** A side analysis, like the gust analysis: it is used nowhere else
in the tool.

## What it answers

*Our lift, drag and thrust tables come from CFD and a cycle deck with no error bars. If
they are off by a few percent, how much runway should we plan, and which table matters
most?*

You state how far off each table might be, as a **1σ percentage**: the table is within
±1σ about 68 % of the time and within ±2σ about 95 % of the time. Each **draw** multiplies
the tables by random factors with that spread,

> CL = k_CL · CL_table,  CD = k_CD · CD_table,  T = k_T · T_table,  k ~ normal(1, σ), cut at ±3σ,

and runs a full solve (balanced field length with the rotation-speed optimizer, takeoff
field length, landing). Over hundreds of draws this gives the spread of the answer that
the data uncertainty causes:

> **P95 = 10,543 ft** means: with this confidence in the tables, 10,543 ft of runway is
> enough with 95 % confidence (747-100, "Typical CFD / NPSS": +1,020 ft, +10.7 % over the
> nominal 9,523 ft).

The factors multiply whatever the base case already has (e.g. the simulator's k_CL
slider), so the *nominal* is the base case itself.

## The confidence presets

There is no standard for the uncertainty of CFD or cycle-deck tables, so the presets are
**starting points (judgement)** to be edited:

| preset | lift 1σ | drag 1σ | thrust 1σ |
|---|---:|---:|---:|
| Validated against test | 2 % | 4 % | 1.5 % |
| Typical CFD / NPSS | 4 % | 8 % | 3 % |
| Early concept estimate | 8 % | 15 % | 5 % |

Drag is usually the least certain (it depends on details CFD struggles with); thrust from
a cycle deck is usually the most certain.

## Reading the page

| Part | What it tells you |
|---|---|
| **Answer** | the runway that is enough with 90 / 95 / 99 % confidence, for the takeoff field length, the landing runway and (when they trade places) the larger, with the margin over nominal and the estimate's own 95 % range |
| **Extra runway vs confidence** | the whole answer in one chart (probability-scaled x axis, shaded sampling uncertainty) |
| **Which data matters** | each table's share of the runway spread, and the runway change for a +1σ error in that table. Improve the data that dominates first |
| **Each draw against each table's error** | the draws behind the shares, with the straight-line trend |
| **The spread of the answer** | the histogram, nominal and 95 % point |
| **How reliable** | the 95 % point settling as draws accumulate; the drawn factors against the intended normal curves; a one-click comparison with the other sampling method |

## When no runway is enough

Some draws have **no takeoff solution**: with less lift and thrust or more drag the aircraft
cannot lift off on one engine at all. These are not dropped (that would hide the worst
cases): they count as needing more runway than any length. If more than 5 % of draws fail,
**no runway gives 95 % confidence**, and the page says so, with the average error of the
failing draws ("drag +1.1σ, lift −0.6σ, …"). Example: the 140,000 lb SR-71 at "Typical",
where about 21 % of draws cannot lift off on one engine.

## Limits

* The three errors are independent and normal. Real errors can be correlated (e.g. lift and
  drag from the same CFD run) or one-sided; neither is modelled.
* A factor scales a whole table uniformly; an error that grows with angle of attack or speed
  is not represented.
* Spoiler, engine-out and landing-flap increments are not varied.
