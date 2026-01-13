# Plan: Pin Access Alignment (Grid Alignment Strategy)

## Problem Statement
The router currently snaps start/end points to the nearest grid intersection. Because component pins are often off-grid (e.g., at `x.05`), this creates two issues:
1.  **Unconnected Items**: The trace ends at `x.0` while the pad is at `x.05`. KiCad DRC flags this gap.
2.  **Clearance Violations**: Snapping to the *nearest* grid point might choose a point too close to a neighbor, whereas the optimal access point might be slightly further away but cleaner.

## Proposed Solution: Explicit Access Nodes
Instead of modifying the A* core to handle continuous coordinates (which destroys performance), we will implement a pre-processing step to identify the **Best Access Node** for each pin.

### Architecture Update

#### 1. Pin Access Analysis (New Stage 4.1.5)
Before running A*, we will iterate through all pins involved in the routing.
For each pin `P` at `(px, py)`:
1.  **Search Neighborhood**: Check grid points within a small radius (e.g., 3 cells).
2.  **Validate**: For each candidate grid point `G` at `(gx, gy)`:
    *   Is `G` free (value 0 or owned by this net)?
    *   Is the straight line `P -> G` collision-free? (Line-of-sight check against obstacles).
3.  **Select Best**: Choose `G` that minimizes distance to `P` while maximizing clearance to obstacles.
4.  **Store**: Map `Pin -> AccessNode(gx, gy)`.

#### 2. Routing Update
*   **A* Search**: Start and End at the stored `AccessNode` grid coordinates. This keeps A* fast and integer-based.
*   **Path Reconstruction**: When converting the grid path to world coordinates (`RoutePath3D`), explicitly prepend `PinCenter` and append `PinCenter`.
    *   Resulting Path: `PinCenter -> AccessNode -> GridPath... -> AccessNode -> PinCenter`.

### Implementation Steps

1.  **Modify `astar_pathfinding.py`**:
    *   Add `find_access_node(grid, pin_pos, net_id)` helper function.
    *   In `run_astar_pathfinding`, pre-calculate `access_nodes` for all endpoints.
    *   Update `attempt_route` to use these access nodes as start/goals.
2.  **Update Output Generation**:
    *   Ensure the final `RoutePath` includes the "stringer" segments connecting the access node to the true pin center.

### Benefits
*   **Performance**: A* remains O(N) on grid graph. No float hashing.
*   **Correctness**: Guarantees that the trace physically touches the pad center (0 gap).
*   **Robustness**: Explicit line-of-sight check prevents starting in a "trapped" grid cell.

## Risks
*   **Access Failure**: If a pin is completely surrounded by obstacles (no valid access node), routing will fail. (This is correct behavior, but we must handle it gracefully).
*   **Acute Angles**: The segment `Pin -> AccessNode` might form a sharp angle with the first grid segment. (Acceptable for now; can be smoothed later).
