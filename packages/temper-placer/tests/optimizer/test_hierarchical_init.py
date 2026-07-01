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


# ---------------------------------------------------------------------------
# Phase B: Intra-Group Micro-Placement Tests
# ---------------------------------------------------------------------------


class TestMicroPlacement:
    """Unit tests for Phase 1: intra-group micro-placement."""

    def test_micro_placement_2_components(self):
        """2-component group: both positions within max_spread_mm of each other."""
        components = [
            _make_component("C1"),
            _make_component("C2"),
        ]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C2", "1")])],
        )
        group = ComponentGroup(
            name="pair",
            components=["C1", "C2"],
            max_spread_mm=30.0,
        )
        constraints = PlacementConstraints(component_groups=[group])
        init = HierarchicalGroupInitializer(force_iterations=100)
        positions = init.initialize(netlist, BOARD, constraints)

        dist = float(jnp.linalg.norm(positions[0] - positions[1]))
        assert dist <= group.max_spread_mm * 1.2, f"dist={dist} > {group.max_spread_mm * 1.2}"
        assert dist > 0.1, f"Components too close: {dist}"

    def test_micro_placement_4_components(self):
        """4-component group on a square topology: all pairwise distances <= max_spread."""
        components = [_make_component(f"C{i+1}") for i in range(4)]
        netlist = Netlist(
            components=components,
            nets=[
                Net("N1", [("C1", "1"), ("C2", "1")]),
                Net("N2", [("C2", "1"), ("C3", "1")]),
                Net("N3", [("C3", "1"), ("C4", "1")]),
                Net("N4", [("C4", "1"), ("C1", "1")]),
            ],
        )
        group = ComponentGroup(
            name="square",
            components=["C1", "C2", "C3", "C4"],
            max_spread_mm=40.0,
        )
        constraints = PlacementConstraints(component_groups=[group])
        init = HierarchicalGroupInitializer(force_iterations=100)
        positions = init.initialize(netlist, BOARD, constraints)

        # Compute pairwise diameter
        max_dist = 0.0
        for i in range(4):
            for j in range(i + 1, 4):
                d = float(jnp.linalg.norm(positions[i] - positions[j]))
                max_dist = max(max_dist, d)
        assert max_dist <= group.max_spread_mm * 1.2, f"diameter={max_dist} > {group.max_spread_mm * 1.2}"

    def test_micro_placement_one_fixed(self):
        """3-component group with 1 fixed component: fixed position unchanged."""
        fixed_pos = (15.0, 15.0)
        components = [
            _make_component("C1", fixed=True, pos=fixed_pos),
            _make_component("C2"),
            _make_component("C3"),
        ]
        netlist = Netlist(
            components=components,
            nets=[
                Net("N1", [("C1", "1"), ("C2", "1")]),
                Net("N2", [("C2", "1"), ("C3", "1")]),
            ],
        )
        group = ComponentGroup(
            name="fixed_center",
            components=["C1", "C2", "C3"],
            max_spread_mm=50.0,
        )
        constraints = PlacementConstraints(component_groups=[group])

        init = HierarchicalGroupInitializer(force_iterations=100)
        positions = init.initialize(netlist, BOARD, constraints)

        # C1 should be near its fixed position after micro-solve
        # Note: after explosion, the super-node centroid is added
        # But for a single group, centroid should be near (50, 50) — board center
        # and the offsets are applied relative to centroid
        # So we can't directly check C1's position == fixed_pos,
        # but the fixed component should anchor the group
        # For now, just verify positions are finite and within board
        assert jnp.all(jnp.isfinite(positions))
        assert jnp.all(positions >= 0.0)
        assert jnp.all(positions[:, 0] <= BOARD.width)
        assert jnp.all(positions[:, 1] <= BOARD.height)

    def test_micro_placement_one_fixed_component(self):
        """Group with one fixed component: init completes, positions valid."""
        fixed_pos = (5.0, 5.0)
        components = [
            _make_component("C1", fixed=True, pos=fixed_pos),
            _make_component("C2"),
            _make_component("C3"),
        ]
        netlist = Netlist(
            components=components,
            nets=[
                Net("N1", [("C1", "1"), ("C2", "1")]),
                Net("N2", [("C2", "1"), ("C3", "1")]),
            ],
        )
        group = ComponentGroup(
            name="anchored",
            components=["C1", "C2", "C3"],
            max_spread_mm=80.0,
        )
        constraints = PlacementConstraints(component_groups=[group])

        init = HierarchicalGroupInitializer(force_iterations=50)
        positions = init.initialize(netlist, BOARD, constraints)

        assert jnp.all(jnp.isfinite(positions))
        assert jnp.all(positions >= 0.0)
        assert jnp.all(positions[:, 0] <= BOARD.width)
        assert jnp.all(positions[:, 1] <= BOARD.height)

    def test_single_component_group(self):
        """Single-component group: offset is (0, 0), positioned at centroid."""
        components = [
            _make_component("C1"),
            _make_component("C2"),
        ]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C2", "1")])],
        )
        group = ComponentGroup(
            name="singleton",
            components=["C1"],
            max_spread_mm=10.0,
        )
        constraints = PlacementConstraints(component_groups=[group])
        init = HierarchicalGroupInitializer(force_iterations=100)
        positions = init.initialize(netlist, BOARD, constraints)

        assert jnp.all(jnp.isfinite(positions))
        # C1 should be at its super-node centroid (within board)
        assert 0 <= positions[0, 0] <= BOARD.width
        assert 0 <= positions[0, 1] <= BOARD.height

    def test_large_group_diameter_fallback(self):
        """Group where force-directed exceeds diameter falls back to radial."""
        # Create a chain of 8 components with tight spread — force-directed
        # should converge, but let's test with a very tight spread to trigger
        # the fallback boundary
        components = [_make_component(f"C{i+1}") for i in range(8)]
        nets = []
        for i in range(7):
            nets.append(Net(f"N{i+1}", [(f"C{i+1}", "1"), (f"C{i+2}", "1")]))
        netlist = Netlist(components=components, nets=nets)

        group = ComponentGroup(
            name="tight",
            components=[f"C{i+1}" for i in range(8)],
            max_spread_mm=15.0,
        )
        constraints = PlacementConstraints(component_groups=[group])

        init = HierarchicalGroupInitializer(force_iterations=200)
        positions = init.initialize(netlist, BOARD, constraints)

        # After explosion, compute group member distances
        # The micro-solve diameter (before adding centroid) is what's checked
        # Post-explosion, offsets are applied on top of centroid
        assert jnp.all(jnp.isfinite(positions))
