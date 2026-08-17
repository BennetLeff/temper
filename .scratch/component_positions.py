#!/usr/bin/env python3
import re
from pathlib import Path

PCB = Path("/home/bennet/Desktop/temper-wt-agent-routing-completeness-recon/pcb/temper.kicad_pcb")


def extract_top_level_blocks(content, keyword):
    pattern = re.compile(r"^\s*\(" + re.escape(keyword) + r"\s")
    lines = content.split("\n")
    blocks = []
    cur = []
    depth = 0
    in_block = False
    for line in lines:
        if not in_block and pattern.match(line):
            in_block = True
            depth = 0
            cur = []
        if in_block:
            cur.append(line)
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                in_block = False
                blocks.append("\n".join(cur))
    return blocks


content = PCB.read_text(encoding="utf-8")
positions = {}
for block in extract_top_level_blocks(content, "footprint"):
    m = re.search(r'\(property "Reference" "([^"]+)"\)', block)
    if not m:
        continue
    ref = m.group(1)
    am = re.search(r"^\s*\(at ([\-\d.]+) ([\-\d.]+)(?: ([\-\d.]+))?\)\s*$", block, re.M)
    if am:
        positions[ref] = (float(am.group(1)), float(am.group(2)))

import sys
if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else sorted(positions)
    for t in targets:
        if t in positions:
            print(f"{t:<10} {positions[t]}")
        else:
            print(f"{t:<10} NOT FOUND")
