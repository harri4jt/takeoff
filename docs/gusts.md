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

Every panel folds away (click its title).

| Panel | What it tells you |
|---|---|
| **Runway on a gusty day** | the calm-day runway, the runway that covers 90 / 95 / 99 % of gusty days (with its sampling range), and up to three **runways you could use**, each with the chance it is enough. The chart: chance of fitting against runway length, your runways marked |
| **How the gusts are made** | the gust generator on its own, at a height and airspeed you pick: Dryden's strength σ and length L, the memory T = L/V, the update rule, one gust history, and a check that the gusts have the strength σ and the correlation e^(−τ/T) Dryden asks for. Make the time step long (0.2 s) and watch Euler–Maruyama's strength go wrong while Heun's barely moves |
| **One gusty run** | one takeoff or landing: the gusts the wing feels, the airspeed it feels, and the (lagged) airspeed the crew flies by |
| **Extra runway vs share of gusty days** | the whole answer as a curve, takeoff and landing, sampling uncertainty shaded |
| **Checks** | gusts off against the main solver; the gust-variance error against Δt/T (Euler–Maruyama first order, Heun second, exact formula and simulation); the P95 settling as runs accumulate (sampling error ~ 1/√N); on demand, the whole run at four time steps |

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
  of the run's steady wind.
* **Dryden low-altitude model** (MIL-F-8785C): from the mean wind at 20 ft (W20) and the
  height h, a strength σ and a length L for each: σ_w = 0.1 W20, σ_u = σ_w/(0.177 +
  0.000823 h)^0.4, L_w = h, L_u = h/(0.177 + 0.000823 h)^1.2.
* **Frozen turbulence**: the aircraft flies through the pattern, so a gust lasts T = L/V.
* **Ornstein–Uhlenbeck SDE**: dg = −(g/T) dt + σ√(2/T) dW. The pull −g/T gives the memory
  (correlation e^(−|τ|/T), which is Dryden's along-runway spectrum); the kick size σ√(2/T)
  keeps the variance at σ² (the variance lost to the pull each step is refilled by the kick).
* Stepped with **stochastic Heun** (default) or Euler–Maruyama together with the aircraft
  equations, Δt = 0.01 s. For this equation the stepped variance is known exactly:
  Euler–Maruyama σ²/(1 − Δt/2T) (first order), Heun 1 − ~(Δt/T)²/4 (second order); at
  Δt = 0.01 s that is +1.7 % vs −0.03 % at worst.
* The wing feels gusts **averaged over its span**: near the ground the vertical length
  scale is only ~10 ft, far shorter than a wing. The variance falls by
  f(r) = 2(r − 1 + e^(−r))/r², r = span/L, and the length scale grows to L/f.
* The aircraft equations are written relative to the ground, so the wind enters only
  through the airspeed and angle of attack the wing sees. With no gusts the page
  reproduces the main solver to within 0.2 % (takeoff) and 1 % (landing).
* From Python: `bfl.gusts.gust_signal(w20, h, v)` makes gust histories exactly as a run
  does (for checks and figures).

## Limits

* Steady-state Dryden turbulence: no wind shear, no discrete gusts, no change of mean wind
  during the run.
* The pilot model is simple: fixed schedule, gust part of the airspeed lagged; no
  attitude corrections for gusts (pitch follows the normal rotation law).
* When a gust pushes the angle of attack past the aero table's range, the coefficients are
  held at its end (a stall plateau); the page says when that happens at flying speed.
* At the end of the thrust table the thrust is held at the last value.
