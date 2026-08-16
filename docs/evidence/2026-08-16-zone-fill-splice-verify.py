#!/usr/bin/env python3
"""Splice the gnd plane + power-island blocks into a board copy and
measure real connectivity after KiCad's own zone fill (pcbnew).

Read-only w.r.t. pcb/temper.kicad_pcb -- writes a scratch copy. This is
the seam-level verification of the 2026-08-16 gnd/+3V3 zone work:
production emission functions (generate_ground_plane_blocks +
generate_power_islands_blocks) -> spliced board -> ZONE_FILLER ->
CONNECTIVITY_DATA.

Usage (needs the relocated KiCad root env, same as the kicad-cli wrapper):

    KICAD_ROOT=... LD_LIBRARY_PATH=... PYTHONPATH=... \\
    .venv/bin/python docs/evidence/2026-08-16-zone-fill-splice-verify.py \\
        [--nets gnd,+3V3,vcc,+15V,V_BUS_SENSE]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nets", default="gnd,+3V3,vcc,+15V,V_BUS_SENSE")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer"))

    from temper_placer.router_v6._ground_plane import generate_ground_plane_blocks
    from temper_placer.router_v6._power_islands import generate_power_islands_blocks

    content = PCB_PATH.read_text()
    # strip existing copper (same R7 strip the route path does) so the
    # spliced zones are the ONLY zones, mirroring a routed output
    from temper_io_types import strip_existing_copper

    stripped, _n = strip_existing_copper(content)

    gnd_blocks, gnd_result = generate_ground_plane_blocks(PCB_PATH)
    island_blocks, island_results = generate_power_islands_blocks(PCB_PATH)

    print("gnd plane result:", repr(gnd_result))
    for net, r in island_results.items():
        print(f"power island {net}: pads={r.pad_count} vias={r.drop_via_count} "
              f"zones={r.zone_polygon_count} area={r.pour_area_mm2:.0f}")

    new_content = stripped.rstrip()
    if new_content.endswith(")"):
        new_content = new_content[:-1] + "\n" + "\n".join(gnd_blocks + island_blocks) + "\n)\n"

    out = args.out or (REPO_ROOT / "docs" / "evidence" / "scratch-zone-splice.kicad_pcb")
    out.write_text(new_content)
    print(f"wrote spliced board: {out} ({len(new_content)} bytes)")

    # --- KiCad's own fill + connectivity ---
    import pcbnew

    board = pcbnew.LoadBoard(str(out))
    zones = [z for z in board.Zones()]
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(zones)
    board.BuildConnectivity()
    conn = board.GetConnectivity()

    netinfo = board.GetNetInfo()
    name_to_code = {}
    for code in range(netinfo.GetNetCount()):
        ni = netinfo.GetNetItem(code)
        if ni is not None:
            name_to_code[ni.GetNetname()] = code

    pads_by_net: dict[int, list] = {}
    for pad in board.GetPads():
        pads_by_net.setdefault(pad.GetNetCode(), []).append(pad)

    from collections import Counter

    def item_key(item):
        t = item.Type()
        if t == pcbnew.PCB_PAD_T:
            pos = item.GetPosition()
            return ("pad", item.GetNetCode(), pos.x, pos.y)
        if t == pcbnew.PCB_VIA_T:
            pos = item.GetPosition()
            return ("via", item.GetNetCode(), pos.x, pos.y)
        if t == pcbnew.PCB_ZONE_T:
            pos = item.GetPosition()
            return ("zone", item.GetNetCode(), pos.x, pos.y, item.GetLayerName())
        if t == pcbnew.PCB_TRACE_T:
            s, e = item.GetStart(), item.GetEnd()
            return ("track", item.GetNetCode(), s.x, s.y, e.x, e.y, item.GetLayerName())
        return (str(t), item.GetNetCode())

    for net_name in args.nets.split(","):
        code = name_to_code.get(net_name)
        if code is None:
            print(f"{net_name}: not on board")
            continue
        pads = pads_by_net.get(code, [])
        if not pads:
            print(f"{net_name}: 0 pads")
            continue
        all_items: dict[tuple, object] = {}
        for p in pads:
            all_items[item_key(p)] = p
            for item in conn.GetConnectedItems(p):
                all_items.setdefault(item_key(item), item)
        parent = {k: k for k in all_items}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for item in all_items.values():
            for other in conn.GetConnectedItems(item):
                k = item_key(other)
                if k in parent:
                    union(item_key(item), k)
        comps = Counter(find(item_key(p)) for p in pads)
        largest = max(comps.values()) if comps else 0
        n_zone = sum(1 for k in all_items if k[0] == "zone")
        print(f"{net_name}: {len(pads)} pads | largest component {largest}/{len(pads)} | "
              f"nodes {len(all_items)} ({n_zone} zones)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
