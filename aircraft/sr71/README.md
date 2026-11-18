# Lockheed SR-71A (J58) — real-aircraft data, estimated drag

Lift, thrust, weights and procedures come from the declassified flight manual. The
manual has no low-speed drag polar, so **drag is an estimate** (see below). The
digitized points live in [`tools/make_sr71_tables.py`](../../tools/make_sr71_tables.py),
which writes the CSVs.

**Scope:** sea-level pressure altitude, −38 to 40 °C (−36 to 104 °F). The thrust table
is not rescaled for altitude. The SR-71 is a military aircraft. Its manual uses a
*refusal speed* and an acceleration check, not a Part 25 balanced field, so the
Part 25 numbers here are a what-if comparison.

## Sources

| Tag | Document | Where |
|---|---|---|
| **[FM]** | USAF T.O. SR-71A-1, *Flight Manual, SR-71A*, 1989 revision (declassified). | Internet Archive, item [`0003756-lockheed-sr-71-03`](https://archive.org/details/0003756-lockheed-sr-71-03), volumes 01–03 |
| **[YF12]** | Berry, Mallick & Gilyard, *Handling Qualities Aspects of NASA YF-12 Flight Experience*, NASA Dryden, 1977. | NASA NTRS 19770011063 |
| **[TB]** | Corda et al., *The SR-71 Test Bed Aircraft*, NASA/TP-2000-209023. | NASA NTRS 20000064011 |

Section and figure numbers are the manual's own.

## Values and where they come from

| Quantity | Value | Source |
|---|---|---|
| Wing area S | 1,605 ft² | [FM] Section I, Dimensions (reference area) |
| Default weight | 140,000 lb | [FM] Section I: loaded gross weight 135,000 to over 140,000 lb ([TB]: 143,000 lb) |
| Thrust per engine vs airspeed and temperature | `thrust.csv` | [FM] Figure 1-3, takeoff thrust, max afterburner, sea level (note 1) |
| Idle thrust | 500 lb/engine | [FM] Figure 1-5: ~1,250 lb static, ~0 at 170 KIAS; the average over a stop |
| CL(α), in ground effect and free air | `aero_*.csv` | [FM] Figure 6-2, wing lift vs angle of attack (wind tunnel) (note 2) |
| α reference | table α = pitch attitude = indicated α + 1.2° | [FM] Section I, attitude indicator: 7° pitch ↔ 5.8° α |
| CLmax for V_S | 0.92 | free-air CL at 18°, the subsonic pitch-up angle, [FM] Section VI (note 3) |
| Ground attitude | 0° | [FM] Section I, attitude indicator ("0° pitch attitude on the ground") |
| Held takeoff attitude | 10° (`theta_tailstrike_deg: 11`) | [FM] Section II: normal takeoff attitude 8–10°; [YF12]: 10° (note 4) |
| Drag chute | 40 ft ribbon, area 1,257 ft², CD 0.50 | diameter: [FM] Section I, Drag chute system. CD is an **estimate** (typical ribbon chute) |
| CD(α) | CD0 + CL·tan(α_ind − α0) | **Estimate** (note 5) |
| Engine-out ΔCD | 0.010 | **Estimate**: windmilling J58 plus rudder and sideslip trim |
| Spoilers | none | the SR-71 has no spoilers |
| V_mcg | not set | note 6 |

### Notes

1. **Thrust.** The chart is against *indicated* airspeed for five temperatures. The model
   looks thrust up by true airspeed, so each curve is resampled at sea-level pressure:
   IAS = TAS·√(288.15 K / T). The chart stops at about 215 KIAS. Above 210 KIAS the
   last 50-kt slope is continued up to 270 kt TAS. The 2-D table interpolates between
   the five temperatures.
2. **Lift, and why the takeoff configuration is "in ground effect".** The chart gives
   two low-speed curves. Ground effect adds about 40% more lift at a given α. The whole
   run to 35 ft stays within about 0.6 wingspan of the runway (span 55.6 ft), so the
   in-ground-effect curve is used for takeoff. With the free-air curve the aircraft
   cannot lift off at its 10° attitude (CL 0.40 would need 260 kt at 140,000 lb), which
   contradicts the flight manual and [YF12]. `free_air` is kept as a second
   configuration. Below the first readable value (≈1°) both curves are continued
   linearly; the ground run sits there.
3. **CLmax.** "No wing stall experienced" (Figure 6-2). The closest equivalent of a
   stall for Part 25's V_S is the subsonic pitch-up angle of attack (~18°, [FM]
   Section VI). Free-air CL there is 0.92, which gives V_S = 167 KEAS at 140,000 lb.
   The operating limit is 14° below 25,000 ft ([FM] Section V), which would give
   V_S = 194 kt. That is too high compared with the flight-test speeds below.
