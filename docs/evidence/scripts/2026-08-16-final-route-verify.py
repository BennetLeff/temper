#!/usr/bin/env python3
"""Final verification of a routed board with the gnd/+3V3 zone work.

Three honest measurements on one routed .kicad_pcb:

1. pad_connectivity_audit (segment/via graph -- the PRIMARY repo metric,
   deliberately fill-blind).
2. KiCad's own fill + CONNECTIVITY_DATA (pcbnew) -- the fill-aware truth
   for zone-connected nets (gnd, +3V3, vcc, +15V, PWR_RTN, ntc-no).
3. kicad-cli DRC with the project + DRU sidecars (--all-track-errors).

Usage:
    KICAD_ROOT=... LD_LIBRARY_PATH=... PYTHONPATH=... \\
    .venv/bin/python docs/evidence/scripts/2026-08-16-final-route-verify.py <routed.kicad_pcb>
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FOCUS_NETS = ("gnd", "+3V3", "vcc", "+15V", "V_BUS_SENSE", "PWR_RTN", "power_in.ntc-no")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("--kicad-cli", type=str, default="kicad-cli")
    args = parser.parse_args()

    sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer"))

    board = args.board.resolve()

    # 1. audit (fill-blind, PRIMARY metric)
    from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file

    results = audit_pcb_file(board)
    total = len(results)
    fully = sum(1 for r in results.values() if r.fully_connected)
    fake = sum(1 for r in results.values() if r.is_fake_completion)
    print(f"[audit] {fully}/{total} nets fully pad-connected, {fake} fake, "
          f"{total - fully - fake} honest-gap")
    for n in FOCUS_NETS:
        r = results.get(n)
        if r:
            print(f"[audit] {n}: {r.pads_connected}/{r.pad_count}  cat={r.category}")

    # 2. pcbnew fill + connectivity
    import pcbnew

    pcb_board = pcbnew.LoadBoard(str(board))
    zones = [z for z in pcb_board.Zones()]
    filler = pcbnew.ZONE_FILLER(pcb_board)
    filler.Fill(zones)
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

    print("\n[pcbnew fill+connectivity]")
    for net_name in FOCUS_NETS:
        code = name_to_code.get(net_name)
        if code is None:
            print(f"  {net_name}: not on board")
            continue
        pads = pads_by_net.get(code, [])
        if not pads:
            print(f"  {net_name}: 0 pads")
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
        print(f"  {net_name}: largest component {largest}/{len(pads)} "
              f"(nodes {len(all_items)}, {n_zone} zones)")

    # 3. kicad-cli DRC with sidecars
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        copy = td / board.name
        shutil.copy(board, copy)
        proj = board.with_suffix(".kicad_pro")
        dru = board.with_suffix(".kicad_dru")
        if proj.is_file():
            shutil.copy(proj, td / (board.stem + ".kicad_pro"))
        if dru.is_file():
            shutil.copy(dru, td / (board.stem + ".kicad_dru"))
        report = td / "drc.json"
        cmd = [
            args.kicad_cli, "pcb", "drc",
            "--refill-zones", "--severity-all", "--all-track-errors",
            "--format", "json", "--output", str(report),
            str(copy),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        print(f"\n[kicad-cli drc] exit={proc.returncode}")
        if report.is_file():
            d = json.loads(report.read_text())
            viols = d.get("violations", [])
            types = Counter(v.get("type", "?") for v in viols)
            print(f"  total violations: {len(viols)}")
            print(f"  by type: {dict(list(types.items())[:16])}")
            creep = [v for v in viols if v.get("type") == "creepage"]
            zone_creep = [
                v for v in creep
                if any("Zone" in i.get("description", "") for i in v.get("items", []))
            ]
            print(f"  creepage: {len(creep)} ({len(zone_creep)} zone-involved)")
        else:
            print("  no DRC report produced")
            print(proc.stdout[-1000:])
            print(proc.stderr[-1000:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
