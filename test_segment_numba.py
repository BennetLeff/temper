#!/usr/bin/env python3.11
"""Quick test/benchmark for _block_segment_numba optimization."""

import sys
import time
import numpy as np

sys.path.insert(0, "packages/temper-placer/src")

from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid


def test_block_segment():
    """Test that block_segment works correctly with Numba optimization."""
    print("Testing _block_segment Numba optimization...")

    # Create a small grid
    grid = ClearanceGrid(width_mm=100.0, height_mm=100.0, cell_size_mm=0.1, layer_count=2)

    print(f"Grid: {grid.rows}x{grid.cols} cells, {grid.layer_count} layers")

    # Test 1: Block a diagonal segment
    print("\n=== Test 1: Block diagonal segment ===")
    grid.block_trace(
        path=[(10.0, 10.0), (50.0, 50.0)],
        width_mm=0.5,
        clearance_mm=0.3,
        layer=0,
        net_name="test_net",
    )

    # Count blocked cells
    blocked = np.sum(grid._trace_net_ids[0] != 0)
    print(f"Blocked cells: {blocked}")
    assert blocked > 0, "Should have blocked some cells"

    # Test 2: Benchmark performance
    print("\n=== Test 2: Benchmark 50 block_segment calls ===")
    grid2 = ClearanceGrid(width_mm=100.0, height_mm=100.0, cell_size_mm=0.1, layer_count=2)

    # Create a long path with many segments
    path = [(i * 2.0, i * 2.0 + 10) for i in range(50)]

    start = time.time()
    grid2.block_trace(path=path, width_mm=0.5, clearance_mm=0.3, layer=0, net_name="bench_net")
    elapsed = time.time() - start

    # Path has 50 points = 49 segments + 50 circles
    # We're primarily measuring segment performance here
    print(f"Time for 49 segments + 50 circles: {elapsed:.4f}s")
    print(f"Average time per segment: {elapsed / 49 * 1000:.2f}ms")

    blocked2 = np.sum(grid2._trace_net_ids[0] != 0)
    print(f"Total blocked cells: {blocked2}")

    # Test 3: Verify conflict detection
    print("\n=== Test 3: Verify conflict detection ===")
    grid3 = ClearanceGrid(width_mm=100.0, height_mm=100.0, cell_size_mm=0.1, layer_count=2)

    # Block two crossing segments
    grid3.block_trace(
        path=[(10.0, 50.0), (90.0, 50.0)], width_mm=0.5, clearance_mm=0.3, layer=0, net_name="net1"
    )

    grid3.block_trace(
        path=[(50.0, 10.0), (50.0, 90.0)], width_mm=0.5, clearance_mm=0.3, layer=0, net_name="net2"
    )

    # Check for conflicts (-1 values)
    conflicts = np.sum(grid3._trace_net_ids[0] == -1)
    print(f"Conflict cells detected: {conflicts}")
    assert conflicts > 0, "Should detect conflicts where segments cross"

    print("\n✅ All tests passed!")
    return True


if __name__ == "__main__":
    success = test_block_segment()
    sys.exit(0 if success else 1)
