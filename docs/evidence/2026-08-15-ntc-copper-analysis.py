#!/usr/bin/env python3
"""Analyze power_in.ntc-no copper in a routed .kicad_pcb output.

2026-08-15 NTC ampacity assessment: count segments + widths, count zone
blocks, and — when the zone blocks carry filled polygons — count the
connected copper islands for the net, to reproduce/verify the handoff's
"single-hull pour fragments into 47+ islands" observation.

Usage:
    .venv/bin/python docs/evidence/2026-08-15-ntc-copper-analysis.py \
        /tmp/opencode/agent-stage3-routed.kicad_pcb
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path


def net_number_for(content: str, name: str) -> str | None:
    for m in re.finditer(r'\(net (\d+) "([^"]+)"', content):
        if m.group(2) == name:
            return m.group(1)
    return None


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/opencode/agent-stage3-routed.kicad_pcb")
    content = path.read_text(encoding="utf-8")
    n = net_number_for(content, "power_in.ntc-no")
    if n is None:
        print(f"power_in.ntc-no not found in {path}")
        return 1
    print(f"net power_in.ntc-no = net {n}")

    # segments: (segment ... (net N)) blocks, width inside
    seg_widths = []
    for m in re.finditer(r"\(segment .*?\(net " + n + r"\)", content, re.S):
        w = re.search(r"\(width ([\d.]+)\)", m.group(0))
        seg_widths.append(float(w.group(1)) if w else -1)
    print(f"segments: {len(seg_widths)}, widths: {Counter(seg_widths)}")

    # zones: (zone (net N ...) ...) top-level blocks
    zones = []
    for m in re.finditer(r"\(zone \(net " + n, content):
        start = m.start()
        d = 0
        i = start
        while i < len(content):
            c = content[i]
            if c == "(":
                d += 1
            elif c == ")":
                d -= 1
                if d == 0:
                    break
            i += 1
        zones.append(content[start : i + 1])
    print(f"zone blocks on net {n}: {len(zones)}")
    for zi, z in enumerate(zones):
        layer = re.search(r'\(layer "([^"]+)"', z)
        print(f"  zone {zi}: layer={layer.group(1) if layer else '?'}")

    # filled polygons inside zones -> count as islands (one filled polygon
    # per connected copper region KiCad emitted)
    total_filled = 0
    for zi, z in enumerate(zones):
        filled = z.count("(filled_polygon")
        total_filled += filled
        if filled:
            print(f"  zone {zi}: {filled} filled_polygon(s)")
    print(f"total filled polygons (copper regions) on net {n}: {total_filled}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
