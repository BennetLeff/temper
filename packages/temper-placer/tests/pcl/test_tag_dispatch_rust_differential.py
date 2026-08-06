"""R1a differential: Rust tag-dispatch pyclasses vs the pinned Python oracle.

Wave 4, Phase 2 -- the contracts-as-pyo3-pyclasses pivot. The Rust
implementation in ``temper-design-bundle``'s ``pcl_tags.rs`` must reproduce
the pre-migration ``temper_placer/pcl/tag_dispatch.py`` bit-identically. The
pre-migration implementation is pinned verbatim as
``_tag_dispatch_py_oracle.py`` (commit ``5a17025b1``).

Because the oracle re-declares its OWN ``ComponentTag``, ``TagRef``, ... the
tests build the *same* expression twice -- once from the live (Rust) node
types and once from the oracle's dataclasses -- via ``_build``, driving
identical shapes through both sides.

Comparison is by type-carrying signature (``_pclsig``); exceptions compare by
qualname + exact message, with only the module component normalised away
(the oracle's ``TagValidationError`` is necessarily a different class object).
"""

from __future__ import annotations

import copy
import dataclasses
import pickle

import pytest
import tests.pcl._tag_dispatch_py_oracle as _oracle
from tests.pcl._pclsig import assert_same, call_signature, signature

from temper_placer.core.netlist import Component, Netlist
from temper_placer.pcl import tag_dispatch as live

# ---------------------------------------------------------------------------
# Parallel expression construction.
# ---------------------------------------------------------------------------

# A spec is a nested tuple: ("tag", NAME) | ("ref", STR) |
# ("and"|"or", spec, spec) | ("not", spec)


def _build(spec, ns):
    """Materialise a spec using namespace ``ns`` (``live`` or ``_oracle``)."""
    kind = spec[0]
    if kind == "tag":
        return ns.TagRef(getattr(ns.ComponentTag, spec[1]))
    if kind == "rawtag":
        # A TagRef holding something that is NOT a ComponentTag -- the
        # duck-typed input the frozen dataclass never rejected.
        return ns.TagRef(spec[1])
    if kind == "ref":
        return ns.ComponentRef(spec[1])
    if kind == "and":
        return ns.TagAnd(_build(spec[1], ns), _build(spec[2], ns))
    if kind == "or":
        return ns.TagOr(_build(spec[1], ns), _build(spec[2], ns))
    if kind == "not":
        return ns.TagNot(_build(spec[1], ns))
    raise AssertionError(f"bad spec {spec!r}")


def _norm(sig):
    """Erase only the module component of a raised exception's class name."""
    if sig[0] == "raise":
        return ("raise", sig[2], sig[3])
    return sig


def _comp(ref: str, tags=()):
    return Component(ref=ref, footprint="0603", bounds=(5.0, 5.0), tags=frozenset(tags))


def _netlist(pairs):
    return Netlist(components=[_comp(r, t) for r, t in pairs], nets=[])


ALL_TAG_NAMES = [
    "ALL",
    "POWER",
    "SIGNAL",
    "MECHANICAL",
    "HV",
    "LV",
    "GATE_DRIVE",
    "SENSOR",
    "MCU",
    "CONNECTOR",
    "MOUNTING",
    "THERMAL",
    "DECOUPLING",
    "FERRITE",
]


# ---------------------------------------------------------------------------
# The lattice: enum surface, closure, and the <= relation.
# ---------------------------------------------------------------------------


def test_component_tag_member_names_and_values_are_unchanged():
    assert [m.name for m in live.ComponentTag] == [m.name for m in _oracle.ComponentTag]
    assert [m.value for m in live.ComponentTag] == [m.value for m in _oracle.ComponentTag]
    assert [m.name for m in live.ComponentTag] == ALL_TAG_NAMES


def test_component_tag_is_still_a_python_enum_with_value_construction():
    """`ComponentTag(value)` and class iteration are used by _tag_parser.py."""
    assert live.ComponentTag("power") is live.ComponentTag.POWER
    with pytest.raises(ValueError):
        live.ComponentTag("not-a-tag")
    assert len(list(live.ComponentTag)) == 14


