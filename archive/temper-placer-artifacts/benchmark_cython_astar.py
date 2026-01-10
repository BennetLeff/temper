#!/usr/bin/env python3
"""Benchmark Cython vs Python A* implementations.

This script measures the performance improvement from the Cython implementation
by comparing against the Python baseline on realistic routing scenarios.

Usage:
    python benchmark_cython_astar.py
    python benchmark_cython_astar.py --verbose
    python benchmark_cython_astar.py --iterations 10
"""

import argparse
import os
import sys
import time
import statistics
from pathlib import Path
from typing import List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.deterministic.stages.multilayer_astar import MultiLayerAStar
from temper_placer.core.units import Millimeters


class BenchmarkResult:
    """Results from a single benchmark run."""

    def __init__(self, name: str, cython_times: List[float], python_times: List[float]):
        self.name = name
        self.cython_times = cython_times
        self.python_times = python_times

        self.cython_mean = statistics.mean(cython_times)
        self.cython_stdev = statistics.stdev(cython_times) if len(cython_times) > 1 else 0.0

        self.python_mean = statistics.mean(python_times)
        self.python_stdev = statistics.stdev(python_times) if len(python_times) > 1 else 0.0

        self.speedup = self.python_mean / self.cython_mean if self.cython_mean > 0 else 0.0

    def __str__(self):
        return (
            f"{self.name}:\n"
            f"  Cython: {self.cython_mean * 1000:.2f}ms ± {self.cython_stdev * 1000:.2f}ms\n"
            f"  Python: {self.python_mean * 1000:.2f}ms ± {self.python_stdev * 1000:.2f}ms\n"
            f"  Speedup: {self.speedup:.1f}x"
        )


def create_test_grid(
    width_mm: float,
    height_mm: float,
    cell_size_mm: float = 0.5,
    layers: int = 4,
    obstacle_density: float = 0.0,
) -> ClearanceGrid:
    """Create a test grid with optional obstacles.

    Args:
        width_mm: Grid width in mm
        height_mm: Grid height in mm
        cell_size_mm: Cell size in mm
        layers: Number of layers
        obstacle_density: Fraction of cells to block (0.0 = empty, 1.0 = full)
    """
    import numpy as np

    cols = int(width_mm / cell_size_mm)
    rows = int(height_mm / cell_size_mm)

    grid = ClearanceGrid(
        width_mm=width_mm, height_mm=height_mm, cell_size_mm=cell_size_mm, layer_count=layers
    )

    # Add random obstacles if requested
    if obstacle_density > 0.0:
        rng = np.random.RandomState(42)  # Deterministic
        for layer in range(layers):
            for row in range(rows):
                for col in range(cols):
                    if rng.random() < obstacle_density:
                        # Mark as obstacle (net_id=-1)
                        grid.occupancy_grid[layer, row, col] = -1

    return grid


def benchmark_route(
    grid: ClearanceGrid,
    start: Tuple[float, float],
    end: Tuple[float, float],
    start_layer: int = 0,
    end_layer: int = -1,
    iterations: int = 5,
    verbose: bool = False,
) -> Tuple[List[float], List[float]]:
    """Benchmark a single route with both implementations.

    Returns:
        (cython_times, python_times) in seconds
    """
    net_name = "benchmark_net"

    cython_times = []
    python_times = []

    # Benchmark Cython
    if verbose:
        print(f"  Benchmarking Cython ({iterations} iterations)...", end="", flush=True)

    os.environ["TEMPER_USE_CYTHON_ASTAR"] = "1"
    astar_cython = MultiLayerAStar(
        grid=grid, net_name=net_name, via_cost=5.0, allowed_layers=list(range(grid.layer_count))
    )

    for i in range(iterations):
        start_time = time.perf_counter()
        path = astar_cython.find_path(start, end, start_layer, end_layer)
        elapsed = time.perf_counter() - start_time
        cython_times.append(elapsed)

        if path is None and i == 0:
            if verbose:
                print(" NO PATH FOUND!")
            return cython_times, python_times

    if verbose:
        print(f" done ({statistics.mean(cython_times) * 1000:.2f}ms)")

    # Benchmark Python
    if verbose:
        print(f"  Benchmarking Python ({iterations} iterations)...", end="", flush=True)

    os.environ["TEMPER_USE_CYTHON_ASTAR"] = "0"
    astar_python = MultiLayerAStar(
        grid=grid, net_name=net_name, via_cost=5.0, allowed_layers=list(range(grid.layer_count))
    )

    for i in range(iterations):
        start_time = time.perf_counter()
        path = astar_python.find_path(start, end, start_layer, end_layer)
        elapsed = time.perf_counter() - start_time
        python_times.append(elapsed)

    if verbose:
        print(f" done ({statistics.mean(python_times) * 1000:.2f}ms)")

    return cython_times, python_times


