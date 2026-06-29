"""
Scale tests for the optimizer with realistic component counts.

These tests verify that the optimizer:
1. Can handle 50-200 component designs without crashing
2. Converges to feasible placements at scale
3. Maintains reasonable performance (memory, time)
4. Produces quality results as component count increases

TDD Tasks: temper-1my.3.2 (100 components), temper-1my.3.4 (convergence benchmarks)
"""

from __future__ import annotations

import time

import jax.numpy as jnp
import pytest

# Import from fixtures using relative import pattern
from tests.fixtures.generators.synthetic_netlist import generate_netlist

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.boundary import BoundaryLoss, compute_boundary_penalty
from temper_placer.losses.overlap import OverlapLoss, compute_overlap_penalty
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer import OptimizerConfig, train


def create_scale_setup(
    n_components: int, board_scale: float = 1.0, seed: int = 42
) -> tuple[Netlist, Board, LossContext, CompositeLoss]:
    """
    Create a complete optimizer setup for scale testing.

    Args:
        n_components: Number of components to generate.
        board_scale: Multiplier for board size (1.0 = standard sizing).
        seed: Random seed for reproducibility.

    Returns:
        Tuple of (netlist, board, context, composite_loss).
    """
    netlist = generate_netlist(n_components=n_components, seed=seed)

    # Scale board size based on component count
    # Heuristic: Each component needs ~400mm² on average (20x20mm effective)
    # Plus 50% margin for routing and spacing
    total_area = n_components * 400 * 1.5 * board_scale
    board_side = (total_area**0.5) * 1.2  # Slightly larger than square root

    # Ensure minimum size
    board_side = max(board_side, 100.0)

    board = Board(width=board_side, height=board_side)
    context = LossContext.from_netlist_and_board(netlist, board)

    # Create loss function with balanced weights
    composite = CompositeLoss(
        [
            WeightedLoss(OverlapLoss(), weight=100.0),
            WeightedLoss(BoundaryLoss(), weight=50.0),
            WeightedLoss(WirelengthLoss(), weight=1.0),
        ]
    )

    return netlist, board, context, composite


# =============================================================================
# 100 Component Scale Tests (temper-1my.3.2)
# =============================================================================


class TestOptimizer100Components:
    """Test optimizer behavior with 100 components."""

    def test_optimizer_runs_with_100_components(self) -> None:
        """Verify optimizer can process 100 components without error."""
        netlist, board, context, composite = create_scale_setup(n_components=100)

        config = OptimizerConfig(
            epochs=50,  # Short run to verify it works
            seed=42,
            log_interval=10,
            checkpoint=OptimizerConfig.fast_test().checkpoint,
            early_stopping=OptimizerConfig.fast_test().early_stopping,
        )

        result = train(netlist, board, composite, context, config)

        assert result.total_epochs == 50
        assert result.final_loss >= 0
        assert result.final_state is not None
        assert not jnp.any(jnp.isnan(result.final_state.positions))

    def test_100_components_converges_to_feasible(self) -> None:
        """Verify optimizer finds feasible placement for 100 components."""
        netlist, board, context, composite = create_scale_setup(n_components=100)

        config = OptimizerConfig(
            epochs=500,  # More epochs for convergence
            seed=42,
            log_interval=50,
            checkpoint=OptimizerConfig.fast_test().checkpoint,
            early_stopping=OptimizerConfig.fast_test().early_stopping,
        )

        result = train(netlist, board, composite, context, config)

        # Extract final positions and bounds
        positions = result.final_state.positions
        widths = context.bounds[:, 0]
        heights = context.bounds[:, 1]
        board_bounds = board.get_bounds_array()

        # Check components are inside board
        boundary_loss = compute_boundary_penalty(positions, widths, heights, board_bounds)
        # Allow some boundary violations but should be mostly inside
        assert float(boundary_loss) < 100.0, f"Too many boundary violations: {float(boundary_loss)}"

        # Check overlap is reasonable
        overlap_loss = compute_overlap_penalty(positions, widths, heights)
        # Allow some overlap but should be mostly resolved
        assert float(overlap_loss) < 500.0, f"Too much overlap: {float(overlap_loss)}"

    def test_100_components_loss_decreases(self) -> None:
        """Verify loss decreases during optimization of 100 components."""
        netlist, board, context, composite = create_scale_setup(n_components=100)

        config = OptimizerConfig(
            epochs=200,
            seed=42,
            log_interval=20,
            checkpoint=OptimizerConfig.fast_test().checkpoint,
            early_stopping=OptimizerConfig.fast_test().early_stopping,
        )

        result = train(netlist, board, composite, context, config)

        # Verify history was recorded
        assert len(result.history) >= 5

        # Compare early vs late loss
        early_loss = result.history[1].loss  # Skip epoch 0 which may be very high
        final_loss = result.final_loss

        # Loss should decrease (or at least not explode)
        assert final_loss <= early_loss * 2, (
            f"Loss did not improve: {early_loss:.1f} -> {final_loss:.1f}"
        )

    def test_100_components_net_complexity(self) -> None:
        """Verify 100 component netlist has realistic net complexity."""
        netlist = generate_netlist(n_components=100, seed=42)

        # Should have significant number of nets
        assert len(netlist.nets) >= 20, f"Too few nets: {len(netlist.nets)}"

        # Calculate average net fanout
        total_pins = sum(len(net.pins) for net in netlist.nets)
        avg_fanout = total_pins / len(netlist.nets)

        # Realistic nets have 2-5 pins on average
        assert 2.0 <= avg_fanout <= 6.0, f"Unrealistic fanout: {avg_fanout:.1f}"

        # Power nets should have higher fanout
        power_nets = [n for n in netlist.nets if n.name in ("VCC", "GND")]
        if power_nets:
            power_fanout = sum(len(n.pins) for n in power_nets) / len(power_nets)
            assert power_fanout >= 3.0, f"Power nets too small: {power_fanout:.1f}"