def test_hierarchy_table_matches_the_rust_lattice_edge_for_edge():
    """The declarative table in Python and TAG_PARENTS in Rust cannot drift.

    Proven indirectly but exactly: recomputing the closure from the Python
    table must reproduce the Rust-built ``_TAG_CLOSURE`` entry for entry.
    """
    recomputed = _oracle._compute_transitive_closure(
        {
            _oracle.ComponentTag(k.value): frozenset(_oracle.ComponentTag(p.value) for p in v)
            for k, v in live._TAG_HIERARCHY_UP.items()
        }
    )
    for tag in live.ComponentTag:
        got = {t.value for t in live._TAG_CLOSURE[tag]}
        want = {t.value for t in recomputed[_oracle.ComponentTag(tag.value)]}
        assert got == want, f"closure mismatch for {tag}"


def test_tag_closure_matches_oracle_exactly():
    oracle_closure = _oracle._TAG_CLOSURE
    assert len(live._TAG_CLOSURE) == len(oracle_closure) == 14
    for tag in live.ComponentTag:
        got = {t.value for t in live._TAG_CLOSURE[tag]}
        want = {t.value for t in oracle_closure[_oracle.ComponentTag(tag.value)]}
        assert_same(got, want, context=f"closure[{tag}]")


def test_tag_closure_dict_iteration_order_matches_list_ComponentTag():
    """The reference built it from `idx_map.items()`, i.e. declaration order."""
    assert [t.name for t in live._TAG_CLOSURE] == ALL_TAG_NAMES


def test_closure_values_are_frozensets_not_sets():
    for value in live._TAG_CLOSURE.values():
        assert type(value) is frozenset


@pytest.mark.parametrize("a", ALL_TAG_NAMES)
@pytest.mark.parametrize("b", ALL_TAG_NAMES)
def test_tag_ordering_matches_oracle_for_every_pair(a, b):
    got = getattr(live.ComponentTag, a) <= getattr(live.ComponentTag, b)
    want = getattr(_oracle.ComponentTag, a) <= getattr(_oracle.ComponentTag, b)
    assert_same(got, want, context=f"{a} <= {b}")


@pytest.mark.parametrize("other", ["power", 1, None, object(), 1.0], ids=repr)
def test_tag_ordering_against_a_non_tag_raises_the_same_typeerror(other):
    # `ComponentTag.HV <= other`, NOT the "un-Yoda'd" `other >= ...`: the two
    # dispatch differently. `HV <= other` calls `ComponentTag.__le__` first --
    # the migrated method -- which must return NotImplemented so Python then
    # tries the reflected `other.__ge__` and finally raises. `other >= HV`
    # reverses that order and exercises the wrong slot. (ruff SIM300 rewrote
    # this once; the tests still passed and stopped testing the migration.)
    got = _norm(call_signature(lambda: live.ComponentTag.HV <= other))  # noqa: SIM300
    want = _norm(call_signature(lambda: _oracle.ComponentTag.HV <= other))  # noqa: SIM300
    assert got == want
    assert got[0] == "raise" and got[1] == "TypeError"


def test_tag_ordering_against_the_other_namespaces_tag_also_raises():
    """Cross-namespace comparison is a TypeError on both sides, identically."""
    got = _norm(call_signature(lambda: live.ComponentTag.HV <= _oracle.ComponentTag.POWER))
    want = _norm(call_signature(lambda: _oracle.ComponentTag.HV <= live.ComponentTag.POWER))
    assert got[0] == want[0] == "raise"
    assert got[1] == want[1] == "TypeError"


# ---------------------------------------------------------------------------
# Frozen-dataclass fidelity of the five pyclass contract types.
# ---------------------------------------------------------------------------

NODE_SPECS = [
    ("tag", "POWER"),
    ("tag", "ALL"),
    ("ref", "Q1"),
    ("ref", ""),
    ("not", ("tag", "HV")),
    ("and", ("tag", "POWER"), ("ref", "Q1")),
    ("or", ("tag", "SIGNAL"), ("not", ("tag", "MCU"))),
    ("and", ("or", ("tag", "HV"), ("tag", "LV")), ("not", ("ref", "R9"))),
]


