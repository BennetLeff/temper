from pathlib import Path
import jax.numpy as jnp
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
from temper_placer.visualization import render_board, create_board_view_from_state, board_to_html
from tests.fixtures.external import get_pcb_path

project_name = "piantor_right"
pcb_path = get_pcb_path(project_name)
result = parse_kicad_pcb(pcb_path)
netlist, board = result.netlist, result.board

# Run Optimizer with settings from test_wirelength_within_tolerance
composite_loss = CompositeLoss([
    WeightedLoss(OverlapLoss(), weight=5000.0),
    WeightedLoss(BoundaryLoss(), weight=5000.0),
    WeightedLoss(WirelengthLoss(), weight=10.0),
])

context = LossContext.from_netlist_and_board(netlist, board)
config = OptimizerConfig(
    epochs=2000,
    seed=42,
    initialization=InitializationConfig(method="spectral"),
    learning_rate=LearningRateSchedule(initial=0.1, final=0.01),
)

opt_result = train(
    netlist=netlist,
    board=board,
    composite_loss=composite_loss,
    context=context,
    config=config,
)

# Render result
board_view = create_board_view_from_state(board, netlist, opt_result.final_state)
fig = render_board(board_view)
fig.write_html("piantor_right_debug.html")

print(f"Final Loss: {opt_result.final_loss:.4f}")
print(f"Total Epochs: {opt_result.total_epochs}")
