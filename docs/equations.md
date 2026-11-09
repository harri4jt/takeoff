# Equations, sign conventions and numerical methods

This file is the reference for what the code computes. It is kept in sync with
`src/bfl/dynamics.py`, `takeoff.py`, `bfl.py`, `integrators.py` and `rootfind.py`.
For the reasoning behind the modelling choices and a glossary of the V-speeds, see
[`assumptions.md`](assumptions.md).

## 1. Units and notation

The dynamics use the consistent **ft–slug–s–lbf** system, with temperature in °R and
angles in radians. Inputs and outputs use ft, kt, lbf, °F and degrees. Conversions
live only in `units.py` and happen only in `model.build_model` (input) and in
`results` / `forces()` (output).

| Symbol | Meaning | Sign / unit |
|---|---|---|
| x | distance along the runway from brake release | ft, + forward |
| h | height above the liftoff point | ft, + up |
| V | ground speed along the runway | ft/s |
| V_w | headwind component | ft/s, **+ headwind**, − tailwind |
| V_a | true airspeed (`V + V_w` on the ground) | ft/s |
| θ | pitch attitude | rad, + nose up |
| γ | flight-path angle relative to the air mass | rad, + climbing |
| α | angle of attack. `α = θ` on the ground, `α = θ − γ` in the air | rad |
| i_T | thrust-line incidence relative to the body axis | rad |
| ε_T = α + i_T | thrust angle relative to the velocity | rad |
| φ | runway slope | rad, **+ uphill** |
| μ | friction coefficient (μ_roll or μ_brake) | – |
| m = W/g₀ | mass | slug, g₀ = 32.174 ft/s² |
| q̄ = ½ρV_a² | dynamic pressure | lbf/ft² |
| S | wing reference area | ft² |

## 2. Atmosphere (ISA troposphere, `atmosphere.py`)

```
T_ISA(h) = 518.67 − 0.0035662·h                    [°R]
p(h)     = 2116.22·(T_ISA/518.67)^(g₀/(L·R))        [lbf/ft²],  g₀/(L·R) = 5.2561
ρ        = p(h_field) / (R·T_actual)                 [slug/ft³], R = 1716.49
```
The pressure comes from ISA at the field elevation. The density uses the **actual**
temperature, either from `temperature_F` directly or as `T_ISA + isa_delta_F`. The
density ratio is σ = ρ/ρ₀ with ρ₀ = 0.0023769 slug/ft³.

## 3. Forces

```
CL = k_CL·CL_table(α) + ΔCL_spoiler·[spoilers out]
CD = k_CD·CD_table(α) + ΔCD_eo·[engine failed] + ΔCD_spoiler·[spoilers out]
L  = q̄·S·CL
D  = q̄·S·CD + f_chute(t)·q̄·A_chute·CD_chute       f_chute ramps 0 → 1 over the inflation time
T  = n_operating · T_engine(V_a, T_amb)            or n_operating · T_idle when at idle
```
The multipliers scale only the table, so `CLmax = k_CL·max(CL_table)`. If the airspeed
is negative (a tailwind at brake release), drag acts forwards and thrust tables are
read at `max(V_a, 0)`.

## 4. Ground roll (state `[x, V]`, `ground_rhs`)

The runway frame is tilted by φ. The relative wind is along the runway, so lift is
perpendicular to the runway and drag is parallel to it.

```
V_a   = V + V_w
N     = W·cos φ − L − T·sin ε_T          (N ≥ 0 is enforced by clamping)
dV/dt = (T·cos ε_T − D − μ·N − W·sin φ) / m
dx/dt = V
```
(`W = m·g₀`.) The weight component `W·sin φ` slows the aircraft on an uphill runway.

**Liftoff** is the event where the *unclamped* N falls through zero (direction −1).

## 5. Airborne (state `[x, h, V_a, γ]`, `air_rhs`)

These equations are for a point mass in the vertical plane, written in the air-mass
frame with steady wind:

```
dV_a/dt = (T·cos ε_T − D)/m − g·sin γ
dγ/dt   = (T·sin ε_T + L)/(m·V_a) − g·cos γ / V_a
dh/dt   = V_a·sin γ
dx/dt   = V_a·cos γ − V_w
α = θ − γ
```
At liftoff `V_a = V + V_w`, `γ = 0` and `h = 0`.

**Assumption (Phase 1):** the airborne segment treats the ground as locally flat,
with h measured above the liftoff point, even when the runway has a slope. With a
slope, N = 0 means `L + T sin ε = W cos φ` instead of `W`. That leaves a residual
`dγ/dt ∝ W(cos φ − 1)` of order 10⁻⁵ rad/s, which is negligible.

**Phase 3 note:** with a time-varying wind, `dV_a/dt` and `dγ/dt` gain wind-rate
terms (`−dV_w/dt·cos γ` and similar), or the state must be rewritten in the ground
frame. That change is confined to `air_terms` and `ground_to_air_state`.

## 6. Procedure (FAA Part 25 style)

### 6.1 Speeds

The V-speeds are **equivalent airspeeds** at the API (KEAS ≈ KCAS). Internally they
are true airspeeds, `V_TAS = V_EAS/√σ`.

```
V_S = sqrt(2W / (ρ·S·CLmax))          (field ρ → TAS; identical to the EAS formula with ρ₀)
VR  = k_VR·V_S
V1  ∈ [V1_min, VR],   V1_min = V_mcg  if given, else 0.6·VR
```

### 6.2 Sequence

All times are measured from brake release, t = 0.

1. **AEO roll**, all engines, θ = θ_ground, μ = μ_roll, from V = 0. This roll is integrated once up to VR and cached.
2. **Engine failure at V_EF.** The failed engine's thrust drops to 0 and ΔCD_eo is added.
3. **Recognition interval** of `t_recog` seconds with one engine out, ending at V1.
   V_EF comes from an inner root solve (§8.3).
