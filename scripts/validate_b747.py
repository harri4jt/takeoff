"""Compare the 747-100 model against Boeing's published FAR takeoff field lengths.

Reference: Boeing D6-58326 "747 Airplane Characteristics for Airport Planning",
sec. 3.3.1 "F.A.R. takeoff runway-length requirements, standard day, model 747-100
(JT9D-3A engines)", sea-level (0 ft) curve, digitized. Archived copy:
web.archive.org/web/20121014235349/http://www.boeing.com/commercial/airports/acaps/747_123sp.pdf

python scripts/validate_b747.py        -> table on stdout + output/b747_validation.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from bfl import compute_bfl, load_config

ROOT = Path(__file__).resolve().parents[1]

# Boeing sea-level standard-day curve: (brake-release weight [1000 lb], FAR length [ft])
BOEING_SL = [
    (500, 4880), (520, 4910), (540, 5180), (560, 5520), (580, 5880), (620, 6750),
    (640, 7220), (660, 7750), (680, 8360), (690, 8720), (705, 9230),
]


def main() -> None:
    rows = []
    for w, ref in BOEING_SL:
        cfg = load_config("b747_100", overrides={"environment.weight_lbf": w * 1000.0})
        r = compute_bfl(cfg)
        rows.append((w, ref, r.faa_field_length_ft, r.bfl_ft, r.v1_kts, r.vr_kts, r.v2_kts))

    print(f"{'W klb':>6} {'Boeing':>7} {'model':>7} {'err':>6} {'BFL':>7}  V1/VR/V2 [KEAS]")
    for w, ref, far, bfl, v1, vr, v2 in rows:
        print(f"{w:6.0f} {ref:7.0f} {far:7.0f} {100 * (far / ref - 1):+5.1f}% {bfl:7.0f}"
              f"  {v1:.0f}/{vr:.0f}/{v2:.0f}")

    fig, ax = plt.subplots(figsize=(7, 4.5))
    w = [r[0] for r in rows]
    ax.plot(w, [r[1] for r in rows], "o-", color="k", label="Boeing D6-58326 (sea level, std day)")
    ax.plot(w, [r[2] for r in rows], "s-", color="C0", label="model: FAR field length")
    ax.plot(w, [r[3] for r in rows], "^--", color="C1", label="model: balanced field length")
    ax.set_xlabel("brake-release weight [1000 lb]")
    ax.set_ylabel("runway length [ft]")
    ax.set_title("747-100, flaps 20, sea level ISA")
    ax.grid(alpha=0.3)
    ax.legend()
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(out / "b747_validation.png", dpi=150)
    print(f"saved {out / 'b747_validation.png'}")


if __name__ == "__main__":
    main()
