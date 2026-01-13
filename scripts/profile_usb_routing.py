#!/usr/bin/env python3
"""
Profile USB Differential Pair Routing Performance

Measures where time is spent during USB diff pair routing to identify bottlenecks.
This script isolates the diff pair routing path and provides detailed timing breakdowns.

Usage:
    python3 scripts/profile_usb_routing.py [--pcb PATH] [--synthetic]

Options:
    --pcb PATH      Path to KiCad PCB file (default: pcb/temper.kicad_pcb)
    --synthetic     Run synthetic benchmark instead of real PCB
    --iterations N  Number of iterations for synthetic benchmark (default: 3)
"""

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set, Tuple, Optional
import numpy as np

# Add package to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "temper-placer" / "src"))

from temper_placer.routing.diff_pair_router import DiffPairRouter, DiffPairPath
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid


@dataclass
class ProfileResult:
    """Detailed profiling results."""

    # Grid info
    grid_cols: int = 0
    grid_rows: int = 0
    grid_layers: int = 0
    grid_cell_size_mm: float = 0.0
    total_cells: int = 0

    # Obstacle info
    obstacle_count: int = 0
    obstacle_density_pct: float = 0.0

    # Timing (all in seconds)
    obstacle_build_time_s: float = 0.0
    router_init_time_s: float = 0.0
    routing_time_s: float = 0.0
    total_time_s: float = 0.0

    # Router stats
    states_explored: int = 0
    states_pruned: int = 0
    beam_pruned: int = 0
    spacing_pruned: int = 0

    # Route result
    success: bool = False
    failure_reason: Optional[str] = None
    coupling_ratio: float = 0.0
    max_skew_mm: float = 0.0
    path_length_cells: int = 0

    # Derived metrics
    @property
    def states_per_second(self) -> float:
        if self.routing_time_s > 0:
            return self.states_explored / self.routing_time_s
        return 0

    @property
    def pruning_efficiency(self) -> float:
        total = self.states_explored + self.states_pruned
        if total > 0:
            return self.states_pruned / total
        return 0

    @property
    def obstacle_build_pct(self) -> float:
        if self.total_time_s > 0:
            return (self.obstacle_build_time_s / self.total_time_s) * 100
        return 0


def build_obstacles_naive(grid: ClearanceGrid) -> Tuple[Set[Tuple[int, int, int]], float]:
    """
    Build obstacles set using the naive O(n³) approach from sequential_routing.py.
    Returns (obstacles, time_taken).
    """
    t0 = time.perf_counter()
    obstacles: Set[Tuple[int, int, int]] = set()

    for layer_idx in range(grid.layer_count):
        for x in range(grid.cols):
            for y in range(grid.rows):
                if not grid.is_available(x * grid.cell_size_mm, y * grid.cell_size_mm, layer_idx):
                    obstacles.add((x, y, layer_idx))

    elapsed = time.perf_counter() - t0
    return obstacles, elapsed


def build_obstacles_vectorized(grid: ClearanceGrid) -> Tuple[Set[Tuple[int, int, int]], float]:
    """
    Build obstacles set using vectorized NumPy approach.
    Returns (obstacles, time_taken).
    """
    t0 = time.perf_counter()
    obstacles: Set[Tuple[int, int, int]] = set()

    for layer_idx in range(grid.layer_count):
        # Get blocked cells from internal arrays
        trace_blocked = grid._trace_net_ids[layer_idx] != 0
        pad_blocked = grid._pad_net_ids[layer_idx] != 0
        blocked = trace_blocked | pad_blocked

        # Get indices of blocked cells
        blocked_indices = np.argwhere(blocked)
        for row, col in blocked_indices:
            obstacles.add((col, row, layer_idx))  # Note: (x, y) = (col, row)

    elapsed = time.perf_counter() - t0
    return obstacles, elapsed


