"""
Tests for BundleAnalyzer — net partitioning into bundle equivalence classes.

Origin: U1 of docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md
Test scenarios: T-U1-1 through T-U1-8
"""

import math

import networkx as nx
import pytest
from shapely.geometry import Point, Polygon

from temper_placer.router_v6.bundle_analyzer import (
    BundleAnalyzer,
    BundleClass,
    BundleManifest,
    TypeSignature,
)


class MockNet:
    """Minimal Net-like object for testing."""

    def __init__(self, name, pin_positions=None):
        self.name = name
        self._pos = pin_positions or []
        self.pins = [(f"COMP_{name}_{i}", f"PIN_{i}") for i in range(len(self._pos))]

    def __repr__(self):
        return f"MockNet({self.name!r})"


class MockPin:
    """Minimal Pin-like object for testing."""

    def __init__(self, x, y, layer="F.Cu", is_pth=True):
        self.position = (x, y)
        self.layer = layer
        self.is_pth = is_pth


class MockComponent:
    """Minimal Component-like object for testing."""

    def __init__(self, ref, pos=(0.0, 0.0), pins=None):
        self.ref = ref
        self.initial_position = pos
        self._pins = pins or {}

    def get_pin(self, pin_name):
        return self._pins.get(pin_name)


class MockPCB:
    """Minimal ParsedPCB-like object for testing."""

    def __init__(self, components=None):
        self.components = components or []


def _make_pcb_for_nets(*nets: MockNet) -> MockPCB:
    """Build a MockPCB with components positioned at each net's pin positions."""
    components = []
    for net in nets:
        for i, (comp_ref, pin_name) in enumerate(net.pins):
            if i < len(net._pos):
                x, y = net._pos[i]
                comp = MockComponent(comp_ref, pos=(x, y), pins={
                    pin_name: MockPin(0, 0)  # pin at component origin
                })
                components.append(comp)
    return MockPCB(components)


class MockDesignRules:
    """Minimal DesignRules-like object for testing."""

    def __init__(self, trace_width=0.2, clearance=0.2):
        self._width = trace_width
        self._clearance = clearance

    def get_rules_for_net(self, _net_name):
        from temper_placer.router_v6.stage0_data import NetClassRules
        return NetClassRules(
            name="Default",
            clearance_mm=self._clearance,
            trace_width_mm=self._width,
            via_diameter_mm=0.6,
            via_drill_mm=0.3,
        )


class MockDiffPair:
    """Minimal DiffPair-like object for testing."""

    def __init__(self, base_name, p_net, n_net):
        self.base_name = base_name
        self.p_net = p_net
        self.n_net = n_net


class MockSkeleton:
    """Minimal ChannelSkeleton-like object for testing."""

    def __init__(self, graph=None):
        self.graph = graph or nx.Graph()


def make_line_skeleton(layer_name: str, points: list[tuple[float, float]]) -> MockSkeleton:
    """Create a skeleton graph as a simple path through points."""
    G = nx.Graph()
    for i in range(len(points)):
        G.add_node(points[i])
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        length = math.sqrt(dx * dx + dy * dy)
        G.add_edge(p1, p2, weight=length)
    return MockSkeleton(G)


def make_grid_skeleton(
    layer_name: str, x_range: tuple[float, float], y_range: tuple[float, float],
    spacing: float = 10.0,
) -> MockSkeleton:
    """Create a grid skeleton graph with regular spacing."""
    G = nx.Graph()
    xs = [x_range[0] + i * spacing for i in range(int((x_range[1] - x_range[0]) / spacing) + 1)]
    ys = [y_range[0] + i * spacing for i in range(int((y_range[1] - y_range[0]) / spacing) + 1)]
    nodes = [(x, y) for x in xs for y in ys]
    for n in nodes:
        G.add_node(n)
    for x in xs:
        for i in range(len(ys) - 1):
            G.add_edge((x, ys[i]), (x, ys[i + 1]), weight=spacing)
    for y in ys:
        for i in range(len(xs) - 1):
            G.add_edge((xs[i], y), (xs[i + 1], y), weight=spacing)
    return MockSkeleton(G)


# ---------------------------------------------------------------------------
# T-U1-1: Identical signal nets bundle
# ---------------------------------------------------------------------------
def test_identical_signal_nets_bundle():
    """Two signal nets with identical signatures and overlapping footprints -> same bundle."""
    nets = [
        MockNet("SIG_A", [(10.0, 10.0), (20.0, 10.0)]),
        MockNet("SIG_B", [(10.0, 10.0), (20.0, 10.0)]),
    ]
    skeletons = {"F.Cu": make_grid_skeleton("F.Cu", (0, 30), (0, 30), spacing=5)}
    dr = MockDesignRules()
    pcb = _make_pcb_for_nets(*nets)
    analyzer = BundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb)

    manifest = analyzer.analyze()

    assert len(manifest.bundles) == 1
    assert manifest.bundles[0].net_indices == [0, 1]
    assert 0 in manifest.bundle_id_for_net
    assert 1 in manifest.bundle_id_for_net


