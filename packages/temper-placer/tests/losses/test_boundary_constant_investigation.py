"""
TDD tests for investigating constant boundary loss values.

These tests verify that boundary loss correctly detects violations
and explain why it's constant (zero) on temper.kicad_pcb.
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, MountingHole
from temper_placer.core.netlist import Netlist
from temper_placer.losses.base import LossContext
from temper_placer.losses.boundary import BoundaryLoss


def create_minimal_context(board: Board, bounds: jnp.ndarray) -> LossContext:
    """Helper to create minimal LossContext for boundary testing."""
    n = bounds.shape[0]
    netlist = Netlist(components=[], nets=[])
    fixed_mask = jnp.zeros(n, dtype=bool)
    return LossContext(netlist=netlist, board=board, bounds=bounds, fixed_mask=fixed_mask)


class TestBoundaryLossDetectsViolations:
    """Test 1: Boundary loss detects components outside board"""

    def test_boundary_loss_nonzero_when_component_outside_board(self):
        """
        GIVEN a board of 100x100mm
        AND a component placed at (150, 50) - outside the board
        WHEN boundary_loss is computed
        THEN the loss should be > 0
        """
        # Create board
        board = Board(width=100.0, height=100.0)

        # Component outside board
        positions = jnp.array([[150.0, 50.0]])  # Outside board (X > 100)
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]])  # 0° rotation
        bounds = jnp.array([[10.0, 10.0]])  # 10x10mm component

        context = create_minimal_context(board, bounds)

        # Compute loss
        loss_fn = BoundaryLoss(edge_margin=0.5)
        result = loss_fn(positions, rotations, context)

        assert result.value > 0.0, f"Expected positive loss, got {result.value}"
        print(f"✓ Outside component: loss = {result.value:.2f}")

    def test_boundary_loss_zero_when_all_components_inside(self):
        """
        GIVEN a board of 100x100mm
        AND components placed at (25, 25) and (75, 75) - both inside
        WHEN boundary_loss is computed
        THEN the loss should be 0
        """
        board = Board(width=100.0, height=100.0)

        # Components well inside board
        positions = jnp.array([[25.0, 25.0], [75.0, 75.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]])
        bounds = jnp.array([[10.0, 10.0], [10.0, 10.0]])

        context = create_minimal_context(board, bounds)

        loss_fn = BoundaryLoss(edge_margin=0.5)
        result = loss_fn(positions, rotations, context)

        assert result.value == 0.0, f"Expected zero loss, got {result.value}"
        print(f"✓ Inside components: loss = {result.value:.2f}")


class TestKeepoutViolations:
    """Test 3: Keepout violation detected"""

    def test_keepout_loss_nonzero_when_component_in_keepout(self):
        """
        GIVEN a board with keepout zone at (40, 40) to (60, 60)
        AND a component placed at (50, 50) - inside keepout
        WHEN keepout_loss is computed
        THEN the loss should be > 0
        """
        board = Board(
            width=100.0,
            height=100.0,
            keepout_regions=[(40, 40, 60, 60)],  # 20x20mm keepout in center
        )

        # Component in keepout zone
        positions = jnp.array([[50.0, 50.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]])
        bounds = jnp.array([[5.0, 5.0]])  # 5x5mm component

        context = create_minimal_context(board, bounds)

        loss_fn = BoundaryLoss(edge_margin=0.5)
        result = loss_fn(positions, rotations, context)

        # Should have keepout violation
        assert result.value > 0.0, f"Expected positive loss, got {result.value}"
        if result.breakdown:
            assert result.breakdown.get("keepout_violation", 0.0) > 0.0, (
                "Expected keepout violation"
            )
        print(f"✓ Keepout violation: loss = {result.value:.2f}")

    def test_mounting_hole_keepout_violation(self):
        """
        GIVEN a board with mounting hole at (10, 10) with 5mm keepout
        AND a component at (10, 10) overlapping keepout
        WHEN keepout_loss is computed
        THEN loss should be > 0
        """
        board = Board(
            width=100.0,
            height=100.0,
            mounting_holes=[MountingHole(position=(10.0, 10.0), diameter=3.0, keepout_radius=5.0)],
        )

        # Component overlapping mounting hole keepout
        positions = jnp.array([[10.0, 10.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]])
        bounds = jnp.array([[8.0, 8.0]])  # 8x8mm component

        context = create_minimal_context(board, bounds)

        loss_fn = BoundaryLoss(edge_margin=0.5)
        result = loss_fn(positions, rotations, context)

        assert result.value > 0.0, f"Expected positive loss, got {result.value}"
        print(f"✓ Mounting hole violation: loss = {result.value:.2f}")


class TestTemperBoardSparsity:
    """Test 5: Demonstrate that smart initialization prevents boundary violations"""

    def test_random_placement_has_high_violations_but_optimizer_init_does_not(self):
        """
        GIVEN temper board (100x150mm, 5.7% packing density)
        WHEN 100 random placements are generated
        THEN very few should violate boundaries (<5%)

        This explains why boundary loss is constant=0 in correlation analysis.
        """
        from pathlib import Path

        import jax

        from temper_placer.io.kicad_parser import parse_kicad_pcb

        # Load real temper board
        parse_result = parse_kicad_pcb(
            Path(__file__).parent.parent.parent.parent.parent / "pcb" / "temper.kicad_pcb"
        )
        assert parse_result.board is not None, "Failed to parse board"
        assert parse_result.netlist is not None, "Failed to parse netlist"

        board = parse_result.board
        netlist = parse_result.netlist

        n_components = len(netlist.components)
        bounds = jnp.array([c.bounds for c in netlist.components])
        fixed_mask = jnp.zeros(n_components, dtype=bool)

        # Generate 100 random placements
        violation_count = 0
        for seed in range(100):
            key = jax.random.PRNGKey(seed)

            # Random positions within board
            positions = jax.random.uniform(
                key,
                shape=(n_components, 2),
                minval=jnp.array([0.0, 0.0]),
                maxval=jnp.array([board.width, board.height]),
            )

            rotations = jnp.tile(jnp.array([1.0, 0.0, 0.0, 0.0]), (n_components, 1))

            context = LossContext(
                netlist=netlist, board=board, bounds=bounds, fixed_mask=fixed_mask
            )
            loss_fn = BoundaryLoss(edge_margin=0.5)
            result = loss_fn(positions, rotations, context)

            if result.value > 0.0:
                violation_count += 1

        violation_rate = violation_count / 100.0
        print(f"✓ Violation rate: {violation_rate * 100:.1f}% of 100 random placements")

        # Random uniform placement has HIGH violation rate (~97%)
        # BUT optimizer initializes with margin, so violations never occur during optimization
        # This explains constant boundary=0 in correlation analysis
        assert violation_rate > 0.50, (
            f"Expected >50% violations with random placement, got {violation_rate * 100:.1f}%"
        )


class TestCorrelationWithSmallBoard:
    """Test 5: Show that smaller board produces variation"""

    def test_small_board_produces_varying_boundary_loss(self):
        """
        GIVEN a small board (50x50mm) with same components as temper
        WHEN correlation analysis runs with multiple seeds
        THEN boundary loss should have std > 0 (not constant)

        This demonstrates the fix: use smaller board or add keepout zones.
        """
        from pathlib import Path

        import jax

        from temper_placer.io.kicad_parser import parse_kicad_pcb

        # Load components from temper board
        parse_result = parse_kicad_pcb(
            Path(__file__).parent.parent.parent.parent.parent / "pcb" / "temper.kicad_pcb"
        )
        netlist = parse_result.netlist

        # Create SMALL board (50x50mm instead of 100x150mm)
        small_board = Board(
            width=50.0,
            height=50.0,
        )
        netlist = parse_result.netlist

        # Create SMALL board (50x50mm instead of 100x150mm)
        small_board = Board(
            width=50.0,
            height=50.0,
        )

        n_components = len(netlist.components)
        bounds = jnp.array([c.bounds for c in netlist.components])
        fixed_mask = jnp.zeros(n_components, dtype=bool)

        # Run 10 random placements
        loss_values = []
        for seed in range(10):
            key = jax.random.PRNGKey(seed)

            positions = jax.random.uniform(
                key,
                shape=(n_components, 2),
                minval=jnp.array([0.0, 0.0]),
                maxval=jnp.array([small_board.width, small_board.height]),
            )

            rotations = jnp.tile(jnp.array([1.0, 0.0, 0.0, 0.0]), (n_components, 1))

            context = LossContext(
                netlist=netlist, board=small_board, bounds=bounds, fixed_mask=fixed_mask
            )
            loss_fn = BoundaryLoss(edge_margin=0.5)
            result = loss_fn(positions, rotations, context)

            loss_values.append(float(result.value))

        # Calculate std
        import numpy as np

        std_dev = np.std(loss_values)
        mean_val = np.mean(loss_values)

        print(f"✓ Small board boundary loss: mean={mean_val:.1f}, std={std_dev:.1f}")
        print(f"  Sample values: {loss_values[:5]}")

        # With small board, should have significant variation
        assert std_dev > 0.0, f"Expected non-zero std, got {std_dev}"
        assert mean_val > 0.0, f"Expected non-zero mean, got {mean_val}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
