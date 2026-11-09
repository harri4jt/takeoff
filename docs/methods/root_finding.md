# Root finding: the secant method

Code: `src/bfl/rootfind.py` (`secant`, `safeguarded_secant`, `observed_order`).

## The secant method

Newton's method needs $f'(x)$. Here $f$ is "run a whole takeoff simulation", with no
formula for its derivative. The secant method replaces $f'$ with the slope through
the last two iterates:

$$
x_{k+1} = x_k - f(x_k)\,\frac{x_k - x_{k-1}}{f(x_k) - f(x_{k-1})}.
$$

* **One new function evaluation per iteration** (Newton needs $f$ and $f'$).
* Near a simple root, the error satisfies $e_{k+1} \approx C\, e_k\, e_{k-1}$, which
  gives **order $p = \frac{1+\sqrt5}{2} \approx 1.618$** (the golden ratio).
  This is "superlinear": faster than bisection's $p=1$, slower than Newton's $p = 2$
  per iteration. Counted per function evaluation, it beats Newton
  ($1.618 > \sqrt2$).
* The observed order is estimated from successive errors as
  $p_k = \ln(e_{k+1}/e_k) / \ln(e_k/e_{k-1})$.

**Weakness:** no guarantee of convergence. If the two points straddle a flat region,
the secant line can throw the next iterate far away.

![secant convergence](../../output/verification/3_secant_convergence.png)

*Left: the error falls super-linearly; the observed orders 1.67 and 1.60 are close to
1.618. Right: on $\arctan x$ from a poor start, plain secant fails, while the
safeguarded version converges.*

## The safeguarded secant method

This keeps a **bracket** $[lo, hi]$ with $f(lo)$ and $f(hi)$ of opposite sign, so a
root is always inside. Each iteration:

1. Propose the secant point from the two most recent iterates.
2. Take a **bisection step** instead if
   * the proposal falls outside the bracket, or
   * the bracket has not at least halved over the last two iterations (stalling).
3. Evaluate $f$ at the new point and replace the bracket end that has the same sign.
4. Stop when $|f| \le$ ftol, or when the bracket is narrower than xtol.

The result keeps the secant method's speed when it is behaving and bisection's
guarantee when it is not. This is the same idea as Brent's or Dekker's method, in
simpler form.

## Where it is used (four places)

| Solve | Unknown | Equation | Tolerance |
|---|---|---|---|
| events | $s$ in one step | $g(t_n+s, \Phi(s)) = 0$ | $10^{-9}$ s |
| inner | V_EF | speed after $t_{\text{recog}}$ one-engine-out $-$ V1 $= 0$ | $10^{-7}$ ft/s |
| outer | V1 | $d_{\text{go}}(V1) - d_{\text{stop}}(V1) = 0$ | 0.05 ft |
| V2 rule | $k_{VR}$ | $V2/V_S - 1.2 = 0$ (each evaluation: rotate → 35 ft only) | $5\times10^{-5}$ |

The outer V1 solve typically needs **6 function evaluations**: the two bracket ends
plus about 4 secant steps. Each evaluation is a full go + stop simulation.

![BFL crossing chart](../../output/verification/6_bfl_crossing.png)

*The go distance falls with V1 and the stop distance rises, so f(V1) has exactly one
sign change on [V1_min, VR]. The secant method finds it without ever drawing this
curve. The curve is drawn only for illustration.*

## Unbalanced cases

If $f$ has the same sign at both ends of [V1_min, VR], there is no balance point:

* **Go is longer even at V1 = VR:** V1 = VR and the go distance governs.
* **Stop is longer even at V1 = V1_min:** V1 = V1_min and the stop distance governs.

The result is flagged "UNBALANCED" with the reason.
