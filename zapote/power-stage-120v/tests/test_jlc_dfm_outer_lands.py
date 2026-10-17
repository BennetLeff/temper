"""Every plated through-hole pad needs copper on both outer layers.

KiCad's DRC accepts a PTH pad whose outer copper was removed by
remove_unused_layers; tools/jlc_dfm_check.py must not.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1]
BOARD = UNIT / "native-17" / "section.kicad_pcb"
KICAD_PY = Path(os.environ.get(
    "TEMPER_PCBNEW_PYTHON",
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
))

STRIP = """
import pcbnew, sys
board = pcbnew.LoadBoard(sys.argv[1])
fp = next(f for f in board.GetFootprints() if f.GetReference() == "C38")
for pad in fp.Pads():
    pad.SetRemoveUnconnected(True)
    pad.SetKeepTopBottom(False)
pcbnew.SaveBoard(sys.argv[1], board)
"""


def run_check(board: Path) -> dict:
    result = subprocess.run([str(KICAD_PY), str(UNIT / "tools/jlc_dfm_check.py"), str(board)],
                            capture_output=True, text=True)
    return json.loads(result.stdout)


@pytest.mark.skipif(not KICAD_PY.exists(), reason="KiCad Python not installed")
def test_current_board_has_outer_lands_on_every_pth_pad():
    report = run_check(BOARD)
    assert [f for f in report["failures"] if f["kind"] == "pth_outer_land_missing"] == []


@pytest.mark.skipif(not KICAD_PY.exists(), reason="KiCad Python not installed")
def test_stripped_outer_lands_are_rejected(tmp_path):
    for name in ("section.kicad_pcb", "section.kicad_pro", "section.kicad_dru", "fp-lib-table"):
        if (BOARD.parent / name).exists():
            shutil.copy(BOARD.parent / name, tmp_path / name)
    board = tmp_path / "section.kicad_pcb"
    subprocess.run([str(KICAD_PY), "-c", STRIP, str(board)], check=True, capture_output=True)
    report = run_check(board)
    missing = {f["ref"] for f in report["failures"] if f["kind"] == "pth_outer_land_missing"}
    assert report["status"] == "FAIL"
    assert {"C38.1", "C38.2"} <= missing
