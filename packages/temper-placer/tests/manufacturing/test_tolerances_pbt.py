"""Property-based tests for the Rust manufacturing tolerance pyclasses
(``temper_design_bundle_python``) — Wave 4 Phase 4 leftovers slice.

The Rust implementation must satisfy the same algebraic invariants the
pre-migration Python implementation satisfies, asserted INDEPENDENTLY of the
oracle (the differential test owns bit-parity; this file owns the closed-form
properties). Every property is fail-capable: each pins a formula, a constant,
a fallback value, or a monotonicity direction that a wrong implementation
would break.

R1c: properties P1-P7 (>= 5).  R1d: MR1-MR4 (>= 3).
"""

from __future__ import annotations

import pytest
import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

COPPER_WEIGHT = _tdb.CopperWeight
LAYER_TYPE = _tdb.LayerType
TOLERANCE_TABLE = _tdb.ToleranceTable
TOLERANCE_ANALYZER = _tdb.ToleranceAnalyzer


def _hex(v: float) -> str:
    return float(v).hex()


# Finite, non-extreme floats so the IEEE arithmetic stays well-behaved.
_finite = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_width = st.floats(min_value=1e-6, max_value=1e3, allow_nan=False, allow_infinity=False)
_etch = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

_CW_MEMBERS = ["HALF_OZ", "ONE_OZ", "TWO_OZ"]
_LT_MEMBERS = ["OUTER", "INNER"]


# ---------------------------------------------------------------------------
# P1: trace formula — tolerance_plus == tolerance_minus == etch, and the
# worst-case bounds are the nominal shifted by exactly the table etch value.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(w=_width, cw_name=st.sampled_from(_CW_MEMBERS))
@settings(max_examples=50, deadline=30000)
def test_p1_trace_formula_bit_exact(w, cw_name):
    """analyze_trace pins the oracle's arithmetic: worst_case_min == w - etch,
    worst_case_max == w + etch, plus == minus == etch (bit-exact hex)."""
    analyzer = TOLERANCE_ANALYZER()
    ft = analyzer.analyze_trace(w, getattr(COPPER_WEIGHT, cw_name))
    etch = TOLERANCE_TABLE().etch_tolerance[getattr(COPPER_WEIGHT, cw_name)]
    # Fails if the Rust kernel reorders the arithmetic or applies an fma.
    assert _hex(ft.tolerance_plus) == _hex(etch)
    assert _hex(ft.tolerance_minus) == _hex(etch)
    assert _hex(ft.worst_case_min) == _hex(w - etch)
    assert _hex(ft.worst_case_max) == _hex(w + etch)
    assert _hex(ft.nominal_value) == _hex(w)
    assert ft.feature_type == "trace_width"


# ---------------------------------------------------------------------------
# P2: clearance formula — tolerance_plus == 0.0, worst_case_max == nominal,
# tolerance_minus == 2*etch + reg with the oracle's parenthesization.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(c=_width, cw_name=st.sampled_from(_CW_MEMBERS), lt_name=st.sampled_from(_LT_MEMBERS))
@settings(max_examples=50, deadline=30000)
def test_p2_clearance_formula_bit_exact(c, cw_name, lt_name):
    """analyze_clearance pins the oracle's arithmetic exactly."""
    analyzer = TOLERANCE_ANALYZER()
    ft = analyzer.analyze_clearance(
        c, getattr(COPPER_WEIGHT, cw_name), getattr(LAYER_TYPE, lt_name)
    )
    table = TOLERANCE_TABLE()
    etch = table.etch_tolerance[getattr(COPPER_WEIGHT, cw_name)]
    reg = table.registration[getattr(LAYER_TYPE, lt_name)]
    assert _hex(ft.tolerance_plus) == _hex(0.0)
    assert _hex(ft.worst_case_max) == _hex(c)
    # (2 * etch) + reg — left-associative, exactly like the oracle.
    assert _hex(ft.tolerance_minus) == _hex(2 * etch + reg)
    assert _hex(ft.worst_case_min) == _hex(c - (2 * etch + reg))
    assert ft.feature_type == "clearance"


# ---------------------------------------------------------------------------
# P3: monotonicity — larger nominal clearance strictly increases both the
# nominal and the worst-case-min bounds (IEEE subtraction is monotonic).
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(c1=_width, c2=_width, cw_name=st.sampled_from(_CW_MEMBERS), lt_name=st.sampled_from(_LT_MEMBERS))
@settings(max_examples=50, deadline=30000)
def test_p3_clearance_monotonic_in_nominal(c1, c2, cw_name, lt_name):
    """c1 > c2 implies ft(c1).worst_case_min > ft(c2).worst_case_min."""
    analyzer = TOLERANCE_ANALYZER()
    kw = {"copper_weight": getattr(COPPER_WEIGHT, cw_name), "layer_type": getattr(LAYER_TYPE, lt_name)}
    ft1 = analyzer.analyze_clearance(c1, **kw)
    ft2 = analyzer.analyze_clearance(c2, **kw)
    if c1 > c2:
        assert _hex(ft1.nominal_value) == _hex(c1)
        assert ft1.worst_case_min > ft2.worst_case_min
    if c1 < c2:
        assert ft1.worst_case_min < ft2.worst_case_min
    if c1 == c2:
        assert _hex(ft1.worst_case_min) == _hex(ft2.worst_case_min)


