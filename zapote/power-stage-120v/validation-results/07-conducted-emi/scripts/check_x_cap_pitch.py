#!/usr/bin/env python3
"""Compare native-13 C1/C2 pad spacing with the exact KEMET part drawing.

Run with KiCad's Python interpreter. The manufacturer dimensions and their
source hash are in ../inputs/part_dimensions.json.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pcbnew


RESULT = Path(__file__).resolve().parents[1]
UNIT = RESULT.parents[1]
BOARD = UNIT / "native-13" / "section.kicad_pcb"
DIMENSIONS = RESULT / "inputs" / "part_dimensions.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    spec = json.loads(DIMENSIONS.read_text())
    datasheet = RESULT / spec["source"]
    actual_source_hash = sha256(datasheet)
    if actual_source_hash != spec["source_sha256"]:
        raise ValueError(f"datasheet SHA-256 changed: {actual_source_hash}")

    board = pcbnew.LoadBoard(str(BOARD))
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    result = {
        "board": str(BOARD.relative_to(UNIT)),
        "board_sha256": sha256(BOARD),
        "source": spec["source"],
        "source_sha256": actual_source_hash,
        "manufacturer_part": spec["part"],
        "manufacturer_pitch_mm": spec["lead_spacing_mm"],
        "manufacturer_pitch_tolerance_mm": spec["lead_spacing_tolerance_mm"],
        "capacitors": [],
        "mosfet_drain_tab_nets": {},
    }
    for ref in ("C1", "C2"):
        fp = footprints[ref]
        if fp.GetValue() != spec["part"]:
            raise ValueError(f"{ref}: board value {fp.GetValue()} differs from datasheet part")
        pads = {pad.GetNumber(): pad for pad in fp.Pads()}
        if set(pads) != {"1", "2"}:
            raise ValueError(f"{ref}: expected pads 1 and 2, found {sorted(pads)}")
        p1, p2 = (pads[num].GetPosition() for num in ("1", "2"))
        pitch_mm = math.hypot(p1.x - p2.x, p1.y - p2.y) / 1_000_000
        delta_mm = spec["lead_spacing_mm"] - pitch_mm
        result["capacitors"].append(
            {
                "reference": ref,
                "footprint": fp.GetFPIDAsString(),
                "pad_center_pitch_mm": pitch_mm,
                "pitch_shortfall_mm": delta_mm,
                "outside_manufacturer_tolerance": abs(delta_mm)
                > spec["lead_spacing_tolerance_mm"],
                "pad_nets": {number: pads[number].GetNetname() for number in ("1", "2")},
            }
        )
    for ref in ("Q2", "Q3", "Q5", "Q6"):
        fp = footprints[ref]
        pads = {pad.GetNumber(): pad for pad in fp.Pads()}
        result["mosfet_drain_tab_nets"][ref] = pads["2"].GetNetname()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