@pytest.mark.parametrize("spec", NODE_SPECS, ids=repr)
def test_repr_is_byte_identical_to_the_frozen_dataclass_repr(spec):
    got = repr(_build(spec, live))
    want = repr(_build(spec, _oracle))
    # The oracle's enum repr names its own class; both are "ComponentTag".
    assert got == want, f"{spec!r}\n  rust  = {got}\n  oracle= {want}"


@pytest.mark.parametrize("spec", NODE_SPECS, ids=repr)
def test_equality_is_reflexive_and_structural(spec):
    a, b = _build(spec, live), _build(spec, live)
    assert a == b
    # NOT `a == b` again: `__ne__` is a separately implemented slot on the
    # pyclass, so exercising `!=` is the point. ruff's SIM202 rewrite would
    # delete the only coverage `__ne__` has.
    assert not (a != b)  # noqa: SIM202
    oa, ob = _build(spec, _oracle), _build(spec, _oracle)
    assert (a == b) == (oa == ob)


@pytest.mark.parametrize("spec", NODE_SPECS, ids=repr)
def test_hash_agrees_with_equality(spec):
    a, b = _build(spec, live), _build(spec, live)
    assert hash(a) == hash(b)
    assert hash(_build(spec, _oracle)) == hash(_build(spec, _oracle))
    # usable as a dict key / set member, as the frozen dataclass was
    assert len({a, b}) == 1


def test_equality_across_different_node_types_is_false_not_an_error():
    pairs = [
        (("tag", "POWER"), ("ref", "power")),
        (("and", ("tag", "HV"), ("ref", "Q1")), ("or", ("tag", "HV"), ("ref", "Q1"))),
        (("not", ("tag", "HV")), ("tag", "HV")),
    ]
    for left, right in pairs:
        got = _build(left, live) == _build(right, live)
        want = _build(left, _oracle) == _build(right, _oracle)
        assert got is False and want is False


def test_equality_against_unrelated_objects_is_false():
    node = _build(("tag", "POWER"), live)
    for other in ("power", 1, None, object(), [1]):
        assert (node == other) is False
        assert (node != other) is True


@pytest.mark.parametrize("spec", NODE_SPECS, ids=repr)
def test_frozen_assignment_raises_frozeninstanceerror_with_the_same_message(spec):
    node = _build(spec, live)
    oracle_node = _build(spec, _oracle)
    field_names = [f.name for f in dataclasses.fields(oracle_node)]
    for name in field_names + ["not_a_field"]:
        got = _norm(call_signature(setattr, node, name, 1))
        want = _norm(call_signature(setattr, oracle_node, name, 1))
        assert got == want, f"setattr {name}"
    for name in field_names:
        got = _norm(call_signature(delattr, node, name))
        want = _norm(call_signature(delattr, oracle_node, name))
        assert got == want, f"delattr {name}"


@pytest.mark.parametrize("spec", NODE_SPECS, ids=repr)
def test_deepcopy_round_trips(spec):
    """`ConstraintCollection.copy()` deep-copies constraints holding these."""
    node = _build(spec, live)
    clone = copy.deepcopy(node)
    assert clone == node
    assert clone is not node
    assert repr(clone) == repr(node)


@pytest.mark.parametrize("spec", NODE_SPECS, ids=repr)
def test_pickle_round_trips(spec):
    node = _build(spec, live)
    clone = pickle.loads(pickle.dumps(node))
    assert clone == node
    assert repr(clone) == repr(node)


@pytest.mark.parametrize("spec", NODE_SPECS, ids=repr)
def test_match_args_matches_the_dataclass_field_order(spec):
    node = _build(spec, live)
    oracle_node = _build(spec, _oracle)
    assert type(node).__match_args__ == type(oracle_node).__match_args__


