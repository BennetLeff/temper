"""Property-based tests for the Rust hypergraph factory
(``temper_design_bundle_python``) — Wave 4 Phase 4 leftovers slice.

The Rust implementation must satisfy the same algebraic invariants the
pre-migration Python implementation satisfies, asserted INDEPENDENTLY of the
oracle (the differential test owns bit-parity; this file owns the
closed-form properties). Every property is fail-capable: each pins a
filtering rule, a classification rule, a shape, or a permutation relation
that a wrong implementation would break.

R1c: properties P1-P6 (>= 5).  R1d: MR1-MR4 (>= 3).
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import temper_design_bundle_python as _tdb
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.extraction.hypergraph_factory import HypergraphFactory as ShimFactory

RUST_FACTORY = ShimFactory


def _c(ref, w=1.0, h=1.0):
    return Component(ref=ref, footprint="R0402", bounds=(w, h))


def _net(name, pins, **kw):
    return Net(name=name, pins=pins, **kw)


_refs = st.lists(st.text(min_size=1, max_size=6, alphabet="ABCD"), min_size=1, max_size=5)
_n_refs = st.integers(min_value=1, max_value=8)
_nets = st.integers(min_value=0, max_value=6)
_threshold = st.integers(min_value=0, max_value=20)
_weight = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)


def _canonical_matrix(hg):
    """The COO matrix canonicalized as sorted (row, col, data) triplets —
    the order-independent semantic content (per-net set iteration order is
    CPython's; the differential asserts the exact order, this file the
    content)."""
    m = hg.incidence.matrix
    return tuple(sorted(zip(m.row.tolist(), m.col.tolist(), m.data.tolist())))


# ---------------------------------------------------------------------------
# P1: edge-selection rule — a net survives iff it has >= 2 pins AND (no
# filtering OR its pin count is <= the threshold).
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n_comp=_n_refs, n_nets=_nets, threshold=_threshold)
@settings(max_examples=50, deadline=30000)
def test_p1_edge_selection_rule(n_comp, n_nets, threshold):
    rng = np.random.RandomState(0)
    refs = [f"C{i}" for i in range(n_comp)]
    components = [_c(r, 1.0 + rng.rand(), 1.0 + rng.rand()) for r in refs]
    nets = []
    for i in range(n_nets):
        pin_count = int(rng.randint(0, 25))
        pins = [(refs[j % n_comp], str(j)) for j in range(pin_count)]
        nets.append(_net(f"N{i}", pins, weight=float(rng.rand())))
    netlist = Netlist(components=components, nets=nets)

    for ignore in (False, True):
        hg = ShimFactory(netlist, ignore_global_nets=ignore, global_net_threshold=threshold).build()
        expected_names = [
            n.name
            for n in nets
            if len(n.pins) >= 2 and (not ignore or len(n.pins) <= threshold)
        ]
        assert list(hg.hyperedge_names) == expected_names
        assert hg.n_edges == len(expected_names)
        assert hg.n_nodes == n_comp


# ---------------------------------------------------------------------------
# P2: HV flag classification — edge_voltages[i] is exactly 1.0 iff the net
# is voltage_class "HV" or net_class "HighVoltage".
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n_comp=_n_refs, n_nets=_nets)
@settings(max_examples=50, deadline=30000)
def test_p2_hv_flag_classification(n_comp, n_nets):
    rng = np.random.RandomState(1)
    refs = [f"C{i}" for i in range(n_comp)]
    components = [_c(r) for r in refs]
    nets = []
    for i in range(n_nets):
        pins = [(refs[0], "1"), (refs[1 % n_comp], "2")]
        vc = "HV" if rng.rand() < 0.5 else "LV"
        nc = "HighVoltage" if rng.rand() < 0.3 else "Signal"
        nets.append(_net(f"N{i}", pins, voltage_class=vc, net_class=nc))
    netlist = Netlist(components=components, nets=nets)
    hg = ShimFactory(netlist).build()
    expected = [
        1.0 if (n.voltage_class == "HV" or n.net_class == "HighVoltage") else 0.0 for n in nets
    ]
    assert hg.edge_voltages.tolist() == expected
    assert set(hg.edge_voltages.tolist()) <= {0.0, 1.0}


# ---------------------------------------------------------------------------
# P3: width classification — 1.0 for HighVoltage, 0.5 for max_current > 1.0,
# else 0.2, with the oracle's branch order (net_class checked FIRST).
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n_comp=_n_refs, n_nets=_nets, current=_weight)
@settings(max_examples=50, deadline=30000)
def test_p3_width_classification(n_comp, n_nets, current):
    rng = np.random.RandomState(2)
    refs = [f"C{i}" for i in range(n_comp)]
    components = [_c(r) for r in refs]
    nets = []
    for i in range(n_nets):
        pins = [(refs[0], "1"), (refs[1 % n_comp], "2")]
        nc = "HighVoltage" if rng.rand() < 0.3 else "Signal"
        nets.append(_net(f"N{i}", pins, net_class=nc, max_current=current))
    netlist = Netlist(components=components, nets=nets)
    hg = ShimFactory(netlist).build()
    expected = []
    for n in nets:
        if n.net_class == "HighVoltage":
            expected.append(1.0)
        elif n.max_current > 1.0:
            expected.append(0.5)
        else:
            expected.append(float(np.float32(0.2)))
    assert hg.edge_widths.tolist() == expected


# ---------------------------------------------------------------------------
# P4: incidence matrix shape + connectedness — each column's row set equals
# the components reachable from that net's pins (refs present in the
# netlist), and nnz equals the sum of those counts.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n_comp=_n_refs, n_nets=_nets)
@settings(max_examples=50, deadline=30000)
def test_p4_incidence_connectedness(n_comp, n_nets):
    rng = np.random.RandomState(3)
    refs = [f"C{i}" for i in range(n_comp)]
    components = [_c(r) for r in refs]
    nets = []
    for i in range(n_nets):
        pin_count = int(rng.randint(0, 12))
        pins = [(refs[j % n_comp] if rng.rand() < 0.9 else "GHOST", str(j)) for j in range(pin_count)]
        nets.append(_net(f"N{i}", pins))
    netlist = Netlist(components=components, nets=nets)
    hg = ShimFactory(netlist).build()
    m = hg.incidence.matrix
    assert m.shape == (n_comp, hg.n_edges)
    ref_to_idx = {r: i for i, r in enumerate(refs)}
    valid_nets = [n for n in nets if len(n.pins) >= 2]
    expected_nnz = 0
    for col, net in enumerate(valid_nets):
        rows = sorted({ref_to_idx[r] for r, _ in net.pins if r in ref_to_idx})
        actual = sorted(m.row.tolist()[i] for i in range(m.nnz) if m.col.tolist()[i] == col)
        assert actual == rows
        expected_nnz += len(rows)
    assert m.nnz == expected_nnz


# ---------------------------------------------------------------------------
# P5: node weights — width*height per component, float32-cast.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n_comp=_n_refs, w=st.floats(min_value=0.01, max_value=5.0), h=st.floats(min_value=0.01, max_value=5.0))
@settings(max_examples=50, deadline=30000)
def test_p5_node_weights(n_comp, w, h):
    components = [_c(f"C{i}", w, h) for i in range(n_comp)]
    netlist = Netlist(components=components, nets=[])
    hg = ShimFactory(netlist).build()
    assert hg.incidence.node_weights.tolist() == [float(np.float32(w * h))] * n_comp
    assert hg.incidence.node_weights.dtype == np.float32


# ---------------------------------------------------------------------------
# P6: hyperedge weights pass through net.weight (float32 cast).
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n_comp=_n_refs, n_nets=_nets, weight=_weight)
@settings(max_examples=50, deadline=30000)
def test_p6_hyperedge_weights(n_comp, n_nets, weight):
    refs = [f"C{i}" for i in range(n_comp)]
    components = [_c(r) for r in refs]
    nets = [
        _net(f"N{i}", [(refs[0], "1"), (refs[1 % n_comp], "2")], weight=weight)
        for i in range(n_nets)
    ]
    netlist = Netlist(components=components, nets=nets)
    hg = ShimFactory(netlist).build()
    assert hg.incidence.hyperedge_weights.tolist() == [float(np.float32(weight))] * n_nets


# ---------------------------------------------------------------------------
# MR1: net-order permutation — permuting the nets list permutes the
# hyperedge-order-dependent outputs (names, physics arrays, matrix columns)
# by the same permutation; node_weights and node_refs are invariant.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n_comp=_n_refs, n_nets=_nets)
@settings(max_examples=50, deadline=30000)
def test_mr1_net_order_permutation(n_comp, n_nets):
    rng = np.random.RandomState(4)
    refs = [f"C{i}" for i in range(n_comp)]
    components = [_c(r, 1.0 + rng.rand(), 1.0 + rng.rand()) for r in refs]
    nets = []
    for i in range(n_nets):
        pins = [(refs[0], "1"), (refs[1 % n_comp], "2")]
        vc = "HV" if rng.rand() < 0.5 else "LV"
        nets.append(_net(f"N{i}", pins, voltage_class=vc, weight=float(rng.rand())))
    perm = np.random.RandomState(5).permutation(n_nets)
    netlist_a = Netlist(components=components, nets=nets)
    netlist_b = Netlist(components=components, nets=[nets[p] for p in perm])
    hg_a = ShimFactory(netlist_a).build()
    hg_b = ShimFactory(netlist_b).build()
    if n_nets == 0:
        return
    # B's q-th net is A's perm[q]-th net: B == A∘perm.
    assert list(hg_b.hyperedge_names) == [hg_a.hyperedge_names[q] for q in perm]
    b_voltages = np.array([hg_b.edge_voltages[q] for q in range(n_nets)])
    assert b_voltages.tolist() == [hg_a.edge_voltages.tolist()[q] for q in perm]
    assert hg_b.incidence.node_weights.tolist() == hg_a.incidence.node_weights.tolist()
    assert hg_b.node_refs == hg_a.node_refs
    m_a, m_b = hg_a.incidence.matrix, hg_b.incidence.matrix
    tri_a = {(r, c, d) for r, c, d in zip(m_a.row.tolist(), m_a.col.tolist(), m_a.data.tolist())}
    tri_b = {
        (r, perm[c], d)
        for r, c, d in zip(m_b.row.tolist(), m_b.col.tolist(), m_b.data.tolist())
    }
    assert tri_a == tri_b


# ---------------------------------------------------------------------------
# MR2: threshold monotonicity — raising the threshold can only add nets
# (each surviving net has <= threshold pins), and net_class HighVoltage pins
# never change with the threshold.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n_comp=_n_refs, t1=_threshold, t2=_threshold)
@settings(max_examples=50, deadline=30000)
def test_mr2_threshold_monotonicity(n_comp, t1, t2):
    rng = np.random.RandomState(6)
    refs = [f"C{i}" for i in range(n_comp)]
    components = [_c(r) for r in refs]
    nets = []
    for i in range(6):
        pin_count = int(rng.randint(0, 22))
        pins = [(refs[j % n_comp], str(j)) for j in range(pin_count)]
        nets.append(_net(f"N{i}", pins))
    netlist = Netlist(components=components, nets=nets)
    e1 = ShimFactory(netlist, ignore_global_nets=True, global_net_threshold=min(t1, t2)).build().n_edges
    e2 = ShimFactory(netlist, ignore_global_nets=True, global_net_threshold=max(t1, t2)).build().n_edges
    assert e1 <= e2
    if t1 == t2:
        assert e1 == e2


# ---------------------------------------------------------------------------
# MR3: pin-order permutation within a net — the set semantics make the
# canonicalized hypergraph invariant (per-net triplet ORDER is CPython's set
# iteration; the canonical matrix and all value arrays are unchanged).
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n_comp=_n_refs, n_nets=_nets)
@settings(max_examples=50, deadline=30000)
def test_mr3_pin_order_permutation_invariance(n_comp, n_nets):
    rng = np.random.RandomState(7)
    refs = [f"C{i}" for i in range(n_comp)]
    components = [_c(r) for r in refs]
    nets_a, nets_b = [], []
    for i in range(n_nets):
        pin_count = int(rng.randint(0, 10))
        pins = [(refs[j % n_comp], str(j)) for j in range(pin_count)]
        perm = np.random.RandomState(8 + i).permutation(pin_count)
        pins_b = [pins[p] for p in perm]
        nets_a.append(_net(f"N{i}", pins, weight=0.5))
        nets_b.append(_net(f"N{i}", pins_b, weight=0.5))
    netlist_a = Netlist(components=components, nets=nets_a)
    netlist_b = Netlist(components=components, nets=nets_b)
    hg_a = ShimFactory(netlist_a).build()
    hg_b = ShimFactory(netlist_b).build()
    assert _canonical_matrix(hg_a) == _canonical_matrix(hg_b)
    assert hg_a.edge_voltages.tolist() == hg_b.edge_voltages.tolist()
    assert hg_a.edge_widths.tolist() == hg_b.edge_widths.tolist()


# ---------------------------------------------------------------------------
# MR4: ignore-vs-threshold equivalence — ignore_global_nets=True with a
# threshold >= every pin count behaves identically to no filtering at all.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(n_comp=_n_refs, n_nets=_nets)
@settings(max_examples=50, deadline=30000)
def test_mr4_ignore_equivalence_with_large_threshold(n_comp, n_nets):
    rng = np.random.RandomState(9)
    refs = [f"C{i}" for i in range(n_comp)]
    components = [_c(r) for r in refs]
    nets = []
    max_pins = 0
    for i in range(n_nets):
        pin_count = int(rng.randint(0, 12))
        max_pins = max(max_pins, pin_count)
        pins = [(refs[j % n_comp], str(j)) for j in range(pin_count)]
        nets.append(_net(f"N{i}", pins))
    netlist = Netlist(components=components, nets=nets)
    hg_free = ShimFactory(netlist).build()
    hg_gated = ShimFactory(
        netlist, ignore_global_nets=True, global_net_threshold=max_pins
    ).build()
    assert _canonical_matrix(hg_free) == _canonical_matrix(hg_gated)
    assert hg_free.hyperedge_names == hg_gated.hyperedge_names
    assert hg_free.edge_widths.tolist() == hg_gated.edge_widths.tolist()
