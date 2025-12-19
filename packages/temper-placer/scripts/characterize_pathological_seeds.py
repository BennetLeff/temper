#!/usr/bin/env python3
"""
Characterize pathological seeds (temper-1my.4.3).

Identifies seeds that caused optimization failure and analyzes their
initial conditions to identify patterns.
"""

from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np
import pandas as pd
import yaml

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import WirelengthLoss


def compute_clustering_coefficient(positions: jnp.ndarray) -> float:
    """
    Compute a simple spatial clustering coefficient.
    Inverse of average distance to nearest neighbor.
    Higher = more clustered.
    """
    n = positions.shape[0]
    if n < 2: return 0.0

    # Compute pairwise distances
    diff = positions[:, None, :] - positions[None, :, :]
    dist = jnp.sqrt(jnp.sum(diff**2, axis=-1))

    # Fill diagonal with large value to ignore self-distance
    dist = dist + jnp.eye(n) * 1e6

    # Min distance for each component
    min_dist = jnp.min(dist, axis=1)

    # Average inverse distance (to highlight tight clusters)
    return float(jnp.mean(1.0 / (min_dist + 1.0)))

def analyze_init(seed: int, netlist: Netlist, board: Board, context: LossContext) -> dict[str, float]:
    """Analyze initial conditions for a given seed."""
    key = jax.random.PRNGKey(seed)
    state = PlacementState.random_init(
        n_components=netlist.n_components,
        board_width=board.width,
        board_height=board.height,
        key=key,
        origin=board.origin
    )

    positions = state.positions
    # Uniform rotations for initial analysis
    rotations = jnp.eye(4)[jnp.zeros(netlist.n_components, dtype=jnp.int32)]

    overlap_loss = OverlapLoss()
    boundary_loss = BoundaryLoss()
    wirelength_loss = WirelengthLoss()

    return {
        "init_overlap": float(overlap_loss(positions, rotations, context).value),
        "init_boundary": float(boundary_loss(positions, rotations, context).value),
        "init_clustering": compute_clustering_coefficient(positions),
        "init_wirelength": float(wirelength_loss(positions, rotations, context).value),
    }

def main():
    results_path = Path("tests/sensitivity/results/seed_analysis.csv")
    if not results_path.exists():
        print(f"Error: {results_path} not found.")
        return

    df = pd.read_csv(results_path)
    print(f"Total seeds: {len(df)}")

    # Recreate netlist and board used in test_seed_sensitivity.py
    import importlib.util
    fixtures_path = Path("tests/fixtures/generators/synthetic_netlist.py")
    spec = importlib.util.spec_from_file_location("synthetic_netlist", fixtures_path)
    synthetic_netlist = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(synthetic_netlist)

    netlist = synthetic_netlist.generate_netlist(n_components=17, seed=12345)
    board = Board(width=100.0, height=100.0)
    context = LossContext.from_netlist_and_board(netlist, board)

    # Analyze initial conditions for all seeds to correlate
    all_init_metrics = []
    for seed in df['seed']:
        metrics = analyze_init(int(seed), netlist, board, context)
        all_init_metrics.append(metrics)

    init_df = pd.DataFrame(all_init_metrics)
    full_df = pd.concat([df, init_df], axis=1)

    # Identify pathological seeds
    median_loss = df['final_loss'].median()
    median_wl = df['wirelength'].median()

    # Define pathological:
    # 1. Hard constraint violation: overlap > 1.0 OR boundary > 1.0
    # 2. Severe quality degradation: wirelength > 1.5x median
    # 3. Severe loss outlier: loss > 1.5x median
    pathological_full = full_df[
        (full_df['overlap_penalty'] > 1.0) |
        (full_df['boundary_penalty'] > 1.0) |
        (full_df['wirelength'] > 1.5 * median_wl) |
        (full_df['final_loss'] > 1.5 * median_loss)
    ].copy()

    print(f"Pathological seeds: {len(pathological_full)}")

    def categorize_failure(row):
        if row['overlap_penalty'] > 1.0:
            if row['init_clustering'] > full_df['init_clustering'].mean():
                return "cluster_trap"
            else:
                return "overlap_deadlock"
        if row['boundary_penalty'] > 1.0:
            return "boundary_escape"
        if row['wirelength'] > 1.5 * median_wl:
            return "connectivity_split"
        return "other"

    if not pathological_full.empty:
        pathological_full['failure_type'] = pathological_full.apply(categorize_failure, axis=1)

    # Compute correlations
    def safe_corr(a, b):
        if np.std(a) == 0 or np.std(b) == 0:
            return 0.0
        return float(np.corrcoef(a, b)[0, 1])

    correlations = {
        "init_overlap_vs_final_overlap": safe_corr(full_df['init_overlap'], full_df['overlap_penalty']),
        "init_clustering_vs_final_loss": safe_corr(full_df['init_clustering'], full_df['final_loss']),
        "init_boundary_vs_final_boundary": safe_corr(full_df['init_boundary'], full_df['boundary_penalty']),
    }

    # Generate report
    report = {
        "total_seeds_tested": len(df),
        "pathological_count": len(pathological_full),
        "pathological_rate": float(len(pathological_full) / len(df)),
        "failure_patterns": pathological_full['failure_type'].value_counts().to_dict() if not pathological_full.empty else {},
        "correlations": correlations,
        "worst_seeds": pathological_full.sort_values(by='final_loss', ascending=False).head(10)[
            ['seed', 'failure_type', 'init_overlap', 'overlap_penalty', 'final_loss']
        ].to_dict(orient='records') if not pathological_full.empty else []
    }

    output_path = Path("pathological_seeds_report.yaml")
    with open(output_path, "w") as f:
        yaml.dump(report, f, default_flow_style=False, sort_keys=False)

    print(f"Report saved to {output_path}")
    if not pathological_full.empty:
        print("\nSummary:")
        print(f"  Pathological rate: {report['pathological_rate']:.1%}")
        print("  Failure patterns:")
        for pattern, count in report['failure_patterns'].items():
            print(f"    - {pattern}: {count}")

if __name__ == "__main__":
    main()
