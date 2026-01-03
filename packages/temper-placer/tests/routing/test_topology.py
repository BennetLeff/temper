"""Tests for power net topology analysis.

Part of temper-glwf
"""

import pytest

from temper_placer.routing.topology import (
    UnionFind,
    PowerPad,
    Island,
    detect_islands,
    compute_stitching_vias,
)


class TestUnionFind:
    """Tests for Union-Find data structure."""

    def test_initial_find(self):
        """Each element starts as its own root."""
        uf = UnionFind()
        assert uf.find(1) == 1
        assert uf.find(2) == 2

    def test_union(self):
        """Union merges components."""
        uf = UnionFind()
        assert uf.union(1, 2) is True
        assert uf.connected(1, 2)

    def test_union_already_connected(self):
        """Union of same component returns False."""
        uf = UnionFind()
        uf.union(1, 2)
        assert uf.union(1, 2) is False

    def test_get_components(self):
        """Components groups all connected elements."""
        uf = UnionFind()
        uf.union(1, 2)
        uf.union(3, 4)
        uf.find(5)  # Singleton
        
        components = uf.get_components()
        assert len(components) == 3


class TestIslandDetection:
    """Tests for island detection."""

    def test_no_pads_returns_empty(self):
        """Empty input returns empty."""
        assert detect_islands([]) == []

    def test_single_pad_is_single_island(self):
        """One pad = one island."""
        pad = PowerPad(id=0, x=10, y=10, layer=0, net="GND", component="C1")
        islands = detect_islands([pad])
        
        assert len(islands) == 1
        assert len(islands[0].pads) == 1

    def test_separate_layers_are_separate_islands(self):
        """Pads on different layers are not connected."""
        p1 = PowerPad(id=0, x=10, y=10, layer=0, net="GND", component="C1")
        p2 = PowerPad(id=1, x=10, y=10, layer=1, net="GND", component="C2")
        
        islands = detect_islands([p1, p2])
        assert len(islands) == 2

    def test_nearby_same_layer_connected(self):
        """Pads within radius on same layer are connected."""
        p1 = PowerPad(id=0, x=10, y=10, layer=0, net="GND", component="C1")
        p2 = PowerPad(id=1, x=10.5, y=10, layer=0, net="GND", component="C2")
        
        islands = detect_islands([p1, p2], connection_radius=1.0)
        assert len(islands) == 1
        assert len(islands[0].pads) == 2


class TestStitchingVias:
    """Tests for via computation."""

    def test_single_island_no_vias(self):
        """Single island needs no stitching."""
        pad = PowerPad(id=0, x=10, y=10, layer=0, net="GND", component="C1")
        island = Island.from_pads(0, [pad])
        
        vias = compute_stitching_vias([island], plane_layer=1)
        assert len(vias) == 0

    def test_two_islands_one_via(self):
        """Two islands need one stitching via."""
        p1 = PowerPad(id=0, x=10, y=10, layer=0, net="GND", component="C1")
        p2 = PowerPad(id=1, x=30, y=10, layer=0, net="GND", component="C2")
        
        i1 = Island.from_pads(0, [p1])
        i2 = Island.from_pads(1, [p2])
        
        vias = compute_stitching_vias([i1, i2], plane_layer=1)
        
        assert len(vias) == 1
        assert vias[0].x == pytest.approx(20)  # Midpoint
        assert vias[0].to_layer == 1

    def test_n_islands_n_minus_1_vias(self):
        """N islands need N-1 vias (MST)."""
        pads = [
            PowerPad(id=i, x=i*10, y=0, layer=0, net="GND", component=f"C{i}")
            for i in range(5)
        ]
        islands = [Island.from_pads(i, [p]) for i, p in enumerate(pads)]
        
        vias = compute_stitching_vias(islands, plane_layer=1)
        assert len(vias) == 4  # N-1 for MST
