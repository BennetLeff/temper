# distutils: language = c++
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True

"""Cython-accelerated A* pathfinding core.

This module contains the high-performance C implementation of the A* algorithm.

Performance:
- 50-100x faster than Python implementation
- Sub-second routing for complex paths (vs 10-15s in Python)
- Minimal memory overhead with pre-allocated C arrays
"""

from typing import Tuple, Optional
from temper_placer.routing.astar.types import MultiLayerPath
from libc.stdlib cimport malloc, free, realloc
from libc.math cimport sqrt, abs as c_abs, INFINITY
import numpy as np
import os
cimport numpy as cnp

# Initialize NumPy C API
cnp.import_array()

# Import struct definitions from .pxd
from temper_placer.routing.astar.astar_core cimport (
    HeapNode, MinHeap, GridView,
    heap_init, heap_push, heap_pop, heap_free,
    state_to_index, index_to_state,
    grid_get, grid_is_available, heuristic
)


# ============================================================================
# MinHeap Implementation
# ============================================================================

cdef void heap_init(MinHeap* heap, int capacity):
    """Initialize a min-heap with given capacity."""
    heap.nodes = <HeapNode*>malloc(capacity * sizeof(HeapNode))
    heap.size = 0
    heap.capacity = capacity


cdef void heap_free(MinHeap* heap):
    """Free heap memory."""
    if heap.nodes != NULL:
        free(heap.nodes)
        heap.nodes = NULL
    heap.size = 0
    heap.capacity = 0


cdef inline void _heap_sift_up(MinHeap* heap, int idx):
    """Sift element up to maintain heap property."""
    cdef int parent_idx
    cdef HeapNode temp
    
    while idx > 0:
        parent_idx = (idx - 1) // 2
        if heap.nodes[idx].priority < heap.nodes[parent_idx].priority:
            # Swap with parent
            temp = heap.nodes[idx]
            heap.nodes[idx] = heap.nodes[parent_idx]
            heap.nodes[parent_idx] = temp
            idx = parent_idx
        else:
            break


cdef inline void _heap_sift_down(MinHeap* heap, int idx):
    """Sift element down to maintain heap property."""
    cdef int left_child, right_child, smallest
    cdef HeapNode temp
    
    while True:
        smallest = idx
        left_child = 2 * idx + 1
        right_child = 2 * idx + 2
        
        # Find smallest among node and its children
        if left_child < heap.size and heap.nodes[left_child].priority < heap.nodes[smallest].priority:
            smallest = left_child
        if right_child < heap.size and heap.nodes[right_child].priority < heap.nodes[smallest].priority:
            smallest = right_child
        
        if smallest != idx:
            # Swap and continue
            temp = heap.nodes[idx]
            heap.nodes[idx] = heap.nodes[smallest]
            heap.nodes[smallest] = temp
            idx = smallest
        else:
            break


cdef void heap_push(MinHeap* heap, float priority, int state_index):
    """Push element onto heap, resizing if necessary."""
    # Resize if at capacity
    if heap.size >= heap.capacity:
        heap.capacity *= 2
        heap.nodes = <HeapNode*>realloc(heap.nodes, heap.capacity * sizeof(HeapNode))
    
    # Add new element at end
    heap.nodes[heap.size].priority = priority
    heap.nodes[heap.size].state_index = state_index
    
    # Sift up to maintain heap property
    _heap_sift_up(heap, heap.size)
    heap.size += 1


cdef int heap_pop(MinHeap* heap, float* priority):
    """Pop minimum element from heap. Returns state_index, or -1 if empty."""
    if heap.size == 0:
        return -1
    
    # Save root (minimum)
    cdef int result = heap.nodes[0].state_index
    priority[0] = heap.nodes[0].priority
    
    # Move last element to root
    heap.size -= 1
    if heap.size > 0:
        heap.nodes[0] = heap.nodes[heap.size]
        _heap_sift_down(heap, 0)
    
    return result


# ============================================================================
# State Indexing
# ============================================================================

cdef inline int state_to_index(int row, int col, int layer, int width, int height, int num_layers):
    """Convert 3D state (row, col, layer) to flat array index."""
    return (layer * height * width) + (row * width) + col


