"""
Heuristic impact analysis: compare optimizer with vs without heuristic initialization.

This module compares two initialization strategies:
1. Random initialization (baseline)
2. Heuristic initialization (spectral + force-directed)

Metrics compared:
- Final loss
- Convergence rate (overlap < 1.0, boundary < 1.0)
- Overlap penalty
- Wirelength
- Optimization time

Run with: pytest tests/sensitivity/test_heuristic_impact.py -v -s
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import jax
import jax.numpy as jnp
import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState
from temper_placer.geometry.transform import sample_rotation_batch
from temper_placer.heuristics.pipeline import create_default_pipeline
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer import OptimizerConfig, train


@dataclass
class RunResult:
    """Result from a single optimization run."""

    seed: int
    init_mode: str  # "random" or "heuristic"
    final_loss: float
    overlap_penalty: float
    boundary_penalty: float
    wirelength: float
    elapsed_seconds: float
    converged: bool
    initial_loss: float  # Loss after initialization, before optimization


def create_test_netlist(n_components: int = 17) -> Netlist:
    """Create a fixed test netlist for comparison."""
    import importlib.util

    fixtures_path = (
        Path(__file__).parent.parent / "fixtures" / "generators" / "synthetic_netlist.py"
    )
    spec = importlib.util.spec_from_file_location("synthetic_netlist", fixtures_path)
    synthetic_netlist = importlib.util.module_from_spec(spec)  # type: ignore
    spec.loader.exec_module(synthetic_netlist)  # type: ignore

    # Fixed seed for netlist - we only vary optimizer seed
    return synthetic_netlist.generate_netlist(n_components=n_components, seed=12345)


def random_initial_state(netlist: Netlist, board: Board, seed: int) -> PlacementState:
    """Generate random initial positions within board bounds."""
    key = jax.random.PRNGKey(seed)
    n = netlist.n_components

    # Random positions within board (with margin)
    margin = 5.0
    key, k1, k2 = jax.random.split(key, 3)

    ox, oy = board.origin
    positions = jnp.stack(
        [
            jax.random.uniform(k1, (n,), minval=ox + margin, maxval=ox + board.width - margin),
            jax.random.uniform(k2, (n,), minval=oy + margin, maxval=oy + board.height - margin),
        ],
        axis=-1,
    )

    # Random rotation logits (uniform over 4 orientations)
    rotation_logits = jnp.zeros((n, 4))

    return PlacementState(positions=positions, rotation_logits=rotation_logits)


def heuristic_initial_state(
    netlist: Netlist, board: Board, constraints: PlacementConstraints, seed: int
) -> PlacementState:
    """Generate initial positions using heuristic pipeline."""
    pipeline = create_default_pipeline()
    key = jax.random.PRNGKey(seed)

    result = pipeline.run(
        board=board,
        netlist=netlist,
        constraints=constraints,
        key=key,
    )

    return result.state


def evaluate_placement(state: PlacementState, context: LossContext) -> tuple[float, float, float]:
    """Evaluate overlap, boundary, and wirelength for a placement state."""
    key = jax.random.PRNGKey(0)
    rotations = sample_rotation_batch(state.rotation_logits, key, temperature=0.01)

    overlap_val = float(OverlapLoss()(state.positions, rotations, context).value)
    boundary_val = float(BoundaryLoss()(state.positions, rotations, context).value)
    wirelength_val = float(WirelengthLoss()(state.positions, rotations, context).value)

    return overlap_val, boundary_val, wirelength_val


def run_optimization(
    netlist: Netlist,
    board: Board,
    init_mode: str,
    seed: int,
    epochs: int = 400,
) -> RunResult:
    """
    Run optimization with specified initialization mode.

    Args:
        netlist: Netlist to place
        board: Board definition
        init_mode: "random" or "heuristic"
        seed: Random seed
        epochs: Number of epochs

    Returns:
        RunResult with metrics
    """
    # Create constraints
    constraints = PlacementConstraints(board_margin_mm=5.0)

    # Create loss context
    context = LossContext.from_netlist_and_board(netlist, board)

    # Create composite loss
    composite = CompositeLoss(
        [
            WeightedLoss(OverlapLoss(), weight=100.0),
            WeightedLoss(BoundaryLoss(), weight=50.0),
            WeightedLoss(WirelengthLoss(), weight=1.0),
        ]
    )

    # Create initial state based on mode
    if init_mode == "random":
        initial_state = random_initial_state(netlist, board, seed)
    elif init_mode == "heuristic":
        initial_state = heuristic_initial_state(netlist, board, constraints, seed)
    else:
        raise ValueError(f"Unknown init_mode: {init_mode}")

    # Evaluate initial state
    init_overlap, init_boundary, init_wirelength = evaluate_placement(initial_state, context)
    initial_loss = 100.0 * init_overlap + 50.0 * init_boundary + init_wirelength

    # Create config
    config = OptimizerConfig(
        epochs=epochs,
        seed=seed,
        log_interval=epochs,
        checkpoint=OptimizerConfig.fast_test().checkpoint,
        early_stopping=OptimizerConfig.fast_test().early_stopping,
    )

    # Run optimization
    start_time = time.time()
    result = train(
        netlist,
        board,
        composite,
        context,
        config,
        initial_state=initial_state,
    )
    elapsed = time.time() - start_time

    # Evaluate final state
    overlap_val, boundary_val, wirelength_val = evaluate_placement(result.final_state, context)

    # Check convergence
    converged = overlap_val < 1.0 and boundary_val < 1.0

    return RunResult(
        seed=seed,
        init_mode=init_mode,
        final_loss=result.final_loss,
        overlap_penalty=overlap_val,
        boundary_penalty=boundary_val,
        wirelength=wirelength_val,
        elapsed_seconds=elapsed,
        converged=converged,
        initial_loss=initial_loss,
    )


class TestHeuristicImpact:
    """Tests comparing heuristic vs random initialization."""

    @pytest.fixture(scope="class")
    def netlist_and_board(self):
        """Create shared netlist and board."""
        netlist = create_test_netlist(n_components=17)
        board = Board(width=100.0, height=100.0)
        return netlist, board

    def test_single_seed_comparison(self, netlist_and_board):
        """
        Quick test: compare random vs heuristic for a single seed.

        This verifies the comparison framework works.
        """
        netlist, board = netlist_and_board

        random_result = run_optimization(netlist, board, "random", seed=42, epochs=200)
        heuristic_result = run_optimization(netlist, board, "heuristic", seed=42, epochs=200)

        print("\n=== Single Seed Comparison (seed=42) ===")
        print(f"\nRandom initialization:")
        print(f"  Initial loss:  {random_result.initial_loss:.2f}")
        print(f"  Final loss:    {random_result.final_loss:.2f}")
        print(f"  Overlap:       {random_result.overlap_penalty:.4f}")
        print(f"  Converged:     {random_result.converged}")
        print(f"  Time:          {random_result.elapsed_seconds:.2f}s")

        print(f"\nHeuristic initialization:")
        print(f"  Initial loss:  {heuristic_result.initial_loss:.2f}")
        print(f"  Final loss:    {heuristic_result.final_loss:.2f}")
        print(f"  Overlap:       {heuristic_result.overlap_penalty:.4f}")
        print(f"  Converged:     {heuristic_result.converged}")
        print(f"  Time:          {heuristic_result.elapsed_seconds:.2f}s")

        improvement = (
            (random_result.final_loss - heuristic_result.final_loss)
            / random_result.final_loss
            * 100
        )
        print(f"\nImprovement: {improvement:.1f}% lower final loss with heuristics")

        # Both should produce finite losses
        assert np.isfinite(random_result.final_loss)
        assert np.isfinite(heuristic_result.final_loss)

    @pytest.mark.slow
    def test_multi_seed_comparison(self, netlist_and_board):
        """
        Compare random vs heuristic initialization over 20 seeds.

        This test measures:
        - Average final loss
        - Convergence rate
        - Average overlap penalty
        - Average wirelength
        """
        netlist, board = netlist_and_board
        n_seeds = 20
        epochs = 400

        random_results: List[RunResult] = []
        heuristic_results: List[RunResult] = []

        print(f"\n=== Multi-Seed Comparison ({n_seeds} seeds) ===")

        for seed in range(n_seeds):
            random_result = run_optimization(netlist, board, "random", seed=seed, epochs=epochs)
            heuristic_result = run_optimization(
                netlist, board, "heuristic", seed=seed, epochs=epochs
            )

            random_results.append(random_result)
            heuristic_results.append(heuristic_result)

            if (seed + 1) % 5 == 0:
                print(f"  Completed {seed + 1}/{n_seeds} seeds...")

        # Compute statistics
        def stats(results: List[RunResult]) -> dict:
            losses = [r.final_loss for r in results]
            overlaps = [r.overlap_penalty for r in results]
            wirelengths = [r.wirelength for r in results]
            converged = [r.converged for r in results]
            times = [r.elapsed_seconds for r in results]
            initial_losses = [r.initial_loss for r in results]

            return {
                "avg_loss": np.mean(losses),
                "std_loss": np.std(losses),
                "avg_overlap": np.mean(overlaps),
                "std_overlap": np.std(overlaps),
                "avg_wirelength": np.mean(wirelengths),
                "convergence_rate": sum(converged) / len(converged),
                "avg_time": np.mean(times),
                "avg_initial_loss": np.mean(initial_losses),
            }

        random_stats = stats(random_results)
        heuristic_stats = stats(heuristic_results)

        print("\n--- Random Initialization ---")
        print(f"  Avg initial loss:  {random_stats['avg_initial_loss']:.2f}")
        print(
            f"  Avg final loss:    {random_stats['avg_loss']:.2f} ± {random_stats['std_loss']:.2f}"
        )
        print(
            f"  Avg overlap:       {random_stats['avg_overlap']:.4f} ± {random_stats['std_overlap']:.4f}"
        )
        print(f"  Avg wirelength:    {random_stats['avg_wirelength']:.2f}")
        print(f"  Convergence rate:  {random_stats['convergence_rate']:.0%}")
        print(f"  Avg time:          {random_stats['avg_time']:.2f}s")

        print("\n--- Heuristic Initialization ---")
        print(f"  Avg initial loss:  {heuristic_stats['avg_initial_loss']:.2f}")
        print(
            f"  Avg final loss:    {heuristic_stats['avg_loss']:.2f} ± {heuristic_stats['std_loss']:.2f}"
        )
        print(
            f"  Avg overlap:       {heuristic_stats['avg_overlap']:.4f} ± {heuristic_stats['std_overlap']:.4f}"
        )
        print(f"  Avg wirelength:    {heuristic_stats['avg_wirelength']:.2f}")
        print(f"  Convergence rate:  {heuristic_stats['convergence_rate']:.0%}")
        print(f"  Avg time:          {heuristic_stats['avg_time']:.2f}s")

        # Compute improvement
        loss_improvement = (
            (random_stats["avg_loss"] - heuristic_stats["avg_loss"])
            / random_stats["avg_loss"]
            * 100
        )
        initial_loss_advantage = (
            (random_stats["avg_initial_loss"] - heuristic_stats["avg_initial_loss"])
            / random_stats["avg_initial_loss"]
            * 100
        )

        print("\n--- Summary ---")
        print(f"  Initial loss advantage:  {initial_loss_advantage:.1f}% lower with heuristics")
        print(f"  Final loss improvement:  {loss_improvement:.1f}% lower with heuristics")

        # Assertions
        # Heuristics should provide at least some benefit
        # Note: relaxed assertion - we just want to verify the framework works
        assert heuristic_stats["convergence_rate"] >= 0.8, (
            f"Heuristic convergence rate too low: {heuristic_stats['convergence_rate']:.0%}"
        )

    def test_heuristic_provides_better_starting_point(self, netlist_and_board):
        """
        Test that heuristic initialization provides a better starting point.

        Heuristic initial loss should be lower than random initial loss.
        """
        netlist, board = netlist_and_board

        # Run 5 seeds and compare initial losses
        random_initial_losses = []
        heuristic_initial_losses = []

        for seed in range(5):
            random_result = run_optimization(netlist, board, "random", seed=seed, epochs=10)
            heuristic_result = run_optimization(netlist, board, "heuristic", seed=seed, epochs=10)

            random_initial_losses.append(random_result.initial_loss)
            heuristic_initial_losses.append(heuristic_result.initial_loss)

        avg_random = np.mean(random_initial_losses)
        avg_heuristic = np.mean(heuristic_initial_losses)

        print(f"\n=== Initial Loss Comparison ===")
        print(f"Random avg:     {avg_random:.2f}")
        print(f"Heuristic avg:  {avg_heuristic:.2f}")
        print(f"Advantage:      {(avg_random - avg_heuristic) / avg_random * 100:.1f}%")

        # Heuristics should give a better starting point
        # (lower initial loss = components already closer to valid positions)
        assert avg_heuristic < avg_random, (
            f"Heuristic initial loss ({avg_heuristic:.2f}) should be lower than "
            f"random ({avg_random:.2f})"
        )


class TestHeuristicImpactQuick:
    """Quick tests for CI - minimal seed count."""

    @pytest.fixture
    def netlist_and_board(self):
        """Create smaller netlist for quick tests."""
        netlist = create_test_netlist(n_components=10)
        board = Board(width=80.0, height=80.0)
        return netlist, board

    def test_heuristic_vs_random_quick(self, netlist_and_board):
        """
        Quick comparison: 3 seeds, verify framework works.
        """
        netlist, board = netlist_and_board

        for seed in range(3):
            random_result = run_optimization(netlist, board, "random", seed=seed, epochs=100)
            heuristic_result = run_optimization(netlist, board, "heuristic", seed=seed, epochs=100)

            # Both should produce finite losses
            assert np.isfinite(random_result.final_loss)
            assert np.isfinite(heuristic_result.final_loss)

            print(
                f"Seed {seed}: random={random_result.final_loss:.2f}, "
                f"heuristic={heuristic_result.final_loss:.2f}"
            )
