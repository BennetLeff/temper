#!/usr/bin/env python3
"""Jet-strip height gate: nothing under the airflow jet box may stand more than 4.0 mm above the board top.

    python3 jet_strip_height.py BOXES.json COURTYARDS.json [OUT.json]     exit 1 on any part over the limit

Why (OPEN-ITEMS S2, temper-8d airflow-r1 DECISIONS D6.2): the route above the 18 A still-air ceiling is eight Ø3 mm
jets from a box whose floor sits 6.0 mm above the board, over the strip between the TO-247 front faces and the HF film
caps. The jets need the 2 mm clear gap, and the B3 jet case assumes the strip's copper and low SMD bodies see the jet.
A later stage must not put a tall part there.

Region: model / KiCad frame (y down), x 0-90, y 7.0-23.5 mm: the B3 jet-case region (`board_h_sweep.py:86`), which
also contains the jet box's projected footprint + 1 mm (model x 1-88, y 10.5-22.5). A STEP solid counts if its AABB
overlaps the region at all (stricter than the B3 model's centre rule). BOXES.json is the chain's board_boxes.py output
(z up from the board bottom); the board top is the top face of the largest-area solid, the bare board.
"""
import json
import sys

REGION = (0.0, 90.0, 7.0, 23.5)     # x0, x1, y0, y1, mm
LIMIT_MM = 4.0                      # above the board top; jet box floor at 6.0 mm (airflow-r1 HANDOFF item 1)


def owner(box, court):
    cx, cy = (box[0] + box[3]) / 2, (box[1] + box[4]) / 2
    best = None
    for ref, c in court.items():
        if c[0] <= cx <= c[2] and c[1] <= cy <= c[3]:
            a = (c[2] - c[0]) * (c[3] - c[1])
            if best is None or a < best[0]:
                best = (a, ref)
    return best[1] if best else None


def check(boxes, court, region=REGION, limit=LIMIT_MM):
    board = max(boxes, key=lambda b: (b[3] - b[0]) * (b[4] - b[1]))
    top = board[5]
    x0, x1, y0, y1 = region
    parts = {}
    for b in boxes:
        if b is board or b[5] <= top + 1e-3:
            continue
        if b[3] > x0 and b[0] < x1 and b[4] > y0 and b[1] < y1:
            ref = owner(b, court) or "UNATTRIBUTED"
            parts[ref] = max(parts.get(ref, 0.0), round(b[5] - top, 3))
    over = sorted(r for r, h in parts.items() if h > limit)
    worst = max(parts.items(), key=lambda kv: kv[1]) if parts else (None, 0.0)
    return {"region_mm": list(region), "limit_mm": limit, "board_top_mm": round(top, 3),
            "max_height_mm": worst[1], "worst_ref": worst[0], "over_limit": over,
            "parts": dict(sorted(parts.items())), "pass": not over}


def main():
    boxes = json.load(open(sys.argv[1]))["boxes"]
    court = json.load(open(sys.argv[2]))
    res = check(boxes, court)
    if len(sys.argv) > 3:
        with open(sys.argv[3], "w") as f:
            json.dump(res, f, indent=1)
            f.write("\n")
    print(f"jet strip: max {res['max_height_mm']} mm ({res['worst_ref']}), limit {LIMIT_MM} mm -> "
          f"{'PASS' if res['pass'] else 'FAIL ' + str(res['over_limit'])}")
    sys.exit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()
