"""Ask KiCad whether PCB copper bypasses R5's internal Kelvin connection."""

import json
import os
from pathlib import Path
import subprocess

import pytest

UNIT = Path(__file__).resolve().parents[1]
KICAD_PY = Path(os.environ.get(
    "TEMPER_PCBNEW_PYTHON",
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
))

PROBE = """
import json, sys, pcbnew
board = pcbnew.LoadBoard(sys.argv[1])
shunt = next(f for f in board.GetFootprints() if f.GetReference() == 'R5')
pads = {p.GetNumber(): p for p in shunt.Pads()}
assert pads['1'].GetNetname() == pads['2'].GetNetname() == 'leg_ret'
if sys.argv[2] == 'bridge':
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pads['1'].GetPosition())
    track.SetEnd(pads['2'].GetPosition())
    track.SetWidth(pcbnew.FromMM(0.3))
    track.SetLayer(pcbnew.F_Cu)
    track.SetNetCode(pads['1'].GetNetCode())
    board.Add(track)
board.BuildConnectivity()
connectivity = board.GetConnectivity()
clusters = [{x.m_Uuid.AsString() for x in connectivity.GetConnectedItems(pads[n])}
            for n in ('1', '2')]
print(json.dumps({'shared_items': len(clusters[0] & clusters[1]),
                  'cluster_sizes': [len(c) for c in clusters]}))
"""


@pytest.mark.parametrize("mutation", ["original", "bridge"])
def test_kelvin_pickup_is_separate_and_a_copper_bridge_is_detected(mutation):
    if not KICAD_PY.is_file():
        pytest.skip("KiCad pcbnew Python is not installed")
    result = subprocess.run(
        [str(KICAD_PY), "-c", PROBE,
         str(UNIT / "native-17/section.kicad_pcb"), mutation],
        capture_output=True, text=True, check=True,
    )
    evidence = json.loads(result.stdout)
    assert min(evidence["cluster_sizes"]) > 1
    if mutation == "original":
        assert evidence["shared_items"] == 0, "PCB copper bypasses R5's Kelvin pickup"
    else:
        assert evidence["shared_items"] > 0, "KiCad missed an injected current-to-sense bridge"
