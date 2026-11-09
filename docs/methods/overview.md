# How it works

This tool answers one question: **how much runway does a big jet need if an engine can
fail at the worst possible moment during takeoff?** Answering it takes a physics model
(forces on the aircraft), an ODE integrator (to move it down the runway), event
location (to find exactly when things happen), root finding (to find the "worst moment"),
and interpolation (to read the aircraft's data tables). Every one of those numerical
methods is hand-written in `src/bfl/`.

## The question, in aviation terms

During the takeoff roll the crew has a **decision speed, V1**.

* If an engine fails **before V1**, they **stop**: brakes, engines to idle, spoilers up.
* If it fails **at or after V1**, they **go**: continue the takeoff on the remaining
  engines and climb to a 35 ft "screen height".

Choosing V1 is a trade:

* **Low V1:** stopping is easy (you're slow), but going means accelerating a long way on
  fewer engines. The *go* distance is long.
* **High V1:** going is easy (you're nearly at rotation speed), but stopping from high
  speed takes a lot of runway. The *stop* distance is long.

The V1 at which **go distance = stop distance** is the *balanced* V1, and that distance
is the **Balanced Field Length (BFL)**. With any other V1, one of the two failure
cases needs more runway than the BFL. See the *V1 trade* tab in the simulator.

The certification rules (FAA Part 25) also require the runway to be at least
**1.15 × the all-engines takeoff distance**. The *FAA field length* is the larger of
the two.

## The computation, from the inside out

```
compute_bfl
├─ [V2 rule] secant on k_VR so that V2 ≥ 1.2 V_S                (root finding)
│     └─ each evaluation: rotate → lift-off → 35 ft only          (RK4 / RK45 + events)
└─ [outer]   secant on V1:  d_go(V1) − d_stop(V1) = 0             (root finding)
      ├─ [inner] secant on V_EF: 1 s of one-engine-out ends at V1 (root finding)
      ├─ go branch:   integrate to h = 35 ft                       (RK4 / RK45 + events)
      └─ stop branch: integrate to V = 0                           (RK4 / RK45 + events)
```

1. **All-engines roll (computed once).** The aircraft accelerates from rest to the
   rotation speed VR. The trajectory is stored so it can be re-used for any V1.
2. **Inner solve, V_EF.** The engine fails at V_EF. The pilot needs about 1 s to
   recognise it, during which the aircraft keeps accelerating on the remaining engines
   and reaches V1. V_EF is the root of "speed after 1 s of one-engine-out
   acceleration = V1" (secant method on the stored roll).
3. **Go branch.** Keep accelerating on the remaining engines to VR, rotate (pitch up
   at 3°/s), lift off when lift carries the weight, climb to 35 ft. Distance = d_go.
4. **Stop branch.** At V1: brakes. 1 s later: idle. 2 s later: spoilers. Integrate
   until the aircraft stops, then add the regulatory **2-second allowance** (2 s × the
   speed at V1). Distance = d_stop.
5. **Outer solve, V1.** f(V1) = d_go − d_stop changes sign between a low V1 and VR, so
   a bracketed secant method finds the balanced V1 in about 6 evaluations.
6. **V2 rule (done first).** The speed at 35 ft (V2) must be at least 1.2 × stall
   speed. Rotating later helps, so a secant solve on k_VR = VR/V_S finds the smallest
   rotation speed that meets the rule. V2 depends only on VR: from VR on, the continued
   takeoff is one-engine-out from the same speed regardless of V1. So each evaluation
   only simulates rotate → 35 ft, and steps 1–5 then run once at the chosen VR.

Every time something switches (engine failure, brakes, idle, spoilers, rotation, lift-
off), the integration **stops exactly at that event** and restarts with the new
equations. This keeps the right-hand side of the ODE smooth inside every step, which
is what RK4's fourth-order accuracy assumes.

## Where each numerical method lives

| Method | File | Used for | Page |
|---|---|---|---|
| RK4 (fixed step) | `integrators.py` | moving the aircraft (default) | [Runge–Kutta](runge_kutta.md) |
| RK45 Dormand–Prince (adaptive) | `integrators.py` | moving the aircraft (fast option, sweeps, heatmap) | [Runge–Kutta](runge_kutta.md) |
| Event location | `integrators.py`, `phases.py` | V1, VR, lift-off, 35 ft, stop, switches | [Event location](event_location.md) |
| Secant / safeguarded secant | `rootfind.py` | V1, V_EF, k_VR and the event times themselves | [Root finding](root_finding.md) |
| Linear / natural cubic spline / bilinear | `tables.py` | CL(α), CD(α), thrust(V, T) | [Interpolation](interpolation.md) |

## Why the animation's stopping aircraft stops short of the red line

The stop distance includes the **2-second allowance**, a regulatory pad of 2 s × V1
ground speed (about 500 ft here) that is *added* to the distance but never flown. So
when go and stop are balanced, the go aircraft crosses 35 ft exactly at the red BFL
line, while the stop aircraft comes to rest one allowance short of it. The shaded
orange box under the runway in the animation is that allowance.

## Next

* [Assumptions & V-speed glossary](assumptions.md): what each V-speed means and every
  modelling decision.
* [Physics & equations](equations.md): the equations of motion and sign conventions.
* [Verification gallery](verification.md): evidence that each method works.
