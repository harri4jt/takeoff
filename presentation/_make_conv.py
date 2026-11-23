"""Background job for the slides: the full-run time-step study (cached in _gust_conv.pkl)."""

import pickle
from pathlib import Path

from bfl import load_config
from bfl.gusts import GustSettings, convergence_study

if __name__ == "__main__":
    df = convergence_study(load_config("b747_100"), GustSettings(intensity="moderate"),
                           dts=(0.04, 0.02, 0.01, 0.005), ref_dt=0.00125, n_paths=16)  # fmt: skip
    Path(__file__).with_name("_gust_conv.pkl").write_bytes(pickle.dumps(df))
    print(df.to_string())
