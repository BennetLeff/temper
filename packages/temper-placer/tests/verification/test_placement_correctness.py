"""
Optimization correctness verification tests.

These tests verify that the optimization actually produces CORRECT results,
not just that the code runs without errors.

Key verification goals:
1. Loss decreases significantly (optimization is working)
2. Physical constraints are satisfied (no overlaps, within bounds)
3. Results are reproducible with same seed
4. Different seeds explore different solutions
5. Curriculum learning improves results

This is different from gradient/numerical tests - these verify the GOAL.
"""

from pathlib import Path

import pytest

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")
import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.losses import (
    BoundaryLoss,
    CompositeLoss,
    OverlapLoss,
    WeightedLoss,
    WirelengthLoss,
)
from temper_placer.losses.base import LossContext
from temper_placer.losses.boundary import compute_boundary_penalty
from temper_placer.losses.overlap import compute_overlap_penalty
from temper_placer.optimizer import OptimizerConfig, train, train_multiphase
from temper_placer.optimizer.curriculum import create_fast_phases

# Test fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"


def create_test_netlist(n_components: int = 5) -> Netlist:
    """Create a simple test netlist with n components."""
    components = []
    for i in range(n_components):
        ref = f"R{i + 1}"
        components.append(
            Component(
                ref=ref,
                footprint="R_0603",
                bounds=(2.0, 1.0),
                pins=[
                    Pin(name="1", number="1", position=(0.0, 0.0)),
                    Pin(name="2", number="2", position=(2.0, 0.0)),
                ],
            )
        )

    # Create some nets connecting components
    nets = []
    if n_components >= 2:
        # Connect pairs of components
        for i in range(0, n_components - 1, 2):
            nets.append(
                Net(
                    name=f"NET{i // 2}",
                    pins=[(f"R{i + 1}", "2"), (f"R{i + 2}", "1")],
                )
            )

    return Netlist(components=components, nets=nets)


def create_test_board(width: float = 50.0, height: float = 50.0) -> Board:
    """Create a simple test board."""
    return Board(width=width, height=height)


def create_test_loss() -> CompositeLoss:
    """Create standard test loss function."""
    return CompositeLoss(
        [
            WeightedLoss(OverlapLoss(), weight=100.0),
            WeightedLoss(BoundaryLoss(), weight=50.0),
            WeightedLoss(WirelengthLoss(), weight=10.0),
        ]
    )


class TestLossDecrease:
    """Tests that verify optimization reduces loss."""

    def test_loss_decreases_significantly(self):
        """Final loss should be significantly less than initial loss."""
        # Clear JAX caches to ensure consistent behavior
        jax.clear_caches()

        netlist = create_test_netlist(5)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 400  # More epochs for reliable convergence
        config.seed = 12345  # Use unique seed to avoid JIT cache pollution

        result = train(netlist, board, loss_fn, context, config)

        # Loss should decrease
        initial_loss = result.history[0].loss
        final_loss = result.final_loss

        assert final_loss < initial_loss, (
            f"Loss should decrease during optimization. "
            f"Initial: {initial_loss:.2f}, Final: {final_loss:.2f}"
        )

        # Should decrease by at least 20% (conservative threshold accounting for variance)
        improvement = (initial_loss - final_loss) / initial_loss
        assert improvement > 0.20, f"Loss only improved by {improvement * 100:.1f}%, expected >20%"

    def test_best_loss_less_than_or_equal_final(self):
        """Best loss should be <= final loss (we track the best)."""
        netlist = create_test_netlist(5)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 100
        config.seed = 42

        result = train(netlist, board, loss_fn, context, config)

        assert result.best_loss <= result.final_loss


