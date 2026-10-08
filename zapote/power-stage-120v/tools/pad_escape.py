#!/usr/bin/env python3
"""Apply or verify Rust-planned, component-local pad escape rule areas.

Run with KiCad's Python. This file transports pcbnew's pad and rule-area
geometry to zapote-drc; Rust owns the area bounds, net contract and DRC rule.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import pcbnew  # type: ignore[import-not-found]

UNIT = Path(__file__).resolve().parents[1]
ZAPOTE = UNIT.parents[0]
PREFIX = "PE_"
KEEPOUT_KINDS = ("Tracks", "Vias", "Pads", "Footprints", "ZoneFills")


def rect_nm(box: object) -> dict[str, int]:
    return {
        "min_x": box.GetX(),
        "min_y": box.GetY(),
        "max_x": box.GetRight(),
        "max_y": box.GetBottom(),
    }


def observed_area(zone: object) -> dict[str, object]:
    outline = zone.Outline()
    if (not zone.GetIsRuleArea()
            or list(zone.GetLayerSet().Seq()) != [pcbnew.F_Cu]
            or any(getattr(zone, "GetDoNotAllow" + kind)()
                   for kind in KEEPOUT_KINDS)
            or outline.OutlineCount() != 1 or outline.HasHoles()
            or outline.COutline(0).PointCount() != 4):
        raise ValueError(f"{zone.GetZoneName()} is not one F.Cu no-keepout rectangle rule area")
    points = [outline.COutline(0).CPoint(i) for i in range(4)]
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    corners = {(min(xs), min(ys)), (min(xs), max(ys)),
               (max(xs), min(ys)), (max(xs), max(ys))}
    if {(point.x, point.y) for point in points} != corners or zone.GetLayer() != pcbnew.F_Cu:
        raise ValueError(f"{zone.GetZoneName()} has unexpected shape or layer")
    return {"name": zone.GetZoneName(), "rect": {
        "min_x": min(xs), "min_y": min(ys), "max_x": max(xs), "max_y": max(ys)}}


def pad_observations(board: object, requests: list[dict[str, object]]) -> list[dict[str, object]]:
    selected = {str(request["reference"]) for request in requests}
    return [
        {
            "reference": footprint.GetReference(),
            "number": pad.GetNumber(),
            "net": pad.GetNetname(),
            "centre": [pad.GetPosition().x, pad.GetPosition().y],
            "orientation_deg": pad.GetOrientationDegrees(),
            "bbox": rect_nm(pad.GetBoundingBox()),
            "shape": {pcbnew.PAD_SHAPE_RECT: "rect", pcbnew.PAD_SHAPE_ROUNDRECT: "roundrect"}
                .get(pad.GetShape(), "unsupported"),
            "front_smd": (pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                          and pad.IsOnLayer(pcbnew.F_Cu)),
        }
        for footprint in board.GetFootprints()
        if footprint.GetReference() in selected
        for pad in footprint.Pads()
    ]


def rust_plan(requests: list[dict[str, object]], pads: list[dict[str, object]],
              actual_areas: list[dict[str, object]] | None) -> dict[str, object]:
    payload = {"requests": requests, "pads": pads, "actual_areas": actual_areas}
    binary = os.environ.get("ZAPOTE_PAD_ESCAPE_BIN")
    command = ([binary] if binary else [
        "cargo", "run", "--quiet", "--locked", "--manifest-path", str(ZAPOTE / "Cargo.toml"),
        "-p", "zapote-harness", "--bin", "zapote-pad-escape",
    ])
    result = subprocess.run(command, input=json.dumps(payload), text=True,
                            capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"pad escape geometry rejected: {result.stderr.strip()}")
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--apply", action="store_true")
    action.add_argument("--verify", action="store_true")
    parser.add_argument("board", type=Path)
    parser.add_argument("--config", type=Path, default=UNIT / "pad_escapes.json")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if config.get("schema") != "power-stage.pad-escapes.v1":
        raise ValueError("unsupported pad escape manifest schema")
    requests = config["requests"]
    board = pcbnew.LoadBoard(str(args.board))
    if board is None:
        raise ValueError(f"KiCad could not load {args.board}")
    areas_on_board = [zone for zone in board.Zones()
                      if zone.GetZoneName().startswith(PREFIX)]
    actual = [observed_area(zone) for zone in areas_on_board] if args.verify else None
    plan = rust_plan(requests, pad_observations(board, requests), actual)
    if args.apply:
        for zone in areas_on_board:
            board.Remove(zone)
        for area in plan["areas"]:
            zone = pcbnew.ZONE(board)
            zone.SetIsRuleArea(True)
            zone.SetZoneName(area["name"])
            zone.SetLayer(pcbnew.F_Cu)
            for kind in KEEPOUT_KINDS:
                getattr(zone, "SetDoNotAllow" + kind)(False)
            rect = area["rect"]
            outline = zone.Outline()
            outline.NewOutline()
            for x, y in ((rect["min_x"], rect["min_y"]),
                         (rect["max_x"], rect["min_y"]),
                         (rect["max_x"], rect["max_y"]),
                         (rect["min_x"], rect["max_y"])):
                outline.Append(x, y)
            board.Add(zone)
        pcbnew.SaveBoard(str(args.board), board)
        print(f"{len(plan['areas'])} validated pad escape areas written")
    else:
        print(plan["rules"])


if __name__ == "__main__":
    main()
