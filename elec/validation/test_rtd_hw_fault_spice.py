"""Run the abstract default-high RTD fault circuit through ngspice."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DECK = ROOT / "elec/validation/rtd_hw_fault_default_high.cir"


def _case_voltages(output: str) -> dict[str, float]:
    """Parse one operating-point fault voltage after each named test case."""

    results: dict[str, float] = {}
    for case, value in re.findall(
        r"CASE_([A-Z_]+).*?v\(rtd_hw_fault\)\s*=\s*([-+0-9.eE]+)",
        output,
        re.DOTALL,
    ):
        results[case] = float(value)
    return results


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is required")
def test_default_high_rtd_fault_spice_contract() -> None:
    """A healthy window alone may hold fault low; every failure releases it."""

    result = subprocess.run(
        ["ngspice", "-b", str(DECK)],
        check=True,
        capture_output=True,
        text=True,
    )
    cases = _case_voltages(result.stdout)

    assert cases["VALID"] < 0.1
    for case in ("SHORT", "OPEN", "BROWNOUT", "RTD_AVDD_LOSS"):
        assert cases[case] > 3.0
