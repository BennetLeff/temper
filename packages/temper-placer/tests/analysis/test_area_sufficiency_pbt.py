"""Property-based + metamorphic tests for the Rust area-sufficiency kernels.

Wave 4, Phase 4 — the analysis-surface migration (plan
``docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md``
R1c/R1d).  These properties exercise the migrated ``temper_geometry``
pyfunctions (``area_sufficiency_compute``, ``top_courtyards``,
``py_sum``) and the ``temper_placer.analysis._area_sufficiency``
delegation shim; bit-identical parity against the pinned pre-migration
Python is asserted separately by
``test_area_sufficiency_rust_differential.py``.

Properties (all non-vacuously guarded):

- P1. Kernel linkage: ``area_sufficiency_compute(...)[0]`` (the total)
  equals ``py_sum(areas)`` equals CPython's builtin ``sum(areas)``,
  bit-exact via ``float.hex()`` with the concrete leaf type carried
  (``sum([])`` is ``int 0``, not ``float 0.0``).
- P2. Usable-area arithmetic: ``usable == (w - 2m) * (h - 2m)`` bit-exact.
- P3. Error path: ``m >= w/2 or m >= h/2`` raises ``ValueError`` whose
  message is byte-identical to the oracle's own f-string construction.
- P4. Empty-input semantics: empty areas give ``int 0`` total and
  ``0.0`` ratio; empty pairs give ``[]`` from ``top_courtyards``.
- P5. ``py_sum`` special-value parity: NaN / ±inf / -0.0 / subnormals
  reproduce the builtin bit-exactly.
- P6. ``top_courtyards`` order/slice contract: non-increasing areas,
  stable ties, and Python ``list[:n]`` slice semantics for positive,
  oversized, zero and negative ``n``.

Metamorphic relations:

- MR1. Power-of-two scaling: multiplying every area by ``2**k`` scales
  the sum by ``2**k`` bit-exactly (IEEE-exact).
- MR2. Margin monotonicity: ``usable(m1) > usable(m2)`` iff ``m1 < m2``,
  and the raw ratio is monotone non-increasing in the margin.
- MR3. Top-N prefix: for ``0 <= n1 <= n2``, ``top(pairs, n1)`` is a
  prefix of ``top(pairs, n2)``.
- MR4. Zero-padding: appending ``+0.0`` entries to a list of non-zero
  finite areas leaves ``py_sum`` bit-identical (bounded: a running sum
  of non-zero finite operands never lands on ``-0.0``).
"""

from __future__ import annotations

import math

import pytest
import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 80

_FINITE = st.floats(
    allow_nan=False,
    allow_infinity=False,
    min_value=-1e12,
    max_value=1e12,
)

_SPECIAL = st.floats(
    allow_nan=True,
    allow_infinity=True,
    allow_subnormal=True,
    min_value=-1e300,
    max_value=1e300,
)

_AREA_LISTS = st.lists(_FINITE, min_size=0, max_size=40)
_SPECIAL_LISTS = st.lists(_SPECIAL, min_size=0, max_size=40)


def _key(v):
    if isinstance(v, int):
        return ("int", v)
    return ("float", float(v).hex())


def _expected_message(w, h, m):
    used_w = w - 2 * m
    used_h = h - 2 * m
    usable = used_w * used_h
    return (
        f"Usable board area is non-positive ({usable:.1f} mm^2) "
        f"with {m}mm margin on {w}x{h}mm board "
        f"(usable region: {used_w:.1f}x{used_h:.1f} mm)."
    )


# --- P1: kernel linkage ----------------------------------------------------


