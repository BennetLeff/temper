"""Regression test for the bundle-id/net-index capacity-constraint collision.

Found 2026-08-07 (docs/evidence/2026-08-07-sat-model-reduction-options.md
Sec 3.3), fixed the same task: `_create_bundle_channel_vars` stores bundle
channel variables keyed by ``bundle_id`` (``0..bundle_count-1``), and
`_create_capacity_constraints` looked those up through the SAME dict as
real per-net variables (keyed by ``net_idx``, also ``0..n_nets-1``) --  two
different, overlapping ID spaces sharing one dict. A real net whose index
happened to numerically coincide with some (unrelated) bundle's id would
either silently drop out of every capacity constraint it should appear in,
or -- worse -- have its identity misattributed to that unrelated bundle's
shared variable, corrupting the capacity accounting for both.

This test builds exactly that numeric coincidence (4 nets, 2 bundles of 2
members each -- net index 1 is a member of bundle 0, but 1 also happens to
equal bundle 1's own id) and asserts each bundle's capacity term reflects
the SUM of its own members' widths only, with no cross-bundle bleed.
"""

from __future__ import annotations

import networkx as nx

from temper_placer.core.netlist import Net
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.constraint_model import (
    CapacityConstraint,
    ModelBuilder,
    canonical_channel_edges,
)
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules


def _the_edge_id(skeletons: dict) -> str:
    """The single edge_id produced for this test's one-edge, one-layer skeleton."""
    (layer_name, sk), = skeletons.items()
    (edge_id, _u, _v), = canonical_channel_edges(sk.graph, layer_name)
    return edge_id


def _design_rules_with_distinct_widths() -> DesignRules:
    """Four net classes, one per net, each with a distinct trace width and
    zero clearance -- so a net's "width" contribution to a capacity term is
    just its trace_width_mm, and expected sums are exact, easy-to-read
    numbers.
    """
    classes = {
        f"W{w}": NetClassRules(
            name=f"W{w}",
            clearance_mm=0.0,
            trace_width_mm=w,
            via_diameter_mm=0.3,
            via_drill_mm=0.15,
        )
        for w in (0.10, 0.20, 0.30, 0.40)
    }
    return DesignRules(
        net_classes=classes,
        net_class_assignments={
            "AAA": "W0.1",
            "BBB": "W0.2",
            "CCC": "W0.3",
            "DDD": "W0.4",
        },
        default_clearance_mm=0.0,
        default_trace_width_mm=0.2,
        default_via_diameter_mm=0.3,
        default_via_drill_mm=0.15,
    )


def _single_edge_skeleton_and_widths():
    g = nx.Graph()
    u, v = (0.0, 0.0), (10.0, 0.0)
    g.add_edge(u, v)
    sk = ChannelSkeleton(graph=g, layer_name="L1", total_length=10.0)
    widths = ChannelWidths(
        layer_name="L1",
        node_widths={},
        edge_widths={(u, v): 10.0},  # plenty of capacity; not the thing under test
        min_width=10.0,
        max_width=10.0,
        avg_width=10.0,
    )
    return {"L1": sk}, {"L1": widths}


def _make_manifest(bundle_id_for_net: dict[int, int]):
    from dataclasses import dataclass, field

    @dataclass
    class MockManifest:
        bundle_id_for_net: dict = field(default_factory=dict)
        unbundled_net_indices: list = field(default_factory=list)

    return MockManifest(bundle_id_for_net=dict(bundle_id_for_net), unbundled_net_indices=[])


