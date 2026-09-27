"""An authored copper UUID must keep its requested net in a saved KiCad board."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1]
TOOLS = UNIT / "tools"
KICAD_PY = Path(os.environ.get(
    "TEMPER_PCBNEW_PYTHON",
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
))

CHECK = """
import importlib.util, json, pathlib, sys
spec = importlib.util.spec_from_file_location('copper_identity', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(module.check(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]))))
"""

MUTATE = """
import pcbnew, sys
path, uuid, wrong_net = sys.argv[1:]
io = pcbnew.PCB_IO_KICAD_SEXPR()
board = io.LoadBoard(path, None)
track = next(item for item in board.GetTracks() if item.m_Uuid.AsString() == uuid)
track.SetNet(board.FindNet(wrong_net))
io.SaveBoard(path, board)
saved = io.LoadBoard(path, None)
assert next(item for item in saved.GetTracks() if item.m_Uuid.AsString() == uuid).GetNetname() == wrong_net
"""


def test_saved_route_via_net_reassignment_is_rejected(tmp_path):
    binary = os.environ.get("ZAPOTE_POWER_COPPER_IDENTITY_BIN")
    if not KICAD_PY.is_file() or not binary or not Path(binary).is_file():
        pytest.skip("requires KiCad pcbnew and the Rust copper identity binary")
    board_dir = tmp_path / "routed"
    board_dir.mkdir()
    board = board_dir / "section.kicad_pcb"
    shutil.copyfile(UNIT / "native-14/section.kicad_pcb", board)
    shutil.copyfile(UNIT / "native-14/source-manifest.json", board_dir / "source-manifest.json")
    route_dir = tmp_path / "routes"
    route_dir.mkdir()
    route = route_dir / "routes-01.json"
    shutil.copyfile(UNIT / "routes/routes-01.json", route)
    receipt_dir = board_dir / "route-receipts"
    receipt_dir.mkdir()
    receipt_path = receipt_dir / "receipt-01.json"
    replay = subprocess.run(
        [str(KICAD_PY), str(TOOLS / "apply_routes.py"), str(board),
         str(route), str(receipt_path)], capture_output=True, text=True,
    )
    assert replay.returncode == 0, replay.stderr
    receipt = json.loads(receipt_path.read_text())
    assert sum(len(op["authored_items"]) for op in receipt["operations"]) > 0

    args = [str(KICAD_PY), "-c", CHECK, str(TOOLS / "check_copper_identity.py"),
            str(board), str(route_dir)]
    baseline = subprocess.run(args, capture_output=True, text=True)
    assert baseline.returncode == 0, baseline.stderr
    assert json.loads(baseline.stdout)["status"] == "PASS"

    operation = next(op for op in receipt["operations"]
                     if any(item["kind"] == "via" for item in op["authored_items"]))
    uuid = next(item["uuid"] for item in operation["authored_items"]
                if item["kind"] == "via")
    wrong_net = "hv_ret" if operation["net"] != "hv_ret" else "bus_p"
    mutation = subprocess.run([str(KICAD_PY), "-c", MUTATE, str(board), uuid, wrong_net],
                              capture_output=True, text=True)
    assert mutation.returncode == 0, mutation.stderr
    rejected = subprocess.run(args, capture_output=True, text=True)
    assert rejected.returncode != 0
    assert f"expected net {operation['net']}, saved net {wrong_net}" in rejected.stderr
