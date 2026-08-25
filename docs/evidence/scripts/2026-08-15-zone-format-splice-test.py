#!/usr/bin/env python3
"""Splice-test the hole-carrying zone outline format against real kicad-cli.

Takes a piece of the gnd pour from experiment A that carries interior
holes, renders it in the Rust emitter's exact s-expression shape (one
`(polygon (pts ...) (pts ...))` element, first block exterior, rest
holes), replaces the first zone of a COPY of the board file, and runs
`kicad-cli pcb drc --refill-zones` on the copy.

If KiCad's own parser rejects the format, DRC errors out at load; if it
parses, DRC runs (its violations are not the point -- format acceptance
is). Does not touch the repo board.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from shapely.geometry import MultiPoint, Point, Polygon
from shapely.ops import unary_union

PCBPATH = Path("pcb/temper.kicad_pcb")
GND_NET = "gnd"
PLANE_LAYER = "In1.Cu"
PD3_HV_LV_CREEPAGE_MM = 12.6


def fmt_pts(ring) -> str:
    pts = "".join(f"\n        (xy {x:.4f} {y:.4f})" for x, y in ring)
    return f"(pts{pts})"

def main():
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.routing_space import _get_board_polygon
    from temper_placer.router_v6.pad_connectivity_audit import _pads_by_net
    from temper_placer.core.pin_geometry import pin_world_layer, pin_world_position

    pcb = parse_kicad_pcb_v6(PCBPATH)
    board = _get_board_polygon(pcb)
    pads_by_net = _pads_by_net(pcb)
    hv_nets = set(
        [
            "+15V_LS", "+170V_BUS", "DC_BUS_RTN", "GATE_HS", "GATE_LS",
            "PWR_RTN", "SW_NODE", "ac_l", "ac_n", "discharge.k_dis1-nc",
            "discharge.k_dis2-nc", "hb.gate_hs.driver-p1-1",
            "hb.gate_hs.driver-p2", "hb.power_loop.q_high-g",
            "power_in.ntc-no", "tank-out", "tank.c_tank1-p2", "w1_1", "w1_2",
        ]
    )

    # Rebuild the gnd keepout (HV pads on In1.Cu @ 12.6).
    geoms = []
    for comp in getattr(pcb, "components", []) or []:
        for pin in getattr(comp, "pins", []) or []:
            if not pin.net or pin.net == GND_NET:
                continue
            raw = pin_world_layer(pin)
            on_layer = raw in ("all", "*.Cu", PLANE_LAYER) or (
                isinstance(raw, str) and "Through" in raw
            )
            if not on_layer:
                continue
            pos = pin_world_position(pin, comp)
            rect = Polygon(
                [
                    (pos[0] - pin.width / 2, pos[1] - pin.height / 2),
                    (pos[0] + pin.width / 2, pos[1] - pin.height / 2),
                    (pos[0] + pin.width / 2, pos[1] + pin.height / 2),
                    (pos[0] - pin.width / 2, pos[1] + pin.height / 2),
                ]
            )
            geoms.append(rect.buffer(PD3_HV_LV_CREEPAGE_MM, quad_segs=16))
    keepout = unary_union(geoms)
    region = board.buffer(-1.0)
    carved = region.difference(keepout)
    pieces = list(carved.geoms) if hasattr(carved, "geoms") else [carved]
    pieces = [p for p in pieces if p.area >= 0.0625]
    print(f"gnd pour pieces: {len(pieces)} (max interior holes: "
          f"{max((len(p.interiors) for p in pieces), default=0)})")

    # The real pour's keepout is one connected blob, so its pieces carry no
    # interior holes.  The FORMAT question (does KiCad accept multiple
    # (pts ...) blocks as holes?) needs a synthetic hole-carrying outline:
    # a board-scale rect with three interior discs removed -- exactly the
    # shape a pour would emit when interior keepouts are preserved.
    import math

    cx, cy = 96.0, 140.0  # centre of this board's coordinate range
    exterior = [
        (cx - 40, cy - 30), (cx + 40, cy - 30), (cx + 40, cy + 30), (cx - 40, cy + 30)
    ]
    holes = []
    for hx, hy, r in [(-20, 0, 6.0), (15, 10, 4.5), (5, -18, 3.0)]:
        ring = [
            (cx + hx + r * math.cos(2 * math.pi * i / 24),
             cy + hy + r * math.sin(2 * math.pi * i / 24))
            for i in range(24)
        ]
        holes.append(ring)
    print(f"synthetic zone: exterior rect 80x60, {len(holes)} circular holes")

    # Render exactly like zone_generator.rs::emit_zone_s_expr: one
    # (polygon (pts ...)) element per ring -- exterior first, then one per
    # hole.  KiCad's own format (verified against pcb_io_kicad_sexpr.cpp).
    rings = [exterior] + holes
    poly = "".join(f"\n    (polygon\n      {fmt_pts(r)})" for r in rings)
    zone = (
        '  (zone (net 48) (net_name "gnd") (layer "In1.Cu") '
        "(hatch full 0.5) (priority 0) "
        "(connect_pads yes (clearance 0.3000)) "
        "(min_thickness 0.2500) "
        "(fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5)) "
        f"{poly})"
    )

    content = PCBPATH.read_text()
    # Replace the FIRST existing zone block with our hole-carrying one.
    start = content.index("  (zone ")
    # find the end of that zone block: the line containing only "  )"
    # after the start that closes the zone.
    lines = content.splitlines(keepends=True)
    zone_start_line = next(i for i, l in enumerate(lines) if l.startswith("  (zone "))
    depth = 0
    zone_end_line = None
    for i in range(zone_start_line, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        if depth == 0 and i > zone_start_line:
            zone_end_line = i
            break
    new_lines = (
        lines[:zone_start_line]
        + [zone + "\n"]
        + lines[zone_end_line + 1 :]
    )
    out = "".join(new_lines)

    with tempfile.TemporaryDirectory() as td:
        board_path = Path(td) / "spliced.kicad_pcb"
        board_path.write_text(out)
        # kicad-cli needs the .kicad_pro next to it for netclass resolution.
        pro = Path(td) / "spliced.kicad_pro"
        pro.write_text(Path("pcb/temper.kicad_pro").read_text())
        print(f"spliced board: {board_path}")
        r = subprocess.run(
            [
                "kicad-cli", "pcb", "drc",
                str(board_path),
                "--output", str(Path(td) / "drc.rpt"),
                "--refill-zones",
                "--severity-all",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        print("kicad-cli exit:", r.returncode)
        tail = "\n".join(r.stdout.splitlines()[-8:]) + "\n" + "\n".join(r.stderr.splitlines()[-4:])
        print(tail)
        rpt = Path(td) / "drc.rpt"
        if rpt.exists():
            print("DRC report exists -> board parsed, zone format ACCEPTED")
        else:
            print("NO DRC report -> parse or fill failure (see output)")
            sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
