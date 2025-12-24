import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.thermal import ThermalLoss
from temper_placer.losses.types import ThermalConstraint
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.optimizer.train import train


def test_optimizer_returns_trace():
    """Verify that the optimizer returns a trace containing expected entries."""
    # 1. Setup simple board and netlist
    board = Board(width=100, height=100)
    components = [
        Component(ref="Q1", footprint="TO-247", bounds=(15, 20)),
        Component(ref="U1", footprint="SOIC-8", bounds=(5, 5)),
    ]
    netlist = Netlist(components=components, nets=[])

    # 2. Add thermal constraint with 'because'
    thermal_constraints = [
        ThermalConstraint(
            component_ref="Q1",
            edge="TOP",
            max_distance=5.0,
            weight=10.0,
            because="Q1 needs top-edge heatsink mounting"
        )
    ]

    # 3. Create context and composite loss
    context = LossContext.from_netlist_and_board(
        netlist, board,
        thermal_constraints=thermal_constraints
    )

    composite_loss = CompositeLoss([
        WeightedLoss(ThermalLoss(), weight=1.0)
    ])

    # 4. Run short optimization
    config = OptimizerConfig.fast_test()
    config.epochs = 50 # Enough to move towards edge

    result = train(netlist, board, composite_loss, context, config)

    # 5. Verify result
    assert result.trace is not None
    assert len(result.trace) > 0

    # Check if 'why' works for the constrained component
    explanation = result.trace.why("Q1")
    assert "Q1 needs top-edge heatsink mounting" in explanation
    print(f"\nExplanation for Q1:\n{explanation}")

if __name__ == "__main__":
    pytest.main([__file__])
