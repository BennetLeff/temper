#!/usr/bin/env python3
"""Extract per-footprint pad geometry from a KiCad .kicad_pcb (read-only) into
sources/kicad-footprints.json, so audit.py runs without the (untracked) board file.

    python3 -I extract_kicad.py <section.kicad_pcb> [sources/kicad-footprints.json]

Pad positions are stored relative to the footprint origin at footprint rotation 0
(KiCad file coordinates, y down)."""
import json, math, re, sys
from pathlib import Path


def tokenize(s):
    return re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+', s)


def parse(tokens):
    stack, cur = [], []
    for t in tokens:
        if t == "(":
            stack.append(cur); cur = []
        elif t == ")":
            done = cur; cur = stack.pop(); cur.append(done)
        else:
            cur.append(t[1:-1] if t.startswith('"') else t)
    return cur


def find(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def main():
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).parent / "sources" / "kicad-footprints.json"
    tree = parse(tokenize(src.read_text()))[0]
    fps = {}
    for fp in find(tree, "footprint"):
        ref = next(p[2] for p in find(fp, "property") if p[1] == "Reference")
        at = find(fp, "at")[0]
        rot = float(at[3]) if len(at) > 3 else 0.0
        layer = find(fp, "layer")[0][1]
        th = math.radians(rot)
        pads = []
        for pd in find(fp, "pad"):
            pat = find(pd, "at")[0]
            x, y = float(pat[1]), float(pat[2])
            sz = find(pd, "size")[0]
            net = find(pd, "net")
            # file stores pad offset relative to footprint, already unrotated
            ang = (float(pat[3]) - rot) % 360 if len(pat) > 3 else (-rot) % 360   # pad angle in the footprint's own frame
            w, h = float(sz[1]), float(sz[2])
            if len(pd) > 3 and pd[3] == "custom" and find(pd, "primitives"):
                # stage 35: a custom pad's copper is its anchor plus its primitives (the 7466004R ring is a gr_circle
                # round the footprint centre, with the anchor on the ring): store the copper's bounding box, centred,
                # as the CPL generator's KiCad pad bounding box does (bom_cpl_jlc.py centroid)
                assert abs(ang) < 1e-6 or abs(ang - 360) < 1e-6, f"{fp[1]} pad {pd[1]}: rotated custom pad not handled"
                xs, ys = [-w / 2, w / 2], [-h / 2, h / 2]
                for prim in find(pd, "primitives")[0][1:]:
                    wid = float(find(prim, "width")[0][1]) / 2 if find(prim, "width") else 0.0
                    if prim[0] == "gr_circle":
                        (cx, cy), (ex, ey) = [tuple(map(float, find(prim, k)[0][1:3])) for k in ("center", "end")]
                        r = math.hypot(ex - cx, ey - cy) + wid
                        xs += [cx - r, cx + r]; ys += [cy - r, cy + r]
                    elif prim[0] == "gr_poly":
                        for q in find(find(prim, "pts")[0], "xy"):
                            xs += [float(q[1]) - wid, float(q[1]) + wid]; ys += [float(q[2]) - wid, float(q[2]) + wid]
                    else:
                        raise SystemExit(f"{fp[1]} pad {pd[1]}: custom primitive {prim[0]} not handled")
                x, y = x + (min(xs) + max(xs)) / 2, y + (min(ys) + max(ys)) / 2
                w, h = max(xs) - min(xs), max(ys) - min(ys)
            pads.append({"num": pd[1], "type": pd[2], "x": x, "y": y, "ang": ang,
                         "w": w, "h": h, "layers": find(pd, "layers")[0][1:] if find(pd, "layers") else [],
                         "net": net[0][1] if net else ""})
        fps[ref] = {"lib": fp[1], "x": float(at[1]), "y": float(at[2]), "rot": rot,
                    "layer": layer, "pads": pads}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fps, indent=1, sort_keys=True) + "\n")
    print(len(fps), "footprints ->", out)


if __name__ == "__main__":
    main()