# ---------------------------------------------------------------------------
# P4: default table constants — the default_factory values are pinned.
# ---------------------------------------------------------------------------


def test_p4_default_table_constants():
    """The default ToleranceTable carries exactly the canonical constants."""
    table = TOLERANCE_TABLE()
    assert set(table.etch_tolerance.keys()) == {
        COPPER_WEIGHT.HALF_OZ,
        COPPER_WEIGHT.ONE_OZ,
        COPPER_WEIGHT.TWO_OZ,
    }
    assert _hex(table.etch_tolerance[COPPER_WEIGHT.HALF_OZ]) == _hex(0.025)
    assert _hex(table.etch_tolerance[COPPER_WEIGHT.ONE_OZ]) == _hex(0.05)
    assert _hex(table.etch_tolerance[COPPER_WEIGHT.TWO_OZ]) == _hex(0.075)
    assert set(table.registration.keys()) == {LAYER_TYPE.OUTER, LAYER_TYPE.INNER}
    assert _hex(table.registration[LAYER_TYPE.OUTER]) == _hex(0.1)
    assert _hex(table.registration[LAYER_TYPE.INNER]) == _hex(0.15)
    assert _hex(table.solder_mask_registration) == _hex(0.075)


# ---------------------------------------------------------------------------
# P5: custom-table fallback — a missing copper weight falls back to 0.05,
# a missing layer type falls back to 0.1, for arbitrary widths/clearances.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(w=_width)
@settings(max_examples=50, deadline=30000)
def test_p5_missing_copper_weight_falls_back(w):
    """Custom table missing TWO_OZ: analyze_trace falls back to 0.05."""
    table = TOLERANCE_TABLE(etch_tolerance={COPPER_WEIGHT.ONE_OZ: 0.01})
    ft = TOLERANCE_ANALYZER(table=table).analyze_trace(w, COPPER_WEIGHT.TWO_OZ)
    assert _hex(ft.tolerance_minus) == _hex(0.05)
    assert _hex(ft.worst_case_min) == _hex(w - 0.05)
    assert _hex(ft.worst_case_max) == _hex(w + 0.05)


@pytest.mark.property
@given(c=_width)
@settings(max_examples=50, deadline=30000)
def test_p5b_missing_layer_type_falls_back(c):
    """Custom table missing INNER: analyze_clearance falls back to 0.1 for reg."""
    table = TOLERANCE_TABLE(registration={LAYER_TYPE.OUTER: 0.05})
    ft = TOLERANCE_ANALYZER(table=table).analyze_clearance(
        c, COPPER_WEIGHT.ONE_OZ, LAYER_TYPE.INNER
    )
    assert _hex(ft.tolerance_minus) == _hex(2 * 0.05 + 0.1)


# ---------------------------------------------------------------------------
# P6: enum value round-trip — constructing a member by its value yields the
# same member; constructing by a foreign value raises ValueError.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(cw_name=st.sampled_from(_CW_MEMBERS), lt_name=st.sampled_from(_LT_MEMBERS))
@settings(max_examples=50, deadline=30000)
def test_p6_enum_value_roundtrip(cw_name, lt_name):
    """Cls(member.value) resolves to the member (eq + hash round-trip).

    NOTE: a pyo3 pyclass enum constructs a fresh instance from ``Cls(value)``
    (documented deviation — Python ``Enum`` returns the cached singleton, so
    ``Cls(value) is member`` is True there and False here). The contract
    surface is name/value/eq/hash/repr — dict-key usage — which the round
    trip asserts.
    """
    cw = getattr(COPPER_WEIGHT, cw_name)
    lt = getattr(LAYER_TYPE, lt_name)
    assert COPPER_WEIGHT(cw.value) == cw
    assert hash(COPPER_WEIGHT(cw.value)) == hash(cw)
    assert COPPER_WEIGHT(cw.value).name == cw_name
    assert LAYER_TYPE(lt.value) == lt
    assert hash(LAYER_TYPE(lt.value)) == hash(lt)
    assert LAYER_TYPE(lt.value).name == lt_name


@pytest.mark.property
@given(bad=st.floats(allow_nan=False, allow_infinity=False).filter(lambda x: x not in (0.5, 1.0, 2.0)))
@settings(max_examples=50, deadline=30000)
def test_p6b_enum_foreign_value_raises(bad):
    """CopperWeight(foreign float) raises ValueError with the Enum text."""
    with pytest.raises(ValueError):
        COPPER_WEIGHT(bad)


