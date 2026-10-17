"""Tile packing for the M11 AlN stack: how many full stacks (1 x tile A + 1 x tile B) per plate.
Maximal-rectangles heuristic with random orders, kerf and edge margin; a LOWER bound on what a good nester finds."""
import random
KERF, EDGE = 0.5, 1.0
def pack(plate, order, A, B):
    W, H = plate
    free = [(EDGE, EDGE, W - EDGE, H - EDGE)]   # x0,y0,x1,y1
    placed = {"A": 0, "B": 0}
    for name in order:
        w, h = (A if name == "A" else B)
        best = None
        for (fx0, fy0, fx1, fy1) in free:
            for (tw, th) in ((w, h), (h, w)):
                if fx0 + tw <= fx1 + 1e-9 and fy0 + th <= fy1 + 1e-9:
                    score = (fx1 - fx0) * (fy1 - fy0)
                    if best is None or score < best[0]:
                        best = (score, fx0, fy0, tw, th)
        if best is None:
            continue
        _, x, y, tw, th = best
        placed[name] += 1
        nf = []
        for (fx0, fy0, fx1, fy1) in free:
            if x >= fx1 or x + tw + KERF <= fx0 or y >= fy1 or y + th + KERF <= fy0:
                nf.append((fx0, fy0, fx1, fy1)); continue
            if x - KERF > fx0: nf.append((fx0, fy0, x - KERF, fy1))
            if x + tw + KERF < fx1: nf.append((x + tw + KERF, fy0, fx1, fy1))
            if y - KERF > fy0: nf.append((fx0, fy0, fx1, y - KERF))
            if y + th + KERF < fy1: nf.append((fx0, y + th + KERF, fx1, fy1))
        free = [r for r in nf if not any(o != r and o[0] <= r[0] and o[1] <= r[1] and o[2] >= r[2] and o[3] >= r[3] for o in nf)]
    return placed
random.seed(1)
def best_stacks(plate, A, B, trials=4000):
    best = (0, 0, 0)
    for _ in range(trials):
        n = 14
        order = [random.choice("AB") for _ in range(n)]
        p = pack(plate, order, A, B)
        s = min(p["A"], p["B"])
        if (s, p["A"] + p["B"]) > (best[0], best[1] + best[2]):
            best = (s, p["A"], p["B"])
    return best
B = (73.75, 31.8)
print("plate (mm) | tile A long edge | full stacks per plate (nA, nB)")
for plate in ((114, 114), (114.3, 114.3), (127, 127), (138, 190)):
    for alen in (42.75, 40.5, 37.6):
        s, a, b = best_stacks(plate, (alen, 31.8), B)
        print(f"{plate[0]}x{plate[1]} | {alen} | {s} stacks (A {a}, B {b})")
