#!/usr/bin/env python3
"""Apply the power stage's plated-through-hole pad layer policy.

    python3 tools/pth_layer_policy.py <native-placement-dir>

Every PTH pad keeps copper on both outer layers (a solder land and an outer
barrel ring) and drops its ring on any inner layer where nothing connects to
it (KiCad remove_unused_layers + keep_end_layers). Unconnected inner rings
add no current path; removing them keeps mains and HOT inner-layer copper
away from other nets.

This is a deliberate rule, applied to the placement board by
tools/build_native.py (so the route receipt chain starts from it).
Native-08..15 got the inner removal by accident, from a footprint parser
that read "(remove_unused_layers no)" as yes, and without keep_end_layers,
which also stripped 23 pads of both outer lands.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

PTH = re.compile(r'^(\s*\(pad "[^"]*" thru_hole .*\(layers \*\.Cu \*\.Mask\)(?: \(roundrect_rratio [0-9.]+\))?)$', re.M)
FLAGS = " (remove_unused_layers yes) (keep_end_layers yes)"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply(output: Path) -> int:
    board_path, manifest_path = output / "section.kicad_pcb", output / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if sha256(board_path) != manifest["board_sha256"]:
        raise ValueError("placement board differs from its source manifest")
    board = board_path.read_text()
    if "remove_unused_layers" in board or "keep_end_layers" in board:
        raise ValueError("placement board already carries pad layer flags")
    total = len(re.findall(r'\(pad "[^"]*" thru_hole ', board))
    board, count = PTH.subn(lambda m: m.group(1) + FLAGS, board)
    if count != total:
        raise ValueError(f"policy matched {count} of {total} PTH pads")
    manifest["input_hashes"]["pth_layer_policy.py"] = sha256(Path(__file__))
    manifest["board_sha256"] = hashlib.sha256(board.encode()).hexdigest()
    board_path.write_text(board)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return count


if __name__ == "__main__":
    print(f"{apply(Path(sys.argv[1]))} PTH pads: inner rings removed where unconnected, outer lands kept")
