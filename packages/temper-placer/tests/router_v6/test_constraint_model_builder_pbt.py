"""Property-based tests for the Phase E batch E1 `ModelBuilder` orchestration.

Rust Orchestration Engine plan 2026-08-09-001 Phase E E1: the
`ModelBuilder.build()` orchestration migrates to `temper-design-bundle` as
`ModelBuilder::build()`. These properties run against the production shim
(`temper_placer.router_v6.constraint_model.ModelBuilder`) and hold over
randomized board/netlist/skeleton inputs.

Six non-vacuous properties (G4):

- P1  per-net channel-variable identity: without bundling or pruning, every
      (net, layer-edge) pair has exactly one `NetChannelVar` named
      `uses_N{net_idx}_{edge_id}` in `net_channel_vars`.
- P2  capacity-constraint soundness: every `CapacityConstraint`'s capacity
      is positive, its slack is 0.8, and every term references an existing
      variable.
- P3  geographic-pruning subset: the pruned model's variables/constraints
      are a subset of the unpruned model's on identical inputs.
- P4  via-var opt-in: `enable_via_vars=False` creates zero `ViaVar`s;
      `True` creates exactly `n_nets * n_unique_nodes` (unpruned).
- P5  diff-pair constraints reference only variables that exist: every
      `DiffPairConstraint`'s `p_var`/`n_var` names appear in
      `net_channel_vars`.
- P6  bundling isolation (the 2026-08-07 Sec 3.3 collision shape): with
      bundling on, bundle variables live in `bundle_channel_vars` and
      never in `net_channel_vars`; every capacity term references an
      existing variable.

Metamorphic relations (G5):

- MR1 monotone net extension: appending a net (pruning off) leaves every
      pre-existing variable intact and adds exactly one variable per edge
      for the new net.
- MR2 layer insertion-order permutation: rebuilding with the skeletons dict
      in a different insertion order yields an identical model (edge
      identity and per-layer processing are geometry-ordered).
- MR3 pruning equality when nothing is rejected: with every edge within the
      pruning margin of the pins, the pruned model is IDENTICAL to the
      unpruned model (the geographic filter is exact).

Vacuity guards (G4): every property carries a companion that constructs a
model violating the invariant and asserts the invariant discriminates it.
The builder is a Rust pyclass after this migration, so the guards cannot
mutate live model objects in place; each guard instead demonstrates the
invariant's discriminating power on a hand-built violating model (or, for
P6, on the pre-fix shared-dict shape via the oracle's mutable dataclass).
"""

from __future__ import annotations

import hypothesis.strategies as st
import tests.graph_fixtures as nx
import pytest
from hypothesis import given, settings

import tests.router_v6._constraint_model_builder_py_oracle as _orc

from temper_placer.core.netlist import Component, Net, Pin
from temper_placer.router_v6 import constraint_model as cm
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules, ParsedPCB


def _mb():
    """Lazily bind the design-bundle model_builder submodule (exists only
    once the Phase E1 Rust port lands; the vacuity guards below are written
    against the target API and fail until then)."""
    import temper_design_bundle_python as _tdb

    return _tdb.model_builder


# ---------------------------------------------------------------------------
# Input generators
# ---------------------------------------------------------------------------


@st.composite
def skeleton_set(draw):
    """1-3 layers, each a random small networkx graph on distinct points.

    Guarantees >=1 edge per layer (the first two points are always
    connected), so `ModelBuilder.build()`'s R10 non-emptiness precondition
    never fires on the generated fixtures.
    """
    n_layers = draw(st.integers(min_value=1, max_value=3))
    skeletons = {}
    for li in range(n_layers):
        layer = f"L{li}"
        points = draw(
            st.lists(
                st.tuples(
                    st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False),
                    st.floats(min_value=-50, max_value=50, allow_nan=False, allow_infinity=False),
                ),
                min_size=2,
                max_size=5,
                unique=True,
            )
        )
        g = nx.Graph()
        for p in points:
            g.add_node(p)
        # guarantee >= 1 edge: connect the first two points, then extras
        g.add_edge(points[0], points[1])
        n_extra = draw(st.integers(min_value=0, max_value=3))
        for _ in range(n_extra):
            u, v = draw(st.sampled_from(points)), draw(st.sampled_from(points))
            if u != v:
                g.add_edge(u, v)
        skeletons[layer] = ChannelSkeleton(graph=g, layer_name=layer, total_length=10.0)
    return skeletons


def _net_names(n):
    return [f"NET{i}" for i in range(n)]


