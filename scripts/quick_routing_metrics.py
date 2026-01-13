#!/usr/bin/env python3.11
"""
Quick routing metrics benchmark.

Runs the routing pipeline and displays detailed per-segment metrics
to help identify bottlenecks and measure improvements.

Usage:
    python scripts/quick_routing_metrics.py
"""

import sys
import time
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.deterministic.stages.astar import DeterministicAStar
from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar


def measure_routing_search():
    """Run A* searches and collect metrics."""

    print("=" * 60)
    print("ROUTING SEARCH METRICS TEST")
    print("=" * 60)

    # Create a moderately complex grid
    grid = ClearanceGrid(width_mm=100, height_mm=150, cell_size_mm=0.5, layer_count=4)

    # Add some obstacles to make it interesting
    # Simulate component pads
    obstacles = [
        (20, 30),
        (25, 30),
        (30, 30),  # Row 1
        (20, 50),
        (25, 50),
        (30, 50),  # Row 2
        (50, 70),
        (55, 70),
        (60, 70),  # Row 3
        (70, 100),
        (75, 100),
        (80, 100),  # Row 4
    ]

    for x, y in obstacles:
        for layer in range(4):
            grid.block_circle(center=(x, y), radius_mm=1.5, clearance_mm=0.3, layer=layer)

    # Test cases: (name, start, end, expected_difficulty)
    test_cases = [
        ("Short direct", (10, 10), (20, 10), "easy"),
        ("Medium direct", (10, 10), (50, 50), "medium"),
        ("Long diagonal", (10, 10), (90, 140), "hard"),
        ("Around obstacles", (15, 30), (35, 30), "medium"),
        ("Cross-board", (5, 5), (95, 145), "hard"),
    ]

    results = []

    print("\n--- Single-Layer A* ---")
    print(f"{'Test':<20} {'Success':<8} {'Iters':<8} {'Limit':<8} {'Timeout':<8} {'Time':<8}")
    print("-" * 68)

    for name, start, end, difficulty in test_cases:
        pathfinder = DeterministicAStar(grid=grid, net_name=name)

        t0 = time.time()
        path = pathfinder.find_path(start=start, end=end, layer=0)
        elapsed = time.time() - t0

        success = "✓" if path else "✗"
        timeout = "YES" if pathfinder.last_timeout else "no"

        print(
            f"{name:<20} {success:<8} {pathfinder.last_iterations:<8} {pathfinder.last_iteration_limit:<8} {timeout:<8} {elapsed * 1000:.1f}ms"
        )

        results.append(
            {
                "name": name,
                "type": "single",
                "success": path is not None,
                "iterations": pathfinder.last_iterations,
                "limit": pathfinder.last_iteration_limit,
                "timeout": pathfinder.last_timeout,
                "elapsed_ms": elapsed * 1000,
            }
        )

    print("\n--- Multi-Layer A* (4 layers) ---")
    print(
        f"{'Test':<20} {'Success':<8} {'Iters':<8} {'Limit':<8} {'Timeout':<8} {'Vias':<6} {'Time':<8}"
    )
    print("-" * 74)

    for name, start, end, difficulty in test_cases:
        ml_pathfinder = MultiLayerAStar(grid=grid, net_name=name, allowed_layers=[0, 1, 2, 3])

        t0 = time.time()
        path = ml_pathfinder.find_path(start=start, end=end, start_layer=0)
        elapsed = time.time() - t0

        success = "✓" if path else "✗"
        timeout = "YES" if ml_pathfinder.last_timeout else "no"
        vias = len(path.via_positions) if path else 0

        print(
            f"{name:<20} {success:<8} {ml_pathfinder.last_iterations:<8} {ml_pathfinder.last_iteration_limit:<8} {timeout:<8} {vias:<6} {elapsed * 1000:.1f}ms"
        )

        results.append(
            {
                "name": name,
                "type": "multi",
                "success": path is not None,
                "iterations": ml_pathfinder.last_iterations,
                "limit": ml_pathfinder.last_iteration_limit,
                "timeout": ml_pathfinder.last_timeout,
                "vias": vias,
                "elapsed_ms": elapsed * 1000,
            }
        )

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    single_results = [r for r in results if r["type"] == "single"]
    multi_results = [r for r in results if r["type"] == "multi"]

    single_success = sum(1 for r in single_results if r["success"])
    multi_success = sum(1 for r in multi_results if r["success"])

    single_timeouts = sum(1 for r in single_results if r["timeout"])
    multi_timeouts = sum(1 for r in multi_results if r["timeout"])

    single_iters = sum(r["iterations"] for r in single_results)
    multi_iters = sum(r["iterations"] for r in multi_results)

    print(f"\nSingle-layer A*:")
    print(
        f"  Success rate:     {single_success}/{len(single_results)} ({single_success / len(single_results):.0%})"
    )
    print(
        f"  Timeout rate:     {single_timeouts}/{len(single_results)} ({single_timeouts / len(single_results):.0%})"
    )
    print(f"  Total iterations: {single_iters:,}")
    print(f"  Avg iterations:   {single_iters / len(single_results):.0f}")

    print(f"\nMulti-layer A*:")
    print(
        f"  Success rate:     {multi_success}/{len(multi_results)} ({multi_success / len(multi_results):.0%})"
    )
    print(
        f"  Timeout rate:     {multi_timeouts}/{len(multi_results)} ({multi_timeouts / len(multi_results):.0%})"
    )
    print(f"  Total iterations: {multi_iters:,}")
    print(f"  Avg iterations:   {multi_iters / len(multi_results):.0f}")
    print(f"  Total vias:       {sum(r.get('vias', 0) for r in multi_results)}")

    return results


if __name__ == "__main__":
    measure_routing_search()
