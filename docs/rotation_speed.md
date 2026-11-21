# Rotation speed and VR optimization

## Can rotating later shorten the field?

Yes, for some aircraft. The **lowest legal VR** is where k_VR = VR/V_S starts at 1.10 and
is raised only as far as needed for V2 ≥ 1.2 V_S (and to avoid a touchback). That is the
right choice for an aircraft with plenty of engine-out excess thrust, but not for every
aircraft, so by default the tool searches upward from there for the VR that gives the
shortest field (`procedure.optimize_vr: true`; set it to false to fly the lowest legal VR).

VR changes three things at once:

| A later rotation… | effect on the field length |
|---|---|
| lengthens the all-engines takeoff (more ground roll, faster lift-off) | longer |
| raises the balanced V1 (V1 ≤ VR), so the stop starts from a higher speed | longer |
| keeps the engine-out aircraft on the runway, at low drag, for longer before it pitches up | **shorter**, if the rotated attitude is draggy |

The third effect is the one that can win. Once an aircraft has rotated to its takeoff
attitude, its drag is much higher than in the ground roll. On the runway the extra drag is
only rolling friction, μ(W − L), which is small. If the one-engine thrust barely beats the
rotated drag, rotating early leaves the aircraft creeping towards lift-off speed at a high
angle of attack. Accelerating on the wheels first and rotating at a higher speed is then
much quicker. Rotating close to lift-off speed also means a lower lift coefficient, so a
lower drag due to lift.

### The two example aircraft (sea level, ISA, default weights)

| | lowest legal VR | optimized VR | field length: lowest VR → optimized |
|---|---|---|---|
| **747-100**, 710 klb, Part 25 | 155 kt | 155 kt (no change) | 9,523 ft → 9,523 ft |
| 747-100, k_CL 0.75, k_CD 1.25 (no ground effect) | 191 kt | 191 kt (no change) | 16,997 ft → 16,997 ft |
| **SR-71A**, 140 klb, MIL-STD-3013 | 184 kt | 212 kt | **29,269 ft → 11,688 ft** (balances) |
| SR-71A, 140 klb, Part 25 rules | 184 kt | 210 kt | 26,863 ft → 10,035 ft (balances) |

* **747:** the field length rises steadily with VR, even with 25 % less lift and 25 % more
  drag. Four engines leave a lot of excess thrust with one out, so the rotated drag is not a
  problem, and the extra all-engines distance and the higher V1 dominate. The lowest legal
  VR is already the optimum; the optimizer confirms it in two extra solves.
* **SR-71:** with one J58 out, the drag at the 10° takeoff attitude (in ground effect,
  ≈ 27,000 lb) almost cancels the remaining engine's ≈ 29,600 lb. Rotating at 184 kt leaves
  it crawling to lift-off for about a minute, so the field never balances. Holding the
  nose down to about 212 kt and then rotating gives a balanced field about 60 % shorter.
  This is why the SR-71 looked "broken": the problem was the rotation schedule, not
  the airspeed conversion or the data. The data page has the curve.

Holding a *lower* attitude does not help the SR-71: it then needs an even higher speed to
lift off (225+ kt), and it runs past the end of the digitized thrust chart. The rotation
speed is the lever, not the attitude.

### Is the optimized VR the takeoff you would actually fly?

It is legal: Part 25.107(e) sets only *lower* bounds on VR (≥ V1, ≥ 1.05 V_MC, V2 reached
by 35 ft, lift-off margins), and the same VR is used with all engines and with one out, as in
this tool. Manufacturers do schedule VR (and V2/V_S) above the minimum when it pays, for
example Boeing's "improved climb" speeds and Airbus's optimized V2/V_S. Under
MIL-STD-3013 the rotation speed is a program choice in the same way.

It costs something, and the tool shows the costs:

* **Tire speed:** the SR-71's maximum ground speed rises from 204 to 229 kt. Check the
  tire rating (Gear & limits tab).
* **Brake energy:** V1 rises (184 → 207 kt), so a rejected takeoff absorbs more energy.
* **All-engines distance:** longer (8,139 → 8,603 ft). This is the takeoff flown on almost
  every day.
* The field length is minimized at **one** weight and condition. A real schedule gives VR
  as a function of weight, temperature and altitude, so the optimization is per condition,
  as here.

So the optimized VR is the preferred plan **when the engine-out field length governs and
the tire and brake limits still hold**. For an aircraft like the 747, where it does not
help, the optimizer returns the lowest legal VR. That is why it is on by default: it
gives the right answer for both kinds of aircraft, the same way every time.

### A smarter way?

Look at the SR-71 curve: the minimum sits just past the point where the field first
balances (balanced V1 = VR). Below that point, raising VR shortens the engine-out go
quickly. Above it, the field is balanced and both distances grow slowly. So "the lowest VR
at which the field balances" is a good first guess. The search does not assume this,
because the minimum can also be set by the all-engines distance.

