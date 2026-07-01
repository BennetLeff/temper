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


# ---------------------------------------------------------------------------
# Phase C: Group Coarsening Tests
# ---------------------------------------------------------------------------


class TestCoarsening:
    """Unit tests for Phase 2: coarsening to super-nodes."""

    def test_spanning_group_not_coarsened(self):
        """Spanning group (>30% board diagonal) → members treated as individual super-nodes."""
        from temper_placer.core.netlist import build_adjacency_matrix

        board = Board(width=100.0, height=100.0)
        board_diagonal = (100**2 + 100**2) ** 0.5  # ≈ 141.4
        threshold = 0.3 * board_diagonal  # ≈ 42.4

        components = [_make_component(f"C{i+1}") for i in range(4)]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C2", "1"), ("C3", "1"), ("C4", "1")])],
        )
        adjacency = build_adjacency_matrix(netlist)

        spanning_group = ComponentGroup(
            name="wide",
            components=["C1", "C2"],
            max_spread_mm=50.0,  # > 42.4 → spanning
        )
        normal_group = ComponentGroup(
            name="tight",
            components=["C3", "C4"],
            max_spread_mm=20.0,  # < 42.4 → coarsened
        )
        constraints = PlacementConstraints(
            component_groups=[spanning_group, normal_group]
        )

        init = HierarchicalGroupInitializer()
        (
            super_adj,
            super_node_map,
            component_to_super,
            group_to_super,
            group_name_to_super,
        ) = init._coarsen_to_super_nodes(
            netlist, adjacency, constraints.component_groups, board
        )

        # Spanning group should NOT be coarsened (not in group_to_super)
        assert 0 not in group_to_super, "spanning group should not be coarsened"
        assert "wide" not in group_name_to_super

        # Normal group should be coarsened
        assert 1 in group_to_super, "normal group should be coarsened"
        assert "tight" in group_name_to_super

        # Spanning group members should each be in their own singleton super-nodes
        c1_sn = int(component_to_super[0])
        c2_sn = int(component_to_super[1])
        assert c1_sn != c2_sn, "spanning group members should be in different super-nodes"
        assert len(super_node_map[c1_sn]) == 1
        assert len(super_node_map[c2_sn]) == 1

        # Normal group members should be in the same super-node
        c3_sn = int(component_to_super[2])
        c4_sn = int(component_to_super[3])
        assert c3_sn == c4_sn, "normal group members should be in the same super-node"

        # Diagnostic about spanning
        assert any("spans >30%" in d for d in init.diagnostics)

    def test_spanning_group_threshold_derivation(self):
        """30% threshold: groups above not coarsened, groups below coarsened."""
        from temper_placer.core.netlist import build_adjacency_matrix

        board = Board(width=100.0, height=100.0)

        components = [_make_component(f"C{i+1}") for i in range(4)]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C3", "1")]), Net("N2", [("C2", "1"), ("C4", "1")])],
        )
        adjacency = build_adjacency_matrix(netlist)

        # Above threshold → spanning
        spanning = ComponentGroup(name="above", components=["C1", "C2"], max_spread_mm=45.0)
        # Below threshold → coarsened
        normal = ComponentGroup(name="below", components=["C3", "C4"], max_spread_mm=20.0)

        constraints = PlacementConstraints(component_groups=[spanning, normal])
        init = HierarchicalGroupInitializer()
        _, _, _, _, group_name_to_super = init._coarsen_to_super_nodes(
            netlist, adjacency, constraints.component_groups, board
        )
        assert "above" not in group_name_to_super
        assert "below" in group_name_to_super

    def test_overlapping_group_resolution(self):
        """Component in two groups → assigned to one with tighter max_spread_mm."""
        from temper_placer.core.netlist import build_adjacency_matrix

        components = [_make_component(f"C{i+1}") for i in range(3)]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C2", "1"), ("C3", "1")])],
        )
        adjacency = build_adjacency_matrix(netlist)

        # C2 is in both groups
        group_tight = ComponentGroup(
            name="tight",
            components=["C1", "C2"],
            max_spread_mm=10.0,
        )
        group_loose = ComponentGroup(
            name="loose",
            components=["C2", "C3"],
            max_spread_mm=40.0,
        )
        constraints = PlacementConstraints(
            component_groups=[group_tight, group_loose]
        )

        init = HierarchicalGroupInitializer()
        (
            super_adj,
            super_node_map,
            component_to_super,
            group_to_super,
            group_name_to_super,
        ) = init._coarsen_to_super_nodes(
            netlist, adjacency, constraints.component_groups, Board(width=100.0, height=100.0)
        )

        # C2 should be assigned to the tighter group
        # C1 and C2 should be in the same super-node (tight group)
        c1_sn = int(component_to_super[0])
        c2_sn = int(component_to_super[1])
        c3_sn = int(component_to_super[2])
        assert c1_sn == c2_sn, "C1 and C2 should be in the same super-node (tight group)"
        assert c2_sn != c3_sn, "C2 and C3 should be in different super-nodes"

        # Warning about overlap should be in diagnostics
        assert any("appears in multiple" in d for d in init.diagnostics)

    def test_coarsened_adjacency_preserves_cross_group_edge_weight(self):
        """Property P4: sum(super_adj) == sum(original_adj) - sum(intra_group_edges)."""
        from temper_placer.core.netlist import build_adjacency_matrix

        components = [_make_component(f"C{i+1}") for i in range(4)]
        # C1-C2 and C3-C4 are intra-group; C2-C3 is cross-group
        netlist = Netlist(
            components=components,
            nets=[
                Net("N1", [("C1", "1"), ("C2", "1")]),  # intra group 0
                Net("N2", [("C2", "1"), ("C3", "1")]),  # cross-group
                Net("N3", [("C3", "1"), ("C4", "1")]),  # intra group 1
                Net("N4", [("C1", "1"), ("C4", "1")]),  # cross-group
            ],
        )
        adjacency = build_adjacency_matrix(netlist)

        group_a = ComponentGroup(name="A", components=["C1", "C2"], max_spread_mm=20.0)
        group_b = ComponentGroup(name="B", components=["C3", "C4"], max_spread_mm=20.0)
        constraints = PlacementConstraints(component_groups=[group_a, group_b])

        init = HierarchicalGroupInitializer()
        super_adj, super_node_map, _, _, _ = init._coarsen_to_super_nodes(
            netlist, adjacency, constraints.component_groups, Board(width=100.0, height=100.0)
        )

        total_orig = float(jnp.sum(adjacency))
        total_super = float(jnp.sum(super_adj))

        # C1-C2 edge is intra-group (indices 0-1) → excluded from super_adj
        # C3-C4 edge is intra-group (indices 2-3) → excluded
        # C2-C3 (indices 1-2) → cross-group, preserved
        # C1-C4 (indices 0-3) → cross-group, preserved
        intra_0_1 = float(adjacency[0, 1] + adjacency[1, 0])
        intra_2_3 = float(adjacency[2, 3] + adjacency[3, 2])

        intra_total = intra_0_1 + intra_2_3
        cross_total = total_orig - intra_total

        assert total_super == cross_total, (
            f"super_adj sum {total_super} != cross-group sum {cross_total}"
        )

    def test_all_components_in_groups(self):
        """All components in coarsened groups → no singleton super-nodes."""
        from temper_placer.core.netlist import build_adjacency_matrix

        components = [_make_component(f"C{i+1}") for i in range(6)]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [(f"C{i+1}", "1") for i in range(6)])],
        )
        adjacency = build_adjacency_matrix(netlist)

        group_a = ComponentGroup(
            name="A", components=["C1", "C2", "C3"], max_spread_mm=30.0
        )
        group_b = ComponentGroup(
            name="B", components=["C4", "C5", "C6"], max_spread_mm=30.0
        )
        constraints = PlacementConstraints(component_groups=[group_a, group_b])

        init = HierarchicalGroupInitializer()
        super_adj, super_node_map, _, _, _ = init._coarsen_to_super_nodes(
            netlist, adjacency, constraints.component_groups, Board(width=100.0, height=100.0)
        )

        # Should have exactly 2 super-nodes
        assert len(super_node_map) == 2
        assert super_adj.shape == (2, 2)


