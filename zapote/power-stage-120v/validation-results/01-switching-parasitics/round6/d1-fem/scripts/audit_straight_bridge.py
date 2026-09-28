"""Check the unmodified native-17 TO-247 pad positions for G–S bridges.

A straight G–S conductive strip crosses pad 2 (drain) on each device.  This
is a negative geometry control only; it does not construct or accept a dogleg.
"""

import argparse
import json
from pathlib import Path

import pcbnew


def audit(board_path: Path) -> dict:
    board = pcbnew.LoadBoard(str(board_path))
    footprints = {item.GetReference(): item for item in board.GetFootprints()}
    result = {}
    for reference in ("Q2", "Q3", "Q5", "Q6"):
        pads = {pad.GetNumber(): pad for pad in footprints[reference].Pads()}
        if set(pads) != {"1", "2", "3"}:
            raise ValueError(f"{reference}: expected G/D/S pads 1/2/3, found {sorted(pads)}")
        points = {number: (pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y))
                  for number, pad in pads.items()}
        gate, drain, source = (points[number] for number in ("1", "2", "3"))
        gx, gy = gate
        dx, dy = drain
        sx, sy = source
        span_sq = (sx - gx) ** 2 + (sy - gy) ** 2
        cross_mm2 = (dx - gx) * (sy - gy) - (dy - gy) * (sx - gx)
        projection = ((dx - gx) * (sx - gx) + (dy - gy) * (sy - gy)) / span_sq
        drain_center_on_segment = abs(cross_mm2) < 1e-8 and 0 < projection < 1
        if not drain_center_on_segment:
            raise ValueError(f"{reference}: expected negative control did not reproduce")
        result[reference] = {"gate_pad1_mm": gate, "drain_pad2_mm": drain,
                             "source_pad3_mm": source, "drain_projection": projection,
                             "drain_center_on_straight_gate_source_segment": True}
    return {"board": str(board_path), "negative_control": result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.board), indent=2))
