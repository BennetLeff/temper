#!/usr/bin/env python3
"""Zone-fill + real pad connectivity via KiCad's own engine (pcbnew).

Fills every zone with KiCad 10.0.5's native fill engine (ZONE_FILLER, the
same engine `kicad-cli pcb drc --refill-zones` and the GUI use), then
measures REAL pad connectivity from KiCad's own connectivity data
(CONNECTIVITY_DATA::GetPadConnectivity -- zone-aware, thermal-relief-aware,
clearance-aware). This is the ground truth the repo's segment/via-only
`pad_connectivity_audit` deliberately cannot see (it is fill-blind by
design).

Usage (needs the relocated KiCad root env, same as the kicad-cli wrapper):

    KICAD_ROOT=/home/bennet/.local/opt/kicad-10.0.5/root \\
    LD_LIBRARY_PATH="\$(find \$KICAD_ROOT -name '*.so*' -printf '%h\\n' | sort -u | tr '\\n' ':')" \\
    PYTHONPATH="\$KICAD_ROOT/usr/lib/python3/dist-packages" \\
    .venv/bin/python docs/evidence/scripts/2026-08-16-pcbnew-zone-fill-connectivity.py \\
        <board.kicad_pcb> [--save-filled <out.kicad_pcb>] [--nets gnd,+3V3]

Exit 0 on success (measurement complete; verdicts are printed, not encoded).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

FOCUS_NETS = ("gnd", "+3V3", "vcc", "+15V", "V_BUS_SENSE", "PWR_RTN", "power_in.ntc-no")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("--save-filled", type=Path, default=None)
    parser.add_argument("--nets", default=",".join(FOCUS_NETS))
    args = parser.parse_args()

    import pcbnew

    board = pcbnew.LoadBoard(str(args.board))
    print(f"board: {args.board.name}, zones: {len(list(board.Zones()))}")

    # --- Fill every zone with KiCad's own engine ---
    zones = [z for z in board.Zones()]
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(zones)
    n_filled = sum(1 for z in zones if z.IsFilled())
    print(f"zones filled: {n_filled}/{len(zones)}")

    # --- Build connectivity data (zone-aware) ---
    board.BuildConnectivity()
    conn = board.GetConnectivity()

    netinfo = board.GetNetInfo()
    focus = {n: None for n in args.nets.split(",") if n}

    # net codes by name
    name_to_code = {}
    for code in range(netinfo.GetNetCount()):
        ni = netinfo.GetNetItem(code)
        if ni is not None:
            name_to_code[ni.GetNetname()] = code

    for n in list(focus):
        focus[n] = name_to_code.get(n)
        if focus[n] is None:
            print(f"  net {n}: NOT ON BOARD")

    # --- Pad connectivity via KiCad's own graph ---
    # For each pad, GetPadConnectivity returns every connected item (pads,
    # vias, zones). A pad is "plane-connected" if any connected item is a
    # ZONE; the per-net component size comes from unioning pad-to-pad edges.
    pads_by_net: dict[int, list] = {}
    for pad in board.GetPads():
        code = pad.GetNetCode()
        pads_by_net.setdefault(code, []).append(pad)

    def item_kind(item) -> str:
        t = item.Type()
        if t == pcbnew.PCB_PAD_T:
            return "pad"
        if t == pcbnew.PCB_VIA_T:
            return "via"
        if t == pcbnew.PCB_ZONE_T:
            return "zone"
        if t == pcbnew.PCB_TRACE_T:
            return "track"
        return str(t)

    from collections import Counter

    def item_key(item) -> tuple:
        """Canonical key for a board item.  The pcbnew Python binding wraps
        the same underlying C++ object in a NEW Python wrapper per call
        (measured: two pads both touching the plane each reported a
        different `id()` for the same ZONE), so `id()` is NOT a stable
        graph node key -- a geometric/attribute tuple is."""
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
        return (str(t), item.GetNetCode(), item.GetPosition().x, item.GetPosition().y)

    for net_name, code in sorted(focus.items()):
        if code is None:
            continue
        pads = pads_by_net.get(code, [])
        if not pads:
            print(f"{net_name} (net {code}): 0 pads")
            continue
        n_with_copper = 0
        n_zone_touching = 0
        connected_kinds: Counter = Counter()
        zone_touching_pads = []
        for pad in pads:
            items = conn.GetConnectedItems(pad)
            kinds = [item_kind(i) for i in items]
            connected_kinds.update(kinds)
            if kinds:
                n_with_copper += 1
            if "zone" in kinds:
                n_zone_touching += 1
                zone_touching_pads.append(pad)
        print(
            f"{net_name} (net {code}): {len(pads)} pads | "
            f"{n_with_copper} with any copper | {n_zone_touching} touching a zone"
        )
        print(f"    connected item kinds: {dict(connected_kinds)}")
        # Component size: union-find over the FULL connected-item graph
        # (pads + vias + tracks + zones -- GetConnectedItems is one hop,
        # and two pads both touching the same zone are connected THROUGH
        # the zone, not directly to each other, so the graph must carry
        # non-pad nodes for the transitive join to be visible).  Nodes are
        # keyed by item_key (stable across wrapper identity).
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
        print(f"    largest pad component: {largest}/{len(pads)}  (components: {len(comps)})")

    if args.save_filled:
        board.Save(str(args.save_filled))
        print(f"saved filled board: {args.save_filled}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
