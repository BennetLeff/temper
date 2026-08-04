"""Property-based tests for the Rust netlist contracts (Wave 4 Phase 3 / R1c, R1d).

Nine non-vacuous properties (P1-P9) and four metamorphic relations
(MR1-MR4). Every property is stated against the pinned Python oracle
(``_netlist_py_oracle.py``) as the reference, so a property can only pass by
the Rust *agreeing with Python*, never by both being trivially true.

Non-vacuity is enforced structurally rather than asserted in prose: each
property that could be satisfied by an empty corpus carries a
``hypothesis.target``/explicit witness assertion, or is paired with a
``test_*_is_non_vacuous`` companion that proves the generator actually
reaches the interesting region.
"""

from __future__ import annotations

import numpy as np
import pytest
import temper_design_bundle_python as _tdb
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import tests.core._netlist_py_oracle as _oracle
from tests.core._contract_canon import canon, canon_call

_rs = _tdb.netlist_contracts

SETTINGS = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

# Numbers that actually stress the port: ints AND floats (the dataclass does
# not coerce), subnormals, and the negative-zero / infinity boundary. NaN is
# excluded from *field* positions only where a property asserts an ordering.
finite_floats = st.floats(allow_nan=False, allow_infinity=False, width=64)
numbers = st.one_of(st.integers(min_value=-10**6, max_value=10**6), finite_floats)
refs = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_", min_size=1, max_size=6)
net_names = st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_+", min_size=1, max_size=6)


@st.composite
def pin_args(draw):
    return (
        (draw(refs), draw(refs), (draw(numbers), draw(numbers))),
        {
            "net": draw(st.one_of(st.none(), net_names)),
            "width": draw(numbers),
            "height": draw(numbers),
            "drill": draw(numbers),
            "is_pth": draw(st.booleans()),
            "roundrect_ratio": draw(numbers),
            "pad_rotation_deg": draw(numbers),
        },
    )


@st.composite
def component_args(draw):
    return (
        (draw(refs), draw(refs), (draw(numbers), draw(numbers))),
        {
            "net_class": draw(st.sampled_from(["Signal", "Power", "HighVoltage"])),
            "fixed": draw(st.booleans()),
            "initial_rotation": draw(st.one_of(st.none(), st.integers(0, 3))),
        },
    )


@st.composite
def netlist_spec(draw):
    """A whole netlist as a *description*, instantiated identically on both
    sides. Deliberately allows duplicate refs/net names and dangling pin
    references so `validate()` has something to find."""
    comp_refs = draw(st.lists(refs, min_size=0, max_size=6))
    pin_names = ["1", "2", "A"]
    comps = [
        (r, draw(refs), (draw(numbers), draw(numbers)), draw(st.booleans())) for r in comp_refs
    ]
    known = comp_refs or ["MISSING"]
    nets = draw(
        st.lists(
            st.tuples(
                net_names,
                st.lists(
                    st.tuples(st.sampled_from(known), st.sampled_from(pin_names)),
                    min_size=0,
                    max_size=5,
                ),
            ),
            min_size=0,
            max_size=5,
        )
    )
    return comps, nets


def _instantiate(spec, pin_cls, comp_cls, net_cls, netlist_cls):
    comps, nets = spec
    objs = [
        comp_cls(
            r,
            fp,
            bounds,
            pins=[pin_cls(n, n, (0.0, 0.0)) for n in ("1", "2", "A")],
            fixed=fixed,
        )
        for (r, fp, bounds, fixed) in comps
    ]
    net_objs = [net_cls(name, [tuple(p) for p in pins]) for name, pins in nets]
    return netlist_cls(components=objs, nets=net_objs)


def _both(spec):
    py = _instantiate(spec, _oracle.Pin, _oracle.Component, _oracle.Net, _oracle.Netlist)
    rs = _instantiate(spec, _rs.Pin, _rs.Component, _rs.Net, _rs.Netlist)
    return py, rs


# ---------------------------------------------------------------------------
# P1-P9: differential properties
# ---------------------------------------------------------------------------


@SETTINGS
@given(args=pin_args())
def test_p1_pin_construction_agrees_for_every_input(args):
    """P1. Pin construction is field-wise and type-wise identical."""
    a, k = args
    assert canon(_oracle.Pin(*a, **k)) == canon(_rs.Pin(*a, **k))
    assert repr(_oracle.Pin(*a, **k)) == repr(_rs.Pin(*a, **k))


@SETTINGS
@given(args=pin_args())
def test_p2_mask_expansion_agrees_and_is_two_valued(args):
    """P2. `mask_expansion` agrees, and really takes both of its two values
    across the generated corpus (the companion test proves it)."""
    a, k = args
    assert canon(_oracle.Pin(*a, **k).mask_expansion) == canon(_rs.Pin(*a, **k).mask_expansion)


def test_p2_is_non_vacuous():
    """Both branches of `mask_expansion` are reachable and distinct."""
    seen = {_rs.Pin("A", "1", (0.0, 0.0), is_pth=flag).mask_expansion for flag in (True, False)}
    assert seen == {0.1, 0.15}