def benchmark_suite(iterations: int = 5, verbose: bool = False) -> List[BenchmarkResult]:
    """Run comprehensive benchmark suite.

    Args:
        iterations: Number of iterations per test
        verbose: Print progress

    Returns:
        List of BenchmarkResult objects
    """
    results = []

    # Test 1: Short straight path (baseline)
    if verbose:
        print("\n1. Short straight path (10mm, empty grid)")

    grid = create_test_grid(50, 50, cell_size_mm=0.5, layers=2)
    cython_t, python_t = benchmark_route(
        grid, (5, 5), (15, 15), iterations=iterations, verbose=verbose
    )
    results.append(BenchmarkResult("Short straight path", cython_t, python_t))

    # Test 2: Long diagonal path
    if verbose:
        print("\n2. Long diagonal path (50mm, empty grid)")

    grid = create_test_grid(100, 100, cell_size_mm=0.5, layers=2)
    cython_t, python_t = benchmark_route(
        grid, (10, 10), (90, 90), iterations=iterations, verbose=verbose
    )
    results.append(BenchmarkResult("Long diagonal path", cython_t, python_t))

    # Test 3: Path with obstacles (10% density)
    if verbose:
        print("\n3. Path with obstacles (50mm, 10% obstacles)")

    grid = create_test_grid(100, 100, cell_size_mm=0.5, layers=2, obstacle_density=0.1)
    cython_t, python_t = benchmark_route(
        grid, (10, 10), (90, 90), iterations=iterations, verbose=verbose
    )
    results.append(BenchmarkResult("Path with 10% obstacles", cython_t, python_t))

    # Test 4: Multi-layer routing
    if verbose:
        print("\n4. Multi-layer path (4 layers)")

    grid = create_test_grid(100, 100, cell_size_mm=0.5, layers=4)
    cython_t, python_t = benchmark_route(
        grid, (10, 10), (90, 90), start_layer=0, end_layer=3, iterations=iterations, verbose=verbose
    )
    results.append(BenchmarkResult("Multi-layer (4 layers)", cython_t, python_t))

    # Test 5: High congestion (25% obstacles)
    if verbose:
        print("\n5. High congestion (50mm, 25% obstacles)")

    grid = create_test_grid(100, 100, cell_size_mm=0.5, layers=2, obstacle_density=0.25)
    cython_t, python_t = benchmark_route(
        grid, (10, 10), (90, 90), iterations=iterations, verbose=verbose
    )
    results.append(BenchmarkResult("High congestion (25%)", cython_t, python_t))

    # Test 6: Very long path (realistic PCB size)
    if verbose:
        print("\n6. Very long path (150mm, PCB-scale)")

    grid = create_test_grid(200, 150, cell_size_mm=0.5, layers=4)
    cython_t, python_t = benchmark_route(
        grid, (20, 20), (180, 130), iterations=max(1, iterations // 2), verbose=verbose
    )
    results.append(BenchmarkResult("Very long path (150mm)", cython_t, python_t))

    return results


def print_summary(results: List[BenchmarkResult]):
    """Print benchmark summary table."""
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS SUMMARY")
    print("=" * 80)

    print(f"\n{'Test':<30} {'Cython (ms)':<15} {'Python (ms)':<15} {'Speedup':<10}")
    print("-" * 80)

    for result in results:
        print(
            f"{result.name:<30} "
            f"{result.cython_mean * 1000:>8.2f} ± {result.cython_stdev * 1000:>4.2f}  "
            f"{result.python_mean * 1000:>8.2f} ± {result.python_stdev * 1000:>4.2f}  "
            f"{result.speedup:>8.1f}x"
        )

    # Overall statistics
    speedups = [r.speedup for r in results if r.speedup > 0]
    if speedups:
        avg_speedup = statistics.mean(speedups)
        min_speedup = min(speedups)
        max_speedup = max(speedups)

        print("-" * 80)
        print(f"{'Average speedup:':<30} {avg_speedup:>8.1f}x")
        print(f"{'Range:':<30} {min_speedup:>8.1f}x - {max_speedup:>8.1f}x")

    print("=" * 80)

    # Performance verdict
    avg_speedup = statistics.mean(speedups) if speedups else 0
    if avg_speedup >= 50:
        verdict = "🚀 EXCELLENT! Target exceeded (50x+)"
    elif avg_speedup >= 30:
        verdict = "✅ TARGET MET! (30-50x)"
    elif avg_speedup >= 10:
        verdict = "✓ Good speedup (10-30x)"
    else:
        verdict = "⚠ Below target (<10x)"

    print(f"\nPerformance: {verdict}\n")


def main():
    parser = argparse.ArgumentParser(description="Benchmark Cython vs Python A* implementations")
    parser.add_argument(
        "--iterations", type=int, default=5, help="Iterations per test (default: 5)"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    print("=" * 80)
    print("Cython A* Pathfinding Benchmark")
    print("=" * 80)
    print(f"Iterations per test: {args.iterations}")
    print(f"Target speedup: 30-100x")

    # Run benchmarks
    results = benchmark_suite(iterations=args.iterations, verbose=args.verbose)

    # Print results
    print_summary(results)


if __name__ == "__main__":
    main()
