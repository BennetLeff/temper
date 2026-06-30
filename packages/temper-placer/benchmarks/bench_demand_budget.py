"""
Benchmark: completion rate and wall time with uniform vs demand-proportional budget.

Compares ``run_astar_pathfinding`` outcomes across 8-12 nets on random
boards using (a) uniform ``max_iter`` cap and (b) demand-proportional
per-net budget from ``compute_demand_budget()``.

Run with:
    cd packages/temper-placer
    uv run python benchmarks/bench_demand_budget.py
"""

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from temper_placer.router_v6.astar_pathfinding import (
    _build_edt_from_grid,
    compute_demand_budget,
    run_astar_pathfinding,
)
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


@dataclass
class RunResult:
    strategy: str
    seed: int
    num_nets: int
    width: int
    height: int
    density: float
    success_count: int
    failure_count: int
    completion_rate: float
    wall_time_ms: float

    @property
    def success_rate_pct(self) -> float:
        return self.completion_rate * 100.0


def _make_random_bench(density: float, seed: int, num_nets: int, size: int) -> tuple[ChannelMapping, OccupancyGrid, dict[str, int]]:
    """Build a random benchmark scenario.

    Returns ``(mapping, grid, budget)`` where ``budget`` is computed via
    ``compute_demand_budget`` from the grid's EDT.
    """
    rng = np.random.default_rng(seed)

    # Occupancy grid with obstacles
    arr = np.zeros((size, size), dtype=np.int8)
    for _ in range(int(density * size * size * 0.5)):
        x = rng.integers(0, size)
        y = rng.integers(0, size)
        if x >= 2 and y >= 2 and x < size - 2 and y < size - 2:
            arr[y, x] = 1
    grid = OccupancyGrid("F.Cu", arr, (0.0, 0.0), 1.0, size, size)

    # N nets with 2-3 waypoints
    paths: dict[str, ChannelPath] = {}
    for i in range(num_nets):
        n_wp = rng.integers(2, 4)
        eps = 2
        wps = [
            (float(rng.integers(eps, size - eps)), float(rng.integers(eps, size - eps)))
            for _ in range(n_wp)
        ]
        net_name = f"N{i}"
        paths[net_name] = ChannelPath(net_name, [], wps, 0.0)

    mapping = ChannelMapping(channel_paths=paths)

    # Demand budget
    edt, bounds, cell_size = _build_edt_from_grid(grid)
    budget = compute_demand_budget(edt, bounds, cell_size, mapping)

    return mapping, grid, budget


def run_strategy(
    strategy: str,
    mapping: ChannelMapping,
    grid: OccupancyGrid,
    budget: dict[str, int] | None,
    max_iter: int,
    seed: int,
    num_nets: int,
    density: float,
) -> RunResult:
    """Run pathfinding and return a ``RunResult``."""
    t0 = time.perf_counter()
    result = run_astar_pathfinding(
        mapping, grid,
        max_iter=max_iter,
        net_budgets=budget,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return RunResult(
        strategy=strategy,
        seed=seed,
        num_nets=num_nets,
        width=grid.width_cells,
        height=grid.height_cells,
        density=density,
        success_count=result.success_count,
        failure_count=result.failure_count,
        completion_rate=result.completion_rate,
        wall_time_ms=elapsed_ms,
    )


def main() -> None:
    print("\n" + "=" * 80)
    print("DEMAND-PROPORTIONAL BUDGET BENCHMARK")
    print("=" * 80)

    configs: list[dict[str, Any]] = [
        {"num_nets": 8, "density": 0.10, "size": 40},
        {"num_nets": 10, "density": 0.15, "size": 50},
        {"num_nets": 10, "density": 0.25, "size": 50},
        {"num_nets": 12, "density": 0.10, "size": 60},
        {"num_nets": 12, "density": 0.20, "size": 60},
        {"num_nets": 8, "density": 0.05, "size": 70},
        {"num_nets": 10, "density": 0.15, "size": 70},
    ]

    results: list[RunResult] = []
    base_seed = 42

    for cfg in configs:
        num_nets = cfg["num_nets"]
        density = cfg["density"]
        size = cfg["size"]

        print(f"\n  Scenario: {num_nets} nets, {density:.0%} density, {size}x{size} grid")
        print(f"  {'Strategy':<20} {'Success':>8} {'Rate':>8} {'Time':>12}")

        for rep in range(3):
            seed = base_seed + rep * 100
            mapping, grid, budget = _make_random_bench(density, seed, num_nets, size)

            # Uniform budget
            r_uniform = run_strategy(
                "uniform", mapping, grid, None, max_iter=100_000,
                seed=seed, num_nets=num_nets, density=density,
            )
            results.append(r_uniform)

            # Proportional budget
            r_prop = run_strategy(
                "proportional", mapping, grid, budget, max_iter=100_000,
                seed=seed, num_nets=num_nets, density=density,
            )
            results.append(r_prop)

            print(f"  {r_uniform.strategy:<20} {r_uniform.success_count:>2}/{r_uniform.num_nets:<4} "
                  f"{r_uniform.success_rate_pct:>6.0f}%  {r_uniform.wall_time_ms:>8.0f}ms")
            print(f"  {r_prop.strategy:<20} {r_prop.success_count:>2}/{r_prop.num_nets:<4} "
                  f"{r_prop.success_rate_pct:>6.0f}%  {r_prop.wall_time_ms:>8.0f}ms")

    # Aggregate
    uniform = [r for r in results if r.strategy == "uniform"]
    proportional = [r for r in results if r.strategy == "proportional"]

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    u_rate = sum(r.completion_rate for r in uniform) / max(len(uniform), 1)
    p_rate = sum(r.completion_rate for r in proportional) / max(len(proportional), 1)
    u_time = sum(r.wall_time_ms for r in uniform) / max(len(uniform), 1)
    p_time = sum(r.wall_time_ms for r in proportional) / max(len(proportional), 1)

    print(f"  Uniform:      avg completion rate = {u_rate:.3f} ({u_rate*100:.1f}%), "
          f"avg time = {u_time:.0f}ms")
    print(f"  Proportional: avg completion rate = {p_rate:.3f} ({p_rate*100:.1f}%), "
          f"avg time = {p_time:.0f}ms")

    rate_delta = (p_rate - u_rate) * 100.0
    time_delta_pct = ((p_time - u_time) / max(u_time, 1.0)) * 100.0
    print(f"  Delta:         completion rate +{rate_delta:.1f}pp, "
          f"time {time_delta_pct:+.1f}%")

    # Save results
    output_path = Path(__file__).parent / "bench_demand_budget.json"
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "results": [asdict(r) for r in results],
        "summary": {
            "uniform_avg_rate": u_rate,
            "proportional_avg_rate": p_rate,
            "uniform_avg_time_ms": u_time,
            "proportional_avg_time_ms": p_time,
            "rate_delta_pp": rate_delta,
            "time_delta_pct": time_delta_pct,
        },
    }
    output_path.write_text(json.dumps(output_data, indent=2))
    print(f"\n  Results saved to: {output_path}")


if __name__ == "__main__":
    main()
