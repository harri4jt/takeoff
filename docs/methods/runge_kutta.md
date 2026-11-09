# Runge–Kutta integrators

Code: `src/bfl/integrators.py` (`rk4_step`, `dp45_step`, `integrate`).

The aircraft's motion is an initial-value problem $y' = f(t, y)$, $y(t_0) = y_0$. On
the ground the state is $y = [x, V]$ (distance, ground speed). In the air it is
$y = [x, h, V_a, \gamma]$ (distance, height, airspeed, flight-path angle). See
[Physics & equations](equations.md) for $f$.

## RK4: the classical fourth-order method

One step of size $h$ from $(t_n, y_n)$:

$$
\begin{aligned}
k_1 &= f(t_n,\; y_n) \\
k_2 &= f(t_n + \tfrac h2,\; y_n + \tfrac h2 k_1) \\
k_3 &= f(t_n + \tfrac h2,\; y_n + \tfrac h2 k_2) \\
k_4 &= f(t_n + h,\; y_n + h k_3) \\
y_{n+1} &= y_n + \tfrac h6 (k_1 + 2k_2 + 2k_3 + k_4)
\end{aligned}
$$

It samples the slope four times across the step and takes a weighted average
(Simpson's-rule weights 1, 2, 2, 1). The **local** error per step is $O(h^5)$. About
$T/h$ steps are needed to reach time $T$, so the **global** error is $O(h^4)$:
**halve the step, and the error falls by $2^4 = 16$**.

The simulator uses $h = 0.01$ s. Halving it to 0.005 s changes the BFL by about
$4\times10^{-10}$ relative, far below any physical uncertainty.

![RK4 observed order](../../output/verification/2_rk4_order.png)

*Log–log error vs step size on $y'' = -4y$. The fitted slope is 3.92 (theory: 4), and
each halving cuts the error by about 15.7× (theory: 16).*

## RK45: Dormand–Prince 5(4), adaptive

Dormand–Prince uses 7 stages per step to build **two** solutions: one of order 5 and
one of order 4. Their difference estimates the local error **for free**, without
re-doing the step:

$$
e = y^{(5)}_{n+1} - y^{(4)}_{n+1},\qquad
\|e\| = \sqrt{\frac1m \sum_i \left(\frac{e_i}{\text{atol} + \text{rtol}\cdot\max(|y_{n,i}|, |y_{n+1,i}|)}\right)^2 }
$$

* $\|e\| \le 1$: **accept** the step and keep the 5th-order solution ("local
  extrapolation").
* $\|e\| > 1$: **reject** it and retry with a smaller $h$.
* Either way, the next step size is
  $h_{\text{new}} = h \cdot \min\!\big(5,\ \max(0.2,\ 0.9\,\|e\|^{-1/5})\big)$.
  The exponent $-1/5$ comes from local error $\propto h^5$. The 0.9 is a safety factor,
  and the 0.2 and 5 limits stop wild changes.
* **FSAL (first same as last):** the 7th stage of an accepted step is evaluated at the
  new point, so it *is* $k_1$ of the next step. This saves one function call.
* The very first $h$ uses the Hairer–Nørsett–Wanner starting heuristic.

Where the solution is smooth (the long, gentle ground roll), RK45 takes big steps.
It shortens them around rotation and lift-off, where things change quickly. That
is why it is about 14× faster than fixed-step RK4 here (0.2 s vs 3 s per full solve) and still agrees to a few hundredths of a foot.

## Comparison against exact solutions and scipy

![RK vs exact](../../output/verification/1_rk_vs_exact.png)

*Left: RK4 with a deliberately coarse $h = 0.25$, and RK45 at rtol $10^{-6}$, on
$y''=-4y$, against the exact $\cos 2t$. Right: pointwise error.*

![RK vs scipy](../../output/verification/4_rk_vs_scipy.png)

*Van der Pol oscillator (nonlinear, no closed form): our RK4 and RK45 against scipy's
DOP853 at $10^{-12}$ tolerance. They agree to about $10^{-11}$ and $10^{-10}$. scipy is
used only in the tests and this script, never in the solver or the app.*

## Why integrate segment by segment?

RK4's $O(h^4)$ error assumes $f$ is smooth across each step. The takeoff has
**discontinuities**: thrust drops when the engine fails, μ jumps when the brakes come
on, and the equations change entirely at lift-off. If a step straddled one of these,
the error for that step would drop to $O(h)$. So every switch is an
[event](event_location.md): integration stops exactly on it, and a new segment begins
with the new right-hand side.
