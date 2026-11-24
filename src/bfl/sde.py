"""Stochastic differential equations: Euler-Maruyama and stochastic Heun.

An SDE adds a random forcing to an ODE:

    dy = f(t, y) dt + g(t, y) dW

W is Brownian motion: over a step dt its increment dW is normal with mean 0 and variance
dt (so it scales like sqrt(dt), not dt). Here the noise is *diagonal*: component i of y
gets g_i(t, y) dW_i with independent W_i (zero g_i = no noise on that component).

Methods (one step from t to t + dt with the increments dW):

* Euler-Maruyama (EM):   y+ = y + f(y) dt + g(y) dW
  Converges to the Ito solution. Strong order 1/2 in general (path error ~ dt^0.5),
  strong order 1 when g does not depend on the noisy components (e.g. additive noise),
  weak order 1 (error in averages ~ dt).
* Stochastic Heun:       y~ = y + f(y) dt + g(y) dW                (EM predictor)
                         y+ = y + (f(y) + f(y~))/2 dt + (g(y) + g(y~))/2 dW
  The same dW in both stages. Converges to the Stratonovich solution; strong order 1
  for diagonal/commutative noise, weak order 2 for additive noise.

When g does not depend on the components that carry noise (true for the gust model:
the gust intensity depends on height and speed, not on the gust itself), the Ito and
Stratonovich solutions coincide, so both methods converge to the same answer.

States are lists of components; a component may be a float (one path) or a numpy array
(many paths at once, used by the convergence tests). f and g return lists of the same
shape. RK45 and other high-order ODE methods are NOT used for SDEs: their order relies on
a smooth right-hand side, and Brownian forcing is continuous but nowhere differentiable.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

Vector = list  # list of float | np.ndarray components
Drift = Callable[[float, Vector], Vector]
Diffusion = Callable[[float, Vector], Vector]


def em_step(f: Drift, g: Diffusion, t: float, y: Vector, dt: float, dw: Sequence) -> Vector:
    """One Euler-Maruyama step."""
    fy, gy = f(t, y), g(t, y)
    return [a + b * dt + c * d for a, b, c, d in zip(y, fy, gy, dw, strict=True)]


def heun_step(f: Drift, g: Diffusion, t: float, y: Vector, dt: float, dw: Sequence) -> Vector:
    """One stochastic Heun step (Stratonovich), same increments in both stages."""
    fy, gy = f(t, y), g(t, y)
    pred = [a + b * dt + c * d for a, b, c, d in zip(y, fy, gy, dw, strict=True)]
    fp, gp = f(t + dt, pred), g(t + dt, pred)
    return [
        a + 0.5 * (b + b2) * dt + 0.5 * (c + c2) * d
        for a, b, b2, c, c2, d in zip(y, fy, fp, gy, gp, dw, strict=True)
    ]


STEPS = {"em": em_step, "heun": heun_step}
METHOD_NAMES = {"em": "Euler–Maruyama", "heun": "Stochastic Heun"}


def get_step(method: str):
    try:
        return STEPS[method]
    except KeyError:
        raise ValueError(f"unknown SDE method {method!r}; choose from {sorted(STEPS)}") from None


@dataclass
class BrownianPath:
    """Brownian increments on a fine grid, coarsened by summing (same path at every dt).

    ``z`` holds standard normals, shape (n_fine_steps, n_components[, n_paths]). The
    increment of a step of r fine steps starting at fine index k is
    sqrt(dt_fine) * sum(z[k:k+r]). Using the same z for every step size is what makes a
    *strong* (path-by-path) convergence study possible.
    """

    z: np.ndarray
    dt_fine: float

    @classmethod
    def sample(
        cls,
        rng: np.random.Generator,
        t_end: float,
        dt_fine: float,
        n_components: int,
        n_paths: int | None = None,
    ) -> BrownianPath:
        n = int(math.ceil(t_end / dt_fine)) + 1
        shape = (n, n_components) if n_paths is None else (n, n_components, n_paths)
        return cls(rng.standard_normal(shape), dt_fine)

    def increments(self, r: int = 1) -> np.ndarray:
        """All increments for steps of r fine steps: shape (n_steps, n_components[, paths])."""
        n = (self.z.shape[0] // r) * r
        zz = self.z[:n].reshape(n // r, r, *self.z.shape[1:]).sum(axis=1)
        return math.sqrt(self.dt_fine) * zz

    def endpoint(self, t_end: float) -> np.ndarray:
        """W(t_end) for each component (and path)."""
        k = int(round(t_end / self.dt_fine))
        return math.sqrt(self.dt_fine) * self.z[:k].sum(axis=0)


def integrate_sde(
    f: Drift,
    g: Diffusion,
    y0: Vector,
    t_end: float,
    dt: float,
    increments: np.ndarray,
    method: str = "em",
    t0: float = 0.0,
) -> Vector:
    """Fixed-step integration to t_end with the given increments (one row per step);
    returns the final state."""
    step = get_step(method)
    n = int(round((t_end - t0) / dt))
    if increments.shape[0] < n:
        raise ValueError(f"need {n} increments, got {increments.shape[0]}")
    y, t = list(y0), t0
    for k in range(n):
        y = step(f, g, t, y, dt, increments[k])
        t += dt
    return y


def observed_order(steps: Sequence[float], errors: Sequence[float]) -> float:
    """Least-squares slope of log(error) against log(step)."""
    x, y = np.log(np.asarray(steps)), np.log(np.asarray(errors))
    return float(np.polyfit(x, y, 1)[0])


__all__ = [
    "em_step",
    "heun_step",
    "get_step",
    "BrownianPath",
    "integrate_sde",
    "observed_order",
    "METHOD_NAMES",
]
