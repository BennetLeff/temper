#!/usr/bin/env python3
"""Coarse block map and per-band utilisation of the s53 power board (reads results/power_area.json).

    python3 power_layout_map.py   -> results/power_layout_map.json (+ ASCII map on stdout)

Each 5 x 5 mm tile of the board gets the letter of the block whose courtyards cover most of it
(lower case when that cover is < 50 % of the tile, '.' when nothing covers it, ' ' off board).
Bands: the board's horizontal and vertical strips, to show where the empty area sits.
Bounding boxes only (courtyard rectangles from the parts' bboxes), so tile cover is approximate.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = HERE.parent / "results"
LET = {"bridge_fets_gate_drive": "Q", "rectifier_bus": "B", "mains_emi_fuse_mov": "M", "blower_ac_tap": "A",
       "tank_bank_studs_ct": "T", "ps2_isolated_bias": "P", "sensing_protection_isolators": "S",
       "connectors_selv_tco": "J", "mech_test": "h"}
TILE = 5.0


def main():
    d = json.loads((R / "power_area.json").read_text())
    W, H = d["bbox_mm"]
    nx, ny = int(W / TILE), int(H / TILE)
    sub = 10  # 0.5 mm sub-samples per tile edge
    step = TILE / sub
    on_board = lambda x, y: (y <= 140) or (x <= 91)  # s53 L outline (power_area outline_pts)
    cover = [[{} for _ in range(nx)] for _ in range(ny)]
    for p in d["parts"]:
        if not p["bbox"]:
            continue
        x0, y0, x1, y1 = p["bbox"]
        i0, i1 = int(x0 / step), int(x1 / step)
        j0, j1 = int(y0 / step), int(y1 / step)
        for j in range(j0, min(j1 + 1, ny * sub)):
            for i in range(i0, min(i1 + 1, nx * sub)):
                c = cover[j // sub][i // sub]
                c.setdefault((i, j), p["block"])
    rows = []
    tiles = {}
    for j in range(ny):
        line = ""
        for i in range(nx):
            cx, cy = (i + 0.5) * TILE, (j + 0.5) * TILE
            if not on_board(cx, cy):
                line += " "
                continue
            c = cover[j][i]
            if not c:
                line += "."
                tiles.setdefault("empty", 0)
                tiles["empty"] += 1
                continue
            cnt = {}
            for b in c.values():
                cnt[b] = cnt.get(b, 0) + 1
            b, n = max(cnt.items(), key=lambda kv: kv[1])
            frac = len(c) / (sub * sub)
            ch = LET.get(b, "?")
            line += ch if frac >= 0.5 else ch.lower()
            tiles.setdefault(b, 0)
            tiles[b] += 1
        rows.append(line)
    # bands: courtyard bbox cover fraction per 10 mm column and per 10 mm row (on-board cells only)
    def band_cover(axis):
        out = []
        n = int((W if axis == "x" else H) / 10)
        for k in range(n):
            tot = cov = 0
            for j in range(ny * sub):
                for i in range(nx * sub):
                    x, y = (i + 0.5) * step, (j + 0.5) * step
                    if (x if axis == "x" else y) // 10 != k or not on_board(x, y):
                        continue
                    tot += 1
                    if (i, j) in cover[j // sub][i // sub]:
                        cov += 1
            out.append({"from_mm": k * 10, "to_mm": k * 10 + 10, "cover_pct": round(100 * cov / tot, 1) if tot else None})
        return out
    res = {"tile_mm": TILE, "legend": LET, "map_rows_y_down": rows, "tiles_by_block": tiles,
           "columns_x": band_cover("x"), "rows_y": band_cover("y"),
           "note": "bbox-based cover (courtyard rectangles), approximate; the exact union is in power_area.json"}
    (R / "power_layout_map.json").write_text(json.dumps(res, indent=1))
    print("     x: 0" + " " * 44 + "145" + " " * 41 + "290")
    for j, r in enumerate(rows):
        print(f"y{j*5:4d} {r}")
    print(tiles)
    print("columns", [c["cover_pct"] for c in res["columns_x"]])
    print("rows", [c["cover_pct"] for c in res["rows_y"]])


if __name__ == "__main__":
    main()
