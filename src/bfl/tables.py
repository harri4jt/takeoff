"""Hand-written table interpolation and CSV loading.

* :class:`Interpolator1D` - piecewise-linear (default) or natural cubic spline
  (second derivatives from a tridiagonal system solved with the Thomas algorithm).
* :class:`Interpolator2D` - bilinear interpolation on a rectangular grid.

Out-of-range queries either raise (``"error"``, default) or are clamped to the end
of the table with a one-time warning (``"clamp"``).
"""

from __future__ import annotations

import warnings
from bisect import bisect_right
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd


class TableRangeError(ValueError):
    """Raised when a table is queried outside its range with out_of_range='error'."""


def thomas_solve(
    sub: Sequence[float], diag: Sequence[float], sup: Sequence[float], rhs: Sequence[float]
) -> list[float]:
    """Solve a tridiagonal system with the Thomas algorithm (no pivoting).

    ``sub[i]`` multiplies x[i-1] in row i (sub[0] unused), ``sup[i]`` multiplies
    x[i+1] (sup[n-1] unused). Stable for diagonally dominant matrices such as the
    natural-spline system.
    """
    n = len(diag)
    c = [0.0] * n
    d = [0.0] * n
    c[0] = sup[0] / diag[0] if n > 1 else 0.0
    d[0] = rhs[0] / diag[0]
    for i in range(1, n):
        m = diag[i] - sub[i] * c[i - 1]
        c[i] = sup[i] / m if i < n - 1 else 0.0
        d[i] = (rhs[i] - sub[i] * d[i - 1]) / m
    x = [0.0] * n
    x[-1] = d[-1]
    for i in range(n - 2, -1, -1):
        x[i] = d[i] - c[i] * x[i + 1]
    return x


def natural_spline_second_derivatives(x: Sequence[float], y: Sequence[float]) -> list[float]:
    """Second derivatives M_i of the natural cubic spline (M_0 = M_n = 0).

    Interior equations: h_{i-1} M_{i-1} + 2(h_{i-1}+h_i) M_i + h_i M_{i+1}
                        = 6[(y_{i+1}-y_i)/h_i - (y_i-y_{i-1})/h_{i-1}].
    """
    n = len(x)
    if n < 3:
        return [0.0] * n
    h = [x[i + 1] - x[i] for i in range(n - 1)]
    m = n - 2
    sub = [0.0] * m
    diag = [0.0] * m
    sup = [0.0] * m
    rhs = [0.0] * m
    for k in range(m):
        i = k + 1
        sub[k] = h[i - 1]
        diag[k] = 2.0 * (h[i - 1] + h[i])
        sup[k] = h[i]
        rhs[k] = 6.0 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
    inner = thomas_solve(sub, diag, sup, rhs)
    return [0.0, *inner, 0.0]


class Interpolator1D:
    """y(x) from tabulated points (x strictly increasing).

    Args:
        x, y: table.
        method: "linear" or "cubic" (natural cubic spline).
        out_of_range: "error" or "clamp".
        name: used in error/warning messages.
    """

    def __init__(
        self,
        x: Sequence[float],
        y: Sequence[float],
        method: str = "linear",
        out_of_range: str = "error",
        name: str = "table",
    ) -> None:
        xs = [float(v) for v in x]
        ys = [float(v) for v in y]
        if len(xs) != len(ys) or len(xs) < 2:
            raise ValueError(f"{name}: need >= 2 points with matching lengths")
        if any(b <= a for a, b in zip(xs, xs[1:], strict=False)):
            raise ValueError(f"{name}: x must be strictly increasing")
        if method not in ("linear", "cubic"):
            raise ValueError(f"{name}: method must be 'linear' or 'cubic'")
        if out_of_range not in ("error", "clamp"):
            raise ValueError(f"{name}: out_of_range must be 'error' or 'clamp'")
        self.x, self.y = xs, ys
        self.method = method
        self.out_of_range = out_of_range
        self.name = name
        self.x_min, self.x_max = xs[0], xs[-1]
        self._M = natural_spline_second_derivatives(xs, ys) if method == "cubic" else None
        self.n_clamped = 0

    def _check(self, xq: float) -> float:
        if self.x_min <= xq <= self.x_max:
            return xq
        if self.out_of_range == "error":
            raise TableRangeError(
                f"{self.name}: query {xq:.6g} outside [{self.x_min:.6g}, {self.x_max:.6g}]"
            )
        if self.n_clamped == 0:
            warnings.warn(
                f"{self.name}: query {xq:.6g} outside table range; clamping", stacklevel=3
            )
        self.n_clamped += 1
        return min(max(xq, self.x_min), self.x_max)

    def __call__(self, xq: float) -> float:
        xq = self._check(float(xq))
        x = self.x
        i = bisect_right(x, xq) - 1
        if i >= len(x) - 1:
            i = len(x) - 2
        x0, x1 = x[i], x[i + 1]
        h = x1 - x0
        a = (x1 - xq) / h
        b = 1.0 - a
        val = a * self.y[i] + b * self.y[i + 1]
        if self._M is not None:
            val += ((a**3 - a) * self._M[i] + (b**3 - b) * self._M[i + 1]) * h * h / 6.0
        return val

    def evaluate(self, xq: Sequence[float]) -> np.ndarray:
        """Vectorised convenience wrapper."""
        return np.array([self(v) for v in xq])

    @property
    def y_max(self) -> float:
        return max(self.y)


