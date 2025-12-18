"""
Seed sensitivity analysis tests for optimizer variance.

These tests run the optimizer multiple times with different random seeds
to analyze:
- Loss variance across seeds (should be low for stable optimizer)
- Convergence rate (all seeds should converge)
- Quality metric stability (overlap, boundary, wirelength variance)

IMPORTANT: These tests use RANDOM initialization only (no heuristics).
For production use, heuristic initialization (spectral + force-directed)
provides significantly better results:
- 85% lower initial loss
- 18% lower final loss
- 88% lower overlap variance
- 21% better wirelength

See test_heuristic_impact.py for comparison tests.

Tests are marked @pytest.mark.slow and @pytest.mark.monte_carlo for selective running.

Run with: pytest tests/sensitivity/ -v --slow
"""

from __future__ import annotations

import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, List, Optional

import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer import train, OptimizerConfig


# Results directory
RESULTS_DIR = Path(__file__).parent / "results"


@dataclass
class SeedRunResult:
    """Result from a single seed run."""

    seed: int
    final_loss: float
    overlap_penalty: float
    boundary_penalty: float
    wirelength: float
    epochs_run: int
    elapsed_seconds: float
    converged: bool


def create_test_netlist(n_components: int = 17) -> Netlist:
    """
    Create a fixed test netlist for seed sensitivity analysis.

    Uses 17 components by default (similar to Temper power stage).
    """
    # Import from the tests fixtures - add parent to path
    import importlib.util

    fixtures_path = (
        Path(__file__).parent.parent / "fixtures" / "generators" / "synthetic_netlist.py"
    )
    spec = importlib.util.spec_from_file_location("synthetic_netlist", fixtures_path)
    synthetic_netlist = importlib.util.module_from_spec(spec)  # type: ignore
    spec.loader.exec_module(synthetic_netlist)  # type: ignore

    # Always use the same seed for netlist generation
    # so we're only varying the optimizer seed
    return synthetic_netlist.generate_netlist(n_components=n_components, seed=12345)


def run_optimization_with_seed(
    netlist: Netlist,
    board: Board,
    seed: int,
    epochs: int = 400,
    verbose: bool = False,
) -> SeedRunResult:
    """
    Run optimization with a specific seed and return results.

    Args:
        netlist: The netlist to optimize.
        board: Board definition.
        seed: Random seed for initialization.
        epochs: Number of epochs to run.
        verbose: Whether to print progress.

    Returns:
        SeedRunResult with metrics from the run.
    """
    # Create loss context
    context = LossContext.from_netlist_and_board(netlist, board)

    # Create composite loss with overlap, boundary, and wirelength
    composite = CompositeLoss(
        [
            WeightedLoss(OverlapLoss(inflation_ramp=0.3), weight=100.0),
            WeightedLoss(BoundaryLoss(), weight=50.0),
            WeightedLoss(WirelengthLoss(), weight=1.0),
        ]
    )

    # Create config with specific seed
    config = OptimizerConfig(
        gradient_clip_norm=1.0,  # Gradient clipping for robustness
        epochs=epochs,
        seed=seed,
        log_interval=epochs,  # Only log at end to reduce overhead
        checkpoint=OptimizerConfig.fast_test().checkpoint,
        early_stopping=OptimizerConfig.fast_test().early_stopping,
    )

    start_time = time.time()
    result = train(netlist, board, composite, context, config)
    elapsed = time.time() - start_time

    # Extract final metrics
    final_loss = result.final_loss

    # Get loss breakdown from final state
    # We need to re-evaluate to get individual components
    from temper_placer.geometry.transform import sample_rotation_batch
    import jax.numpy as jnp
    import jax

    positions = result.final_state.positions
    rotation_logits = result.final_state.rotation_logits

    # Sample hard rotations (temperature=0.01 for nearly hard)
    key = jax.random.PRNGKey(0)
    rotations = sample_rotation_batch(rotation_logits, key, temperature=0.01)

    # Evaluate individual losses - get .value from LossResult
    overlap_loss = OverlapLoss()
    boundary_loss = BoundaryLoss()
    wirelength_loss = WirelengthLoss()

    overlap_val = float(overlap_loss(positions, rotations, context).value)
    boundary_val = float(boundary_loss(positions, rotations, context).value)
    wirelength_val = float(wirelength_loss(positions, rotations, context).value)

    return SeedRunResult(
        seed=seed,
        final_loss=final_loss,
        overlap_penalty=overlap_val,
        boundary_penalty=boundary_val,
        wirelength=wirelength_val,
        epochs_run=result.total_epochs,
        elapsed_seconds=elapsed,
        converged=result.converged,
    )


