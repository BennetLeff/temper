"""Fail-closed evidence checks for route replay and plan-view insulation."""

import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1]
TOOLS = UNIT / "tools"
NATIVE04 = UNIT / "native-04" / "section.kicad_pcb"
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


def load_barrier():
    pytest.importorskip("shapely")
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