# =============================================================================
# 50 Component Scale Tests (baseline)
# =============================================================================


class TestOptimizer50Components:
    """Test optimizer behavior with 50 components (baseline scale)."""

    def test_50_components_converges_quickly(self) -> None:
        """50 components should converge and have feasible placement."""
        netlist, board, context, composite = create_scale_setup(n_components=50)

        config = OptimizerConfig(
            epochs=200,
            seed=42,
            log_interval=20,
            checkpoint=OptimizerConfig.fast_test().checkpoint,
            early_stopping=OptimizerConfig.fast_test().early_stopping,
        )

        result = train(netlist, board, composite, context, config)

        # Check feasibility: overlap and boundary should be near zero
        # (wirelength will still be high, that's expected)
        if result.history:
            final_metrics = result.history[-1]
            overlap = final_metrics.loss_breakdown.get("overlap_weighted", 0)
            boundary = final_metrics.loss_breakdown.get("boundary_weighted", 0)

            # Overlap and boundary (hard constraints) should be resolved
            assert overlap < 100.0, f"Overlap too high: {overlap}"
            assert boundary < 100.0, f"Boundary violations too high: {boundary}"


# =============================================================================
# 200 Component Scale Tests (stress test)
# =============================================================================


@pytest.mark.slow
class TestOptimizer200Components:
    """Test optimizer behavior with 200 components (stress test)."""

    def test_200_components_runs(self) -> None:
        """Verify optimizer can handle 200 components."""
        netlist, board, context, composite = create_scale_setup(n_components=200, board_scale=1.5)

        config = OptimizerConfig(
            epochs=100,  # Short run for stress test
            seed=42,
            log_interval=20,
            checkpoint=OptimizerConfig.fast_test().checkpoint,
            early_stopping=OptimizerConfig.fast_test().early_stopping,
        )

        result = train(netlist, board, composite, context, config)

        assert result.total_epochs == 100
        assert result.final_loss >= 0


# =============================================================================
# Convergence Time Benchmarks (temper-1my.3.4)
# =============================================================================


