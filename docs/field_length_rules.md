# Field-length rules: FAA Part 25 vs MIL-STD-3013

The tool can compute the runway two ways. **FAA Part 25** gives the *balanced field
length* (BFL) used for civil transports. **MIL-STD-3013** gives the *critical field length*
(CFL) used for military aircraft. Pick one with the **Field-length rules** switch (or
`procedure.rules: part25 | mil3013` in a run file). The two use the same physics. What
differs is the timing of the crew's actions, what counts as the end of the takeoff, and
which margins are added.

## Side by side

| | FAA Part 25 (BFL) | MIL-STD-3013 (CFL) |
|---|---|---|
| Key speed | **V1**, decision speed | **V_CEF**, critical engine failure speed |
| Engine failure → first action | V_EF, then 1 s recognition, reaching V1 (§25.107) | V_CEF, then **3 s** acceleration on the remaining engines (§3.2.10.1a) |
| First action | at V1: brakes; idle +1 s; spoilers +2 s | at end of the 3 s: brakes instantly; idle and devices deploy after their own delays (§3.2.10.1b) |
| Distance pad on the stop | **+2 s at V1** (§25.109(a)) | none |
| Go branch ends at | **35 ft** screen height (§25.113) | **50 ft** obstacle *(see note below)* |
| All-engines distance | to 35 ft, **× 1.15** | total takeoff distance to 50 ft (§3.2.8), **no factor** |
| Runway required | max(BFL, 1.15 × AEO) | max(CFL, AEO to 50 ft) |
| Drag chute / reverse thrust | no credit (dry runway) | allowed with approval (§3.2.10.1): **optional, off by default** |
| Speed minimums | V2 ≥ 1.2 V_S at 35 ft | V_LO ≥ 1.1 V_S (§3.2.3.1a, checked); V_obs ≥ 1.2 V_S at 50 ft (§3.2.4a, enforced like V2) |
| Lowest V1 / V_CEF | V_mcg (as a lower bound on V1) | V_CEF ≥ V_mcg (§3.2.11, warned if not) |
| Refusal speed | — | §3.2.12: highest speed from which you can stop on the runway you have |

Every one of these is an input. The rule set only supplies **defaults**. For example, the
3-s recognition delay is the standard's default, and a program may argue for a different
number (§3.2.10.2). Type it into **Engine failure → action delay**, or set
`procedure.t_recog_s`.

## How it maps onto the solver

The solver does not change. Both rule sets use the same go/stop search with a secant
root finder. MIL-STD-3013 is a set of procedure values:

```
t_recog_s = 3      # engine failure -> brakes (the Part 25 "V1" point is now "brakes on")
t_brakes_s = 0     # brakes at the end of the delay
t_v1_allowance_s = 0
screen_height_ft = 50
field_length_aeo_factor = 1.0
chute_enabled = false   # optional
```

The search is over the same variable. In MIL terms the balanced point is reported as
**V_CEF**, the engine-failure speed. The test suite checks that the MIL preset gives exactly
the same answer as a Part 25 run with those values typed in by hand.

## Runway condition presets

MIL-STD-3013 §3.2.14 and Table II give friction values. The **Runway condition** dropdown
fills both sliders from this table, and they stay editable. They apply under either rule set.

| Condition | RCR | Rolling | Braked | Braked, anti-skid |
|---|---|---|---|---|
| Dry | 23 | 0.025 (0.015 radial) | 0.30 | 0.38 (0.33 brake-limited) |
| Wet | 15 | 0.050 | 0.20 | 0.25 |
| Wet snow | 11 | 0.090 | 0.14 | 0.18 |
| Wet ice | 7 | 0.050 | 0.09 | 0.12 |

## Which revision?

The text above comes from **MIL-STD-3013 (14 Feb 2003)** and **MIL-STD-3013A (9 Sep 2008)**.
Their takeoff sections are word-for-word the same. The current revision is
**MIL-STD-3013B (1 Sep 2022)**. It is distribution A but was not available while this was
written.

> **Note on the 50 ft end point.** In 3013 and 3013A, §3.2.10 defines the CFL go case as the
> distance "to accelerate to **liftoff speed** with the critical engine inoperative". There,
> the 50 ft obstacle belongs to the *total takeoff distance* (§3.2.8). The tool ends the MIL
> go branch at **50 ft** on the expectation that 3013B changed this. A 2025 paper describes
> 3013B's CFL as the maximum of the all-engines, accelerate-stop and accelerate-go
> distances. To use the 3013/3013A definition, set `procedure.screen_height_ft` and
> re-check this page once the 3013B text is confirmed.

## Sources

- 14 CFR Part 25 §25.107, §25.109, §25.113.
- MIL-STD-3013 (2003) and MIL-STD-3013A (2008), *Glossary of Definitions, Ground Rules, and
  Mission Profiles to Define Air Vehicle Performance Capability*, §3.2 (everyspec.com).
- MIL-STD-3013B (2022), DLA ASSIST (not yet reviewed here).
