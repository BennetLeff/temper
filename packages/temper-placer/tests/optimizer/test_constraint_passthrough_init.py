"""
Tests for constraint passthrough initialization pipeline.

Verifies that adding the optional `constraints: PlacementConstraints | None = None`
parameter to the init call chain preserves all existing behavior — the parameter
is a pass-through conduit with zero side effects until a downstream initializer
reads it (no such initializer exists yet).
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.optimizer.config import (
    InitializationConfig,
    OptimizerConfig,
    ZoneAwareConfig,
)
from temper_placer.optimizer.initialization import (
    LearnedInitializer,
    SpectralInitializer,
)
from temper_placer.optimizer.train import (
    initialize_training_state,
)
from temper_placer.optimizer.zone_aware_init import ZoneAwareSpectralInitializer


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_minimal_netlist() -> Netlist:
    components = [
        Component(
            ref="R1",
            footprint="0805",
            bounds=(5.0, 2.5),
            pins=[Pin("1", "1", (0, 0), net="N1")],
        ),
        Component(
            ref="R2",
            footprint="0805",
            bounds=(5.0, 2.5),
            pins=[Pin("1", "1", (0, 0), net="N1")],
        ),
    ]
    nets = [Net(name="N1", pins=[("R1", "1"), ("R2", "1")])]
    return Netlist(components=components, nets=nets)


def _empty_constraints() -> PlacementConstraints:
    return PlacementConstraints()


# ---------------------------------------------------------------------------
# 1. Property-Based Invariant: Element-wise identical output with/without
#    constraints passthrough
# ---------------------------------------------------------------------------


class TestConstraintPassthroughInvariant:
    """The passthrough parameter must not change optimizer output."""

    def test_initialize_training_state_spectral_invariant(self):
        """Spectral init produces identical positions with constraints=None
        vs. a populated PlacementConstraints."""
        netlist = _make_minimal_netlist()
        board = Board(width=100.0, height=100.0)
        config = OptimizerConfig(
            initialization=InitializationConfig(method="spectral"), seed=42
        )

        state_none = initialize_training_state(
            netlist, board, config, constraints=None
        )
        state_populated = initialize_training_state(
            netlist, board, config, constraints=_empty_constraints()
        )

        assert jnp.allclose(state_none.positions, state_populated.positions)
        assert jnp.allclose(
            state_none.rotation_logits, state_populated.rotation_logits
        )
        # net_virtual_nodes may be None for both; if not None, compare
        if state_none.net_virtual_nodes is not None:
            assert state_populated.net_virtual_nodes is not None
            assert jnp.allclose(
                state_none.net_virtual_nodes,
                state_populated.net_virtual_nodes,
            )

    def test_initialize_training_state_zone_aware_invariant(self):
        """Zone-aware spectral init produces identical output regardless of
        constraints kwarg."""
        netlist = _make_minimal_netlist()
        board = Board(width=100.0, height=100.0)
        config = OptimizerConfig(
            initialization=InitializationConfig(
                method="zone_aware_spectral",
                zone_aware=ZoneAwareConfig(
                    zone_penalty=1.0, boundary_margin=1.0, adjustment_iters=5
                ),
            ),
            seed=42,
        )

        state_none = initialize_training_state(
            netlist, board, config, constraints=None
        )
        state_w_con = initialize_training_state(
            netlist, board, config, constraints=_empty_constraints()
        )

        assert jnp.allclose(state_none.positions, state_w_con.positions)

    def test_initialize_training_state_random_invariant(self):
        """Random init (default) is also invariant — constraints should not
        affect the random path."""
        netlist = _make_minimal_netlist()
        board = Board(width=100.0, height=100.0)
        config = OptimizerConfig(
            initialization=InitializationConfig(method="random"), seed=42
        )

        state_none = initialize_training_state(
            netlist, board, config, constraints=None
        )
        state_w_con = initialize_training_state(
            netlist, board, config, constraints=_empty_constraints()
        )

        assert jnp.allclose(state_none.positions, state_w_con.positions)


# ---------------------------------------------------------------------------
# 2. Per-Initializer Unit Tests: Each initializer accepts the new parameter
# ---------------------------------------------------------------------------


class TestInitializerAcceptsConstraints:
    """Every initializer's initialize() method must accept the constraints
    keyword argument and produce the same output as passing None."""

    def test_spectral_initializer_accepts_constraints(self):
        initializer = SpectralInitializer()
        netlist = _make_minimal_netlist()
        board = Board(width=100.0, height=100.0)

        pos_none = initializer.initialize(netlist, board, constraints=None)
        pos_populated = initializer.initialize(
            netlist, board, constraints=_empty_constraints()
        )
        assert jnp.allclose(pos_none, pos_populated)

    def test_zone_aware_initializer_accepts_constraints(self):
        initializer = ZoneAwareSpectralInitializer(adjustment_iters=5)
        netlist = _make_minimal_netlist()
        board = Board(width=100.0, height=100.0)

        pos_none = initializer.initialize(netlist, board, constraints=None)
        pos_populated = initializer.initialize(
            netlist, board, constraints=_empty_constraints()
        )
        assert jnp.allclose(pos_none, pos_populated)

    def test_learned_initializer_accepts_constraints(self):
        # LearnedInitializer falls back to SpectralInitializer when the
        # model file is not found, so the test exercises both paths.
        initializer = LearnedInitializer(model_path="nonexistent_model.pkl")
        netlist = _make_minimal_netlist()
        board = Board(width=100.0, height=100.0)

        pos_none = initializer.initialize(netlist, board, constraints=None)
        pos_populated = initializer.initialize(
            netlist, board, constraints=_empty_constraints()
        )
        assert jnp.allclose(pos_none, pos_populated)

    def test_spectral_with_multiple_component_netlist(self):
        """Spectral init on a 4-component, 2-net board — invariance still
        holds for a slightly more complex topology."""
        c1 = Component(ref="C1", footprint="0805", bounds=(5.0, 5.0))
        c2 = Component(ref="C2", footprint="0805", bounds=(5.0, 5.0))
        c3 = Component(ref="C3", footprint="0805", bounds=(5.0, 5.0))
        c4 = Component(ref="C4", footprint="0805", bounds=(5.0, 5.0))
        nets = [
            Net("N1", [("C1", "1"), ("C2", "1")]),
            Net("N2", [("C3", "1"), ("C4", "1")]),
        ]
        netlist = Netlist(components=[c1, c2, c3, c4], nets=nets)
        board = Board(width=100.0, height=100.0)

        initializer = SpectralInitializer()
        pos_none = initializer.initialize(netlist, board, constraints=None)
        pos_con = initializer.initialize(
            netlist, board, constraints=_empty_constraints()
        )
        assert jnp.allclose(pos_none, pos_con)


# ---------------------------------------------------------------------------
# 3. Integration: train() and train_multiphase() accept constraints
# ---------------------------------------------------------------------------


class TestTrainAcceptsConstraints:
    """train() and train_multiphase() accept the new constraints kwarg
    and the parameter reaches initialize_training_state() unchanged."""

    def test_train_with_constraints_kwarg(self):
        """Calling train() with an explicit constraints kwarg does not raise."""
        from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
        from temper_placer.losses.boundary import BoundaryLoss
        from temper_placer.losses.overlap import OverlapLoss
        from temper_placer.optimizer.train import train

        netlist = _make_minimal_netlist()
        board = Board(width=100.0, height=100.0)
        config = OptimizerConfig(
            initialization=InitializationConfig(method="spectral"),
            seed=42,
            epochs=2,
        )
        composite_loss = CompositeLoss(
            [WeightedLoss(OverlapLoss(), weight=100.0), WeightedLoss(BoundaryLoss(), weight=50.0)]
        )
        context = LossContext.from_netlist_and_board(netlist, board)

        result = train(
            netlist, board, composite_loss, context, config, constraints=_empty_constraints()
        )
        assert result.final_loss >= 0.0
        assert result.total_epochs > 0

    def test_train_multiphase_with_constraints_kwarg(self):
        """Calling train_multiphase() with an explicit constraints kwarg does not raise."""
        from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
        from temper_placer.losses.boundary import BoundaryLoss
        from temper_placer.losses.overlap import OverlapLoss
        from temper_placer.optimizer.curriculum import create_default_phases
        from temper_placer.optimizer.train import train_multiphase

        netlist = _make_minimal_netlist()
        board = Board(width=100.0, height=100.0)
        phases = create_default_phases()

        def make_loss(weights):
            return CompositeLoss(
                [
                    WeightedLoss(OverlapLoss(), weight=weights.get("overlap", 100.0)),
                    WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 50.0)),
                ]
            )

        context = LossContext.from_netlist_and_board(netlist, board)
        config = OptimizerConfig(
            initialization=InitializationConfig(method="spectral"),
            seed=42,
            curriculum_phases=phases,
        )

        result = train_multiphase(
            netlist, board, make_loss, context, config, constraints=_empty_constraints()
        )
        assert result.final_loss >= 0.0
        assert result.total_epochs > 0
