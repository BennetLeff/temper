#!/usr/bin/env python3
"""Stage 52: geometric check of the bank-variant fit mark on the built board (F.SilkS, plan_board_only21.py
`bank_fit_mark`), against what the chain's capped DRC report cannot show (KiCad lists at most 199 items per type, and
s51 already has 199 silk_over_copper / silk_overlap items, so an equal count proves nothing).

    python3 -I validation-results/11-candidates/s52-proto-bom/scripts/bank_mark52.py BUILD/section.kicad_pcb
        -> s52-proto-bom/results/bank-mark-s52.json

KiCad's own python (bank_mark_dump52.py) turns every mark text / tick box and every neighbour inside a window around it
into polygons (pads on F.Mask with their mask expansion, footprint silk and fields, board silk, courtyards, Edge.Cuts);
shapely gives the minimum distances. Pass: no overlap with any mask opening (silk would be clipped: the DRC's
silk_over_copper), any other silk (silk_overlap), any courtyard (the mark must stay visible with the parts fitted), and
>= 0.5 mm from all of them and >= 1.5 mm from the board edge; text height = the board's other board-only text height and
stroke >= JLC's 0.15 mm minimum line width. Controls: the same distance code finds the C152 courtyard a positive
distance away and C3's pads overlap C3's own courtyard.
"""
import sys as _s; _s.dont_write_bytecode = True
import json
import subprocess
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results"
KPY = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
WIN = (180.0, 100.0, 245.0, 135.0)
CLR, EDGE_CLR, JLC_STROKE = 0.5, 1.5, 0.15


def geom(rec):
    ps = [Polygon(p) for p in rec["poly"] if len(p) >= 3]
    return unary_union([p if p.is_valid else p.buffer(0) for p in ps]) if ps else None


def main():
    board = Path(_s.argv[1])
    raw = subprocess.run([KPY, str(HERE / "bank_mark_dump52.py"), str(board), *map(str, WIN)], check=True,
                         capture_output=True, text=True).stdout
    d = json.loads(raw.strip().splitlines()[-1])
    texts = d["mark"]
    xs = [x for t in texts for p in t["poly"] for x, _ in p]
    ys = [y for t in texts for p in t["poly"] for _, y in p]
    tb = (min(xs) - 3.5, min(ys) - 1.0, max(xs) + 0.5, max(ys) + 1.0)
    boxes = [s for s in d["silk"] if s.get("bbox") and s["kind"] == "PCB_SHAPE" and "ref" not in s
             and tb[0] <= s["bbox"][0] and s["bbox"][2] <= tb[2] and tb[1] <= s["bbox"][1] and s["bbox"][3] <= tb[3]]
    mark_ids = {id(b) for b in boxes}
    others = [s for s in d["silk"] if id(s) not in mark_ids]
    mk = [(t["text"], geom(t)) for t in texts] + [(f"tick box {i + 1}", geom(b)) for i, b in enumerate(boxes)]
    mark_all = unary_union([g for _, g in mk])

    def nearest(group, label):
        best = None
        for r in group:
            g = geom(r)
            if g is None:
                continue
            dist = mark_all.distance(g)
            if best is None or dist < best[0]:
                best = (dist, f"{r.get('ref', 'board')} {r.get('pad', r.get('kind', ''))}".strip())
        return {"min_mm": round(best[0], 3) if best else None, "nearest": best[1] if best else None, "of": label}

    rows = {"mask_openings": nearest(d["mask"], "pads / mask openings on F.Mask, with mask expansion"),
            "other_silk": nearest(others, "footprint silk, fields and board silk"),
            "courtyards": nearest(d["courtyards"], "footprint courtyards (F.CrtYd)")}
    edge = unary_union([Polygon(p).exterior for p in d["edge"] if len(p) >= 3])
    rows["board_edge"] = {"min_mm": round(mark_all.distance(edge), 3), "of": "Edge.Cuts"}
    c152 = [geom(c) for c in d["courtyards"] if c.get("ref") == "C152" and c.get("courtyard")]
    c3c = [geom(c) for c in d["courtyards"] if c.get("ref") == "C3" and c.get("courtyard")]
    c3p = [geom(m) for m in d["mask"] if m.get("ref") == "C3"]
    controls = {"C152 courtyard distance > 0": bool(c152) and mark_all.distance(c152[0]) > 0,
                "C3 pads overlap C3 courtyard (distance 0)": bool(c3c and c3p) and c3p[0].distance(c3c[0]) == 0.0}
    fails = [k for k in ("mask_openings", "other_silk", "courtyards") if rows[k]["min_mm"] is None or rows[k]["min_mm"] < CLR]
    if rows["board_edge"]["min_mm"] < EDGE_CLR:
        fails.append("board_edge")
    if len(texts) != 3 or len(boxes) != 2:
        fails.append(f"mark items: {len(texts)} texts / {len(boxes)} boxes (expect 3 / 2)")
    for t in texts:
        if t["stroke_mm"] < JLC_STROKE - 1e-9:
            fails.append(f"stroke {t['stroke_mm']} < {JLC_STROKE}: {t['text']}")
    for b in boxes:
        if b["stroke_mm"] < JLC_STROKE - 1e-9:
            fails.append(f"box stroke {b['stroke_mm']}")
    fails += [k for k, v in controls.items() if not v]
    out = {"board": str(board), "window_mm": WIN, "mark_bbox_mm": [round(v, 2) for v in mark_all.bounds],
           "texts": [{"text": t["text"], "height_mm": round(t["size_mm"], 3), "stroke_mm": round(t["stroke_mm"], 3)}
                     for t in texts],
           "tick_boxes_mm": [[round(v, 2) for v in b["bbox"]] for b in boxes],
           "tick_box_stroke_mm": [round(b["stroke_mm"], 3) for b in boxes],
           "clearances": rows, "rule": {"clearance_mm": CLR, "edge_mm": EDGE_CLR, "jlc_min_stroke_mm": JLC_STROKE},
           "controls": controls, "failed": fails, "verdict": "PASS" if not fails else "FAIL"}
    OUT.mkdir(exist_ok=True)
    (OUT / "bank-mark-s52.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    _s.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