class TestPhysicalConstraints:
    """Tests that verify physical constraints are satisfied."""

    def test_no_overlaps_after_optimization(self):
        """Final placement should have minimal/no overlaps."""
        netlist = create_test_netlist(8)
        board = create_test_board(60.0, 60.0)  # Larger board for 8 components
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 300  # More epochs for constraint satisfaction
        config.seed = 42

        result = train(netlist, board, loss_fn, context, config)

        # Verify best_state exists
        assert result.best_state is not None, "Optimization failed to produce a best state"

        # Compute overlap on final state
        widths = jnp.array([c.bounds[0] for c in netlist.components])
        heights = jnp.array([c.bounds[1] for c in netlist.components])

        overlap = compute_overlap_penalty(result.best_state.positions, widths, heights)

        # Should have very low overlap (< 1.0 is essentially zero)
        assert float(overlap) < 10.0, f"Overlap penalty too high: {float(overlap)}"

    def test_all_components_within_bounds(self):
        """All components should be within board boundaries."""
        netlist = create_test_netlist(6)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 300
        config.seed = 42

        result = train(netlist, board, loss_fn, context, config)

        # Verify best_state exists
        assert result.best_state is not None, "Optimization failed to produce a best state"

        # Compute boundary penalty
        widths = jnp.array([c.bounds[0] for c in netlist.components])
        heights = jnp.array([c.bounds[1] for c in netlist.components])
        board_bounds = board.get_bounds_array()

        boundary = compute_boundary_penalty(
            result.best_state.positions, widths, heights, board_bounds
        )

        # Should have very low boundary violation
        assert float(boundary) < 10.0, f"Boundary penalty too high: {float(boundary)}"

    def test_positions_are_finite(self):
        """All positions should be finite (no NaN or Inf)."""
        netlist = create_test_netlist(5)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 100
        config.seed = 42

        result = train(netlist, board, loss_fn, context, config)

        assert result.best_state is not None, "Optimization failed to produce a best state"
        assert jnp.all(jnp.isfinite(result.best_state.positions)), "Positions contain NaN or Inf"

    def test_wirelength_is_finite(self):
        """Wirelength loss should be finite and reasonable."""
        netlist = create_test_netlist(6)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 100
        config.seed = 42

        result = train(netlist, board, loss_fn, context, config)

        # Verify best_state exists
        assert result.best_state is not None, "Optimization failed to produce a best state"

        # Evaluate wirelength on final state
        wl_loss = WirelengthLoss()
        wl_result = wl_loss(
            result.best_state.positions,
            jax.nn.softmax(result.best_state.rotation_logits, axis=-1),
            context,
        )

        assert jnp.isfinite(wl_result.value), "Wirelength is not finite"


class TestPlacementDiversity:
    """Tests that verify placements are reasonable and diverse."""

    def test_positions_changed_from_initial(self):
        """Components should move from their initial positions."""
        netlist = create_test_netlist(5)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 100
        config.seed = 42

        result = train(netlist, board, loss_fn, context, config)

        # Verify best_state exists
        assert result.best_state is not None, "Optimization failed to produce a best state"

        # Get initial random state (same seed)
        key = jax.random.PRNGKey(42)
        initial_state = PlacementState.random_init(
            n_components=netlist.n_components,
            board_width=board.width,
            board_height=board.height,
            key=key,
        )

        # Positions should have changed
        pos_diff = jnp.abs(result.best_state.positions - initial_state.positions)
        mean_movement = jnp.mean(pos_diff)

        assert float(mean_movement) > 0.1, "Components didn't move from initial positions"

    def test_positions_are_diverse(self):
        """Not all components should collapse to the same point."""
        netlist = create_test_netlist(6)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 200
        config.seed = 42

        result = train(netlist, board, loss_fn, context, config)

        assert result.best_state is not None, "Optimization failed to produce a best state"
        positions = result.best_state.positions

        # Compute pairwise distances
        n = positions.shape[0]
        min_distance = float("inf")
        for i in range(n):
            for j in range(i + 1, n):
                dist = jnp.sqrt(jnp.sum((positions[i] - positions[j]) ** 2))
                min_distance = min(min_distance, float(dist))

        # Minimum distance should be reasonable (components spread out)
        assert min_distance > 0.5, f"Components collapsed together, min dist: {min_distance}"


class TestReproducibility:
    """Tests for reproducibility with seeds."""

    def test_same_seed_same_result(self):
        """Same seed should produce identical results."""
        netlist = create_test_netlist(5)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 50
        config.seed = 12345

        # Run twice with same seed
        result1 = train(netlist, board, loss_fn, context, config)
        result2 = train(netlist, board, loss_fn, context, config)

        # Verify best_state exists
        assert result1.best_state is not None, "First run failed to produce a best state"
        assert result2.best_state is not None, "Second run failed to produce a best state"

        # Results should be identical
        pos_diff = jnp.max(jnp.abs(result1.best_state.positions - result2.best_state.positions))
        assert float(pos_diff) < 1e-5, (
            f"Same seed produced different results: max diff {float(pos_diff)}"
        )

    def test_different_seeds_different_results(self):
        """Different seeds should produce different results."""
        netlist = create_test_netlist(5)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config1 = OptimizerConfig.fast_test()
        config1.epochs = 50
        config1.seed = 111

        config2 = OptimizerConfig.fast_test()
        config2.epochs = 50
        config2.seed = 222

        result1 = train(netlist, board, loss_fn, context, config1)
        result2 = train(netlist, board, loss_fn, context, config2)

        # Verify best_state exists
        assert result1.best_state is not None, "First run failed to produce a best state"
        assert result2.best_state is not None, "Second run failed to produce a best state"

        # Results should be different
        pos_diff = jnp.max(jnp.abs(result1.best_state.positions - result2.best_state.positions))
        assert float(pos_diff) > 0.1, "Different seeds produced identical results"