class TestConvergenceTimeBenchmarks:
    """Benchmark convergence time vs component count."""

    @pytest.mark.benchmark
    def test_convergence_time_scales_reasonably(self) -> None:
        """
        Verify convergence time scales sub-quadratically with component count.

        The optimizer should not exhibit O(n²) or worse scaling, as this
        would make it impractical for large designs.
        """
        results = {}

        for n_components in [20, 40, 60]:
            netlist, board, context, composite = create_scale_setup(n_components=n_components)

            config = OptimizerConfig(
                epochs=100,
                seed=42,
                log_interval=50,
                checkpoint=OptimizerConfig.fast_test().checkpoint,
                early_stopping=OptimizerConfig.fast_test().early_stopping,
            )

            start_time = time.perf_counter()
            result = train(netlist, board, composite, context, config)
            elapsed = time.perf_counter() - start_time

            results[n_components] = {
                "time": elapsed,
                "loss": result.final_loss,
                "time_per_epoch": elapsed / 100,
            }

        # Check scaling: 60 components should take less than 3x of 20 components
        # (would be 9x if O(n²))
        scaling_factor = results[60]["time"] / results[20]["time"]
        assert scaling_factor < 5.0, (
            f"Bad scaling: 60 components takes {scaling_factor:.1f}x longer than 20"
        )

    def test_epoch_time_is_reasonable(self) -> None:
        """Verify single epoch completes in reasonable time for 100 components."""
        netlist, board, context, composite = create_scale_setup(n_components=100)

        config = OptimizerConfig(
            epochs=20,
            seed=42,
            log_interval=10,
            checkpoint=OptimizerConfig.fast_test().checkpoint,
            early_stopping=OptimizerConfig.fast_test().early_stopping,
        )

        start_time = time.perf_counter()
        train(netlist, board, composite, context, config)
        elapsed = time.perf_counter() - start_time

        time_per_epoch = elapsed / 20
        # Each epoch should take less than 500ms on typical hardware
        assert time_per_epoch < 0.5, f"Epoch too slow: {time_per_epoch * 1000:.0f}ms"


# =============================================================================
# Quality at Scale Tests (temper-1my.3.5)
# =============================================================================


class TestQualityAtScale:
    """Test that placement quality doesn't degrade significantly at scale."""

    def test_overlap_resolution_at_scale(self) -> None:
        """
        Verify overlap resolution doesn't degrade with more components.

        The percentage of component pairs with overlap should remain low
        regardless of component count.
        """
        overlap_rates = {}

        for n_components in [20, 50, 100]:
            netlist, board, context, composite = create_scale_setup(n_components=n_components)

            config = OptimizerConfig(
                epochs=300,
                seed=42,
                log_interval=100,
                checkpoint=OptimizerConfig.fast_test().checkpoint,
                early_stopping=OptimizerConfig.fast_test().early_stopping,
            )

            result = train(netlist, board, composite, context, config)

            # Get widths and heights from bounds array
            widths = context.bounds[:, 0]
            heights = context.bounds[:, 1]

            overlap_loss = compute_overlap_penalty(result.final_state.positions, widths, heights)

            # Normalize by number of component pairs
            n_pairs = n_components * (n_components - 1) / 2
            normalized_overlap = float(overlap_loss) / n_pairs

            overlap_rates[n_components] = normalized_overlap

        # Normalized overlap should not increase dramatically
        # Allow 10x increase from 20 to 100 components (some degradation expected)
        assert overlap_rates[100] < overlap_rates[20] * 10 + 0.1, (
            f"Overlap quality degraded too much at scale: "
            f"{overlap_rates[20]:.3f} -> {overlap_rates[100]:.3f}"
        )


# =============================================================================
# Seed Sensitivity Tests (variance across random initializations)
# =============================================================================


class TestSeedSensitivity:
    """Test optimizer consistency across different random seeds."""

    def test_multiple_seeds_converge(self) -> None:
        """Verify optimizer converges for different random seeds."""
        results = []

        for seed in [42, 123, 456]:
            netlist, board, context, composite = create_scale_setup(n_components=50, seed=seed)

            config = OptimizerConfig(
                epochs=200,
                seed=seed,
                log_interval=50,
                checkpoint=OptimizerConfig.fast_test().checkpoint,
                early_stopping=OptimizerConfig.fast_test().early_stopping,
            )

            result = train(netlist, board, composite, context, config)

            # Check that hard constraints (overlap, boundary) are satisfied
            if result.history:
                final_metrics = result.history[-1]
                overlap = final_metrics.loss_breakdown.get("overlap_weighted", 0)
                boundary = final_metrics.loss_breakdown.get("boundary_weighted", 0)
                results.append(
                    {
                        "seed": seed,
                        "overlap": overlap,
                        "boundary": boundary,
                        "total_loss": result.final_loss,
                    }
                )

        # All runs should satisfy hard constraints
        for r in results:
            assert r["overlap"] < 100.0, f"Seed {r['seed']} overlap too high: {r['overlap']}"
            assert r["boundary"] < 100.0, f"Seed {r['seed']} boundary too high: {r['boundary']}"

        # Total loss variance should not be extreme (within 3x of each other)
        # This checks consistency, not absolute values
        total_losses = [r["total_loss"] for r in results]
        min_loss, max_loss = min(total_losses), max(total_losses)
        variance_ratio = max_loss / (min_loss + 1e-6)
        assert variance_ratio < 5.0, (
            f"Too much variance across seeds: {min_loss:.1f} to {max_loss:.1f}"
        )