def test_keyword_construction_still_works():
    assert live.TagRef(tag=live.ComponentTag.POWER) == live.TagRef(live.ComponentTag.POWER)
    assert live.ComponentRef(ref="Q1") == live.ComponentRef("Q1")
    left, right = live.TagRef(live.ComponentTag.HV), live.ComponentRef("Q1")
    assert live.TagAnd(left=left, right=right) == live.TagAnd(left, right)
    assert live.TagNot(expr=left) == live.TagNot(left)


def test_field_accessors_return_what_was_stored():
    tag = live.ComponentTag.POWER
    assert live.TagRef(tag).tag is tag
    assert live.ComponentRef("Q1").ref == "Q1"
    inner = live.TagRef(tag)
    assert live.TagNot(inner).expr == inner
    node = live.TagAnd(inner, live.ComponentRef("Q1"))
    assert node.left == inner
    assert node.right == live.ComponentRef("Q1")


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------

TAG_SETS = [
    (),
    ("power",),
    ("POWER",),
    ("Power",),
    ("hv",),
    ("hv", "decoupling"),
    ("signal", "mcu"),
    ("mechanical",),
    ("connector", "mounting"),
    ("all",),
    ("bogus",),
    ("bogus", "hv"),
    ("gate_drive",),
    ("GATE_DRIVE",),
    ("ferrite", "thermal", "sensor"),
    ("power", "signal", "mechanical"),
]

RESOLVE_SPECS = NODE_SPECS + [
    ("tag", "MECHANICAL"),
    ("not", ("not", ("tag", "POWER"))),
    ("and", ("tag", "ALL"), ("not", ("tag", "ALL"))),
    ("or", ("ref", "Q1"), ("ref", "Q2")),
    ("and", ("tag", "POWER"), ("not", ("tag", "HV"))),
    ("not", ("or", ("tag", "HV"), ("tag", "LV"))),
]


@pytest.mark.parametrize("tags", TAG_SETS, ids=repr)
@pytest.mark.parametrize("spec", RESOLVE_SPECS, ids=repr)
def test_resolve_matches_oracle(spec, tags):
    comp = _comp("Q1", tags)
    got = live.resolve(_build(spec, live), comp)
    want = _oracle.resolve(_build(spec, _oracle), comp)
    assert_same(got, want, context=f"resolve({spec!r}, tags={tags!r})")


@pytest.mark.parametrize("tags", TAG_SETS, ids=repr)
def test_resolve_component_ref_matches_on_refdes_not_tags(tags):
    for ref in ("Q1", "Q2", "", "power"):
        comp = _comp(ref, tags)
        got = live.resolve(live.ComponentRef("Q1"), comp)
        want = _oracle.resolve(_oracle.ComponentRef("Q1"), comp)
        assert_same(got, want, context=f"ref={ref!r}")


def test_resolve_with_a_non_componenttag_tagref_raises_the_same_typeerror():
    """`ct <= expr.tag` returns NotImplemented, so Python raises TypeError.

    Only reachable when the component carries a recognised tag: the
    uppercase membership test runs first and short-circuits otherwise.
    """
    comp = _comp("Q1", ("hv",))
    got = _norm(call_signature(live.resolve, _build(("rawtag", "power"), live), comp))
    want = _norm(call_signature(_oracle.resolve, _build(("rawtag", "power"), _oracle), comp))
    assert got == want
    assert got[0] == "raise" and got[1] == "AttributeError"


def test_resolve_with_a_duck_typed_tag_object_matches():
    """Anything with `.value` walks the same path; only `<=` can complain."""

    class DuckTag:
        value = "power"

    comp_matching = _comp("Q1", ("POWER",))  # uppercase test hits first
    got = live.resolve(_build(("rawtag", DuckTag()), live), comp_matching)
    want = _oracle.resolve(_build(("rawtag", DuckTag()), _oracle), comp_matching)
    assert_same(got, want)
    assert got is True

    comp_hierarchical = _comp("Q1", ("hv",))  # forces the `<=` branch
    got = _norm(
        call_signature(live.resolve, _build(("rawtag", DuckTag()), live), comp_hierarchical)
    )
    want = _norm(
        call_signature(_oracle.resolve, _build(("rawtag", DuckTag()), _oracle), comp_hierarchical)
    )
    assert got == want