def profile_synthetic_routing(
    grid_size: Tuple[int, int, int] = (400, 600, 4),
    cell_size_mm: float = 0.25,
    obstacle_density: float = 0.1,
    route_distance_cells: int = 200,
) -> ProfileResult:
    """
    Profile routing with synthetic grid and obstacles.

    Args:
        grid_size: (cols, rows, layers)
        cell_size_mm: Grid resolution
        obstacle_density: Fraction of cells blocked (0.0 to 1.0)
        route_distance_cells: Approximate distance to route
    """
    result = ProfileResult()
    result.grid_cols, result.grid_rows, result.grid_layers = grid_size
    result.grid_cell_size_mm = cell_size_mm
    result.total_cells = result.grid_cols * result.grid_rows * result.grid_layers

    total_start = time.perf_counter()

    # Generate random obstacles
    print(f"  Generating {obstacle_density:.0%} obstacle density...")
    t0 = time.perf_counter()

    np.random.seed(42)  # Reproducible
    obstacles: Set[Tuple[int, int, int]] = set()

    # Block random cells
    num_obstacles = int(result.total_cells * obstacle_density)
    for _ in range(num_obstacles):
        x = np.random.randint(0, result.grid_cols)
        y = np.random.randint(0, result.grid_rows)
        layer = np.random.randint(0, result.grid_layers)
        obstacles.add((x, y, layer))

    # Clear a corridor for the route (so it's possible)
    corridor_y = result.grid_rows // 2
    corridor_width = 10
    for x in range(result.grid_cols):
        for dy in range(-corridor_width, corridor_width + 1):
            y = corridor_y + dy
            if 0 <= y < result.grid_rows:
                for layer in range(result.grid_layers):
                    obstacles.discard((x, y, layer))

    result.obstacle_build_time_s = time.perf_counter() - t0
    result.obstacle_count = len(obstacles)
    result.obstacle_density_pct = (len(obstacles) / result.total_cells) * 100

    # Initialize router
    print(f"  Initializing DiffPairRouter...")
    t0 = time.perf_counter()

    router = DiffPairRouter(
        grid_size=grid_size,
        cell_size_mm=cell_size_mm,
        target_separation_mm=0.2,
        max_divergence_mm=0.5,
        max_skew_mm=0.5,
        beam_width=1000,
    )

    result.router_init_time_s = time.perf_counter() - t0

    # Define start and goal pins
    margin = 20  # cells from edge
    start_x = margin
    goal_x = result.grid_cols - margin
    center_y = result.grid_rows // 2

    start_pins = (
        (start_x * cell_size_mm, center_y * cell_size_mm),
        (start_x * cell_size_mm, (center_y - 2) * cell_size_mm),
    )
    goal_pins = (
        (goal_x * cell_size_mm, center_y * cell_size_mm),
        (goal_x * cell_size_mm, (center_y - 2) * cell_size_mm),
    )

    # Route
    print(f"  Routing diff pair ({start_x},{center_y}) -> ({goal_x},{center_y})...")
    t0 = time.perf_counter()

    route_result = router.route_pair(
        start_pins=start_pins,
        goal_pins=goal_pins,
        obstacles=obstacles,
        enable_length_matching=False,
    )

    result.routing_time_s = time.perf_counter() - t0
    result.total_time_s = time.perf_counter() - total_start

    # Collect router stats
    result.states_explored = router.states_explored
    result.states_pruned = router.states_pruned
    result.beam_pruned = router.beam_pruned
    result.spacing_pruned = router.spacing_pruned

    # Route result
    result.success = route_result.success
    result.failure_reason = route_result.failure_reason
    result.coupling_ratio = route_result.coupling_ratio
    result.max_skew_mm = route_result.max_skew_mm
    if route_result.success:
        result.path_length_cells = len(route_result.pos_cells)

    return result