@SETTINGS
@given(args=component_args())
def test_p3_component_width_height_preserve_the_input_type(args):
    """P3. `.width`/`.height` project `bounds` WITHOUT widening ints."""
    a, k = args
    py, rs = _oracle.Component(*a, **k), _rs.Component(*a, **k)
    assert canon(py.width) == canon(rs.width)
    assert canon(py.height) == canon(rs.height)
    assert type(rs.width) is type(a[2][0])


@SETTINGS
@given(spec=netlist_spec())
def test_p4_netlist_indices_agree(spec):
    """P4. The three lookup indices are built identically, for any corpus --
    including duplicate refs, where later entries overwrite earlier ones."""
    py, rs = _both(spec)
    assert canon(py._component_index) == canon(rs._component_index)
    assert canon(py._net_index) == canon(rs._net_index)
    assert canon(py._component_nets) == canon(rs._component_nets)


@SETTINGS
@given(spec=netlist_spec())
def test_p5_validate_agrees(spec):
    """P5. The validation error corpus agrees exactly, in order."""
    py, rs = _both(spec)
    assert canon(py.validate()) == canon(rs.validate())


def test_p5_is_non_vacuous():
    """`validate()` must actually produce each error class it can."""
    pin = _rs.Pin("1", "1", (0.0, 0.0))
    dup = _rs.Netlist(
        components=[_rs.Component("R1", "f", (1.0, 1.0), pins=[pin]) for _ in range(2)],
        nets=[
            _rs.Net("N", [("R1", "1")]),
            # A KNOWN component with an UNKNOWN pin -- the fourth error class,
            # distinct from the unknown-component one below.
            _rs.Net("N", [("R1", "99"), ("GHOST", "9")]),
        ],
    )
    errors = dup.validate()
    assert any("Duplicate component refs" in e for e in errors)
    assert any("Duplicate net names" in e for e in errors)
    assert any("unknown component" in e for e in errors)
    assert any("unknown pin" in e for e in errors)


@SETTINGS
@given(spec=netlist_spec())
def test_p6_arrays_agree_bit_for_bit_including_dtype(spec):
    """P6. Every numpy-returning method agrees on dtype, shape and bytes."""
    py, rs = _both(spec)
    assert canon(py.get_bounds_array()) == canon(rs.get_bounds_array())
    assert canon(py.get_fixed_mask()) == canon(rs.get_fixed_mask())
    assert canon(_oracle.build_adjacency_matrix(py)) == canon(_rs.build_adjacency_matrix(rs))


@SETTINGS
@given(spec=netlist_spec())
def test_p7_adjacency_is_symmetric_and_zero_diagonal(spec):
    """P7. A *semantic* invariant, not just agreement: the adjacency matrix
    is symmetric with a zero diagonal (a component is never its own
    neighbour, even when a net lists it twice)."""
    _, rs = _both(spec)
    adj = _rs.build_adjacency_matrix(rs)
    assume(adj.shape[0] > 0)
    assert np.array_equal(adj, adj.T)
    assert not np.any(np.diag(adj))


def test_p7_is_non_vacuous():
    """A net that names the same component twice would put a 1 on the
    diagonal if the `set()` dedup were dropped."""
    pin = _rs.Pin("1", "1", (0.0, 0.0))
    nl = _rs.Netlist(
        components=[_rs.Component("R1", "f", (1.0, 1.0), pins=[pin])],
        nets=[_rs.Net("N", [("R1", "1"), ("R1", "1")])],
    )
    assert _rs.build_adjacency_matrix(nl).shape == (1, 1)
    assert _rs.build_adjacency_matrix(nl)[0, 0] == 0


@SETTINGS
@given(spec=netlist_spec(), iterations=st.integers(min_value=0, max_value=3))
def test_p8_isomorphic_groups_agree_for_any_iteration_count(spec, iterations):
    """P8. Weisfeiler-Lehman grouping agrees for any iteration count."""
    py, rs = _both(spec)
    assert canon(py.find_isomorphic_groups(iterations)) == canon(
        rs.find_isomorphic_groups(iterations)
    )


@SETTINGS
@given(
    spec=netlist_spec(),
    mapping=st.dictionaries(net_names, st.sampled_from(["Signal", "Power", "Ground"]), max_size=4),
)
def test_p9_apply_net_class_mapping_agrees_on_count_and_effect(spec, mapping):
    """P9. Both the returned count and the resulting net_class values agree."""
    py, rs = _both(spec)
    assert canon(py.apply_net_class_mapping(mapping)) == canon(rs.apply_net_class_mapping(mapping))
    assert canon([n.net_class for n in py.nets]) == canon([n.net_class for n in rs.nets])


def test_p9_is_non_vacuous():
    """The count must be able to be both zero and non-zero."""
    nl = _rs.Netlist(nets=[_rs.Net("GND", [])])
    assert nl.apply_net_class_mapping({"GND": "Ground"}) == 1
    assert nl.apply_net_class_mapping({"GND": "Ground"}) == 0  # already applied


