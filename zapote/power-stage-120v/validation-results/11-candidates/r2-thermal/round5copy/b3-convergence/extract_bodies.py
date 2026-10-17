#!/usr/bin/env python3
"""Extract per-part body/footprint facts for the heat-source parts from the built board (section.kicad_pcb).

    python3 extract_bodies.py <section.kicad_pcb> <heat-sources.json> inputs/part-bodies.json

The .kicad_pcb is gitignored (built by native-21/layout); this derived file (reference, footprint, MPN, position,
F.Fab / F.CrtYd bounding boxes) is what the thermal model reads. Provenance is recorded in the output.
"""
import hashlib
import json
import re
import sys
from pathlib import Path


def parse(s):
    stack = [[]]
    for m in re.finditer(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', s):
        t = m.group()
        if t == "(":
            stack.append([])
        elif t == ")":
            x = stack.pop()
            stack[-1].append(x)
        else:
            stack[-1].append(t[1:-1] if t.startswith('"') else t)
    return stack[0][0]


def bbox(fp, layer):
    xs, ys = [], []
    for p in fp:
        if isinstance(p, list) and p and p[0] in ("fp_line", "fp_rect", "fp_circle", "fp_poly"):
            ly = next((q[1] for q in p if isinstance(q, list) and q and q[0] == "layer"), None)
            if ly != layer:
                continue
            for q in p:
                if isinstance(q, list) and q and q[0] in ("start", "end", "center", "mid"):
                    xs.append(float(q[1])); ys.append(float(q[2]))
                if isinstance(q, list) and q and q[0] == "pts":
                    for xy in q[1:]:
                        xs.append(float(xy[1])); ys.append(float(xy[2]))
    return [min(xs), min(ys), max(xs), max(ys)] if xs else None


def main():
    pcb, heat, out = map(Path, sys.argv[1:4])
    refs = {p["ref"] for p in json.loads(heat.read_text())["parts"]} | {"Q2", "Q3", "Q5", "Q6"}
    tree = parse(pcb.read_text())
    res = {}
    for n in tree:
        if isinstance(n, list) and n and n[0] == "footprint":
            props = {p[1]: p[2] for p in n if isinstance(p, list) and p and p[0] == "property"}
            ref = props.get("Reference")
            if ref not in refs:
                continue
            at = next(p for p in n if isinstance(p, list) and p and p[0] == "at")
            res[ref] = {"fp": n[1], "mpn": props.get("MPN"), "at": [float(v) for v in at[1:]],
                        "fab": bbox(n, "F.Fab"), "crt": bbox(n, "F.CrtYd"),
                        "layer": next(p for p in n if isinstance(p, list) and p and p[0] == "layer")[1]}
    out.write_text(json.dumps({"source_board": pcb.name, "source_board_sha256": hashlib.sha256(pcb.read_bytes()).hexdigest(),
                               "parts": res}, indent=1) + "\n")
    print(len(res), "parts ->", out)


if __name__ == "__main__":
    main()
