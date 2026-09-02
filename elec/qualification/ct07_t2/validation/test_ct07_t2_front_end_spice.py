"""Small U4-A model checks; this is screening evidence, never U5 closure."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "validation/ct07_t2_front_end.cir.in"


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is required")
def test_front_end_screen_runs_and_has_finite_outputs(tmp_path: Path) -> None:
    deck = tmp_path / "ct07_u4a.cir"
    deck.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        ["ngspice", "-b", str(deck)], capture_output=True, text=True, check=True
    )
    assert "Error" not in result.stderr
    assert re.search(r"sense_max\s*=", result.stdout, re.IGNORECASE)
    assert re.search(r"comparator_max\s*=", result.stdout, re.IGNORECASE)


def test_front_end_screen_is_not_presented_as_representative_hardware() -> None:
    text = TEMPLATE.read_text(encoding="utf-8").lower()
    assert "u4-a" in text
    assert "not u5 evidence" in text