def test_net_index_bundle_id_collision_does_not_corrupt_capacity():
    """bundle 0 = {net 0 (AAA), net 1 (BBB)}, bundle 1 = {net 2 (CCC), net 3 (DDD)}.

    Net index 1 (a member of bundle 0, BBB) numerically coincides with
    bundle 1's own id -- exactly the collision shape described in
    docs/evidence/2026-08-07-sat-model-reduction-options.md Sec 3.3. Before
    the fix, this made bundle 1's capacity term pick up BBB's width (via the
    shared, colliding dict) instead of -- or in addition to -- its own
    members' (CCC, DDD) widths.
    """
    nets = [Net(name=n, pins=[]) for n in ("AAA", "BBB", "CCC", "DDD")]
    skeletons, widths = _single_edge_skeleton_and_widths()
    design_rules = _design_rules_with_distinct_widths()
    manifest = _make_manifest({0: 0, 1: 0, 2: 1, 3: 1})

    builder = ModelBuilder(
        skeletons=skeletons,
        nets=nets,
        channel_widths=widths,
        design_rules=design_rules,
        enable_bundling=True,
        bundle_manifest=manifest,
    )
    model = builder.build()

    # Bundle vars must live in bundle_channel_vars, never net_channel_vars --
    # the dict split that removes the collision at the root.
    assert len(model.net_channel_vars) == 0, (
        "all 4 nets are bundled; no per-net channel var should exist"
    )
    assert len(model.bundle_channel_vars) == 2, "one shared var per bundle per edge"

    constraints = [c for c in model.constraints if isinstance(c, CapacityConstraint)]
    assert len(constraints) == 1
    terms = constraints[0].terms
    assert len(terms) == 2, f"expected exactly 2 terms (1 per bundle), got {len(terms)}: {terms}"

    edge_id = _the_edge_id(skeletons)
    bundle0_var = model.bundle_channel_vars[(0, edge_id)]
    bundle1_var = model.bundle_channel_vars[(1, edge_id)]

    weight_by_var = {var.name: width for var, width in terms}

    # Bundle 0 (AAA + BBB) must carry exactly AAA's + BBB's width.
    assert weight_by_var[bundle0_var.name] == 0.10 + 0.20

    # Bundle 1 (CCC + DDD) must carry exactly CCC's + DDD's width -- NOT
    # BBB's width (0.20), which is what the pre-fix collision would have
    # substituted in (net index 1 == bundle 1's id).
    assert weight_by_var[bundle1_var.name] == 0.30 + 0.40
    assert weight_by_var[bundle1_var.name] != 0.20


def test_mixed_bundled_and_unbundled_nets_no_double_counting():
    """3 nets: net 0+1 bundled together, net 2 stays unbundled (singleton).

    Regression guard for the OTHER direction of the fix: an unbundled net's
    own per-net term must appear exactly once, and must not also be pulled
    into a bundle's term (or vice versa) merely because of index overlap.
    """
    nets = [Net(name=n, pins=[]) for n in ("AAA", "BBB", "CCC")]
    skeletons, widths = _single_edge_skeleton_and_widths()
    design_rules = _design_rules_with_distinct_widths()
    # CCC isn't in net_class_assignments's set of 4 -- reuse DDD's class.
    design_rules.net_class_assignments["CCC"] = "W0.4"
    manifest = _make_manifest({0: 0, 1: 0})  # net 2 (CCC) unbundled

    builder = ModelBuilder(
        skeletons=skeletons,
        nets=nets,
        channel_widths=widths,
        design_rules=design_rules,
        enable_bundling=True,
        bundle_manifest=manifest,
    )
    model = builder.build()

    assert len(model.bundle_channel_vars) == 1  # bundle 0, 1 edge
    assert len(model.net_channel_vars) == 1  # net 2 (unbundled), 1 edge

    constraints = [c for c in model.constraints if isinstance(c, CapacityConstraint)]
    assert len(constraints) == 1
    terms = constraints[0].terms
    assert len(terms) == 2  # 1 bundle term + 1 per-net term

    weight_by_var = {var.name: width for var, width in terms}
    edge_id = _the_edge_id(skeletons)
    bundle0_var = model.bundle_channel_vars[(0, edge_id)]
    net2_var = model.net_channel_vars[(2, edge_id)]

    assert weight_by_var[bundle0_var.name] == 0.10 + 0.20
    assert weight_by_var[net2_var.name] == 0.40
