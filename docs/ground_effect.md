# Ground effect (Raymer method)

Close to the runway, the ground blocks part of the downwash behind the wing. The wing
then needs less induced drag to make the same lift. For a takeoff this matters: the whole
ground roll and the first few feet of climb happen with the wing within a fraction of a
span of the ground.

The tool uses the method from Raymer's *Aircraft Design: A Conceptual Approach*. It needs
only what a conceptual-design aero table already has, plus two lengths you can read off a
three-view.

## 1. Split the drag into a "zero-lift" part and an "induced" part

The aero table gives CD(α) and CL(α). Over the attached-flow part of the curve, a drag
polar is close to a parabola:

$$ C_D \approx C_{D0} + K\,C_L^2 $$

The tool fits $C_{D0}$ and $K$ to the table by **linear least squares** in the two unknowns
$(C_{D0}, K)$, with $C_L^2$ as the regressor. It uses the table rows with
$0 < C_L \le 0.85\,C_{L,\max}$, because near stall the drag rises faster than the parabola.
The fit and its $R^2$ are reported with the result (`polar_fit`). If you already know $K$
(for example $K = 1/(\pi A e)$), give it as `ground_effect.K` and the fit is skipped.

This is the same thing you would do by hand: estimate $C_{D0}$ and $K$ from a fit of the
polar, then scale only the induced part.

## 2. Scale the induced part by Raymer's factor

With $h$ the height of the wing above the runway and $b$ the span:

$$ \phi\!\left(\tfrac{h}{b}\right) = \frac{33\,(h/b)^{1.5}}{1 + 33\,(h/b)^{1.5}} $$

$\phi$ is the fraction of free-air induced drag that remains. It is 0 on the ground plane,
about 0.4 for a low-wing airliner on its gear ($h/b \approx 0.08$), and tends to 1 above
roughly one span. The drag the solver uses is

$$ C_D = C_{D,\text{table}} - (1-\phi)\,K\,C_L^2 $$

with $h$ = `wing_height_ft` on the runway and `wing_height_ft` + altitude once airborne, so
the benefit fades smoothly during the climb to the screen height. **Lift is unchanged**.
Ground effect also raises the lift-curve slope a little, which this method ignores.

| h/b | 0.05 | 0.08 | 0.10 | 0.15 | 0.20 | 0.30 | 0.50 | 1.0 |
|---|---|---|---|---|---|---|---|---|
| φ | 0.27 | 0.43 | 0.51 | 0.66 | 0.75 | 0.84 | 0.92 | 0.97 |

## 3. Inputs

```yaml
ground_effect:
  enabled: true
  span_ft: 195.7          # b
  wing_height_ft: 16.0    # quarter-chord of the MAC above the runway, on the gear
  # K: 0.045              # optional: skip the fit
  # fit_CL_fraction: 0.85 # optional: which part of the table is fitted
```

`k_CL` and `k_CD` still apply. The scaled polar is $k_{CD}C_{D0} + (k_{CD}/k_{CL}^2)\,K\,(k_{CL}C_L)^2$,
so the induced factor used is $K\,k_{CD}/k_{CL}^2$.

**Do not turn it on for a table that already contains ground effect.** The SR-71's
`ground_effect` table is measured in ground effect, so it stays off there.

## 4. What it does to the 747

On the 747-100 (span 195.7 ft, wing height ~16 ft, estimated, $h/b \approx 0.08$) the fit gives
$C_{D0} \approx 0.072$, $K \approx 0.037$ ($R^2 \approx 0.95$, gear down, flaps 20). Ground
effect removes about 57 % of the induced drag on the runway. The FAA field length at
710,000 lb drops from about 10,000 ft to about 9,500 ft, which closes roughly half of the
gap to Boeing's published value. See the 747 data page.

## Compared with MIL-STD-3013's method

MIL-STD-3013 §3.2.9.2 blends an in-ground-effect and an out-of-ground-effect polar:
$C_D = C_{D,OGE}(1 - E_2/E_1) + C_{D,IGE}\,E_2/E_1$, where $E(h/b)$ is an empirical curve,
$E_1$ is its value on the wheels and $E_2$ its value at height. That needs **two** complete
tables, which a conceptual design usually does not have. Raymer's factor needs one table and
two lengths, so it is the method used here under both rule sets.