cdef inline void index_to_state(int index, int* row, int* col, int* layer, int width, int height, int num_layers):
    """Convert flat array index back to 3D state (row, col, layer)."""
    layer[0] = index // (height * width)
    cdef int remainder = index % (height * width)
    row[0] = remainder // width
    col[0] = remainder % width


# ============================================================================
# GridView (Direct Memory Access)
# ============================================================================

cdef inline int grid_get(GridView* grid, int row, int col, int layer):
    """Get grid value at (row, col, layer)."""
    return grid.data[layer * grid.height * grid.width + row * grid.width + col]


cdef inline bint grid_is_available(GridView* grid, int row, int col, int layer, int net_id):
    """Check if grid cell is available for routing."""
    # Bounds check
    if row < 0 or row >= grid.height or col < 0 or col >= grid.width:
        return False
    if layer < 0 or layer >= grid.num_layers:
        return False

    cdef int value = grid_get(grid, row, col, layer)
    return value == 0 or value == net_id


cdef inline bint grid_is_available_bitmap(GridView* grid, int row, int col, int layer, int net_id):
    """Check if grid cell is available using bitmap fast-path.

    If bitmap is present, checks the bitmap first (L1-cache hot).
    Falls back to full int32 grid check only when bitmap shows free.
    """
    cdef int word, bit, stride, value
    cdef unsigned long long val

    if row < 0 or row >= grid.height or col < 0 or col >= grid.width:
        return False
    if layer < 0 or layer >= grid.num_layers:
        return False

    if grid.bitmap != NULL:
        word = col >> 6
        bit = col & 63
        stride = grid.bitmap_row_stride
        val = grid.bitmap[layer * grid.height * stride + row * stride + word]
        if (val >> bit) & 1:
            return False

    value = grid_get(grid, row, col, layer)
    return value == 0 or value == net_id


# ============================================================================
# Heuristic Function
# ============================================================================

cdef inline float heuristic(int row1, int col1, int layer1, int row2, int col2, int layer2, float cell_size, float via_cost):
    """Octile distance heuristic with via penalty.
    
    NOTE: Returns distance in grid cells (not mm) to match edge costs.
    The cell_size parameter is kept for API compatibility but not used.
    """
    cdef float dx = <float>c_abs(col2 - col1)
    cdef float dy = <float>c_abs(row2 - row1)
    cdef float min_dist = dx if dx < dy else dy
    cdef float octile = (dx + dy) + (1.414213562 - 2.0) * min_dist
    cdef float layer_penalty = via_cost if layer1 != layer2 else 0.0
    return octile + layer_penalty


# ============================================================================
# Test Functions (for unit testing)
# ============================================================================

def test_heap_operations(test_name: str) -> bool:
    """Test MinHeap operations."""
    cdef MinHeap heap
    cdef float priority
    cdef int state_idx
    
    if test_name == 'push_pop_single':
        heap_init(&heap, 10)
        heap_push(&heap, 5.0, 42)
        state_idx = heap_pop(&heap, &priority)
        heap_free(&heap)
        return state_idx == 42 and priority == 5.0
    
    elif test_name == 'min_order':
        heap_init(&heap, 10)
        # Push in non-sorted order
        heap_push(&heap, 5.0, 5)
        heap_push(&heap, 1.0, 1)
        heap_push(&heap, 10.0, 10)
        heap_push(&heap, 3.0, 3)
        heap_push(&heap, 8.0, 8)
        
        # Should pop in priority order
        result = True
        result = result and (heap_pop(&heap, &priority) == 1 and priority == 1.0)
        result = result and (heap_pop(&heap, &priority) == 3 and priority == 3.0)
        result = result and (heap_pop(&heap, &priority) == 5 and priority == 5.0)
        result = result and (heap_pop(&heap, &priority) == 8 and priority == 8.0)
        result = result and (heap_pop(&heap, &priority) == 10 and priority == 10.0)
        
        heap_free(&heap)
        return result
    
    elif test_name == 'resize':
        heap_init(&heap, 2)  # Small capacity to force resize
        # Push more than initial capacity
        for i in range(10):
            heap_push(&heap, <float>i, i)
        
        # Should have resized successfully
        result = heap.size == 10 and heap.capacity >= 10
        
        # Verify all elements present
        for i in range(10):
            state_idx = heap_pop(&heap, &priority)
            result = result and (state_idx == i and priority == <float>i)
        
        heap_free(&heap)
        return result
    
    elif test_name == 'empty':
        heap_init(&heap, 10)
        state_idx = heap_pop(&heap, &priority)
        heap_free(&heap)
        return state_idx == -1
    
    return False