def test_resolve_of_an_unknown_node_type_answers_false_rather_than_raising():
    """The reference's trailing `return False`, preserved."""
    comp = _comp("Q1", ("hv",))
    for foreign in ("a string", 42, None, object()):
        got = live.resolve(foreign, comp)
        want = _oracle.resolve(foreign, comp)
        assert_same(got, want, context=repr(foreign))
        assert got is False


# ---------------------------------------------------------------------------
# components() / _tag_to_component_refs()
# ---------------------------------------------------------------------------

NETLISTS = [
    [],
    [("Q1", ("hv",))],
    [("Q1", ("hv",)), ("Q2", ("lv",)), ("C1", ("decoupling",))],
    [("U1", ("mcu", "signal")), ("J1", ("connector",)), ("H1", ("mounting",))],
    [("R1", ()), ("R2", ("bogus",)), ("R3", ("POWER",))],
    [(f"C{i}", ("power", "decoupling")) for i in range(8)],
]


@pytest.mark.parametrize("pairs", NETLISTS, ids=lambda p: f"n{len(p)}")
@pytest.mark.parametrize("spec", RESOLVE_SPECS, ids=repr)
def test_components_matches_oracle_including_order(spec, pairs):
    nl = _netlist(pairs)
    got = [c.ref for c in live.components(_build(spec, live), nl)]
    want = [c.ref for c in _oracle.components(_build(spec, _oracle), nl)]
    assert_same(got, want, context=f"components({spec!r})")


@pytest.mark.parametrize("pairs", NETLISTS, ids=lambda p: f"n{len(p)}")
@pytest.mark.parametrize("spec", RESOLVE_SPECS, ids=repr)
def test_tag_to_component_refs_matches_oracle(spec, pairs):
    nl = _netlist(pairs)
    got = live._tag_to_component_refs(_build(spec, live), nl)
    want = _oracle._tag_to_component_refs(_build(spec, _oracle), nl)
    assert_same(got, want, context=f"refs({spec!r})")


def test_components_returns_the_very_same_component_objects():
    """Not copies -- callers compare by identity downstream."""
    nl = _netlist([("Q1", ("hv",)), ("Q2", ("lv",))])
    got = live.components(live.TagRef(live.ComponentTag.POWER), nl)
    assert [id(c) for c in got] == [id(c) for c in nl.components]


# ---------------------------------------------------------------------------
# _check_overconstrained()
# ---------------------------------------------------------------------------


class _FakeAdj:
    constraint_type = "adjacent"

    def __init__(self, a, b, max_distance_mm, id="adj"):
        self.a, self.b, self.max_distance_mm, self.id = a, b, max_distance_mm, id


class _FakeSep:
    constraint_type = "separated"

    def __init__(self, a, b, min_distance_mm, id="sep"):
        self.a, self.b, self.min_distance_mm, self.id = a, b, min_distance_mm, id


class _FakeOther:
    constraint_type = "aligned"

    def __init__(self, components):
        self.components, self.id = components, "aln"


def _expanded(objs, with_meta=True):
    if with_meta:
        return [(o, None, str(o.constraint_type), o.id) for o in objs]
    return [(o, None) for o in objs]


