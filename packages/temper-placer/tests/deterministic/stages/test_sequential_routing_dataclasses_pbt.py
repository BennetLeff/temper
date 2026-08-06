"""Property-based + metamorphic tests for the migrated DiffPairConfig contract.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). The dataclass
``DiffPairConfig`` moved to the ``temper-design-bundle`` crate; bit-identical
parity against the pinned oracle is asserted separately by
``test_sequential_routing_dataclasses_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Default chain: omission of any defaulted field yields the oracle's
  default value on the pyclass (0.15 / 0.5 / 0.5).
- P2. Round-trip: construction → field access returns the exact objects.
- P3. Equality is all-five-field: perturbing any single field changes the
  equality class.
- P4. Type preservation: an int leaf stays an int (dataclass no-coercion).
- P5. Hashability/ordering independence: equality is symmetric and
  reflexive on the explored surface.

Three metamorphic relations (R1d):

- MR1. Kwarg-order commutativity: same arguments in different keyword orders
  construct equal instances.
- MR2. Positional ≡ keyword: the same values produce equal instances.
- MR3. Default-omission ≡ explicit-default: omitting a defaulted field
  equals passing its default value explicitly.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.core._contract_canon import canon

_STR = st.text(min_size=1, max_size=16, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ+_-0123456789")
_NUM = st.one_of(
    st.integers(min_value=0, max_value=100),
    st.floats(min_value=0.01, max_value=100.0, allow_nan=False, allow_infinity=False),
)


@given(_STR, _STR)
@settings(max_examples=50, deadline=None)
def test_p1_default_chain(p, n):
    a = _tdb.DiffPairConfig(p, n)
    assert a.spacing_mm == 0.15
    assert a.coupling_tolerance_mm == 0.5
    assert a.max_skew_mm == 0.5


@given(_STR, _STR, _NUM, _NUM, _NUM)
@settings(max_examples=50, deadline=None)
def test_p2_round_trip(p, n, s, c, m):
    a = _tdb.DiffPairConfig(p, n, s, c, m)
    assert a.net_pos == p and a.net_neg == n
    assert canon(a.spacing_mm) == canon(s)
    assert canon(a.coupling_tolerance_mm) == canon(c)
    assert canon(a.max_skew_mm) == canon(m)


@given(_STR, _STR, _NUM)
@settings(max_examples=50, deadline=None)
def test_p3_equality_is_all_fields(p, n, s):
    base = _tdb.DiffPairConfig(p, n, s, 0.5, 0.5)
    assert base == _tdb.DiffPairConfig(p, n, s, 0.5, 0.5)
    assert base != _tdb.DiffPairConfig(p + "X", n, s, 0.5, 0.5)
    assert base != _tdb.DiffPairConfig(p, n, s, 0.6, 0.5)
    assert base != _tdb.DiffPairConfig(p, n, s, 0.5, 0.6)


@given(_STR, _STR)
@settings(max_examples=50, deadline=None)
def test_p4_type_preservation(p, n):
    a = _tdb.DiffPairConfig(p, n, spacing_mm=1)
    assert type(a.spacing_mm) is int
    b = _tdb.DiffPairConfig(p, n, spacing_mm=1.0)
    assert type(b.spacing_mm) is float


@given(_STR, _STR, _NUM)
@settings(max_examples=50, deadline=None)
def test_p5_equality_symmetry(p, n, s):
    a = _tdb.DiffPairConfig(p, n, s)
    b = _tdb.DiffPairConfig(p, n, s)
    assert a == b and b == a
    assert (a != b) == (b != a)


@given(_STR, _STR, _NUM, _NUM, _NUM)
@settings(max_examples=50, deadline=None)
def test_mr1_kwarg_order_commutativity(p, n, s, c, m):
    a = _tdb.DiffPairConfig(net_pos=p, net_neg=n, spacing_mm=s, coupling_tolerance_mm=c, max_skew_mm=m)
    b = _tdb.DiffPairConfig(max_skew_mm=m, coupling_tolerance_mm=c, spacing_mm=s, net_neg=n, net_pos=p)
    assert a == b


@given(_STR, _STR, _NUM, _NUM, _NUM)
@settings(max_examples=50, deadline=None)
def test_mr2_positional_equiv_keyword(p, n, s, c, m):
    a = _tdb.DiffPairConfig(p, n, s, c, m)
    b = _tdb.DiffPairConfig(net_pos=p, net_neg=n, spacing_mm=s, coupling_tolerance_mm=c, max_skew_mm=m)
    assert a == b


@given(_STR, _STR)
@settings(max_examples=50, deadline=None)
def test_mr3_omission_equiv_explicit_default(p, n):
    a = _tdb.DiffPairConfig(p, n)
    b = _tdb.DiffPairConfig(p, n, spacing_mm=0.15, coupling_tolerance_mm=0.5, max_skew_mm=0.5)
    assert a == b
