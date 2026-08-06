"""Differential test: cli/timing.py compute, Rust vs oracle.

Wave 4, **Phase 5** (cli/adapters/temper-workflow slice). The numeric
compute of ``temper_placer/cli/timing.py`` moves to the
``temper-orchestration`` crate (``temper_orchestration.compare_stage``,
``temper_orchestration.p95``); the Python module keeps its full click
surface (flags, help, exit codes, output text) and delegates the compute
across the boundary.

The pre-migration module is pinned VERBATIM as the oracle
(``tests/cli/_timing_py_oracle.py``). The compute it pins is **inline** in
the click command bodies — the pre-migration module never extracted it — so
the reference arms below are mechanical extractions of those inline
expressions, each annotated with the oracle line it came from. Every
assertion drives IDENTICAL inputs through both sides.

Extracted compute:

1. ``_ref_compare_stage`` — from ``timing_check`` (oracle lines 266-273,
   the ``delta_ms`` … ``passed`` block). Pure numeric: subtraction,
   guarded division, Python ``max`` (asymmetric on NaN — see below),
   multiply, ``<=``.
2. ``_ref_p95`` — from the ``wall_ms_p95`` expression used in
   ``timing_baseline`` (oracle line ~198), ``timing_regenerate`` (twice,
   ~oracle lines 464/512) and ``timing_tighten`` (oracle line ~690):
   ``round(sorted(values)[int(len(values) * 0.95)], 3)``.

Bit-exactness conventions (R1a):
- floats compare via ``float.hex()`` (canon) — never a tolerance;
- every leaf carries its concrete ``type`` (``int`` vs ``float`` cannot hide);
- error parity via ``canon_call``: empty ``p95`` must raise ``IndexError``
  exactly as the bare expression does (the ``timing_tighten`` call site
  guards empty with ``else 0.0`` in Python, which is NOT part of this
  function's contract).

Numerical traps pinned here:
- ``round(x, 3)`` is CPython's decimal round-half-to-even (David Gay dtoa
  mode 1) — NOT ``(x * 1000).round() / 1000``, which double-rounds and
  diverges (measured 494/2M mismatches on uniform samples plus every exact
  ``.xxx5`` tick). The Rust side therefore calls Python's ``round`` for the
  final step (bit-identical by identity) and does the sort + index
  selection itself.
- CPython ``sorted()`` on floats is a stable sort under ``<``, where
  ``-0.0 < 0.0`` is False and every NaN comparison is False — the Rust side
  sorts with a comparator that maps non-comparable pairs to ``Equal``
  (stable), reproducing CPython for finite values, ``-0.0``/``+0.0`` ties
  and NaN alike.
- ``max(baseline_ms, floor_ms)`` is CPython's ``max``, which is *asymmetric
  on NaN* (``max(nan, 1.0)`` → ``nan``; ``max(1.0, nan)`` → ``1.0``). The
  Rust side reproduces ``if b > a { b } else { a }`` rather than
  ``f64::max`` (which would always return the non-NaN operand).
- ``baseline_ms > 0`` guards the division, so a zero/``-0.0`` baseline
  yields ``delta_pct == 0.0`` and the division never executes (there is no
  float-division-by-zero path to diverge on). NaN baseline also lands in the
  ``else`` arm.

The differential domain is non-empty lists of ``float`` wall-clock values
(the timing gate's ``individual_ms`` are floats). All-int and mixed
int/float lists are ALSO pinned (``test_p95_all_int_inputs_preserve_int_type``):
``round(int, 3)`` returns an int, and the shim writes the result into the
YAML manifest where ``100`` and ``100.0`` render differently, so the Rust
side must preserve the selected element's type exactly as the oracle does.
Ints with ``|x| >= 2**53`` sort by their f64 approximation (the sort key
was always f64); values of that magnitude are not claimed.
"""

from __future__ import annotations

import random

import temper_orchestration as _to

import tests.cli._timing_py_oracle as _oracle  # noqa: F401  (provenance anchor)
from tests.core._contract_canon import canon, canon_call

# Rust symbols under test — must exist or this file fails to collect (RED).
RS_COMPARE_STAGE = _to.compare_stage
RS_P95 = _to.p95


# ---------------------------------------------------------------------------
# Reference arms — mechanically extracted from the oracle's inline compute.
# ---------------------------------------------------------------------------

def _ref_compare_stage(
    baseline_ms: float, current_ms: float, margin: float, floor_ms: float
) -> tuple[float, float, float, float, bool]:
    """Extracted from the oracle's ``timing_check`` (delta..passed block)."""
    delta_ms = current_ms - baseline_ms
    delta_pct = (delta_ms / baseline_ms) * 100.0 if baseline_ms > 0 else 0.0
    effective_baseline = max(baseline_ms, floor_ms)
    threshold_ms = effective_baseline * (1.0 + margin)
    passed = current_ms <= threshold_ms
    return (delta_ms, delta_pct, effective_baseline, threshold_ms, passed)


