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

Written for the end of a design pass: *is the runway fine, how sure, and am I on a
knife's edge?* Every panel folds away (click its title); the method checks start folded.

| Part | What it tells you |
|---|---|
| **Runway required** | nominal; the runway to plan for at 90 / 95 / 99 % confidence (with its sampling range); and **runways you could use**: up to three real lengths (they start at the nominal rounded up to 1,000 ft, +1,000, +2,000), each with the chance it is enough and that chance's sampling range. The chart beside them is the whole story: chance of fitting against runway length, your runways marked on it (747-100 at ±5 %: 10,000 ft 70 %, 11,000 ft 95 %, 12,000 ft 99 %). If some draws cannot take off, the curve stops climbing at a ceiling no runway can beat. The verdict line says whether the design is near a cliff, and which operation sets the runway |
| **Extra runway vs confidence** | the same answer read the other way (extra runway for a chosen confidence), takeoff and landing separately, sampling uncertainty shaded |
| **What if the tables are off by…** | sliders for each multiplier and three plots of runway against each one, the others held at their slider values; your runways are drawn across. The curves come from a quadratic response surface fitted through the draws (accuracy on draws it did not see in the subtitle), anchored to the exact nominal |
| **Cliff map** | runway contours over the two tables that matter most for an equal error (from exact one-table-at-a-time solves at ±5 %; the third held exact), with the ellipses holding 50 % and 95 % of the draws, your runways as bold contours and the no-takeoff region shaded. The title gives how far the cliff is from nominal, in σ |
| **Method checks** (collapsed) | the drawn factors against the target normals, and the 95 % answer settling as draws accumulate (its sampling error) |

## When no runway is enough

Some draws have **no takeoff solution**: with less lift and thrust or more drag the aircraft
cannot lift off on one engine at all. These are not dropped (that would hide the worst
cases): they count as needing more runway than any length. If more than 5 % of draws fail,
**no runway gives 95 % confidence**, and the page says so, with the average error of the
failing draws ("drag +1.1σ, lift −0.6σ, …"). Example: the 140,000 lb SR-71 at ±5 %, where
about 22 % of draws cannot lift off on one engine, 10 % worse lift, drag or thrust alone
is enough, and the cliff map puts the cliff 1σ from nominal.

## Limits

* The three errors are independent and normal. Real errors can be correlated (e.g. lift and
  drag from the same CFD run) or one-sided; neither is modelled.
* A factor scales a whole table uniformly; an error that grows with angle of attack or speed
  is not represented.
* Spoiler, engine-out and landing-flap increments are not varied.
