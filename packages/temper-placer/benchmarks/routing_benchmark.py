"""
Routing benchmark suite for maze router performance measurement.

Run with: cd packages/temper-placer && uv run python benchmarks/routing_benchmark.py

This creates deterministic routing problems of various sizes and measures:
- Total routing time
- Nets per second
- RRR iterations to convergence
- Final conflict count
"""

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.router_v6.adapter import MazeRouter
from temper_placer.router_v6.layer_assignment import Layer, LayerAssignment


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""
    name: str
    net_count: int
    grid_width: int
    grid_height: int
    num_layers: int
    total_time_ms: float
    iterations: int
    final_conflicts: int
    nets_per_second: float
    avg_path_length: float
    total_vias: int
    success_rate: float


@dataclass
class BenchmarkSuite:
    """Collection of benchmark results."""
    timestamp: str
    results: list[BenchmarkResult]

    def to_json(self) -> str:
        return json.dumps({
            "timestamp": self.timestamp,
            "results": [asdict(r) for r in self.results],
        }, indent=2)

    def print_table(self):
        """Print results as a formatted table."""
        print("\n" + "=" * 80)
        print("ROUTING BENCHMARKS")
        print("=" * 80)
        print(f"{'Name':<25} {'Nets':>5} {'Grid':>10} {'Time':>8} {'Nets/s':>8} {'Conflicts':>9}")
        print("-" * 80)
        for r in self.results:
            grid = f"{r.grid_width}x{r.grid_height}"
            time_str = f"{r.total_time_ms:.0f}ms"
            print(f"{r.name:<25} {r.net_count:>5} {grid:>10} {time_str:>8} {r.nets_per_second:>8.1f} {r.final_conflicts:>9}")
        print("=" * 80)


def create_test_netlist(
    net_count: int,
    component_count: int,
    board_width: float,
    board_height: float,
    seed: int = 42,
) -> tuple[Netlist, jnp.ndarray]:
    """Create a deterministic test netlist for benchmarking.

    Components are arranged in a grid pattern with random nets connecting them.
    """
    import random
    random.seed(seed)

    components = []
    positions = []

    # Arrange components in a grid
    cols = int(component_count ** 0.5)
    rows = (component_count + cols - 1) // cols

    margin = 5.0
    x_spacing = (board_width - 2 * margin) / max(1, cols - 1) if cols > 1 else 0
    y_spacing = (board_height - 2 * margin) / max(1, rows - 1) if rows > 1 else 0

    for i in range(component_count):
        col = i % cols
        row = i // cols
        x = margin + col * x_spacing if cols > 1 else board_width / 2
        y = margin + row * y_spacing if rows > 1 else board_height / 2

        comp = Component(
            ref=f"U{i+1}",
            footprint="SOIC-8",
            bounds=(3.0, 5.0),
            pins=[
                Pin("1", "1", (-1.0, -1.5)),
                Pin("2", "2", (-1.0, 0.0)),
                Pin("3", "3", (-1.0, 1.5)),
                Pin("4", "4", (1.0, 1.5)),
                Pin("5", "5", (1.0, 0.0)),
                Pin("6", "6", (1.0, -1.5)),
            ],
            initial_position=(x, y),
        )
        components.append(comp)
        positions.append([x, y])

    # Create nets connecting random pairs of components
    nets = []

    for i in range(net_count):
        # Pick two random components
        comp1_idx = random.randint(0, component_count - 1)
        comp2_idx = random.randint(0, component_count - 1)
        while comp2_idx == comp1_idx:
            comp2_idx = random.randint(0, component_count - 1)

        pin1 = random.choice(["1", "2", "3", "4", "5", "6"])
        pin2 = random.choice(["1", "2", "3", "4", "5", "6"])

        net = Net(
            name=f"NET_{i+1}",
            pins=[(f"U{comp1_idx+1}", pin1), (f"U{comp2_idx+1}", pin2)],
        )
        nets.append(net)

    return Netlist(components=components, nets=nets), jnp.array(positions)