def _ref_p95(values: list[float | int]) -> float | int:
    """Extracted from the oracle's ``wall_ms_p95`` expression. The result
    carries the selected element's type: round(int, 3) returns int."""
    return round(sorted(values)[int(len(values) * 0.95)], 3)


def _assert_stage_equal(baseline_ms, current_ms, margin, floor_ms) -> None:
    ref = canon(_ref_compare_stage(baseline_ms, current_ms, margin, floor_ms))
    got = canon(RS_COMPARE_STAGE(baseline_ms, current_ms, margin, floor_ms))
    assert ref == got, (
        f"compare_stage mismatch: baseline={baseline_ms!r} current={current_ms!r} "
        f"margin={margin!r} floor={floor_ms!r}\n  ref={ref}\n  got={got}"
    )


def _assert_p95_equal(values: list[float | int]) -> None:
    ref = canon_call(_ref_p95, values)
    got = canon_call(RS_P95, values)
    assert ref == got, f"p95 mismatch for {values!r}\n  ref={ref}\n  got={got}"


# ---------------------------------------------------------------------------
# compare_stage
# ---------------------------------------------------------------------------

def test_compare_stage_fixed_cases():
    cases = [
        # (baseline, current, margin, floor)
        (100.0, 110.0, 0.20, 10.0),   # within margin -> pass
        (100.0, 125.0, 0.20, 10.0),   # exactly at threshold -> pass (<=)
        (100.0, 125.1, 0.20, 10.0),   # just over -> fail
        (100.0, 90.0, 0.20, 10.0),    # improvement
        (10.0, 20.0, 0.20, 10.0),     # floor == baseline
        (1.0, 5.0, 0.20, 10.0),       # baseline below floor -> floor applies
        (5.0, 10.0, 0.20, 10.0),      # current exactly at floored threshold
        (0.0, 5.0, 0.20, 10.0),       # zero baseline -> delta_pct 0.0
        (-0.0, 5.0, 0.20, 10.0),      # -0.0 baseline -> delta_pct 0.0
        (100.0, 100.0, 0.0, 0.0),     # zero margin/floor: threshold == baseline
        (100.0, 100.0000001, 0.0, 0.0),
        (1e9, 1.5e9, 0.20, 10.0),     # large values
        (1e-9, 2e-9, 0.20, 1e-12),    # tiny values
        (100.0, 110.0, -0.1, 10.0),   # negative margin -> threshold below baseline
        (100.0, 90.0, -0.1, 10.0),
    ]
    for baseline, current, margin, floor in cases:
        _assert_stage_equal(baseline, current, margin, floor)


def test_compare_stage_nan_semantics():
    """CPython max() is asymmetric on NaN; the Rust port must reproduce it."""
    nan = float("nan")
    _assert_stage_equal(nan, 110.0, 0.20, 10.0)   # max(nan, 10) -> nan
    _assert_stage_equal(100.0, nan, 0.20, 10.0)   # nan current -> passed False
    _assert_stage_equal(100.0, 110.0, nan, 10.0)  # nan margin -> nan threshold
    _assert_stage_equal(100.0, 110.0, 0.20, nan)  # max(100, nan) -> 100
    _assert_stage_equal(nan, nan, nan, nan)


def test_compare_stage_infinities():
    inf = float("inf")
    _assert_stage_equal(inf, inf, 0.20, 10.0)
    _assert_stage_equal(100.0, inf, 0.20, 10.0)
    _assert_stage_equal(100.0, -inf, 0.20, 10.0)
    _assert_stage_equal(inf, 100.0, 0.20, 10.0)


def test_compare_stage_randomized():
    rng = random.Random(1234)
    for _ in range(300):
        baseline = rng.uniform(-50, 5000)
        current = rng.uniform(-50, 5000)
        margin = rng.uniform(-0.5, 2.0)
        floor = rng.uniform(0, 100)
        _assert_stage_equal(baseline, current, margin, floor)


def test_compare_stage_discriminating_baselines():
    """Baselines that exercise the >0 guard and the floor interaction."""
    for baseline in [0.0, -0.0, 1e-300, -1e-300, 0.1, 10.0, 10.0000001]:
        for current in [-1.0, 0.0, baseline, baseline * 1.2, 1e300]:
            for floor in [0.0, 5.0, 10.0, 1e300]:
                _assert_stage_equal(baseline, current, 0.20, floor)


