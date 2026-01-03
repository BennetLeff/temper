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
def get_asymmetric_clearance_numba(current_class, obstacle_class, min_clearance):
    """Get required clearance between two net classes (Numba version)."""
    # CLASS_HV = 1, CLASS_LV = 2
    if current_class == 0:  # Default class
        return min_clearance
        
    if (current_class == 1 and obstacle_class != 1) or \
       (current_class != 1 and obstacle_class == 1):
        return 8.0  # Reinforced isolation
        
    if current_class == 1 and obstacle_class == 1:
        return 2.5  # Basic isolation
        
    return min_clearance


@njit(cache=True)
def find_path_astar_numba(
    start_x,
    start_y,
    start_l,
    end_x,
    end_y,
    end_l,
    grid_w,
    grid_h,
    num_layers,
    occupancy,
    history_cost,
    present_congestion,
    via_cost,
    p_scale,
    cost_map=None,
    clearance_mask=None,
    soft_blocking=False,
    soft_c_space=None,
    tap_mask=None,
    allowed_layers_mask=None,
    class_grid=None,
    current_class_id=0,
    min_clearance=0.0,
    cell_size=1.0,
    primary_layer_idx=-1,
    layer_penalty=0.0,
    owner_grid=None,
    current_net_id=0,
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
        class_grid: Optional 3D int8 array for net class IDs.
        current_class_id: Class ID of the net being routed.
        min_clearance: Minimum clearance in mm.
        cell_size: Grid cell size in mm.

    Returns:
        List of (x, y, l) coordinates or empty list if no path.
    """

    # Priority queue: (f_score, counter, x, y, l)
    # Numba's heapq implementation requires identical tuples.
    # We use a counter to break ties.
    pq = [
        (0.0, 0.0, float(start_x), float(start_y), float(start_l))
    ]  # Ensure strict float type consistency

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
                px, py, pl = (
                    came_from_x[curr_x, curr_y, curr_l],
                    came_from_y[curr_x, curr_y, curr_l],
                    came_from_l[curr_x, curr_y, curr_l],
                )
                curr_x, curr_y, curr_l = px, py, pl

            # Use list comprehension for reversal if needed, but simplistic reversed logic is fine
            # Numba efficient way involves creating a new list
            res = [(0, 0, 0)]  # Dummy list initialization to fix type inference
            res.pop()  # empty it
            for i in range(len(path) - 1, -1, -1):
                res.append(path[i])
            return res

        # Get neighbors (inline logic would be faster but function call is ok with inlining)
        # We inline the neighbor generation for maximum speed in the loop

        # Directions: Right, Left, Up, Down, Via Up, Via Down
        # Store delta-x, delta-y, delta-l
        moves = [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]

        for dx, dy, dl in moves:
            nx, ny, nl = cx + dx, cy + dy, cl + dl

            # Check bounds
            if not (0 <= nx < grid_w and 0 <= ny < grid_h and 0 <= nl < num_layers):
                continue

            if allowed_layers_mask is not None:
                if not allowed_layers_mask[nl]:
                    continue

            # Check blocked (component)
            if occupancy[nx, ny, nl] == -1:
                continue

            # Check tap mask (forbid star-point tapping)
            if tap_mask is not None:
                if tap_mask[nx, ny, nl] != 0:
                    continue
            
            # Check class clearance (HV/LV isolation)
            # This is the "Numba Port" of temper-kmbw
            if class_grid is not None and current_class_id != 0:
                # We check a radius around the neighbor
                # For performance, we first check the neighbor itself
                obs_class = class_grid[nx, ny, nl]
                if obs_class != 0 and obs_class != current_class_id:
                    req = get_asymmetric_clearance_numba(current_class_id, obs_class, min_clearance)
                    if 0.0 < req: # Distance is 0
                         continue

                # If we are HV/LV, scan radius
                # Using 3.0mm radius as in Python implementation
                # This loop might be slow if not careful, but Numba makes it fast.
                # Optimization: Only scan if potential conflict exists?
                # We assume sparse class_grid (mostly 0).
                
                # Check radius only if we passed the center check
                radius_mm = 8.0  # Increased to 8.0mm for HV/LV isolation
                radius_cells = int(math.ceil(radius_mm / cell_size))
                
                violation = False
                for rdx in range(-radius_cells, radius_cells + 1):
                    for rdy in range(-radius_cells, radius_cells + 1):
                        rnx, rny = nx + rdx, ny + rdy
                        if 0 <= rnx < grid_w and 0 <= rny < grid_h:
                            obs_c = class_grid[rnx, rny, nl]
                            if obs_c != 0 and obs_c != current_class_id:
                                dist = math.sqrt(rdx*rdx + rdy*rdy) * cell_size
                                req = get_asymmetric_clearance_numba(current_class_id, obs_c, min_clearance)
                                if dist < req:
                                    violation = True
                                    break
                    if violation:
                        break
                if violation:
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
            
            # Layer penalty (discourage layers other than primary_layer)
            if primary_layer_idx != -1 and nl != primary_layer_idx:
                step_cost += layer_penalty

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

            # Net ownership check (prevent same-layer crossing)
            owner_penalty = 0.0
            if owner_grid is not None and current_net_id != 0:
                owner = owner_grid[nx, ny, nl]
                if owner != 0 and owner != current_net_id:
                    # HEAVY penalty for crossing another net on the same layer
                    # In final pass (soft_blocking=False), this is impassable due to occupancy=2
                    # In RRR iterations, this helps avoid creating shortcuts through other nets
                    owner_penalty = 1000.0

            move_cost = (
                strategy_mult
                * (step_cost + h_cost + c_space_cost + sharing + owner_penalty)
                * (1.0 + p_cost * p_scale)
            )

            tentative_g = g_score[cx, cy, cl] + move_cost

            if tentative_g < g_score[nx, ny, nl]:
                g_score[nx, ny, nl] = tentative_g

                # Heuristic
                h = abs(nx - end_x) + abs(ny - end_y) + abs(nl - end_l) * 2.0
                new_f = tentative_g + h

                came_from_x[nx, ny, nl] = cx
                came_from_y[nx, ny, nl] = cy
                came_from_l[nx, ny, nl] = cl

                counter += 1.0  # monotonic counter for tie-breaking
                heapq.heappush(pq, (float(new_f), float(counter), float(nx), float(ny), float(nl)))

    # Create typed empty list for failure case
    empty_res = [(0, 0, 0)]
    empty_res.pop()
    return empty_res  # No path


@njit(cache=True)
def find_path_astar_numba_adaptive(
    start_x,
    start_y,
    start_l,
    end_x,
    end_y,
    end_l,
    grid_w,
    grid_h,
    num_layers,
    occupancy,
    history_cost,
    present_congestion,
    via_cost,
    p_scale,
    dist_map,
    cost_map=None,
    clearance_mask=None,
    soft_blocking=False,
    soft_c_space=None,
    tap_mask=None,
    guide_map=None,
    guide_bias=0.0,
    class_grid=None,
    current_class_id=0,
    min_clearance=0.0,
    cell_size=1.0,
    allowed_layers_mask=None,
    primary_layer_idx=-1,
    layer_penalty=0.0,
    owner_grid=None,
    current_net_id=0,
):
    """
    Numba-accelerated A* pathfinding with adaptive distance map heuristic.

    This is the core function for temper-tfvr: Port Adaptive A* to Numba.
    Uses a pre-computed distance map as heuristic instead of Manhattan distance,
    providing a tighter bound and reducing A* search iterations.

    Supports guide_map for hierarchical routing (guided pass).

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
        dist_map: 3D float32 array with pre-computed distances to target (from BFS)
        cost_map: Optional 2D float32 array for additional node costs
        clearance_mask: Optional 3D int32 array (1=blocked by clearance, 0=free)
        soft_blocking: If False, treat occupied cells as blocked.
        soft_c_space: Optional 2D float32 array for soft obstacle costs.
        tap_mask: Optional 3D int32 array (1=forbidden tap point, 0=allowed).
        guide_map: Optional 3D float32 array for hierarchical guide biasing.
        guide_bias: Strength of guide biasing (default 0.0).
        class_grid: Optional 3D int8 array for net class IDs.
        current_class_id: Class ID of the net being routed.
        min_clearance: Minimum clearance in mm.
        cell_size: Grid cell size in mm.

    Returns:
        List of (x, y, l) coordinates or empty list if no path.
    """
    INF = float("inf")

    pq = [(0.0, 0.0, float(start_x), float(start_y), float(start_l))]

    # Work arrays - direct allocation is faster than pooling due to .fill() overhead
    g_score = np.full((grid_w, grid_h, num_layers), INF, dtype=np.float32)
    g_score[start_x, start_y, start_l] = 0.0

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
            # print("DEBUG_NUMBA: Path Found!")
            path = []
            curr_x, curr_y, curr_l = end_x, end_y, end_l
            while curr_x != -1:
                path.append((curr_x, curr_y, curr_l))
                px, py, pl = (
                    came_from_x[curr_x, curr_y, curr_l],
                    came_from_y[curr_x, curr_y, curr_l],
                    came_from_l[curr_x, curr_y, curr_l],
                )
                curr_x, curr_y, curr_l = px, py, pl

            res = [(0, 0, 0)]
            res.pop()
            for i in range(len(path) - 1, -1, -1):
                res.append(path[i])
            return res

        moves = [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]

        for dx, dy, dl in moves:
            nx, ny, nl = cx + dx, cy + dy, cl + dl

            if not (0 <= nx < grid_w and 0 <= ny < grid_h and 0 <= nl < num_layers):
                continue

            if allowed_layers_mask is not None:
                if not allowed_layers_mask[nl]:
                    continue

            if occupancy[nx, ny, nl] == -1:
                continue

            if tap_mask is not None:
                if tap_mask[nx, ny, nl] != 0:
                    continue

            # Class Clearance Check (HV/LV isolation) - Adaptive Version
            if class_grid is not None and current_class_id != 0:
                # print("DEBUG_NUMBA: Checking clearance for class", current_class_id)
                obs_class = class_grid[nx, ny, nl]
                if obs_class != 0 and obs_class != current_class_id:
                    req = get_asymmetric_clearance_numba(current_class_id, obs_class, min_clearance)
                    if 0.0 < req:
                         continue

                # Check radius only if we passed the center check
                radius_mm = 8.0  # Increased to 8.0mm for HV/LV isolation
                radius_cells = int(math.ceil(radius_mm / cell_size))
                
                violation = False
                for rdx in range(-radius_cells, radius_cells + 1):
                    for rdy in range(-radius_cells, radius_cells + 1):
                        rnx, rny = nx + rdx, ny + rdy
                        if 0 <= rnx < grid_w and 0 <= rny < grid_h:
                            obs_c = class_grid[rnx, rny, nl]
                            if obs_c != 0 and obs_c != current_class_id:
                                dist = math.sqrt(rdx*rdx + rdy*rdy) * cell_size
                                req = get_asymmetric_clearance_numba(current_class_id, obs_c, min_clearance)
                                if dist < req:
                                    violation = True
                                    break
                    if violation:
                        break
                if violation:
                    continue

            c_space_cost = 0.0
            if soft_c_space is not None:
                if soft_c_space.ndim == 2:
                    c_space_cost = soft_c_space[nx, ny]
                else:
                    c_space_cost = soft_c_space[nx, ny, nl]

                if c_space_cost == INF:
                    continue

            cell_occupied = occupancy[nx, ny, nl] == 2

            if cell_occupied and not soft_blocking:
                continue

            if clearance_mask is not None:
                if clearance_mask[nx, ny, nl] != 0:
                    continue

            step_cost = 1.0

            # Layer penalty
            if primary_layer_idx != -1 and nl != primary_layer_idx:
                step_cost += layer_penalty

            if nl != cl:
                step_cost += via_cost

            h_cost = history_cost[nx, ny, nl]
            p_cost = present_congestion[nx, ny, nl]

            sharing = 0.0
            if cell_occupied and soft_blocking:
                sharing = 50.0 * (1.0 + p_cost)

            strategy_mult = 1.0
            if cost_map is not None:
                if cost_map.ndim == 2:
                    strategy_mult = cost_map[nx, ny]
                else:
                    strategy_mult = cost_map[nx, ny, nl]

            # If multiplier is infinity, skip this neighbor
            if strategy_mult >= INF:
                continue

            # Net ownership check (prevent same-layer crossing)
            owner_penalty = 0.0
            if owner_grid is not None and current_net_id != 0:
                owner = owner_grid[nx, ny, nl]
                if owner != 0 and owner != current_net_id:
                    owner_penalty = 1000000.0

            move_cost = (
                strategy_mult
                * (step_cost + h_cost + c_space_cost + sharing + owner_penalty)
                * (1.0 + p_cost * p_scale)
            )

            tentative_g = g_score[cx, cy, cl] + move_cost

            if tentative_g < g_score[nx, ny, nl]:
                g_score[nx, ny, nl] = tentative_g

                h = dist_map[nx, ny, nl]
                if h >= INF:
                    h = abs(nx - end_x) + abs(ny - end_y) + abs(nl - end_l) * 2.0

                # Apply guide map bias (hierarchical routing)
                if guide_map is not None:
                    # Find min distance across ALL layers at this (x,y)
                    # to match the logic in hierarchical.py
                    min_guide_dist = guide_map[nx, ny, 0]
                    for layer_idx in range(1, num_layers):
                        d_guide = guide_map[nx, ny, layer_idx]
                        if d_guide < min_guide_dist:
                            min_guide_dist = d_guide

                    # Reduction in h means higher priority
                    h += -min(min_guide_dist, 20.0) * guide_bias

                new_f = tentative_g + h

                came_from_x[nx, ny, nl] = cx
                came_from_y[nx, ny, nl] = cy
                came_from_l[nx, ny, nl] = cl

                counter += 1.0
                heapq.heappush(pq, (float(new_f), float(counter), float(nx), float(ny), float(nl)))

    # print("DEBUG_NUMBA: No path found")
    empty_res = [(0, 0, 0)]
    empty_res.pop()
    return empty_res


@njit(cache=True)
def compute_distance_map_numba(
    target_x: int,
    target_y: int,
    target_l: int,
    grid_w: int,
    grid_h: int,
    num_layers: int,
    occupancy: np.ndarray,
) -> np.ndarray:
    """Numba-accelerated BFS to compute distance map from target.

    This provides obstacle-aware distance from any cell to the target,
    giving a tight admissible heuristic for A*.

    Performance: ~50-100x faster than pure Python BFS.

    Args:
        target_x, target_y, target_l: Target coordinates
        grid_w, grid_h: Grid dimensions
        num_layers: Number of layers
        occupancy: 3D int32 array (-1=blocked, 0=free, >=1=occupied)

    Returns:
        3D float32 array of distances (inf for unreachable)
    """
    INF = float("inf")

    # Initialize distance map with infinity
    dist_map = np.full((grid_w, grid_h, num_layers), INF, dtype=np.float32)
    dist_map[target_x, target_y, target_l] = 0.0

    # Use arrays as a queue (much faster than Python deque in Numba)
    # Pre-allocate for worst case (full grid exploration)
    max_queue_size = grid_w * grid_h * num_layers
    queue_x = np.zeros(max_queue_size, dtype=np.int32)
    queue_y = np.zeros(max_queue_size, dtype=np.int32)
    queue_l = np.zeros(max_queue_size, dtype=np.int32)

    # Initialize queue with target
    queue_x[0] = target_x
    queue_y[0] = target_y
    queue_l[0] = target_l
    queue_head = 0
    queue_tail = 1

    # BFS loop
    while queue_head < queue_tail:
        cx = queue_x[queue_head]
        cy = queue_y[queue_head]
        cl = queue_l[queue_head]
        queue_head += 1

        current_dist = dist_map[cx, cy, cl]
        new_dist = current_dist + 1.0

        # Check 4-connected neighbors (planar moves)
        # Right
        nx, ny = cx + 1, cy
        if nx < grid_w:
            if occupancy[nx, ny, cl] != -1:
                if new_dist < dist_map[nx, ny, cl]:
                    dist_map[nx, ny, cl] = new_dist
                    queue_x[queue_tail] = nx
                    queue_y[queue_tail] = ny
                    queue_l[queue_tail] = cl
                    queue_tail += 1

        # Left
        nx, ny = cx - 1, cy
        if nx >= 0:
            if occupancy[nx, ny, cl] != -1:
                if new_dist < dist_map[nx, ny, cl]:
                    dist_map[nx, ny, cl] = new_dist
                    queue_x[queue_tail] = nx
                    queue_y[queue_tail] = ny
                    queue_l[queue_tail] = cl
                    queue_tail += 1

        # Up
        nx, ny = cx, cy + 1
        if ny < grid_h:
            if occupancy[nx, ny, cl] != -1:
                if new_dist < dist_map[nx, ny, cl]:
                    dist_map[nx, ny, cl] = new_dist
                    queue_x[queue_tail] = nx
                    queue_y[queue_tail] = ny
                    queue_l[queue_tail] = cl
                    queue_tail += 1

        # Down
        nx, ny = cx, cy - 1
        if ny >= 0:
            if occupancy[nx, ny, cl] != -1:
                if new_dist < dist_map[nx, ny, cl]:
                    dist_map[nx, ny, cl] = new_dist
                    queue_x[queue_tail] = nx
                    queue_y[queue_tail] = ny
                    queue_l[queue_tail] = cl
                    queue_tail += 1

        # Layer transitions (via moves) - cost 2 for layer change
        if num_layers > 1:
            via_dist = current_dist + 2.0  # Via costs more than planar move

            # Up layer
            if cl < num_layers - 1:
                nl = cl + 1
                if occupancy[cx, cy, nl] != -1:
                    if via_dist < dist_map[cx, cy, nl]:
                        dist_map[cx, cy, nl] = via_dist
                        queue_x[queue_tail] = cx
                        queue_y[queue_tail] = cy
                        queue_l[queue_tail] = nl
                        queue_tail += 1

            # Down layer
            if cl > 0:
                nl = cl - 1
                if occupancy[cx, cy, nl] != -1:
                    if via_dist < dist_map[cx, cy, nl]:
                        dist_map[cx, cy, nl] = via_dist
                        queue_x[queue_tail] = cx
                        queue_y[queue_tail] = cy
                        queue_l[queue_tail] = nl
                        queue_tail += 1

    return dist_map


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
                0, 0, 0, 2, 2, 0, w, h, l, occ, hist, cong, 1.0, 1.0, None, None, False, None, None, None, None, 0, 0.0, 1.0, -1, 0.0
            )
        except:
            pass

        # 2. Warmup with cost_map, soft_blocking=False
        try:
            find_path_astar_numba(
                0, 0, 0, 2, 2, 0, w, h, l, occ, hist, cong, 1.0, 1.0, cmap, None, False, None, None, None, None, 0, 0.0, 1.0, -1, 0.0
            )
        except:
            pass

        # 3. Warmup with soft_blocking=True and soft_c_space
        try:
            find_path_astar_numba(
                0, 0, 0, 2, 2, 0, w, h, l, occ, hist, cong, 1.0, 1.0, cmap, cmask, True, cspace, None, None, None, 0, 0.0, 1.0, -1, 0.0
            )
        except:
            pass

        # 4. Warmup with 3D cost_map
        try:
            cmap_3d = np.zeros((w, h, l), dtype=np.float32)
            find_path_astar_numba(
                0, 0, 0, 2, 2, 0, w, h, l, occ, hist, cong, 1.0, 1.0, cmap_3d, None, False, None, None, None, None, 0, 0.0, 1.0, -1, 0.0
            )
        except:
            pass

        # 5. Warmup for adaptive (distance map) version
        try:
            dist_map = np.zeros((w, h, l), dtype=np.float32)
            find_path_astar_numba_adaptive(
                0,
                0,
                0,
                2,
                2,
                0,
                w,
                h,
                l,
                occ,
                hist,
                cong,
                1.0,
                1.0,
                dist_map,
                None,
                None,
                False,
                None,
                None,
                None,
                0.0,
                None,
                0,
                0.0,
                1.0,
                None,
                -1,
                0.0,
            )
        except:
            pass

        # 6. Warmup for adaptive with cost_map and guide_map
        try:
            gmap = np.zeros((w, h, l), dtype=np.float32)
            find_path_astar_numba_adaptive(
                0,
                0,
                0,
                2,
                2,
                0,
                w,
                h,
                l,
                occ,
                hist,
                cong,
                1.0,
                1.0,
                dist_map,
                cmap,
                None,
                False,
                None,
                None,
                gmap,
                0.0,
                None,
                0,
                0.0,
                1.0,
                None,
                -1,
                0.0,
            )
        except:
            pass

        # 7. Warmup for BFS distance map
        try:
            compute_distance_map_numba(1, 1, 0, w, h, l, occ)
        except:
            pass

    # Execute warmup on import
    _warmup()
