#!/usr/bin/env python3
"""
Search Quality Study: Simulated Annealing vs Greedy.

Quantifies the reduction in hard overlaps and final loss when using
SA vs Greedy for discrete rotation refinement.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import jax
import jax.numpy as jnp

from temper_placer.core.state import PlacementState
from temper_placer.io.config_loader import (
    create_board_from_constraints,
    load_constraints,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer.postprocess import discrete_rotation_refinement


def run_refinement_study(pcb_path: Path, config_path: Path, iterations: int = 500):
    """Run Greedy and SA on the same optimized state."""
    # 1. Setup
    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist
    constraints = load_constraints(config_path)
    board = create_board_from_constraints(constraints)
    context = LossContext.from_netlist_and_board(netlist, board)

    # Simple evaluation loss (Overlap + Wirelength)
    composite = CompositeLoss(
        [
            WeightedLoss(OverlapLoss(), weight=100.0),
            WeightedLoss(WirelengthLoss(), weight=1.0),
        ]
    )

    def loss_fn(state):
        return float(composite(state.positions, state.get_rotations(), context).value)

    # 2. Extract initial state from PCB
    positions = []
    rotations = []
    for comp in netlist.components:
        positions.append(comp.initial_position or (0.0, 0.0))
        logits = [-1.0] * 4
        logits[comp.initial_rotation or 0] = 1.0
        rotations.append(logits)

    initial_state = PlacementState(jnp.array(positions), jnp.array(rotations))

    results = {}

    # 3. Greedy Refinement
    start = time.time()
    greedy_state, greedy_loss = discrete_rotation_refinement(
        initial_state, loss_fn, search_type="greedy"
    )
    results["greedy"] = {"loss": greedy_loss, "time_s": time.time() - start}

    # 4. SA Refinement
    start = time.time()
    sa_state, sa_loss = discrete_rotation_refinement(
        initial_state, loss_fn, search_type="sa", sa_iterations=iterations
    )
    results["sa"] = {"loss": sa_loss, "time_s": time.time() - start}

    return results


def main():
    parser = argparse.ArgumentParser(description="Compare rotation refinement methods.")
    parser.add_argument("pcb", type=Path, help="Input .kicad_pcb file")
    parser.add_argument("config", type=Path, help="Constraints .yaml file")
    parser.add_argument(
        "-i", "--iterations", type=int, default=500, help="SA iterations"
    )

    args = parser.parse_args()

    print(f"Analyzing {args.pcb}...")
    results = run_refinement_study(args.pcb, args.config, args.iterations)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
