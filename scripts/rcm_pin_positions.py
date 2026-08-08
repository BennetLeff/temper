#!/usr/bin/env python3
"""Read-only extraction of per-net pin positions and per-component centroid
positions from pcb/temper.kicad_pcb, using the project's own kicad_parser
(temper_placer.io.kicad_parser.parse_kicad_pcb) -- never an ad hoc
s-expression parse of copper. Used only for spatial region mapping in the
placement-remediation evidence doc; writes no board file.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("pin_positions.json")

sys.path.insert(0, str(REPO_ROOT))

from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402

parsed = parse_kicad_pcb(REPO_ROOT / "pcb" / "temper.kicad_pcb")

net_pins: dict[str, list[dict]] = defaultdict(list)
comp_pins: dict[str, list[tuple[float, float]]] = defaultdict(list)

for p in parsed.pads:
    if not p.net:
        continue
    net_pins[p.net].append(
        {"ref": p.component_ref, "x": p.position[0], "y": p.position[1], "layer": p.layer}
    )
    comp_pins[p.component_ref].append((p.position[0], p.position[1]))

comp_centroid = {}
comp_bbox = {}
for ref, pts in comp_pins.items():
    xs = [x for x, y in pts]
    ys = [y for x, y in pts]
    comp_centroid[ref] = (sum(xs) / len(xs), sum(ys) / len(ys))
    comp_bbox[ref] = (min(xs), min(ys), max(xs), max(ys))

out = {
    "board_origin": list(parsed.board.origin),
    "board_width": parsed.board.width,
    "board_height": parsed.board.height,
    "net_pins": net_pins,
    "component_centroid": comp_centroid,
    "component_bbox": comp_bbox,
    "component_pad_count": {ref: len(pts) for ref, pts in comp_pins.items()},
}
OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
print(f"Wrote {OUT}: {len(net_pins)} nets, {len(comp_pins)} components")
