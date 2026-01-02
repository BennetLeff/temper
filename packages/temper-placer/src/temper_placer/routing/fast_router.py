"""JIT-compiled A* pathfinding using Numba.

This module provides a high-performance implementation of A* pathfinding
that runs 50-100x faster than pure Python. It uses Numba to compile
the core logic to machine code.
"""

import heapq
import math
import numpy as np

# Try to import numba, fall back gracefully if not installed
try:
    from numba import njit, int32, float32
    from numba.typed import List
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    # Dummy decorator if numba is missing
    def njit(*args, **kwargs):
        def wrapper(func):
            return func
        return wrapper

@njit(cache=True)
def get_neighbors_numba(cx, cy, cl, grid_w, grid_h, num_layers, occupancy, allow_violation):
    """Get valid neighbors for a cell."""
    neighbors = []
    
    # Planar moves (NSEW)
    # Check 4 directions: (0, 1), (0, -1), (1, 0), (-1, 0)
    # Manual unrolling for speed
    
    # (0, 1)
    nx, ny = cx, cy + 1
    if 0 <= nx < grid_w and 0 <= ny < grid_h:
        occ = occupancy[nx, ny, cl]
        if occ != -1 or allow_violation:
            neighbors.append((nx, ny, cl))
            
    # (0, -1)
    nx, ny = cx, cy - 1
    if 0 <= nx < grid_w and 0 <= ny < grid_h:
        occ = occupancy[nx, ny, cl]
        if occ != -1 or allow_violation:
            neighbors.append((nx, ny, cl))

    # (1, 0)
    nx, ny = cx + 1, cy
    if 0 <= nx < grid_w and 0 <= ny < grid_h:
        occ = occupancy[nx, ny, cl]
        if occ != -1 or allow_violation:
            neighbors.append((nx, ny, cl))

    # (-1, 0)
    nx, ny = cx - 1, cy
    if 0 <= nx < grid_w and 0 <= ny < grid_h:
        occ = occupancy[nx, ny, cl]
        if occ != -1 or allow_violation:
            neighbors.append((nx, ny, cl))
            
    # Via moves (Up/Down)
    if num_layers > 1:
        # Up
        if cl < num_layers - 1:
            occ = occupancy[cx, cy, cl + 1]
            if occ != -1 or allow_violation:
                neighbors.append((cx, cy, cl + 1))
        # Down
        if cl > 0:
            occ = occupancy[cx, cy, cl - 1]
            if occ != -1 or allow_violation:
                neighbors.append((cx, cy, cl - 1))
                
    return neighbors

@njit(cache=True)
def heuristic_numba(x1, y1, l1, x2, y2, l2):
    """Manhattan distance heuristic."""
    return abs(x1 - x2) + abs(y1 - y2) + abs(l1 - l2) * 2

@njit(cache=True)
def dilate_grid_numba(grid, radius):
    """Dilate non-zero elements in a 3D grid by radius (2D per layer)."""
    w, h, num_layers = grid.shape
    out = np.zeros_like(grid)
    
    for z in range(num_layers):
        for x in range(w):
            for y in range(h):
                if grid[x, y, z] != 0:
                    # Set window in output
                    x_start = max(0, x - radius)
                    x_end = min(w, x + radius + 1)
                    y_start = max(0, y - radius)
                    y_end = min(h, y + radius + 1)
                    out[x_start:x_end, y_start:y_end, z] = 1
    return out