# ---------------------------------------------------------------------------
# T-U1-2: Dissimilar types don't bundle
# ---------------------------------------------------------------------------
def test_dissimilar_types_dont_bundle():
    """An HV net and a signal net in the same region -> different bundle classes."""
    nets = [
        MockNet("AC_L", [(10.0, 10.0), (20.0, 10.0)]),
        MockNet("SIG_A", [(10.0, 10.0), (20.0, 10.0)]),
    ]
    skeletons = {"F.Cu": make_grid_skeleton("F.Cu", (0, 30), (0, 30), spacing=5)}
    dr = MockDesignRules()
    pcb = _make_pcb_for_nets(*nets)
    analyzer = BundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb)

    manifest = analyzer.analyze()

    # They should NOT be in the same bundle because net_class differs (hv vs signal)
    manifest_len = len(manifest.bundles)
    if manifest_len == 2:
        assert manifest_len == 2
    else:
        # At minimum, they're not in the same bundle
        for b in manifest.bundles.values():
            assert not (0 in b.net_indices and 1 in b.net_indices), \
                "HV and signal nets should not be in the same bundle"


# ---------------------------------------------------------------------------
# T-U1-3: Different widths don't bundle
# ---------------------------------------------------------------------------
def test_different_widths_dont_bundle():
    """Two signal nets with 0.2mm and 0.5mm trace widths -> different bundle classes."""
    nets = [
        MockNet("SIG_A", [(10.0, 10.0), (20.0, 10.0)]),
        MockNet("SIG_B", [(10.0, 10.0), (20.0, 10.0)]),
    ]
    skeletons = {"F.Cu": make_grid_skeleton("F.Cu", (0, 30), (0, 30), spacing=5)}
    pcb = _make_pcb_for_nets(*nets)
    analyzer = BundleAnalyzer(
        nets, skeletons,
        design_rules=FakeDesignRules(widths={"SIG_A": 0.2, "SIG_B": 0.5}),
        pcb=pcb,
    )

    manifest = analyzer.analyze()

    for b in manifest.bundles.values():
        assert not (0 in b.net_indices and 1 in b.net_indices), \
            "Nets with different widths should not bundle"


class FakeDesignRules:
    """DesignRules that returns per-net trace widths for testing."""

    def __init__(self, widths=None, clearances=None):
        self._widths = widths or {}
        self._clearances = clearances or {}

    def get_rules_for_net(self, net_name):
        from temper_placer.router_v6.stage0_data import NetClassRules
        return NetClassRules(
            name="Default",
            clearance_mm=self._clearances.get(net_name, 0.2),
            trace_width_mm=self._widths.get(net_name, 0.2),
            via_diameter_mm=0.6,
            via_drill_mm=0.3,
        )


# ---------------------------------------------------------------------------
# T-U1-4: Disjoint regions don't bundle
# ---------------------------------------------------------------------------
def test_disjoint_regions_dont_bundle():
    """Two identical signal nets on opposite corners -> different bundle classes (Jaccard=0)."""
    nets = [
        MockNet("SIG_A", [(0.0, 0.0), (5.0, 0.0)]),
        MockNet("SIG_B", [(95.0, 95.0), (100.0, 100.0)]),
    ]
    skeletons = {"F.Cu": make_grid_skeleton("F.Cu", (0, 100), (0, 100), spacing=10)}
    dr = MockDesignRules()
    pcb = _make_pcb_for_nets(*nets)
    analyzer = BundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb)

    manifest = analyzer.analyze()

    for b in manifest.bundles.values():
        assert not (0 in b.net_indices and 1 in b.net_indices), \
            "Nets in disjoint regions should not bundle"


# ---------------------------------------------------------------------------
# T-U1-5: Diff pair always singleton (2-net bundle)
# ---------------------------------------------------------------------------
def test_diff_pair_singleton_bundle():
    """A diff pair -> always their own dedicated 2-net bundle."""
    nets = [
        MockNet("USB_DP", [(10.0, 10.0), (20.0, 10.0)]),
        MockNet("USB_DN", [(10.0, 10.0), (20.0, 10.0)]),
        MockNet("SIG_A", [(10.0, 10.0), (20.0, 10.0)]),
    ]
    diff_pairs = [MockDiffPair("USB_D", "USB_DP", "USB_DN")]
    skeletons = {"F.Cu": make_grid_skeleton("F.Cu", (0, 30), (0, 30), spacing=5)}
    dr = MockDesignRules()
    pcb = _make_pcb_for_nets(*nets)
    analyzer = BundleAnalyzer(nets, skeletons, design_rules=dr, diff_pairs=diff_pairs, pcb=pcb)

    manifest = analyzer.analyze()

    # Find the diff-pair bundle
    diff_bundles = [b for b in manifest.bundles.values() if b.is_diff_pair]
    assert len(diff_bundles) >= 1, "Diff pair should form a bundle"
    diff_b = diff_bundles[0]
    assert sorted(diff_b.net_indices) == [0, 1], "Diff pair nets should be bundled together"
    # The signal net should NOT be in the diff-pair bundle
    assert 2 not in diff_b.net_indices