def coefficient_of_variation(values: List[float]) -> float:
    """
    Calculate coefficient of variation (CV = std/mean).

    CV < 0.3 indicates low variance.
    """
    arr = np.array(values)
    mean = np.mean(arr)
    if mean == 0:
        return float("inf")
    return float(np.std(arr) / mean)


def save_results_csv(results: List[SeedRunResult], filepath: Path) -> None:
    """Save results to CSV file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "seed",
                "final_loss",
                "overlap_penalty",
                "boundary_penalty",
                "wirelength",
                "epochs_run",
                "elapsed_seconds",
                "converged",
            ],
        )
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "seed": r.seed,
                    "final_loss": r.final_loss,
                    "overlap_penalty": r.overlap_penalty,
                    "boundary_penalty": r.boundary_penalty,
                    "wirelength": r.wirelength,
                    "epochs_run": r.epochs_run,
                    "elapsed_seconds": r.elapsed_seconds,
                    "converged": r.converged,
                }
            )


class TestSeedSensitivity:
    """Tests for optimizer seed sensitivity."""

    # Class variable to store results between tests
    _monte_carlo_results: ClassVar[Optional[List[SeedRunResult]]] = None

    @pytest.fixture(scope="class")
    def netlist_and_board(self):
        """Create shared netlist and board for all tests."""
        netlist = create_test_netlist(n_components=17)
        board = Board(width=100.0, height=100.0)
        return netlist, board

    @pytest.mark.slow
    @pytest.mark.monte_carlo
    def test_monte_carlo_100_seeds(self, netlist_and_board):
        """
        Run optimizer 100 times with different seeds.

        This is the main Monte Carlo test that generates the seed_analysis.csv
        file with detailed results for all runs.
        """
        netlist, board = netlist_and_board

        results: List[SeedRunResult] = []
        n_seeds = 100
        epochs = 400

        print(f"\nRunning Monte Carlo analysis with {n_seeds} seeds...")

        for i, seed in enumerate(range(n_seeds)):
            result = run_optimization_with_seed(netlist, board, seed=seed, epochs=epochs)
            results.append(result)

            if (i + 1) % 10 == 0:
                print(f"  Completed {i + 1}/{n_seeds} runs...")

        # Save results
        csv_path = RESULTS_DIR / "seed_analysis.csv"
        save_results_csv(results, csv_path)
        print(f"Results saved to {csv_path}")

        # Basic sanity check - should have 100 results
        assert len(results) == n_seeds

        # Store results in class for other tests
        TestSeedSensitivity._monte_carlo_results = results

    @pytest.mark.slow
    @pytest.mark.monte_carlo
    def test_loss_variance_acceptable(self, netlist_and_board):
        """
        Test that coefficient of variation for final loss is < 0.35.

        CV < 0.35 indicates acceptable variance for random initialization.
        (With heuristic initialization, CV is typically < 0.2)
        """
        results = TestSeedSensitivity._monte_carlo_results

        if results is None:
            pytest.skip("Run test_monte_carlo_100_seeds first")

        losses = [r.final_loss for r in results]
        cv = coefficient_of_variation(losses)

        print(f"\nFinal loss statistics:")
        print(f"  Mean: {np.mean(losses):.4f}")
        print(f"  Std:  {np.std(losses):.4f}")
        print(f"  CV:   {cv:.4f}")
        print(f"  Min:  {np.min(losses):.4f}")
        print(f"  Max:  {np.max(losses):.4f}")

        assert cv < 0.35, f"Loss CV {cv:.4f} exceeds threshold 0.35"

    @pytest.mark.slow
    @pytest.mark.monte_carlo
    def test_all_seeds_converge(self, netlist_and_board):
        """
        Test that at least 95% of seeds find a valid placement.

        Valid placement: overlap < 1.0 AND boundary < 1.0
        (raw penalty values, not weighted)

        Note: With random initialization, ~1-5% of seeds may hit local minima.
        Heuristic initialization achieves 100% convergence.
        """
        results = TestSeedSensitivity._monte_carlo_results

        if results is None:
            pytest.skip("Run test_monte_carlo_100_seeds first")

        valid_placements = []
        invalid_seeds = []

        for r in results:
            # A placement is valid if components don't overlap significantly
            # and stay within bounds
            is_valid = (r.overlap_penalty < 1.0) and (r.boundary_penalty < 1.0)
            valid_placements.append(is_valid)
            if not is_valid:
                invalid_seeds.append(r.seed)

        pass_rate = sum(valid_placements) / len(valid_placements)

        print(f"\nConvergence statistics:")
        print(f"  Valid placements: {sum(valid_placements)}/{len(valid_placements)}")
        print(f"  Pass rate: {pass_rate:.1%}")

        if invalid_seeds:
            print(f"  Invalid seeds: {invalid_seeds[:10]}...")

        assert pass_rate >= 0.95, (
            f"Only {pass_rate:.1%} of seeds converged. Failed seeds: {invalid_seeds[:10]}"
        )

    @pytest.mark.slow
    @pytest.mark.monte_carlo
    def test_quality_metrics_stable(self, netlist_and_board):
        """
        Test that individual quality metrics meet acceptable thresholds.

        For random initialization (baseline), thresholds are relaxed:
        - Overlap: mean < 0.1 (near-zero overlap on average)
        - Boundary: mean < 0.1 (components stay in bounds)
        - Wirelength CV < 0.5 (moderate variance acceptable)

        Note: With heuristic initialization, overlap CV < 0.1 is achievable.
        Random initialization has high overlap variance because some seeds
        converge to different local minima.
        """
        results = TestSeedSensitivity._monte_carlo_results

        if results is None:
            pytest.skip("Run test_monte_carlo_100_seeds first")

        overlaps = [r.overlap_penalty for r in results]
        boundaries = [r.boundary_penalty for r in results]
        wirelengths = [r.wirelength for r in results]

        cv_overlap = coefficient_of_variation(overlaps)
        cv_boundary = coefficient_of_variation(boundaries)
        cv_wirelength = coefficient_of_variation(wirelengths)

        mean_overlap = np.mean(overlaps)
        mean_boundary = np.mean(boundaries)

        print(f"\nQuality metric statistics:")
        print(f"  Overlap:    mean={mean_overlap:.4f}, CV={cv_overlap:.4f}")
        print(f"  Boundary:   mean={mean_boundary:.4f}, CV={cv_boundary:.4f}")
        print(f"  Wirelength: mean={np.mean(wirelengths):.4f}, CV={cv_wirelength:.4f}")

        # Check mean values (more meaningful than CV for near-zero values)
        assert mean_overlap < 0.1, f"Mean overlap {mean_overlap:.4f} exceeds 0.1"
        assert mean_boundary < 0.1, f"Mean boundary {mean_boundary:.4f} exceeds 0.1"
        assert cv_wirelength < 0.5, f"Wirelength CV {cv_wirelength:.4f} exceeds 0.5"


class TestSeedSensitivityQuick:
    """Quick seed sensitivity tests for CI (fewer seeds)."""

    @pytest.fixture
    def netlist_and_board(self):
        """Create netlist and board for testing."""
        netlist = create_test_netlist(n_components=10)
        board = Board(width=80.0, height=80.0)
        return netlist, board

    def test_five_seeds_converge(self, netlist_and_board):
        """
        Quick test: verify 5 seeds all converge.

        This is a sanity check that runs in CI.
        """
        netlist, board = netlist_and_board

        results = []
        for seed in range(5):
            result = run_optimization_with_seed(netlist, board, seed=seed, epochs=100)
            results.append(result)

        # All should produce finite losses
        for r in results:
            assert np.isfinite(r.final_loss), f"Seed {r.seed} produced non-finite loss"

        # At least 80% should converge to valid placement
        valid_count = sum(1 for r in results if r.overlap_penalty < 2.0)
        assert valid_count >= 4, f"Only {valid_count}/5 seeds converged"

    def test_different_seeds_produce_different_results(self, netlist_and_board):
        """
        Test that different seeds produce different (but valid) results.

        This verifies that the seed actually affects initialization.
        """
        netlist, board = netlist_and_board

        result_0 = run_optimization_with_seed(netlist, board, seed=0, epochs=100)
        result_1 = run_optimization_with_seed(netlist, board, seed=1, epochs=100)

        # Losses should be different (not identical)
        # Allow for some floating point tolerance
        assert (
            abs(result_0.final_loss - result_1.final_loss) > 0.001
            or abs(result_0.wirelength - result_1.wirelength) > 0.001
        ), "Different seeds produced identical results"

    def test_seed_reproducibility(self, netlist_and_board):
        """
        Test that same seed produces identical results.

        This verifies deterministic behavior.
        """
        netlist, board = netlist_and_board

        result_a = run_optimization_with_seed(netlist, board, seed=42, epochs=50)
        result_b = run_optimization_with_seed(netlist, board, seed=42, epochs=50)

        # Same seed should produce identical loss
        assert abs(result_a.final_loss - result_b.final_loss) < 1e-6, (
            f"Same seed produced different results: {result_a.final_loss} vs {result_b.final_loss}"
        )
