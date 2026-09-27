"""Fail-closed evidence checks for route replay and plan-view insulation."""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1]
TOOLS = UNIT / "tools"
NATIVE04 = UNIT / "native-04" / "section.kicad_pcb"
PLACEMENT = UNIT / "native-12"  # current placement (JLCPCB stackup)
KICAD_PY = Path(os.environ.get(
    "TEMPER_PCBNEW_PYTHON",
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
))


def run_kicad(script, *args):
    if not KICAD_PY.is_file():
        pytest.skip("KiCad pcbnew Python is not installed")
    return subprocess.run([str(KICAD_PY), str(TOOLS / script), *map(str, args)],
                          capture_output=True, text=True)


def append_pcb_item(board, text):
    source = NATIVE04.read_text()
    board.write_text(source.rstrip()[:-1] + text + "\n)\n")


def test_replay_rejects_stale_two_layer_placement_before_output(tmp_path):
    output = tmp_path / "result"
    result = run_kicad("route_board.py", UNIT / "native-04", output)
    assert result.returncode != 0
    assert "stale" in result.stderr or "wrong enabled copper layers" in result.stderr
    assert not output.exists()


def test_replay_never_deletes_an_existing_output(tmp_path):
    output = tmp_path / "result"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("must survive")
    result = run_kicad("route_board.py", UNIT / "native-04", output)
    assert result.returncode != 0
    assert "refusing to replace" in result.stderr
    assert sentinel.read_text() == "must survive"


@pytest.mark.parametrize("source_name", ["default.net", "default.csv", "resolved-components.json"])
def test_replay_rejects_placement_with_stale_frozen_source(tmp_path, source_name):
    placement = tmp_path / "placement"
    placement.mkdir()
    for name in ("section.kicad_pcb", "source-manifest.json"):
        shutil.copyfile(PLACEMENT / name, placement / name)
    baseline = subprocess.run(
        [str(KICAD_PY), "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
         "import route_board; from pathlib import Path; "
         "route_board.preflight(Path(sys.argv[2]), Path(sys.argv[3]))",
         str(TOOLS), str(placement), str(tmp_path / "routed")],
        capture_output=True, text=True,
    )
    assert baseline.returncode == 0, baseline.stderr
    manifest_path = placement / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["input_hashes"][source_name] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    output = tmp_path / "routed"
    result = run_kicad("route_board.py", placement, output)
    assert result.returncode != 0
    assert f"placement was generated from stale {source_name}" in result.stderr
    assert not output.exists()


def test_copper_dump_rejects_arc_instead_of_serializing_a_chord(tmp_path):
    board = tmp_path / "arc.kicad_pcb"
    append_pcb_item(board, '''
    (arc (start 105 40) (mid 123.555 50.875) (end 142 40)
      (width 0.5) (layer "B.Cu") (net "bus_p")
      (uuid "d75c388d-f612-453d-a0de-a1143fab44d4"))''')
    out = tmp_path / "copper.json"
    result = run_kicad("copper_dump.py", board, out)
    assert result.returncode != 0
    assert "unsupported copper track shape: PCB_ARC" in result.stderr
    assert not out.exists()


def test_copper_dump_rejects_unfilled_zone(tmp_path):
    board = tmp_path / "unfilled.kicad_pcb"
    append_pcb_item(board, '''
    (zone (net "bus_p") (layer "F.Cu")
      (uuid "e29dd503-bb23-400c-9df0-f0080ac47642")
      (hatch edge 0.5) (connect_pads yes (clearance 0.3))
      (min_thickness 0.25)
      (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))
      (polygon (pts (xy 120 60) (xy 130 60) (xy 130 70) (xy 120 70))))''')
    out = tmp_path / "copper.json"
    result = run_kicad("copper_dump.py", board, out)
    assert result.returncode != 0
    assert "unfilled copper zone" in result.stderr
    assert not out.exists()


