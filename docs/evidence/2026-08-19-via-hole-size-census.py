#!/usr/bin/env python3
"""Drill/pad census of every (via ...) block in a .kicad_pcb, plus the
same-net / any-net near-coincident hole-pair census.

Read-only. Balanced-paren scan, stdlib only -- no placer import, so it can
run against any board on any branch.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import math
import re
from pathlib import Path


def _blocks(text: str, token: str) -> list[str]:
    out = []
    i = 0
    tok = "(" + token + " "
    while True:
        i = text.find(tok, i)
        if i < 0:
            return out
        depth = 0
        j = i
        while j < len(text):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append(text[i : j + 1])
        i = j + 1


def vias(text: str) -> list[dict]:
    out = []
    for b in _blocks(text, "via"):
        at = re.search(r"\(at\s+([-\d.]+)\s+([-\d.]+)", b)
        size = re.search(r"\(size\s+([\d.]+)\)", b)
        drill = re.search(r"\(drill\s+([\d.]+)\)", b)
        net = re.search(r'\(net\s+(\d+)\)', b)
        layers = re.search(r'\(layers\s+"([^"]+)"\s+"([^"]+)"\)', b)
        vtype = "through"
        if re.search(r"\(via\s+blind", b) or b.startswith("(via blind"):
            vtype = "blind"
        if "blind" in b[:20]:
            vtype = "blind"
        elif "buried" in b[:20]:
            vtype = "buried"
        if not (at and size and drill):
            continue
        out.append(
            {
                "x": float(at.group(1)),
                "y": float(at.group(2)),
                "size": float(size.group(1)),
                "drill": float(drill.group(1)),
                "net": int(net.group(1)) if net else -1,
                "type": vtype,
                "layers": (layers.group(1), layers.group(2)) if layers else ("?", "?"),
            }
        )
    return out


def pth_pads(text: str) -> list[dict]:
    """Every thru_hole / np_thru_hole pad, in board coordinates."""
    out = []
    for fp in _blocks(text, "footprint"):
        at = re.search(r"\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\s*\)", fp)
        if not at:
            continue
        fx, fy = float(at.group(1)), float(at.group(2))
        frot = float(at.group(3) or 0.0)
        ref = re.search(r'\(property "Reference" "([^"]+)"', fp)
        for pad in _blocks(fp, "pad"):
            if "thru_hole" not in pad[:80]:
                continue
            pat = re.search(r"\(at\s+([-\d.]+)\s+([-\d.]+)", pad)
            dr = re.search(r"\(drill\s+(?:oval\s+)?([\d.]+)", pad)
            if not (pat and dr):
                continue
            ox, oy = float(pat.group(1)), float(pat.group(2))
            # KiCad footprint rotation is CW-positive in the Y-down frame.
            th = math.radians(-frot)
            rx = ox * math.cos(th) - oy * math.sin(th)
            ry = ox * math.sin(th) + oy * math.cos(th)
            out.append(
                {
                    "x": fx + rx,
                    "y": fy + ry,
                    "drill": float(dr.group(1)),
                    "ref": ref.group(1) if ref else "?",
                }
            )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcb", type=Path)
    ap.add_argument("--min-drill", type=float, default=0.3)
    ap.add_argument("--hole-to-hole", type=float, default=0.5)
    args = ap.parse_args()

    text = args.pcb.read_text(encoding="utf-8")
    print(f"board            {args.pcb}")
    print(f"sha256           {hashlib.sha256(args.pcb.read_bytes()).hexdigest()}")
    print(f"segments {text.count('(segment ')}  vias {text.count('(via ')}  zones {text.count('(zone ')}")

    vs = vias(text)
    hist = collections.Counter((v["size"], v["drill"]) for v in vs)
    print(f"\nvia (size, drill) histogram -- {len(vs)} vias")
    for (size, drill), n in sorted(hist.items()):
        ring = (size - drill) / 2
        flags = []
        if drill < args.min_drill - 1e-9:
            flags.append(f"DRILL<{args.min_drill}")
        if ring < 0.254 - 1e-9:
            flags.append("RING<0.254")
        print(
            f"  size {size:.4f}  drill {drill:.4f}  ring {ring:.4f}  "
            f"x{n:<5d} {' '.join(flags)}"
        )
    sub = [v for v in vs if v["drill"] < args.min_drill - 1e-9]
    print(f"\nvias below min_through_hole_diameter={args.min_drill}: {len(sub)}")
    by_type = collections.Counter(v["type"] for v in sub)
    print(f"  by via type: {dict(by_type)}")

    # hole-to-hole census over vias + PTH pads
    pads = pth_pads(text)
    holes = [(v["x"], v["y"], v["drill"], f"via/net{v['net']}") for v in vs]
    holes += [(p["x"], p["y"], p["drill"], f"pad/{p['ref']}") for p in pads]
    H = args.hole_to_hole
    bad = []
    cell = H + 3.5
    grid: dict[tuple[int, int], list[int]] = {}
    for i, (x, y, d, lab) in enumerate(holes):
        grid.setdefault((int(x // cell), int(y // cell)), []).append(i)
    for (gx, gy), idxs in grid.items():
        cand = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cand += grid.get((gx + dx, gy + dy), [])
        for i in idxs:
            for j in cand:
                if j <= i:
                    continue
                x1, y1, d1, l1 = holes[i]
                x2, y2, d2, l2 = holes[j]
                gap = math.hypot(x1 - x2, y1 - y2) - (d1 + d2) / 2
                if gap < H - 1e-9:
                    bad.append((gap, l1, l2, x1, y1, x2, y2))
    bad.sort()
    print(f"\nhole-pairs closer than {H}mm edge-to-edge: {len(bad)}")
    for gap, l1, l2, x1, y1, x2, y2 in bad[:20]:
        print(f"  gap {gap:+.4f}mm  {l1} @({x1:.3f},{y1:.3f})  <->  {l2} @({x2:.3f},{y2:.3f})")


if __name__ == "__main__":
    main()
