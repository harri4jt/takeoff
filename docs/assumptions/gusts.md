# Gust analysis

A side analysis on its own page (☰ › Gust analysis, or `bfl.gusts` from Python): gusts are
used nowhere else in the tool.

## What it answers

*How much more runway than the calm-day answer should I plan for a gusty day, and how sure
is that?*

Each **run** is one takeoff and one landing on a gusty day:

* the takeoff has the engine failure at the same critical moment as the balanced field
  length, and the crew flies the **calm-day schedule** (same V_EF, V1, VR);
* the landing is flown at the calm-day approach speed (plus an optional additive) with
  the same flare and stopping technique as the landing calculation.

Gusts move every event: a headwind gust makes VR arrive earlier on the runway, a tailwind
gust later; gusts in the air change lift and drag during the climb; vertical gusts change
the angle of attack around lift-off. Over hundreds of runs this gives a **distribution** of
distances. It is **not a worst case**: it answers how often a given runway is enough.

> **P95 = 9,918 ft** means 95 % of gusty-day operations needed at most 9,918 ft. With a
> calm-day answer of 9,523 ft, covering 95 % of such days costs +395 ft (+4.1 %).

## Inputs

| Input | Meaning |
|---|---|
| Conditions | from the simulator's last run (weight, weather, runway), or overridden on the page |
| Turbulence | light / moderate / severe: wind speed at 20 ft of 15 / 30 / 45 kt, the standard Dryden low-altitude categories (MIL-F-8785C) |
| Runs | 200 – 2,000. Four times the runs halves the sampling band |
| Operations | takeoff, landing, or both |
| SDE method, time step | stochastic Heun (default) or Euler–Maruyama; 0.01 s is accurate to a few feet ([Stochastic methods](../methods/sde.md)) |
| Pilot lag on gusts | the gust part of the airspeed the crew acts on is lagged by this (1 s): pilots and instruments do not react to every gust |
| Approach speed additive | knots added to the approach speed on gusty days (common practice: half the gust increment). Gusts alone barely change the landing; the additive does |

## The gust model

* Two gust components, along the runway (u_g, + headwind) and vertical (w_g, + up), on top
  of the run's steady wind.
* **Dryden low-altitude model** (MIL-F-8785C / MIL-HDBK-1797), from the mean wind at 20 ft
  W20 and the height h (10–1000 ft):

$$ \sigma_w = 0.1\,W_{20},\quad \sigma_u = \frac{\sigma_w}{(0.177 + 0.000823h)^{0.4}},\quad L_w = h,\quad L_u = \frac{h}{(0.177 + 0.000823h)^{1.2}} $$

* **Frozen turbulence**: the aircraft flies through the pattern, so a gust lasts T = L/V,
  with V the airspeed relative to the turbulence (at least 10 kt).
* Each component is an **Ornstein–Uhlenbeck process**, dg = −(g/T) dt + σ√(2/T) dW: the
  pull −g/T gives the memory (correlation e^(−|τ|/T), Dryden's along-runway spectrum), and
  the kick size σ√(2/T) keeps the variance at σ².
* The wing feels gusts **averaged over its span**: near the ground the vertical length
  scale is only ~10 ft, far shorter than a wing. For r = b/L the variance falls by
  f(r) = 2(r − 1 + e^(−r))/r², and the length scale grows to L/f(r).
* The aircraft equations are written relative to the ground, so the wind enters only
  through the air-relative velocity (u + V_w + u_g, w − w_g) that sets lift, drag and angle
  of attack. The crew acts on u + V_w + ũ_g, where ũ_g is u_g through the pilot lag. With
  no gusts the page reproduces the main solver to within 0.2 % (takeoff) and 1 % (landing).
* From Python: `bfl.gusts.gust_signal(w20, h, v)` makes gust histories exactly as a run
  does.

## Limits

* Steady-state Dryden turbulence: no wind shear, no discrete gusts, no change of mean wind
  during the run.
* The pilot model is simple: fixed schedule, gust part of the airspeed lagged; no attitude
  corrections for gusts (pitch follows the normal rotation law).
* When a gust pushes the angle of attack past the aero table's range, the coefficients are
  held at its end (a stall plateau); the page says when that happens at flying speed.
* At the end of the thrust table the thrust is held at the last value.