class Interpolator2D:
    """Bilinear interpolation z(x, y) on a rectangular grid ``z[i][j] = z(x_i, y_j)``."""

    def __init__(
        self,
        x: Sequence[float],
        y: Sequence[float],
        z: Sequence[Sequence[float]],
        out_of_range: str = "error",
        name: str = "table2d",
    ) -> None:
        self.x = [float(v) for v in x]
        self.y = [float(v) for v in y]
        self.z = [[float(v) for v in row] for row in z]
        if len(self.z) != len(self.x) or any(len(r) != len(self.y) for r in self.z):
            raise ValueError(f"{name}: z must have shape (len(x), len(y))")
        for arr, lab in ((self.x, "x"), (self.y, "y")):
            if len(arr) < 2 or any(b <= a for a, b in zip(arr, arr[1:], strict=False)):
                raise ValueError(f"{name}: {lab} must be strictly increasing with >= 2 points")
        if out_of_range not in ("error", "clamp"):
            raise ValueError(f"{name}: out_of_range must be 'error' or 'clamp'")
        self.out_of_range = out_of_range
        self.name = name
        self.n_clamped = 0

    def _clip(self, v: float, arr: list[float], lab: str) -> float:
        if arr[0] <= v <= arr[-1]:
            return v
        if self.out_of_range == "error":
            raise TableRangeError(
                f"{self.name}: {lab}={v:.6g} outside [{arr[0]:.6g}, {arr[-1]:.6g}]"
            )
        if self.n_clamped == 0:
            warnings.warn(f"{self.name}: {lab}={v:.6g} outside table; clamping", stacklevel=3)
        self.n_clamped += 1
        return min(max(v, arr[0]), arr[-1])

    def __call__(self, xq: float, yq: float) -> float:
        xq = self._clip(float(xq), self.x, "x")
        yq = self._clip(float(yq), self.y, "y")
        i = min(bisect_right(self.x, xq) - 1, len(self.x) - 2)
        j = min(bisect_right(self.y, yq) - 1, len(self.y) - 2)
        tx = (xq - self.x[i]) / (self.x[i + 1] - self.x[i])
        ty = (yq - self.y[j]) / (self.y[j + 1] - self.y[j])
        z = self.z
        return (
            (1 - tx) * (1 - ty) * z[i][j]
            + tx * (1 - ty) * z[i + 1][j]
            + (1 - tx) * ty * z[i][j + 1]
            + tx * ty * z[i + 1][j + 1]
        )


# ------------------------------------------------------------------------------------
# CSV loading
# ------------------------------------------------------------------------------------
def read_csv_table(path: str | Path, required: Sequence[str]) -> pd.DataFrame:
    """Read a CSV (``#`` comment lines allowed) and check the required columns exist.

    Extra columns are kept but ignored by the callers (hook for e.g. a later
    ``h_over_b`` ground-effect column).
    """
    path = Path(path)
    df = pd.read_csv(path, comment="#", skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}; found {list(df.columns)}")
    if df[list(required)].isna().any().any():
        raise ValueError(f"{path}: empty values in required columns (unfilled template?)")
    return df


def grid_from_long(
    df: pd.DataFrame, xcol: str, ycol: str, zcol: str
) -> tuple[list[float], list[float], list[list[float]]]:
    """Pivot a long-format (x, y, z) table into a full rectangular grid."""
    piv = df.pivot_table(index=xcol, columns=ycol, values=zcol, aggfunc="first")
    if piv.isna().any().any():
        raise ValueError(f"2-D table {zcol}({xcol}, {ycol}) is not a full rectangular grid")
    piv = piv.sort_index().sort_index(axis=1)
    return list(piv.index), list(piv.columns), piv.to_numpy().tolist()