OVERCONSTRAINED_CASES = [
    [],
    [_FakeAdj("Q1", "Q2", 10.0)],
    [_FakeSep("Q1", "Q2", 10.0)],
    # satisfiable: sep <= adj
    [_FakeAdj("Q1", "Q2", 10.0), _FakeSep("Q1", "Q2", 5.0)],
    [_FakeAdj("Q1", "Q2", 10.0), _FakeSep("Q1", "Q2", 10.0)],
    # contradictory
    [_FakeAdj("Q1", "Q2", 5.0), _FakeSep("Q1", "Q2", 20.0)],
    # order of a/b normalised by sorted()
    [_FakeAdj("Q2", "Q1", 5.0), _FakeSep("Q1", "Q2", 20.0)],
    # different pairs -> no intersection
    [_FakeAdj("Q1", "Q2", 5.0), _FakeSep("Q3", "Q4", 20.0)],
    # non-pair constraints are skipped
    [_FakeOther(["A", "B"]), _FakeAdj("Q1", "Q2", 5.0), _FakeSep("Q1", "Q2", 20.0)],
    # multiple entries on one key: itertools.product, adjacency outer
    [
        _FakeAdj("Q1", "Q2", 5.0, id="a1"),
        _FakeAdj("Q1", "Q2", 50.0, id="a2"),
        _FakeSep("Q1", "Q2", 20.0, id="s1"),
    ],
    # float formatting: .1f rounding, including a half-way case
    [_FakeAdj("Q1", "Q2", 0.25, id="a"), _FakeSep("Q1", "Q2", 0.35, id="s")],
    [_FakeAdj("Q1", "Q2", 1e-9, id="a"), _FakeSep("Q1", "Q2", 1e9, id="s")],
    [_FakeAdj("Q1", "Q2", 0.0, id="a"), _FakeSep("Q1", "Q2", 1e-300, id="s")],
    # NaN: `s_dist > a_dist` is False for NaN on both sides
    [_FakeAdj("Q1", "Q2", float("nan")), _FakeSep("Q1", "Q2", 20.0)],
    [_FakeAdj("Q1", "Q2", 5.0), _FakeSep("Q1", "Q2", float("nan"))],
    [_FakeAdj("Q1", "Q2", float("-inf")), _FakeSep("Q1", "Q2", float("inf"))],
    # refdes ordering by code point
    [_FakeAdj("Z", "a", 5.0), _FakeSep("a", "Z", 20.0)],
    [_FakeAdj("é", "e", 5.0), _FakeSep("e", "é", 20.0)],
]


@pytest.mark.parametrize("objs", OVERCONSTRAINED_CASES, ids=lambda o: f"n{len(o)}")
@pytest.mark.parametrize("with_meta", [True, False])
def test_check_overconstrained_matches_oracle(objs, with_meta):
    expanded = _expanded(objs, with_meta)
    got = _norm(call_signature(live._check_overconstrained, expanded))
    want = _norm(call_signature(_oracle._check_overconstrained, expanded))
    assert got == want


def test_check_overconstrained_message_is_byte_identical():
    expanded = _expanded([_FakeAdj("Q1", "Q2", 5.25, id="a"), _FakeSep("Q1", "Q2", 20.55, id="s")])
    got = call_signature(live._check_overconstrained, expanded)
    want = call_signature(_oracle._check_overconstrained, expanded)
    assert got[3] == want[3]
    assert "≤" in got[3] and "≥" in got[3]


def test_check_overconstrained_raises_the_live_tagvalidationerror():
    expanded = _expanded([_FakeAdj("Q1", "Q2", 5.0), _FakeSep("Q1", "Q2", 20.0)])
    with pytest.raises(live.TagValidationError):
        live._check_overconstrained(expanded)


def test_a_constraint_carrying_both_bounds_counts_only_as_adjacency():
    """The reference uses if/elif, so max_distance_mm wins."""

    class Both:
        constraint_type = "weird"
        a, b, id = "Q1", "Q2", "w"
        max_distance_mm = 5.0
        min_distance_mm = 99.0

    expanded = _expanded([Both(), _FakeSep("Q1", "Q2", 3.0)])
    got = _norm(call_signature(live._check_overconstrained, expanded))
    want = _norm(call_signature(_oracle._check_overconstrained, expanded))
    assert got == want


# ---------------------------------------------------------------------------
# Mutation-closing tests.
#
# Each test below exists because a specific mutant in
# `packages/temper-design-bundle/mutation_corpus_pcl.py` SURVIVED the gate
# suite on its first run. They are the discriminating cases that kill it --
# not a weakening of any claim. See VERIFICATION.md for the corpus table.
# ---------------------------------------------------------------------------