def test_state_indexing(test_name: str, width: int, height: int, num_layers: int) -> bool:
    """Test state indexing functions."""
    cdef int row, col, layer
    cdef int row_out, col_out, layer_out
    cdef int index
    
    if test_name == 'roundtrip':
        # Test roundtrip conversion for several states
        for layer in range(num_layers):
            for row in range(0, height, 10):
                for col in range(0, width, 10):
                    index = state_to_index(row, col, layer, width, height, num_layers)
                    index_to_state(index, &row_out, &col_out, &layer_out, width, height, num_layers)
                    
                    if row != row_out or col != col_out or layer != layer_out:
                        return False
        return True
    
    elif test_name == 'unique':
        # Check that all states map to unique indices
        seen_indices = set()  # Python set, not cdef
        for layer in range(num_layers):
            for row in range(height):
                for col in range(width):
                    index = state_to_index(row, col, layer, width, height, num_layers)
                    if index in seen_indices:
                        return False
                    seen_indices.add(index)
        return True
    
    elif test_name == 'layer_separation':
        # Same (row, col) on different layers should have different indices
        row, col = 10, 20
        indices = []
        for layer in range(num_layers):
            index = state_to_index(row, col, layer, width, height, num_layers)
            indices.append(index)
        
        # All indices should be unique
        return len(set(indices)) == num_layers
    
    return False


def test_grid_access(test_name: str) -> bool:
    """Test GridView operations."""
    cdef GridView grid
    cdef cnp.ndarray[cnp.int32_t, ndim=3] grid_data
    cdef int value
    
    # Create test grid (4 layers, 10x10)
    grid_data = np.zeros((4, 10, 10), dtype=np.int32)
    grid.data = <int*>cnp.PyArray_DATA(grid_data)
    grid.width = 10
    grid.height = 10
    grid.num_layers = 4
    
    if test_name == 'get_set':
        # Set a value via NumPy
        grid_data[1, 5, 7] = 42
        # Read via GridView
        value = grid_get(&grid, 5, 7, 1)
        return value == 42
    
    elif test_name == 'available_empty':
        # Empty cells should be available
        return grid_is_available(&grid, 3, 4, 2, 999)
    
    elif test_name == 'available_same_net':
        # Set cell to net_id=123
        grid_data[0, 2, 3] = 123
        # Should be available for same net
        return grid_is_available(&grid, 2, 3, 0, 123)
    
    elif test_name == 'available_blocked':
        # Set cell to net_id=100
        grid_data[1, 4, 5] = 100
        # Should NOT be available for different net
        return not grid_is_available(&grid, 4, 5, 1, 200)
    
    elif test_name == 'bounds_check':
        # Out of bounds should return False
        result = True
        result = result and not grid_is_available(&grid, -1, 5, 0, 1)
        result = result and not grid_is_available(&grid, 5, -1, 0, 1)
        result = result and not grid_is_available(&grid, 10, 5, 0, 1)
        result = result and not grid_is_available(&grid, 5, 10, 0, 1)
        result = result and not grid_is_available(&grid, 5, 5, -1, 1)
        result = result and not grid_is_available(&grid, 5, 5, 4, 1)
        return result
    
    return False


# ============================================================================
# Neighbor Generation
# ============================================================================

