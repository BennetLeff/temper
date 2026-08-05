"""Differential test: temper-workflow routing/route_and_measure.py compute,
Rust vs oracle.

Wave 4, **Phase 5** (cli/adapters/temper-workflow slice). The copper-length
compute of ``temper_workflow/routing/route_and_measure.py``
(``measure_copper_length``) moves to the ``temper-orchestration`` crate
(``temper_orchestration.measure_copper_length``); the Python module keeps
its parse call (``temper_placer.io.kicad_parser.parse_kicad_pcb`` — a
Phase-3 surface, not this slice's) and its script ``main()``, and delegates
the per-trace accumulation across the boundary. The parse step stays Python
and the shim flattens ``result.traces`` to ``(net, sx, sy, ex, ey)`` tuples.

The pre-migration module is pinned VERBATIM as the oracle
(``tests/_route_and_measure_py_oracle.py``). ``measure_copper_length``'s
loop body is extracted mechanically as ``_ref_accumulate`` (oracle lines
~32-47: the falsy-net skip, ``dx = trace.end[0] - trace.start[0]`` /
``dy = ...``, ``math.sqrt(dx**2 + dy**2)``, the per-net
``net_lengths.get(net, 0.0) + length`` in first-seen order, and the naive
``total_length += length``).

Bit-exactness conventions (R1a): floats compare via ``float.hex()``
(canon); the net-length map compares as an insertion-order-preserving dict
(first-seen order IS part of the contract); ``via_count`` is an int.

Numerical traps pinned here:
- ``dx ** 2`` / ``dy ** 2`` are CPython ``float ** float`` — libm ``pow``
  via ``dlsym``, NOT ``x * x`` (the Wave-4 guide's measured trap: 262/200000
  mismatches of ``x*x`` vs ``x**2``). The Rust side resolves ``pow`` via
  ``dlsym(RTLD_DEFAULT, ...)`` to the exact libm the host CPython loads.
- ``math.sqrt`` is the correctly-rounded IEEE sqrt → ``f64::sqrt`` (the
  guide's measured 0/200000 mismatches for sqrt).
- ``total_length += length`` and ``net_lengths.get(net, 0.0) + length`` are
  naive (non-compensated) accumulation — the Rust side uses plain f64
  ``+=`` / add, NOT pairwise or compensated summation.
- ``if not trace.net`` is a truthiness skip: empty string and None both
  skip. The flattened ``Option<String>`` net preserves that.

The differential domain is flattened segment tuples; the shim's
flatten-and-assemble path (``_measure_from_segments``) is driven directly
and compared against the oracle extraction's full dict result.
"""

from __future__ import annotations

import math
import random

import pytest
import temper_orchestration as _to

import tests._route_and_measure_py_oracle as _oracle  # noqa: F401  (provenance anchor)
from temper_workflow.routing.route_and_measure import _measure_from_segments


