"""Trade studies: solve a grid of cases, varying any inputs, and get one table back.

    from bfl import load_config, trade_study
    cfg = load_config("b747_100")
    df = trade_study(cfg, {"multipliers.k_CL": [0.9, 1.0, 1.1],
                           "multipliers.k_CD": [0.9, 1.0, 1.1]})

Every combination of the varied values (a full grid) is one ``compute_bfl`` solve. The
keys are the same dotted paths as ``load_config(overrides=...)`` (e.g.
``environment.weight_lbf``, ``environment.temperature_F``, ``environment.mu_brake``).

Speed:
* Cases run in parallel processes (``workers``; 1 = serial).
* The cases are solved in runs along the LAST varied input, outward from its middle
  value, and each case passes its optimal rotation speed to the next as a warm start
  for the VR optimizer (see docs/assumptions/rotation_speed.md). Put the input that changes the
  answer most smoothly last, and give it the most values.
"""

from __future__ import annotations

import itertools
import math
import multiprocessing
import os
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import Executor, ProcessPoolExecutor
from typing import Any

import pandas as pd

from .bfl import compute_bfl
from .config import RunConfig
from .landing import compute_landing

#: columns returned by default (any BFLResult.scalars() key can be asked for)
DEFAULT_OUTPUTS = (
    "runway_required_ft",
    "field_length_ft",
    "landing_runway_required_ft",
    "bfl_ft",
    "aeo_distance_ft",
    "balanced",
    "v1_kts",
    "vr_kts",
    "v2_kts",
    "k_VR",
    "max_tire_speed_kts",
    "brake_energy_MJ",
)
#: extra outputs: anything in LandingResult.scalars() ("landing_..."), and
#: "runway_required_ft" = max(takeoff field length, landing runway required)
LANDING_PREFIX = "landing_"

# forkserver: forking a process that has threads (the app's server) can deadlock
_MP = multiprocessing.get_context("forkserver")


def _needs_landing(outputs: Sequence[str]) -> bool:
    return any(o.startswith(LANDING_PREFIX) or o == "runway_required_ft" for o in outputs)


def _solve_run(args: tuple):
    """Solve cases that differ only in ``key`` (in the given order), warm-starting VR.
    ``order`` is each case's position in the grid, so rows can be put back in order."""
    cfg_json, fixed, key, values, order, outputs, warm = args
    base = RunConfig.model_validate_json(cfg_json)
    hint: float | None = None
    rows = []
    for v, pos in zip(values, order, strict=True):
        row: dict[str, Any] = {"_pos": pos, **fixed, key: v}
        try:
            case = base.with_updates({**fixed, key: v})
            r = compute_bfl(case, vr_hint=hint if warm else None)
            hint = r.k_VR
            sc = r.scalars()
            if _needs_landing(outputs):
                sc.update(compute_landing(case).scalars())
                sc["runway_required_ft"] = max(
                    sc["field_length_ft"], sc["landing_runway_required_ft"]
                )
            row.update({o: sc.get(o) for o in outputs})
            row["error"] = ""
        except Exception as exc:  # noqa: BLE001 - one failed case must not stop the study
            row.update({o: math.nan for o in outputs})
            row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
    return rows


def _outward(n: int) -> list[tuple[int, ...]]:
    """Index runs over 0..n-1: middle -> end, and just below the middle -> start."""
    mid = n // 2
    return [r for r in (tuple(range(mid, n)), tuple(range(mid - 1, -1, -1))) if r]


def trade_study(
    config: RunConfig,
    vary: Mapping[str, Iterable[float]],
    outputs: Sequence[str] = DEFAULT_OUTPUTS,
    workers: int | None = None,
    warm_start: bool = True,
    executor: Executor | None = None,
) -> pd.DataFrame:
    """Solve every combination of ``vary`` and return one row per case.

    Args:
        config: the base case (from ``load_config``).
        vary: {dotted path: values}. All combinations are solved (a full grid).
        outputs: result columns, any key of ``BFLResult.scalars()``, of
            ``LandingResult.scalars()`` (``landing_...``; the landing is then solved too),
            or ``runway_required_ft`` = max(takeoff field length, landing runway).
        workers: parallel processes (default: CPU count - 1; 1 = serial).
        warm_start: pass each case's optimal k_VR to the next along the last input.
        executor: an existing executor to use instead of starting processes (the app
            keeps one alive between studies).

    Returns:
        DataFrame with one column per varied path, then ``outputs``, then ``error``
        (empty when the case solved; failed cases have NaN outputs). Rows are in grid
        order (the last varied path changes fastest).
    """
    if not vary:
        raise ValueError("vary needs at least one input to change")
    keys = list(vary)
    values = {k: tuple(float(x) for x in vary[k]) for k in keys}
    if any(len(v) == 0 for v in values.values()):
        raise ValueError("every varied input needs at least one value")
    config.with_updates({k: v[0] for k, v in values.items()})  # fail early on a bad path
    # only scalars come back, so skip the evenly sampled (RK4) display trajectories
    cfg_json = config.with_updates({"solver.trajectory_dt_s": None}).model_dump_json()
    last, outer = keys[-1], keys[:-1]
    outs = tuple(outputs)

    n = len(values[last])
    jobs = []
    for c, combo in enumerate(itertools.product(*(values[k] for k in outer))):
        fixed = dict(zip(outer, combo, strict=True))
        for idx in _outward(n):
            vals = tuple(values[last][i] for i in idx)
            jobs.append((cfg_json, fixed, last, vals, tuple(c * n + i for i in idx), outs,
                         warm_start))  # fmt: skip

    if workers is None:
        workers = max(1, (os.cpu_count() or 2) - 1)
    if executor is not None:
        chunks = list(executor.map(_solve_run, jobs))
    elif workers > 1 and len(jobs) > 1:
        try:
            with ProcessPoolExecutor(mp_context=_MP, max_workers=min(workers, len(jobs))) as ex:
                chunks = list(ex.map(_solve_run, jobs))
        except Exception:  # noqa: BLE001 - no usable process pool here: run serially
            chunks = [_solve_run(j) for j in jobs]
    else:
        chunks = [_solve_run(j) for j in jobs]

    df = pd.DataFrame([row for chunk in chunks for row in chunk])
    return df.sort_values("_pos").drop(columns="_pos").reset_index(drop=True)


def grid(df: pd.DataFrame, x: str, y: str, value: str) -> pd.DataFrame:
    """One output as a 2-D table: rows = ``y`` values, columns = ``x`` values."""
    missing = [c for c in (x, y, value) if c not in df.columns]
    if missing:
        raise KeyError(
            f"column(s) {missing} not in the study; columns are {list(df.columns)} "
            "(ask for more with trade_study(..., outputs=...))"
        )
    return df.pivot_table(index=y, columns=x, values=value, aggfunc="first")
