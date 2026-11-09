# Boeing 747-100 — data template (NOT YET FILLED)

**Status:** this folder holds templates only. **No values have been entered.** The
aircraft fails config validation on purpose until every `null`/TODO is filled.

## Sources to digitize from
1. Hanke, C. R. & Nordwall, D. R., *The Simulation of a Jumbo Jet Transport Aircraft,
   Vol. II: Modeling Data*, NASA CR-114494, 1970.
2. Hanke, C. R., *The Simulation of a Large Jet Transport Aircraft, Vol. I: Mathematical
   Model*, NASA CR-1756, 1971.

For every number, record the report, the figure/table and the page in the table below.

## Quantities needed

| Quantity | File / field | Units | Source (report, fig/table, page) |
|---|---|---|---|
| Wing reference area S | `aircraft.yaml: geometry.wing_area_ft2` | ft² | TODO |
| Takeoff weight for the case compared | `weight.default_weight_lbf` | lbf | TODO |
| Tail-strike pitch attitude | `attitude.theta_tailstrike_deg` | deg | TODO |
| Ground attitude | `attitude.theta_ground_deg` | deg | TODO |
| Takeoff-flap CL vs α | `aero_takeoff.csv: CL` | – | TODO |
| Takeoff-flap CD vs α (gear down) | `aero_takeoff.csv: CD` | – | TODO |
| Ground spoiler ΔCL, ΔCD | `spoilers.delta_CL`, `spoilers.delta_CD` | – | TODO |
| Takeoff thrust per engine vs airspeed (and temperature) | `thrust.csv` | kt, °F, lbf | TODO |
| Ground idle thrust per engine | `engines.idle_thrust_per_engine_lbf` | lbf | TODO |
| Engine-out drag increment (windmilling + trim) | `aero.delta_CD_engine_out` | – | TODO |
| (optional) V_mcg | `speeds.V_mcg_kts` | KCAS | TODO |

## Notes
* Use the **body-axis** α the report uses and state which reference.
* If thrust is given as total for 4 engines, divide by 4 (the tables are **per engine**).
* If the source data are SI, use the helpers in `src/bfl/units.py`.
* Validate against Boeing *747 Airplane Characteristics for Airport Planning* takeoff
  runway-length charts using `faa_field_length_ft` (Phase 2).
