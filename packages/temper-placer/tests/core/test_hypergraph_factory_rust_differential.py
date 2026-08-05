"""Differential test: Rust hypergraph factory (``temper_design_bundle_python``)
vs the pinned Python oracle.

Wave 4, Phase 4 leftovers slice — the extraction/hypergraph_factory.py
migration. The Rust pyo3 pyclasses (``HypergraphFactory`` +
``HypergraphBuildResult`` in ``temper-design-bundle/src/hypergraph_factory.rs``)
must reproduce the pre-migration Python implementation of
``temper_placer/extraction/hypergraph_factory.py`` bit-identically. The
pre-migration implementation is pinned verbatim as the oracle
(``_hypergraph_factory_py_oracle.py``, commit 58b302ce8) and every assertion
here drives IDENTICAL inputs through both sides.

Comparison conventions:
- numpy arrays as ``(dtype, shape, tobytes())`` (bit-exact);
- the scipy COO matrix by ``(shape, nnz, data-tobytes, row, col)`` — the
  triplet ORDER is asserted, not just the multiset, because the oracle's
  per-net triplet order comes from CPython set iteration, and the shim
  preserves it by re-deriving the same set from the same pin-order list;
- every non-float leaf's concrete type rides in the comparison key.

Boundary notes (KTD9 — kept Python-side, argued in ``VERIFICATION.md``):
- ``scipy.sparse.coo_matrix`` construction stays Python (scipy sparse
  semantics are not reimplementable);
- the numpy dtype casts (``np.array(..., dtype=np.float32)``) stay Python
  (numpy conversion semantics);
- CPython ``set`` iteration order stays Python — the shim builds
  ``set(connected_indices)`` from the Rust-returned pin-order list, which is
  the exact construction the oracle performed, so iteration order (and
  therefore the COO triplet order) is CPython's on both sides;
- the Rust side owns the net filtering, the ref→index mapping, the physics
  classification (HV/width/currents), the per-net connected-index lists in
  pin order, and the node/hyperedge weight collection — with every value
  arithmetic (``width * height``, ``max_current`` passthrough) performed by
  Python so no type-preserving conversion is lost.
"""

from __future__ import annotations

import numpy as np
import pytest
import temper_design_bundle_python as _tdb

import tests.core._hypergraph_factory_py_oracle as _oracle
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.extraction.hypergraph_factory import (
    HypergraphFactory as ShimFactory,
    netlist_to_hypergraph as shim_netlist_to_hypergraph,
)

# Rust symbols under test — must exist or this file fails to collect (RED).
RUST_FACTORY = _tdb.HypergraphFactory
RUST_BUILD_RESULT = _tdb.HypergraphBuildResult


# ---------------------------------------------------------------------------
# Canonicalization.
# ---------------------------------------------------------------------------


def _arr(a) -> tuple:
    return (a.dtype.str, a.shape, a.tobytes())


def _matrix_key(m):
    return (
        m.shape,
        m.nnz,
        _arr(m.data),
        m.row.tolist(),
        m.col.tolist(),
    )


def _hg_key(hg):
    return (
        hg.n_nodes,
        hg.n_edges,
        list(hg.node_refs),
        list(hg.hyperedge_names),
        _matrix_key(hg.incidence.matrix),
        _arr(hg.incidence.node_weights),
        _arr(hg.incidence.hyperedge_weights),
        _arr(hg.edge_voltages),
        _arr(hg.edge_currents),
        _arr(hg.edge_widths),
    )


def _both(netlist, **kw):
    py_hg = _oracle.HypergraphFactory(netlist, **kw).build()
    rust_hg = ShimFactory(netlist, **kw).build()
    return py_hg, rust_hg


def _both_wrapper(netlist, **kw):
    py_hg = _oracle.netlist_to_hypergraph(netlist, **kw)
    rust_hg = shim_netlist_to_hypergraph(netlist, **kw)
    return py_hg, rust_hg


