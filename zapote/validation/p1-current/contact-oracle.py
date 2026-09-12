#!/usr/bin/env python3
"""Create and capture an asymmetric native KiCad pad contact fixture.

The expected contact result is calculated by the Rust regression from the
captured polygons; this transport only records pcbnew's saved geometry.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pcbnew
import wx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "p2"))
from extract import extract  # noqa: E402


def xy(x: float, y: float):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def make_board(path: Path) -> None:
    board = pcbnew.BOARD()
    for a, b in [((0, 0), (40, 0)), ((40, 0), (40, 40)), ((40, 40), (0, 40)), ((0, 40), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(board)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts)
        edge.SetStart(xy(*a))
        edge.SetEnd(xy(*b))
        board.Add(edge)
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("JCONTACT")
    fp.SetPosition(xy(20, 20))
    board.Add(fp)
    pad = pcbnew.PAD(fp)
    pad.SetNumber("1")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetLayerSet(pcbnew.LSET.AllCuMask())
    pad.SetShape(pcbnew.PAD_SHAPE_OVAL)
    pad.SetSize(xy(6, 3))
    pad.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
    pad.SetDrillSize(xy(3, 1))
    pad.SetPosition(xy(22, 21))
    fp.Add(pad)
    fp.SetOrientationDegrees(30)
    pcbnew.SaveBoard(str(path), board)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_suffix(".json")
    board_path = out.with_suffix(".kicad_pcb")
    make_board(board_path)
    raw = board_path.read_bytes()
    captured = extract(board_path)["input"]
    pad = next(p for p in captured["pads"] if "@F.Cu:" in p["id"] and p["id"].startswith("JCONTACT.1:"))
    hole = next(h for h in captured["holes"] if h["id"].startswith("JCONTACT.1:"))
    result = {
        "schema": "zapote.p1-current-contact-native.v1",
        "board_sha256": hashlib.sha256(raw).hexdigest(),
        "tool_version": pcbnew.Version(),
        "board_file": str(board_path.name),
        "trace": {"start_mm": [17.9019237886, 22.3660254038], "end_mm": [26.5621778265, 17.3660254038], "width_mm": 0.8},
        "pad": pad["inner_copper_polygons"][0],
        "extractor_sha256": hashlib.sha256((ROOT / "validation/p2/extract.py").read_bytes()).hexdigest(),
        "drill": hole["polygon"],
    }
    out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    app = wx.App(False)
    main()
    del app
