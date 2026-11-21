# Lockheed SR-71A (J58) — real-aircraft data, estimated drag

Lift, thrust, weights and procedures come from the declassified flight manual. The
manual has no low-speed drag polar, so **drag is an estimate** (see below). The
digitized points live in [`tools/make_sr71_tables.py`](../../tools/make_sr71_tables.py),
which writes the CSVs.

**Scope:** sea-level pressure altitude, −38 to 40 °C (−36 to 104 °F). The thrust table
is not rescaled for altitude. The SR-71 is a military aircraft. Its manual uses a
*refusal speed* and an acceleration check, not a Part 25 balanced field. MIL-STD-3013 is
its rule set (`certification.rules: mil3013` in `aircraft.yaml`); the Part 25 numbers are a
comparison.

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
| TSFC | 1.9 /hr | **Estimate**: J58 maximum afterburner, sea-level static |
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

## What the model gives (sea level, ISA)

Fuel burn is on (J58 maximum-afterburner TSFC 1.9 /hr, an **estimate**). Stop distances
are at V1 = VR, because at the lowest legal VR the field does not balance (below).

| Weight (klb) | VR / V_LOF (OEI) / V2 (kt) | Part 25: AEO to 35 ft | stop (chute) | engine-out go | MIL-STD-3013: AEO to 50 ft | stop (no chute / chute) | engine-out go to 50 ft |
|---:|---|---:|---:|---:|---:|---:|---:|
| 100 | 156 / 171 / 188 | 4,340 | 5,088 | 7,133 | 4,664 | 5,954 / 4,858 | 8,079 |
| 120 | 170 / 188 / 200 | 5,831 | 6,537 | 12,046 | 6,229 | 7,604 / 6,303 | 13,369 |
| 140 | 184 / 203 / 208 | 7,658 | 8,182 | 26,863 | 8,139 | 9,459 / 7,948 | 29,269 |

- **At the lowest legal VR the field does not balance, under either rule set.** Even at
  V1 = VR, stopping is shorter than going on, so V1 = VR and the go distance governs. At a
  10° attitude in ground effect, the drag (≈27,000 lb with the engine-out increment)
  nearly cancels the one engine's ≈29,600 lb. The aircraft creeps from 185 to about
  204 kt over roughly a minute before it lifts off. On a 95 °F day at 140,000 lb there is
  no one-engine liftoff at all.
- **A later rotation fixes it** (`procedure.optimize_vr`, on by default, see
  `docs/rotation_speed.md`). Held on the runway, where the only extra drag is rolling
  friction, the aircraft accelerates well on one engine. Rotating close to lift-off speed
  avoids the slow, high-drag crawl:

  | Weight (klb) | rules | lowest legal VR: VR / field | optimized: VR / V1 / field (balanced) | tire speed | brake energy |
  |---:|---|---|---|---|---|
  | 100 | MIL | 156 kt / 8,079 ft | 172 / 168 kt / **6,827 ft** | 183 → 197 kt | 144 → 166 MJ |
  | 120 | MIL | 170 kt / 13,369 ft | 193 / 188 kt / **9,084 ft** | 194 → 214 kt | 204 → 244 MJ |
  | 140 | MIL | 184 kt / 29,269 ft | 212 / 207 kt / **11,688 ft** | 204 → 229 kt | 275 → 339 MJ |
  | 140 | Part 25 | 184 kt / 26,863 ft | 210 / 209 kt / **10,035 ft** | 204 → 227 kt | 184 → 216 MJ |

  The VR validated against the YF-12 (≈180 KIAS) is the normal all-engines rotation, i.e.
  the lowest legal VR. The optimized VR is an engine-out field-length schedule. A lower
  held attitude does not help: it needs an even higher lift-off speed.
- **Under MIL-STD-3013** (3-s delay, no 2-s pad, go to 50 ft) the go grows a little and the
  stop grows more, but neither changes the conclusion. Neither does the chute. It is
  optional under MIL rules and off by default, and it only shortens the stop.
- **It is not a drag-tuning problem.** At the lowest legal VR, with 30 % less drag
  (k_CD 0.7), the go still beats the stop at every weight. With 20 % less (k_CD 0.8) the
  140,000 lb engine-out go is 14,559 ft instead of 26,863 ft. The all-engines distance
  barely moves. No published low-speed SR-71/YF-12 polar was found (NASA TM X-3532,
  sometimes cited, is the XB-70). So the drag estimate is kept, not adjusted.
- **With the optimized VR, drag hardly matters either.** At 140,000 lb, MIL-STD-3013:

  | change | field length |
  |---|---:|
  | baseline | 11,688 ft |
  | engine-out ΔCD 0.010 → 0.005 / 0 | 11,544 / 11,404 ft |
  | all drag −10 % / −20 % (k_CD 0.9 / 0.8) | 11,458 / 11,238 ft |
  | drag chute on | 10,679 ft |
  | μ_brake 0.30 → 0.40 / 0.50 | 10,994 / 10,690 ft |
  | engine-failure delay 3 s → 2 s | 11,462 ft |
  | Part 25 rules (35 ft, 1 s + 2-s pad, chute credited) | 10,035 ft |

  The balanced field is 6,090 ft of acceleration to V1 = 207 kt plus a 5,600 ft stop from
  there. One J58 needs about 210 kt to fly the aircraft off, so V1 cannot be much lower,
  and stopping a 140,000 lb aircraft from 207 kt takes about 5,600 ft whatever the drag.
  The ~11,700 ft result follows from those two numbers. For scale, the SR-71's home base,
  Beale AFB, has a runway of about 12,000 ft (not from the sources above).
- **Fuel burn matters here.** It shortens the 140,000 lb engine-out go from 30,494 ft
  (constant weight) to 26,863 ft, because the aircraft sheds ~1,800 lb of fuel during the
  long crawl to lift-off.
- **Check against flight test, all engines.** [YF12] says the nosewheel comes up at
  about 180 KIAS, the aircraft is held at 10°, and it lifts off at about 200 KIAS. The
  model at 140,000 lb rotates at 184 kt and lifts off at 204 kt. This is checked by
  `tests/test_validation.py` (±10 kt) and shown on the app's SR-71 data page.
- **Real practice.** Operational SR-71s often took off with partial fuel and refueled
  in the air soon after ([TB]: "a takeoff with approximately 35,000 lb of fuel"), i.e.
  near 95–100k lb, where the engine-out continuation is far less marginal.
- The drag chute shortens the stop by about 17 % (110k lb, Part 25: 5,788 ft with,
  6,986 ft without). The manual's chute deployment limit is 210 KIAS.

The manual's own takeoff-distance charts (Appendix I, Part II) were not available in
the public scans, so there is no runway-length validation like the 747's.
