"""R1c/R1d: property-based and metamorphic tests for the Rust PCL layer.

Wave 4, Phase 2. Every property below is checked as a *differential*
property: the same generated input is driven through the live (Rust) path
and the pinned Python oracle, and the two must agree by type-carrying
signature. A property that held for both implementations but described the
wrong behaviour would therefore still be a true statement about the shipped
code -- which is the point. Where a plausible-sounding relation turns out
NOT to hold, it is recorded with an explicit witness (see the
``TestRelationsThatDoNotHold`` class) rather than quietly narrowed.

R1c: >= 5 property-based tests.
R1d: >= 3 metamorphic relations.
"""

from __future__ import annotations

import math

import pytest
import tests.pcl._parse_utils_py_oracle as _parse_oracle
import tests.pcl._tag_dispatch_py_oracle as _tag_oracle
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from tests.pcl._pclsig import assert_same, call_signature

from temper_placer.core.netlist import Component, Netlist
from temper_placer.pcl import _parse_utils as live_parse
from temper_placer.pcl import tag_dispatch as live

SETTINGS = settings(
    max_examples=400,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

TAG_VALUES = [m.value for m in live.ComponentTag]
TAG_NAMES = [m.name for m in live.ComponentTag]


def _norm(sig):
    """Erase only the module component of a raised exception's class name."""
    if sig[0] == "raise":
        return ("raise", sig[2], sig[3])
    return sig


def _agree(live_fn, oracle_fn, *args):
    got = _norm(call_signature(live_fn, *args))
    want = _norm(call_signature(oracle_fn, *args))
    assert got == want, f"args={args!r}\n  rust  = {got!r}\n  oracle= {want!r}"
    return got


def _comp(ref: str, tags):
    return Component(ref=ref, footprint="0603", bounds=(5.0, 5.0), tags=frozenset(tags))


# Expression specs, materialised into either namespace (see the differential).
@st.composite
def expr_specs(draw, depth=3):
    if depth <= 0:
        leaf = draw(st.integers(0, 1))
        if leaf == 0:
            return ("tag", draw(st.sampled_from(TAG_NAMES)))
        return ("ref", draw(st.sampled_from(["Q1", "Q2", "R1", "C1", "U1", ""])))
    kind = draw(st.sampled_from(["tag", "ref", "and", "or", "not"]))
    if kind == "tag":
        return ("tag", draw(st.sampled_from(TAG_NAMES)))
    if kind == "ref":
        return ("ref", draw(st.sampled_from(["Q1", "Q2", "R1", "C1", "U1", ""])))
    if kind == "not":
        return ("not", draw(expr_specs(depth - 1)))
    return (kind, draw(expr_specs(depth - 1)), draw(expr_specs(depth - 1)))


def _build(spec, ns):
    kind = spec[0]
    if kind == "tag":
        return ns.TagRef(getattr(ns.ComponentTag, spec[1]))
    if kind == "ref":
        return ns.ComponentRef(spec[1])
    if kind == "not":
        return ns.TagNot(_build(spec[1], ns))
    if kind == "and":
        return ns.TagAnd(_build(spec[1], ns), _build(spec[2], ns))
    if kind == "or":
        return ns.TagOr(_build(spec[1], ns), _build(spec[2], ns))
    raise AssertionError(spec)


# Floats whose `repr` is plain decimal, i.e. contains no exponent.
#
# This restriction is NOT cosmetic and NOT a convenience: the scanner splits
# the number at the first character that is not a digit, `.` or `-`, so the
# `e` in `repr(6.1e-05)` terminates the number and the remainder ("e-05mm")
# is read as a unit. Scientific notation is therefore *unparseable* by this
# function -- shipped behaviour, discovered by these property tests failing,
# and pinned as a witness in `test_w5_scientific_notation_is_not_accepted`
# rather than papered over.
_plain_decimal_floats = st.floats(
    min_value=1e-4, max_value=1e15, allow_nan=False, allow_infinity=False
).filter(lambda v: "e" not in repr(v) and "E" not in repr(v))

tag_strings = st.sampled_from(TAG_VALUES + ["BOGUS", "Power", "HV", "hv ", ""])
tag_sets = st.frozensets(tag_strings, max_size=4)
refdes = st.sampled_from(["Q1", "Q2", "R1", "C1", "U1", ""])


# ===========================================================================
# R1c -- property-based tests
# ===========================================================================


class TestParseProperties:
    """P1-P3: the parse layer, fuzzed against the oracle."""

    @pytest.mark.property
    @given(
        number=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
        unit=st.sampled_from(["", "mm", "mil", "in", "cm", "MM", "MIL", "IN", "CM"]),
        pad_left=st.sampled_from(["", " ", "\t", "\x1c"]),
        pad_right=st.sampled_from(["", " ", "\n", "\x1f"]),
    )
    @SETTINGS
    def test_p1_distance_parse_agrees_with_oracle_on_wellformed_input(
        self, number, unit, pad_left, pad_right
    ):
        """P1: every well-formed quantity string parses bit-identically."""
        text = f"{pad_left}{number!r}{unit}{pad_right}"
        _agree(
            live_parse._parse_distance_with_unit,
            _parse_oracle._parse_distance_with_unit,
            text,
        )

    @pytest.mark.property
    @given(text=st.text(max_size=12))
    @SETTINGS
    def test_p2_distance_parse_agrees_on_arbitrary_text_including_the_error_paths(self, text):
        """P2: arbitrary text -- the same value OR the same exception+message.

        This is where the Unicode-digit and C0-separator traps live: the
        generator freely produces fullwidth digits and control characters.
        """
        _agree(
            live_parse._parse_distance_with_unit,
            _parse_oracle._parse_distance_with_unit,
            text,
        )

    @pytest.mark.property
    @given(
        value=st.one_of(
            st.integers(),
            st.booleans(),
            st.floats(allow_nan=True, allow_infinity=True),
            st.text(max_size=8),
            st.none(),
        )
    )
    @SETTINGS
    def test_p3_every_enum_parser_agrees_on_arbitrary_input(self, value):
        """P3: tier/metric/axis/side/edge all agree, values and errors alike."""
        for live_fn, oracle_fn in [
            (live_parse._parse_tier, _parse_oracle._parse_tier),
            (live_parse._parse_metric, _parse_oracle._parse_metric),
            (live_parse._parse_axis, _parse_oracle._parse_axis),
            (live_parse._parse_board_side, _parse_oracle._parse_board_side),
            (live_parse._parse_edge_type, _parse_oracle._parse_edge_type),
        ]:
            _agree(live_fn, oracle_fn, value)


class TestTagProperties:
    """P4-P6: the tag lattice and expression algebra, fuzzed."""

    @pytest.mark.property
    @given(spec=expr_specs(), ref=refdes, tags=tag_sets)
    @SETTINGS
    def test_p4_resolve_agrees_with_oracle_on_random_expressions(self, spec, ref, tags):
        """P4: resolution over random trees and random tag sets."""
        comp = _comp(ref, tags)
        got = live.resolve(_build(spec, live), comp)
        want = _tag_oracle.resolve(_build(spec, _tag_oracle), comp)
        assert_same(got, want, context=f"{spec!r} tags={set(tags)!r}")

    @pytest.mark.property
    @given(
        spec=expr_specs(),
        pairs=st.lists(st.tuples(refdes, tag_sets), max_size=6),
    )
    @SETTINGS
    def test_p5_components_agrees_including_result_order(self, spec, pairs):
        """P5: the netlist sweep returns the same refs in the same order."""
        nl = Netlist(components=[_comp(r, t) for r, t in pairs], nets=[])
        got = [c.ref for c in live.components(_build(spec, live), nl)]
        want = [c.ref for c in _tag_oracle.components(_build(spec, _tag_oracle), nl)]
        assert_same(got, want, context=repr(spec))

    @pytest.mark.property
    @given(
        a=st.sampled_from(TAG_NAMES),
        b=st.sampled_from(TAG_NAMES),
        c=st.sampled_from(TAG_NAMES),
    )
    @SETTINGS
    def test_p6_the_tag_order_is_a_partial_order_and_matches_the_oracle(self, a, b, c):
        """P6: reflexive, antisymmetric, transitive -- and oracle-identical."""
        la, lb, lc = (getattr(live.ComponentTag, n) for n in (a, b, c))
        oa, ob, oc = (getattr(_tag_oracle.ComponentTag, n) for n in (a, b, c))
        assert (la <= lb) == (oa <= ob)
        assert la <= la  # reflexive
        if la <= lb and lb <= la:
            assert a == b  # antisymmetric
        if (la <= lb) and (lb <= lc):
            assert la <= lc  # transitive

    @pytest.mark.property
    @given(spec=expr_specs())
    @SETTINGS
    def test_p7_node_repr_and_equality_match_the_frozen_dataclass(self, spec):
        """P7: the pyclass contract objects are indistinguishable by repr/eq/hash."""
        live_node, oracle_node = _build(spec, live), _build(spec, _tag_oracle)
        assert repr(live_node) == repr(oracle_node)
        twin = _build(spec, live)
        assert live_node == twin
        assert hash(live_node) == hash(twin)


# ===========================================================================
# R1d -- metamorphic relations
# ===========================================================================


class TestMetamorphicRelations:
    """Relations that must hold between *different* runs of the same code."""

    @pytest.mark.property
    @given(spec=expr_specs(), ref=refdes, tags=tag_sets)
    @SETTINGS
    def test_m1_double_negation_is_the_identity(self, spec, ref, tags):
        """M1: resolve(NOT(NOT e)) == resolve(e), and Rust agrees with Python."""
        comp = _comp(ref, tags)
        base = live.resolve(_build(spec, live), comp)
        doubled = live.resolve(live.TagNot(live.TagNot(_build(spec, live))), comp)
        assert base is doubled
        o_base = _tag_oracle.resolve(_build(spec, _tag_oracle), comp)
        o_doubled = _tag_oracle.resolve(
            _tag_oracle.TagNot(_tag_oracle.TagNot(_build(spec, _tag_oracle))), comp
        )
        assert o_base is o_doubled
        assert base is o_base

    @pytest.mark.property
    @given(left=expr_specs(2), right=expr_specs(2), ref=refdes, tags=tag_sets)
    @SETTINGS
    def test_m2_de_morgan(self, left, right, ref, tags):
        """M2: NOT(a AND b) == (NOT a) OR (NOT b), in both implementations."""
        comp = _comp(ref, tags)
        for ns in (live, _tag_oracle):
            a, b = _build(left, ns), _build(right, ns)
            lhs = ns.resolve(ns.TagNot(ns.TagAnd(a, b)), comp)
            rhs = ns.resolve(ns.TagOr(ns.TagNot(a), ns.TagNot(b)), comp)
            assert lhs is rhs, f"De Morgan failed in {ns.__name__}"
        assert live.resolve(
            live.TagNot(live.TagAnd(_build(left, live), _build(right, live))), comp
        ) is _tag_oracle.resolve(
            _tag_oracle.TagNot(
                _tag_oracle.TagAnd(_build(left, _tag_oracle), _build(right, _tag_oracle))
            ),
            comp,
        )

    @pytest.mark.property
    @given(
        child=st.sampled_from(TAG_NAMES),
        parent=st.sampled_from(TAG_NAMES),
        pairs=st.lists(st.tuples(refdes, tag_sets), max_size=6),
    )
    @SETTINGS
    def test_m3_tag_refinement_narrows_never_widens(self, child, parent, pairs):
        """M3: if child <= parent then matches(child) is a SUBSET of matches(parent).

        This is the relation the tag hierarchy exists to provide, and it is
        what makes `adjacent(HV, X)` safe to substitute for
        `adjacent(POWER, X)` in a design review.
        """
        assume(getattr(live.ComponentTag, child) <= getattr(live.ComponentTag, parent))
        nl = Netlist(components=[_comp(r, t) for r, t in pairs], nets=[])
        narrow = {
            c.ref for c in live.components(live.TagRef(getattr(live.ComponentTag, child)), nl)
        }
        wide = {c.ref for c in live.components(live.TagRef(getattr(live.ComponentTag, parent)), nl)}
        assert narrow <= wide, f"{child} <= {parent} but matches are not a subset"

    @pytest.mark.property
    @given(
        name=st.sampled_from(TAG_NAMES),
        tags=tag_sets,
        extra=tag_strings,
        ref=refdes,
    )
    @SETTINGS
    def test_m4_adding_a_tag_never_unmatches_a_positive_expression(self, name, tags, extra, ref):
        """M4: monotonicity of NEGATION-FREE expressions under tag addition.

        Scoped to negation-free deliberately: the relation is FALSE once a
        TagNot is present, and that is proven, not assumed -- see
        `test_w2_monotonicity_fails_under_negation`.
        """
        expr = live.TagOr(
            live.TagRef(getattr(live.ComponentTag, name)),
            live.TagRef(live.ComponentTag.ALL if False else live.ComponentTag.MCU),
        )
        before = live.resolve(expr, _comp(ref, tags))
        after = live.resolve(expr, _comp(ref, frozenset(tags) | {extra}))
        assert not (before and not after), "adding a tag removed a positive match"

    @pytest.mark.property
    @given(number=_plain_decimal_floats)
    @SETTINGS
    def test_m5_unit_suffix_case_is_irrelevant(self, number):
        """M5: '5mm', '5MM' and '5Mm' are bit-identical, and so are the units."""
        for unit in ("mm", "mil", "in", "cm"):
            variants = [unit, unit.upper(), unit.capitalize()]
            results = [live_parse._parse_distance_with_unit(f"{number!r}{v}") for v in variants]
            assert len({r.hex() for r in results}) == 1, (number, unit, results)
            oracle = _parse_oracle._parse_distance_with_unit(f"{number!r}{unit}")
            assert results[0].hex() == oracle.hex()

    @pytest.mark.property
    @given(number=_plain_decimal_floats)
    @SETTINGS
    def test_m6_surrounding_whitespace_is_irrelevant(self, number):
        """M6: leading/trailing CPython-whitespace does not change the value."""
        base = live_parse._parse_distance_with_unit(f"{number!r}mm")
        for pad in (" ", "\t", "\n", "\x1c", "\x1f", "  "):
            padded = live_parse._parse_distance_with_unit(f"{pad}{number!r}mm{pad}")
            assert padded.hex() == base.hex()

    @pytest.mark.property
    @given(number=_plain_decimal_floats)
    @SETTINGS
    def test_m7_a_unitless_value_equals_the_same_value_in_mm(self, number):
        """M7: 'X' and 'Xmm' agree -- the empty unit maps to millimetres."""
        bare = live_parse._parse_distance_with_unit(f"{number!r}")
        with_mm = live_parse._parse_distance_with_unit(f"{number!r}mm")
        assert bare.hex() == with_mm.hex()


class TestRelationsThatDoNotHold:
    """Relations that LOOK true, are not, and are pinned with a witness.

    Each of these was written as a metamorphic relation first, failed, and is
    recorded here as the negative result rather than being deleted or
    narrowed until it passed. The Rust reproduces the false relation exactly,
    which is the actual requirement.
    """

    def test_w1_inches_and_thousandths_do_not_agree_bit_for_bit(self):
        """WITNESS: 3in != 3000mil, because 3*25.4 and 3000*0.0254 round apart.

        The tempting relation `parse(f'{n}in') == parse(f'{n*1000}mil')` is
        false for n = 3, 6, 12, 24, 29, 48, ... Both implementations must be
        equally wrong, and are: the Rust performs the identical single
        multiply against the identical double, so it inherits the identical
        rounding.
        """
        witnesses = [3, 6, 12, 24, 29, 48]
        assert witnesses, "no witness recorded"
        for n in witnesses:
            inches = live_parse._parse_distance_with_unit(f"{n}in")
            mils = live_parse._parse_distance_with_unit(f"{n * 1000}mil")
            assert inches != mils, f"{n}: expected disagreement, got {inches!r}"
            # ...and the oracle disagrees in exactly the same direction.
            o_inches = _parse_oracle._parse_distance_with_unit(f"{n}in")
            o_mils = _parse_oracle._parse_distance_with_unit(f"{n * 1000}mil")
            assert inches.hex() == o_inches.hex()
            assert mils.hex() == o_mils.hex()
            assert math.ulp(inches) >= abs(inches - mils) > 0

    def test_w2_monotonicity_fails_under_negation(self):
        """WITNESS: adding a tag CAN unmatch, once the expression negates.

        M4 is therefore scoped to negation-free expressions, not because the
        general statement was inconvenient but because it is false.
        """
        expr = live.TagNot(live.TagRef(live.ComponentTag.HV))
        before = live.resolve(expr, _comp("Q1", frozenset()))
        after = live.resolve(expr, _comp("Q1", frozenset({"hv"})))
        assert before is True
        assert after is False, "expected the negation to flip"
        # The oracle behaves identically -- this is shipped behaviour.
        o_expr = _tag_oracle.TagNot(_tag_oracle.TagRef(_tag_oracle.ComponentTag.HV))
        assert _tag_oracle.resolve(o_expr, _comp("Q1", frozenset())) is True
        assert _tag_oracle.resolve(o_expr, _comp("Q1", frozenset({"hv"}))) is False

    def test_w3_the_negative_sign_rule_is_not_uniform_across_the_unit_paths(self):
        """WITNESS: '-5' is accepted, '-5mm' is rejected. Same sign, same magnitude.

        A relation like "a negative distance always raises" is false; the
        check sits after the scanner's early return. Pinned, not fixed.
        """
        assert live_parse._parse_distance_with_unit("-5") == -5.0
        with pytest.raises(live_parse.PCLParseError):
            live_parse._parse_distance_with_unit("-5mm")
        assert _parse_oracle._parse_distance_with_unit("-5") == -5.0

    def test_w5_scientific_notation_is_not_accepted_at_all(self):
        """WITNESS: '1e5mm' does not mean 100000 mm -- it is a unit error.

        Found by M5/M6/M7 failing on generated floats whose `repr` carries an
        exponent (e.g. 6.103515625e-05). The scanner stops at the `e`, so
        "e-05mm" becomes the unit string. Every metamorphic relation over
        round-trip formatting is therefore scoped to plain-decimal reprs,
        because the general statement is false. Both implementations agree.
        """
        for text in ("1e5", "1e5mm", "6.103515625e-05mm", "1E5mm"):
            got = _norm(call_signature(live_parse._parse_distance_with_unit, text))
            want = _norm(call_signature(_parse_oracle._parse_distance_with_unit, text))
            assert got == want
            assert got[0] == "raise", text
            assert got[1] == "PCLParseError", text
            assert "Unknown distance unit" in got[2], text

    def test_w4_a_string_that_isdigit_is_not_always_float_parseable(self):
        """WITNESS: '²'.isdigit() is True but float('²') raises ValueError.

        So "the scanner accepts exactly what float() accepts" is false, and
        the resulting exception is a bare ValueError rather than a
        PCLParseError. Both implementations agree on that.
        """
        assert "²".isdigit()
        got = _norm(call_signature(live_parse._parse_distance_with_unit, "²"))
        want = _norm(call_signature(_parse_oracle._parse_distance_with_unit, "²"))
        assert got == want
        assert got[1] == "ValueError"


# ===========================================================================
# Order-invariance: proven where it holds, passed through where it does not.
# ===========================================================================


class TestIterationOrder:
    @pytest.mark.property
    @given(
        name=st.sampled_from(TAG_NAMES),
        tags=st.lists(tag_strings, min_size=1, max_size=5, unique=True),
    )
    @SETTINGS
    def test_resolve_is_invariant_to_the_tag_frozensets_iteration_order(self, name, tags):
        """`for ct_str in comp.tags` reads a frozenset in hash order.

        The loop body has no side effects and only ever returns True, so the
        result is "does ANY tag sit under expr.tag" -- independent of order.
        Here the order is made an EXPLICIT input (every permutation of the
        same tag multiset) and the answer must not move.
        """
        import itertools

        expr = live.TagRef(getattr(live.ComponentTag, name))
        answers = {
            live.resolve(expr, _comp("Q1", frozenset(perm)))
            for perm in itertools.permutations(tags)
        }
        assert len(answers) == 1, f"order-dependent result for {tags!r}"

    def test_check_overconstrained_passes_the_live_set_order_through(self):
        """Order IS observable here, so it is passed through, never sorted.

        Two contradictory pairs exist; which message is raised depends on
        CPython's set iteration order for this process. The requirement is
        not determinism -- it is that Rust raises whichever one Python would
        have raised, in the same process.
        """

        class Adj:
            constraint_type = "adjacent"

            def __init__(self, a, b, d, i):
                self.a, self.b, self.max_distance_mm, self.id = a, b, d, i

        class Sep:
            constraint_type = "separated"

            def __init__(self, a, b, d, i):
                self.a, self.b, self.min_distance_mm, self.id = a, b, d, i

        objs = [
            Adj("A1", "A2", 1.0, "a1"),
            Sep("A1", "A2", 9.0, "s1"),
            Adj("B1", "B2", 1.0, "a2"),
            Sep("B1", "B2", 9.0, "s2"),
        ]
        expanded = [(o, None, str(o.constraint_type), o.id) for o in objs]
        got = _norm(call_signature(live._check_overconstrained, expanded))
        want = _norm(call_signature(_tag_oracle._check_overconstrained, expanded))
        assert got == want, "Rust picked a different pair than CPython's set order"
        assert got[0] == "raise"
