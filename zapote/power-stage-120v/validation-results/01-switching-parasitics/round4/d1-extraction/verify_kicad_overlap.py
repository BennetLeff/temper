#!/usr/bin/env python3
"""Explain a phantom Q3 gate / LEG_RET overlap from unflashed pad copper.

Run with KiCad's bundled Python. Zone refill is in memory only; the board file
is never saved or modified. The intersection and area are computed by KiCad's
own polygon engine, independently of the Shapely extraction prototypes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pcbnew as pcb

EXPECTED_BOARD_SHA256 = "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155"
ZONE_UUID = "26fcc76c-3754-4241-8ae6-f6ddc92aace8"
PAD_REF = "Q3"
PAD_NUMBER = "1"
SAMPLE_MM = (131.625, 2.0)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    board_path = args.board.resolve(strict=True)
    original_sha = sha256(board_path)
    if original_sha != EXPECTED_BOARD_SHA256:
        raise ValueError(f"board changed: {original_sha}")
    board = pcb.LoadBoard(str(board_path))
    zone = next(z for z in board.Zones() if z.m_Uuid.AsString() == ZONE_UUID)
    pad = next(p for f in board.GetFootprints() if f.GetReference() == PAD_REF
               for p in f.Pads() if p.GetNumber() == PAD_NUMBER)
    if zone.GetNetname() != "leg_ret" or pad.GetNetname() != "leg_a-gate_l":
        raise ValueError("zone/pad net identity changed")
    if not zone.IsOnLayer(pcb.In1_Cu) or not pad.IsOnLayer(pcb.In1_Cu):
        raise ValueError("expected both items on In1.Cu")
    sample = pcb.VECTOR2I(pcb.FromMM(SAMPLE_MM[0]), pcb.FromMM(SAMPLE_MM[1]))

    def inspect() -> dict:
        zone_shape = zone.GetFilledPolysList(pcb.In1_Cu)
        pad_shape = pad.GetEffectivePolygon(pcb.In1_Cu)
        intersection = zone_shape.CloneDropTriangulation()
        intersection.BooleanIntersection(pad_shape)
        return {
            "zone_contains_sample": bool(zone_shape.Contains(sample)),
            "pad_contains_sample": bool(pad_shape.Contains(sample)),
            "pad_nominally_on_layer": bool(pad.IsOnLayer(pcb.In1_Cu)),
            "pad_flash_layer": bool(pad.FlashLayer(pcb.In1_Cu)),
            "pad_remove_unconnected": bool(pad.GetRemoveUnconnected()),
            "intersection_area_mm2": intersection.Area() / 1e12,
            "intersection_outline_count": intersection.OutlineCount(),
        }

    before = inspect()
    fill_succeeded = bool(pcb.ZONE_FILLER(board).Fill(board.Zones()))
    after = inspect()
    final_sha = sha256(board_path)
    if final_sha != original_sha:
        raise RuntimeError("on-disk board changed unexpectedly")
    result = {
        "board_sha256": original_sha,
        "board_sha256_after_in_memory_refill": final_sha,
        "kicad_version": pcb.Version(),
        "zone_uuid": ZONE_UUID,
        "zone_net": zone.GetNetname(),
        "zone_net_code": zone.GetNetCode(),
        "pad": f"{PAD_REF}.{PAD_NUMBER}",
        "pad_net": pad.GetNetname(),
        "pad_net_code": pad.GetNetCode(),
        "layer": "In1.Cu",
        "sample_xy_mm": SAMPLE_MM,
        "before_refill": before,
        "in_memory_refill_succeeded": fill_succeeded,
        "after_refill": after,
        "verdict": "NOMINAL_UNFLASHED_PAD_OVERLAP" if after["intersection_area_mm2"] > 0 and not after["pad_flash_layer"] else
                   "FLASHED_COPPER_OVERLAP" if after["intersection_area_mm2"] > 0 else "NO_OVERLAP",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
