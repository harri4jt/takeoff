# Landing distance

The tool answers "what runway does landing need?" next to the takeoff answer. Every run
computes both. The runway a design needs is the larger of the two:

**runway required = max(takeoff field length, landing runway required)**

Landing is often shorter than takeoff for a transport at maximum takeoff weight, but not
always. The civil landing factor is large (÷ 0.6). An aircraft that lands near its takeoff
weight, has a high approach speed, or (military) lands without its chute can be
landing-critical. Example: the 747-100 at a 600,000 lb takeoff weight needs 6,534 ft to
take off but 6,735 ft to land at its 564,000 lb maximum landing weight.

## What is flown

| segment | model |
|---|---|
| glide | from 50 ft at the approach speed V_A = ratio × V_S(landing), steady on the glide slope (3° default): constant γ and V_A |
| flare | **constant load factor** n = L/W (1.15 default), power at idle. It starts at the height where a constant-n pull-up turns the glide slope into the touchdown sink rate: h_flare = V_A² / (g (n − 1)) · (cos γ_td − cos γ_A) |
| final | the touchdown sink rate (2 ft/s default) held to the runway. The speed bleeds off in the flare, so the pull-up ends a little above the runway |
| free roll | idle thrust, rolling friction, for `free_roll_s` (2 s default) |
| braking | brakes + spoilers, plus reversers and the drag chute where the rules credit them, to a stop |

In the glide and flare the manoeuvre sets the lift (L = n W), so the angle of attack is
found by inverting the table's lift curve, and the drag is the table's at that angle
(with ground effect if it is on). The same RK45 integrator and event location as the
takeoff are used (events: flare start, end of flare, touchdown, stop).

## Rules

| | FAA Part 25 (civil) | MIL-STD-3013 (military) |
|---|---|---|
| start | 50 ft | 50 ft obstacle |
| approach speed | V_REF ≥ 1.23 V_SR0 (25.125) | 1.2 V_S (**to confirm against 3013B**) |
| reverse thrust | no credit | credited (`reverse_thrust_fraction`) |
| drag chute | no credit | credited (`use_chute`) |
| runway required | landing distance ÷ 0.6 (Part 121.195) | landing distance × 1.0 (**to confirm**) |

A wet or icy runway is not a separate option: set the braking friction (μ, runway
condition presets) as for the takeoff.

## Aircraft settings (`landing:` in aircraft.yaml, builder › Landing)

| field | meaning |
|---|---|
| `weight_lbf` | landing weight; blank = the takeoff weight (an immediate return) |
| `configuration` | aero table to start from; blank = the takeoff table |
| `k_CL`, `k_CD` | landing flaps as multipliers on that table (k_CL also scales CLmax, so it sets the landing stall speed) |
| `approach_speed_ratio`, `field_factor` | blank = the rule's value |
| `approach_angle_deg`, `flare_load_factor`, `touchdown_sink_rate_fps`, `free_roll_s` | technique |
| `reverse_thrust_fraction`, `use_chute` | military stopping devices (ignored, with a warning, under Part 25) |

The run's own k_CL / k_CD multiply on top, so a trade study on the aero moves the landing
answer as well. Trade-study outputs: `landing_runway_required_ft`, `runway_required_ft`,
and everything in `LandingResult.scalars()`.

## Limits of the model

* Constant weight and no fuel burn during the landing (a few seconds of idle).
* Reversers act at a fixed fraction of maximum thrust from the end of the free roll to the
  stop; real reversers are stowed at low speed (~60 kt), which matters little to distance.
