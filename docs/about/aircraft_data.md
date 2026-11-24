# Aircraft data

An aircraft is a folder with an `aircraft.yaml` and one or more CSV tables. The
**Aircraft builder** (☰ menu) writes both: fill in the form, drop in the CSVs, check, and
save to `aircraft/` or download a `.zip`. Loading an existing aircraft into the builder
(*Start from*) is the quickest way to make a variant.

```
my_concept/
├── aircraft.yaml
├── aero_takeoff.csv        alpha_deg, CL, CD
├── aero_landing.csv        (optional, more flap settings)
└── thrust.csv              airspeed_kts, thrust_lbf  [, temperature_F] [, tsfc_per_hr]
```

All units are English: ft, ft², lbf, kt, °F, degrees, seconds.

## Tables

**Aero** (`alpha_deg, CL, CD`), one file per flap setting. α is the angle of the table's
reference line; the ground and tail-strike attitudes in `attitude:` use the same
reference. Rows must be in increasing α. The tool reads the table by linear
interpolation (natural cubic spline available: `solver.interpolation`) and **stops with
an error** outside the table's range rather than extrapolating, so cover the attitudes
the takeoff reaches (ground attitude to tail-strike).

**Thrust** per engine against true airspeed: `airspeed_kts, thrust_lbf`, or with a
`temperature_F` column for a 2-D table (one block of rows per temperature). An optional
`tsfc_per_hr` column turns on fuel burn. The table should reach the highest airspeed of
the takeoff (lift-off with one engine out, plus margin). Tables are sea-level: they are
not lapsed for altitude.

Lines starting with `#` are comments; use them for sources. The builder checks each CSV
with the solver's own loaders and plots it (Aero / Thrust tabs).

## Several tables per aircraft

Both kinds are lists of `name: file.csv` with a default:

```yaml
aero:
  configurations: {flaps10: aero_flaps10.csv, flaps20: aero_flaps20.csv}
  takeoff_configuration: flaps20
engines:
  thrust_mode: table
  thrust_tables: {JT9D-3: thrust.csv, JT9D-7: thrust_7.csv}
  thrust_table: JT9D-3
```

The simulator offers the others in its Aero / Thrust table dropdowns, and the trade study
compares them side by side.

## When a file has a problem

Loading reports every problem at once, for example:

```
my_concept/aircraft.yaml has 3 problems:
  1. geometry.wing_area_ft2: missing, and it is required (reference wing area S_ref [ft^2])
  2. weight.default_weight_lb: not a known setting (did you mean 'default_weight_lbf'?)
  3. aero.configurations: table file 'aero_flaps30.csv' not found in my_concept
```

## Every field

Generated from the model (`tools/make_aircraft_field_docs.py`); the builder shows the same
text when you hover a field.

<!-- BEGIN FIELDS (generated) -->

#### General

| field | default | meaning |
|---|---|---|
| `name` | **required** | display name, e.g. Boeing 747-100 |
| `description` | – | free text shown with the aircraft |

#### Geometry (`geometry:`)

| field | default | meaning |
|---|---|---|
| `wing_area_ft2` | **required** | reference wing area S_ref [ft^2] |
| `span_ft` | – | wing span [ft]; optional (gust analysis averages gusts over it; ground effect uses its own span_ft) |

#### Weight (`weight:`)

| field | default | meaning |
|---|---|---|
| `default_weight_lbf` | **required** | weight used if the run gives none |

#### Engines (`engines:`)

| field | default | meaning |
|---|---|---|
| `n_engines` | **required** | number of engines (one fails in the BFL cases) |
| `thrust_mode` | `constant` | constant: one thrust value; table: thrust CSV(s) |
| `thrust_per_engine_lbf` | – | takeoff thrust per engine [lbf] (constant mode) |
| `thrust_tables` | – | thrust tables (name -> CSV in the aircraft dir), e.g. different engines or ratings; selectable in the app and compared in the trade study |
| `thrust_table` | – | name of the default thrust table (a key of thrust_tables) |
| `idle_thrust_per_engine_lbf` | **required** | idle thrust per engine [lbf], used in the stop and the landing |
| `thrust_incidence_deg` | `0.0` | thrust line angle above the aero-table alpha reference line |
| `tsfc_per_hr` | `0.0` | thrust-specific fuel consumption [lbm/(lbf hr)]; 0 -> constant weight. A tsfc_per_hr column in the thrust CSV overrides it |