def profile_with_clearance_grid(
    board_width_mm: float = 100.0,
    board_height_mm: float = 150.0,
    cell_size_mm: float = 0.25,
    layer_count: int = 4,
) -> ProfileResult:
    """
    Profile using actual ClearanceGrid infrastructure.
    Tests both naive and vectorized obstacle extraction.
    """
    result = ProfileResult()

    print(
        f"\n  Creating ClearanceGrid ({board_width_mm}x{board_height_mm}mm, {cell_size_mm}mm cells)..."
    )

    t0 = time.perf_counter()
    grid = ClearanceGrid(
        width_mm=board_width_mm,
        height_mm=board_height_mm,
        cell_size_mm=cell_size_mm,
        layer_count=layer_count,
    )
    grid_init_time = time.perf_counter() - t0

    result.grid_cols = grid.cols
    result.grid_rows = grid.rows
    result.grid_layers = grid.layer_count
    result.grid_cell_size_mm = grid.cell_size_mm
    result.total_cells = grid.cols * grid.rows * grid.layer_count

    print(f"    Grid: {grid.cols}x{grid.rows}x{grid.layer_count} = {result.total_cells:,} cells")
    print(f"    Init time: {grid_init_time * 1000:.1f}ms")

    # Block some random obstacles to simulate real board
    print(f"  Blocking synthetic components...")
    np.random.seed(42)

    # Add some component pads (circles)
    num_components = 50
    for _ in range(num_components):
        cx = np.random.uniform(10, board_width_mm - 10)
        cy = np.random.uniform(10, board_height_mm - 10)
        layer = np.random.randint(0, layer_count)
        grid.block_circle(
            center=(cx, cy),
            radius_mm=1.0,
            clearance_mm=0.2,
            layer=layer,
            net_name=f"obstacle_{_}",
        )

    # Add some traces (line segments)
    num_traces = 100
    for i in range(num_traces):
        x1 = np.random.uniform(5, board_width_mm - 5)
        y1 = np.random.uniform(5, board_height_mm - 5)
        x2 = x1 + np.random.uniform(-20, 20)
        y2 = y1 + np.random.uniform(-20, 20)
        x2 = float(np.clip(x2, 0, board_width_mm))
        y2 = float(np.clip(y2, 0, board_height_mm))
        layer = np.random.randint(0, layer_count)
        # Use block_trace with a simple 2-point path
        grid.block_trace(
            path=[(float(x1), float(y1)), (x2, y2)],
            width_mm=0.25,
            clearance_mm=0.2,
            layer=layer,
            net_name=f"trace_{i}",
        )

    # Test naive obstacle extraction
    print(f"\n  Testing NAIVE obstacle extraction (O(n³))...")
    obstacles_naive, naive_time = build_obstacles_naive(grid)
    print(f"    Time: {naive_time:.3f}s ({naive_time * 1000:.1f}ms)")
    print(f"    Obstacles: {len(obstacles_naive):,}")

    # Test vectorized obstacle extraction
    print(f"\n  Testing VECTORIZED obstacle extraction...")
    obstacles_vec, vec_time = build_obstacles_vectorized(grid)
    print(f"    Time: {vec_time:.3f}s ({vec_time * 1000:.1f}ms)")
    print(f"    Obstacles: {len(obstacles_vec):,}")
    print(f"    Speedup: {naive_time / vec_time:.1f}x")

    result.obstacle_build_time_s = naive_time  # Use naive time for comparison
    result.obstacle_count = len(obstacles_naive)
    result.obstacle_density_pct = (len(obstacles_naive) / result.total_cells) * 100

    return result


