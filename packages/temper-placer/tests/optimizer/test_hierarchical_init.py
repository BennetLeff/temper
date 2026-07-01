"""
Tests for HierarchicalGroupInitializer — hierarchical group pre-clustering.

Phase A: Configuration and scaffolding tests.
Phase B: Micro-placement tests.
Phase C: Coarsening tests.
Phase D: Embedding + explosion tests.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.config_loader import (
    ComponentGroup,
    GroupSeparation,
    PlacementConstraints,
)
from temper_placer.optimizer.initialization import (
    HierarchicalGroupInitializer,
    SpectralInitializer,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

BOARD = Board(width=100.0, height=100.0)


def _make_component(ref: str, fixed: bool = False, pos: tuple | None = None) -> Component:
    return Component(
        ref=ref,
        footprint="0805",
        bounds=(5.0, 5.0),
        pins=[Pin("1", "1", (0, 0))],
        fixed=fixed,
        initial_position=pos,
    )


def _make_netlist(n_components: int, add_nets: bool = True) -> Netlist:
    comps = [_make_component(f"C{i+1}") for i in range(n_components)]
    nets = []
    if add_nets and n_components > 1:
        for i in range(n_components - 1):
            nets.append(Net(f"N{i+1}", [(f"C{i+1}", "1"), (f"C{i+2}", "1")]))
    return Netlist(components=comps, nets=nets)


# ---------------------------------------------------------------------------
# Phase A: Scaffolding Tests
# ---------------------------------------------------------------------------


class TestFallbackToSpectral:
    """Graceful fallback when no component_groups are defined."""

    def test_fallback_empty_groups(self):
        """Empty component_groups → falls back to SpectralInitializer."""
        netlist = _make_netlist(4)
        constraints = PlacementConstraints(component_groups=[])
        init = HierarchicalGroupInitializer()
        positions = init.initialize(netlist, BOARD, constraints)

        # Should match spectral init
        spectral = SpectralInitializer()
        expected = spectral.initialize(netlist, BOARD)
        assert jnp.allclose(positions, expected)

    def test_fallback_none_constraints(self):
        """None constraints → falls back to SpectralInitializer."""
        netlist = _make_netlist(4)
        init = HierarchicalGroupInitializer()
        positions = init.initialize(netlist, BOARD, constraints=None)

        spectral = SpectralInitializer()
        expected = spectral.initialize(netlist, BOARD)
        assert jnp.allclose(positions, expected)

    def test_empty_netlist(self):
        """Empty netlist → returns (0, 2)."""
        netlist = Netlist(components=[], nets=[])
        init = HierarchicalGroupInitializer()
        positions = init.initialize(netlist, BOARD)
        assert positions.shape == (0, 2)


class TestConfiguration:
    """Configuration flag gating."""

    def test_group_preclustering_config_field(self):
        """group_preclustering config field exists in InitializationConfig."""
        from temper_placer.optimizer.config import InitializationConfig

        cfg = InitializationConfig()
        assert hasattr(cfg, "group_preclustering")
        assert cfg.group_preclustering is False

    def test_initialize_with_single_group(self):
        """Single small group → pre-clustering path used."""
        netlist = _make_netlist(3)
        group = ComponentGroup(
            name="test_group",
            components=["C1", "C2", "C3"],
            max_spread_mm=30.0,
        )
        constraints = PlacementConstraints(component_groups=[group])
        init = HierarchicalGroupInitializer(force_iterations=50)
        positions = init.initialize(netlist, BOARD, constraints)

        assert positions.shape == (3, 2)
        # All positions should be valid (finite)
        assert jnp.all(jnp.isfinite(positions))
        # Positions should be within board bounds
        assert jnp.all(positions >= 0.0)
        assert jnp.all(positions[:, 0] <= BOARD.width)
        assert jnp.all(positions[:, 1] <= BOARD.height)


class TestDiagnostics:
    """Diagnostic messages are populated."""

    def test_diagnostics_populated(self):
        """Initialize populates diagnostics list."""
        netlist = _make_netlist(2)
        group = ComponentGroup(
            name="test_group",
            components=["C1", "C2"],
            max_spread_mm=20.0,
        )
        constraints = PlacementConstraints(component_groups=[group])
        init = HierarchicalGroupInitializer(force_iterations=50)
        init.initialize(netlist, BOARD, constraints)
        assert len(init.diagnostics) > 0
        assert any("Pre-clustered" in d for d in init.diagnostics)
        assert any("Phase 1" in d for d in init.diagnostics)
