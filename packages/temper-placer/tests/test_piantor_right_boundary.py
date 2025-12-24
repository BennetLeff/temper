import jax

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
from temper_placer.visualization import create_board_view_from_state, render_board
from tests.fixtures.external import get_pcb_path


def test_debug_piantor_right_convergence():
    """Debug test to investigate piantor_right convergence issues."""
    project_name = "piantor_right"
    pcb_path = get_pcb_path(project_name)
    result = parse_kicad_pcb(pcb_path)
    netlist, board = result.netlist, result.board

    # Use settings from the failing test
    composite_loss = CompositeLoss([
        WeightedLoss(OverlapLoss(), weight=5000.0),
        WeightedLoss(BoundaryLoss(), weight=5000.0),
        WeightedLoss(WirelengthLoss(), weight=10.0),
    ])

    context = LossContext.from_netlist_and_board(netlist, board)
    config = OptimizerConfig(
        epochs=4000, # Try more epochs
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

    # Calculate final metrics
    positions = opt_result.final_state.positions
    rotations = jax.nn.softmax(opt_result.final_state.rotation_logits)

    wl = WirelengthLoss()(positions, rotations, context).value
    overlap = OverlapLoss()(positions, rotations, context).value
    boundary = BoundaryLoss()(positions, rotations, context).value

    print("\nPiantor Right Final Metrics (4000 epochs):")
    print(f"  Wirelength: {wl:.4f}")
    print(f"  Overlap:    {overlap:.4f}")
    print(f"  Boundary:   {boundary:.4f}")

    # Render result to file
    board_view = create_board_view_from_state(board, netlist, opt_result.final_state)
    fig = render_board(board_view)
    fig.write_html("piantor_right_debug_4000.html")

    # Assert nothing, just for debugging