# ---------------------------------------------------------------------------
# P7: per-member etch arithmetic identity — the analyzer and the raw table
# lookup agree on the applied etch for every member.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(w=_width, cw_name=st.sampled_from(_CW_MEMBERS))
@settings(max_examples=50, deadline=30000)
def test_p7_analyzer_uses_table_etch(w, cw_name):
    """The etch applied by analyze_trace equals the table's etch for that member."""
    table = TOLERANCE_TABLE()
    cw = getattr(COPPER_WEIGHT, cw_name)
    ft = TOLERANCE_ANALYZER(table=table).analyze_trace(w, cw)
    assert _hex(ft.tolerance_minus) == _hex(table.etch_tolerance[cw])


# ---------------------------------------------------------------------------
# MR1: enum value-construction commutativity — construction by value is the
# same object as the named member, so both paths give identical results.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(w=_width, cw_name=st.sampled_from(_CW_MEMBERS))
@settings(max_examples=50, deadline=30000)
def test_mr1_enum_construction_commutativity(w, cw_name):
    """analyze_trace via CopperWeight(value) == analyze_trace via named member."""
    cw = getattr(COPPER_WEIGHT, cw_name)
    analyzer = TOLERANCE_ANALYZER()
    ft_by_value = analyzer.analyze_trace(w, COPPER_WEIGHT(cw.value))
    ft_by_name = analyzer.analyze_trace(w, cw)
    assert _hex(ft_by_value.worst_case_min) == _hex(ft_by_name.worst_case_min)
    assert _hex(ft_by_value.worst_case_max) == _hex(ft_by_name.worst_case_max)


# ---------------------------------------------------------------------------
# MR2: dict insertion-order permutation invariance — reordering the keys of
# a custom etch table changes nothing (lookup is order-independent).
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(w=_width, e1=_etch, e2=_etch)
@settings(max_examples=50, deadline=30000)
def test_mr2_dict_order_permutation_invariance(w, e1, e2):
    """{ONE_OZ: e1, TWO_OZ: e2} and {TWO_OZ: e2, ONE_OZ: e1} analyze identically."""
    table_a = TOLERANCE_TABLE(etch_tolerance={COPPER_WEIGHT.ONE_OZ: e1, COPPER_WEIGHT.TWO_OZ: e2})
    table_b = TOLERANCE_TABLE(etch_tolerance={COPPER_WEIGHT.TWO_OZ: e2, COPPER_WEIGHT.ONE_OZ: e1})
    fa = TOLERANCE_ANALYZER(table=table_a).analyze_trace(w, COPPER_WEIGHT.ONE_OZ)
    fb = TOLERANCE_ANALYZER(table=table_b).analyze_trace(w, COPPER_WEIGHT.ONE_OZ)
    assert _hex(fa.worst_case_min) == _hex(fb.worst_case_min)
    assert _hex(fa.worst_case_max) == _hex(fb.worst_case_max)


# ---------------------------------------------------------------------------
# MR3: fallback consistency — a table that omits a member behaves identically
# to a table that maps it to exactly the fallback value.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(w=_width, e=_etch)
@settings(max_examples=50, deadline=30000)
def test_mr3_fallback_equals_explicit_default(w, e):
    """Table missing TWO_OZ == table with TWO_OZ mapped to 0.05 exactly."""
    missing = TOLERANCE_TABLE(etch_tolerance={COPPER_WEIGHT.ONE_OZ: e})
    explicit = TOLERANCE_TABLE(etch_tolerance={COPPER_WEIGHT.ONE_OZ: e, COPPER_WEIGHT.TWO_OZ: 0.05})
    fm = TOLERANCE_ANALYZER(table=missing).analyze_trace(w, COPPER_WEIGHT.TWO_OZ)
    fe = TOLERANCE_ANALYZER(table=explicit).analyze_trace(w, COPPER_WEIGHT.TWO_OZ)
    assert _hex(fm.worst_case_min) == _hex(fe.worst_case_min)
    assert _hex(fm.worst_case_max) == _hex(fe.worst_case_max)


# ---------------------------------------------------------------------------
# MR4: monotonicity in etch — a table with a larger etch value for a member
# yields a smaller worst_case_min (and larger worst_case_max) for trace width.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(w=_width, e1=_etch, e2=_etch)
@settings(max_examples=50, deadline=30000)
def test_mr4_etch_monotonicity(w, e1, e2):
    """e2 >= e1 => worst_case_min(e2) <= worst_case_min(e1), and vice versa for max."""
    cw = COPPER_WEIGHT.ONE_OZ
    ft1 = TOLERANCE_ANALYZER(table=TOLERANCE_TABLE(etch_tolerance={cw: e1})).analyze_trace(w, cw)
    ft2 = TOLERANCE_ANALYZER(table=TOLERANCE_TABLE(etch_tolerance={cw: e2})).analyze_trace(w, cw)
    if e2 > e1:
        assert ft2.worst_case_min <= ft1.worst_case_min
        assert ft2.worst_case_max >= ft1.worst_case_max
    if e2 == e1:
        assert _hex(ft2.worst_case_min) == _hex(ft1.worst_case_min)