# ---------------------------------------------------------------------------
# Fixtures: small netlists exercising every classification branch.
# ---------------------------------------------------------------------------


def _c(ref, w=1.0, h=1.0):
    return Component(ref=ref, footprint="R0402", bounds=(w, h))


def _net(name, pins, **kw):
    return Net(name=name, pins=pins, **kw)


@pytest.fixture
def star_ground_netlist():
    """100-component ground net (global) + a 2-pin signal net."""
    components = [_c(f"U{i}") for i in range(100)]
    gnd = _net("GND", [(f"U{i}", "GND") for i in range(100)])
    sig = _net("SIG", [("U0", "1"), ("U1", "1")])
    return Netlist(components=components, nets=[gnd, sig])


@pytest.fixture
def physics_netlist():
    """HV bus (net_class HighVoltage), high-current net, plain signal net."""
    c1 = _c("C1", 2.0, 3.0)
    c2 = _c("C2", 0.5, 4.0)
    c3 = _c("C3")
    hv = _net("HV_BUS", [("C1", "1"), ("C2", "1")], net_class="HighVoltage")
    hi = _net("PWR", [("C2", "2"), ("C3", "1")], max_current=2.5)
    lo = _net("SIG", [("C1", "2"), ("C3", "2")], max_current=0.1)
    return Netlist(components=[c1, c2, c3], nets=[hv, hi, lo])


@pytest.fixture
def mixed_netlist():
    """Every filtering branch: single-pin, two-pin, many-pin, unknown refs,
    duplicate pin refs, voltage_class HV, custom weights."""
    components = [_c("R1", 1.0, 2.0), _c("R2", 3.0, 1.0), _c("R3", 0.5, 0.5)]
    nets = [
        _net("SINGLE", [("R1", "1")]),
        _net("DUP", [("R1", "1"), ("R1", "2")], weight=0.5),
        _net("UNKNOWN_REF", [("R1", "3"), ("NO_SUCH", "1")]),
        _net("BIG", [(f"R{i % 3}", str(i)) for i in range(60)], weight=2.0),
        _net("HV", [("R2", "1"), ("R3", "1")], voltage_class="HV", weight=0.25),
        _net("CURRENT", [("R3", "2"), ("R2", "2")], max_current=5.0),
    ]
    return Netlist(components=components, nets=nets)


# ---------------------------------------------------------------------------
# Full-build parity.
# ---------------------------------------------------------------------------


def test_star_ground_filtering_parity(star_ground_netlist):
    """ignore_global_nets=True + threshold 50: only the signal net survives —
    the full hypergraph (matrix triplets included) is bit-identical."""
    py_hg, rust_hg = _both(star_ground_netlist, ignore_global_nets=True, global_net_threshold=50)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    assert rust_hg.n_edges == 1
    assert rust_hg.hyperedge_names == ["SIG"]
    assert rust_hg.incidence.matrix.shape == (100, 1)


def test_no_filtering_parity(star_ground_netlist):
    """ignore_global_nets=False: both nets survive; the ground net's 100
    connections produce 100 triplets in the oracle's set-iteration order."""
    py_hg, rust_hg = _both(star_ground_netlist)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    assert rust_hg.n_edges == 2
    assert rust_hg.incidence.matrix.shape == (100, 2)


def test_custom_threshold_parity(star_ground_netlist):
    """threshold 100: the 100-pin ground net is NOT > 100, so it survives."""
    py_hg, rust_hg = _both(star_ground_netlist, ignore_global_nets=True, global_net_threshold=100)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    assert rust_hg.n_edges == 2


def test_physics_embedding_parity(physics_netlist):
    """HV via net_class, high-current width 0.5, plain width 0.2, node
    weights width*height (int*int → int, float32 cast) — all bit-identical."""
    py_hg, rust_hg = _both(physics_netlist)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    assert rust_hg.edge_voltages.tolist() == [1.0, 0.0, 0.0]
    assert rust_hg.edge_widths.tolist() == [1.0, 0.5, float(np.float32(0.2))]
    assert rust_hg.incidence.node_weights.tolist() == [6.0, 2.0, 1.0]


