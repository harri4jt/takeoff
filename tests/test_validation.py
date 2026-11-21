"""Validation against published data (writes app/assets/validation/<aircraft>/).

The app's data pages show the figures and a pass/fail badge from these runs.
"""

from __future__ import annotations

import pytest

from bfl.validation import read_status, validate_b747, validate_sr71


@pytest.mark.parametrize("validate", [validate_b747, validate_sr71], ids=["b747_100", "sr71"])
def test_validation(validate):
    status = validate(write=True)
    assert read_status(status.aircraft)["data_hash"] == status.data_hash
    failed = [f"{c.name}: model {c.model:.1f} vs {c.reference:.1f} {c.unit} ({c.detail})"
              for c in status.checks if not c.passed]  # fmt: skip
    assert status.passed, f"{status.tolerance}; failed: {failed}"