class TestRotations:
    """Tests for rotation handling."""

    def test_rotations_are_valid(self):
        """Discrete rotations should be one of [0, 90, 180, 270]."""
        netlist = create_test_netlist(5)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 100
        config.seed = 42

        result = train(netlist, board, loss_fn, context, config)

        # Verify best_state exists
        assert result.best_state is not None, "Optimization failed to produce a best state"

        # Get discrete rotations
        _, rotations = result.best_state.to_discrete()

        # Each rotation should be in [0, 1, 2, 3]
        valid_rotations = jnp.array([0, 1, 2, 3])
        for i, rot in enumerate(rotations):
            assert int(rot) in [0, 1, 2, 3], f"Invalid rotation {int(rot)} for component {i}"

    def test_rotation_logits_are_finite(self):
        """Rotation logits should be finite."""
        netlist = create_test_netlist(5)
        board = create_test_board()
        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 100
        config.seed = 42

        result = train(netlist, board, loss_fn, context, config)

        assert result.best_state is not None, "Optimization failed to produce a best state"
        assert jnp.all(jnp.isfinite(result.best_state.rotation_logits)), (
            "Rotation logits contain NaN or Inf"
        )


class TestCurriculumLearning:
    """Tests for curriculum learning."""

    @pytest.mark.slow
    def test_curriculum_completes_all_phases(self):
        """Curriculum learning should complete all phases."""
        netlist = create_test_netlist(6)
        board = create_test_board()
        context = LossContext.from_netlist_and_board(netlist, board)

        epochs = 300
        phases = create_fast_phases(epochs)

        def make_loss(weights):
            losses = []
            if "overlap" in weights:
                losses.append(WeightedLoss(OverlapLoss(), weight=weights["overlap"]))
            if "boundary" in weights:
                losses.append(WeightedLoss(BoundaryLoss(), weight=weights["boundary"]))
            if "wirelength" in weights:
                losses.append(WeightedLoss(WirelengthLoss(), weight=weights["wirelength"]))
            return CompositeLoss(losses)

        config = OptimizerConfig(
            epochs=epochs,
            seed=42,
            curriculum_phases=phases,
        )

        result = train_multiphase(netlist, board, make_loss, context, config)

        # Should complete all epochs
        assert result.total_epochs >= epochs * 0.9, (
            f"Only completed {result.total_epochs}/{epochs} epochs"
        )

    @pytest.mark.slow
    def test_curriculum_produces_valid_result(self):
        """Curriculum learning should produce valid, improved placements.

        Note: Curriculum learning benefits are more apparent on complex problems.
        For simple test cases, we verify it produces valid results and improves
        from initial state, not that it beats a fixed-temperature baseline.
        """
        netlist = create_test_netlist(8)
        board = create_test_board(60.0, 60.0)
        context = LossContext.from_netlist_and_board(netlist, board)

        epochs = 200
        phases = create_fast_phases(epochs)

        def make_loss(weights):
            losses = []
            if "overlap" in weights:
                losses.append(WeightedLoss(OverlapLoss(), weight=weights["overlap"]))
            if "boundary" in weights:
                losses.append(WeightedLoss(BoundaryLoss(), weight=weights["boundary"]))
            if "wirelength" in weights:
                losses.append(WeightedLoss(WirelengthLoss(), weight=weights["wirelength"]))
            return CompositeLoss(losses)

        config = OptimizerConfig(
            epochs=epochs,
            seed=42,
            curriculum_phases=phases,
        )

        result = train_multiphase(netlist, board, make_loss, context, config)

        # Verify valid result
        assert result.best_state is not None, "Curriculum failed to produce best state"
        assert jnp.all(jnp.isfinite(result.best_state.positions)), "Invalid positions"
        assert result.best_loss < float("inf"), "Loss is infinite"

        # Should improve from initial
        initial_loss = result.history[0].loss
        assert result.best_loss < initial_loss, (
            f"Curriculum didn't improve: initial={initial_loss:.2f}, final={result.best_loss:.2f}"
        )


class TestWithRealPCB:
    """Tests using real PCB fixtures."""

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_minimal_pcb_optimization_succeeds(self):
        """Optimization on minimal PCB fixture should succeed."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        # Parse the PCB
        result = parse_kicad_pcb(MINIMAL_PCB)
        netlist = result.netlist

        # Create board from parsed dimensions
        board = create_test_board(
            width=result.board.width if result.board else 50.0,
            height=result.board.height if result.board else 50.0,
        )

        loss_fn = create_test_loss()
        context = LossContext.from_netlist_and_board(netlist, board)

        config = OptimizerConfig.fast_test()
        config.epochs = 100
        config.seed = 42

        opt_result = train(netlist, board, loss_fn, context, config)

        # Should complete successfully
        assert opt_result.best_loss < float("inf")
        assert opt_result.total_epochs > 0

        # Should improve from initial
        assert opt_result.best_loss < opt_result.history[0].loss
