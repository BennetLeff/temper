#!/usr/bin/env python3
"""
Experiment T1: The Packing Limit (Calibration).

Determines the practical routing efficiency (eta) of the Lazy Theta* router
under different via densities.
"""

import random
import time
import numpy as np
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.astar_pathfinding import _astar_route, RoutePath
from temper_placer.router_v6.stage0_data import DesignRules
from dataclasses import dataclass


@dataclass
class MockChannelPath:
    waypoints: list[tuple[float, float]]
    preferred_layer: str


def run_trial(n_nets: int, mode: str, width_mm: float, height_mm: float) -> float:
    """
    Run a routing trial.
    mode: "straight" (no vias) or "switch" (force via)
    Returns success rate (0.0 to 1.0).
    """
    # 1. Setup Grid (Multi-layer)
    resolution = 0.05
    w_cells = int(width_mm / resolution)
    h_cells = int(height_mm / resolution)

    # Create 2 layers
    grid_f = OccupancyGrid(
        "F.Cu", np.zeros((h_cells, w_cells), dtype=np.int16), (0, 0), resolution, w_cells, h_cells
    )
    grid_b = OccupancyGrid(
        "B.Cu", np.zeros((h_cells, w_cells), dtype=np.int16), (0, 0), resolution, w_cells, h_cells
    )
    grid_f.__post_init__()
    grid_b.__post_init__()

    # We need a unified grid dict
    all_grids = {"F.Cu": grid_f, "B.Cu": grid_b}

    # THT locations everywhere (allow vias anywhere for this test)
    # In reality, vias can be placed anywhere.
    # We'll mock THT locations to cover the whole grid step 1mm
    tht_locs = set()
    for x in np.arange(0, width_mm, 0.5):
        for y in np.arange(0, height_mm, 0.5):
            tht_locs.add((x, y))

    # 2. Route Nets
    success_count = 0
    trace_width = 0.2
    clearance = 0.2

    # Pitch = 0.4mm. Via Dia = 0.6mm (0.3 drill + pad).
    # Via needs 0.6 + 0.4(clearance) = 1.0mm space?
    # No, via clearance is usually same as trace clearance?
    # Let's assume standard Via.

    indices = list(range(n_nets))
    pitch = height_mm / (n_nets + 1)

    for i in indices:
        y_pos = (i + 1) * pitch
        start = (0.5, y_pos)
        end = (width_mm - 0.5, y_pos)

        # If switch mode, we force layer change?
        # A* automatically switches if start/end on diff layers.
        # Let's set start on F.Cu, end on B.Cu.

        # Mock channel path needs to guide this?
        # A* uses grids.

        # We need to call _astar_route_multilayer logic?
        # Or _astar_route_with_ripup which handles it.
        # But that function is complex.
        # Let's use _astar_route_multilayer directly.

        from temper_placer.router_v6.astar_pathfinding import _astar_route_multilayer

        # Need channel path to have start/end
        channel_path = MockChannelPath([start, end], "F.Cu")

        if mode == "switch":
            # Force switch by blocking target on F.Cu?
            # Or just rely on A* finding best path?
            # Actually, standard A* 3D neighbor expansion handles vias.
            # But our router uses `_astar_route_multilayer` which does segment-based switching.
            # It tries Primary -> if fail -> Alternate.
            # To FORCE a via, we need to make F.Cu blocked at destination?

            # Let's manually block the end of F.Cu
            # Block region around end on F.Cu
            grid_f.mark_via_blocked(end[0], end[1], 2.0, 0.0, 999)
            # But leave B.Cu open.
            pass

        # Run router
        # We need to adapt the call
        path = _astar_route_multilayer(
            f"Net{i}",
            channel_path,
            primary_grid=grid_f,
            alternate_grid=grid_b,
            tht_locations=tht_locs,
            use_lazy_theta_star=True,
        )

        if path:
            success_count += 1
            # Mark blocked on both layers for via?
            # RoutePath3D has segments with layers.
            # And via_positions.

            from temper_placer.router_v6.occupancy_grid import mark_path_blocked_3d

            mark_path_blocked_3d(all_grids, path.segments, trace_width, clearance, i + 1)

            # Mark vias
            for v in path.via_positions:
                grid_f.mark_via_blocked(v[0], v[1], 0.6, clearance, i + 1)
                grid_b.mark_via_blocked(v[0], v[1], 0.6, clearance, i + 1)

    return success_count / n_nets


def main():
    print("Experiment T1-Via: Packing Limit with Layer Switching")
    print("-----------------------------------------------------")
    print(f"{'Mode':<10} | {'Nets':<5} | {'Success':<8} | {'Eff (eta)':<10}")
    print("-" * 50)

    width = 10.0
    height = 5.0
    pitch = 0.4
    theoretical_max = int(height / pitch)  # 12

    modes = ["straight", "switch"]

    for mode in modes:
        for n in range(6, 16, 2):  # 6, 8, 10, 12, 14
            # Run trials
            rates = [run_trial(n, mode, width, height) for _ in range(3)]
            avg_rate = sum(rates) / len(rates)
            eta = n / theoretical_max
            print(f"{mode:<10} | {n:<5} | {avg_rate * 100:.0f}%     | {eta:.2f}")


if __name__ == "__main__":
    main()