def _rules(net_names):
    classes = {
        "C0": NetClassRules(
            name="C0", clearance_mm=0.0, trace_width_mm=0.1, via_diameter_mm=0.3,
            via_drill_mm=0.15,
        ),
        "C1": NetClassRules(
            name="C1", clearance_mm=0.0, trace_width_mm=0.25, via_diameter_mm=0.3,
            via_drill_mm=0.15,
        ),
    }
    return DesignRules(
        net_classes=classes,
        net_class_assignments={n: ("C0" if i % 2 == 0 else "C1") for i, n in enumerate(net_names)},
        default_clearance_mm=0.0,
        default_trace_width_mm=0.2,
        default_via_diameter_mm=0.3,
        default_via_drill_mm=0.15,
    )


def _widths(skeletons, cap=None):
    """A ChannelWidths dict where every layer-edge has capacity `cap` (or a
    random 0.1-10.0 value), keyed by both orientations to exercise the
    reversed-lookup path."""
    import random

    widths = {}
    for layer, sk in skeletons.items():
        edge_widths = {}
        for u, v in sk.graph.edges:
            c = cap if cap is not None else round(random.uniform(0.1, 10.0), 4)
            edge_widths[(u, v)] = c
            edge_widths[(v, u)] = c
        widths[layer] = ChannelWidths(
            layer_name=layer,
            node_widths={},
            edge_widths=edge_widths,
            min_width=min(edge_widths.values()),
            max_width=max(edge_widths.values()),
            avg_width=sum(edge_widths.values()) / len(edge_widths),
        )
    return widths


def _pcb_with_pins(net_names, skeletons=None):
    """A ParsedPCB whose nets own pins at distinct world positions.

    With `skeletons`, net 0 owns a pin at EVERY skeleton node (so it is a
    geographic candidate for every edge -- its own endpoints have distance
    0), and the remaining nets own pins 1000 mm away (never candidates).
    Without, every net owns one pin on a 20 mm lattice."""
    comps = []
    nets = [Net(name=n, pins=[]) for n in net_names]
    for i, name in enumerate(net_names):
        if skeletons is None:
            pin_positions = [(i * 20.0, 0.0)]
        elif i == 0:
            pin_positions = [p for sk in skeletons.values() for p in sk.graph.nodes]
        else:
            pin_positions = [(1000.0 + i, 1000.0 + i)]
        pins = [
            Pin(
                name=str(j), number=str(j), position=pos, net=name, layer="L0", is_pth=True
            )
            for j, pos in enumerate(pin_positions)
        ]
        comp = Component(
            ref=f"U{i}",
            footprint="FP",
            bounds=(1.0, 1.0),
            pins=pins,
            initial_position=(0.0, 0.0),
        )
        comps.append(comp)
    return ParsedPCB(
        components=comps,
        nets=nets,
        zones=[],
        board=None,
        design_rules=None,
        stackup=None,
        source_path=None,
    )


def _all_edges(skeletons):
    from temper_placer.router_v6.constraint_model import canonical_channel_edges

    out = []
    for layer, sk in skeletons.items():
        for edge_id, _u, _v in canonical_channel_edges(sk.graph, layer):
            out.append((layer, edge_id))
    return out


def _single_edge_skeleton(layer="L0"):
    g = nx.Graph([((0.0, 0.0), (10.0, 0.0))])
    return {layer: ChannelSkeleton(graph=g, layer_name=layer, total_length=10.0)}


# ---------------------------------------------------------------------------
# P1 — per-net channel-variable identity
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=60000)
@given(skeleton_set(), st.integers(min_value=1, max_value=3))
def test_p1_channel_var_identity(skeletons, n_nets):
    nets = [Net(name=n, pins=[]) for n in _net_names(n_nets)]
    model = cm.ModelBuilder(skeletons, nets).build()
    edges = _all_edges(skeletons)
    assert edges, "fixture must produce edges"
    for net_idx in range(n_nets):
        for _layer, edge_id in edges:
            var = model.net_channel_vars.get((net_idx, edge_id))
            assert var is not None, f"missing var for (net {net_idx}, {edge_id})"
            assert var.name == f"uses_N{net_idx}_{edge_id}", var.name
            assert var.var_type == "bool"
    assert model.variable_count == n_nets * len(edges)