cdef inline int get_neighbors(
    int row, int col, int layer,
    int* neighbor_rows, int* neighbor_cols, int* neighbor_layers, float* neighbor_costs,
    int width, int height, int num_layers,
    GridView* grid, int net_id,
    int* allowed_layers, int num_allowed_layers,
    float via_cost
):
    """Generate valid neighbors for current state.
    
    Returns number of valid neighbors found.
    Neighbors are written to the output arrays.
    """
    cdef int num_neighbors = 0
    cdef int new_row, new_col, new_layer
    cdef float cost
    cdef int i
    
    # 8-connected movement on same layer
    # Order: up, right, down, left, up-left, up-right, down-left, down-right
    cdef int dr[8]
    cdef int dc[8]
    dr[:] = [-1, 0, 1, 0, -1, -1, 1, 1]
    dc[:] = [0, 1, 0, -1, -1, 1, -1, 1]
    cdef float costs[8]
    costs[:] = [1.0, 1.0, 1.0, 1.0, 1.414, 1.414, 1.414, 1.414]
    
    # Same-layer neighbors
    for i in range(8):
        new_row = row + dr[i]
        new_col = col + dc[i]
        
        if grid_is_available_bitmap(grid, new_row, new_col, layer, net_id):
            neighbor_rows[num_neighbors] = new_row
            neighbor_cols[num_neighbors] = new_col
            neighbor_layers[num_neighbors] = layer
            neighbor_costs[num_neighbors] = costs[i]
            num_neighbors += 1
    
    # Layer transitions (vias)
    for i in range(num_allowed_layers):
        new_layer = allowed_layers[i]
        if new_layer == layer:
            continue
        
        # Check if target layer is available at current position
        if grid_is_available_bitmap(grid, row, col, new_layer, net_id):
            neighbor_rows[num_neighbors] = row
            neighbor_cols[num_neighbors] = col
            neighbor_layers[num_neighbors] = new_layer
            neighbor_costs[num_neighbors] = via_cost
            num_neighbors += 1
    
    return num_neighbors


# ============================================================================
# Path Reconstruction
# ============================================================================

cdef tuple reconstruct_path(
    int* came_from, int goal_index,
    int width, int height, int num_layers,
    float start_x, float start_y, float end_x, float end_y,
    float cell_size, float via_cost
):
    """Reconstruct path from came_from array.
    
    Returns tuple: (segments, via_positions, total_cost)
    where segments is list of RouteSegment
    """
    cdef int current_idx = goal_index
    cdef int parent_idx
    cdef int row, col, layer
    cdef int parent_row, parent_col, parent_layer
    cdef list path_indices = []
    cdef list segments = []
    cdef list via_positions = []
    cdef float total_cost = 0.0
    cdef int i
    cdef float via_x, via_y, p2_x, p2_y
    
    # Import RouteSegment
    from temper_placer.routing.astar.types import RouteSegment
    
    # Trace back from goal to start
    path_indices.append(goal_index)
    current_idx = goal_index
    while came_from[current_idx] != -1:
        current_idx = came_from[current_idx]
        path_indices.append(current_idx)
    
    # Reverse to get start->goal order
    path_indices.reverse()
    
    # Convert indices to states and build segments
    for i in range(len(path_indices) - 1):
        current_idx = path_indices[i]
        parent_idx = path_indices[i + 1]
        
        index_to_state(current_idx, &row, &col, &layer, width, height, num_layers)
        index_to_state(parent_idx, &parent_row, &parent_col, &parent_layer, width, height, num_layers)
        
        if layer != parent_layer:
            # Layer transition - add via
            via_x = col * cell_size + cell_size / 2.0
            via_y = row * cell_size + cell_size / 2.0
            via_positions.append((via_x, via_y, layer, parent_layer))
            total_cost += via_cost
            
            # Add landing segment on new layer if position changed
            p2_x = parent_col * cell_size + cell_size / 2.0
            p2_y = parent_row * cell_size + cell_size / 2.0
            if via_x != p2_x or via_y != p2_y:
                segments.append(RouteSegment(
                    start=(via_x, via_y),
                    end=(p2_x, p2_y),
                    layer=parent_layer
                ))
        else:
            # Same layer - add trace segment
            if i == 0:
                p1_x = start_x
                p1_y = start_y
            else:
                p1_x = col * cell_size + cell_size / 2.0
                p1_y = row * cell_size + cell_size / 2.0
            
            if i == len(path_indices) - 2:
                p2_x = end_x
                p2_y = end_y
            else:
                p2_x = parent_col * cell_size + cell_size / 2.0
                p2_y = parent_row * cell_size + cell_size / 2.0
            
            segments.append(RouteSegment(start=(p1_x, p1_y), end=(p2_x, p2_y), layer=layer))
            
            # Calculate cost
            dx = p2_x - p1_x
            dy = p2_y - p1_y
            total_cost += sqrt(dx*dx + dy*dy)
    
    return (segments, via_positions, total_cost)


