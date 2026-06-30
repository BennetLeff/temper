"""
Congestion Derivative Benchmark.

Measures iterations wasted before/after early abort on congestion-thrashing
scenarios and on the temper board (SPI_CS_TEMP net).

Run with:
    cd packages/temper-placer && uv run python benchmarks/congestion_derivative_bench.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

from temper_placer.router_v6.astar_core import (
    _CONGESTION_CHECK_INTERVAL,
    _CONGESTION_GROWTH_THRESHOLD,
    _CONGESTION_PLATEAU_STRIKES,
    _astar_search_lazy_theta_star,
    _astar_search_theta_star,
)
from temper_placer.router_v6.occupancy_grid import OccupancyGrid


def _make_grid(rows: int, cols: int, blocked: set[tuple[int, int]] | None = None) -> OccupancyGrid:
    arr = np.zeros((rows, cols), dtype=np.int8)
    for cx, cy in (blocked or set()):
        arr[cy, cx] = 1
    return OccupancyGrid("Bench", arr, (0.0, 0.0), 1.0, cols, rows)


def _make_wall_grid(width: int, height: int, wall_col: int) -> OccupancyGrid:
    blocked = {(wall_col, y) for y in range(height)}
    return _make_grid(width, height, blocked)


def _make_spiral_maze(size: int) -> OccupancyGrid:
    """Create a spiral maze where start and goal are physically close but
    the search must explore a long spiral to find a path."""
    blocked: set[tuple[int, int]] = set()
    # Fill center with obstacles except a spiral corridor
    half = size // 2
    for y in range(size):
        for x in range(size):
            # Keep center clear for start
            if x == half and y == half:
                continue
            # Make a dense obstacle field
            if abs(x - half) < size // 4 and abs(y - half) < size // 4:
                blocked.add((x, y))
    return _make_grid(size, size, blocked)


def _make_congested_grid() -> tuple[OccupancyGrid, tuple[int, int], tuple[int, int]]:
    """Create a grid with a narrow bottleneck that causes thrashing.

    Grid layout (50x50):
    - Start at (1, 1)
    - Goal at (48, 48)
    - A dense obstacle block in the middle with only a 1-cell gap at the edges
    - This ensures the frontier must explore the entire left half before
      discovering the gap
    """
    size = 50
    blocked: set[tuple[int, int]] = set()
    # Full wall except for a tiny gap
    for y in range(size):
        blocked.add((25, y))
    # Remove a 1-cell gap at the very edge
    blocked.discard((25, 0))
    blocked.discard((25, size - 1))
    return _make_grid(size, size, blocked), (1, 1), (48, 48)


def _benchmark_scenario(
    name: str,
    grid: OccupancyGrid,
    start: tuple[int, int],
    goal: tuple[int, int],
    theta_fn,
    lazy_fn,
):
    """Benchmark a single scenario with/without early abort."""
    print(f"\n--- {name} ---")
    print(f"  Grid: {grid.width_cells}x{grid.height_cells}, "
          f"{start}->{goal}, free={np.sum(grid.grid == 0)} cells")

    min_iter = _CONGESTION_CHECK_INTERVAL * _CONGESTION_PLATEAU_STRIKES
    print(f"  Early abort triggers after >= {min_iter} expansions with "
          f"<{_CONGESTION_GROWTH_THRESHOLD} new cells/{_CONGESTION_CHECK_INTERVAL} window")

    for label, fn in [
        ("Theta* ON ", lambda: theta_fn(grid, start, goal, enable_congestion_derivative=True)),
        ("Theta* OFF", lambda: theta_fn(grid, start, goal, enable_congestion_derivative=False)),
        ("LazyT* ON ", lambda: lazy_fn(grid, start, goal, enable_congestion_derivative=True)),
        ("LazyT* OFF", lambda: lazy_fn(grid, start, goal, enable_congestion_derivative=False)),
    ]:
        t0 = time.perf_counter()
        path = fn()
        elapsed_ms = (time.perf_counter() - t0) * 1000

        status = "FOUND" if path else "NONE "
        path_len = len(path) if path else 0
        # Estimate: closed_set stops growing at abort time
        # Since we can't easily count expansions, report time
        overhead = "EARLY-ABORT" if path is None and "OFF" not in label else "FULL-SCAN" if path is None else ""

        print(f"  {label}: {status} path={path_len:>4}  {elapsed_ms:>8.2f}ms  {overhead}")


def benchmark_synthetic():
    """Benchmark on synthetic scenarios."""
    print("=" * 70)
    print("CONGESTION DERIVATIVE BENCHMARK — Synthesis")
    print("=" * 70)
    print(f"  Interval: {_CONGESTION_CHECK_INTERVAL} expansions")
    print(f"  Threshold: {_CONGESTION_GROWTH_THRESHOLD} new cells/window")
    print(f"  Strikes: {_CONGESTION_PLATEAU_STRIKES}")

    # Scenario 1: Wall grid (thrashing)
    grid = _make_wall_grid(100, 100, 50)
    _benchmark_scenario(
        "Wall Grid (100x100, vertical wall at x=50)",
        grid, (0, 0), (99, 99),
        theta_fn=lambda g, s, t, **kw: _astar_search_theta_star(g, s, t, net_id=0, **kw),
        lazy_fn=lambda g, s, t, **kw: _astar_search_lazy_theta_star(g, s, t, net_id=0, **kw),
    )

    # Scenario 2: Open grid (no thrashing)
    grid2 = _make_grid(100, 100)
    _benchmark_scenario(
        "Open Grid (100x100, no obstacles)",
        grid2, (0, 0), (99, 99),
        theta_fn=lambda g, s, t, **kw: _astar_search_theta_star(g, s, t, net_id=0, **kw),
        lazy_fn=lambda g, s, t, **kw: _astar_search_lazy_theta_star(g, s, t, net_id=0, **kw),
    )

    # Scenario 3: Congested bottleneck
    grid3, s3, g3 = _make_congested_grid()
    _benchmark_scenario(
        "Bottleneck Grid (50x50, wall with 2-cell gap)",
        grid3, s3, g3,
        theta_fn=lambda g, s, t, **kw: _astar_search_theta_star(g, s, t, net_id=0, **kw),
        lazy_fn=lambda g, s, t, **kw: _astar_search_lazy_theta_star(g, s, t, net_id=0, **kw),
    )

    # Scenario 4: Boxed-in (isolated region)
    blocked: set[tuple[int, int]] = set()
    for x in range(60):
        blocked.add((x, 29))
    for y in range(30):
        blocked.add((59, y))
        blocked.add((0, y))
    grid4 = _make_grid(60, 60, blocked)
    _benchmark_scenario(
        "Boxed-in Grid (60x60, isolated top-left quadrant)",
        grid4, (5, 5), (55, 55),
        theta_fn=lambda g, s, t, **kw: _astar_search_theta_star(g, s, t, net_id=0, **kw),
        lazy_fn=lambda g, s, t, **kw: _astar_search_lazy_theta_star(g, s, t, net_id=0, **kw),
    )

    # Scenario 5: Large wall grid (amplify the thrashing effect)
    grid5 = _make_wall_grid(300, 300, 150)
    _benchmark_scenario(
        "Wall Grid (300x300, vertical wall at x=150)",
        grid5, (0, 0), (299, 299),
        theta_fn=lambda g, s, t, **kw: _astar_search_theta_star(g, s, t, net_id=0, **kw),
        lazy_fn=lambda g, s, t, **kw: _astar_search_lazy_theta_star(g, s, t, net_id=0, **kw),
    )


def benchmark_temper_board():
    """Benchmark on the temper board, routing the 5th net (SPI_CS_TEMP).

    Parses the temper PCB, extracts pin positions, builds a routing grid
    (2000x2000, 0.1mm), and benchmarks routing of SPI_CS_TEMP.
    """
    print("\n" + "=" * 70)
    print("CONGESTION DERIVATIVE BENCHMARK — Temper Board (SPI_CS_TEMP)")
    print("=" * 70)

    # Find temper PCB
    temper_pcb = Path(__file__).resolve().parents[3] / "pcb" / "temper.kicad_pcb"
    if not temper_pcb.exists():
        print("  SKIP: temper.kicad_pcb not found")
        return

    try:
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        result = parse_kicad_pcb(temper_pcb)
        netlist = result.netlist
        board = result.board
    except Exception as e:
        print(f"  SKIP: Failed to parse temper PCB: {e}")
        return

    # Find SPI_CS_TEMP net
    target_net = None
    for net in netlist.nets:
        if "SPI_CS_TEMP" in net.name.upper() or "CS_TEMP" in net.name.upper():
            target_net = net
            break

    if target_net is None:
        nets_list = list(netlist.nets)
        if len(nets_list) >= 5:
            target_net = nets_list[4]
            print(f"  Using 5th net: {target_net.name}")
        else:
            print(f"  SKIP: Not enough nets ({len(nets_list)})")
            return
    else:
        print(f"  Found net: {target_net.name} ({len(target_net.pins)} pins)")

    if len(target_net.pins) < 2:
        print(f"  SKIP: Net has insufficient pins")
        return

    # Get pin world positions
    pin_positions = []
    for comp_ref, pin_num in target_net.pins:
        comp = next((c for c in netlist.components if c.ref == comp_ref), None)
        if comp is None:
            continue
        pin = next((p for p in comp.pins if p.number == pin_num), None)
        if pin is None:
            continue
        if comp.initial_position is None:
            continue
        wx = comp.initial_position[0] + pin.position[0]
        wy = comp.initial_position[1] + pin.position[1]
        pin_positions.append((wx, wy))

    if len(pin_positions) < 2:
        print("  SKIP: Could not resolve pin positions")
        return

    p1, p2 = pin_positions[0], pin_positions[1]
    print(f"  Pins: {p1} -> {p2}")

    # Build a simple 2000x2000 grid at 0.1mm resolution (covers 200mm board)
    grid_res = 0.1
    width_cells = 2000
    height_cells = 2000
    grid_array = np.zeros((height_cells, width_cells), dtype=np.int8)
    routable_grid = OccupancyGrid(
        "F.Cu", grid_array, (0.0, 0.0), grid_res, width_cells, height_cells,
    )

    # Convert to grid coordinates
    start_grid = (int(p1[0] / grid_res), int(p1[1] / grid_res))
    goal_grid = (int(p2[0] / grid_res), int(p2[1] / grid_res))
    print(f"  Grid cells: {start_grid} -> {goal_grid}")

    if not (0 <= start_grid[0] < width_cells and 0 <= start_grid[1] < height_cells):
        print("  SKIP: Start out of bounds")
        return
    if not (0 <= goal_grid[0] < width_cells and 0 <= goal_grid[1] < height_cells):
        print("  SKIP: Goal out of bounds")
        return

    _benchmark_scenario(
        f"Temper Board: {target_net.name}",
        routable_grid, start_grid, goal_grid,
        theta_fn=lambda g, s, t, **kw: _astar_search_theta_star(g, s, t, net_id=-1, **kw),
        lazy_fn=lambda g, s, t, **kw: _astar_search_lazy_theta_star(g, s, t, net_id=-1, **kw),
    )


if __name__ == "__main__":
    benchmark_synthetic()
    benchmark_temper_board()
    print("\nDone.")