4. **Go:** keep rolling with one engine out to VR, then rotate:
   `θ(t) = min(θ_ground + q·(t − t_R), θ_target)` with `θ_target = θ_tailstrike − margin`.
   Liftoff happens at N = 0. If θ_target is reached first, the aircraft holds θ and keeps
   rolling. If liftoff happens first, the pitch-up continues in the air until θ_target.
   θ_target is then held. The go branch ends at the event **h = 35 ft**, and
   `d_go = x(h = 35)`.
5. **Stop:** at V1 + `t_brakes` (default 0 s) μ becomes μ_brake. At V1 + `t_idle` (1 s)
   the operating engines go to idle thrust. At V1 + `t_spoilers` (2 s) the spoilers
   deploy. The optional chute is deployed at V1 + `deploy_delay_s` and ramps up over
   `inflation_time_s`. The branch ends at the event V = 0.
   `d_stop = x_stop + t_v1_allowance·V1_ground`, with a default allowance of 2 s.
6. **AEO takeoff** to 35 ft uses the same rotation logic.
   `FAA field length = max(BFL, 1.15·d_AEO)`.

Every procedural switch is a **segment boundary**. The integrator never steps across a
discontinuity in the right-hand side, so RK4 and RK45 keep their formal order.

### 6.3 Touchback guard

The touchback event is `h + 0.01 ft` crossing zero downward. When it fires, the whole
BFL solve is rerun with `k_VR += 0.01`, up to `max_vr_retries` times. Each retry is
recorded in `vr_adjustments` and `warnings`. The small tolerance stops a harmless
~10⁻⁹ ft dip right after liftoff (see §5) from triggering it.

## 7. Analytic ground-roll check (verification 9.3)

Take constant T, CL, CD and μ, with α = 0, φ = 0 and V_w = 0. Then `N = W − L` and

```
m dV/dt = T − μW − ½ρS(CD − μ CL)·V²  ≡  A − B·V²,
          A = T − μ m g,   B = ½ρS(CD − μ CL).
```
Change variables with `dV/dt = V dV/dx` and let `u = V²`, so `du = 2V dV`:

```
(m/2)·du/dx = A − B u   ⇒   ∫₀^{V²} du/(A − B u) = (2/m)·x
⇒  −(1/B)·ln(A − B u) |₀^{V²} = 2x/m
⇒  x(V) = (m/(2B))·ln( A / (A − B V²) ).
```
This needs A > 0 (thrust beats static friction) and A − BV² > 0 (still accelerating).
It also holds for B < 0: both `m/(2B)` and the logarithm are negative, so x stays
positive. The test (`tests/test_physics.py::test_analytic_ground_roll`) matches this
to a relative error of 10⁻⁸ with both RK4 and RK45.

## 8. Numerical methods (all hand-written)

### 8.1 Integrators (`integrators.py`)

* **RK4.** Classical four-stage method with fixed `dt`. Local error is O(h⁵), global error O(h⁴).
* **RK45 (Dormand–Prince 5(4)).** It propagates the 5th-order solution (local
  extrapolation) and reuses the last stage as the next step's first (FSAL). The error
  norm is `‖e‖ = RMS(e_i / (atol + rtol·max(|y_i|, |y_i,new|)))`. A step is accepted
  if ‖e‖ ≤ 1. The next step is `h·min(5, max(0.2, 0.9‖e‖^(−1/5)))`. Rejected steps
  are counted, and the starting step uses the Hairer–Nørsett–Wanner heuristic.
* **Events.** Each event is `g(t, y)` with a direction and a terminal flag. After every
  accepted step [t_n, t_n+h], a sign change is checked. If there is one, the safeguarded
  secant method solves `φ(s) = g(t_n + s, Φ(t_n, y_n, s)) = 0` on s ∈ [0, h], where Φ is
  **one RK step of size s re-taken from the step start**. The event state is then as
  accurate as an ordinary step of the method. A step that *starts* on g = 0 does not
  count as a crossing. Event points are inserted into the output rows.

### 8.2 Root finding (`rootfind.py`)

* **Secant.** `x_{k+1} = x_k − f_k (x_k − x_{k−1})/(f_k − f_{k−1})`. Near a simple root
  its order is p = (1+√5)/2 ≈ 1.618. The observed order is estimated as
  `p_k = ln(e_{k+1}/e_k)/ln(e_k/e_{k−1})`.
* **Safeguarded secant.** This keeps a sign-change bracket. It takes a bisection step
  when the secant iterate would leave the bracket, or when the bracket has not halved
  over two iterations. It stops on |f| ≤ ftol or on bracket width ≤ xtol.

### 8.3 The nested solves

| Solve | Unknown | Equation | Method |
|---|---|---|---|
| outer | V1 ∈ [V1_min, VR] | `d_go(V1) − d_stop(V1) = 0`, tolerance 0.05 ft | safeguarded secant |
| inner | V_EF ∈ [V_a(0), V1] | `V_a(t_EF + t_recog) − V1 = 0`, tolerance 10⁻⁷ ft/s | safeguarded secant |
| events | t* within a step | `g(t*, y(t*)) = 0`, tolerance 10⁻⁹ s | safeguarded secant |

To find the state at V_EF, the code looks it up in the **cached AEO roll** (binary
search over the stored rows, then event location inside one step). Each inner
iteration therefore integrates only the 1-second recognition interval.

If f(V1) has no sign change on [V1_min, VR], the result is reported as **unbalanced**.
If go is still longer at VR, V1 = VR and the go distance governs. If stop is longer
even at V1_min, V1 = V1_min and the stop distance governs.
