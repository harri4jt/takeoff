# Rotation speed and VR optimization

## Can rotating later shorten the field?

Yes, for some aircraft. By default the tool rotates at the **lowest legal VR**: k_VR = VR/V_S
starts at 1.10 and is raised only as far as needed for V2 ≥ 1.2 V_S (and to avoid a
touchback). That is the right choice for an aircraft with plenty of engine-out excess
thrust, but not for every aircraft.

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
  VR is already the optimum, and that is what the default does.
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
help, the default (lowest legal VR) is already the answer.

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

`procedure.optimize_vr: true` (in the app: *Procedure & solver › Optimize VR*; trade-study
override *Optimize VR*):

1. Solve at the lowest legal VR as usual (V2 rule, touchback).
2. **Scan** k_VR upward in steps of 0.05 (each point is a full BFL solve) until the field
   length has risen twice in a row past its best value, or `procedure.k_VR_max` (1.6) is
   reached. Solves that fail (for example past the end of a table) count as +∞.
3. **Golden-section search** (`bfl.optimize.golden_section`, hand-written) on the bracket
   around the best scan point, to Δk_VR = 0.002 (~0.3 kt).
4. Re-solve at the best k_VR with the normal output settings. If it does not beat the
   lowest legal VR, that result is kept.

Golden section suits this objective. FL(k_VR) is continuous but has kinks: it is the
larger of the balanced and all-engines distances, and it switches from unbalanced to
balanced. A derivative-free bracketing method only needs the function to be unimodal on
the bracket. Each iteration keeps the part of the interval that must contain the minimum
and shrinks it by 1/φ = 0.618. The scan supplies the bracket, so a second dip further out
(not seen in practice) cannot be missed between scan points of 0.05.

Cost: 10–20 BFL solves, about 1 s for the examples. In the trade study, every cell
runs its own optimization, so maps take about ten times longer with it on.