@njit(cache=True)
def find_path_astar_numba(
    start_x, start_y, start_l,
    end_x, end_y, end_l,
    grid_w, grid_h, num_layers,
    occupancy,
    history_cost,
    present_congestion,
    via_cost,
    p_scale,
    cost_map=None,
    clearance_mask=None,
    soft_blocking=False,
    soft_c_space=None,
    tap_mask=None
):
    """
    Numba-accelerated A* pathfinding.

    Args:
        start_x, start_y, start_l: Start coordinates
        end_x, end_y, end_l: End coordinates
        grid_w, grid_h: Grid dimensions
        num_layers: Number of layers
        occupancy: 3D int32 array (-1=blocked, 0=free, 2=routed)
        history_cost: 3D float32 array
        present_congestion: 3D float32 array
        via_cost: Cost of a via
        p_scale: Penalty scale for congestion
        cost_map: Optional 2D float32 array for additional node costs (None if not used)
        clearance_mask: Optional 3D int32 array (1=blocked by clearance, 0=free)
        soft_blocking: If False, treat occupied cells as blocked (no crossing).
                       If True, allow routing through at high cost (negotiated congestion).
        soft_c_space: Optional 2D float32 array for soft obstacle costs.
        tap_mask: Optional 3D int32 array (1=forbidden tap point, 0=allowed).
                  Used for star-point routing to prevent joining existing traces.

    Returns:
        List of (x, y, l) coordinates or empty list if no path.
    """
    
    # Priority queue: (f_score, counter, x, y, l)
    # Numba's heapq implementation requires identical tuples.
    # We use a counter to break ties.
    pq = [(0.0, 0.0, float(start_x), float(start_y), float(start_l))] # Ensure strict float type consistency
    
    # Cost to reach each cell (g_score)
    # Initialize with infinity
    g_score = np.full((grid_w, grid_h, num_layers), np.inf, dtype=np.float32)
    g_score[start_x, start_y, start_l] = 0.0
    
    # Came from map: stores (sources_x, source_y, source_l)
    # Initialize with -1
    came_from_x = np.full((grid_w, grid_h, num_layers), -1, dtype=np.int32)
    came_from_y = np.full((grid_w, grid_h, num_layers), -1, dtype=np.int32)
    came_from_l = np.full((grid_w, grid_h, num_layers), -1, dtype=np.int32)
    
    visited = np.zeros((grid_w, grid_h, num_layers), dtype=np.bool_)
    
    counter = 0.0
    
    while len(pq) > 0:
        f, _, cx_f, cy_f, cl_f = heapq.heappop(pq)
        cx, cy, cl = int(cx_f), int(cy_f), int(cl_f)
        
        if visited[cx, cy, cl]:
            continue
        visited[cx, cy, cl] = True
        
        if cx == end_x and cy == end_y and cl == end_l:
            # Reconstruct path
            path = []
            curr_x, curr_y, curr_l = end_x, end_y, end_l
            while curr_x != -1:
                path.append((curr_x, curr_y, curr_l))
                px, py, pl = came_from_x[curr_x, curr_y, curr_l], came_from_y[curr_x, curr_y, curr_l], came_from_l[curr_x, curr_y, curr_l]
                curr_x, curr_y, curr_l = px, py, pl
            
            # Use list comprehension for reversal if needed, but simplistic reversed logic is fine
            # Numba efficient way involves creating a new list
            res = [(0, 0, 0)] # Dummy list initialization to fix type inference
            res.pop() # empty it
            for i in range(len(path) - 1, -1, -1):
                res.append(path[i])
            return res

        # Get neighbors (inline logic would be faster but function call is ok with inlining)
        # We inline the neighbor generation for maximum speed in the loop
        
        # Directions: Right, Left, Up, Down, Via Up, Via Down
        # Store delta-x, delta-y, delta-l
        moves = [
            (0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0),
            (0, 0, 1), (0, 0, -1)
        ]
        
        for dx, dy, dl in moves:
            nx, ny, nl = cx + dx, cy + dy, cl + dl
            
            # Check bounds
            if not (0 <= nx < grid_w and 0 <= ny < grid_h and 0 <= nl < num_layers):
                continue
                
            # Check blocked (component)
            if occupancy[nx, ny, nl] == -1:
                continue

            # Check tap mask (forbid star-point tapping)
            if tap_mask is not None:
                if tap_mask[nx, ny, nl] != 0:
                    continue

            # Soft C-space cost
            c_space_cost = 0.0
            if soft_c_space is not None:
                c_space_cost = soft_c_space[nx, ny]
                if c_space_cost == np.inf:
                    continue

            # Check if cell is occupied by another net
            cell_occupied = occupancy[nx, ny, nl] == 2

            # If soft_blocking is disabled, occupied cells are impassable
            if cell_occupied and not soft_blocking:
                continue

            # Check clearance violation
            if clearance_mask is not None:
                if clearance_mask[nx, ny, nl] != 0:
                    continue

            # Compute cost

            # Base step cost
            step_cost = 1.0

            # Via cost
            if nl != cl:
                step_cost += via_cost

            # Congestion cost
            # cost = (base + h) * (1 + p * p_scale)
            h_cost = history_cost[nx, ny, nl]
            p_cost = present_congestion[nx, ny, nl]

            # Sharing penalty for occupied cells (negotiated congestion)
            # Only applies when soft_blocking=True
            sharing = 0.0
            if cell_occupied and soft_blocking:
                # Match Python behavior: 50.0 * (1.0 + congestion)
                sharing = 50.0 * (1.0 + p_cost)
                
            # Cost map multiplier (strategy multiplier)
            strategy_mult = 1.0
            if cost_map is not None:
                if cost_map.ndim == 2:
                    strategy_mult = cost_map[nx, ny]
                else:
                    strategy_mult = cost_map[nx, ny, nl]
                
            move_cost = strategy_mult * (step_cost + h_cost + c_space_cost + sharing) * (1.0 + p_cost * p_scale)
            
            tentative_g = g_score[cx, cy, cl] + move_cost
            
            if tentative_g < g_score[nx, ny, nl]:
                g_score[nx, ny, nl] = tentative_g
                
                # Heuristic
                h = abs(nx - end_x) + abs(ny - end_y) + abs(nl - end_l) * 2.0
                new_f = tentative_g + h
                
                came_from_x[nx, ny, nl] = cx
                came_from_y[nx, ny, nl] = cy
                came_from_l[nx, ny, nl] = cl
                
                counter += 1.0 # monotonic counter for tie-breaking
                heapq.heappush(pq, (float(new_f), float(counter), float(nx), float(ny), float(nl)))

    # Create typed empty list for failure case
    empty_res = [(0, 0, 0)]
    empty_res.pop()
    return empty_res # No path