def test_M15_uppercase_membership_is_not_redundant_with_the_hierarchy_walk():
    """Kills M15 (`t == tag_upper`, i.e. dropping the .upper() normalisation).

    The uppercase membership test and the hierarchy walk agree on every
    ASCII tag, which is why the mutant survived the first corpus run. They
    diverge exactly where Unicode case mapping is not a bijection: the
    Turkish dotless 'ı' uppercases to 'I', so 'sıgnal'.upper() == 'SIGNAL'
    while 'sıgnal'.lower() != 'signal'. The reference matches such a tag via
    the uppercase test; a port without it answers False.
    """
    assert "sıgnal".upper() == "signal".upper()
    assert "sıgnal".lower() != "signal"

    comp = _comp("Q1", ("sıgnal",))
    expr_live = live.TagRef(live.ComponentTag.SIGNAL)
    expr_oracle = _oracle.TagRef(_oracle.ComponentTag.SIGNAL)
    got = live.resolve(expr_live, comp)
    want = _oracle.resolve(expr_oracle, comp)
    assert_same(got, want, context="dotless-i tag")
    assert got is True, "the uppercase membership test must carry this match"


def test_M15_duck_typed_tag_value_outside_the_enum_only_matches_via_uppercase():
    """Second discriminator for M15, without relying on Unicode casing.

    A TagRef holding a non-ComponentTag object with `.value == 'custom'`
    can only ever match through the uppercase membership test -- 'custom' is
    not an enum value, so ComponentTag('custom') raises and the hierarchy
    walk skips it.
    """

    class DuckTag:
        value = "custom"

    comp = _comp("Q1", ("CUSTOM",))
    got = live.resolve(live.TagRef(DuckTag()), comp)
    want = _oracle.resolve(_oracle.TagRef(DuckTag()), comp)
    assert_same(got, want)
    assert got is True


def test_M23_product_nesting_determines_which_contradiction_is_reported():
    """Kills M23 (swapping the itertools.product loop nesting).

    With one adjacency and one separation entry per key, both nestings find
    the same first offending pair -- which is why the mutant survived. Two
    of each, chosen so the adjacency-outer scan reaches (a1, s2) before the
    separation-outer scan would reach (s1, a2), separates them:

      adjacency = [a1: <=25, a2: <=5]   separation = [s1: >=20, s2: >=30]
      adj outer: (a1,s1) 20>25 no -> (a1,s2) 30>25 YES  -> reports a1/s2
      sep outer: (s1,a1) 20>25 no -> (s1,a2) 20>5  YES  -> reports a2/s1
    """
    objs = [
        _FakeAdj("Q1", "Q2", 25.0, id="a1"),
        _FakeAdj("Q1", "Q2", 5.0, id="a2"),
        _FakeSep("Q1", "Q2", 20.0, id="s1"),
        _FakeSep("Q1", "Q2", 30.0, id="s2"),
    ]
    expanded = _expanded(objs)
    got = _norm(call_signature(live._check_overconstrained, expanded))
    want = _norm(call_signature(_oracle._check_overconstrained, expanded))
    assert got == want
    assert got[0] == "raise"
    # Pin WHICH pair the reference reports, so the nesting cannot be flipped.
    assert "[adjacent:a1]" in got[2], got[2]
    assert "[separated:s2]" in got[2], got[2]


