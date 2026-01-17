#!/usr/bin/env python3
"""
Initialization Displacement Metric Collector.

Compares Random, Spectral, and Analytical initializations and measures
the L2 displacement required to legalize the board.
"""

import argparse
import json
from pathlib import Path

import jax
import jax.numpy as jnp
from temper_placer.core.state import PlacementState
from temper_placer.io.config_loader import (
    create_board_from_constraints,
    load_constraints,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses.base import LossContext
from temper_placer.optimizer.analytical import solve_quadratic_placement
from temper_placer.optimizer.initialization import SpectralInitializer
from temper_placer.optimizer.legalization import project_to_drc_feasible


def measure_displacement(pcb_path: Path, config_path: Path, seed: int = 42):
    """Run all three initializations and measure legalization displacement."""
    # 1. Setup
    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist
    constraints = load_constraints(config_path)
    board = create_board_from_constraints(constraints)
    context = LossContext.from_netlist_and_board(netlist, board)

    n = netlist.n_components
    results = {}

    # 2. Random Initialization
    key = jax.random.PRNGKey(seed)
    random_state = PlacementState.random_init(
        n_components=n,
        board_width=board.width,
        board_height=board.height,
        key=key,
        origin=board.origin,
    )
    results["random"] = run_legalization_study(random_state, context)

    # 3. Spectral Initialization
    spectral_init = SpectralInitializer()
    spectral_pos = spectral_init.initialize(netlist, board)
    spectral_state = PlacementState(spectral_pos, jnp.zeros((n, 4)))
    results["spectral"] = run_legalization_study(spectral_state, context)

    # 4. Analytical (Quadratic) Initialization
    # We need some fixed components for quadratic.
    # Use mounting holes or if none, fix the first few components randomly for the study
    fixed_indices = jnp.where(context.fixed_mask)[0]
    if fixed_indices.shape[0] == 0:
        # For study purposes, fix component 0 at board center if nothing is fixed
        fixed_indices = jnp.array([0])
        fixed_positions = jnp.array(
            [[board.origin[0] + board.width / 2, board.origin[1] + board.height / 2]]
        )
    else:
        fixed_positions = netlist.get_bounds_array()[
            fixed_indices
        ]  # Wrong, get positions
        # Actually get positions from parse_result
        all_initial_pos = jnp.array(
            [
                c.initial_position if c.initial_position else (0, 0)
                for c in netlist.components
            ]
        )
        fixed_positions = all_initial_pos[fixed_indices]

    analytical_pos = solve_quadratic_placement(
        netlist, board, fixed_indices, fixed_positions
    )
    analytical_state = PlacementState(analytical_pos, jnp.zeros((n, 4)))
    results["analytical"] = run_legalization_study(analytical_state, context)

    return results


def run_legalization_study(initial_state, context):
    """Legalize a state and measure the displacement."""
    legal_state = project_to_drc_feasible(initial_state, context, max_iterations=50)

    # Calculate L2 displacement per component
    disp = jnp.linalg.norm(legal_state.positions - initial_state.positions, axis=1)

    return {
        "mean_displacement_mm": float(jnp.mean(disp)),
        "max_displacement_mm": float(jnp.max(disp)),
        "total_displacement_mm": float(jnp.sum(disp)),
        "std_displacement_mm": float(jnp.std(disp)),
    }


def main():
    parser = argparse.ArgumentParser(description="Measure initialization displacement.")
    parser.add_argument("pcb", type=Path, help="Input .kicad_pcb file")
    parser.add_argument("config", type=Path, help="Constraints .yaml file")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON report")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")

    args = parser.parse_args()

    print(f"Analyzing {args.pcb}...")
    results = measure_displacement(args.pcb, args.config, args.seed)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Report written to {args.output}")
    else:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
