#!/usr/bin/env python3
"""Check the two FR-4 pad Gerber zips from the files alone (not from the generator's objects), and render them.

    ~/.local/share/temper/cadenv/bin/python -I scripts/bench_pads_verify.py      (from bench-sink-r1/; needs gerbv)
      -> fab/pads/pads-check.md, fab/pads/bench-pads-<t>-r1.png; exits 1 on any FAIL

Per zip:
  * the layer set (outline, NPTH drill, empty F/B copper, F/B mask, F silk) and nothing else;
  * the outline: Edge.Cuts is parsed (lines and arcs) and polygonised; panel = the outer ring, slots = the inner rings;
  * the break lines: the NPTH mouse-bites are grown to touch their neighbours (radius = pitch / 2), and the board is
    cut along them. The pieces must be one frame plus exactly the expected pads, each FR4_PAD in size. That also checks
    that every tab is fully perforated: an unbroken tab would leave a pad joined to the frame;
  * each tab: width, hole count, hole size and web, position on its pad edge, and what it joins;
  * copper layers hold no image; each pad lies wholly inside a mask opening on both sides (bare laminate faces);
    every silkscreen stroke lies off the pads (on the frame);
  * gerbv renders every layer and reports no error.
"""
from __future__ import annotations

import math
import re
import subprocess
import sys
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(HERE))
import bench_params as P  # noqa: E402

OUT = STUDY / "fab" / "pads"
REPORT = OUT / "pads-check.md"
ZIPS = {"1.6mm": OUT / "bench-pads-1.6mm-r1.zip", "0.8mm": OUT / "bench-pads-0.8mm-r1.zip"}
N_PADS = 6
# JLCPCB capabilities page, read 2026-11-28 (README): minimum board 3 x 3 mm; mouse-bite tab >= 5 mm; NPTH >= 0.50 mm;
# recommended bites 0.5-0.8 mm with 0.2-0.3 mm between them; board spacing 1.6 or 2 mm; tooling edge >= 3 mm.
JLC = dict(min_board=(3.0, 3.0), tab_min=5.0, npth_min=0.50, bite_d=(0.5, 0.8), bite_web=(0.2, 0.3),
           spacing=(1.6, 2.0), rail_min=3.0)
LAYER_SUFFIX = {"Edge_Cuts.gm1": "outline", "NPTH.drl": "drill", "F_Cu.gtl": "copper", "B_Cu.gbl": "copper",
                "F_Mask.gts": "mask", "B_Mask.gbs": "mask", "F_Silkscreen.gto": "silk"}
TOL = 0.01


