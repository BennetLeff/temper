# provenance: commit=fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 dirty=false
# Branch agent/residual-connectivity-diagnosis, branched from fd4e73644
# (= origin/main eb5022510 + the two backbone fixes), MIN_BARRIER_WIDTH_MM = 12.6
# -- the reference configuration the 251/82/36 figures of
# docs/evidence/2026-08-19-per-pairing-placement-routed.md come from.
# pcb/temper.kicad_pcb sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
# unchanged before AND after; never opened for writing. Every board written by
# these scripts goes to a scratch path outside the repo.
"""Execution proof: Tier 3 with a blocked GOAL cell is unsatisfiable at any
budget, and it spends its whole budget discovering that.

Reads nothing from the board. Builds synthetic occupancy grids and calls the
SAME production kernel entry Tier 3 calls (`route_segment_3d_rust`).

Claim under test
----------------
`astar_nlayer::astar_search_3d` only ever *pushes* a node after
`is_free(nx, ny)`, and detects the goal only on *pop*. Both moves that can
enter the goal cell (same-layer step, and a via from another layer at the same
x/y) test `grids[goal_layer].is_free(gx, gy)`. So if the goal cell is blocked
on its own layer, no path can be found no matter how many layers are open or
how large the budget is -- and, because nothing short-circuits, the search runs
to frontier exhaustion or the iteration cap first.
"""
from __future__ import annotations

import time

import numpy as np

from temper_placer.router_v6.astar_nlayer_rust import route_segment_3d_rust
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

CELL = 0.1
W = H = 400  # 40mm x 40mm at 0.1mm cells -- 160k cells/layer, 4 layers


def make_grids(layers=("F.Cu", "In3.Cu", "In4.Cu", "B.Cu")):
    grids = {}
    for ln in layers:
        g = OccupancyGrid(
            layer_name=ln,
            grid=np.zeros((H, W), dtype=np.int8),
            origin=(0.0, 0.0),
            cell_size=CELL,
            width_cells=W,
            height_cells=H,
        )
        grids[ln] = g
    return grids


def call(grids, start_w, goal_w, sl, gl, max_iter):
    t0 = time.perf_counter()
    r = route_segment_3d_rust(start_w, goal_w, sl, gl, grids,
                              net_id=0, max_iter=max_iter)
    return r, (time.perf_counter() - t0) * 1000.0


def main():
    start_w, goal_w = (2.0, 2.0), (35.0, 35.0)

    print("=" * 74)
    print("A. CONTROL — wide-open grids, goal cell free")
    print("=" * 74)
    for budget in (200_000, 1_000_000):
        g = make_grids()
        r, ms = call(g, start_w, goal_w, "F.Cu", "F.Cu", budget)
        print(f"  budget={budget:>9,}  found={r is not None}  {ms:8.1f} ms")

    print()
    print("=" * 74)
    print("B. GOAL CELL BLOCKED on its own layer, every other layer WIDE OPEN")
    print("   (a via cannot rescue it: entering (gx,gy,gl) requires that cell free)")
    print("=" * 74)
    for budget in (200_000, 1_000_000, 4_000_000):
        g = make_grids()
        gx, gy = g["F.Cu"].world_to_grid(*goal_w)
        g["F.Cu"].grid[gy, gx] = -1          # exactly ONE cell blocked
        r, ms = call(g, start_w, goal_w, "F.Cu", "F.Cu", budget)
        free = int(np.count_nonzero(g["F.Cu"].grid == 0))
        print(f"  budget={budget:>9,}  found={r is not None}  {ms:8.1f} ms  "
              f"(F.Cu still {free}/{W*H} cells free)")

    print()
    print("=" * 74)
    print("C. START CELL BLOCKED — seeded regardless, so it CAN still succeed")
    print("=" * 74)
    g = make_grids()
    sx, sy = g["F.Cu"].world_to_grid(*start_w)
    g["F.Cu"].grid[sy, sx] = -1
    r, ms = call(g, start_w, goal_w, "F.Cu", "F.Cu", 1_000_000)
    print(f"  budget=1,000,000  found={r is not None}  {ms:8.1f} ms")

    print()
    print("=" * 74)
    print("D. Cost of the blocked-goal case as a share of a real budget")
    print("=" * 74)
    g = make_grids()
    gx, gy = g["F.Cu"].world_to_grid(*goal_w)
    g["F.Cu"].grid[gy, gx] = -1
    _, ms_blocked = call(g, start_w, goal_w, "F.Cu", "F.Cu", 1_000_000)
    g2 = make_grids()
    _, ms_ok = call(g2, start_w, goal_w, "F.Cu", "F.Cu", 1_000_000)
    print(f"  goal free   : {ms_ok:8.1f} ms")
    print(f"  goal blocked: {ms_blocked:8.1f} ms   ({ms_blocked / max(ms_ok, 1e-9):.0f}x)")
    print()
    print("  A one-line `if not grids[gl].is_free(gx,gy): return None` precheck")
    print("  would return the same answer in O(1).")


main()
