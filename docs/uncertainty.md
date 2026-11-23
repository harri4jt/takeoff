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

> **P95 = 11,043 ft** means: with this confidence in the tables, 11,043 ft of runway is
> enough with 95 % confidence (747-100, ±5 % on all three tables: +1,520 ft, +16 % over the
> nominal 9,523 ft).

The factors multiply whatever the base case already has (e.g. the simulator's k_CL
slider), so the *nominal* is the base case itself.

## Setting the uncertainty

Each table gets a **±1σ percentage**, ±5 % by default. There is no standard for the
uncertainty of CFD or cycle-deck tables, so these are judgement: drag is usually the least
certain (it depends on details CFD struggles with), thrust from a cycle deck usually the
most. The plot beside the inputs shows the three distributions that will be drawn.

## Reading the page

| Part | What it tells you |
|---|---|
| **Answer** | the runway that is enough with 90 / 95 / 99 % confidence, for the takeoff field length, the landing runway and (when they trade places) the larger, with the margin over nominal and the estimate's own 95 % range |
| **Extra runway vs confidence** | the whole answer in one chart (probability-scaled x axis, shaded sampling uncertainty) |
| **Explore (profiler)** | three plots, runway against each multiplier, with sliders setting the other two: "what if drag is 10 % high and thrust 3 % low?". The curves come from a quadratic response surface fitted through the draws (its accuracy, checked on draws it did not see, is in the subtitle); regions where the aircraft is predicted not to take off at all are shaded |
| **Where the uncertainty comes from** | a pie: each table's share of the runway spread (its variance). If a table were known exactly, the spread would shrink by its share. Grey: the part a straight-line model cannot explain. The table beside it gives the runway change per 1 % and per 1σ error |
| **Every draw, three times** | each draw plotted against each table's error: a tight band means that table alone sets the runway, vertical scatter is the other tables' errors; the panel titles give the slope (ft per 1 %) |
| **The spread of the answer** | the histogram, nominal and 95 % point |
| **How reliable** | the 95 % point settling as draws accumulate; the drawn factors against the intended normal curves; a one-click comparison with the other sampling method |

## When no runway is enough

Some draws have **no takeoff solution**: with less lift and thrust or more drag the aircraft
cannot lift off on one engine at all. These are not dropped (that would hide the worst
cases): they count as needing more runway than any length. If more than 5 % of draws fail,
**no runway gives 95 % confidence**, and the page says so, with the average error of the
failing draws ("drag +1.1σ, lift −0.6σ, …"). Example: the 140,000 lb SR-71 at ±5 %, where
about 22 % of draws cannot lift off on one engine; the profiler shades where that happens.

## Limits

* The three errors are independent and normal. Real errors can be correlated (e.g. lift and
  drag from the same CFD run) or one-sided; neither is modelled.
* A factor scales a whole table uniformly; an error that grows with angle of attack or speed
  is not represented.
* Spoiler, engine-out and landing-flap increments are not varied.
