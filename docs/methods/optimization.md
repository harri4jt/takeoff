# Optimization: the rotation speed

Code: `src/bfl/optimize.py` (`brent_min`, `golden_section`), `src/bfl/bfl.py`.

The objective is FL(k_VR), the field length from a full BFL solve at that rotation
speed, on k_VR ≥ k_lo (the lowest legal value: V2 rule, touchback). Why rotating later can
help is under [Rotation speed](../assumptions/rotation_speed.md).

## The search

1. Solve at k_lo as usual.
2. **Bracket the minimum.**
   * **Probe** k_lo + 0.01 (about 1.5 kt of VR), then **scan** k_lo + 0.05, 0.10, … until
     the field length has risen twice in a row past its best value, or `procedure.k_VR_max`
     (1.6) is reached. If the probe and the first scan point are both worse, k_lo is the
     answer: **2 extra solves** (the 747 case).
   * **Warm start** (`compute_bfl(cfg, vr_hint=k)`, used by trade studies): evaluate the
     hint and hint ± 0.02, and walk downhill in doubling steps until the best point has a
     worse point on each side.
3. **Brent's method** inside the bracket, started from the best point found, to
   Δk_VR = 0.005 (~0.8 kt; the field length is flat there, within a few feet).
4. If the best point sits next to a **failed** solve (past the end of the thrust table,
   for example), the field length was still falling where the data ran out. That edge is
   located by bisection to Δk_VR = 2·10⁻⁵ and the result carries a warning that it is the
   data's limit, not a true optimum.
5. If nothing beats k_lo, the k_lo result is kept. The search runs without display
   trajectories; the winner is re-solved once with them when the app needs an animation.

## Why Brent's method

FL(k_VR) is continuous but has kinks: it is the larger of the balanced and all-engines
distances, and it switches from unbalanced (V1 = VR) to balanced. There is no derivative.
Golden-section search needs only a bracket and unimodality, and shrinks the bracket by
0.618 per evaluation whatever the shape. **Brent's method** keeps the same bracket and
safeguards, but where f looks smooth it jumps to the vertex of the parabola through its
three best points (order ≈ 1.32). It falls back to a golden step whenever the parabola is
not trusted. On the SR-71 it needs about 4 evaluations where golden section needs about 8;
on a pure kink it is no worse (`tests/test_features.py::test_brent_min`).

## Limits of the search

* It stops after the probe and one scan point are worse, so it would miss a second dip more
  than 0.05 above k_lo. None has been seen on either aircraft at any k_CL / k_CD.
* Warm starts find the minimum nearest the hint. Over the 11 × 11 SR-71 trade map they agree
  with cold starts to within 2 ft (`test_optimize_vr_warm_start_agrees_with_cold`).