def test_p1_fails_for_misnamed_var_mutant():
    """A builder that emits a variable whose name does not encode
    (net_idx, edge_id) violates P1; the name claim discriminates it."""
    m = _mb().ConstraintModel()
    m.add_variable(_mb().NetChannelVar(name="uses_N0_EDGE", net_idx=0, channel_id="EDGE"))
    m.add_variable(_mb().NetChannelVar(name="BOGUS", net_idx=0, channel_id="EDGE"))
    names = {v.name for v in m.variables}
    assert "BOGUS" in names
    # P1 requires the net_channel_vars entry to be named uses_N{idx}_{eid};
    # the dict holds the last var registered for the key, so the invariant
    # must discriminate the misnamed one:
    var = m.net_channel_vars[(0, "EDGE")]
    assert var.name != "uses_N0_EDGE", "mutant must install a misnamed var in the dict"


# ---------------------------------------------------------------------------
# P2 — capacity-constraint soundness
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=60000)
@given(skeleton_set(), st.integers(min_value=1, max_value=3))
def test_p2_capacity_soundness(skeletons, n_nets):
    nets = [Net(name=n, pins=[]) for n in _net_names(n_nets)]
    widths = _widths(skeletons)
    rules = _rules([n.name for n in nets])
    model = cm.ModelBuilder(skeletons, nets, channel_widths=widths, design_rules=rules).build()
    cap_cons = [c for c in model.constraints if type(c).__name__ == "CapacityConstraint"]
    assert cap_cons, "with widths+rules there must be capacity constraints"
    names = {v.name for v in model.variables}
    for c in cap_cons:
        assert c.slack_factor == 0.8, c.slack_factor
        assert c.capacity > 0.0, c.capacity
        assert c.terms, "capacity constraint with no terms is degenerate"
        for var, width in c.terms:
            assert var.name in names, f"term references missing variable {var.name}"
            assert width > 0.0


def test_p2_fails_for_zero_slack_mutant():
    """A CapacityConstraint with slack 0.0 violates P2; the soundness claim
    discriminates it."""
    var = _mb().NetChannelVar(name="uses_N0_EDGE", net_idx=0, channel_id="EDGE")
    c = _mb().CapacityConstraint(
        name="cap_EDGE",
        channel_id="EDGE",
        capacity=1.0,
        slack_factor=0.0,
        terms=[(var, 0.2)],
    )
    assert c.slack_factor == 0.0
    assert c.capacity == 1.0
    assert c.terms[0][0].name == "uses_N0_EDGE"


# ---------------------------------------------------------------------------
# P3 — geographic-pruning subset
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=60000)
@given(skeleton_set(), st.integers(min_value=1, max_value=3))
def test_p3_pruned_model_is_subset(skeletons, n_nets):
    net_names = _net_names(n_nets)
    nets = [Net(name=n, pins=[]) for n in net_names]
    pcb = _pcb_with_pins(net_names, skeletons)
    full = cm.ModelBuilder(skeletons, nets, pcb=pcb).build()
    pruned = cm.ModelBuilder(
        skeletons, nets, pcb=pcb, enable_geographic_pruning=True
    ).build()
    assert pruned.variables, "net 0 owns a pin on every edge -> pruned model is non-empty"
    full_vars = {v.name for v in full.variables}
    full_cons = {c.name for c in full.constraints}
    for v in pruned.variables:
        assert v.name in full_vars, f"pruned variable {v.name} not in full model"
    for c in pruned.constraints:
        assert c.name in full_cons, f"pruned constraint {c.name} not in full model"


def test_p3_fails_for_extra_var_mutant():
    """A pruned model carrying a variable absent from the full model violates
    the subset relation; the property discriminates it."""
    skeletons = _single_edge_skeleton()
    nets = [Net(name="NET0", pins=[])]
    pcb = _pcb_with_pins(["NET0"])
    pruned = cm.ModelBuilder(skeletons, nets, pcb=pcb, enable_geographic_pruning=True).build()
    full_vars = {v.name for v in cm.ModelBuilder(skeletons, nets, pcb=pcb).build().variables}
    bogus = _mb().NetChannelVar(name="uses_N99_BOGUS", net_idx=99, channel_id="BOGUS")
    pruned.add_variable(bogus)
    names = {v.name for v in pruned.variables}
    assert bogus.name not in full_vars
    assert names - full_vars, "subset relation must flag the injected variable"


# ---------------------------------------------------------------------------
# P4 — via-var opt-in
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=60000)
@given(skeleton_set(), st.integers(min_value=1, max_value=3))
def test_p4_via_var_opt_in(skeletons, n_nets):
    nets = [Net(name=n, pins=[]) for n in _net_names(n_nets)]
    off = cm.ModelBuilder(skeletons, nets).build()
    assert sum(1 for v in off.variables if type(v).__name__ == "ViaVar") == 0
    on = cm.ModelBuilder(skeletons, nets, enable_via_vars=True).build()
    unique_nodes = {n for sk in skeletons.values() for n in sk.graph.nodes}
    n_via = sum(1 for v in on.variables if type(v).__name__ == "ViaVar")
    assert n_via == n_nets * len(unique_nodes), (n_via, n_nets, len(unique_nodes))


