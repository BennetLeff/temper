# provenance: commit=fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 dirty=false
# Branch agent/residual-connectivity-diagnosis, branched from fd4e73644
# (= origin/main eb5022510 + the two backbone fixes), MIN_BARRIER_WIDTH_MM = 12.6
# -- the reference configuration the 251/82/36 figures of
# docs/evidence/2026-08-19-per-pairing-placement-routed.md come from.
# pcb/temper.kicad_pcb sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
# unchanged before AND after; never opened for writing. Every board written by
# these scripts goes to a scratch path outside the repo.
"""Edge case for the proposed Tier-3 blocked-goal precheck.

If a blocked cell that is BOTH start and goal still reports `found` today,
then a naive `goal blocked -> return None` precheck is a REGRESSION, not a
no-op, and the precheck must carry a `start != goal` guard.
"""
import numpy as np

from temper_placer.router_v6.astar_nlayer_rust import route_segment_3d_rust
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

W = H = 200
CELL = 0.1


def grids():
    return {
        ln: OccupancyGrid(
            layer_name=ln,
            grid=np.zeros((H, W), dtype=np.int8),
            origin=(0.0, 0.0),
            cell_size=CELL,
            width_cells=W,
            height_cells=H,
        )
        for ln in ("F.Cu", "B.Cu")
    }


g = grids()
pt = (5.0, 5.0)
gx, gy = g["F.Cu"].world_to_grid(*pt)
g["F.Cu"].grid[gy, gx] = -1
r = route_segment_3d_rust(pt, pt, "F.Cu", "F.Cu", g, net_id=0, max_iter=200_000)
print("start == goal, cell BLOCKED  -> found =", r is not None)

g2 = grids()
r2 = route_segment_3d_rust(pt, pt, "F.Cu", "F.Cu", g2, net_id=0, max_iter=200_000)
print("start == goal, cell free     -> found =", r2 is not None)