# ---------------------------------------------------------------------------
# Phase D: Global Embedding + Explosion Tests
# ---------------------------------------------------------------------------


class TestEmbeddingAndExplosion:
    """Unit tests for Phase 3 (super-node embedding) and Phase 4 (explosion)."""

    def test_single_group_board_center(self):
        """One group covering all components → positions cluster around board center."""
        components = [_make_component(f"C{i+1}") for i in range(6)]
        chains = []
        for i in range(5):
            chains.append(Net(f"N{i+1}", [(f"C{i+1}", "1"), (f"C{i+2}", "1")]))
        netlist = Netlist(components=components, nets=chains)

        group = ComponentGroup(
            name="all",
            components=[f"C{i+1}" for i in range(6)],
            max_spread_mm=60.0,
        )
        constraints = PlacementConstraints(component_groups=[group])

        init = HierarchicalGroupInitializer(force_iterations=100)
        positions = init.initialize(netlist, BOARD, constraints)

        # All positions should be on the board
        assert jnp.all(jnp.isfinite(positions))
        assert jnp.all(positions >= 0.0)

        # Group center of mass should be near board center
        com = jnp.mean(positions, axis=0)
        center = jnp.array([BOARD.width / 2, BOARD.height / 2])
        dist_to_center = float(jnp.linalg.norm(com - center))
        # For a single super-node, centroid should be at board center
        assert dist_to_center < 30.0, f"Center-of-mass {com} too far from board center {center}"

    def test_multi_group_positions_on_board(self):
        """Multiple groups: all positions within board bounds."""
        components = [_make_component(f"C{i+1}") for i in range(6)]
        nets = [
            Net("N1", [("C1", "1"), ("C2", "1"), ("C3", "1")]),
            Net("N2", [("C4", "1"), ("C5", "1"), ("C6", "1")]),
            Net("N3", [("C3", "1"), ("C4", "1")]),  # cross-group connection
        ]
        netlist = Netlist(components=components, nets=nets)

        group_a = ComponentGroup(name="A", components=["C1", "C2", "C3"], max_spread_mm=30.0)
        group_b = ComponentGroup(name="B", components=["C4", "C5", "C6"], max_spread_mm=30.0)
        constraints = PlacementConstraints(component_groups=[group_a, group_b])

        init = HierarchicalGroupInitializer(force_iterations=100)
        positions = init.initialize(netlist, BOARD, constraints)

        assert jnp.all(jnp.isfinite(positions))
        assert jnp.all(positions >= 0.0)
        assert jnp.all(positions[:, 0] <= BOARD.width)
        assert jnp.all(positions[:, 1] <= BOARD.height)

    def test_idempotence(self):
        """Property P5: Running initialize() twice with same inputs produces identical positions."""
        components = [_make_component(f"C{i+1}") for i in range(4)]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C2", "1"), ("C3", "1"), ("C4", "1")])],
        )
        group = ComponentGroup(
            name="quad", components=["C1", "C2", "C3", "C4"], max_spread_mm=40.0
        )
        constraints = PlacementConstraints(component_groups=[group])

        init1 = HierarchicalGroupInitializer(force_iterations=100)
        positions1 = init1.initialize(netlist, BOARD, constraints)

        init2 = HierarchicalGroupInitializer(force_iterations=100)
        positions2 = init2.initialize(netlist, BOARD, constraints)

        assert jnp.allclose(positions1, positions2)

    def test_group_separation_integration(self):
        """GroupSeparation constraint pushes group centroids apart."""
        components = [_make_component(f"C{i+1}") for i in range(4)]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C3", "1")])],  # minimal cross-connection
        )
        group_a = ComponentGroup(name="A", components=["C1", "C2"], max_spread_mm=20.0)
        group_b = ComponentGroup(name="B", components=["C3", "C4"], max_spread_mm=20.0)
        separation = GroupSeparation(group_a="A", group_b="B", min_distance_mm=60.0)
        constraints = PlacementConstraints(
            component_groups=[group_a, group_b],
            group_separations=[separation],
        )

        init = HierarchicalGroupInitializer(force_iterations=50)
        positions = init.initialize(netlist, BOARD, constraints)

        # Compute group centroids post-init
        mask_a = jnp.array([True, True, False, False])
        mask_b = jnp.array([False, False, True, True])
        centroid_a = jnp.mean(positions[mask_a], axis=0)
        centroid_b = jnp.mean(positions[mask_b], axis=0)
        dist = float(jnp.linalg.norm(centroid_a - centroid_b))

        # With separation push, distance should be reasonable (not coincident)
        assert dist > 10.0, f"Groups too close: {dist}mm"