@given(st.floats(min_value=1.0, max_value=1000.0), st.floats(min_value=1.0, max_value=1000.0), _AREA_LISTS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_kernel_linkage(w, h, areas):
    m = min(w, h) / 4.0
    total, _usable, _ratio, _w, _h, n = _tg.area_sufficiency_compute(w, h, m, areas)
    assert _key(total) == _key(_tg.py_sum(areas)) == _key(sum(areas))
    assert n == len(areas)


# --- P2: usable-area arithmetic --------------------------------------------


@given(st.floats(min_value=1.0, max_value=1000.0), st.floats(min_value=1.0, max_value=1000.0), _AREA_LISTS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_usable_area_arithmetic(w, h, areas):
    m = min(w, h) / 4.0
    _total, usable, _ratio, _w, _h, _n = _tg.area_sufficiency_compute(w, h, m, areas)
    assert _key(usable) == _key((w - 2 * m) * (h - 2 * m))


# --- P3: error path --------------------------------------------------------


@given(st.floats(min_value=1.0, max_value=200.0), st.floats(min_value=1.0, max_value=200.0), _AREA_LISTS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_non_positive_usable_area_message(w, h, areas):
    # Margin >= half of either dimension → non-positive usable region.
    m = max(w, h) / 2.0 + 1.0
    with pytest.raises(ValueError) as exc:
        _tg.area_sufficiency_compute(w, h, m, areas)
    assert str(exc.value) == _expected_message(w, h, m)


# --- P4: empty-input semantics ---------------------------------------------


def test_p4_empty_areas_int_zero_total_and_zero_ratio():
    total, usable, ratio, w, h, n = _tg.area_sufficiency_compute(100.0, 100.0, 5.0, [])
    assert type(total) is int and total == 0
    assert _key(ratio) == _key(0.0)
    assert usable == 90.0 * 90.0
    assert n == 0


def test_p4_empty_pairs_top_courtyards_empty():
    assert _tg.top_courtyards([], 8) == []
    assert _tg.top_courtyards([], 0) == []
    assert _tg.top_courtyards([], -1) == []


# --- P5: special-value sum parity ------------------------------------------


@given(_SPECIAL_LISTS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_py_sum_special_values(areas):
    assert _key(_tg.py_sum(areas)) == _key(sum(areas))


# --- P6: top_courtyards contract -------------------------------------------


@given(
    st.lists(st.tuples(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=1, max_size=8), _FINITE), min_size=0, max_size=30),
    st.integers(min_value=-10, max_value=40),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p6_top_courtyards_contract(pairs, n):
    result = _tg.top_courtyards(pairs, n)
    areas = [a for _r, a in result]
    assert all(areas[i] >= areas[i + 1] for i in range(len(areas) - 1))
    # Python list[:n] slice semantics on the oracle's own sorted() order.
    oracle = sorted(pairs, key=lambda kv: kv[1], reverse=True)[:n]
    assert [(r, _key(a)) for r, a in result] == [(r, _key(a)) for r, a in oracle]


def test_p6_ties_preserve_input_order():
    pairs = [("a", 1.0), ("b", 2.0), ("c", 1.0), ("d", 2.0), ("e", 0.5)]
    result = _tg.top_courtyards(pairs, 10)
    # Ties at 2.0 keep input order (b before d); ties at 1.0 keep a before c.
    assert [r for r, _a in result] == ["b", "d", "a", "c", "e"]


# --- MR1: power-of-two scaling ---------------------------------------------


@given(_AREA_LISTS, st.integers(min_value=-20, max_value=20))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_power_of_two_scaling(areas, k):
    if not areas:
        return
    factor = 2.0**k
    scaled = [a * factor for a in areas]
    assert _key(_tg.py_sum(scaled)) == _key(_tg.py_sum(areas) * factor)


# --- MR2: margin monotonicity ----------------------------------------------


@given(st.floats(min_value=20.0, max_value=200.0), st.floats(min_value=20.0, max_value=200.0), _AREA_LISTS)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr2_margin_monotonicity(w, h, areas):
    m1 = min(w, h) / 6.0
    m2 = min(w, h) / 3.0
    _t1, u1, r1, _w, _h, _n = _tg.area_sufficiency_compute(w, h, m1, areas)
    _t2, u2, r2, _w, _h, _n = _tg.area_sufficiency_compute(w, h, m2, areas)
    assert u1 > u2
    assert r1 <= r2


# --- MR3: top-N prefix ------------------------------------------------------


@given(
    st.lists(st.tuples(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=1, max_size=8), _FINITE), min_size=0, max_size=30),
    st.integers(min_value=0, max_value=25),
    st.integers(min_value=0, max_value=25),
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr3_top_n_prefix(pairs, n1, n2):
    if n1 > n2:
        n1, n2 = n2, n1
    small = _tg.top_courtyards(pairs, n1)
    large = _tg.top_courtyards(pairs, n2)
    assert small == large[:n1] if n1 >= 0 else small == large


# --- MR4: zero padding ------------------------------------------------------


@given(st.lists(st.floats(allow_nan=False, allow_infinity=False, allow_subnormal=True, min_value=-1e6, max_value=1e6).filter(lambda v: v != 0.0), min_size=1, max_size=20))
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr4_appending_zeros_unchanged(areas):
    padded = areas + [0.0, 0.0, 0.0]
    assert _key(_tg.py_sum(padded)) == _key(_tg.py_sum(areas))