#### Attitude (`attitude:`)

| field | default | meaning |
|---|---|---|
| `theta_ground_deg` | `0.0` | angle of attack of the aero-table alpha reference while on the runway (wing incidence + fuselage ground pitch, in the table's alpha frame) |
| `theta_tailstrike_deg` | **required** | rotation is held 1 deg below this |

#### Aerodynamics (`aero:`)

| field | default | meaning |
|---|---|---|
| `configurations` | **required** | aero tables (name -> CSV in the aircraft dir), e.g. flap settings; selectable in the app and compared in the trade study |
| `takeoff_configuration` | `takeoff` | name of the default aero table (a key of configurations) |
| `delta_CD_engine_out` | `0.0` | drag added when an engine fails (windmilling + trim) |
| `CLmax` | – | optional CLmax per configuration for V_S (e.g. from certified stall speeds); configurations not listed use max(CL) of their table |

#### Spoilers (increments while braking) (`spoilers:`)

| field | default | meaning |
|---|---|---|
| `delta_CL` | `0.0` | lift increment (negative = dump) |
| `delta_CD` | `0.0` | drag increment of the spoilers |

#### Drag chute (`chute:`)

| field | default | meaning |
|---|---|---|
| `enabled` | `False` | credit the chute in the rejected takeoff |
| `area_ft2` | `0.0` | chute reference area [ft^2] |
| `CD` | `0.0` | chute drag coefficient on that area |
| `deploy_delay_s` | `1.0` | after V1 |
| `inflation_time_s` | `1.0` | deployment to full drag (linear ramp) |

#### Speeds (`speeds:`)

| field | default | meaning |
|---|---|---|
| `V_mcg_kts` | – | min control speed, ground |

#### Ground effect (Raymer) (`ground_effect:`)

| field | default | meaning |
|---|---|---|
| `enabled` | `False` | Raymer ground effect on the induced drag |
| `span_ft` | – | wing span b |
| `wing_height_ft` | – | wing (quarter-chord MAC) height above the runway, on gear |
| `K` | – | induced-drag factor; None -> fit |
| `fit_CL_fraction` | `0.85` | fit uses table points with 0 < CL <= this x CLmax |

#### Gear limits (optional) (`gear:`)

| field | default | meaning |
|---|---|---|
| `tire_speed_limit_kts` | – | ground speed |
| `max_brake_energy_MJ` | – | whole aircraft |

#### Certification (field-length rules) (`certification:`)

| field | default | meaning |
|---|---|---|
| `rules` | `part25` | part25 (civil) or mil3013 (military) |
| `t_recog_s` | – | engine failure -> action delay; None -> rule default (Part 25: 1 s to V1, MIL-STD-3013: 3 s to brakes). Programs may argue their own value |

#### Landing (flaps, technique, stopping devices) (`landing:`)

| field | default | meaning |
|---|---|---|
| `weight_lbf` | – | landing weight (e.g. max landing weight), capped at the takeoff weight; blank -> the takeoff weight (an immediate return, the worst case) |
| `configuration` | – | aero table to start from; blank -> the takeoff table |
| `k_CL` | `1.0` | landing flaps: CL multiplier on that table (includes CLmax, so it sets the landing stall speed) |
| `k_CD` | `1.0` | landing flaps: CD multiplier |
| `approach_speed_ratio` | – | approach speed / landing stall speed; blank -> rule (Part 25: V_REF = 1.23 V_SR0; MIL: 1.2) |
| `approach_angle_deg` | `3.0` | glide slope |
| `flare_load_factor` | `1.15` | constant-g flare: n = L/W in the flare |
| `touchdown_sink_rate_fps` | `2.0` | the flare ends at this sink rate, held to touchdown |
| `free_roll_s` | `2.0` | touchdown -> brakes and spoilers (and reversers) |
| `reverse_thrust_fraction` | `0.0` | reverse thrust as a fraction of max thrust. Military only: Part 25.125 gives no reverse-thrust credit |
| `use_chute` | `False` | military only: deploy the drag chute at touchdown (needs the chute section). Part 25 gives no credit |
| `field_factor` | – | runway required / landing distance; blank -> rule (Part 25/121: 1/0.6 = 1.67; MIL: 1.0) |

<!-- END FIELDS -->
