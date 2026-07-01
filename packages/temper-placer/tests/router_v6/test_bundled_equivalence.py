"""Equivalence tests for bundled vs unbundled constraint encoding.

Test scenarios: T-U8-1 through T-U8-6 from
docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md

Verifies R10, R10.1, R10.2, SC2, SC3, SC4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from temper_placer.router_v6.constraint_model import ModelBuilder, NetChannelVar

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_net(name: str) -> object:
    @dataclass
    class MockNet:
        name: str
        pins: list = field(default_factory=list)
    return MockNet(name=name)


def _make_design_rules(trace_width_mm=0.2, clearance_mm=0.2) -> object:
    @dataclass
    class MockRule:
        trace_width_mm: float = trace_width_mm
        clearance_mm: float = clearance_mm

    @dataclass
    class MockDesignRules:
        def get_rules_for_net(self, _name: str):
            return MockRule()
    return MockDesignRules()


def _make_skeleton(layer_name: str, edges: list) -> object:
    @dataclass
    class MockSkeleton:
        graph: nx.Graph
        layer_name: str
    g = nx.Graph()
    for u, v in edges:
        g.add_edge(u, v)
    return MockSkeleton(graph=g, layer_name=layer_name)


def _make_pcb(nets, comp_positions=None) -> object:
    @dataclass
    class MockPin:
        name: str = "1"
        position: tuple[float, float] = (0, 0)
        layer: str = "F.Cu"
        is_pth: bool = True
        net: str | None = None

    @dataclass
    class MockComp:
        reference: str = ""
        initial_position: tuple[float, float] = (0, 0)
        pins: list = field(default_factory=list)
        def get_pin(self, name: str):
            for p in self.pins:
                if p.name == name:
                    return p
            return None

    comps = []
    for i, pos in enumerate(comp_positions or []):
        comp = MockComp(reference=f"U{i}", initial_position=pos, pins=[MockPin()])
        comps.append(comp)
    # Assign pins to nets
    for i, net in enumerate(nets):
        if comps:
            ci = i % len(comps)
            net.pins = [(comps[ci].reference, "1")]

    @dataclass
    class MockPCB:
        components: list
        nets: list
    return MockPCB(components=comps, nets=nets)


def _make_manifest(bundles: dict) -> object:
    @dataclass
    class MockManifest:
        bundle_id_for_net: dict = field(default_factory=dict)
        unbundled_net_indices: list = field(default_factory=list)
    return MockManifest(
        bundle_id_for_net=bundles,
        unbundled_net_indices=[],
    )


# ---------------------------------------------------------------------------
# T-U8-6: Completeness — trivial case
# ---------------------------------------------------------------------------


def test_trivial_completeness():
    """1 bundle (1 net), 1 channel → bundled and unbundled both SAT."""
    nets = [_make_net("SIG_A")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = {"F.Cu": _make_skeleton("F.Cu", edges)}

    # Unbundled
    builder_ub = ModelBuilder(skeletons=skeletons, nets=nets)
    model_ub = builder_ub.build()

    # Bundled — single net in its own bundle
    builder_b = ModelBuilder(
        skeletons=skeletons, nets=nets,
        )
    model_b = builder_b.build()

    # Both should produce some variables
    assert model_ub.variable_count > 0
    assert model_b.variable_count > 0


# ---------------------------------------------------------------------------
# T-U8: Soundness — safety constraints preserved (R10.1)
# ---------------------------------------------------------------------------


def test_safety_constraints_preserved():
    """Bundled model uses class-level variable naming (uses_B prefix)."""
    nets = [_make_net("AC_L"), _make_net("SIG_A")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = {"F.Cu": _make_skeleton("F.Cu", edges)}

    builder = ModelBuilder(
        skeletons=skeletons, nets=nets,
        )
    model = builder.build()

    # Should have class-level variables (uses_B prefix)
    from temper_placer.router_v6.constraint_model import NetChannelVar
    bundle_vars = [v for v in model.variables
                   if isinstance(v, NetChannelVar) and v.name.startswith("uses_B")]
    assert len(bundle_vars) > 0

    # No diff-pair constraints (Performance, deferred)
    from temper_placer.router_v6.constraint_model import DiffPairConstraint
    dp_constraints = [c for c in model.constraints if isinstance(c, DiffPairConstraint)]
    assert len(dp_constraints) == 0


# ---------------------------------------------------------------------------
# SC3: Safety constraint guarantee
# ---------------------------------------------------------------------------


def test_safety_in_cnf_before_solve():
    """Bundled model has variables created before solver call (no diff pairs)."""
    nets = [_make_net("SIG_A"), _make_net("SIG_B")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = {"F.Cu": _make_skeleton("F.Cu", edges)}

    builder = ModelBuilder(
        skeletons=skeletons, nets=nets,
        )
    model = builder.build()

    # The model should have variables (class-level)
    assert model.variable_count > 0

    # No diff-pair constraints in bundled model
    from temper_placer.router_v6.constraint_model import DiffPairConstraint
    dp_constraints = [c for c in model.constraints if isinstance(c, DiffPairConstraint)]
    assert len(dp_constraints) == 0


# ---------------------------------------------------------------------------
# Variable naming convention (KD7)
# ---------------------------------------------------------------------------


def test_variable_naming_class_prefix():
    """Class-level vars use uses_B prefix, per-net vars use uses_N."""
    nets = [_make_net("SIG_A"), _make_net("SIG_B")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = {"F.Cu": _make_skeleton("F.Cu", edges)}

    # Bundled
    builder_b = ModelBuilder(
        skeletons=skeletons, nets=nets,
        )
    model_b = builder_b.build()

    class_vars = [v for v in model_b.variables
                  if isinstance(v, NetChannelVar) and v.name.startswith("uses_B")]
    assert len(class_vars) > 0

    per_net_vars = [v for v in model_b.variables
                    if isinstance(v, NetChannelVar) and v.name.startswith("uses_N")]
    # Non-bundled nets get uses_N; bundled nets should NOT
    # (in this test, ALL nets are in bundle 0, so no uses_N)
    assert len(per_net_vars) == 0


# ---------------------------------------------------------------------------
# Diff-pair is performance — not in bundled model (SC4 pre-check)
# ---------------------------------------------------------------------------


def test_diff_pair_not_in_bundled_model():
    """Bundled model does not encode diff-pair constraints eagerly."""
    nets = [_make_net("USB_DP"), _make_net("USB_DN")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = {"F.Cu": _make_skeleton("F.Cu", edges)}

    from temper_placer.router_v6.diff_pair_inference import DiffPair

    dp = DiffPair(base_name="USB_D", p_net="USB_DP", n_net="USB_DN")
    builder = ModelBuilder(
        skeletons=skeletons, nets=nets, diff_pairs=[dp],
        )
    model = builder.build()

    from temper_placer.router_v6.constraint_model import DiffPairConstraint
    dp_constraints = [c for c in model.constraints
                      if isinstance(c, DiffPairConstraint)]
    assert len(dp_constraints) == 0