def test_voltage_class_hv_flag(physics_netlist):
    """voltage_class 'HV' alone (no HighVoltage class) also sets the flag."""
    netlist = Netlist(
        components=[_c("A"), _c("B")],
        nets=[_net("HVV", [("A", "1"), ("B", "1")], voltage_class="HV", max_current=0.1)],
    )
    py_hg, rust_hg = _both(netlist)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    assert rust_hg.edge_voltages.tolist() == [1.0]
    assert rust_hg.edge_widths.tolist() == [float(np.float32(0.2))]


def test_mixed_netlist_parity(mixed_netlist):
    """All branches at once: single-pin filtered, duplicate-ref net, unknown
    ref, 60-pin global net (with and without filtering), HV flag, custom
    weights — full hypergraph parity."""
    for kw in ({}, {"ignore_global_nets": True, "global_net_threshold": 50}):
        py_hg, rust_hg = _both(mixed_netlist, **kw)
        assert _hg_key(py_hg) == _hg_key(rust_hg)


def test_mixed_netlist_filtered_counts(mixed_netlist):
    """Filtering arithmetic: without it 5 nets survive (SINGLE dropped);
    with ignore+threshold 50 only HV and CURRENT survive."""
    rust_hg_all = ShimFactory(mixed_netlist).build()
    assert rust_hg_all.n_edges == 5
    assert rust_hg_all.hyperedge_names == ["DUP", "UNKNOWN_REF", "BIG", "HV", "CURRENT"]
    rust_hg_f = ShimFactory(mixed_netlist, ignore_global_nets=True, global_net_threshold=50).build()
    assert rust_hg_f.n_edges == 4
    assert rust_hg_f.hyperedge_names == ["DUP", "UNKNOWN_REF", "HV", "CURRENT"]


def test_pyclass_build_result_direct(star_ground_netlist):
    """The raw pyclass build() returns a HypergraphBuildResult whose fields
    are the shim's assembly inputs — the migrated compute boundary."""
    parts = RUST_FACTORY(star_ground_netlist, ignore_global_nets=True, global_net_threshold=50).build()
    assert isinstance(parts, RUST_BUILD_RESULT)
    assert parts.n_nodes == 100
    assert parts.n_edges == 1
    assert parts.hyperedge_names == ["SIG"]
    assert parts.edge_voltages == [0.0]
    assert parts.edge_widths == [0.2]
    assert parts.node_refs[0] == "U0"
    assert parts.connected_indices == [[0, 1]]


def test_empty_netlist_parity():
    """No components, no nets: zero-size matrix and arrays on both sides."""
    netlist = Netlist(components=[], nets=[])
    py_hg, rust_hg = _both(netlist)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    assert rust_hg.n_nodes == 0 and rust_hg.n_edges == 0
    assert rust_hg.incidence.matrix.shape == (0, 0)
    assert rust_hg.incidence.matrix.nnz == 0


def test_components_without_nets_parity():
    """Components present, no nets: (N, 0) matrix, node_weights populated."""
    netlist = Netlist(components=[_c("A", 2.0, 3.0), _c("B", 0.5, 0.25)], nets=[])
    py_hg, rust_hg = _both(netlist)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    assert rust_hg.incidence.node_weights.tolist() == [6.0, 0.125]
    assert rust_hg.incidence.matrix.shape == (2, 0)


def test_nets_without_components_parity():
    """Nets whose refs match no component: zero triplets, full edge arrays."""
    netlist = Netlist(components=[], nets=[_net("ORPHAN", [("X", "1"), ("Y", "1")], weight=3.0)])
    py_hg, rust_hg = _both(netlist)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    assert rust_hg.n_edges == 1
    assert rust_hg.incidence.matrix.nnz == 0