# ---------------------------------------------------------------------------
# T-U1-6: Determinism
# ---------------------------------------------------------------------------
def test_determinism():
    """Running BundleAnalyzer three times with identical inputs -> identical results."""
    nets = [
        MockNet("SIG_A", [(10.0, 10.0), (20.0, 10.0)]),
        MockNet("SIG_B", [(10.0, 10.0), (20.0, 10.0)]),
        MockNet("SIG_C", [(50.0, 50.0), (60.0, 60.0)]),
    ]
    skeletons = {"F.Cu": make_grid_skeleton("F.Cu", (0, 70), (0, 70), spacing=5)}
    dr = MockDesignRules()
    pcb = _make_pcb_for_nets(*nets)

    results = []
    for _ in range(3):
        analyzer = BundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb)
        manifest = analyzer.analyze()
        results.append(manifest)

    r0, r1, r2 = results
    assert r0.bundles.keys() == r1.bundles.keys() == r2.bundles.keys()
    assert r0.bundle_id_for_net == r1.bundle_id_for_net == r2.bundle_id_for_net
    assert r0.unbundled_net_indices == r1.unbundled_net_indices == r2.unbundled_net_indices


# ---------------------------------------------------------------------------
# T-U1-7: Empty nets
# ---------------------------------------------------------------------------
def test_empty_nets():
    """Zero nets -> empty BundleManifest."""
    nets = []
    skeletons = {}
    analyzer = BundleAnalyzer(nets, skeletons)
    manifest = analyzer.analyze()
    assert manifest.bundle_count == 0
    assert manifest.bundle_id_for_net == {}
    assert manifest.unbundled_net_indices == []


# ---------------------------------------------------------------------------
# T-U1-8: Jaccard boundary
# ---------------------------------------------------------------------------
def test_jaccard_boundary_exact():
    """Explicit Jaccard boundary test with controlled edge sets."""
    # Use a simplified flow path: build edge sets manually and verify Jaccard logic.
    # For integration tests, we use the full analyzer.
    # Here we verify the Jaccard function directly.
    from temper_placer.router_v6.bundle_analyzer import BundleAnalyzer

    nets = [MockNet("DUMMY", []), MockNet("DUMMY2", [])]
    analyzer = BundleAnalyzer(nets, {})

    a = frozenset({"E0", "E1", "E2"})
    b = frozenset({"E2", "E3", "E4"})
    # |A ∩ B| = 1, |A ∪ B| = 5 → Jaccard = 0.2
    assert analyzer._jaccard(a, b) == pytest.approx(0.200, abs=0.001)
    assert analyzer._jaccard(a, a) == pytest.approx(1.0, abs=0.001)
    assert analyzer._jaccard(frozenset(), frozenset()) == 1.0
    assert analyzer._jaccard(a, frozenset()) == 0.0


def test_jaccard_boundary_grouping():
    """Nets with controlled Jaccard values using directional placement."""
    nets = [
        MockNet("SIG_A", [(0.0, 0.0), (8.0, 0.0)]),
        MockNet("SIG_B", [(4.0, 0.0), (12.0, 0.0)]),   # ~50% overlap with A
        MockNet("SIG_C", [(30.0, 0.0), (40.0, 0.0)]),   # far away
    ]
    skeletons = {"F.Cu": make_grid_skeleton("F.Cu", (-5, 45), (-10, 10), spacing=5)}
    dr = MockDesignRules()
    pcb = _make_pcb_for_nets(*nets)
    analyzer = BundleAnalyzer(nets, skeletons, design_rules=dr, pcb=pcb)

    manifest = analyzer.analyze()
    # A and B should bundle (overlap); C should not be in that bundle
    bundled_nets: set[int] = set()
    for b in manifest.bundles.values():
        if len(b.net_indices) >= 2:
            bundled_nets.update(b.net_indices)
    assert 0 in bundled_nets and 1 in bundled_nets, "SIG_A and SIG_B should bundle"
    assert 2 not in bundled_nets, "SIG_C should not be in the same bundle"