def print_profile_report(result: ProfileResult, title: str = "Profile Results"):
    """Pretty-print profiling results."""
    print(f"\n{'=' * 70}")
    print(f" {title}")
    print(f"{'=' * 70}")

    print(f"\n📊 Grid Configuration:")
    print(f"   Size: {result.grid_cols} x {result.grid_rows} x {result.grid_layers}")
    print(f"   Cell size: {result.grid_cell_size_mm}mm")
    print(f"   Total cells: {result.total_cells:,}")

    print(f"\n🚧 Obstacles:")
    print(f"   Count: {result.obstacle_count:,}")
    print(f"   Density: {result.obstacle_density_pct:.2f}%")

    print(f"\n⏱️  Timing Breakdown:")
    print(
        f"   Obstacle extraction: {result.obstacle_build_time_s * 1000:>8.1f}ms ({result.obstacle_build_pct:.1f}%)"
    )
    print(f"   Router init:         {result.router_init_time_s * 1000:>8.1f}ms")
    print(f"   Routing:             {result.routing_time_s * 1000:>8.1f}ms")
    print(f"   ────────────────────────────────")
    print(
        f"   TOTAL:               {result.total_time_s * 1000:>8.1f}ms ({result.total_time_s:.2f}s)"
    )

    if result.states_explored > 0:
        print(f"\n🔍 Search Statistics:")
        print(f"   States explored: {result.states_explored:,}")
        print(f"   States pruned:   {result.states_pruned:,}")
        print(f"   Beam pruned:     {result.beam_pruned:,}")
        print(f"   Spacing pruned:  {result.spacing_pruned:,}")
        print(f"   Pruning efficiency: {result.pruning_efficiency:.1%}")
        print(f"   States/second:   {result.states_per_second:,.0f}")

    if result.success:
        print(f"\n✅ Route Result: SUCCESS")
        print(f"   Path length: {result.path_length_cells} cells")
        print(f"   Coupling: {result.coupling_ratio:.1%}")
        print(f"   Max skew: {result.max_skew_mm:.3f}mm")
    elif result.failure_reason:
        print(f"\n❌ Route Result: FAILED")
        print(f"   Reason: {result.failure_reason}")

    # Analysis
    print(f"\n💡 Analysis:")
    if result.obstacle_build_pct > 50:
        print(f"   ⚠️  Obstacle extraction takes {result.obstacle_build_pct:.0f}% of time!")
        print(f"      → Consider vectorized extraction (see build_obstacles_vectorized)")

    if result.routing_time_s > 10:
        print(f"   ⚠️  Routing took {result.routing_time_s:.1f}s (target: <10s)")
        if result.states_explored > 50000:
            print(f"      → {result.states_explored:,} states explored - state space explosion?")
        if result.pruning_efficiency < 0.5:
            print(
                f"      → Low pruning efficiency ({result.pruning_efficiency:.0%}) - increase beam_width?"
            )

    print(f"{'=' * 70}\n")


def main():
    parser = argparse.ArgumentParser(description="Profile USB diff pair routing")
    parser.add_argument("--pcb", type=Path, help="Path to KiCad PCB file")
    parser.add_argument("--synthetic", action="store_true", help="Run synthetic benchmark")
    parser.add_argument("--iterations", type=int, default=3, help="Iterations for synthetic test")
    parser.add_argument(
        "--grid-test", action="store_true", help="Test ClearanceGrid obstacle extraction"
    )
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print(" USB Differential Pair Routing Profiler")
    print("=" * 70)

    if args.grid_test:
        print("\n📋 Testing ClearanceGrid obstacle extraction methods...")
        profile_with_clearance_grid()
        return

    if args.synthetic:
        print(f"\n📋 Running synthetic benchmark ({args.iterations} iterations)...")

        # Test different grid sizes
        configs = [
            ("Small (200x300)", (200, 300, 4), 0.05),
            ("Medium (400x600)", (400, 600, 4), 0.05),
            ("Large (400x600) Dense", (400, 600, 4), 0.15),
        ]

        for name, grid_size, density in configs:
            print(f"\n{'─' * 70}")
            print(f"  Configuration: {name}")
            print(f"  Grid: {grid_size}, Obstacle density: {density:.0%}")

            times = []
            result: Optional[ProfileResult] = None
            for i in range(args.iterations):
                print(f"\n  Iteration {i + 1}/{args.iterations}:")
                result = profile_synthetic_routing(
                    grid_size=grid_size,
                    obstacle_density=density,
                )
                times.append(result.routing_time_s)

            avg_time = sum(times) / len(times)
            if result is not None:
                print_profile_report(result, f"Results: {name}")
            print(f"  Average routing time: {avg_time * 1000:.1f}ms over {args.iterations} runs")

        return

    # Real PCB profiling (to be implemented with actual PCB parsing)
    print("\n⚠️  Real PCB profiling requires the full pipeline.")
    print("   Use --synthetic for now, or --grid-test to profile obstacle extraction.")
    print("\n   Example commands:")
    print("     python3 scripts/profile_usb_routing.py --synthetic")
    print("     python3 scripts/profile_usb_routing.py --grid-test")


if __name__ == "__main__":
    main()
