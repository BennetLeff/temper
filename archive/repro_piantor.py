
import jax
import jax.numpy as jnp
import pytest
import numpy as np
from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses import (
    BoundaryLoss,
    CompositeLoss,
    LossContext,
    OverlapLoss,
    WeightedLoss,
    WirelengthLoss,
)
from temper_placer.optimizer import InitializationConfig, OptimizerConfig, train
from temper_placer.optimizer.config import LearningRateSchedule
from temper_placer.optimizer.legalization import project_to_drc_feasible
from tests.fixtures.external import get_pcb_path

def calculate_metrics(netlist, board, state):
    context = LossContext.from_netlist_and_board(netlist, board)
    positions = state.positions
    rotations = jax.nn.softmax(state.rotation_logits)
    wl_loss = WirelengthLoss()(positions, rotations, context)
    overlap_loss = OverlapLoss()(positions, rotations, context)
    boundary_loss = BoundaryLoss()(positions, rotations, context)
    return {
        "wirelength": float(wl_loss.value),
        "overlap": float(overlap_loss.value),
        "boundary": float(boundary_loss.value),
    }

def run_test():
    project_name = "piantor_right"
    pcb_path = get_pcb_path(project_name)
    if not pcb_path:
        print("PCB not found")
        return

    result = parse_kicad_pcb(pcb_path)
    netlist = result.netlist
    board = result.board

    print(f"Running optimization for {project_name}")

    # Same config as the test
    composite_loss = CompositeLoss(
        [
            WeightedLoss(OverlapLoss(), weight=5000.0),
            WeightedLoss(BoundaryLoss(edge_margin=0.5), weight=5000.0),
            WeightedLoss(WirelengthLoss(), weight=10.0),
        ]
    )

    context = LossContext.from_netlist_and_board(netlist, board)
    config = OptimizerConfig(
        epochs=1000, # Reduced for speed in reproduction
        seed=42,
        initialization=InitializationConfig(method="spectral"),
        learning_rate=LearningRateSchedule(initial=0.1, final=0.001),
    )

    opt_result = train(
        netlist=netlist,
        board=board,
        composite_loss=composite_loss,
        context=context,
        config=config,
    )

    metrics_before = calculate_metrics(netlist, board, opt_result.final_state)
    print(f"Metrics BEFORE legalization:")
    print(f"  Overlap:  {metrics_before['overlap']:.4f}")
    print(f"  Boundary: {metrics_before['boundary']:.4f}")

    # Apply Legalization
    print("Applying legalization...")
    legalized_state = project_to_drc_feasible(
        opt_result.final_state,
        context,
        margin_mm=0.2, # Slightly looser margin for success? or stricter? 
        max_iterations=1000 # Give it plenty of time
    )

    metrics_after = calculate_metrics(netlist, board, legalized_state)
    print(f"Metrics AFTER legalization:")
    print(f"  Overlap:  {metrics_after['overlap']:.4f}")
    print(f"  Boundary: {metrics_after['boundary']:.4f}")

if __name__ == "__main__":
    run_test()