# ============================================================================
# Main A* Function
# ============================================================================

def find_path_cython(
    grid,
    start_pos: Tuple[float, float],
    end_pos: Tuple[float, float],
    net_id: int,
    config: dict,
    start_layer: int = 0,
    end_layer: int = -1,
    drc_oracle = None,
    net_name: str = None,
    via_diameter: float = 0.6,
) -> Optional[MultiLayerPath]:
    """Cython-accelerated A* pathfinding.
    
    Args:
        grid: ClearanceGrid for collision checking
        start_pos: (x, y) start position in mm
        end_pos: (x, y) end position in mm
        net_id: Net ID for clearance checking
        config: Configuration dict with keys:
            - via_cost: Cost penalty for vias (default: 5.0)
            - max_iterations: Maximum search iterations (default: 100000)
        start_layer: Starting layer index
        end_layer: Ending layer index (-1 for any layer)
        drc_oracle: Optional DRCOracle for via placement validation
        net_name: Net name for DRC oracle checks
        via_diameter: Via diameter in mm for DRC checks (default: 0.6)
        
    Returns:
        MultiLayerPath or None if no path found
    """
    # Extract config parameters
    cdef float via_cost = config.get('via_cost', 5.0)
    cdef int max_iterations = config.get('max_iterations', 100000)
    
    # Get grid parameters
    cdef int width = grid.cols
    cdef int height = grid.rows
    cdef int num_layers = grid.layer_count
    cdef float cell_size = grid.cell_size_mm
    
    # Convert start/end positions to grid cells
    start_cell = grid._mm_to_cell(start_pos[0], start_pos[1])
    end_cell = grid._mm_to_cell(end_pos[0], end_pos[1])
    
    cdef int start_row = start_cell[0]
    cdef int start_col = start_cell[1]
    cdef int end_row = end_cell[0]
    cdef int end_col = end_cell[1]
    
    # Validate bounds
    if not (0 <= start_row < height and 0 <= start_col < width):
        return None
    if not (0 <= end_row < height and 0 <= end_col < width):
        return None
    
    # Setup allowed layers
    cdef int allowed_layers[4]  # Max 4 layers
    cdef int num_allowed_layers = min(4, num_layers)
    cdef int i
    for i in range(num_allowed_layers):
        allowed_layers[i] = i
    
    # Validate start_layer
    if start_layer < 0 or start_layer >= num_layers:
        start_layer = 0
    
    # Setup GridView for fast access
    cdef GridView grid_view
    cdef cnp.ndarray[cnp.int32_t, ndim=3] grid_data = grid.occupancy_grid
    grid_view.data = <int*>cnp.PyArray_DATA(grid_data)
    grid_view.width = width
    grid_view.height = height
    grid_view.num_layers = num_layers

    cdef cnp.ndarray[cnp.uint64_t, ndim=3] bitmap_data
    grid_view.bitmap = NULL
    grid_view.bitmap_row_stride = 0
    if not os.environ.get("TEMPER_DISABLE_BITMAP"):
        if hasattr(grid, 'occupancy_bitmap') and getattr(grid, 'occupancy_bitmap') is not None:
            bitmap_data = np.ascontiguousarray(grid.occupancy_bitmap, dtype=np.uint64)
            grid_view.bitmap = <unsigned long long*>cnp.PyArray_DATA(bitmap_data)
            grid_view.bitmap_row_stride = grid.bitmap_row_stride
    
    # State space size
    cdef int state_space_size = width * height * num_layers
    
    # Allocate arrays
    cdef float* g_score = <float*>malloc(state_space_size * sizeof(float))
    cdef int* came_from = <int*>malloc(state_space_size * sizeof(int))
    cdef MinHeap open_set

    cdef int closed_set_words = (state_space_size + 63) // 64
    cdef unsigned long long* closed_set = <unsigned long long*>malloc(closed_set_words * sizeof(unsigned long long))

    # Initialize arrays
    for i in range(state_space_size):
        g_score[i] = INFINITY
        came_from[i] = -1
    for i in range(closed_set_words):
        closed_set[i] = 0
    
    # Initialize heap
    heap_init(&open_set, 1000)
    
    # Start state
    cdef int start_idx = state_to_index(start_row, start_col, start_layer, width, height, num_layers)
    g_score[start_idx] = 0.0
    cdef float h_start = heuristic(start_row, start_col, start_layer, end_row, end_col, end_layer, cell_size, via_cost)
    heap_push(&open_set, h_start, start_idx)
    
    # Neighbor arrays (max 8 same-layer + 3 other layers = 11)
    cdef int neighbor_rows[11]
    cdef int neighbor_cols[11]
    cdef int neighbor_layers[11]
    cdef float neighbor_costs[11]
    cdef int num_neighbors
    
    cdef int iterations = 0
    cdef float priority
    cdef int current_idx, neighbor_idx
    cdef int current_row, current_col, current_layer
    cdef float tentative_g, f_score
    cdef int j
    cdef bint goal_found = False
    cdef int goal_idx = -1
    
    # A* main loop
    try:
        while open_set.size > 0 and iterations < max_iterations:
            iterations += 1
            
            # Pop minimum from heap
            current_idx = heap_pop(&open_set, &priority)
            if current_idx == -1:
                break

            closed_set[current_idx >> 6] |= (1ULL << (current_idx & 63))

            # Convert to state
            index_to_state(current_idx, &current_row, &current_col, &current_layer, width, height, num_layers)
            
            # Check if goal reached
            if current_row == end_row and current_col == end_col:
                if end_layer == -1 or current_layer == end_layer:
                    goal_found = True
                    goal_idx = current_idx
                    break
            
            # Generate neighbors
            num_neighbors = get_neighbors(
                current_row, current_col, current_layer,
                neighbor_rows, neighbor_cols, neighbor_layers, neighbor_costs,
                width, height, num_layers,
                &grid_view, net_id,
                allowed_layers, num_allowed_layers,
                via_cost
            )
            
            # Process neighbors
            for j in range(num_neighbors):
                # Check if this is a layer transition (via placement)
                if neighbor_layers[j] != current_layer:
                    # DRC oracle check for via placement
                    if drc_oracle is not None and net_name is not None:
                        via_x = neighbor_cols[j] * cell_size + cell_size / 2.0
                        via_y = neighbor_rows[j] * cell_size + cell_size / 2.0
                        valid, _ = drc_oracle.can_place_via(
                            position=(via_x, via_y),
                            diameter=via_diameter,
                            net=net_name,
                        )
                        if not valid:
                            continue  # Skip this via - DRC violation
                
                neighbor_idx = state_to_index(
                    neighbor_rows[j], neighbor_cols[j], neighbor_layers[j],
                    width, height, num_layers
                )

                if (closed_set[neighbor_idx >> 6] >> (neighbor_idx & 63)) & 1:
                    continue

                tentative_g = g_score[current_idx] + neighbor_costs[j]
                
                if tentative_g < g_score[neighbor_idx]:
                    # Better path found
                    came_from[neighbor_idx] = current_idx
                    g_score[neighbor_idx] = tentative_g
                    
                    # Calculate f_score with heuristic
                    f_score = tentative_g + heuristic(
                        neighbor_rows[j], neighbor_cols[j], neighbor_layers[j],
                        end_row, end_col, end_layer,
                        cell_size, via_cost
                    )
                    
                    heap_push(&open_set, f_score, neighbor_idx)
        
        # Reconstruct path if goal found
        if goal_found:
            path_data = reconstruct_path(
                came_from, goal_idx,
                width, height, num_layers,
                start_pos[0], start_pos[1], end_pos[0], end_pos[1],
                cell_size, via_cost
            )
            
            from temper_placer.routing.astar.types import MultiLayerPath
            result = MultiLayerPath(
                segments=path_data[0],
                via_positions=path_data[1],
                total_cost=path_data[2]
            )
        else:
            result = None
            
            # Log timeout warning
            if iterations >= max_iterations:
                print(f"WARNING: Cython A* exceeded {max_iterations} iterations for net {net_id}")
        
        return result
        
    finally:
        # Always cleanup memory
        free(g_score)
        free(came_from)
        free(closed_set)
        heap_free(&open_set)
