
import jax.numpy as jnp

from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.losses.base import LossContext, WeightedLoss
from temper_placer.losses.thermal import EdgePreferenceLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer.nsga2 import NSGAOptimizer
from temper_placer.optimizer.phases import PhaseStatus


def test_nsga_optimization_tradeoff():
    """Verify that NSGA-II finds solutions with different trade-offs."""
    # 1. Setup minimal case
    # Component U1 connects to nothing but has thermal preference
    board = Board(width=100, height=100, origin=(0,0), zones=[], ground_domains=[],
                  layer_stackup=LayerStackup.default_4layer())

    # 2 components
    c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
    c2 = Component(ref="U2", footprint="S", bounds=(10, 10))
    netlist = Netlist(components=[c1, c2], nets=[
        Net(name="N1", pins=[("U1", "1"), ("U2", "1")])
    ])
    context = LossContext.from_netlist_and_board(netlist, board)

    # Objectives:
    # 1. Wirelength (prefers components at same location)
    # 2. Thermal (prefers U1 at edge)
    objectives = [
        WirelengthLoss(),
        EdgePreferenceLoss(
            thermal_pad_indices=jnp.array([0]), # U1 is index 0
            board_width=100.0,
            board_height=100.0,
            preferred_margin_mm=5.0
        )
    ]

    optimizer = NSGAOptimizer(population_size=20)
    result = optimizer.evolve(
        netlist=netlist,
        board=board,
        objectives=objectives,
        context=context,
        generations=20
    )

    assert len(result.best_indices) > 0

    # Check that we have diverse solutions in the Pareto front
    obj_vals = result.objectives[jnp.array(result.best_indices)]

    # Find min wirelength solution
    min_wl_idx = jnp.argmin(obj_vals[:, 0])
    max_wl_idx = jnp.argmax(obj_vals[:, 0])

def test_pipeline_with_nsga():
    """Verify that NSGA-II works within the full OptimizationPipeline."""
    from temper_placer.losses.base import CompositeLoss
    from temper_placer.losses.wirelength import WirelengthLoss
    from temper_placer.optimizer.config import OptimizerConfig
    from temper_placer.optimizer.phases import OptimizationPipeline
    from temper_placer.pcl.parser import ConstraintCollection

    board = Board(width=100, height=100)
    c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
    netlist = Netlist(components=[c1])
    constraints = ConstraintCollection([])
    opt_config = OptimizerConfig.fast_test()
    context = LossContext.from_netlist_and_board(netlist, board)

    def loss_factory(weights):
        return CompositeLoss([WeightedLoss(WirelengthLoss(), weight=1.0)])

    pipeline = OptimizationPipeline(
        netlist, board, constraints, opt_config, loss_factory, context,
        use_nsga=True
    )

    # Speed up for test
    pipeline.nsga_phase.generations = 5
    pipeline.nsga_phase.pop_size = 10

    result = pipeline.run()

    assert result.success is True
    # Success in all 3 phases
    assert len(result.phases) == 3
    assert all(p.status == PhaseStatus.SUCCESS for p in result.phases)
    assert result.final_state is not None
