"""Run one BFL computation, print the summary and save figures to output/.

python scripts/run_example.py                         # synthetic widebody
python scripts/run_example.py --aircraft <name> --headwind 10 --kcl 1.1
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import matplotlib.pyplot as plt

from bfl import compute_bfl, load_config, sweep_v1
from bfl.plotting import bfl_chart, time_histories

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--aircraft", default="generic_widebody_synthetic")
    ap.add_argument("--run-yaml", default=None, help="optional YAML with run settings")
    ap.add_argument("--kcl", type=float, default=None, help="CL multiplier")
    ap.add_argument("--kcd", type=float, default=None, help="CD multiplier")
    ap.add_argument("--headwind", type=float, default=None, help="headwind [kts]")
    ap.add_argument("--method", choices=["rk4", "rk45"], default=None)
    ap.add_argument("--out", default=str(ROOT / "output"))
    a = ap.parse_args()

    overrides = {}
    if a.kcl is not None:
        overrides["multipliers.k_CL"] = a.kcl
    if a.kcd is not None:
        overrides["multipliers.k_CD"] = a.kcd
    if a.headwind is not None:
        overrides["environment.headwind_kts"] = a.headwind
    if a.method is not None:
        overrides["solver.method"] = a.method
    cfg = load_config(a.aircraft, a.run_yaml, overrides)

    t0 = time.perf_counter()
    result = compute_bfl(cfg)
    dt = time.perf_counter() - t0
    print(result.summary())
    print(f"\n(solved in {dt:.2f} s, {cfg.solver.method}, dt = {cfg.solver.dt_s} s)")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    sweep = sweep_v1(cfg, n=21)
    ax = bfl_chart(sweep, result)
    ax.figure.savefig(out / "bfl_chart.png", bbox_inches="tight")
    plt.close(ax.figure)
    time_histories(result, out / "time_histories.png")
    sweep.to_csv(out / "v1_sweep.csv", index=False)
    result.go.to_dataframe().to_csv(out / "go_trajectory.csv", index=False)
    result.stop.to_dataframe().to_csv(out / "stop_trajectory.csv", index=False)
    (out / "result.json").write_text(result.to_json())
    print(f"figures and CSVs written to {out}")


if __name__ == "__main__":
    main()
