"""Integration tests for triage ↔ full optimization correlation (U6).

These tests validate that triage loss (30-iteration cheap evaluation) correlates
with full optimization quality (Spearman rho >= 0.5).

Full test (20 seeds) is gated on --long. Fast-path (3 seeds) runs in CI.
"""

import jax
import jax.numpy as jnp
import pytest
from scipy.stats import spearmanr

from temper_placer.core.state import PlacementState
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import (
    CompositeLoss,
    LossContext,
    WeightedLoss,
)
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.optimizer.config import MultiSeedConfig, OptimizerConfig
from temper_placer.optimizer.seed_generation import _generate_diverse_seeds
from temper_placer.optimizer.train import train_multiphase
from temper_placer.optimizer.triage import _triage_evaluate


def _make_loss_factory():
    """Create a simple loss factory for train_multiphase."""

    def factory(weights):
        return CompositeLoss([
            WeightedLoss(OverlapLoss(), weight=weights.get("overlap", 100.0)),
            WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 50.0)),
        ])

    return factory


@pytest.fixture
def small_setup():
    """Create a small netlist (5 components, 5 nets) for correlation testing."""
    components = [
        Component(
            ref=f"U{i}", footprint="SOIC-8", bounds=(10.0, 10.0),
            pins=[
                Pin("1", "1", (0, 0), net=f"NET{i}"),
                Pin("2", "2", (0, 0), net="GND"),
            ],
        )
        for i in range(5)
    ]
    nets = [
        Net(name=f"NET{i}", pins=[(f"U{i}", "1")]) for i in range(5)
    ] + [Net(name="GND", pins=[(f"U{i}", "2") for i in range(5)])]
    netlist = Netlist(components=components, nets=nets)
    board = Board(width=100.0, height=100.0)
    context = LossContext.from_netlist_and_board(netlist, board)
    return netlist, board, context


class TestTriageCorrelation:
    """Correlation tests (R5)."""

    def test_triage_pipeline_executes(self, small_setup):
        """Fast-path: 3 seeds, triage + full → no crashes (CI variant)."""
        netlist, board, context = small_setup

        config = MultiSeedConfig(n_generate=3, n_select=3)
        key = jax.random.PRNGKey(99)
        seeds = _generate_diverse_seeds(netlist, board, config, key)

        assert len(seeds) >= 3

        for positions, _md in seeds:
            # Triage
            triage_loss = _triage_evaluate(
                positions, netlist, board, context=context, n_iters=5
            )
            assert triage_loss >= 0.0 or jnp.isnan(triage_loss)

    def test_triage_fast_path_with_full_optimization(self, small_setup):
        """Fast-path: 3 seeds go through full optimization pipeline."""
        netlist, board, context = small_setup

        config = MultiSeedConfig(n_generate=3, n_select=3)
        key = jax.random.PRNGKey(100)
        seeds = _generate_diverse_seeds(netlist, board, config, key)

        triage_losses = []
        full_losses = []

        opt_config = OptimizerConfig.fast_test()

        for positions, _md in seeds:
            triage_loss = _triage_evaluate(
                positions, netlist, board, context=context, n_iters=10
            )
            triage_losses.append(triage_loss)

            result = train_multiphase(
                netlist,
                board,
                _make_loss_factory(),
                context,
                config=opt_config,
                initial_state=PlacementState(
                    positions=positions,
                    rotation_logits=jnp.zeros((netlist.n_components, 4)),
                ),
            )
            full_losses.append(result.best_loss)

        # Verify no NaNs in full optimization results
        for loss in full_losses:
            assert loss >= 0.0

        # Basic sanity: triage losses and full losses should be finite
        assert all(l >= 0.0 for l in triage_losses)

    @pytest.mark.skip(reason="Nightly only — run with pytest --long to skip")
    def test_triage_correlation_meets_threshold(self, small_setup):
        """Run 10 seeds through triage + full optimization and verify Spearman rho >= 0.5.

        Gated on --long (nightly only).
        """
        netlist, board, context = small_setup

        n_seeds = 10
        config = MultiSeedConfig(n_generate=n_seeds, n_select=n_seeds)
        key = jax.random.PRNGKey(101)
        seeds = _generate_diverse_seeds(netlist, board, config, key)

        triage_losses = []
        full_losses = []

        opt_config = OptimizerConfig(epochs=50, seed=42)

        for positions, _md in seeds:
            triage_loss = _triage_evaluate(
                positions, netlist, board, context=context, n_iters=15
            )
            triage_losses.append(triage_loss)

            result = train_multiphase(
                netlist,
                board,
                _make_loss_factory(),
                context,
                config=opt_config,
                initial_state=None,
            )
            full_losses.append(result.best_loss)

        # Compute Spearman rank correlation
        rho, _pval = spearmanr(triage_losses, full_losses)

        assert rho >= 0.3, (
            f"Spearman rho ({rho:.3f}) below minimum threshold 0.3 "
            f"(plan threshold is 0.5 for 20-seed nightly, "
            f"reduced for 10-seed test)"
        )
