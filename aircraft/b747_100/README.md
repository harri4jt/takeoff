# Boeing 747-100 (JT9D-3) — real-aircraft data

Digitized from two public documents. Every number in `aircraft.yaml` and the CSVs
traces to a page below. The digitized points live in
[`tools/make_b747_tables.py`](../../tools/make_b747_tables.py), which writes the CSVs.

**Scope:** sea level, standard day (ISA). The thrust table is not rescaled for
altitude or temperature, so results at other elevations or temperatures are not valid
for this aircraft.

## Sources

| Tag | Document | Where |
|---|---|---|
| **[H&N]** | Hanke & Nordwall, *The Simulation of a Jumbo Jet Transport Aircraft, Vol. II: Modeling Data*, NASA CR-114494 (Boeing D6-30643), Sept 1970. The data Boeing gave NASA Ames for its 747 flight simulator. Includes an excerpt of the FAA-approved Airplane Flight Manual (AFM). | NASA NTRS, ID 19730001300 |
| **[ACAP]** | Boeing D6-58326, *747 Airplane Characteristics for Airport Planning* (747-100/-200/-300/SP). | Boeing (withdrawn); [archived copy](https://web.archive.org/web/20121014235349/http://www.boeing.com/commercial/airports/acaps/747_123sp.pdf) |

Page numbers are the documents' own (e.g. "2.0-7"), not PDF page numbers.

## Values and where they come from

| Quantity | Value | Source |
|---|---|---|
| Wing area S | 5,500 ft² | [H&N] 1.1-3, Summary of areas and dimensions |
| Default weight | 710,000 lb (MTOW) | [ACAP] 1.3 and the MTOW line on the 3.3.1 chart |
| CL(α), flaps 10 and 20 | `aero_flaps*.csv` | [H&N] 2.0-7, Effect of angle of attack on basic CL |
| CD(α), flaps 10 and 20 | `aero_flaps*.csv` | [H&N] 3.0-5 basic CD (gear up) **plus** 3.0-15 landing-gear increment |
| α reference | α_WRP = α_FRL + 2° | [H&N] 1.3-4 (wing datum plane vs fuselage reference line) |
| CLmax for V_S | 1.95 (flaps 10), 2.13 (flaps 20) | [H&N] 2.0-37, Certification stall speeds, at 600–700k lb (see note 1) |
| Thrust per engine vs speed | `thrust.csv` | [H&N] 12.2-3, installed generalized net thrust, read at EPR 1.42 (note 2) |
| Takeoff EPR | 1.42 | [H&N] 15.0-17 (AFM takeoff EPR): 1.405 packs on + 0.0175 packs-off correction |
| Engine-out ΔCD | 0.0015 | [H&N] 12.4-2 windmilling drag: ~500–800 lb per engine at V1–V2, i.e. ΔCD ≈ 0.0015 |
| V_mcg | 106 kt | [H&N] 15.0-23 (AFM minimum control speeds), sea level, 15 °C |
| Ground attitude | 2.0° (WRP) | Fuselage taken as level on the ground (FRL 0°), so WRP = 2° |
| Tail-strike attitude | 15.0° (WRP) | ≈13° fuselage, measured on the [ACAP] 2.2.1 side view (note 3) |
| Idle thrust | 2,000 lb/engine | **Estimate**, not from a source |
| TSFC | 0.36 /hr | **Estimate**: JT9D-3 class at takeoff thrust (fuel burn ~0.1 % of TOGW) |
| Span, wing height (ground effect) | 195.7 ft, 16 ft | span: D6-58326; wing height **estimated** (quarter-chord MAC on the gear) |
| Ground spoilers ΔCL / ΔCD | −0.60 / +0.070 | **Estimate**, not from a source (note 4) |

### Notes

1. **CLmax.** The 1960s certification stall speeds come from a stall manoeuvre with
   load factor below 1, so they imply a higher CLmax than the basic lift curve tops
   out at (1.88–1.91 for flaps 10, 2.09 for flaps 20). Part 25's V2 ≥ 1.2 V_S rule
   refers to this certified V_S, so `aero.CLmax` sets V_S from the certified value.
   The lift curve the dynamics use is unchanged. The implied CLmax falls slightly
   with weight (Mach effect): for flaps 20 it is 2.29 at 400k lb and 2.11 at 700k lb.
   The 600–700k value is used.
2. **Thrust.** The chart gives Fn/δ (δ = ambient pressure ratio) against EPR for Mach
   0–0.4. At sea level δ = 1. EPR is held at the takeoff setting for the whole run.
   Values at EPR 1.42: 41.8, 38.3, 36.1, 34.5, 32.8 klb at Mach 0, 0.1, 0.2, 0.3, 0.4.
   The simulator report is for the JT9D-3. The [ACAP] chart says JT9D-3A, a slightly
   higher-rated version.
3. **Tail strike.** Neither document lists a tail-strike angle. The angle from the aft
   main-gear wheels to the aft-fuselage underside on the scaled side view is about
   13° (±1°, limited by the drawing).
4. **Spoilers.** [H&N] builds ground-spoiler drag panel by panel (3.0-10 to 3.0-14).
   It was not digitized, because this tool targets conceptual design, where that
   detail is not available. The magnitudes are typical for full-span ground spoilers.

### Simplifications

- The basic CL and CD are free-air values. Ground effect is added by the Raymer method
  (drag only, see `docs/ground_effect.md`), which is on in `aircraft.yaml`. Stabilizer
  trim drag and the Mach/aeroelastic corrections in [H&N] are left out (they are
  small at takeoff speeds).
- Digitizing accuracy is about ±0.01 in CL, ±0.002 in CD (±0.003 at the drag
  minimum, where three flap curves overlap) and ±0.3 klb in thrust. Method: native
  300 dpi scans, deskewed, grid removed with a morphological opening, axes calibrated
  from the printed grid, and curves read by pixel scans or from calibrated zooms.

## Validation against Boeing's runway-length chart

[ACAP] 3.3.1 gives the FAR takeoff field length (the larger of 1.15 × the all-engines
distance to 35 ft and the engine-failure distance) for the 747-100, standard day.
Sea-level curve against the model (flaps 20, Raymer ground effect, defaults otherwise,
fuel burn on).
`tests/test_validation.py` runs this, checks every point is within ±12 %, and writes the
figures shown on the app's 747 data page. `python scripts/validate_b747.py` does the same
from the command line:

| Weight (klb) | Boeing (ft) | Model (ft) | Error | what-if: no ground effect (ft) | Error |
|---:|---:|---:|---:|---:|---:|
| 500 | 4,880 | 4,612 | −5.5% | 4,669 | −4.3% |
| 540 | 5,180 | 5,285 | +2.0% | 5,437 | +5.0% |
| 580 | 5,880 | 6,067 | +3.2% | 6,352 | +8.0% |
| 620 | 6,750 | 7,023 | +4.0% | 7,360 | +9.0% |
| 660 | 7,750 | 8,072 | +4.2% | 8,470 | +9.3% |
| 690 | 8,720 | 8,923 | +2.3% | 9,373 | +7.5% |
| 705 | 9,230 | 9,371 | +1.5% | 9,848 | +6.7% |

The model is 1.5–4.4% conservative over most of the weight range (−5.5 % at 500 klb).
In the model the all-engines case (1.15 × AEO distance) sets the field length at every
weight. Nothing was tuned to match. Sensitivities found while checking:

- Rolling friction μ = 0.03 (project default) → 0.02 shortens the field by about 3 %.
- **Ground effect** (Raymer, span 195.7 ft, wing height 16 ft **estimated**) cuts the
  error roughly in half compared with no ground effect. It is on in the baseline; turn it
  off with `ground_effect.enabled: false` or the app's checkbox.
- **Rotation speed:** the field length rises with VR, so the lowest legal VR is optimal
  (the VR optimizer, on by default, confirms it in two extra solves).
- JT9D-3 thrust is used, while Boeing's chart is for the JT9D-3A.
- Fuel burn (TSFC 0.36 /hr, **estimate**) is about 0.1 % of the weight and moves the
  result by ~0.1 %.
- Below about 520k lb Boeing's curve flattens near 4,900 ft. The model keeps
  falling. This is probably a minimum-speed or control limit the model does not
  include.

Flaps 10 gives runs 7–20% longer than flaps 20 in the model. That is consistent with
Boeing using flaps 20 except where the climb gradient requires flaps 10.

## Landing (`landing:` in aircraft.yaml, see docs/landing.md)

| Quantity | Value | Source |
|---|---|---|
| Landing weight | 564,000 lb | maximum landing weight as commonly published; **confirm** against the Boeing airport-planning document |
| Landing flaps | flaps 20 table × k_CL 1.12, k_CD 1.30 | **Estimate**: no flaps 25/30 table yet |
| Technique | 3° glide, 1.15 g flare, 2 s free roll | defaults |

Part 25 result (sea level, ISA): V_REF 139 kt, landing distance
4,041 ft, **landing runway required 6,735 ft** (÷ 0.6).
Not yet checked against Boeing's landing chart.
