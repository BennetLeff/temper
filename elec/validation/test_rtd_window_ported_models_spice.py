"""Validate the RTD safety circuit with portable ngspice component macros."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DECK = ROOT / "elec/validation/rtd_window_ported_models.cir"


def _fault_cases(output: str) -> dict[str, float]:
    """Extract the fault net voltage after each named operating point."""

    cases: dict[str, float] = {}
    for name, block in re.findall(r"CASE_([A-Z0-9_]+)(.*?)(?=CASE_|\Z)", output, re.DOTALL):
        match = re.search(r"v\(rtd_hw_fault\)\s*=\s*([-+0-9.eE]+)", block)
        assert match is not None, f"{name} did not report RTD_HW_FAULT"
        cases[name] = float(match.group(1))
    return cases


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is required")
def test_ported_component_models_preserve_rtd_fail_safe_truth_table() -> None:
    """A clear condition alone may sink the fault; every fault releases it."""

    result = subprocess.run(
        ["ngspice", "-b", str(DECK)], capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"ngspice exited {result.returncode}\n"
        f"--- stderr ---\n{result.stderr}\n--- stdout tail ---\n{result.stdout[-2000:]}"
    )
    cases = _fault_cases(result.stdout)
    for name in ("VALID_100R", "VALID_194R1"):
        assert cases[name] < 0.1
    for name in ("SHORT_10R", "OPEN_300R", "AVDD_BROWNOUT", "AVDD_LOSS"):
        assert cases[name] > 3.0