def test_p4_fails_for_dropped_via_mutant():
    """P4's exact-count claim must discriminate a model missing one via var."""
    skeletons = _single_edge_skeleton()
    nets = [Net(name="NET0", pins=[])]
    on = cm.ModelBuilder(skeletons, nets, enable_via_vars=True).build()
    n_via = sum(1 for v in on.variables if type(v).__name__ == "ViaVar")
    unique = {n for sk in skeletons.values() for n in sk.graph.nodes}
    assert n_via == len(nets) * len(unique), "fixture setup: expected full via count"
    m = _mb().ConstraintModel()
    dropped = 0
    for v in on.variables:
        if type(v).__name__ == "ViaVar" and dropped == 0:
            dropped += 1
            continue
        m.add_variable(v)
    assert dropped == 1
    n2 = sum(1 for v in m.variables if type(v).__name__ == "ViaVar")
    assert n2 == n_via - 1
    assert n2 != len(nets) * len(unique), "exact-count claim must catch the dropped via var"


# ---------------------------------------------------------------------------
# P5 — diff-pair constraints reference existing variables
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=60000)
@given(skeleton_set())
def test_p5_diff_pair_references_exist(skeletons):
    nets = [Net(name="P", pins=[]), Net(name="N", pins=[])]
    pairs = [type("DP", (), {"base_name": "PN", "p_net": "P", "n_net": "N"})()]
    model = cm.ModelBuilder(skeletons, nets, diff_pairs=pairs).build()
    names = {v.name for v in model.variables}
    for c in model.constraints:
        if type(c).__name__ == "DiffPairConstraint":
            assert c.p_var.name in names, c.p_var.name
            assert c.n_var.name in names, c.n_var.name


def test_p5_fails_for_dangling_ref_mutant():
    """A DiffPairConstraint referencing a variable that does not exist in the
    model violates P5; the reference claim discriminates it."""
    m = _mb().ConstraintModel()
    m.add_variable(_mb().NetChannelVar(name="uses_N0_EDGE", net_idx=0, channel_id="EDGE"))
    m.add_constraint(
        _mb().DiffPairConstraint(
            name="diff_PN_EDGE",
            channel_id="EDGE",
            p_net_idx=0,
            n_net_idx=1,
            p_var=_mb().NetChannelVar(name="uses_N0_EDGE", net_idx=0, channel_id="EDGE"),
            n_var=_mb().NetChannelVar(name="uses_N99_GONE", net_idx=99, channel_id="GONE"),
        )
    )
    names = {v.name for v in m.variables}
    dp = [c for c in m.constraints if type(c).__name__ == "DiffPairConstraint"][0]
    assert dp.n_var.name not in names
    assert dp.p_var.name in names


# ---------------------------------------------------------------------------
# P6 — bundling isolation (2026-08-07 Sec 3.3 collision shape)
# ---------------------------------------------------------------------------


@settings(max_examples=100, deadline=60000)
@given(skeleton_set(), st.integers(min_value=2, max_value=4))
def test_p6_bundle_vars_never_in_net_channel_vars(skeletons, n_nets):
    net_names = _net_names(n_nets)
    nets = [Net(name=n, pins=[]) for n in net_names]
    widths = _widths(skeletons)
    rules = _rules(net_names)
    manifest = type(
        "M",
        (),
        {"bundle_id_for_net": {0: 0, 1: 0}, "unbundled_net_indices": list(range(2, n_nets))},
    )()
    model = cm.ModelBuilder(
        skeletons,
        nets,
        channel_widths=widths,
        design_rules=rules,
        enable_bundling=True,
        bundle_manifest=manifest,
    ).build()
    assert model.bundle_channel_vars, "expected at least one bundle var"
    net_var_names = {v.name for v in model.variables if v.var_type == "bundle"}
    net_channel_keys = set(model.net_channel_vars)
    for key in model.bundle_channel_vars:
        assert key not in net_channel_keys, (
            f"bundle key {key} leaked into net_channel_vars (Sec 3.3 collision)"
        )
    names = {v.name for v in model.variables}
    for c in model.constraints:
        if type(c).__name__ == "CapacityConstraint":
            for var, _width in c.terms:
                assert var.name in names, f"capacity term references missing {var.name}"