def parse_gerber(text):
    """-> dict(strokes=[(pts, aperture_d)], regions=[pts], flashes=[(x, y, d)]) in mm; G75 arcs are discretised."""
    fs = re.search(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", text)
    dec = int(fs.group(2))
    assert "%MOMM*%" in text, "Gerber not in mm"
    aps = {m.group(1): float(m.group(2)) for m in re.finditer(r"%ADD(\d+)C,([0-9.]+)", text)}
    x = y = 0.0
    mode, ap, region = "G01", None, None
    strokes, regions, flashes, cur = [], [], [], None
    for cmd in re.findall(r"([^*%]+)\*", text):
        cmd = cmd.strip()
        if cmd.startswith("G04") or cmd.startswith("FS") or cmd.startswith("MO") or cmd.startswith("AD") or cmd.startswith("LP") or cmd.startswith("TF") or cmd.startswith("TA") or cmd.startswith("TD") or cmd.startswith("TO"):
            continue
        if cmd == "G36":
            region = []
            continue
        if cmd == "G37":
            if region:
                regions.append(region)
            region = None
            continue
        m = re.match(r"^D(\d+)$", cmd)
        if m and int(m.group(1)) >= 10:
            ap = m.group(1)
            continue
        m = re.match(r"^(G0[123])?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?(D0[123])?$", cmd)
        if not m or not any(m.groups()):
            continue
        if m.group(1):
            mode = m.group(1)
        nx = int(m.group(2)) / 10 ** dec if m.group(2) else x
        ny = int(m.group(3)) / 10 ** dec if m.group(3) else y
        i = int(m.group(4)) / 10 ** dec if m.group(4) else 0.0
        j = int(m.group(5)) / 10 ** dec if m.group(5) else 0.0
        d = m.group(6)
        if d == "D02":
            if region is not None:
                if len(region) > 2:
                    regions.append(region)
                region = [(nx, ny)]
            else:
                cur = [(nx, ny)]
                strokes.append((cur, aps.get(ap, 0.0)))
        elif d == "D01":
            if mode == "G01":
                seg = [(nx, ny)]
            else:
                cx, cy = x + i, y + j
                a0, a1 = math.atan2(y - cy, x - cx), math.atan2(ny - cy, nx - cx)
                r = math.hypot(x - cx, y - cy)
                if mode == "G03" and a1 <= a0:
                    a1 += 2 * math.pi
                if mode == "G02" and a1 >= a0:
                    a1 -= 2 * math.pi
                n = max(2, int(abs(a1 - a0) / (math.pi / 64)))
                seg = [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(1, n + 1)]
            if region is not None:
                region += seg
            else:
                if cur is None:
                    cur = [(x, y)]
                    strokes.append((cur, aps.get(ap, 0.0)))
                cur += seg
        elif d == "D03":
            flashes.append((nx, ny, aps.get(ap, 0.0)))
        x, y = nx, ny
    return dict(strokes=strokes, regions=regions, flashes=flashes)


def parse_drill(text):
    tools = {m.group(1): float(m.group(2)) for m in re.finditer(r"^T(\d+)C([0-9.]+)", text, re.M)}
    assert "METRIC" in text
    hits, t = [], None
    body = text.split("%", 1)[1] if "%" in text else text
    for line in body.splitlines():
        m = re.match(r"^T(\d+)$", line.strip())
        if m:
            t = m.group(1)
            continue
        m = re.match(r"^X(-?[0-9.]+)Y(-?[0-9.]+)$", line.strip())
        if m:
            hits.append((float(m.group(1)), float(m.group(2)), tools[t]))
    return hits


def cluster_tabs(hits, pitch_max):
    """Group mouse-bite hits into tabs: same row (y), consecutive x within pitch_max."""
    rows = {}
    for x, y, d in hits:
        rows.setdefault(round(y, 3), []).append((x, d))
    tabs = []
    for y, xs in sorted(rows.items()):
        xs.sort()
        grp = [xs[0]]
        for p in xs[1:]:
            if p[0] - grp[-1][0] <= pitch_max:
                grp.append(p)
            else:
                tabs.append((y, grp))
                grp = [p]
        tabs.append((y, grp))
    return tabs


def check_zip(tag, zpath, rows, fails):
    from shapely.geometry import LineString, Point, Polygon, box  # noqa: F401
    from shapely.ops import polygonize, unary_union

    def check(name, measured, expected, ok, note=""):
        rows.append((tag, name, measured, expected, "PASS" if ok else "FAIL", note))
        if not ok:
            fails.append(f"{tag}: {name}")

    with zipfile.ZipFile(zpath) as z:
        files = {n: z.read(n).decode() for n in z.namelist()}
    kinds = {}
    for n in files:
        suf = [s for s in LAYER_SUFFIX if n.endswith(s)]
        kinds[n] = LAYER_SUFFIX[suf[0]] if suf else "UNEXPECTED"
    check("layer files", ", ".join(sorted(n.split(f"bench-pads-{tag}-")[-1] for n in files)),
          ", ".join(sorted(LAYER_SUFFIX)), sorted(n.split(f"bench-pads-{tag}-")[-1] for n in files) == sorted(LAYER_SUFFIX))

    # ---------------------------------------------------------------- outline
    edge = parse_gerber(next(t for n, t in files.items() if kinds[n] == "outline"))
    lines = [LineString(pts) for pts, _ in edge["strokes"] if len(pts) > 1]
    merged = unary_union(lines)
    faces = list(polygonize(merged))
    board_face = max(faces, key=lambda f: Polygon(f.exterior).area)      # the board, its slots as holes
    outer = Polygon(board_face.exterior)
    slots = [f for f in faces if f is not board_face]
    board = outer.difference(unary_union(slots))
    minx, miny, maxx, maxy = outer.bounds
    pw, ph = maxx - minx, maxy - miny
    check("panel size (outline bbox)", f"{pw:.3f} x {ph:.3f}", f">= {JLC['min_board'][0]} x {JLC['min_board'][1]} (JLC min)",
          pw >= JLC["min_board"][0] and ph >= JLC["min_board"][1], "60 x 48 by design")
    check("outline closes into the panel and its milled slots", f"{len(slots)} slot regions, board area {board.area:.1f} mm2",
          ">= 1 slot region, board = outer - slots", len(slots) >= 1 and abs(board.area - board_face.area) < 1e-3)
    segs = [ls for ls in getattr(merged, "geoms", [merged])]

    # ---------------------------------------------------------------- drill / mouse-bites
    hits = parse_drill(next(t for n, t in files.items() if kinds[n] == "drill"))
    dias = sorted({d for *_, d in hits})
    check("NPTH sizes", ", ".join(f"{d:.2f}" for d in dias), f">= {JLC['npth_min']:.2f}, in {JLC['bite_d']}",
          all(JLC["bite_d"][0] - 1e-9 <= d <= JLC["bite_d"][1] for d in dias) and all(d >= JLC["npth_min"] for d in dias))
    inside_n = sum(board.buffer(1e-6).contains(Point(x, y)) for x, y, _ in hits)
    check("NPTH hits inside the board", f"{inside_n} of {len(hits)}", f"{len(hits)} of {len(hits)}", inside_n == len(hits))
    tabs = cluster_tabs(hits, 1.2)
    pitch = min(b[0] - a[0] for _, g in tabs for a, b in zip(g, g[1:]))
    web = pitch - max(dias)
    check("mouse-bite pitch / web between holes", f"{pitch:.3f} / {web:.3f}", f"web in {JLC['bite_web']} (JLC recommended)",
          JLC["bite_web"][0] - 0.005 <= web <= JLC["bite_web"][1] + 0.005)
    cutters = unary_union([Point(x, y).buffer(pitch / 2 + 0.005, 64) for x, y, _ in hits])
    pieces = board.difference(cutters)
    pieces = sorted(getattr(pieces, "geoms", [pieces]), key=lambda g: -g.area)
    frame = pieces[0]
    w, h = P.FR4_PAD
    pads = [g for g in pieces[1:] if g.area > 0.5 * w * h]
    bridges = [g for g in pieces[1:] if g.area <= 0.5 * w * h]
    pads.sort(key=lambda g: (-round(g.centroid.y, 1), round(g.centroid.x, 1)))    # row-major from the top left
    check("pieces after breaking along the bites", f"1 frame + {len(pads)} pads + {len(bridges)} pad-to-pad bridges",
          f"1 frame + {N_PADS} pads", len(pads) == N_PADS, "every tab fully perforated, else a pad stays joined")

    def nominal(piece):
        """The pad's routed outline: the long axis-aligned Edge.Cuts segments that bound this piece."""
        near = piece.buffer(0.02)
        xs, ys = [], []
        for ls in segs:
          for (x0, y0), (x1, y1) in zip(ls.coords, list(ls.coords)[1:]):
            if not near.contains(LineString([(x0, y0), (x1, y1)])):
                continue
            if abs(y0 - y1) < 0.01 and abs(x1 - x0) > 1.0:
                ys.append(y0)
            if abs(x0 - x1) < 0.01 and abs(y1 - y0) > 1.0:
                xs.append(x0)
        return min(xs), min(ys), max(xs), max(ys)

    rects = [nominal(g) for g in pads]
    sizes = [(r[2] - r[0], r[3] - r[1]) for r in rects]
    check("pad routed outline (Edge.Cuts edges of each pad)", "; ".join(f"{a:.3f} x {b:.3f}" for a, b in sizes),
          f"{w:.3f} x {h:.3f} (bench_params.FR4_PAD)", all(abs(a - w) < 1e-3 and abs(b - h) < 1e-3 for a, b in sizes))
    nubs = [max(g.bounds[3] - r[3], r[1] - g.bounds[1], g.bounds[2] - r[2], r[0] - g.bounds[0]) for g, r in zip(pads, rects)]
    check("residue beyond the outline after the break (model)", f"max {max(nubs):.3f} mm", "<= 0.10 mm",
          max(nubs) <= 0.10, "router-radius fillet just outside the last bite at each tab end; sand flush")
    hgaps, vgaps = [], []
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if abs(a[1] - b[1]) < 1e-3 and b[0] > a[2]:
                hgaps.append(b[0] - a[2])
            if abs(a[0] - b[0]) < 1e-3 and a[1] > b[3]:
                vgaps.append(a[1] - b[3])
    hgap = min(hgaps) if hgaps else float("nan")
    vgap = min(vgaps) if vgaps else float("nan")
    check("milled gap between neighbouring pads (x, y)", f"{hgap:.3f}, {vgap:.3f}", f"in {JLC['spacing']} (JLC board spacing)",
          all(JLC["spacing"][0] - 1e-3 <= g <= JLC["spacing"][1] + 1e-3 for g in (hgap, vgap)))
    ib = unary_union(slots).bounds
    rails = (ib[0] - minx, maxx - ib[2], ib[1] - miny, maxy - ib[3])
    check("frame rail widths (L, R, B, T)", ", ".join(f"{r:.3f}" for r in rails), f">= {JLC['rail_min']} (JLC tooling edge)",
          all(r >= JLC["rail_min"] - 1e-6 for r in rails))
    pr = (min(r[0] for r in rects) - ib[0], ib[2] - max(r[2] for r in rects), min(r[1] for r in rects) - ib[1], ib[3] - max(r[3] for r in rects))
    check("milled gap pads-to-frame (L, R, B, T)", ", ".join(f"{g:.3f}" for g in pr), f"in {JLC['spacing']}",
          all(JLC["spacing"][0] - 1e-3 <= g <= JLC["spacing"][1] + 1e-3 for g in pr))
    # tabs
    tab_rows = []
    for y, grp in tabs:
        x0, x1 = grp[0][0] - grp[0][1] / 2, grp[-1][0] + grp[-1][1] / 2
        xc = (grp[0][0] + grp[-1][0]) / 2
        owner = min(range(len(rects)), key=lambda k: min(abs(rects[k][1] - y), abs(rects[k][3] - y)) if rects[k][0] < xc < rects[k][2] else 99)
        r = rects[owner]
        top = abs(r[3] - y) < abs(r[1] - y)
        edge_y = r[3] if top else r[1]
        sgn = 1.0 if top else -1.0
        far = Point(xc, edge_y + sgn * 2.5)     # past a 2 mm gap: the frame or the next pad
        joins = "frame" if frame.buffer(1e-6).contains(far) else "?"
        for k, rr in enumerate(rects):
            if k != owner and box(*rr).contains(far):
                joins = f"pad {k + 1}"
        tab_material = board.contains(Point(xc, edge_y + sgn * 1.0))
        tab_rows.append(dict(pad=owner + 1, side="top" if top else "bottom", xc=xc, y=y, width=x1 - x0, n=len(grp),
                             offset=xc - (r[0] + r[2]) / 2, inset=abs(edge_y - y), joins=joins if tab_material else "NO TAB"))
    per_pad = {k + 1: sorted(t["side"] for t in tab_rows if t["pad"] == k + 1) for k in range(len(rects))}
    check("perforated tabs per pad", ", ".join(f"pad {k}: {'+'.join(v)}" for k, v in per_pad.items()), "top+bottom each (the 14 mm edges)",
          all(v == ["bottom", "top"] for v in per_pad.values()))
    check("every tab joins the frame or a neighbouring pad", ", ".join(sorted({t["joins"] for t in tab_rows})), "frame / pad n",
          all(t["joins"] == "frame" or t["joins"].startswith("pad ") for t in tab_rows))
    check("tab perforated width (first hole edge to last hole edge)", ", ".join(sorted({f"{t['width']:.3f}" for t in tab_rows})),
          f">= {JLC['tab_min']} (JLC mouse-bite tab minimum)", all(t["width"] >= JLC["tab_min"] - 1e-6 for t in tab_rows))
    check("tab centred on its pad edge (x offset)", f"max {max(abs(t['offset']) for t in tab_rows):.3f}", "< 0.01",
          all(abs(t["offset"]) < TOL for t in tab_rows))
    check("bite row inset from the pad's routed edge", ", ".join(sorted({f"{t['inset']:.3f}" for t in tab_rows})),
          "0.250 (break inside the outline)", all(abs(t["inset"] - 0.25) < TOL for t in tab_rows))

    # ---------------------------------------------------------------- copper, mask, silk
    for n, t in files.items():
        if kinds[n] == "copper":
            g = parse_gerber(t)
            img = len(g["strokes"]) + len(g["regions"]) + len(g["flashes"])
            check(f"{n.split('-')[-1]} empty (no copper)", f"{img} objects", "0", img == 0)
        if kinds[n] == "mask":
            g = parse_gerber(t)
            opening = unary_union([Polygon(r) for r in g["regions"] if len(r) > 2] +
                                  [Point(x, y).buffer(d / 2) for x, y, d in g["flashes"]])
            inside = [opening.buffer(1e-6).contains(p) for p in pads]
            check(f"{n.split('-')[-1]}: each pad wholly in a mask opening", f"{sum(inside)} of {len(pads)}", f"{len(pads)} of {len(pads)}",
                  all(inside), "bare laminate on both faces")
        if kinds[n] == "silk":
            g = parse_gerber(t)
            pts = [p for pts, _ in g["strokes"] for p in pts] + [(x, y) for x, y, _ in g["flashes"]]
            on_pad = sum(any(pd.buffer(0.2).contains(Point(p)) for pd in pads) for p in pts)
            check("silkscreen off the pads", f"{on_pad} of {len(pts)} stroke points on a pad", "0", on_pad == 0 and len(pts) > 0)

    # ---------------------------------------------------------------- gerbv render
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        paths = {}
        for n, t in files.items():
            (Path(td) / n).write_text(t)
            paths[kinds[n] + n] = Path(td) / n
        order = [("outline", "#000000"), ("drill", "#d00000"), ("silk", "#2080ff"), ("mask", "#20a020")]
        args = ["gerbv", "-x", "png", "-D", "300", "-B", "2", "-b", "#ffffff", "-o", str(OUT / f"bench-pads-{tag}-r1.png")]
        for kind, col in order:
            for k, pth in sorted(paths.items()):
                if k.startswith(kind) and (kind != "mask" or "F_Mask" in k):
                    args += ["-f", col, str(pth)]
        r = subprocess.run(args, capture_output=True, text=True)
        err = (r.stderr + r.stdout).strip()
        check("gerbv render (outline, NPTH, F.SilkS, F.Mask)", f"exit {r.returncode}; {err[:80] or 'no messages'}",
              "exit 0, no messages", r.returncode == 0 and not err)
        for n in files:   # every layer, including the empty copper, must load
            r2 = subprocess.run(["gerbv", "-x", "png", "-o", str(Path(td) / "probe.png"), str(Path(td) / n)], capture_output=True, text=True)
            msg = (r2.stderr + r2.stdout).strip()
            empty_cu = kinds[n] == "copper" and "RS-274D" in msg and r2.returncode == 0
            check(f"gerbv loads {n.split('-')[-1]}", "exit %d; %s" % (r2.returncode, "RS-274D guess (empty file)" if empty_cu else (msg[:60] or "no messages")),
                  "exit 0", r2.returncode == 0 and (not msg or empty_cu),
                  "gerbv's format guess for a Gerber with no apertures; the file is RS-274X with %FS/%MO" if empty_cu else "")
    return tab_rows, pads, (pw, ph)


def main():
    rows, fails, detail = [], [], []
    for tag, z in ZIPS.items():
        tab_rows, pads, size = check_zip(tag, z, rows, fails)
        detail += ["", f"**{tag} tabs** (pads numbered row by row from the top left; y is the Gerber y):", "",
                   "| pad | edge | tab centre x, y | perforated width | holes | joins |", "|---|---|---|---|---|---|"]
        detail += [f"| {t['pad']} | {t['side']} | {t['xc']:.3f}, {t['y']:.3f} | {t['width']:.3f} | {t['n']} | {t['joins']} |"
                   for t in sorted(tab_rows, key=lambda t: (t["pad"], t["side"]))]
    md = ["# FR-4 pad Gerber check (scripts/bench_pads_verify.py; do not edit)", "",
          "Files: `fab/pads/bench-pads-1.6mm-r1.zip`, `fab/pads/bench-pads-0.8mm-r1.zip`. Renders: `fab/pads/bench-pads-*-r1.png` "
          "(gerbv: outline black, NPTH red, silk blue, F.Mask openings green).", "",
          "| zip | check | measured | expected | verdict | note |", "|---|---|---|---|---|---|"]
    md += [f"| {a} | {b} | {c} | {d} | {e} | {f} |" for a, b, c, d, e, f in rows]
    md += detail + ["", f"**{len(rows) - len(fails)} PASS, {len(fails)} FAIL.**"]
    REPORT.write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
