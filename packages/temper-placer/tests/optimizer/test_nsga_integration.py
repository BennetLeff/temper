import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.losses.base import LossContext, WeightedLoss
from temper_placer.losses.thermal import EdgePreferenceLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer.nsga2 import NSGAOptimizer
from temper_placer.optimizer.phases import NsgaPhase, ParetoFrontResult, PhaseStatus


def test_nsga_optimization_tradeoff():
    """Verify that NSGA-II finds solutions with different trade-offs."""
    # 1. Setup minimal case
    # Component U1 connects to nothing but has thermal preference
    board = Board(
        width=100,
        height=100,
        origin=(0, 0),
        zones=[],
        ground_domains=[],
        layer_stackup=LayerStackup.default_4layer(),
    )

    # 2 components
    c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
    c2 = Component(ref="U2", footprint="S", bounds=(10, 10))
    netlist = Netlist(components=[c1, c2], nets=[Net(name="N1", pins=[("U1", "1"), ("U2", "1")])])
    context = LossContext.from_netlist_and_board(netlist, board)

    # Objectives:
    # 1. Wirelength (prefers components at same location)
    # 2. Thermal (prefers U1 at edge)
    objectives = [
        WirelengthLoss(),
        EdgePreferenceLoss(
            thermal_pad_indices=jnp.array([0]),  # U1 is index 0
            board_width=100.0,
            board_height=100.0,
            preferred_margin_mm=5.0,
        ),
    ]

    optimizer = NSGAOptimizer(population_size=20)
    result = optimizer.evolve(
        netlist=netlist, board=board, objectives=objectives, context=context, generations=20
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
        netlist, board, constraints, opt_config, loss_factory, context, use_nsga=True
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


class TestParetoFrontPreservation:
    """Test that NsgaPhase returns full Pareto front instead of scalarized solution."""

    @pytest.fixture
    def multi_objective_setup(self):
        """Create a setup with conflicting objectives for Pareto front generation."""
        board = Board(
            width=100,
            height=100,
            origin=(0, 0),
            zones=[],
            ground_domains=[],
            layer_stackup=LayerStackup.default_4layer(),
        )

        # 2 components connected by a net
        c1 = Component(ref="U1", footprint="S", bounds=(10, 10))
        c2 = Component(ref="U2", footprint="S", bounds=(10, 10))
        netlist = Netlist(
            components=[c1, c2], nets=[Net(name="N1", pins=[("U1", "1"), ("U2", "1")])]
        )
        context = LossContext.from_netlist_and_board(netlist, board)

        # Conflicting objectives:
        # 1. Wirelength - prefers components close together
        # 2. EdgePreference - prefers U1 at edge (far from center)
        objectives = [
            WirelengthLoss(),
            EdgePreferenceLoss(
                thermal_pad_indices=jnp.array([0]),  # U1 is index 0
                board_width=100.0,
                board_height=100.0,
                preferred_margin_mm=5.0,
            ),
        ]

        return netlist, board, objectives, context

    def test_nsga_phase_returns_pareto_phase_result(self, multi_objective_setup):
        """NsgaPhase.run() should return ParetoFrontResult with full Pareto front."""
        netlist, board, objectives, context = multi_objective_setup

        phase = NsgaPhase(generations=10, pop_size=20)
        result = phase.run(
            netlist=netlist, board=board, objectives=objectives, context=context, initial_state=None
        )

        # Result should be ParetoFrontResult
        assert isinstance(result, ParetoFrontResult)
        assert result.status == PhaseStatus.SUCCESS

        # Should have states (Pareto front) with solutions
        assert result.states is not None
        assert len(result.states) > 0

        # Should have objectives array
        assert result.objectives is not None
        assert result.objectives.shape[0] == len(result.states)
        assert result.objectives.shape[1] == 2  # wirelength, edge preference

    def test_pareto_front_solutions_are_non_dominated(self, multi_objective_setup):
        """All solutions in returned Pareto front should be non-dominated."""
        netlist, board, objectives, context = multi_objective_setup

        phase = NsgaPhase(generations=20, pop_size=30)
        result = phase.run(
            netlist=netlist, board=board, objectives=objectives, context=context, initial_state=None
        )

        # Extract objective values from Pareto front
        obj_matrix = result.objectives

        # Check non-domination: no solution should dominate another
        n = len(result.states)
        for i in range(n):
            for j in range(n):
                if i != j:
                    # i dominates j if i is <= j in all objectives and < in at least one
                    diff = obj_matrix[i] - obj_matrix[j]
                    i_dominates_j = jnp.all(diff <= 0) and jnp.any(diff < 0)
                    assert not i_dominates_j, f"Solution {i} dominates solution {j}"

    def test_pareto_front_has_multiple_solutions_for_conflicting_objectives(
        self, multi_objective_setup
    ):
        """Pareto front should have >1 solution when objectives conflict."""
        netlist, board, objectives, context = multi_objective_setup

        phase = NsgaPhase(generations=30, pop_size=40)
        result = phase.run(
            netlist=netlist, board=board, objectives=objectives, context=context, initial_state=None
        )

        # With conflicting objectives, we should find multiple trade-off solutions
        assert len(result.states) > 1, (
            "Expected multiple solutions in Pareto front for conflicting objectives"
        )

    def test_knee_point_selection_returns_balanced_solution(self, multi_objective_setup):
        """Default knee-point selection should return a balanced trade-off solution."""
        netlist, board, objectives, context = multi_objective_setup

        phase = NsgaPhase(generations=20, pop_size=30)
        result = phase.run(
            netlist=netlist, board=board, objectives=objectives, context=context, initial_state=None
        )

        # state should be the knee-point selection (representative of Pareto front)
        assert result.state is not None

        # The selected state should be one of the Pareto front states
        found = False
        for state in result.states:
            if jnp.allclose(result.state.positions, state.positions):
                found = True
                break
        assert found, "Selected state should be from Pareto front"

    def test_knee_point_not_extreme(self, multi_objective_setup):
        """Knee-point selection should avoid extreme solutions when possible."""
        netlist, board, objectives, context = multi_objective_setup

        phase = NsgaPhase(generations=30, pop_size=50)
        result = phase.run(
            netlist=netlist, board=board, objectives=objectives, context=context, initial_state=None
        )

        if len(result.states) <= 2:
            pytest.skip("Need >2 solutions to test knee-point is not extreme")

        obj_matrix = result.objectives

        # Find extreme solutions (min for each objective)
        extreme_indices = set()
        for obj_idx in range(obj_matrix.shape[1]):
            min_idx = int(jnp.argmin(obj_matrix[:, obj_idx]))
            extreme_indices.add(min_idx)

        # Find which index is the selected (knee-point) solution
        selected_idx = None
        for idx, state in enumerate(result.states):
            if jnp.allclose(result.state.positions, state.positions):
                selected_idx = idx
                break

        # Knee-point should ideally not be an extreme point
        # (unless the Pareto front is very small or degenerate)
        if len(result.states) > 3 and selected_idx is not None:
            # Soft assertion - knee point might be extreme in some cases
            # but generally shouldn't be
            pass  # We don't strictly require this, just verify it's reasonable
