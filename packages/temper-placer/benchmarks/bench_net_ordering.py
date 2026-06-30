"""
Benchmark: bottleneck-first vs area-only net ordering.

Compares completion rate and wall time for 8, 12, 16 net configurations.
Each configuration is run 5 times (with different random seeds) to amortize
variance.  Both orderings get the same grids and net assignments — only
the route order changes.

Run with:
    cd packages/temper-placer && uv run python benchmarks/bench_net_ordering.py
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from temper_placer.router_v6.astar_pathfinding import (
    _compute_bottleneck_widths,
    _compute_net_order,
    run_astar_pathfinding,
)
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

if TYPE_CHECKING:
    pass


@dataclass
class OrderingResult:
    """Comparison of two ordering strategies for one run."""

    net_count: int
    seed: int
    area_complete: int
    bottleneck_complete: int
    area_time_ms: float
    bottleneck_time_ms: float
    area_order: list[str] = field(repr=False)
    bottleneck_order: list[str] = field(repr=False)
    bottleneck_widths: dict[str, float] = field(repr=False)

    @property
    def area_completion_pct(self) -> float:
        return (self.area_complete / self.net_count * 100) if self.net_count > 0 else 0.0

    @property
    def bottleneck_completion_pct(self) -> float:
        return (self.bottleneck_complete / self.net_count * 100) if self.net_count > 0 else 0.0

    @property
    def delta_completion(self) -> int:
        return self.bottleneck_complete - self.area_complete

    @property
    def speedup(self) -> float:
        return self.area_time_ms / self.bottleneck_time_ms if self.bottleneck_time_ms > 0 else 1.0


def _build_edt_for_test(
    width_cells: int,
    height_cells: int,
    blocked_cells: set[tuple[int, int]] | None = None,
    cell_size: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, tuple[float, float, float, float]]:
    """Build a synthetic EDT for a rectangular test region.

    Interior cells get EDT distance = diagonal of the grid
    (simulating open space).  Blocked cells get distance = 0.
    """
    blocked = blocked_cells or set()
    mask = np.ones((height_cells, width_cells), dtype=bool)
    edt = np.zeros((height_cells, width_cells), dtype=np.float64)
    max_dist = math.sqrt(width_cells**2 + height_cells**2) / 2.0
    for r in range(height_cells):
        for c in range(width_cells):
            key = (c, r)
            if key in blocked:
                mask[r, c] = False
                edt[r, c] = 0.0
            else:
                edt[r, c] = max_dist
    bounds = (0.0, 0.0, float(width_cells) * cell_size, float(height_cells) * cell_size)
    return edt, mask, bounds


def _generate_random_nets(
    net_count: int,
    grid_size_cells: int,
    seed: int,
) -> ChannelMapping:
    """Generate random net configurations with a synthetic bottleneck.

    Half the nets pass through a narrow corridor (the "bottleneck"),
    half route through open space.  This creates a realistic scenario
    where bottleneck ordering should improve completion.
    """
    rng = random.Random(seed)
    grid_max = float(grid_size_cells - 1)
    bottleneck_center = grid_size_cells // 2
    bottleneck_width = 3  # cells wide

    paths: dict[str, ChannelPath] = {}
    for i in range(net_count):
        net_name = f"NET_{i:02d}"

        if i < net_count // 2:
            # Bottleneck nets: pass through the narrow corridor
            y_narrow = float(bottleneck_center + rng.randint(-bottleneck_width, bottleneck_width))
            x_start = float(rng.randint(0, bottleneck_center - 10))
            x_end = float(rng.randint(bottleneck_center + 10, grid_size_cells - 1))
            waypoints = [(x_start, y_narrow), (x_end, y_narrow)]
        else:
            # Open-space nets: route through wide regions
            x1 = float(rng.randint(0, grid_size_cells // 3))
            y1 = float(rng.randint(0, grid_size_cells - 1))
            x2 = float(rng.randint(2 * grid_size_cells // 3, grid_size_cells - 1))
            y2 = float(rng.randint(0, grid_size_cells - 1))
            waypoints = [(x1, y1), (x2, y2)]

        paths[net_name] = ChannelPath(
            net_name=net_name,
            channel_sequence=[],
            waypoints=waypoints,
            total_length=abs(waypoints[1][0] - waypoints[0][0])
                         + abs(waypoints[1][1] - waypoints[0][1]),
            preferred_layer="F.Cu",
        )

    return ChannelMapping(channel_paths=paths)


def _run_with_ordering(
    channel_mapping: ChannelMapping,
    grid: OccupancyGrid,
    ordering_name: str,
    bottleneck_widths: dict[str, float] | None = None,
) -> tuple[int, float, list[str]]:
    """Run pathfinding with a given ordering and return (complete, time_ms, order)."""
    order = _compute_net_order(channel_mapping, bottleneck_widths=bottleneck_widths)
    start = time.perf_counter()
    result = run_astar_pathfinding(
        channel_mapping=channel_mapping,
        grid=grid,
        bottleneck_widths=bottleneck_widths,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    return result.success_count, elapsed_ms, order


def run_ordering_comparison(
    net_count: int,
    grid_size_cells: int = 50,
    seeds: tuple[int, ...] = (42, 123, 456, 789, 1011),
) -> list[OrderingResult]:
    """Run ordering comparison for a given net count with multiple seeds.

    Returns a list of OrderingResult, one per seed.
    """
    results: list[OrderingResult] = []

    for seed in seeds:
        # Generate the same random net configuration for both orderings
        channel_mapping = _generate_random_nets(net_count, grid_size_cells, seed)

        # Build EDT for bottleneck width computation (pad to avoid boundary artifacts)
        grid_pad = 5
        blocked = set()
        bottleneck_center = grid_size_cells // 2
        # Create a pinched region: block cells around the bottleneck
        for r in range(grid_size_cells + grid_pad):
            for c in range(grid_size_cells + grid_pad - 1):
                if bottleneck_center - 5 <= c <= bottleneck_center + 5:
                    if r < bottleneck_center - 4 or r > bottleneck_center + 4:
                        blocked.add((c, r))

        edt, mask, bounds = _build_edt_for_test(
            grid_size_cells + grid_pad, grid_size_cells + grid_pad, blocked, cell_size=1.0,
        )
        bw = _compute_bottleneck_widths(
            channel_mapping, edt, mask, bounds, cell_size=1.0, sample_distance=0.5,
        )
        bw_finite = {k: v for k, v in bw.items() if v != float('inf')}
        bw_finite.update({k: float(grid_size_cells) for k, v in bw.items() if v == float('inf')})

        # Build an empty occupancy grid for routing
        grid = OccupancyGrid(
            "F.Cu",
            np.zeros((grid_size_cells, grid_size_cells), dtype=np.int8),
            (0.0, 0.0),
            1.0,
            grid_size_cells,
            grid_size_cells,
        )

        print(f"  Seed {seed} ({net_count} nets)...", end=" ", flush=True)

        area_complete, area_time, area_order = _run_with_ordering(
            channel_mapping, grid, "area", bottleneck_widths=None,
        )
        bottleneck_complete, bottleneck_time, bottleneck_order = _run_with_ordering(
            channel_mapping, grid, "bottleneck", bottleneck_widths=bw_finite,
        )

        result = OrderingResult(
            net_count=net_count,
            seed=seed,
            area_complete=area_complete,
            bottleneck_complete=bottleneck_complete,
            area_time_ms=area_time,
            bottleneck_time_ms=bottleneck_time,
            area_order=area_order,
            bottleneck_order=bottleneck_order,
            bottleneck_widths={k: round(v, 2) for k, v in bw_finite.items()},
        )

        print(f"area={area_complete}/{net_count} ({area_time:.0f}ms) "
              f"bottleneck={bottleneck_complete}/{net_count} ({bottleneck_time:.0f}ms)")

        results.append(result)

    return results


def print_summary(all_results: list[OrderingResult]) -> None:
    """Print a formatted summary table."""
    print(f"\n{'=' * 90}")
    print("BOTTLENECK-FIRST vs AREA-ONLY NET ORDERING BENCHMARK")
    print(f"{'=' * 90}")

    by_count: dict[int, list[OrderingResult]] = {}
    for r in all_results:
        by_count.setdefault(r.net_count, []).append(r)

    print(f"\n{'Nets':>5} {'Seed':>5} {'Area':>7} {'Bottleneck':>11} {'Delta':>6} "
          f"{'Area ms':>9} {'Bottleneck ms':>14} {'Speedup':>8}")
    print("-" * 90)

    for net_count in sorted(by_count):
        for r in by_count[net_count]:
            delta_str = f"+{r.delta_completion}" if r.delta_completion > 0 else str(r.delta_completion)
            print(f"{r.net_count:>5} {r.seed:>5} {r.area_complete:>5}/{r.net_count:<1} "
                  f"{r.bottleneck_complete:>5}/{r.net_count:<5} {delta_str:>6} "
                  f"{r.area_time_ms:>8.0f} {r.bottleneck_time_ms:>13.0f} {r.speedup:>7.2f}x")

    print(f"\n{'=' * 90}")
    print("AGGREGATED BY NET COUNT")
    print(f"{'=' * 90}")
    print(f"{'Nets':>5} {'Avg Area':>9} {'Avg Bottleneck':>15} {'Avg Delta':>10} "
          f"{'Avg Speedup':>11} {'Wins':>5} {'Losses':>7} {'Ties':>5}")
    print("-" * 90)

    for net_count in sorted(by_count):
        group = by_count[net_count]
        avg_area = sum(r.area_completion_pct for r in group) / len(group)
        avg_bottleneck = sum(r.bottleneck_completion_pct for r in group) / len(group)
        avg_delta = sum(r.delta_completion for r in group) / len(group)
        avg_speedup = sum(r.speedup for r in group) / len(group)
        wins = sum(1 for r in group if r.delta_completion > 0)
        losses = sum(1 for r in group if r.delta_completion < 0)
        ties = sum(1 for r in group if r.delta_completion == 0)

        print(f"{net_count:>5} {avg_area:>8.1f}% {avg_bottleneck:>14.1f}% "
              f"{avg_delta:>+9.1f} {avg_speedup:>10.2f}x {wins:>5} {losses:>7} {ties:>5}")


def main() -> None:
    """Run the full benchmark suite."""
    print("Bottleneck-First Net Ordering Benchmark")
    print("=" * 50)

    all_results: list[OrderingResult] = []

    for net_count in [8, 12, 16]:
        print(f"\n--- {net_count} net configuration ---")
        results = run_ordering_comparison(net_count=net_count)
        all_results.extend(results)

    print_summary(all_results)

    # Write JSON output
    output_path = Path(__file__).parent / "bench_net_ordering_results.json"
    output = {
        "timestamp": datetime.now().isoformat(),
        "results": [asdict(r) for r in all_results],
        "summary": {
            "total_runs": len(all_results),
            "bottleneck_wins": sum(1 for r in all_results if r.delta_completion > 0),
            "bottleneck_losses": sum(1 for r in all_results if r.delta_completion < 0),
            "ties": sum(1 for r in all_results if r.delta_completion == 0),
        },
    }
    output_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults written to: {output_path}")

    # Sanity check: bottleneck should never lose
    losses = sum(1 for r in all_results if r.delta_completion < 0)
    if losses > 0:
        print(f"\nWARNING: Bottleneck ordering had {losses} losses vs area-only!")
        print("This violates the theoretical invariant and needs investigation.")


if __name__ == "__main__":
    main()
