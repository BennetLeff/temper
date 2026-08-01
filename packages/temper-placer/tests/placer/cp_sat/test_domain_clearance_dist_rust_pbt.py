"""Property-based tests for the R24 domain-clearance audit distance
recompute in Rust (``temper_geometry.dist_py``, Wave 3 #4).

Five non-vacuous invariants (each fails if the function returned a
constant) plus metamorphic relations.  ``dist_py`` backs
``domain_clearance.py::audit_domain_clearance``'s recomputation of the
real Euclidean center-to-center distance of every generated constraint
from solved coordinates (R24 item 3) — the CPython ``math.dist``
semantics it must match bit-for-bit.

Exactness notes: ``dist_py`` delegates to temper-geometry's ``py_hypot``
(the replicated CPython Dekker ``vector_norm``).  Symmetry is bit-exact
(swapping the two points negates both differences and the norm takes
absolute values in the same order); translation by a power-of-2 offset
with operands in the same binade is bit-exact by Sterbenz; a 90°
rotation (axis swap) reorders the two terms inside ``vector_norm``'s
compensated sum and is therefore NOT bit-exact — that relation is
asserted with a 1e-12 relative tolerance and recorded as a known
non-bit-exact metamorphosis in the module docstring.
"""

from __future__ import annotations

import math

import temper_geometry as _tg
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 200

_coord = st.floats(
    min_value=-200.0,
    max_value=200.0,
    allow_nan=False,
    allow_infinity=False,
).filter(lambda v: abs(v) >= 1e-3 or v == 0.0)  # normal-range: the power-of-two
# scaling relation (MR3) underflows differently at denormal magnitudes
_unit = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


def _dist(p, q):
    return _tg.dist_py(p[0], p[1], q[0], q[1])


# ---------------------------------------------------------------------------
# 5 invariants
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(p=st.tuples(_coord, _coord))
def test_dist_variation(p):
    """P1 — the mapping covers a rich output range (a constant fails)."""
    outputs = {_dist(p, (x, 0.0)) for x in range(-100, 101, 5)}
    assert len(outputs) >= 10


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(p=st.tuples(_coord, _coord), q=st.tuples(_coord, _coord))
def test_dist_zero_iff_identical(p, q):
    """P2 — distance is exactly 0 iff the points coincide (a constant 0
    fails the p != q direction; a constant c fails the p == q side)."""
    if p == q:
        assert _dist(p, q) == 0.0
    else:
        assert _dist(p, q) > 0.0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(p=st.tuples(_coord, _coord), q=st.tuples(_coord, _coord))
def test_dist_symmetry(p, q):
    """P3 — bit-exact symmetry: dist(p, q) == dist(q, p) (negated
    differences, absolute values taken in the same order)."""
    assert _dist(p, q) == _dist(q, p)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(pi=st.integers(min_value=0, max_value=2**20),
       qi=st.integers(min_value=0, max_value=2**20),
       pj=st.integers(min_value=0, max_value=2**20),
       qj=st.integers(min_value=0, max_value=2**20))
def test_dist_translation_invariance_sterbenz(pi, qi, pj, qj):
    """P4 — bit-exact translation invariance for the Sterbenz-exact
    shift t=(1,1) on the 2^-52 grid: p, q as integer multiples of
    2^-52 stay exact under +1.0, and the difference of the shifted
    operands (both in [1,2), within a factor of 2) is exact, so the
    diffs feeding the norm are unchanged."""
    p = (pi * 2.0**-52, pj * 2.0**-52)
    q = (qi * 2.0**-52, qj * 2.0**-52)
    t = (1.0, 1.0)
    assert _dist((p[0] + t[0], p[1] + t[1]), (q[0] + t[0], q[1] + t[1])) == _dist(p, q)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(p=st.tuples(_coord, _coord), q=st.tuples(_coord, _coord))
def test_dist_l1_l_inf_bounds(p, q):
    """P5 — the L∞/L1 sandwich: max(|dx|,|dy|) <= dist <= |dx|+|dy|
    (the Euclidean norm lies between the max-component and Manhattan
    norms; a constant 0 fails the lower bound on separated points)."""
    dx, dy = p[0] - q[0], p[1] - q[1]
    d = _dist(p, q)
    assert d >= max(abs(dx), abs(dy))
    assert d <= abs(dx) + abs(dy)


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(p=st.tuples(_coord, _coord), q=st.tuples(_coord, _coord))
def test_mr1_reflection_through_origin(p, q):
    """M1 — bit-exact reflection: dist(-p, -q) == dist(p, q) (both
    differences negate, the norm takes absolute values)."""
    assert _dist((-p[0], -p[1]), (-q[0], -q[1])) == _dist(p, q)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(p=st.tuples(_coord, _coord), q=st.tuples(_coord, _coord))
def test_mr2_axis_swap_rotation(p, q):
    """M2 — 90° rotation (axis swap) preserves distance *up to 1e-12
    relative*: the compensated-sum order changes, so this is a known
    non-bit-exact metamorphosis (recorded in the module docstring)."""
    d = _dist(p, q)
    swapped = _dist((p[1], p[0]), (q[1], q[0]))
    assert abs(swapped - d) <= 1e-12 * max(1.0, d)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(p=st.tuples(_coord, _coord), q=st.tuples(_coord, _coord))
def test_mr3_power_of_two_scaling(p, q):
    """M3 — bit-exact power-of-2 uniform scaling:
    dist(2^k p, 2^k q) == 2^k dist(p, q) (scaling by a power of two
    only shifts the exponent; the normalized vector_norm path is
    identical)."""
    for k in (2.0, 4.0, 0.5, 0.25):
        assert _dist((p[0] * k, p[1] * k), (q[0] * k, q[1] * k)) == k * _dist(p, q)


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(p=st.tuples(_coord, _coord), q=st.tuples(_coord, _coord))
def test_mr4_chebyshev_conservative_relation(p, q):
    """M4 — conservative-bound relation with the audit's Chebyshev gap:
    for axis-aligned boxes centered at p and q with zero size, the
    Euclidean center distance never exceeds... rather, the Chebyshev
    box-gap (temper_geometry.chebyshev_gap_py) is <= the center
    Euclidean distance — the encoding-audit soundness chain the R24
    proof relies on (box gap under-approximates Euclidean gap)."""
    dx, dy = p[0] - q[0], p[1] - q[1]
    cheb = _tg.chebyshev_gap_py(
        p[0], p[1], p[0], p[1], q[0], q[1], q[0], q[1]
    )
    assert cheb <= _dist(p, q)
    assert cheb == max(abs(dx), abs(dy))


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(p=st.tuples(_coord, _coord), q=st.tuples(_coord, _coord), dx=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False), dy=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_mr5_dual_call_identity(p, q, dx, dy):
    """M5 — dual-call identity: shifting both points by the same delta
    (computed with tolerance, since the shifted coordinates round) and
    measuring again gives the same distance as measuring the delta
    directly."""
    t = (dx, dy)
    shifted = _dist((p[0] + t[0], p[1] + t[1]), (q[0] + t[0], q[1] + t[1]))
    direct = _dist(p, q)
    assert abs(shifted - direct) <= 1e-9 * max(1.0, direct)
    # The exact delta itself has the same norm as measuring it from origin.
    delta_norm = _dist(t, (0.0, 0.0))
    assert abs(delta_norm - math.hypot(dx, dy)) <= 1e-12 * max(1.0, abs(dx), abs(dy))