@pytest.mark.parametrize("script,function", [
    ("copper_dump.py", "dump"),
    ("check_native_parity.py", "extract"),
])
def test_saved_board_change_during_extraction_is_rejected(tmp_path, script, function):
    if not KICAD_PY.is_file():
        pytest.skip("KiCad pcbnew Python is not installed")
    board = tmp_path / "section.kicad_pcb"
    shutil.copyfile(PLACEMENT / "section.kicad_pcb", board)
    code = """
import importlib.util
import pathlib
import pcbnew
import sys
real_load = pcbnew.LoadBoard
def concurrent_save(path):
    loaded = real_load(path)
    with open(path, 'ab') as board:
        board.write(b'\\n')
    return loaded
pcbnew.LoadBoard = concurrent_save
spec = importlib.util.spec_from_file_location('adapter', sys.argv[1])
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
getattr(adapter, sys.argv[2])(pathlib.Path(sys.argv[3]))
"""
    result = subprocess.run(
        [str(KICAD_PY), "-c", code, str(TOOLS / script), function, str(board)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "board changed during" in result.stderr


@pytest.mark.parametrize("source_name", ["default.net", "default.csv", "resolved-components.json"])
def test_native_parity_rejects_mutated_frozen_source(tmp_path, source_name):
    binary_name = os.environ.get("ZAPOTE_POWER_NATIVE_PARITY_BIN")
    if not binary_name or not Path(binary_name).is_file():
        pytest.skip("native parity binary is not built")
    binary = Path(binary_name)
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    for name in ("default.net", "default.csv", "resolved-components.json"):
        shutil.copyfile(UNIT / "frozen" / name, frozen / name)
    args = (PLACEMENT / "section.kicad_pcb", PLACEMENT / "source-manifest.json",
            frozen / "default.net", binary)
    baseline = run_kicad("check_native_parity.py", *args)
    assert baseline.returncode == 0, baseline.stderr
    with (frozen / source_name).open("ab") as source:
        source.write(b"\n")
    result = run_kicad("check_native_parity.py", *args)
    assert result.returncode != 0
    assert f"frozen {source_name} hash differs" in result.stderr


def test_real_pcbnew_adapter_rejects_saved_pad_net_mutation(tmp_path):
    binary = os.environ.get("ZAPOTE_POWER_NATIVE_PARITY_BIN")
    if not binary or not Path(binary).is_file() or not KICAD_PY.is_file():
        pytest.skip("requires the native parity binary and KiCad Python")
    board = tmp_path / "section.kicad_pcb"
    shutil.copyfile(PLACEMENT / "section.kicad_pcb", board)
    args = (board, PLACEMENT / "source-manifest.json", UNIT / "frozen/default.net", binary)
    baseline = run_kicad("check_native_parity.py", *args)
    assert baseline.returncode == 0, baseline.stderr
    code = """
import pcbnew, sys
b = pcbnew.LoadBoard(sys.argv[1])
fp = next(fp for fp in b.GetFootprints() if fp.GetReference() == 'J4')
pad = next(p for p in fp.Pads() if p.GetNumber() == '1')
assert pad.GetNetname() == 'v15_selv'
pad.SetNet(b.FindNet('selv_gnd'))
pcbnew.SaveBoard(sys.argv[1], b)
"""
    mutation = subprocess.run([str(KICAD_PY), "-c", code, str(board)],
                              capture_output=True, text=True)
    assert mutation.returncode == 0, mutation.stderr
    result = run_kicad("check_native_parity.py", *args)
    assert result.returncode != 0
    assert "J4" in result.stderr and "selv_gnd" in result.stderr


def load_barrier():
    spec = importlib.util.spec_from_file_location("barrier_check", TOOLS / "barrier_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def envelope(tmp_path, barrier):
    board = tmp_path / "board.kicad_pcb"
    board.write_text("board evidence identity")
    items = [
        {"kind": "pad", "ref": "U1.1", "net": "pwm_ha", "layers": ["F.Cu"],
         "box": [0, 0, 1, 1]},
        {"kind": "pad", "ref": "R1.1", "net": "bus_p", "layers": ["B.Cu"],
         "box": [20, 20, 21, 21]},
    ]
    return {"schema": barrier.SCHEMA, "board_path": str(board),
            "board_sha256": hashlib.sha256(board.read_bytes()).hexdigest(),
            "copper_layers": ["F.Cu", "B.Cu"],
            "census": {"footprints": 2, "pads": 2, "tracks": 0, "vias": 0,
                       "zones": 0, "filled_zone_polygons": 0, "items": 2},
            "items_sha256": barrier.hashlib.sha256(json.dumps(
                items, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()).hexdigest(), "items": items}


def test_barrier_evidence_detects_cross_layer_overlap_and_stale_board(tmp_path):
    barrier = load_barrier()
    evidence = envelope(tmp_path, barrier)
    assert barrier.check(evidence, 8.0)["violations"] == 0
    evidence["items"][1]["box"] = [0.5, 0.5, 1.5, 1.5]
    evidence["items_sha256"] = barrier.hashlib.sha256(json.dumps(
        evidence["items"], sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    result = barrier.check(evidence, 8.0)
    assert result["violations"] == result["cross_layer"] == 1
    Path(evidence["board_path"]).write_text("changed board")
    with pytest.raises(ValueError, match="stale"):
        barrier.check(evidence, 8.0)


def test_barrier_rejects_unsupported_or_missing_copper(tmp_path):
    barrier = load_barrier()
    evidence = envelope(tmp_path, barrier)
    evidence["items"][1]["kind"] = "arc"
    evidence["items_sha256"] = barrier.hashlib.sha256(json.dumps(
        evidence["items"], sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    with pytest.raises(ValueError, match="unsupported copper item kinds"):
        barrier.check(evidence, 8.0)