# WARMUP ROUTINE
if HAS_NUMBA:
    def _warmup():
        """Trigger JIT compilation for all signature variations."""
        # Create minimal dummy data
        w, h, l = 3, 3, 2
        occ = np.zeros((w, h, l), dtype=np.int32)
        hist = np.zeros((w, h, l), dtype=np.float32)
        cong = np.zeros((w, h, l), dtype=np.float32)
        cmap = np.zeros((w, h), dtype=np.float32)
        cmask = np.zeros((w, h, l), dtype=np.int32)
        cspace = np.zeros((w, h), dtype=np.float32)

        # 1. Warmup without cost_map/clearance_mask, soft_blocking=False
        try:
            find_path_astar_numba(
                0, 0, 0, 2, 2, 0,
                w, h, l,
                occ, hist, cong,
                1.0, 1.0, None, None, False, None
            )
        except: pass

        # 2. Warmup with cost_map, soft_blocking=False
        try:
            find_path_astar_numba(
                0, 0, 0, 2, 2, 0,
                w, h, l,
                occ, hist, cong,
                1.0, 1.0, cmap, None, False, None
            )
        except: pass

        # 3. Warmup with soft_blocking=True and soft_c_space
        try:
            find_path_astar_numba(
                0, 0, 0, 2, 2, 0,
                w, h, l,
                occ, hist, cong,
                1.0, 1.0, cmap, cmask, True, cspace
            )
        except: pass

        # 4. Warmup with 3D cost_map
        try:
            cmap_3d = np.zeros((w, h, l), dtype=np.float32)
            find_path_astar_numba(
                0, 0, 0, 2, 2, 0,
                w, h, l,
                occ, hist, cong,
                1.0, 1.0, cmap_3d, None, False, None
            )
        except: pass

    # Execute warmup on import
    _warmup()
