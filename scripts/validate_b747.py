"""Compare the 747-100 model against Boeing's published FAR takeoff field lengths.

Reference: Boeing D6-58326 "747 Airplane Characteristics for Airport Planning",
sec. 3.3.1 "F.A.R. takeoff runway-length requirements, standard day, model 747-100
(JT9D-3A engines)", sea-level curve, digitized. Archived copy:
web.archive.org/web/20121014235349/http://www.boeing.com/commercial/airports/acaps/747_123sp.pdf

python scripts/validate_b747.py   -> table on stdout; figures + status.json in
                                     app/assets/validation/b747_100/ (same as the test suite)
"""

from __future__ import annotations

from bfl.validation import OUT_ROOT, validate_b747


def main() -> None:
    st = validate_b747(write=True)
    print(f"{'W klb':>6} {'Boeing':>7} {'model':>7} {'err':>6} {'BFL':>7} {'+GE':>7}")
    for r in st.extra["rows"]:
        err = 100 * (r["model_field_ft"] / r["boeing_ft"] - 1)
        print(
            f"{r['weight_klb']:6.0f} {r['boeing_ft']:7.0f} {r['model_field_ft']:7.0f} "
            f"{err:+5.1f}% {r['model_bfl_ft']:7.0f} {r['model_field_ground_effect_ft']:7.0f}"
        )
    print(f"{'PASS' if st.passed else 'FAIL'}: {st.tolerance}")
    print(f"saved {OUT_ROOT / 'b747_100'}")


if __name__ == "__main__":
    main()
