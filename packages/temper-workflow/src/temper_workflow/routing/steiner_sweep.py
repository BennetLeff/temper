#!/usr/bin/env python3
"""
Steiner Correction Factor Tuning Sweep.

Correlates SteinerTreeLoss against actual routed copper length
to optimize the pin-count-dependent correction factor.
"""

import argparse
import json
from pathlib import Path

import jax.numpy as jnp
from temper_placer.io.config_loader import (
    create_board_from_constraints,
    load_constraints,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses.base import LossContext
from temper_placer.losses.wirelength import SteinerTreeLoss, WirelengthLoss

from temper_workflow.routing.route_and_measure import measure_copper_length


def run_correlation_study(pcb_path: Path, config_path: Path):
    """Correlate Steiner estimation with real copper."""
    # 1. Measure real copper
    print(f"Measuring real copper for {pcb_path}...")
    real_metrics = measure_copper_length(pcb_path)
    # real_net_lengths available via real_metrics["net_lengths_mm"] if needed

    # 2. Compute HPWL and Steiner estimates
    parse_result = parse_kicad_pcb(pcb_path)
    constraints = load_constraints(config_path)
    board = create_board_from_constraints(constraints)
    context = LossContext.from_netlist_and_board(parse_result.netlist, board)

    # Need positions and rotations for loss functions
    positions = jnp.array(
        [c.initial_position or (0, 0) for c in parse_result.netlist.components]
    )
    rotations = jnp.zeros((len(parse_result.netlist.components), 4))
    for i, c in enumerate(parse_result.netlist.components):
        rotations = rotations.at[i, c.initial_rotation or 0].set(1.0)

    hpwl_loss = WirelengthLoss()
    steiner_loss = SteinerTreeLoss()

    # We want per-net breakdown
    # Note: These loss functions typically return a total.
    # For tuning, we need to extract per-net HPWL.

    # Simplified logic for now: compare totals
    est_hpwl = float(hpwl_loss(positions, rotations, context).value)
    est_steiner = float(steiner_loss(positions, rotations, context).value)
    actual = real_metrics["total_wirelength_mm"]

    return {
        "actual_mm": actual,
        "hpwl_mm": est_hpwl,
        "steiner_mm": est_steiner,
        "hpwl_error": (est_hpwl / actual) if actual > 0 else 1.0,
        "steiner_error": (est_steiner / actual) if actual > 0 else 1.0,
    }


def main():
    parser = argparse.ArgumentParser(description="Tune Steiner correction factor.")
    parser.add_argument("pcbs", type=Path, nargs="+", help="Routed .kicad_pcb files")
    parser.add_argument(
        "-c", "--config", type=Path, required=True, help="Constraints .yaml"
    )

    args = parser.parse_args()

    results = {}
    for pcb in args.pcbs:
        try:
            res = run_correlation_study(pcb, args.config)
            results[pcb.name] = res
            print(f"  {pcb.name}: Steiner Error = {res['steiner_error']:.2f}x")
        except Exception as e:
            print(f"  Failed to analyze {pcb}: {e}")

    print("\nSummary:")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
