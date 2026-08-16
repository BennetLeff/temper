#!/usr/bin/env python3
"""Measure the routed-copper-avoidance fix: feed a routed board's own
segment/via strings back into the plane/power-island generators and
re-measure connectivity + crossings.

The generators normally re-parse the STRIPPED source board (no routed
tracks); with `segments=` they now see the route's real copper. This
harness extracts the (segment ...)/(via ...) strings from a routed
.kicad_pcb and passes them in, then fills + measures with pcbnew.

Usage (KiCad env as for the other harnesses):
    .venv/bin/python docs/evidence/2026-08-16-routed-obstacle-verify.py <routed.kicad_pcb>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def extract_segments(content: str) -> list[str]:
    """Rebuild (segment ...)/(via ...) strings from a routed board file.
    Each block is a single line in this router's emission format; nested
    inside the top-level (kicad_pcb ...) block."""
    out: list[str] = []
    for line in content.splitlines():
        s = line.lstrip()
        if s.startswith("(segment ") or s.startswith("(via "):
            out.append(s)
    return out


def main() -> int:
    board = Path(sys.argv[1])
    sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer"))

    content = board.read_text()
    segs = extract_segments(content)
    print(f"routed segment/via strings extracted: {len(segs)}")

    from temper_placer.router_v6._ground_plane import generate_ground_plane_blocks
    from temper_placer.router_v6._power_islands import generate_power_islands_blocks

    # Recompute gnd plane + power islands WITH the routed copper as
    # obstacles (the fixed production path).
    gnd_blocks, gnd_result = generate_ground_plane_blocks(
        board, segments=segs
    )
    island_blocks, island_results = generate_power_islands_blocks(
        board, segments=segs
    )
    print("gnd plane result:", repr(gnd_result))
    for net, r in island_results.items():
        print(f"power island {net}: vias={r.drop_via_count} mst={r.mst_edge_count} "
              f"conflict={r.via_unresolved_conflict_count} "
              f"astar={r.mst_edges_astar_routed_count} fallback={r.mst_edges_fallback_count}")

    # Splice into a stripped copy and fill+measure with pcbnew.
    from temper_io_types import strip_existing_copper

    stripped, _ = strip_existing_copper(content)
    new_content = stripped.rstrip()
    if new_content.endswith(")"):
        new_content = new_content[:-1] + "\n" + "\n".join(gnd_blocks + island_blocks) + "\n)\n"
    scratch = REPO_ROOT / "docs" / "evidence" / "scratch-routed-obstacle.kicad_pcb"
    scratch.write_text(new_content)

    import pcbnew
    from collections import Counter

    pcb_board = pcbnew.LoadBoard(str(scratch))
    filler = pcbnew.ZONE_FILLER(pcb_board)
    filler.Fill([z for z in pcb_board.Zones()])
    pcb_board.BuildConnectivity()
    conn = pcb_board.GetConnectivity()
    netinfo = pcb_board.GetNetInfo()
    name_to_code = {}
    for code in range(netinfo.GetNetCount()):
        ni = netinfo.GetNetItem(code)
        if ni is not None:
            name_to_code[ni.GetNetname()] = code
    pads_by_net: dict[int, list] = {}
    for pad in pcb_board.GetPads():
        pads_by_net.setdefault(pad.GetNetCode(), []).append(pad)

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

    print("\n[pcbnew fill+connectivity, routed obstacles]")
    for net_name in ("gnd", "+3V3", "vcc", "+15V"):
        code = name_to_code.get(net_name)
        if code is None:
            continue
        pads = pads_by_net.get(code, [])
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
        print(f"  {net_name}: largest component {largest}/{len(pads)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