The other levers are the **V1/VR ratio** (Part 25 allows V1 below the balanced value with a
longer runway; this tool always balances) and the **engine-out rotation technique**
(rotation rate, held attitude). They are not optimized here.

## How the optimizer works

`procedure.optimize_vr` (default **on**; in the app: *Procedure & solver › Optimize VR*;
trade-study override *Optimize VR*). The objective is FL(k_VR), the field length from a
full BFL solve at that rotation speed, on k_VR ≥ k_lo (the lowest legal value).

1. Solve at k_lo as usual (V2 rule, touchback).
2. **Bracket the minimum.**
   * **Probe** k_lo + 0.01 (about 1.5 kt of VR), then **scan** k_lo + 0.05, 0.10, … until
     the field length has risen twice in a row past its best value, or `procedure.k_VR_max`
     (1.6) is reached. If the probe and the first scan point are both worse, the lowest legal
     VR is the answer: **2 extra solves** (the 747 case).
   * **Warm start** (`compute_bfl(cfg, vr_hint=k)`, used by the trade study): evaluate the
     hint and hint ± 0.02, and walk downhill in doubling steps until the best point has a
     worse point on each side. If the hint is k_lo itself, one probe is enough.
3. **Brent's method** (`bfl.optimize.brent_min`, hand-written) inside the bracket, started
   from the best point found, to Δk_VR = 0.005 (~0.8 kt).
4. If the best point sits next to a **failed** solve (past the end of the thrust table,
   for example), the field length was still falling where the data ran out. That edge is
   located by bisection to Δk_VR = 2·10⁻⁵ and the result carries a warning that it is the
   data's limit, not a true optimum.
5. If none of this beats k_lo, the k_lo result is kept. Otherwise the winning solve is used.
   The search runs without display trajectories; if the app wants them, the winner is solved
   once more with them. This is the only RK4 re-run, so the animation costs one extra
   solve, not one per search point.

**Why these methods.** FL(k_VR) is continuous but has kinks: it is the larger of the
balanced and all-engines distances, and it switches from unbalanced (V1 = VR) to balanced.
There is no derivative to use. Golden-section search needs only a bracket and unimodality,
and shrinks the bracket by 0.618 per evaluation whatever the shape. **Brent's method** keeps
the same bracket and safeguards, but where f looks smooth it jumps to the vertex of the
parabola through its three best points (order ≈ 1.32 instead of linear). It falls back to a
golden step whenever the parabola is not trusted. On the SR-71 the minimum is smooth, so it
needs about 4 evaluations where golden section needs about 8. On a pure kink it is no
worse than golden section (`tests/test_features.py::test_brent_min`).

### Run time, and what the speed-ups cost

Each evaluation is a whole BFL solve (about 6 go/stop pairs, 0.05–0.17 s here), so the cost
is the number of solves.

| | solves added | time (this machine) |
|---|---|---|
| 747, before (scan + golden section, Δk 0.002) | 11 | 1.0 s |
| 747, now (probe + first scan point) | 2 | 0.38 s (0.17 s without) |
| SR-71, before | 16 | 1.1 s |
| SR-71, now (probe, scan, Brent) | 10 | 0.63 s (0.05 s without) |
| trade map 11×11, SR-71: off / cold / warm-started | – | 1.1 / 8.3 / 6.7 s |
| trade map 11×11, 747: off / cold / warm-started | – | 1.7 / 4.3 / 3.6 s |

What each speed-up gives up:

* **Δk_VR 0.005 instead of 0.002.** VR moves by at most ~0.5 kt. The field length is flat
  near the minimum (SR-71: within 4 ft over ±0.003 in k_VR), so the error is a few feet.
* **"Probe and one scan point worse → stop".** This misses a *second* dip more than 0.05
  above k_lo, after FL has risen. None has been seen in either aircraft at any k_CL/k_CD,
  and the full scan had the same blind spot further out.
* **Warm starts** find the minimum nearest the hint. If a cell had two separated minima,
  a warm and a cold start could pick different ones. Over the 11×11 SR-71 map they agree to
  within 2 ft (`test_optimize_vr_warm_start_agrees_with_cold`). Each row of the map is split
  at its middle into two runs that walk outward along k_CD, one parallel task each, and only
  the first cell of each run starts cold.

Further speed-ups not taken:
* A V1 warm start inside each solve (start the secant at the neighbour's V1 instead of
  bracketing [V1_min, VR] afresh) would save about 2 of the ~6 go/stop pairs per solve.
  This is a change to the core solver, kept separate from the optimizer.
* Looser RK45 tolerances or a coarser V1 tolerance change every result, not only the
  optimized ones.
* Optimizing on a coarse grid and interpolating k_VR to the fine grid would be ~3× faster
  for the trade study, but the cells between would not be true optima.
