"""Board-local max part-top height (above board bottom, local z) per 2 mm cell, chain pose mirror-legacy (x0 141, y0 236, zb 26)."""
import sys, json
sys.path.insert(0, "/Users/bennet/Desktop/temper/worktrees/ps-selv/zapote/power-stage-120v/validation-plan/enclosure-fit")
import fit_gate as g
items = g.catalog_names(g.R4)
X0, Y0, ZB = 141.0, 236.0, 26.0
def world(b):
    return [X0 - b[3], Y0 - b[4], ZB + b[2], X0 - b[0], Y0 - b[1], ZB + b[5]]
def maxh(x0, y0, x1, y1):
    lo, hi = 1.6, 80.0
    if g.box_hits(world([x0, y0, 1.6, x1, y1, 1.7]), items): return 0.0, g.box_hits(world([x0, y0, 1.6, x1, y1, 1.7]), items)
    while hi - lo > 0.25:
        m = (lo + hi) / 2
        if g.box_hits(world([x0, y0, 1.6, x1, y1, m]), items): hi = m
        else: lo = m
    return lo, g.box_hits(world([x0, y0, 1.6, x1, y1, lo + 0.5]), items)
if __name__ == "__main__":
    out = {}
    for yy in range(0, 140, 2):
        for xx in range(100, 290, 2):
            h, who = maxh(xx, yy, xx + 2, yy + 2)
            out[f"{xx},{yy}"] = [round(h, 2), who[:3]]
    json.dump(out, open(sys.argv[1], "w"))