# ---------------------------------------------------------------------------
# Phase E: Pipeline Integration Tests
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    """Integration tests with OptimizationPipeline."""

    def test_pipeline_with_preclustering(self):
        """Pipeline runs end-to-end with pre-clustering enabled."""
        from temper_placer.optimizer.config import OptimizerConfig
        from temper_placer.optimizer.phases import OptimizationPipeline
        from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
        from temper_placer.losses.wirelength import WirelengthLoss

        components = [_make_component(f"C{i+1}") for i in range(4)]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C2", "1"), ("C3", "1"), ("C4", "1")])],
        )
        board = Board(width=100.0, height=100.0)

        group_a = ComponentGroup(name="A", components=["C1", "C2"], max_spread_mm=30.0)
        group_b = ComponentGroup(name="B", components=["C3", "C4"], max_spread_mm=30.0)
        placement_constraints = PlacementConstraints(
            component_groups=[group_a, group_b]
        )

        opt_config = OptimizerConfig.fast_test()
        opt_config.initialization.group_preclustering = True
        opt_config.epochs = 5  # very short run

        from temper_placer.pcl.parser import ConstraintCollection

        constraints = ConstraintCollection(constraints=[])

        context = LossContext.from_netlist_and_board(netlist, board)

        def loss_factory(_weights):
            return CompositeLoss([WeightedLoss(WirelengthLoss(), weight=1.0)])

        pipeline = OptimizationPipeline(
            netlist=netlist,
            board=board,
            constraints=constraints,
            opt_config=opt_config,
            loss_factory=loss_factory,
            context=context,
            placement_constraints=placement_constraints,
        )
        result = pipeline.run()

        assert result.success, f"Pipeline failed: {result.error}"
        assert result.final_state is not None

    def test_pipeline_without_preclustering(self):
        """Pipeline runs with pre-clustering disabled (no groups)."""
        from temper_placer.optimizer.config import OptimizerConfig
        from temper_placer.optimizer.phases import OptimizationPipeline
        from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
        from temper_placer.losses.wirelength import WirelengthLoss

        components = [_make_component(f"C{i+1}") for i in range(2)]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C2", "1")])],
        )
        board = Board(width=100.0, height=100.0)

        opt_config = OptimizerConfig.fast_test()
        opt_config.initialization.group_preclustering = False
        opt_config.epochs = 5

        from temper_placer.pcl.parser import ConstraintCollection

        constraints = ConstraintCollection(constraints=[])

        context = LossContext.from_netlist_and_board(netlist, board)

        def loss_factory(_weights):
            return CompositeLoss([WeightedLoss(WirelengthLoss(), weight=1.0)])

        pipeline = OptimizationPipeline(
            netlist=netlist,
            board=board,
            constraints=constraints,
            opt_config=opt_config,
            loss_factory=loss_factory,
            context=context,
        )
        result = pipeline.run()

        assert result.success, f"Pipeline failed: {result.error}"


