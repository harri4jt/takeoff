# Sampling: Monte Carlo and Latin hypercube (data uncertainty)

Code: `src/bfl/uncertainty.py` (`sample_factors`, `quantile_ci_inf`, `sensitivity`), tests in
`tests/test_uncertainty.py`.

## Drawing a truncated normal

Each factor is normal(1, σ) cut at ±3σ. Both methods draw a uniform number
$u \in [\Phi(-3), \Phi(3)]$ and map it through the inverse normal CDF,
$k = 1 + \sigma\,\Phi^{-1}(u)$, which gives the truncated normal exactly.

* **Monte Carlo:** $u$ independent and uniform.
* **Latin hypercube:** for N draws, each factor's range is cut into N equally likely strata;
  $u_i = (\pi(i) + U_i)/N$ (rescaled) with $\pi$ a random permutation per factor, so each
  stratum of every factor gets exactly one draw, and the strata are paired at random between
  factors. The test checks that every stratum is hit exactly once.

## What Latin hypercube buys, and what it does not

Measured on the 747-100 (Typical CFD / NPSS, 200 draws, 20 repeats of each method):

| | spread of the **mean** | spread of the **P95** |
|---|---:|---:|
| Monte Carlo | ±46 ft | ±89 ft |
| Latin hypercube | **±2 ft** | ±88 ft |

The runway is almost a straight-line function of the three factors (the straight-line fit
explains 99 % of the spread). For an additive function, Latin hypercube's even coverage of
each input cancels almost all the sampling noise of the **mean**: about 20× here. A tail
percentile like the P95 is set by rare *combinations* of inputs, which stratifying each input
separately does not make more frequent, so it is about as uncertain as with Monte Carlo. For
the answers on the page (percentiles), more draws is what helps; Latin hypercube is the default
because it never hurts and makes the average essentially exact.

## Percentiles with draws that have no solution

Draws with no takeoff solution are counted as $+\infty$. The p-quantile is the order statistic
at $\lceil Np \rceil$ (inverted CDF), which is $+\infty$ when more than a share $1-p$ of draws
fail. The confidence interval is the distribution-free order-statistic interval of
[Stochastic methods](sde.md) (the number of draws below the true quantile is Binomial(N, p)),
kept with the infinities.

## The profiler: a response surface

The draws are scattered (not on a grid), so to show the runway at any combination of table
errors the page fits a **quadratic response surface** through them,

$$ y \approx c_0 + \sum_j c_j x_j + \sum_{i \le j} c_{ij} x_i x_j, \qquad x_j = k_j - 1, $$

ten coefficients by linear least squares. Its accuracy is checked on draws it did not see by
**leave-one-out cross-validation**, without refitting: the left-out residual of draw $i$ is
$e_i / (1 - h_{ii})$, with $h_{ii}$ the diagonal of the hat matrix $A(A^TA)^{-1}A^T$ (computed from a
QR factorization). For the 747 it is about ±9 ft over ±3σ of every table; a fresh full solve
at $(0.95, 1.05, 0.97)$ agrees with it to 10 ft.

Where some draws have no solution, a **logistic regression** $P(\text{no solution}) =
1/(1 + e^{-(b_0 + b \cdot x)})$ is fitted by Newton's method (iteratively reweighted least
squares). The physics is deterministic, so the boundary is sharp and the data separable; a tiny
ridge term and a clipped exponent keep the coefficients finite. The profiler shades where
$P > 0.5$.

## Which table matters: variance shares

Over the draws that solved, fit $y \approx b_0 + \sum_j b_j z_j$ with the standardized factors
$z_j = (k_j - 1)/\sigma_j$. Table $j$'s share of the spread is

$$ s_j = \frac{b_j\,\mathrm{cov}(z_j, y)}{\mathrm{var}(y)}, \qquad \sum_j s_j = R^2, $$

which for independent factors is $b_j^2\,\mathrm{var}(z_j)/\mathrm{var}(y)$. $R^2$ is the part of
the spread a straight-line model explains (99 % for the 747); $b_j$ is the runway change for a
+1σ error in table $j$.