def run_benchmark(
    name: str,
    net_count: int,
    board_width: float,
    board_height: float,
    component_count: int,
    cell_size: float = 1.0,
    num_layers: int = 1,
    max_iterations: int = 10,
) -> BenchmarkResult:
    """Run a single benchmark scenario."""

    print(f"  Running {name}...", end=" ", flush=True)

    # Create test data
    netlist, positions = create_test_netlist(
        net_count=net_count,
        component_count=component_count,
        board_width=board_width,
        board_height=board_height,
    )

    board = Board(width=board_width, height=board_height)
    router = MazeRouter.from_board(board, cell_size_mm=cell_size, num_layers=num_layers)

    # Create assignments
    net_order = [n.name for n in netlist.nets]
    assignments = {
        n.name: LayerAssignment(n.name, Layer.L1_TOP, {Layer.L1_TOP})
        for n in netlist.nets
    }

    # Run routing
    start = time.perf_counter()

    results = router.rrr_route_all_nets(
        netlist=netlist,
        positions=positions,
        net_order=net_order,
        assignments=assignments,
        max_iterations=max_iterations,
        incremental=True,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000

    # Calculate metrics
    successful = sum(1 for r in results.values() if r.success)
    success_rate = successful / max(1, len(results))
    total_length = sum(r.length for r in results.values())
    avg_length = total_length / max(1, len(results))
    total_vias = sum(r.via_count for r in results.values())

    iterations = len(router.progress_history) if hasattr(router, 'progress_history') else 0
    final_conflicts = router.progress_history[-1].total_conflicts if router.progress_history else 0

    nets_per_second = len(net_order) / (elapsed_ms / 1000) if elapsed_ms > 0 else 0

    print(f"{elapsed_ms:.0f}ms")

    return BenchmarkResult(
        name=name,
        net_count=net_count,
        grid_width=router.grid_size[0],
        grid_height=router.grid_size[1],
        num_layers=num_layers,
        total_time_ms=elapsed_ms,
        iterations=iterations,
        final_conflicts=final_conflicts,
        nets_per_second=nets_per_second,
        avg_path_length=avg_length,
        total_vias=total_vias,
        success_rate=success_rate,
    )


def run_all_benchmarks() -> BenchmarkSuite:
    """Run the complete benchmark suite."""

    print("\nStarting routing benchmarks...")

    results = []

    # Small board, few nets
    results.append(run_benchmark(
        name="small_sparse",
        net_count=10,
        board_width=20.0,
        board_height=20.0,
        component_count=8,
        cell_size=1.0,
    ))

    # Small board, dense nets
    results.append(run_benchmark(
        name="small_dense",
        net_count=30,
        board_width=20.0,
        board_height=20.0,
        component_count=8,
        cell_size=1.0,
    ))

    # Medium board, moderate density
    results.append(run_benchmark(
        name="medium_moderate",
        net_count=50,
        board_width=50.0,
        board_height=50.0,
        component_count=20,
        cell_size=1.0,
    ))

    # Medium board, dense
    results.append(run_benchmark(
        name="medium_dense",
        net_count=100,
        board_width=50.0,
        board_height=50.0,
        component_count=25,
        cell_size=1.0,
    ))

    # Large board, sparse
    results.append(run_benchmark(
        name="large_sparse",
        net_count=80,
        board_width=100.0,
        board_height=100.0,
        component_count=40,
        cell_size=2.0,  # Coarser grid for speed
    ))

    # Large board, dense (stress test)
    results.append(run_benchmark(
        name="large_dense",
        net_count=150,
        board_width=100.0,
        board_height=100.0,
        component_count=50,
        cell_size=2.0,
        max_iterations=5,  # Limit iterations
    ))

    suite = BenchmarkSuite(
        timestamp=datetime.now().isoformat(),
        results=results,
    )

    return suite


def benchmark_incremental_vs_full() -> None:
    """Compare incremental vs full rerouting."""
    print("\n" + "=" * 50)
    print("INCREMENTAL VS FULL REROUTING COMPARISON")
    print("=" * 50)

    netlist, positions = create_test_netlist(
        net_count=50,
        component_count=20,
        board_width=50.0,
        board_height=50.0,
    )

    board = Board(width=50.0, height=50.0)
    net_order = [n.name for n in netlist.nets]
    assignments = {
        n.name: LayerAssignment(n.name, Layer.L1_TOP, {Layer.L1_TOP})
        for n in netlist.nets
    }

    # Full rerouting
    router1 = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)
    start1 = time.perf_counter()
    router1.rrr_route_all_nets(
        netlist, positions, net_order, assignments,
        max_iterations=10,
        incremental=False,
    )
    time1 = (time.perf_counter() - start1) * 1000

    # Incremental rerouting
    router2 = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)
    start2 = time.perf_counter()
    router2.rrr_route_all_nets(
        netlist, positions, net_order, assignments,
        max_iterations=10,
        incremental=True,
    )
    time2 = (time.perf_counter() - start2) * 1000

    speedup = time1 / time2 if time2 > 0 else 0

    print(f"\nFull rerouting:        {time1:.0f}ms")
    print(f"Incremental rerouting: {time2:.0f}ms")
    print(f"Speedup:               {speedup:.2f}x")


if __name__ == "__main__":
    suite = run_all_benchmarks()
    suite.print_table()

    # Save results
    output_path = Path(__file__).parent / "benchmark_results.json"
    output_path.write_text(suite.to_json())
    print(f"\nResults saved to: {output_path}")

    # Run comparison
    benchmark_incremental_vs_full()