# ---------------------------------------------------------------------------
# p95
# ---------------------------------------------------------------------------

def test_p95_fixed_cases():
    cases = [
        [40.0],
        [1.0, 2.0],
        [1.0, 2.0, 3.0],
        [10.0, 20.0, 30.0, 40.0],
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0],
        [40.123, 41.456, 39.789, 42.111],
        [0.0, 0.0, 0.0],
        [-5.0, -4.0, -3.0, -2.0, -1.0],
        [1e300, 2e300],
        [1e-300, 2e-300, 3e-300],
        [1234.5678, 1234.5678, 1234.5678],
    ]
    for values in cases:
        _assert_p95_equal(values)


def test_p95_decimal_rounding_discriminators():
    """Values where decimal round-half-to-even differs from a
    multiply-by-1000 double-round (the traps measured pre-migration)."""
    cases = [
        [0.0005, 0.001, 0.002],       # 0.0005 binary is just above half
        [0.0025, 0.003, 0.004],
        [0.1235, 0.1245, 0.1255],
        [0.9995, 1.0005, 1.0015],
        [2.675, 2.685, 2.695],
        [0.005, 0.015, 0.025],
        [40.0005, 40.0015, 40.0025],
        [9.9995, 10.0005, 10.0015],
    ]
    for values in cases:
        _assert_p95_equal(values)


def test_p95_all_int_inputs_preserve_int_type():
    """``round(int, 3)`` is the identity and returns an ``int`` — so an
    all-int list must yield an int from the Rust side too, not a float (the
    shim writes the result into the YAML manifest, where ``100`` vs
    ``100.0`` render differently; review P2-6). Mixed lists follow the
    ORACLE's rule: the type of the SELECTED element wins (e.g.
    ``[1.5, 2.0, 3]`` selects int ``3`` -> int). ``canon`` carries the
    concrete type on every leaf, so an int-vs-float drift cannot hide."""
    cases = [
        [1, 2, 3],
        [10, 20, 30, 40],
        list(range(1, 41)),
        [5],
        [0, 0, 0],
        [100] * 7,
        [1.5, 2.0, 3],
        [1, 2, 3.5],
        [1.0, 2, 3.0],
    ]
    for values in cases:
        ref = canon_call(_ref_p95, values)
        got = canon_call(RS_P95, values)
        assert ref == got, f"p95 type mismatch for {values!r}\n  ref={ref}\n  got={got}"


def test_p95_index_boundaries():
    """int(len * 0.95) boundaries: lengths where the index changes."""
    for n in range(1, 41):
        values = [float(i) for i in range(n)]
        _assert_p95_equal(values)
        _assert_p95_equal(list(reversed(values)))
        # same value repeated — sorted() must be stable-neutral here
        _assert_p95_equal([7.5] * n)


def test_p95_negative_and_zero_zeros():
    _assert_p95_equal([-0.0, 0.0, -0.0, 0.0])
    _assert_p95_equal([-1.0, -0.5, 0.0, 0.5, 1.0])
    _assert_p95_equal([-0.0] * 10)
    _assert_p95_equal([0.0, -0.0, 1.0, -1.0, 2.0, -2.0])


def test_p95_nan_inputs():
    """CPython sorted() places NaN by stable sort under < (every comparison
    False); the Rust comparator maps non-comparable pairs to Equal."""
    nan = float("nan")
    _assert_p95_equal([nan, 1.0, 2.0, 3.0])
    _assert_p95_equal([1.0, nan, 2.0, 3.0])
    _assert_p95_equal([1.0, 2.0, 3.0, nan])
    _assert_p95_equal([nan, nan, nan])


def test_p95_empty_raises_index_error():
    """Empty list -> IndexError, exactly like the bare expression."""
    ref = canon_call(_ref_p95, [])
    got = canon_call(RS_P95, [])
    assert ref == got, f"empty p95 mismatch\n  ref={ref}\n  got={got}"
    assert ref[0] == "raised"
    assert ref[1] == "IndexError"


def test_p95_randomized():
    rng = random.Random(99)
    for _ in range(200):
        n = rng.randint(1, 30)
        values = [
            rng.uniform(-100, 5000) for _ in range(n)
        ] + [round(rng.uniform(0, 100), 3) for _ in range(3)]
        _assert_p95_equal(values)


def test_p95_round_half_even_ticks():
    """Exactly-half decimal ticks at the third digit: round-half-to-even."""
    rng = random.Random(7)
    for _ in range(150):
        n = rng.randint(2, 12)
        # values landing exactly on a .xxx5 tick in decimal
        values = [rng.randint(0, 100000) / 1000.0 + 0.0005 for _ in range(n)]
        _assert_p95_equal(values)
