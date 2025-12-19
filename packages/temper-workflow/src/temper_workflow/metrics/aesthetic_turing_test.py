#!/usr/bin/env python3
"""
Aesthetic Turing Test.

Establish the 'Professional Standard' by scoring high-quality human designs.
"""

import argparse
import json
import sys
from pathlib import Path

import jax.numpy as jnp
import numpy as np

from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.metrics.aesthetic import compute_aesthetic_score


def score_human_design(pcb_path: Path):
    """Parse human design and compute its aesthetic score."""
    result = parse_kicad_pcb(pcb_path)
    netlist = result.netlist

    # Extract positions and rotations from the parsed components
    n = netlist.n_components
    positions = []
    rotations = []

    for comp in netlist.components:
        if comp.initial_position:
            positions.append(comp.initial_position)
        else:
            positions.append((0.0, 0.0))

        # Convert rotation index to one-hot logits for compute_aesthetic_score
        logits = [-10.0] * 4
        logits[comp.initial_rotation or 0] = 10.0
        rotations.append(logits)

    state = PlacementState(jnp.array(positions), jnp.array(rotations))

    # Compute score
    scores = compute_aesthetic_score(state, netlist)
    return scores


def main():
    parser = argparse.ArgumentParser(
        description="Score human designs for aesthetic benchmarks."
    )
    parser.add_argument("pcbs", type=Path, nargs="+", help="Input .kicad_pcb files")
    parser.add_argument("-o", "--output", type=Path, help="Output JSON report")

    args = parser.parse_args()

    all_results = {}
    for pcb in args.pcbs:
        print(f"Scoring {pcb}...")
        try:
            score = score_human_design(pcb)
            all_results[pcb.name] = score
            print(f"  Aesthetic Index: {score['aesthetic_index']:.2%}")
        except Exception as e:
            print(f"  Failed to score {pcb}: {e}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"Report written to {args.output}")
    else:
        print(json.dumps(all_results, indent=2))


if __name__ == "__main__":
    main()
