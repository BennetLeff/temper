#!/usr/bin/env python3
"""
TEST-04: Trace Neighbor Generation Patterns

Logs the first 20 cells visited by A* and their neighbor counts to verify
that _get_neighbors() correctly generates vias and horizontal moves.

This test adds obstacles to see how neighbor generation changes.

Expected Results:
- Each cell should have 4 neighbors (same layer) + 1 via (cross-layer) ≈ 5 total
- Obstacles should reduce neighbor count appropriately
- Via transitions should be present when allow_layer_change=True

Issue: temper-iymq
Epic: temper-koke (Debug A* Pathfinding Inefficiency)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.routing.maze_router import MazeRouter, GridCell


def trace_neighbors_no_obstacles():
    """Trace neighbor generation with no obstacles."""
    print("\n" + "="*60)
    print("TEST 1: Neighbor Generation (No Obstacles)")
    print("="*60)
    
    router = MazeRouter(
        grid_size=(50, 50),
        cell_size_mm=1.0,
        num_layers=2,
        min_clearance=0.0
    )
    
    # Test a cell in the middle of the grid
    test_cell = GridCell(25, 25, 0)
    
    # Same-layer neighbors
    neighbors_no_via = router._get_neighbors(test_cell, allow_layer_change=False)
    print(f"\nCell {test_cell} (same-layer only):")
    print(f"  Neighbors: {len(neighbors_no_via)}")
    print(f"  Expected: 4 (up, down, left, right)")
    
    # With vias
    neighbors_with_via = router._get_neighbors(test_cell, allow_layer_change=True)
    print(f"\nCell {test_cell} (with via option):")
    print(f"  Neighbors: {len(neighbors_with_via)}")
    print(f"  Expected: 5 (4 horizontal + 1 via to L1)")
    
    # Check via is actually generated
    via_neighbors = [n for n in neighbors_with_via if n.layer != test_cell.layer]
    print(f"  Via neighbors: {len(via_neighbors)}")
    if via_neighbors:
        print(f"    {via_neighbors[0]}")
    
    return len(neighbors_with_via) == 5 and len(via_neighbors) == 1


def trace_neighbors_with_obstacles():
    """Trace neighbor generation with obstacles blocking some directions."""
    print("\n" + "="*60)
    print("TEST 2: Neighbor Generation (With Obstacles)")
    print("="*60)
    
    router = MazeRouter(
        grid_size=(50, 50),
        cell_size_mm=1.0,
        num_layers=2,
        min_clearance=0.0
    )
    
    # Block cells around test position
    test_x, test_y = 25, 25
    
    # Block right neighbor
    router.occupancy[test_x + 1, test_y, 0] = -1
    
    # Block cell on layer 1 (should prevent via)
    router.occupancy[test_x, test_y, 1] = -1
    
    test_cell = GridCell(test_x, test_y, 0)
    neighbors = router._get_neighbors(test_cell, allow_layer_change=True)
    
    print(f"\nCell {test_cell} with obstacles:")
    print(f"  RIGHT blocked on L0: occupancy[{test_x+1}, {test_y}, 0] = -1")
    print(f"  Via blocked on L1: occupancy[{test_x}, {test_y}, 1] = -1")
    print(f"  Neighbors found: {len(neighbors)}")
    print(f"  Expected: 3 (up, down, left - blocked right and via)")
    
    # Check that blocked directions are not in neighbors
    blocked_right = any(n.x == test_x + 1 and n.y == test_y and n.layer == 0 for n in neighbors)
    blocked_via = any(n.x == test_x and n.y == test_y and n.layer == 1 for n in neighbors)
    
    if blocked_right:
        print("  ❌ ERROR: Blocked right cell is in neighbors!")
        return False
    if blocked_via:
        print("  ❌ ERROR: Blocked via cell is in neighbors!")
        return False
    
    print("  ✅ Obstacles correctly filter neighbors")
    return len(neighbors) == 3


def trace_first_n_cells():
    """Trace the first 20 cells A* visits during routing."""
    print("\n" + "="*60)
    print("TEST 3: First 20 Cells Visited by A*")
    print("="*60)
    
    router = MazeRouter(
        grid_size=(100, 100),
        cell_size_mm=1.0,
        num_layers=2,
        min_clearance=0.0
    )
    
    # Monkey-patch find_path_rrr to trace visits
    visited_cells = []
    original_get_neighbors = router._get_neighbors
    
    def tracing_get_neighbors(cell, *args, **kwargs):
        neighbors = original_get_neighbors(cell, *args, **kwargs)
        if len(visited_cells) < 20:
            visited_cells.append((cell, len(neighbors)))
        return neighbors
    
    router._get_neighbors = tracing_get_neighbors
    
    start = (10, 50)
    end = (90, 50)
    
    path = router.find_path_rrr(
        start=start,
        end=end,
        layer=0,
        allow_layer_change=True,
        end_layer=1
    )
    
    print(f"\nRouting from {start}@L0 to {end}@L1")
    print(f"Path found: {'Yes' if path else 'No'}")
    print(f"\nFirst 20 cells explored:")
    print(f"{'Cell':<30} {'Neighbors':>10}")
    print("-" * 42)
    
    for cell, neighbor_count in visited_cells:
        print(f"{str(cell):<30} {neighbor_count:>10}")
    
    # Check if exploration makes sense
    # Early cells should have ~5 neighbors (4 + via)
    avg_neighbors = sum(n for _, n in visited_cells) / len(visited_cells) if visited_cells else 0
    print(f"\nAverage neighbors: {avg_neighbors:.1f}")
    print(f"Expected: ~4-5 for open grid")
    
    return avg_neighbors >= 3.0  # At least 3 neighbors on average


if __name__ == "__main__":
    print("\n" + "="*60)
    print("A* NEIGHBOR GENERATION TESTS")
    print("="*60)
    
    results = []
    results.append(("No obstacles", trace_neighbors_no_obstacles()))
    results.append(("With obstacles", trace_neighbors_with_obstacles()))
    results.append(("First cells traced", trace_first_n_cells()))
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n🎉 Neighbor generation is correct!")
        sys.exit(0)
    else:
        print("\n💥 Neighbor generation has bugs!")
        sys.exit(1)