def test_M21_the_set_intersection_is_not_sorted():
    """Kills M21 (sorting `set(adjacency) & set(separation)` before iterating).

    This is the mutation the Wave-4 brief singles out as an *undetectable*
    behaviour change, and it survived the first corpus run: with one or two
    contradictory keys, sorted order and CPython's set order coincide, so
    every message matched.

    Twelve contradictory keys do not coincide. `_check_overconstrained`
    raises on the FIRST offending pair it reaches, so the reported message
    names whichever key CPython's set happens to yield first -- and a sorted
    port names 'N00'/'N01' instead. The assertion is against the oracle
    rather than against a literal, because the true answer is
    PYTHONHASHSEED-dependent: the requirement is that Rust reports whatever
    CPython would report *in this process*, not that it be deterministic.
    """
    names = [f"N{i:02d}" for i in range(24)]
    keys = list(zip(names[::2], names[1::2]))
    assert len(keys) == 12
    # Guard the test's own premise: if set order ever equalled sorted order
    # for this key set, the test would pass vacuously.
    assert list(set(keys)) != sorted(keys), (
        "set iteration order coincides with sorted order -- this test cannot "
        "discriminate on this interpreter/seed"
    )

    objs = []
    for i, (a, b) in enumerate(keys):
        objs.append(_FakeAdj(a, b, 1.0, id=f"a{i}"))
        objs.append(_FakeSep(a, b, 9.0, id=f"s{i}"))
    expanded = _expanded(objs)

    got = _norm(call_signature(live._check_overconstrained, expanded))
    want = _norm(call_signature(_oracle._check_overconstrained, expanded))
    assert got == want, (
        "Rust reported a different contradiction than CPython's set order "
        f"would have:\n  rust  = {got!r}\n  oracle= {want!r}"
    )
    assert got[0] == "raise"


@pytest.mark.parametrize("spec", NODE_SPECS, ids=repr)
def test_M26_hash_distinguishes_distinct_nodes_exactly_as_the_dataclass_did(spec):
    """Kills M26 (a constant __hash__).

    A constant hash is still *consistent* with __eq__, so the equal-implies-
    equal-hash assertions all passed. What it destroys is the distinctness
    the frozen dataclass provided. Literal hash values are process-dependent
    (they derive from id() of the enum members), so what is asserted is the
    equality RELATION over a corpus: for every pair of nodes, Rust's hashes
    must collide exactly when the oracle's do.
    """
    others = [s for s in NODE_SPECS if s != spec]
    node, oracle_node = _build(spec, live), _build(spec, _oracle)
    for other in others:
        live_collides = hash(node) == hash(_build(other, live))
        oracle_collides = hash(oracle_node) == hash(_build(other, _oracle))
        assert live_collides == oracle_collides, (
            f"hash collision behaviour differs for {spec!r} vs {other!r}"
        )


def test_M26_nodes_are_usable_as_distinct_dict_keys():
    """The practical consequence a constant hash would silently degrade."""
    nodes = [_build(s, live) for s in NODE_SPECS]
    oracle_nodes = [_build(s, _oracle) for s in NODE_SPECS]
    assert len(set(nodes)) == len(set(oracle_nodes)) == len(NODE_SPECS)
    assert len({hash(n) for n in nodes}) == len({hash(n) for n in oracle_nodes})


# ---------------------------------------------------------------------------
# End-to-end through E(), which stayed in Python.
# ---------------------------------------------------------------------------


def test_E_still_expands_through_the_migrated_primitives():
    from temper_placer.pcl.constraints import ConstraintTier
    from temper_placer.pcl.tagged_constraints import TaggedAdjacentConstraint

    nl = _netlist([("C1", ("decoupling",)), ("U1", ("mcu",)), ("C2", ("decoupling",))])
    tc = TaggedAdjacentConstraint(
        tag_expr_a=live.TagRef(live.ComponentTag.DECOUPLING),
        tag_expr_b=live.TagRef(live.ComponentTag.MCU),
        max_distance_mm=5.0,
        tier=ConstraintTier.STRONG,
        because="decoupling caps near the MCU",
    )
    assert len(live.E(tc, nl)) == 2


def test_signature_of_a_full_expansion_is_stable():
    nl = _netlist([("C1", ("decoupling",)), ("U1", ("mcu",))])
    expr = live.TagOr(live.TagRef(live.ComponentTag.POWER), live.TagRef(live.ComponentTag.SIGNAL))
    oracle_expr = _oracle.TagOr(
        _oracle.TagRef(_oracle.ComponentTag.POWER),
        _oracle.TagRef(_oracle.ComponentTag.SIGNAL),
    )
    assert signature(live._tag_to_component_refs(expr, nl)) == signature(
        _oracle._tag_to_component_refs(oracle_expr, nl)
    )