4. **Attitude.** The tool rotates to (tail-strike limit − 1°) and holds it. The SR-71's
   geometric tail-scrape angle is not in these sources, so the limit is set to 11° to
   reproduce the manual's 10° takeoff attitude. It is not a geometric value.
5. **Drag.** No low-speed polar is published. The SR-71 wing is a thin, sharp-edged
   slender delta. Such a wing gets almost no leading-edge suction, so its resultant
   force stays nearly normal to the wing and the drag due to lift is CL·tan α. The
   zero-lift angles α0 are read from the chart (0.6° in ground effect, 1.0° free air).
   CD0 = 0.028 is an estimate: 0.018 clean, plus 0.010 for the gear (about 16 ft² of
   gear drag area).
6. **Minimum control speed.** [FM] Figure 3-2 gives a single-engine minimum *aerodynamic*
   control speed of about 180 KIAS at sea level, 59 °F (gear down, 5° sideslip; about
   215 KIAS wings level). The manual warns that below it, directional control on the
   ground "cannot be maintained". That is at or above the rotation speed at every
   weight here. So with V_mcg set there is no legal V1, and the tool stops with an
   error. Real SR-71 procedure is the same: abort before rotation speed, continue after.

## What the model gives (sea level, ISA, chute on)

| Weight (klb) | VR / V_LOF (OEI) / V2 (kt) | All engines to 35 ft | Stop from V1 | Engine-out go |
|---:|---|---:|---:|---:|
| 100 | 156 / 171 / 189 | 4,369 ft | 5,098 ft | 7,288 ft |
| 120 | 170 / 188 / 200 | 5,881 ft | 6,552 ft | 12,506 ft |
| 140 | 184 / 204 / 209 | 7,747 ft | 8,206 ft | 30,494 ft |

- **The field never balances.** Even at V1 = VR, stopping is shorter than going on, so
  V1 = VR and the go distance governs. At a 10° attitude in ground effect, the drag
  (≈27,000 lb with the engine-out increment) nearly cancels the one engine's
  ≈29,600 lb. The aircraft creeps from 185 to 204 kt over about 70 s before it lifts
  off. This matches the manual's engine-failure procedure, which says to dump fuel to
  stay airborne at heavy weight and, if unable to hold altitude and accelerate, to
  eject. On a 95 °F day at 140,000 lb there is no one-engine liftoff at all.
- **That result rests on the drag estimate.** With 20% less drag (k_CD 0.8) the
  140,000 lb engine-out go is 15,070 ft instead of 30,494 ft. Without the
  engine-out increment it is 19,229 ft. The all-engines distance barely moves
  (7,544 ft).
- **Check against flight test, all engines.** [YF12] says the nosewheel comes up at
  about 180 KIAS, the aircraft is held at 10°, and it lifts off at about 200 KIAS. The
  model at 140,000 lb rotates at 184 kt and lifts off at 204 kt (120,000 lb: 170 and
  188 kt).
- **Real practice.** Operational SR-71s often took off with partial fuel and refueled
  in the air soon after ([TB]: "a takeoff with approximately 35,000 lb of fuel"), i.e.
  near 95–100k lb, where the engine-out continuation is far less marginal.
- The drag chute shortens the stop by about 17% (110k lb: 5,801 ft with, 6,996 ft
  without). The manual's chute deployment limit is 210 KIAS.

The manual's own takeoff-distance charts (Appendix I, Part II) were not available in
the public scans, so there is no runway-length validation like the 747's.