def _canon(value) -> tuple:
    """Minimal type-carrying, bit-exact canonicalizer for this differential's
    leaf types (the temper-placer ``tests.core._contract_canon`` helper lives
    in a different test tree and is not importable from this package).
    Floats compare as ``float.hex()``; bool before int; dicts keep insertion
    order (it IS part of the net-lengths contract)."""
    if value is None:
        return ("NoneType",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, float):
        return ("float", "nan" if value != value else value.hex())
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, dict):
        return ("dict", tuple((_canon(k), _canon(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(_canon(v) for v in value))
    raise TypeError(f"unhandled type {type(value)!r} for {value!r}")

# Rust symbol under test — must exist or this file fails to collect (RED).
RS_MEASURE = _to.measure_copper_length


# ---------------------------------------------------------------------------
# Reference arm — mechanically extracted from the oracle's
# measure_copper_length loop body (oracle lines 32-47).
# ---------------------------------------------------------------------------

def _ref_accumulate(segments: list[tuple]) -> tuple[float, dict]:
    """Extracted from the oracle's ``measure_copper_length`` loop body.

    First-seen net order and the per-net addition order are part of the
    contract (the oracle builds the dict fresh as it goes).
    """
    net_lengths: dict = {}
    total_length = 0.0
    for net_name, sx, sy, ex, ey in segments:
        if not net_name:
            continue
        dx = ex - sx
        dy = ey - sy
        length = math.sqrt(dx**2 + dy**2)
        net_lengths[net_name] = net_lengths.get(net_name, 0.0) + length
        total_length += length
    return total_length, net_lengths


def _ref_measure(segments: list[tuple], via_count: int) -> dict:
    """The oracle's full return value for flattened segments."""
    total, net_lengths = _ref_accumulate(segments)
    return {
        "total_wirelength_mm": total,
        "net_lengths_mm": net_lengths,
        "via_count": via_count,
    }


def _assert_segments_equal(segments: list[tuple], via_count: int) -> None:
    ref = _canon(_ref_measure(segments, via_count))
    got = _canon(_measure_from_segments(segments, via_count))
    assert ref == got, f"measure mismatch for {segments!r} via={via_count}\n  ref={ref}\n  got={got}"
    # Also drive the raw Rust kernel directly (the shim's flatten is thin).
    rust_total, rust_pairs = RS_MEASURE(segments)
    ref_total, ref_map = _ref_accumulate(segments)
    assert _canon(rust_total) == _canon(ref_total)
    assert _canon(list(rust_pairs)) == _canon(list(ref_map.items()))


# ---------------------------------------------------------------------------
# Fixed cases
# ---------------------------------------------------------------------------

def test_measure_empty_traces():
    _assert_segments_equal([], 0)
    _assert_segments_equal([], 7)


def test_measure_single_segment():
    _assert_segments_equal([("GND", 0.0, 0.0, 3.0, 4.0)], 2)   # 3-4-5 triangle
    _assert_segments_equal([("VCC", 1.0, 1.0, 1.0, 1.0)], 0)   # zero length
    _assert_segments_equal([("A", 0.0, 0.0, -3.0, -4.0)], 1)   # negative coords


def test_measure_multiple_nets_first_seen_order():
    segments = [
        ("GND", 0.0, 0.0, 1.0, 0.0),
        ("VCC", 0.0, 0.0, 0.0, 2.0),
        ("GND", 1.0, 0.0, 1.0, 3.0),   # GND again — order stays first-seen
    ]
    _assert_segments_equal(segments, 3)


def test_measure_falsy_nets_skipped():
    segments = [
        ("GND", 0.0, 0.0, 3.0, 4.0),
        ("", 0.0, 0.0, 100.0, 100.0),     # empty net — skipped by truthiness
        (None, 0.0, 0.0, 100.0, 100.0),   # None net — skipped
        ("VCC", 0.0, 0.0, 6.0, 8.0),
    ]
    _assert_segments_equal(segments, 5)


def test_measure_total_is_naive_sum():
    """Naive accumulation order: total_length += length in trace order."""
    rng = random.Random(3)
    segments = [(f"N{i % 3}", float(rng.uniform(-10, 10)), float(rng.uniform(-10, 10)),
                 float(rng.uniform(-10, 10)), float(rng.uniform(-10, 10))) for i in range(50)]
    ref_total, ref_map = _ref_accumulate(segments)
    rust_total, rust_pairs = RS_MEASURE(segments)
    assert _canon(ref_total) == _canon(rust_total)
    assert _canon(list(ref_map.items())) == _canon(list(rust_pairs))


# ---------------------------------------------------------------------------
# Randomized differential
# ---------------------------------------------------------------------------

def test_measure_randomized():
    rng = random.Random(2026)
    nets = ["GND", "VCC", "SIG1", "SIG2", "", None, "HV"]
    for _ in range(150):
        n = rng.randint(0, 40)
        segments = []
        for _ in range(n):
            net = rng.choice(nets)
            if rng.random() < 0.6:
                # full-precision differences: pow-vs-multiply ulp boundaries
                # need full-precision doubles (the M10 survivor's fix)
                segments.append((
                    net,
                    rng.uniform(-100, 100),
                    rng.uniform(-100, 100),
                    rng.uniform(-100, 100),
                    rng.uniform(-100, 100),
                ))
            else:
                segments.append((
                    net,
                    round(rng.uniform(-100, 100), 6),
                    round(rng.uniform(-100, 100), 6),
                    round(rng.uniform(-100, 100), 6),
                    round(rng.uniform(-100, 100), 6),
                ))
        _assert_segments_equal(segments, rng.randint(0, 20))


def test_measure_pow_vs_multiply_discriminators():
    """Full-precision deltas where ``math.sqrt(dx**2 + dy**2)`` (libm pow)
    differs from ``math.sqrt(dx*dx + dy*dy)`` in the last ulp — the M10
    survivor's discriminating cases (found by the mutation campaign)."""
    discriminators = [
        (0.0, 0.0, 19.502714311008788, 77.77522467438322),
        (0.0, 0.0, 63.25882713708185, 96.53268856857747),
        (0.0, 0.0, -5.007201717971483, -65.13159001325664),
        (10.5, -3.25, 73.76269374144761, 20.182844750239716),
    ]
    for sx, sy, ex, ey in discriminators:
        _assert_segments_equal([("N", sx, sy, ex, ey)], 1)
        _assert_segments_equal([("N", sx, sy, ex, ey), ("M", sx, sy, ex, ey)], 2)


def test_measure_exact_half_squares():
    """Segments whose squared deltas land exactly on .5 / discriminating
    dyadic fractions — pow-vs-multiply discriminators."""
    rng = random.Random(11)
    for _ in range(120):
        sx, sy = 0.0, 0.0
        ex = rng.randint(-20, 20) + 0.5
        ey = rng.randint(-20, 20) + 0.5
        _assert_segments_equal([("N", sx, sy, ex, ey)], 0)


def test_measure_accumulation_order_discriminates():
    """The same three segments in different orders give different totals under
    naive accumulation — the Rust must accumulate in the SAME order."""
    a = ("GND", 0.0, 0.0, 0.1, 0.0)
    b = ("VCC", 0.0, 0.0, 1e16, 0.0)   # huge — swallows the small add
    c = ("SIG", 0.0, 0.0, 0.2, 0.0)
    _assert_segments_equal([a, b, c], 0)
    _assert_segments_equal([b, a, c], 0)
    _assert_segments_equal([c, b, a], 0)


@pytest.mark.parametrize("n", [0, 1, 2, 3, 7, 8, 19, 20, 63])
def test_measure_net_count_boundaries(n):
    """Single-net accumulation across lengths — the dict/vec grows 1..n."""
    segments = [("ONENET", float(i), 0.0, float(i + 1), 0.0) for i in range(n)]
    _assert_segments_equal(segments, n)