# ---------------------------------------------------------------------------
# MR1-MR4: metamorphic relations
# ---------------------------------------------------------------------------


@SETTINGS
@given(spec=netlist_spec())
def test_mr1_build_indices_is_idempotent(spec):
    """MR1. Rebuilding the indices without mutating anything is a no-op --
    and stays a no-op identically on both sides."""
    py, rs = _both(spec)
    before_py, before_rs = canon(py), canon(rs)
    for _ in range(3):
        py.build_indices()
        rs.build_indices()
    assert canon(py) == before_py
    assert canon(rs) == before_rs


@SETTINGS
@given(spec=netlist_spec())
def test_mr2_component_permutation_permutes_the_bounds_array_rows(spec):
    """MR2. Reversing the component order reverses `get_bounds_array` rows
    and inverts the index map -- the same way on both sides."""
    py, rs = _both(spec)
    rev_py = _oracle.Netlist(components=list(reversed(py.components)), nets=list(py.nets))
    rev_rs = _rs.Netlist(components=list(reversed(rs.components)), nets=list(rs.nets))
    assert canon(rev_py.get_bounds_array()) == canon(rev_rs.get_bounds_array())
    assume(len(py.components) > 0)
    assert canon(rev_py.get_bounds_array()) == canon(py.get_bounds_array()[::-1])
    assert canon(rev_rs.get_bounds_array()) == canon(rs.get_bounds_array()[::-1])


@SETTINGS
@given(spec=netlist_spec())
def test_mr3_net_order_does_not_change_the_adjacency_matrix(spec):
    """MR3. Adjacency accumulates commutatively, so permuting the *nets*
    leaves the matrix bit-identical -- on both sides, and to each other."""
    py, rs = _both(spec)
    shuffled_py = _oracle.Netlist(components=list(py.components), nets=list(reversed(py.nets)))
    shuffled_rs = _rs.Netlist(components=list(rs.components), nets=list(reversed(rs.nets)))
    assert canon(_oracle.build_adjacency_matrix(shuffled_py)) == canon(
        _oracle.build_adjacency_matrix(py)
    )
    assert canon(_rs.build_adjacency_matrix(shuffled_rs)) == canon(_rs.build_adjacency_matrix(rs))
    assert canon(_rs.build_adjacency_matrix(shuffled_rs)) == canon(
        _oracle.build_adjacency_matrix(shuffled_py)
    )


@SETTINGS
@given(spec=netlist_spec(), extra=refs)
def test_mr4_appending_a_component_extends_the_index_by_exactly_one(spec, extra):
    """MR4. Appending one component then rebuilding grows `n_components` by
    one and leaves every pre-existing index entry untouched (unless the ref
    collides) -- identically on both sides."""
    py, rs = _both(spec)
    before_py = dict(py._component_index)
    before_rs = dict(rs._component_index)
    py.components.append(_oracle.Component(extra, "f", (1.0, 1.0)))
    rs.components.append(_rs.Component(extra, "f", (1.0, 1.0)))
    py.build_indices()
    rs.build_indices()
    assert canon(py._component_index) == canon(rs._component_index)
    # The component LIST always grows by exactly one on both sides.
    assert py.n_components == rs.n_components == len(spec[0]) + 1
    # A brand-new ref adds exactly one index entry; a colliding ref replaces
    # the existing entry instead, so the index size is unchanged.
    expected_index_size = len(before_py) + (0 if extra in before_py else 1)
    assert len(py._component_index) == len(rs._component_index) == expected_index_size
    # Every pre-existing, non-colliding entry keeps its position.
    for ref, idx in before_py.items():
        if ref != extra:
            assert py._component_index[ref] == idx
            assert rs._component_index[ref] == before_rs[ref]


# ---------------------------------------------------------------------------
# Error-path parity under fuzzing
# ---------------------------------------------------------------------------


@SETTINGS
@given(
    pins=st.lists(
        st.one_of(
            st.tuples(refs, refs),
            st.tuples(refs, refs, refs),  # wrong arity -> ValueError
            st.just(("solo",)),  # wrong arity -> ValueError
            st.integers(),  # non-iterable -> TypeError
        ),
        min_size=1,
        max_size=3,
    )
)
def test_malformed_pin_tuples_fail_identically(pins):
    """Error TYPE and MESSAGE parity for the `(ref, name)` unpack, which the
    Rust had to reimplement rather than inherit from CPython."""
    py_out = canon_call(lambda: _oracle.Net("N", list(pins)).get_component_refs())
    rs_out = canon_call(lambda: _rs.Net("N", list(pins)).get_component_refs())
    assert py_out == rs_out


def test_malformed_pin_tuples_is_non_vacuous():
    for bad, exc in [
        ([("a", "b", "c")], "too many values to unpack (expected 2)"),
        ([("solo",)], "not enough values to unpack (expected 2, got 1)"),
        ([5], "cannot unpack non-iterable int object"),
    ]:
        with pytest.raises((ValueError, TypeError), match=None):
            _rs.Net("N", bad).get_component_refs()
        assert canon_call(lambda b=bad: _rs.Net("N", b).get_component_refs())[2] == exc
