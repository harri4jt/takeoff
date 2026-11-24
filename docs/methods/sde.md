# Stochastic methods (gust analysis)

Code: `src/bfl/sde.py` (Euler–Maruyama, stochastic Heun, Brownian paths),
`src/bfl/gusts.py` (the gust model and the takeoff and landing), tests in
`tests/test_sde.py` and `tests/test_gusts.py`.

## Stochastic differential equations

An ODE gives the rate of change; an **SDE** adds a random forcing:

$$ dy = f(t, y)\,dt + g(t, y)\,dW $$

$W$ is **Brownian motion**: over a step $\Delta t$ its increment $\Delta W$ is normal with
mean 0 and variance $\Delta t$, so it scales like $\sqrt{\Delta t}$, not $\Delta t$. Noise
adds up like a random walk. Each solution path is different; what is studied is the
statistics over many paths.

In the gust analysis, the random forcing drives the two gust components (each an
**Ornstein–Uhlenbeck** process, $du_g = -u_g/T\,dt + \sigma\sqrt{2/T}\,dW$), and the gusts
feed the aircraft equations through airspeed and angle of attack. The state is
$[x, h, u, w, u_g, w_g, \tilde u_g, \text{fuel}]$, with noise only on $u_g$ and $w_g$
(diagonal noise).

## Why not RK45?

Runge–Kutta methods get their order from Taylor expansions, which need a smooth right-hand
side. A Brownian-driven right-hand side is continuous but nowhere differentiable: the
high order is lost, and an adaptive step-size controller chases the noise. SDEs use their
own methods with a fixed step.

## Euler–Maruyama

$$ y_{n+1} = y_n + f(y_n)\,\Delta t + g(y_n)\,\Delta W_n,\qquad \Delta W_n = \sqrt{\Delta t}\,Z_n,\ Z_n \sim N(0, 1) $$

Euler's method plus the random kick. It converges to the **Itô** solution.

## Stochastic Heun

$$
\tilde y = y_n + f(y_n)\Delta t + g(y_n)\Delta W_n,\qquad
y_{n+1} = y_n + \tfrac12\big(f(y_n) + f(\tilde y)\big)\Delta t + \tfrac12\big(g(y_n) + g(\tilde y)\big)\Delta W_n
$$

The trapezoid (RK2) idea with the **same** $\Delta W_n$ in both stages. It converges to the
**Stratonovich** solution. Here the two coincide: the gust intensity depends on height
and speed, which carry no noise themselves, so the Itô–Stratonovich correction
$\tfrac12 g\,\partial g/\partial y$ is zero.

## Two kinds of convergence

* **Strong order** $\gamma$: the error of one path, driven by the same Brownian path,
  $E|y_N - y(T)| \le C\,\Delta t^{\gamma}$.
* **Weak order** $\beta$: the error of averages, $|E[\phi(y_N)] - E[\phi(y(T))]| \le C\,\Delta t^{\beta}$.

| | strong order | weak order | measured here (tests) |
|---|---|---|---|
| Euler–Maruyama, multiplicative noise | ½ | 1 | 0.48 on geometric Brownian motion |
| Euler–Maruyama, additive noise | 1 | 1 | weak order ≈ 1 on Ornstein–Uhlenbeck |
| Stochastic Heun (Stratonovich) | 1 | (2 for additive noise) | 0.98 on geometric Brownian motion |

![SDE strong order](../../output/verification/9_sde_strong_order.png)

*Same Brownian paths at every step size, 4,000 paths. Euler–Maruyama against the Itô
solution, stochastic Heun against the Stratonovich solution.*

Measuring a *strong* order needs the same Brownian path at every step size. The tests
draw the increments once on a fine grid and sum consecutive ones for the coarser steps
(`BrownianPath.increments(r)`), so a step of $r$ fine steps gets
$\Delta W = \sqrt{\Delta t_{\text{fine}}}\sum Z$, exactly the same path.

**On the gust problem** both methods come out about first order, a few feet of path error at
$\Delta t = 0.01$ s (the page's *Check the time step*). Two reasons: the noise structure
makes Euler–Maruyama strong order 1 here, and procedural switches (engine failure, VR,
brakes) take effect at the next step, which is a first-order effect for both methods.
Crossings that end a run (35 ft, the stop) are located by linear interpolation within the
step.

## Sampling error: Monte Carlo

The page's answers are percentiles of N runs. A sample percentile is itself uncertain, by
about $1/\sqrt N$: four times the runs halve the band. The confidence interval needs no
assumption about the distribution: the number of runs below the true p-quantile is
Binomial(N, p), so the interval runs between the order statistics at
$Np \mp z\sqrt{Np(1-p)}$ (`bfl.gusts.quantile_ci`; the test checks its coverage and the
$1/\sqrt N$ width).

## Time step against number of runs

The total error of a percentile has both parts: the time-step bias (~ $C\Delta t$) and the
sampling error (~ $1/\sqrt N$). Halving $\Delta t$ doubles the cost of every run; doubling N
doubles the cost too but only shrinks the sampling error by $\sqrt 2$. At $\Delta t = 0.01$ s
the step error is a few feet while the sampling error at 500 runs is tens of feet, so
compute is best spent on more runs, not smaller steps.

## The stepped gust variance

For the Ornstein–Uhlenbeck gust equation (the model is under
[Gust analysis](../assumptions/gusts.md)) the variance of the stepped process is known
exactly: Euler–Maruyama gives $\sigma^2/(1 - \Delta t/2T)$ (first-order error); Heun's
relative error is about $-(\Delta t/T)^2/4$ (second order). At $\Delta t = 0.01$ s that is
+1.7 % against −0.03 % at worst. The page's checks plot both formulas against simulation.
