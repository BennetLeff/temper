"""Tests for BundleAnalyzer — bundle equivalence class partitioning.

Test scenarios: T-U1-1 through T-U1-8 from
docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from temper_placer.router_v6.bundle_analyzer import (
    BundleAnalyzer,
    TypeSignature,
    _jaccard_cluster,
    _jaccard_edge_cover,
)

# ---------------------------------------------------------------------------
# Test fixtures — minimal mocks matching the interfaces consumed by
# BundleAnalyzer
# ---------------------------------------------------------------------------


def _make_net(name: str, pins: list[tuple[str, str]] | None = None) -> object:
    """Create a mock Net object."""

    @dataclass
    class MockNet:
        name: str
        pins: list[tuple[str, str]] = field(default_factory=list)

    return MockNet(name=name, pins=pins or [])


def _make_design_rules(
    trace_width_mm: float = 0.2, clearance_mm: float = 0.2
) -> object:
    """Create a mock DesignRules object."""

    @dataclass
    class MockRule:
        trace_width_mm: float = trace_width_mm
        clearance_mm: float = clearance_mm

    @dataclass
    class MockDesignRules:
        default_rule: MockRule = field(default_factory=MockRule)

        def get_rules_for_net(self, _name: str) -> MockRule:
            return self.default_rule

    return MockDesignRules()


def _make_skeleton(
    layer_name: str, edges: list[tuple[tuple[float, float], tuple[float, float]]]
) -> object:
    """Create a mock ChannelSkeleton with given edges."""

    @dataclass
    class MockSkeleton:
        graph: nx.Graph = field(default_factory=nx.Graph)
        layer_name: str = "F.Cu"

    g = nx.Graph()
    for u, v in edges:
        g.add_edge(u, v)
    return MockSkeleton(graph=g, layer_name=layer_name)


def _make_skeletons(edges_per_layer: list) -> dict[str, object]:
    """Create dict of layer_name -> MockSkeleton."""
    result = {}
    for layer_name, edges in edges_per_layer:
        result[layer_name] = _make_skeleton(layer_name, edges)
    return result


def _make_pcb(
    nets: list[object], components: list[dict] | None = None
) -> object:
    """Create a mock ParsedPCB."""

    @dataclass
    class MockPCB:
        nets: list[object] = field(default_factory=list)
        components: list[object] = field(default_factory=list)

    comp_objs = []
    for comp_data in (components or []):
        pin_objs = []

        @dataclass
        class MockPin:
            name: str = ""
            position: tuple[float, float] = (0, 0)
            layer: str = "F.Cu"

        for pin_data in comp_data.get("pins", []):
            pin_objs.append(MockPin(**pin_data))

        @dataclass
        class MockComp:
            reference: str = ""
            initial_position: tuple[float, float] = (0, 0)
            _pins: list = field(default_factory=list)

            def get_pin(self, name: str):
                for p in self._pins:
                    if p.name == name:
                        return p
                return None

        comp = MockComp(
            reference=comp_data["ref"],
            initial_position=comp_data.get("pos", (0, 0)),
        )
        comp._pins = pin_objs
        comp_objs.append(comp)

    return MockPCB(nets=nets, components=comp_objs)


def _make_diff_pair(p_net: str, n_net: str, base_name: str = "X") -> object:
    """Create a mock DiffPair."""

    @dataclass
    class MockDiffPair:
        p_net: str
        n_net: str
        base_name: str

    return MockDiffPair(p_net=p_net, n_net=n_net, base_name=base_name)


# ---------------------------------------------------------------------------
# T-U1-1: Identical signal nets bundle
# ---------------------------------------------------------------------------


def test_identical_signal_nets_bundle():
    """Two signal nets with same widths, same region, overlapping footprints
    → same bundle class."""
    nets = [_make_net("SIG_A"), _make_net("SIG_B")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = _make_skeletons([("F.Cu", edges)])
    pcb = _make_pcb(nets,
        components=[
            {"ref": "U1", "pos": (0, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
            {"ref": "U2", "pos": (10, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
        ])
    # Assign pins so both nets have overlapping footprints
    nets[0].pins = [("U1", "1")]
    nets[1].pins = [("U2", "1")]
    dr = _make_design_rules()

    analyzer = BundleAnalyzer(
        nets=nets, skeletons=skeletons, design_rules=dr, pcb=pcb,
    )
    manifest = analyzer.analyze()

    assert manifest.bundle_count == 1
    b0 = manifest.bundles[0]
    assert b0.net_indices == [0, 1]
    assert b0.is_diff_pair is False


# ---------------------------------------------------------------------------
# T-U1-2: Dissimilar types don't bundle
# ---------------------------------------------------------------------------


def test_dissimilar_types_dont_bundle():
    """HV net and signal net in same region → different bundles."""
    nets = [_make_net("AC_L"), _make_net("SIG_A")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = _make_skeletons([("F.Cu", edges)])
    pcb = _make_pcb(nets,
        components=[
            {"ref": "U1", "pos": (0, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
            {"ref": "U2", "pos": (10, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
        ])
    nets[0].pins = [("U1", "1")]
    nets[1].pins = [("U2", "1")]
    dr = _make_design_rules()

    analyzer = BundleAnalyzer(nets=nets, skeletons=skeletons, design_rules=dr, pcb=pcb)
    manifest = analyzer.analyze()

    # AC_L → hv, SIG_A → signal  (different type signatures)
    assert manifest.bundle_count >= 2


# ---------------------------------------------------------------------------
# T-U1-3: Different trace widths don't bundle
# ---------------------------------------------------------------------------


def test_different_widths_dont_bundle():
    """Two signal nets with different trace widths → different bundles."""
    nets = [_make_net("SIG_A"), _make_net("SIG_B")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = _make_skeletons([("F.Cu", edges)])
    pcb = _make_pcb(nets,
        components=[
            {"ref": "U1", "pos": (0, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
            {"ref": "U2", "pos": (10, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
        ])
    nets[0].pins = [("U1", "1")]
    nets[1].pins = [("U2", "1")]

    # Two different design rule sets
    dr_wide = _make_design_rules(0.5, 0.2)
    _make_design_rules(0.2, 0.2)

    # Analyze with wide rules only (both get same width → same bundle)
    analyzer_same = BundleAnalyzer(nets=nets, skeletons=skeletons, design_rules=dr_wide, pcb=pcb)
    manifest_same = analyzer_same.analyze()
    assert manifest_same.bundle_count == 1

    # Now simulate different widths by patching: SIG_A gets 0.5mm, SIG_B gets 0.2mm
    # We need to control this — let's make a custom design_rules
    @dataclass
    class PerNetRules:
        widths: dict[str, float]

        def get_rules_for_net(self, name: str):
            w = self.widths.get(name, 0.2)

            @dataclass
            class R:
                trace_width_mm: float = w
                clearance_mm: float = 0.2

            return R()

    dr_per = PerNetRules(widths={"SIG_A": 0.5, "SIG_B": 0.2})
    analyzer_diff = BundleAnalyzer(nets=nets, skeletons=skeletons, design_rules=dr_per, pcb=pcb)
    manifest_diff = analyzer_diff.analyze()
    assert manifest_diff.bundle_count >= 2, f"Expected >=2 bundles, got {manifest_diff.bundle_count}"


# ---------------------------------------------------------------------------
# T-U1-4: Disjoint regions don't bundle
# ---------------------------------------------------------------------------


def test_disjoint_regions_dont_bundle():
    """Two identical signal nets on opposite corners → different bundles."""
    nets = [_make_net("SIG_A"), _make_net("SIG_B")]
    edges = [
        ((0.0, 0.0), (100.0, 100.0)),
    ]
    skeletons = _make_skeletons([("F.Cu", edges)])
    pcb = _make_pcb(nets,
        components=[
            {"ref": "U1", "pos": (0, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
            {"ref": "U2", "pos": (100, 100), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
        ])
    nets[0].pins = [("U1", "1")]  # corner at (0,0)
    nets[1].pins = [("U2", "1")]  # corner at (100,100)
    dr = _make_design_rules()

    # Use a narrow jaccard threshold to ensure they don't bundle
    analyzer = BundleAnalyzer(nets=nets, skeletons=skeletons, design_rules=dr, pcb=pcb)
    manifest = analyzer.analyze()
    # With small pin footprints and a large edge, the footprints may not overlap
    assert manifest.bundle_count == 2


# ---------------------------------------------------------------------------
# T-U1-5: Diff pair always singleton
# ---------------------------------------------------------------------------


def test_diff_pair_singleton():
    """A diff pair forms its own dedicated 2-net bundle (KD6)."""
    nets = [_make_net("USB_DP"), _make_net("USB_DN"), _make_net("SIG_A")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = _make_skeletons([("F.Cu", edges)])
    pcb = _make_pcb(nets,
        components=[
            {"ref": "U1", "pos": (0, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
            {"ref": "U2", "pos": (5, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
            {"ref": "U3", "pos": (10, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
        ])
    nets[0].pins = [("U1", "1")]
    nets[1].pins = [("U2", "1")]
    nets[2].pins = [("U3", "1")]
    dr = _make_design_rules()
    diff_pairs = [_make_diff_pair("USB_DP", "USB_DN", "USB_D")]

    analyzer = BundleAnalyzer(
        nets=nets, skeletons=skeletons, design_rules=dr, pcb=pcb,
        diff_pairs=diff_pairs,
    )
    manifest = analyzer.analyze()

    # Find the diff-pair bundle
    dp_bundles = [b for b in manifest.bundles.values() if b.is_diff_pair]
    assert len(dp_bundles) == 1
    dp_bundle = dp_bundles[0]
    assert sorted(dp_bundle.net_indices) == [0, 1]  # USB_DP (0), USB_DN (1)
    assert dp_bundle.is_diff_pair is True


# ---------------------------------------------------------------------------
# T-U1-6: Determinism
# ---------------------------------------------------------------------------


def test_determinism():
    """Three runs with identical inputs → identical manifests."""
    nets = [_make_net("SIG_A"), _make_net("SIG_B"), _make_net("SIG_C")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = _make_skeletons([("F.Cu", edges)])
    pcb = _make_pcb(nets,
        components=[
            {"ref": "U1", "pos": (0, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
            {"ref": "U2", "pos": (5, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
            {"ref": "U3", "pos": (10, 0), "pins": [{"name": "1", "position": (0, 0), "layer": "F.Cu"}]},
        ])
    nets[0].pins = [("U1", "1")]
    nets[1].pins = [("U2", "1")]
    nets[2].pins = [("U3", "1")]
    dr = _make_design_rules()

    manifests = []
    for _ in range(3):
        analyzer = BundleAnalyzer(nets=nets, skeletons=skeletons, design_rules=dr, pcb=pcb)
        manifests.append(analyzer.analyze())

    m0 = manifests[0]
    for m in manifests[1:]:
        assert m.bundle_count == m0.bundle_count
        assert m.bundle_id_for_net == m0.bundle_id_for_net
        assert m.unbundled_net_indices == m0.unbundled_net_indices
        for bid in m0.bundles:
            assert m.bundles[bid].net_indices == m0.bundles[bid].net_indices
            assert m.bundles[bid].type_signature == m0.bundles[bid].type_signature


# ---------------------------------------------------------------------------
# T-U1-7: Empty nets
# ---------------------------------------------------------------------------


def test_empty_nets():
    """Zero nets → empty BundleManifest."""
    nets: list = []
    skeletons = _make_skeletons([("F.Cu", [((0.0, 0.0), (10.0, 0.0))])])
    analyzer = BundleAnalyzer(nets=nets, skeletons=skeletons)
    manifest = analyzer.analyze()

    assert manifest.bundle_count == 0
    assert manifest.bundle_id_for_net == {}
    assert manifest.unbundled_net_indices == []


# ---------------------------------------------------------------------------
# T-U1-8: Jaccard boundary
# ---------------------------------------------------------------------------


def test_jaccard_boundary():
    """Jaccard > 0.5 bundles; Jaccard <= 0.5 does not."""
    a = frozenset({"e1", "e2", "e3"})
    b_close = frozenset({"e1", "e2"})  # Jaccard = 2/3 ≈ 0.667 > 0.5
    b_far = frozenset({"e1"})            # Jaccard = 1/3 ≈ 0.333 ≤ 0.5

    assert _jaccard_edge_cover(a, b_close) > 0.5
    assert _jaccard_edge_cover(a, b_far) <= 0.5


def test_jaccard_cluster_basic():
    """Greedy clustering by Jaccard coverage."""
    covers = [
        frozenset({"e1", "e2", "e3"}),
        frozenset({"e1", "e2"}),
        frozenset({"e4", "e5"}),
    ]
    clusters = _jaccard_cluster([0, 1, 2], covers, 0.5)
    assert len(clusters) == 2
    flat = sorted([sorted(c) for c in clusters])
    assert flat[0] == [0, 1]
    assert flat[1] == [2]


# ---------------------------------------------------------------------------
# TypeSignature
# ---------------------------------------------------------------------------


def test_type_signature_equality():
    sig1 = TypeSignature("signal", 0.2, 0.2, False, frozenset({"F.Cu"}))
    sig2 = TypeSignature("signal", 0.2, 0.2, False, frozenset({"F.Cu"}))
    sig3 = TypeSignature("signal", 0.5, 0.2, False, frozenset({"F.Cu"}))
    assert sig1 == sig2
    assert sig1 != sig3
    assert hash(sig1) == hash(sig2)