def test_int_widths_heights_type_preservation():
    """int bounds: width*height stays int through the Python multiply, and
    the float32 cast of an int leaf is numpy's on both sides."""
    c1 = Component(ref="Q1", footprint="SOT", bounds=(2, 3))
    c2 = Component(ref="Q2", footprint="SOT", bounds=(2, 3))
    netlist = Netlist(
        components=[c1, c2],
        nets=[_net("N", [("Q1", "1"), ("Q2", "1")], weight=7)],
    )
    py_hg, rust_hg = _both(netlist)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    assert rust_hg.incidence.node_weights.tolist() == [6.0, 6.0]
    assert rust_hg.incidence.hyperedge_weights.tolist() == [7.0]


def test_float32_boundary_weight():
    """weight=0.2 (not exactly representable): the f32 cast is numpy's on
    both sides — the Rust passthrough never touches the value."""
    netlist = Netlist(
        components=[_c("A"), _c("B")],
        nets=[_net("N", [("A", "1"), ("B", "1")], weight=0.2)],
    )
    py_hg, rust_hg = _both(netlist)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    assert (
        np.float32(rust_hg.incidence.hyperedge_weights[0]).tobytes()
        == np.float32(0.2).tobytes()
    )


def test_wrapper_parity(star_ground_netlist):
    """netlist_to_hypergraph is a thin wrapper — the factory result equals it."""
    py_hg, rust_hg = _both_wrapper(star_ground_netlist)
    assert _hg_key(py_hg) == _hg_key(rust_hg)


def test_factory_attributes_parity(mixed_netlist):
    """The factory stores its constructor args as attributes, like the
    oracle class."""
    f = RUST_FACTORY(mixed_netlist, ignore_global_nets=True, global_net_threshold=37)
    assert f.ignore_global_nets is True
    assert f.global_net_threshold == 37
    assert f.netlist is mixed_netlist


def test_duplicate_component_refs_last_wins():
    """Two components sharing a ref: node_ref_to_idx keeps the LAST — the
    net's triplet lands on the last component's index; node_weights holds
    BOTH entries."""
    c1 = _c("R1", 1.0, 1.0)
    c2 = _c("R1", 2.0, 2.0)
    c3 = _c("R2")
    netlist = Netlist(
        components=[c1, c2, c3],
        nets=[_net("N", [("R1", "1"), ("R2", "1")], weight=0.5)],
    )
    py_hg, rust_hg = _both(netlist)
    assert _hg_key(py_hg) == _hg_key(rust_hg)
    # The net connects to index 1 (the LAST R1) and index 2 (R2).
    assert sorted(rust_hg.incidence.matrix.row.tolist()) == [1, 2]
    assert rust_hg.incidence.node_weights.tolist() == [1.0, 4.0, 1.0]


def test_matrix_triplet_order_is_cpython_set_order(mixed_netlist):
    """The DUP net (two pins on the same component) collapses to ONE triplet;
    the BIG net's 60-pin set (refs R1/R2 repeated 20× each) collapses to two
    triplets — the per-net triplet ORDER is CPython's small-int set
    iteration, identical on both sides because both build the identical set
    from the identical pin-order list."""
    py_hg, rust_hg = _both(mixed_netlist)
    assert py_hg.incidence.matrix.row.tolist() == rust_hg.incidence.matrix.row.tolist()
    assert py_hg.incidence.matrix.col.tolist() == rust_hg.incidence.matrix.col.tolist()
    dup_col = 0
    big_col = rust_hg.hyperedge_names.index("BIG")
    assert rust_hg.incidence.matrix.col.tolist().count(dup_col) == 1  # DUP collapsed
    big_rows = [
        r for r, c in zip(rust_hg.incidence.matrix.row.tolist(), rust_hg.incidence.matrix.col.tolist())
        if c == big_col
    ]
    assert sorted(big_rows) == [0, 1]  # R1, R2 — R0 is not a component
    assert len(big_rows) == 2
    assert rust_hg.incidence.matrix.nnz == 8
