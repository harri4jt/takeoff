# Gust analysis

**☰ › Gust analysis.** A side analysis: gusts are used nowhere else in the tool (not on the
simulator, not in trade studies).

## What it answers

*How much more runway than the calm-day answer should I plan for a gusty day, and how sure
is that?*

Each **run** is one takeoff and one landing on a gusty day:

* the takeoff has the engine failure at the same critical moment as the balanced field
  length, and the crew flies the **calm-day schedule** (same V_EF, V1, VR);
* the landing is flown at the calm-day approach speed (plus an optional additive) with
  the same flare and stopping technique as the landing calculation.

Gusts move every event: a headwind gust makes VR arrive earlier on the runway, a
tailwind gust later; gusts in the air change lift and drag during the climb; vertical
gusts change the angle of attack around lift-off. Over hundreds of runs this gives a
**distribution** of distances.

It is **not a worst case** (with a carefully chosen gust, any runway can be beaten). It
answers *how often* a given runway is enough:

> **P95 = 9,918 ft** means 95 % of gusty-day operations needed at most 9,918 ft. With a
> calm-day answer of 9,523 ft, covering 95 % of such days costs +395 ft (+4.1 %).

## Reading the page

| Part | What it tells you |
|---|---|
| **Answer** | the runway that covers 90 / 95 / 99 % of runs, for the takeoff field length, the landing runway and (when they trade places) the larger of the two, with the margin over calm and a 95 % confidence interval |
| **Extra runway vs share covered** | the whole answer in one chart: pick the share you want to cover, read the margin. The x axis is a probability scale so 99 % gets room. Shaded: the sampling uncertainty |
| **Where the spread comes from** | the change in each takeoff branch (go, stop, all engines) and in the landing. The widest one is what gusts hurt most |
| **What the gusts look like** | one sampled takeoff or landing: the gusts the wing feels, the true airspeed, and the airspeed the crew acts on |
| **How reliable** | the P95 estimate settling as runs accumulate (sampling error ~ 1/√N), and on demand, the error from the integration time step |

Every chart has a camera icon that saves a high-resolution PNG, titled with its result,
for slides. The runs download as CSV (one row per run) and the summary as text.

## Inputs

| Input | Meaning |
|---|---|
| Conditions | from the simulator's last run (weight, weather, runway); override them in *Conditions* |
| Turbulence | light / moderate / severe: wind speed at 20 ft of 15 / 30 / 45 kt, the standard Dryden low-altitude categories (MIL-F-8785C) |
| Vertical too | include vertical gusts (on by default) |
| Operations | takeoff, landing, or both |
| Runs | 200 – 2,000. More runs tighten the estimates (4× the runs halves the band) |
| SDE method, time step | stochastic Heun (default) or Euler–Maruyama; 0.01 s is accurate to a few feet (Methods › Stochastic methods) |
| Random seed | the same seed gives the same runs |
| Pilot lag on gusts | the gust part of the airspeed the crew acts on is lagged by this (1 s): pilots and instruments do not react to every gust |
| Approach speed additive | knots added to the approach speed on gusty days (common practice: half the gust increment). Gusts alone barely change the landing; the additive does |

## The gust model, in short

* Two gust components, along the runway (u_g, + headwind) and vertical (w_g, + up), on top
  of the run's steady wind. Each is an **Ornstein–Uhlenbeck process**: a random wander
  pulled back toward zero, with a spread σ and a length scale L from the **Dryden
  low-altitude model** (σ_w = 0.1 W20, σ_u ≈ 1.9 σ_w at 20 ft, L_w = height,
  L_u ≈ 140 ft at 20 ft).
* The wing feels gusts **averaged over its span**: near the ground the vertical length
  scale is only ~10 ft, far shorter than a wing. The variance falls by
  f(r) = 2(r − 1 + e^(−r))/r², r = span/L, and the length scale grows to L/f.
* The aircraft equations are written relative to the ground, so the wind enters only
  through the airspeed and angle of attack the wing sees. With no gusts the page
  reproduces the main solver to within 0.2 % (takeoff) and 1 % (landing).

## Limits

* Steady-state Dryden turbulence: no wind shear, no discrete gusts, no change of mean wind
  during the run.
* The pilot model is simple: fixed schedule, gust part of the airspeed lagged; no
  attitude corrections for gusts (pitch follows the normal rotation law).
* When a gust pushes the angle of attack past the aero table's range, the coefficients are
  held at its end (a stall plateau); the page says when that happens at flying speed.
* At the end of the thrust table the thrust is held at the last value.
