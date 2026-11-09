# Interpolation: reading the aircraft's tables

Code: `src/bfl/tables.py` (`Interpolator1D`, `Interpolator2D`, `thomas_solve`,
`natural_spline_second_derivatives`).

The aircraft data are tables:

* `aero_takeoff.csv`: lift coefficient CL and drag coefficient CD vs angle of attack α;
* `thrust.csv`: thrust per engine vs airspeed (optionally also vs temperature).

The integrator needs values *between* the table points, many thousands of times per
solve.

## Piecewise linear (default)

On the interval $[x_i, x_{i+1}]$ containing the query (found by binary search),

$$
p(x) = a\,y_i + b\,y_{i+1},\qquad a = \frac{x_{i+1}-x}{x_{i+1}-x_i},\; b = 1-a.
$$

The error is $O(h^2)$ for smooth data, and it **never overshoots** the data.

## Natural cubic spline (option `solver.interpolation: cubic`)

On each interval, a cubic that matches the data, with continuous first **and second**
derivatives at every knot:

$$
p(x) = a\,y_i + b\,y_{i+1} + \frac{h_i^2}{6}\Big[(a^3-a)M_i + (b^3-b)M_{i+1}\Big],
$$

where $M_i = p''(x_i)$. Requiring $p'$ to be continuous at the interior knots gives

$$
h_{i-1}M_{i-1} + 2(h_{i-1}+h_i)M_i + h_iM_{i+1}
= 6\left[\frac{y_{i+1}-y_i}{h_i} - \frac{y_i-y_{i-1}}{h_{i-1}}\right],
$$

with the **natural** end conditions $M_0 = M_n = 0$. This is a **tridiagonal** linear
system.

### The Thomas algorithm

Tridiagonal systems are solved by Gaussian elimination that touches only the three
diagonals: a forward sweep, then back substitution. That costs $O(n)$ operations
instead of $O(n^3)$. No pivoting is needed because the spline matrix is strictly
diagonally dominant ($2(h_{i-1}+h_i) > h_{i-1} + h_i$).

![spline vs scipy](../../output/verification/8_spline_vs_scipy.png)

*Left: the synthetic CL(α) table with linear and natural-spline interpolation. Right:
the difference between our spline and scipy's `CubicSpline(bc_type="natural")`, about
$10^{-16}$ (machine precision).*

## Bilinear (2-D thrust tables)

For thrust $T(V, T_{amb})$ on a rectangular grid: find the cell, compute
$t_x, t_y \in [0, 1]$, and blend the four corners:

$$
z = (1-t_x)(1-t_y)z_{ij} + t_x(1-t_y)z_{i+1,j} + (1-t_x)t_y z_{i,j+1} + t_x t_y z_{i+1,j+1}.
$$

## Why linear is the default

The solver's accuracy argument (RK4, $O(h^4)$) assumes a smooth right-hand side. A
linear table has *kinks* at the knots, which is a mild violation. A spline is
$C^2$-smooth, but it can **overshoot** between points. For example, it can invent a
lift peak higher than any tabulated CLmax, and CLmax sets the stall speed and
everything after it. For data with a sharp stall, a non-overshooting interpolant is the
safer engineering choice. The switch is in the config, and on the synthetic data the two
give BFLs that differ by about 0.03 ft.

## Out of range

Asking for a value outside the table raises `TableRangeError` by default
(`out_of_range: error`). The alternative, `clamp`, holds the end value and warns once.
Silent extrapolation is never done.