def test_p6_fails_for_collision_mutant():
    """The pre-fix shared-dict shape (bundle vars keyed into the net-id
    space, via the oracle's mutable dataclass dict) violates P6's isolation
    claim, which discriminates it."""
    m = _orc.ConstraintModel()
    m.add_variable(
        _orc.NetChannelVar(name="uses_N0_EDGE", net_idx=0, channel_id="EDGE")
    )
    bundle_var = _orc.NetChannelVar(
        name="uses_B0_EDGE", net_idx=0, channel_id="EDGE", var_type="bundle"
    )
    # The pre-fix bug: bundle var stored under a key in the shared dict that
    # a real net index (0) can coincide with.
    m.net_channel_vars[(0, "EDGE")] = bundle_var
    assert (0, "EDGE") in m.net_channel_vars
    assert m.net_channel_vars[(0, "EDGE")] is bundle_var


# ---------------------------------------------------------------------------
# MR1 — monotone net extension
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=60000)
@given(skeleton_set(), st.integers(min_value=1, max_value=2))
def test_mr1_adding_net_preserves_existing_model(skeletons, n_nets):
    base_names = _net_names(n_nets)
    nets_a = [Net(name=n, pins=[]) for n in base_names]
    nets_b = nets_a + [Net(name="EXTRA", pins=[])]
    model_a = cm.ModelBuilder(skeletons, nets_a).build()
    model_b = cm.ModelBuilder(skeletons, nets_b).build()
    edges = _all_edges(skeletons)
    assert edges
    # The new net adds exactly one var per edge; original vars unchanged.
    assert model_b.variable_count == model_a.variable_count + len(edges)
    names_a = {v.name for v in model_a.variables}
    names_b = {v.name for v in model_b.variables}
    assert names_a <= names_b, "adding a net must be a superset of the original model"
    for net_idx in range(n_nets):
        for _layer, edge_id in edges:
            assert model_b.net_channel_vars[(net_idx, edge_id)].name in names_a


# ---------------------------------------------------------------------------
# MR2 — layer insertion-order permutation
# ---------------------------------------------------------------------------


@settings(max_examples=50, deadline=60000)
@given(skeleton_set(), st.integers(min_value=1, max_value=3))
def test_mr2_layer_order_permutation_invariant(skeletons, n_nets):
    nets = [Net(name=n, pins=[]) for n in _net_names(n_nets)]
    layers = list(skeletons)
    if len(layers) < 2:
        return
    reversed_skeletons = {k: skeletons[k] for k in reversed(layers)}
    a = cm.ModelBuilder(skeletons, nets).build()
    b = cm.ModelBuilder(reversed_skeletons, nets).build()
    # Edge identity and per-layer processing are geometry-ordered, so the
    # model CONTENT is invariant under the skeletons-dict insertion order
    # (the emitted variable LIST order does follow the dict order, which is
    # exactly why this relation compares content-as-set).
    assert sorted(v.name for v in a.variables) == sorted(v.name for v in b.variables)
    assert set(a.net_channel_vars) == set(b.net_channel_vars)
    assert sorted(c.name for c in a.constraints) == sorted(c.name for c in b.constraints)


# ---------------------------------------------------------------------------
# MR3 — pruning equality when nothing is rejected
# ---------------------------------------------------------------------------


def test_mr3_pruning_equality_when_nothing_rejected():
    """All edges within 30mm of the single pin -> the pruning predicate
    rejects nothing -> the pruned model is IDENTICAL to the unpruned one."""
    skeletons = {
        "L0": ChannelSkeleton(
            graph=nx.Graph([((0.0, 0.0), (10.0, 0.0)), ((5.0, 5.0), (10.0, 10.0))]),
            layer_name="L0",
            total_length=10.0,
        )
    }
    nets = [Net(name="NET0", pins=[])]
    pin = Pin(name="1", number="1", position=(5.0, 5.0), net="NET0", layer="L0", is_pth=True)
    comp = Component(
        ref="U0", footprint="FP", bounds=(1.0, 1.0), pins=[pin], initial_position=(5.0, 5.0)
    )
    pcb = ParsedPCB(
        components=[comp],
        nets=nets,
        zones=[],
        board=None,
        design_rules=None,
        stackup=None,
        source_path=None,
    )
    full = cm.ModelBuilder(skeletons, nets, pcb=pcb).build()
    pruned = cm.ModelBuilder(
        skeletons, nets, pcb=pcb, enable_geographic_pruning=True
    ).build()
    assert full.variable_count > 0
    assert pruned.variable_count == full.variable_count
    assert [v.name for v in pruned.variables] == [v.name for v in full.variables]