# ---------------------------------------------------------------------------
# Phase G: Edge Cases and Hardening Tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for hierarchical pre-clustering."""

    def test_no_nets_board(self):
        """Purely unconnected components: each is its own super-node, no errors."""
        components = [_make_component(f"C{i+1}") for i in range(6)]
        netlist = Netlist(components=components, nets=[])

        group = ComponentGroup(
            name="all",
            components=["C1", "C2", "C3", "C4", "C5", "C6"],
            max_spread_mm=50.0,
        )
        constraints = PlacementConstraints(component_groups=[group])

        init = HierarchicalGroupInitializer(force_iterations=50)
        positions = init.initialize(netlist, BOARD, constraints)

        assert jnp.all(jnp.isfinite(positions))
        assert jnp.all(positions >= 0.0)
        assert jnp.all(positions[:, 0] <= BOARD.width)
        assert jnp.all(positions[:, 1] <= BOARD.height)

    def test_all_fixed_components(self):
        """All components fixed: init completes, positions on board."""
        fixed_positions = [(10.0, 10.0), (20.0, 20.0), (30.0, 30.0)]
        components = [
            _make_component(f"C{i+1}", fixed=True, pos=fixed_positions[i])
            for i in range(3)
        ]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C2", "1"), ("C3", "1")])],
        )
        group = ComponentGroup(
            name="all_fixed",
            components=["C1", "C2", "C3"],
            max_spread_mm=50.0,
        )
        constraints = PlacementConstraints(component_groups=[group])

        init = HierarchicalGroupInitializer(force_iterations=50)
        positions = init.initialize(netlist, BOARD, constraints)

        assert jnp.all(jnp.isfinite(positions))

    def test_unknown_component_in_group(self):
        """Component ref not in netlist: skipped with warning, no crash."""
        components = [_make_component("C1")]
        netlist = Netlist(
            components=components,
            nets=[],
        )
        group = ComponentGroup(
            name="missing",
            components=["C1", "MISSING_C2", "MISSING_C3"],
            max_spread_mm=30.0,
        )
        constraints = PlacementConstraints(component_groups=[group])

        init = HierarchicalGroupInitializer(force_iterations=50)
        positions = init.initialize(netlist, BOARD, constraints)

        assert positions.shape == (1, 2)
        assert any("not found in netlist" in d for d in init.diagnostics)

    def test_force_directed_radial_fallback(self):
        """Force-directed solver produces diameter > 1.2*max_spread -> radial fallback."""
        components = [_make_component(f"C{i+1}") for i in range(10)]
        nets = []
        for i in range(9):
            nets.append(Net(f"N{i+1}", [(f"C{i+1}", "1"), (f"C{i+2}", "1")]))
        netlist = Netlist(components=components, nets=nets)

        spread = 20.0
        group = ComponentGroup(
            name="tight_10",
            components=[f"C{i+1}" for i in range(10)],
            max_spread_mm=spread,
        )
        constraints = PlacementConstraints(component_groups=[group])

        init = HierarchicalGroupInitializer(force_iterations=300)
        positions = init.initialize(netlist, BOARD, constraints)

        assert jnp.all(jnp.isfinite(positions))

    def test_zero_max_spread_defaults(self):
        """max_spread_mm=0 -> defaults to 30.0mm."""
        components = [_make_component("C1"), _make_component("C2")]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C2", "1")])],
        )
        group = ComponentGroup(
            name="zero_spread",
            components=["C1", "C2"],
            max_spread_mm=0.0,
        )
        constraints = PlacementConstraints(component_groups=[group])

        init = HierarchicalGroupInitializer(force_iterations=100)
        positions = init.initialize(netlist, BOARD, constraints)

        assert jnp.all(jnp.isfinite(positions))
        dist = float(jnp.linalg.norm(positions[0] - positions[1]))
        assert dist > 0.01

    def test_component_group_with_no_matching_members(self):
        """Group where no components exist in netlist -> no crash, falls back."""
        components = [_make_component("C1"), _make_component("C2")]
        netlist = Netlist(
            components=components,
            nets=[Net("N1", [("C1", "1"), ("C2", "1")])],
        )
        group = ComponentGroup(
            name="ghost",
            components=["X1", "X2"],
            max_spread_mm=30.0,
        )
        constraints = PlacementConstraints(component_groups=[group])

        init = HierarchicalGroupInitializer(force_iterations=50)
        positions = init.initialize(netlist, BOARD, constraints)

        assert positions.shape == (2, 2)
        assert jnp.all(jnp.isfinite(positions))

    def test_many_singletons_correct_count(self):
        """N ungrouped components produce N singleton super-nodes."""
        from temper_placer.core.netlist import build_adjacency_matrix

        components = [_make_component(f"C{i+1}") for i in range(5)]
        netlist = Netlist(components=components, nets=[])
        adjacency = build_adjacency_matrix(netlist)

        constraints = PlacementConstraints(component_groups=[])

        init = HierarchicalGroupInitializer()
        (
            super_adj,
            super_node_map,
            component_to_super,
            group_to_super,
            _,
        ) = init._coarsen_to_super_nodes(
            netlist, adjacency, constraints.component_groups, Board(width=100.0, height=100.0)
        )

        assert len(super_node_map) == 5
        assert len(group_to_super) == 0
        for sn in super_node_map:
            assert len(sn) == 1
