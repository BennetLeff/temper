
import time
from pathlib import Path

import jax.numpy as jnp

from temper_placer.io.config_loader import PlacementConstraints, create_board_from_constraints
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses import (
    BoundaryLoss,
    CompositeLoss,
    OverlapLoss,
    WeightedLoss,
    WirelengthLoss,
)
from temper_placer.losses.base import LossContext
from temper_placer.optimizer import OptimizerConfig, train


def run_experiment(pcb_path, use_centrality):
    # Parse PCB
    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist

    # Create dummy constraints/board
    constraints = PlacementConstraints()
    board = create_board_from_constraints(constraints)
    # Match large_board dimensions from info output
    board.width = 100.0
    board.height = 150.0
    board.origin = (5.0, 5.0)

    # Create context
    context = LossContext.from_netlist_and_board(
        netlist, board, use_centrality_weighting=use_centrality
    )

    # Define losses
    losses = [
        WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True), weight=100.0),
        WeightedLoss(BoundaryLoss(), weight=50.0),
        WeightedLoss(WirelengthLoss(), weight=10.0),
    ]
    composite_loss = CompositeLoss(losses)

    # Config
    cfg = OptimizerConfig(
        epochs=1000,  # Enough to see convergence trends
        seed=42,
        use_centrality_weighting=use_centrality,
        log_interval=50
    )

    # Run optimization
    start_time = time.time()
    result = train(netlist, board, composite_loss, context, cfg)
    elapsed = time.time() - start_time

    return result, context, elapsed

def main():
    pcb_path = Path("tests/fixtures/large_board.kicad_pcb")

    print(f"Analyzing centrality impact on {pcb_path.name}...")

    # 1. Baseline (no centrality)
    print("\nRunning Baseline (no centrality)...")
    res_base, ctx_base, time_base = run_experiment(pcb_path, False)
    print(f"Baseline: Final Loss = {res_base.final_loss:.4f}, Time = {time_base:.2f}s")

    # 2. Centrality Enabled
    print("\nRunning Centrality-Driven Optimization...")
    res_cent, ctx_cent, time_cent = run_experiment(pcb_path, True)
    print(f"Centrality: Final Loss = {res_cent.final_loss:.4f}, Time = {time_cent:.2f}s")

    # Analyze Hub Stability
    # Find hub components (highest centrality)
    adj = ctx_cent.centrality # wait, centrality is in LossContext
    centrality = res_cent.final_state.positions # No, centrality is in context

    centrality = ctx_cent.centrality
    hub_indices = jnp.argsort(centrality)[-5:] # Top 5 hubs

    print("\nTop 5 Hub Components stability:")
    for idx in hub_indices:
        ref = ctx_cent.netlist.components[int(idx)].ref
        c_val = float(centrality[idx])

        # Compare movement/final position
        pos_base = res_base.final_state.positions[idx]
        pos_cent = res_cent.final_state.positions[idx]

        print(f"  {ref} (c={c_val:.4f}): Base Pos={pos_base}, Cent Pos={pos_cent}")

    # Compare convergence curves
    print("\nConvergence Trends:")
    print(f"  Epoch 500 Loss: Base={res_base.history[10].loss:.2f}, Cent={res_cent.history[10].loss:.2f}")

    # Analysis Report
    improvement = (res_base.final_loss - res_cent.final_loss) / res_base.final_loss * 100
    print("\nFinal Analysis:")
    print(f"  Loss Improvement: {improvement:.2f}%")

    if improvement > 0:
        print("  Status: Centrality improved global convergence.")
    else:
        print("  Status: Centrality did not significantly improve global loss (may be better for hubs).")

if __name__ == "__main__":
    main()
