#!/usr/bin/env python3
"""Capture footprint poses from a KiCad board back into poses.json.

Use after moving parts in KiCad: the captured poses feed tools/build_native.py,
so the board is regenerated from source and stays a verified projection. Only
footprint positions and rotations are captured; any copper, net or footprint
edit made in KiCad is discarded by regeneration.

Each footprint is keyed by its SourceInstance property (added by
tools/planning_stackup.py). Capture fails closed if an instance is missing,
duplicated, unknown to the source, or placed on the back side.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]


def sexpr_end(text: str, start: int) -> int:
    depth = 0
    quoted = escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    raise ValueError("unterminated KiCad expression")


def footprint_blocks(board: str) -> list[str]:
    blocks = []
    for match in re.finditer(r"\n  \(footprint ", board):
        start = match.start() + 3
        blocks.append(board[start:sexpr_end(board, start)])
    return blocks


def capture(board_path: Path, expected: set[str]) -> dict[str, list[float]]:
    poses: dict[str, list[float]] = {}
    for block in footprint_blocks(board_path.read_text(encoding="utf-8")):
        instance = re.search(r'\(property "SourceInstance" "([^"]+)"', block)
        if instance is None:
            raise ValueError("footprint without SourceInstance; generate with --stackup")
        name = instance[1]
        if name in poses:
            raise ValueError(f"duplicate SourceInstance: {name}")
        layer = re.search(r'^\(footprint "[^"]*"\s*(?:\(\w+[^()]*\)\s*)*\(layer "([^"]+)"\)', block)
        if layer is None or layer[1] != "F.Cu":
            raise ValueError(f"{name}: only front-side placement is supported")
        # The footprint's own (at ...) precedes its first property.
        head = block[: block.index("(property ")]
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", head)
        if at is None:
            raise ValueError(f"{name}: footprint has no position")
        angle = float(at[3] or 0.0) % 360.0
        poses[name] = [round(float(at[1]), 3), round(float(at[2]), 3), round(angle, 3)]
    missing = sorted(expected - poses.keys())
    extra = sorted(poses.keys() - expected)
    if missing or extra:
        raise ValueError(f"pose set differs from source: missing {missing}, extra {extra}")
    return dict(sorted(poses.items()))


def source_instances(export: Path) -> set[str]:
    components = json.loads(export.read_text(encoding="utf-8"))["components"]
    return {c["address"].split("PowerStage120V::", 1)[1] for c in components}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path, help="Placed section.kicad_pcb")
    parser.add_argument("--source", type=Path, default=UNIT / "frozen/resolved-components.json")
    parser.add_argument("--output", type=Path, default=UNIT / "poses.json")
    args = parser.parse_args()
    poses = capture(args.board, source_instances(args.source))
    args.output.write_text(json.dumps(poses, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"parts": len(poses), "output": str(args.output)}))


if __name__ == "__main__":
    main()
