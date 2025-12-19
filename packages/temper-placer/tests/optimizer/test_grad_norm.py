"""Tests for GradNorm adaptive loss weighting."""

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer.config import GradNormConfig, OptimizerConfig
from temper_placer.optimizer.train import train


class TestGradNorm:
    """Tests for GradNorm integration."""

    def create_mock_data(self):
        """Create mock netlist and board."""
        u1 = Component(ref="U1", footprint="SOIC-8", bounds=(10, 10))
        u2 = Component(ref="U2", footprint="SOIC-8", bounds=(10, 10))
        net = Net(name="N1", pins=[("U1", "1"), ("U2", "1")])

        netlist = Netlist()
        netlist.components = [u1, u2]
        netlist.nets = [net]
        netlist.build_indices()

        board = Board(width=100, height=100)
        return netlist, board

    def test_grad_norm_updates_weights(self):
        """Verify that weights actually change when GradNorm is enabled."""
        netlist, board = self.create_mock_data()

        config = OptimizerConfig(
            epochs=10,
            use_grad_norm=True,
            grad_norm=GradNormConfig(learning_rate=0.1),
            log_interval=1
        )

        composite_loss = CompositeLoss([
            WeightedLoss(WirelengthLoss(), weight=1.0),
            WeightedLoss(OverlapLoss(), weight=1.0)
        ])

        context = LossContext.from_netlist_and_board(netlist, board)

        result = train(netlist, board, composite_loss, context, config)

        # Check if weights changed from initial [1.0, 1.0]
        # Weights are normalized to sum to n_losses (2.0)
        initial_weights = [1.0, 1.0]

        # history[0] is epoch 0 (weights might not have changed yet if update is after step)
        # But our implementation updates them within the step.

        last_metrics = result.history[-1]
        assert last_metrics.loss_weights is not None

        weights = list(last_metrics.loss_weights.values())
        assert len(weights) == 2
        # Sum should be approx 2.0 (n_losses)
        assert sum(weights) == pytest.approx(2.0)

        # With high overlap and low wirelength, weights should shift
        # This is a bit non-deterministic but we expect SOME change
        assert any(w != 1.0 for w in weights)

    def test_grad_norm_disabled_constant_weights(self):
        """Verify that weights stay constant when GradNorm is disabled."""
        netlist, board = self.create_mock_data()

        config = OptimizerConfig(
            epochs=5,
            use_grad_norm=False,
            log_interval=1
        )

        composite_loss = CompositeLoss([
            WeightedLoss(WirelengthLoss(), weight=1.0),
            WeightedLoss(OverlapLoss(), weight=1.0)
        ])

        context = LossContext.from_netlist_and_board(netlist, board)

        result = train(netlist, board, composite_loss, context, config)

        for metrics in result.history:
            assert metrics.loss_weights is None
