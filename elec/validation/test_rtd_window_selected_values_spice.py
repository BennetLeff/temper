"""Exercise the populated RTD-window passive networks in ngspice."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DECK = ROOT / "elec/validation/rtd_window_selected_values.cir"


def _case_fault_voltages(output: str) -> dict[str, float]:
    """Return each named operating point's selected-value fault level."""

    results: dict[str, float] = {}
    for case, block in re.findall(
        r"CASE_([A-Z0-9_]+)(.*?)(?=CASE_|\Z)", output, re.DOTALL
    ):
        match = re.search(r"v\(rtd_hw_fault\)\s*=\s*([-+0-9.eE]+)", block)
        assert match is not None, f"{case} did not report RTD_HW_FAULT"
        results[case] = float(match.group(1))
    return results


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is required")
def test_selected_rtd_window_values_keep_valid_pt100_clear_and_fault_edges_high() -> None:
    """Nominal SPICE validates the captured RREF/reference/divider topology."""

    result = subprocess.run(
        ["ngspice", "-b", str(DECK)], check=True, capture_output=True, text=True
    )
    cases = _case_fault_voltages(result.stdout)

    for case in ("VALID_100R", "VALID_194R1"):
        assert cases[case] < 0.1
    for case in ("SHORT_10R", "OPEN_300R", "AVDD_BROWNOUT"):
        assert cases[case] > 3.0
