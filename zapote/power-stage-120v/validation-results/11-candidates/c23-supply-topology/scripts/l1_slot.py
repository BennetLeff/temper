#!/usr/bin/env python3
"""Does the KEMET / YAGEO SCF31X-220-2R1A011JH fit the L1 slot without moving a part? (DECISIONS 47 item 3)

    python3 -I l1_slot.py [COURTYARDS.json] [OUT.json]

Reads the board's part courtyards (validation-plan/enclosure-fit/native21-courtyards.json, written by the chain) and
grows the free rectangle round L1's centre: in y, the nearest courtyard edges above and below among parts that
overlap the L1 x range; in x, the same among parts that overlap the resulting y range. L1 itself is removed first.
The SCF31X body (spec sheet, YAGEO 10/15/2026: D 45 x T 42 x H 33 mm max) must fit in either orientation, before any
courtyard margin is added. The PS1 area freed at stage 38 is its stage-35 courtyard (read from the stage-35 commit with
git); it is compared with the body directly (it also lies off the L_FILT / N_FILT path, which is a second reason)."""
import json, subprocess, sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[4]
CY = Path(sys.argv[1]) if len(sys.argv) > 1 else UNIT / "validation-plan/enclosure-fit/native21-courtyards.json"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "results/l1_slot.json"
BODY = (45.0, 42.0)          # SCF31X D x T, mm (max)
TDK = "B82726S2203A020"
BASE = "0aecdc56f"           # stage-35 integration head (the s38 branch point)


def free_box(cy, cx, cyy, skip):
    others = {k: v for k, v in cy.items() if k not in skip}
    def span(lo_ax, hi_ax, c, lo_lim, hi_lim, cross):
        lo, hi = lo_lim, hi_lim
        for v in others.values():
            if v[cross[0]] < cross[2] and v[cross[1]] > cross[3]:          # overlaps on the other axis
                if v[hi_ax] <= c:
                    lo = max(lo, v[hi_ax])
                elif v[lo_ax] >= c:
                    hi = min(hi, v[lo_ax])
        return lo, hi
    x0, x1 = cx - 0.5, cx + 0.5
    y0, y1 = span(1, 3, cyy, -1e9, 1e9, (0, 2, x1, x0))
    x0, x1 = span(0, 2, cx, -1e9, 1e9, (1, 3, y1, y0))
    y0, y1 = span(1, 3, cyy, -1e9, 1e9, (0, 2, x1, x0))
    return [round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3)]


def fits(box):
    w, h = box[2] - box[0], box[3] - box[1]
    return {"w_mm": round(w, 3), "h_mm": round(h, 3),
            "fits_45x42": w >= BODY[0] and h >= BODY[1], "fits_42x45": w >= BODY[1] and h >= BODY[0]}


def main():
    cy = json.loads(CY.read_text())
    l1 = cy["L1"]
    c = ((l1[0] + l1[2]) / 2, (l1[1] + l1[3]) / 2)
    box = free_box(cy, c[0], c[1], {"L1"})
    blockers = sorted(k for k, v in cy.items() if k != "L1" and
                      any(abs(v[i] - box[j]) < 1e-6 for i, j in ((3, 1), (1, 3), (2, 0), (0, 2))))
    s35 = json.loads(subprocess.run(["git", "show", f"{BASE}:./validation-plan/enclosure-fit/native21-courtyards.json"],
                                    cwd=UNIT, capture_output=True, text=True, check=True).stdout)
    pbox = s35["PS1"]
    inside = sorted(k for k, v in cy.items() if v[0] < pbox[2] and v[2] > pbox[0] and v[1] < pbox[3] and v[3] > pbox[1])
    out = {"courtyards": str(CY.relative_to(UNIT)) if CY.is_relative_to(UNIT) else str(CY),
           "scf31x_body_mm": BODY, "l1_courtyard_TDK": l1,
           "l1_slot_free_box": box, "l1_slot": fits(box), "l1_slot_bounded_by": blockers,
           "ps1_courtyard_s35": pbox, "ps1_freed": fits(pbox), "parts_now_overlapping_ps1_box": inside}
    out["verdict"] = ("SCF31X fits the L1 slot" if out["l1_slot"]["fits_45x42"] or out["l1_slot"]["fits_42x45"]
                      else "SCF31X does not fit the L1 slot without moving a bounding part")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
