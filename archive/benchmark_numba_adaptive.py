#!/usr/bin/env python3
"""Benchmark comparing Python vs Numba adaptive A* pathfinding."""

import sys
import time
import random
import numpy as np

sys.path.insert(0, "packages/temper-placer/src")

from temper_placer.routing.maze_router import MazeRouter, GridCell
from temper_placer.routing.fast_router import HAS_NUMBA, find_path_astar_numba_adaptive


def create_test_router(grid_w=100, grid_h=100, num_layers=2, obstacle_density=0.2):
    """Create a router with some obstacles for testing."""
    router = MazeRouter(
        grid_size=(grid_w, grid_h),
        cell_size_mm=1.0,
        num_layers=num_layers,
        via_cost=1.0,
        soft_blocking=True,
    )

    occ = router.occupancy

    for x in range(grid_w):
        for y in range(grid_h):
            for l in range(num_layers):
                if random.random() < obstacle_density:
                    occ[x, y, l] = -1

    return router


def benchmark_python_adaptive(router, start, end, layer, runs=100):
    """Benchmark Python adaptive pathfinding."""
    times = []
    for _ in range(runs):
        router._prepare_cost_arrays()
        try:
            dist_map = router._compute_distance_map(GridCell(end[0], end[1], layer), _layer=layer)
            start_time = time.perf_counter()
            path = router._find_path_python_adaptive(
                start,
                end,
                layer,
                allow_layer_change=True,
                allowed_layers=None,
                cost_map=None,
                p_scale=1.0,
                dist_map=dist_map,
            )
            elapsed = time.perf_counter() - start_time
            times.append(elapsed)
        finally:
            router._clear_cost_arrays()
    return times


def benchmark_numba_adaptive(router, start, end, layer, runs=100):
    """Benchmark Numba adaptive pathfinding."""
    times = []
    for _ in range(runs):
        router._prepare_cost_arrays()
        try:
            dist_map = router._compute_distance_map(GridCell(end[0], end[1], layer), _layer=layer)
            start_time = time.perf_counter()
            result = find_path_astar_numba_adaptive(
                start[0],
                start[1],
                layer,
                end[0],
                end[1],
                layer,
                router.grid_size[0],
                router.grid_size[1],
                router.num_layers,
                router._occupancy_np,
                router._history_np,
                router._congestion_np,
                router.via_cost,
                1.0,
                dist_map,
                cost_map=None,
                clearance_mask=None,
                soft_blocking=router.soft_blocking,
                soft_c_space=router._soft_c_space_np
                if router._soft_c_space_np is not None
                else None,
                tap_mask=None,
            )
            elapsed = time.perf_counter() - start_time
            times.append(elapsed)
        finally:
            router._clear_cost_arrays()
    return times


def main():
    print("=" * 60)
    print("Adaptive A* Pathfinding Benchmark")
    print("=" * 60)
    print(f"Numba available: {HAS_NUMBA}")
    print()

    grid_sizes = [
        (50, 50, 2, "Small (50x50, 2 layers)"),
        (100, 100, 2, "Medium (100x100, 2 layers)"),
        (100, 100, 4, "Multi-layer (100x100, 4 layers)"),
        (200, 200, 2, "Large (200x200, 2 layers)"),
    ]

    for grid_w, grid_h, num_layers, desc in grid_sizes:
        print(f"\n{desc}")
        print("-" * 40)

        router = create_test_router(grid_w, grid_h, num_layers, obstacle_density=0.15)

        start = (5, 5)
        end = (grid_w - 6, grid_h - 6)
        layer = 0
        runs = 50

        print(f"  Grid: {grid_w}x{grid_h}x{num_layers}")
        print(f"  Start: {start}, End: {end}")
        print(f"  Runs per test: {runs}")

        python_times = benchmark_python_adaptive(router, start, end, layer, runs)
        python_avg = np.mean(python_times) * 1000
        python_std = np.std(python_times) * 1000
        print(f"\n  Python adaptive:")
        print(f"    Avg: {python_avg:.3f} ms (±{python_std:.3f} ms)")

        if HAS_NUMBA:
            numba_times = benchmark_numba_adaptive(router, start, end, layer, runs)
            numba_avg = np.mean(numba_times) * 1000
            numba_std = np.std(numba_times) * 1000
            speedup = python_avg / numba_avg
            print(f"\n  Numba adaptive:")
            print(f"    Avg: {numba_avg:.3f} ms (±{numba_std:.3f} ms)")
            print(f"\n  Speedup: {speedup:.1f}x faster")
        else:
            print("\n  Numba not available - skipping Numba benchmark")

    print("\n" + "=" * 60)
    print("Benchmark complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
