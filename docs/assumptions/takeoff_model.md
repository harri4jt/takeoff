# Takeoff model

A conceptual-design runway estimator: the kind of estimate a performance engineer makes
before certified, flight-test-calibrated data exist. This section defines the speeds and
the modelling choices behind every takeoff result; the full list of what is left out is
under [Limits](limits.md).

## The takeoff speeds

| Speed | Name | What it means here |
|---|---|---|
| **V_S** | stall speed | `sqrt(2W/(ρ S CLmax))` in the takeoff configuration; the reference the other speeds are scaled from. CLmax is the table's maximum CL, or `aero.CLmax` if the aircraft file gives one (e.g. from certified stall speeds, as for the 747), times k_CL. |
| **V_mcg** | minimum control speed, ground | optional; when given, the lowest V1 allowed |
| **V_EF** | engine-failure speed | the speed at which the engine **actually fails** |
| **V1** | decision speed | the speed by which the crew has **recognised** the failure and takes the first action (brakes if stopping) |
| **VR** | rotation speed | `VR = k_VR·V_S`, default 1.10, raised if needed for the V2 rule and by the rotation-speed optimizer |
| **V_LOF** | lift-off speed | the airspeed when the wheels leave the ground (N = 0) |
| **V2** | takeoff safety speed | the airspeed at 35 ft, one engine out; must be ≥ 1.2 V_S (enforced, below) |

**V_EF and V1 differ** by the recognition time `t_recog` (Part 25: 1 s). The engine
fails at V_EF, the aircraft keeps accelerating on the remaining engines for t_recog, and
reaches V1. With `t_recog = 0` the two are equal. If V1 is so low that it is passed within
t_recog even with a failure at brake release, the solver stops with an error.

## Modelling choices

### V-speeds are airspeeds (KEAS ≈ KCAS)

* Inputs and outputs are **equivalent airspeed in knots (KEAS)**. At takeoff Mach numbers
  (< 0.3), KEAS and KCAS differ by well under 1 kt; no position-error correction is
  modelled.
* Internally, "reach V_EF / V1 / VR" compares **true airspeed** against `V_EAS/√σ`, which
  is the stall formula evaluated with field density.
* The Part 25 **2-second distance allowance** is a distance, so it uses the **ground
  speed** at V1. With no wind the two are the same.
* A headwind reaches a given airspeed at a lower ground speed, so it needs less runway.

### k_CL and k_CD scale the airframe, not the devices

k_CL = 1.1 means 10 % more lift from the wing and flaps everywhere, including CLmax. The
increments for **spoilers** (stop branch only), **engine-out drag** (windmilling engine
plus control deflections, from V_EF on) and the **drag chute** are separate hardware and
are not scaled. They are all optional in `aircraft.yaml`. Part 25 gives a chute no credit,
so a civil run that uses one is flagged.

### V2 ≥ 1.2 V_S is met by raising VR

Part 25.107 requires V2 ≥ 1.2 V_S, with VR chosen so that V2 is reached by 35 ft with one
engine out. An airframer meets this by scheduling VR, and so does the tool:

1. Solve at the configured `k_VR` (default 1.10).
2. If V2/V_S < 1.2, find the smallest `k_VR` with V2/V_S = 1.2. From VR on, the continued
   takeoff is one-engine-out from the same airspeed and does not depend on V1, so each
   evaluation only simulates rotate → lift-off → 35 ft. The BFL is then solved once at
   that k_VR.

For the 747-100 at 710,000 lb this moves k_VR from 1.100 to 1.154 and the BFL from
8,454 ft to 9,104 ft. Turn it off with `procedure.enforce_v2_min: false` (the result is
then flagged); the ratio is `procedure.v2_min_ratio`. The rotation-speed optimizer may
raise VR further ([Rotation speed](rotation_speed.md)).

### After lift-off, rotation continues to the target attitude

The pitch-up continues in the air at the rotation rate until θ_target = θ_tailstrike − 1°,
which is then held.

### Stopping

No reverse-thrust credit under Part 25. The operating engines go to idle 1 s after V1;
the failed engine stays at zero thrust and keeps its drag increment. Friction is a single
coefficient: μ_roll before the brakes, μ_brake after. Anti-skid enters only through the
value chosen.

### Weight

Constant unless the engines have a TSFC (`engines.tsfc_per_hr`, or a `tsfc_per_hr`
column in the thrust CSV). Then the fuel burned is an extra state,
`df/dt = TSFC·T/3600` for the operating engines, and `W = W₀ − f`.

### Thrust

Read from the table at the true airspeed and the actual temperature, but **not lapsed
with altitude**: the tables are sea-level tables. Lookups use `max(V_a, 0)` (with a
tailwind the airspeed is briefly negative at brake release).

### Runway slope

Uphill makes the acceleration to V1 longer, so the **total** accelerate-stop distance can
grow even though the deceleration after V1 is shorter.
