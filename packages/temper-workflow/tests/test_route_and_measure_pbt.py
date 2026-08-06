"""Property-based + metamorphic tests for the migrated route_and_measure
compute.

Wave 4, Phase 5 (cli/adapters/temper-workflow slice). These properties
exercise the migrated ``temper_orchestration.measure_copper_length`` via the
delegation shim ``temper_workflow/routing/route_and_measure.py``
(``_measure_from_segments``) and the raw kernel; bit-identical parity
against the pinned pre-migration Python is asserted separately by
``test_route_and_measure_rust_differential.py``.

Deterministic seeded-random generation (the workflow package has no
hypothesis dev dependency); every property is non-vacuously guarded by a G4
vacuity mutant swapped in via the ``_kernels`` indirection.

Five properties (R1c):

- C1. Single-net identity: for one net, ``total_wirelength_mm`` is
  bit-exactly that net's accumulated length.
- C2. Zero-length inertness: a segment with ``sx == ex`` and ``sy == ey``
  contributes exactly ``0.0`` and leaves the total bit-unchanged.
- C3. Falsy-net inertness: ``""``/``None`` net segments contribute nothing
  to the total or to ``net_lengths_mm``.
- C4. Non-negativity: the total and every per-net length are ``>= 0.0``.
- C5. First-seen key order: ``net_lengths_mm`` keys appear in first-seen
  order, and the map has exactly one entry per distinct non-falsy net.

Three metamorphic relations (R1d):

- MC1. Zero-length removal: deleting every zero-length segment leaves the
  report bit-identical.
- MC2. Falsy-net removal: deleting every falsy-net segment leaves the
  report bit-identical.
- MC3. Via-count passthrough: ``via_count`` is echoed unchanged into the
  report dict (the shim's assembly, not the kernel).
"""

from __future__ import annotations

import random

import pytest
import temper_orchestration as _to

from temper_workflow.routing.route_and_measure import _measure_from_segments

_SEED = 20260804


def _segments(rng: random.Random, n: int) -> list[tuple]:
    nets = ["GND", "VCC", "SIG1", "SIG2", "", None]
    out = []
    for _ in range(n):
        out.append((
            rng.choice(nets),
            round(rng.uniform(-100, 100), 6),
            round(rng.uniform(-100, 100), 6),
            round(rng.uniform(-100, 100), 6),
            round(rng.uniform(-100, 100), 6),
        ))
    return out


def _hex(x: float) -> str:
    return x.hex()


# ---------------------------------------------------------------------------
# Kernel indirection — the vacuity-mutant seam (G4 evidence pattern).
# ---------------------------------------------------------------------------


class _Kernels:
    measure = staticmethod(lambda segments: _to.measure_copper_length(segments))


_kernels = _Kernels()


@pytest.fixture
def _restore_kernels():
    saved = _kernels.measure
    yield
    _kernels.measure = saved


def _assert_property_fails(property_fn, *args):
    with pytest.raises((AssertionError, KeyError, AttributeError, TypeError)):
        property_fn(*args)


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_c1_single_net_identity():
    """C1: with a single net, total is bit-exactly that net's length."""
    rng = random.Random(_SEED)
    for _ in range(80):
        net = rng.choice(["GND", "VCC"])
        segs = [
            (net, round(rng.uniform(-100, 100), 6), round(rng.uniform(-100, 100), 6),
             round(rng.uniform(-100, 100), 6), round(rng.uniform(-100, 100), 6))
            for _ in range(rng.randint(1, 12))
        ]
        total, pairs = _kernels.measure(segs)
        assert len(pairs) == 1
        assert total.hex() == pairs[0][1].hex()
        report = _measure_from_segments(segs, 3)
        assert report["total_wirelength_mm"].hex() == report["net_lengths_mm"][pairs[0][0]].hex()


def test_c2_zero_length_inertness():
    """C2: zero-length segments contribute exactly 0.0 — the total stays
    bit-unchanged, existing nets keep their accumulated lengths bit-exactly,
    and a zero-length segment of a NEW net adds an exact 0.0 entry (the
    oracle's ``net_lengths.get(net, 0.0) + 0.0``)."""
    rng = random.Random(_SEED + 1)
    for _ in range(60):
        segs = _segments(rng, rng.randint(0, 10))
        zeros = [("N", round(rng.uniform(-10, 10), 6), round(rng.uniform(-10, 10), 6),
                  round(rng.uniform(-10, 10), 6), round(rng.uniform(-10, 10), 6))
                 for _ in range(3)]
        # make them zero-length
        zeros = [(net, sx, sy, sx, sy) for net, sx, sy, _, _ in zeros]
        total_a, pairs_a = _kernels.measure(segs)
        total_b, pairs_b = _kernels.measure(segs + zeros)
        assert total_b.hex() == total_a.hex()
        map_b = dict(pairs_b)
        for net, length in pairs_a:
            assert map_b[net].hex() == length.hex()
        for net, *_ in zeros:
            assert map_b[net] == 0.0


def test_c3_falsy_net_inertness():
    """C3: ""/None net segments contribute nothing."""
    rng = random.Random(_SEED + 2)
    for _ in range(60):
        segs = _segments(rng, rng.randint(0, 10))
        falsy = [("", 0.0, 0.0, 100.0, 100.0), (None, 0.0, 0.0, 100.0, 100.0)]
        total_a, pairs_a = _kernels.measure(segs)
        total_b, pairs_b = _kernels.measure(segs + falsy)
        assert total_b.hex() == total_a.hex()
        assert pairs_b == pairs_a
        report = _measure_from_segments(segs + falsy, 4)
        assert set(report["net_lengths_mm"]) == {n for n, *_ in segs if n}


def test_c4_non_negativity():
    """C4: total and per-net lengths are >= 0.0 (Euclidean lengths)."""
    rng = random.Random(_SEED + 3)
    for _ in range(60):
        segs = _segments(rng, rng.randint(0, 15))
        total, pairs = _kernels.measure(segs)
        assert total >= 0.0
        for _, length in pairs:
            assert length >= 0.0


def test_c5_first_seen_order_and_distinct_count():
    """C5: keys in first-seen order; one entry per distinct non-falsy net."""
    rng = random.Random(_SEED + 4)
    for _ in range(60):
        segs = _segments(rng, rng.randint(0, 20))
        _, pairs = _kernels.measure(segs)
        seen: list[str] = []
        for net, _, _, _, _ in segs:
            if net and net not in seen:
                seen.append(net)
        assert [n for n, _ in pairs] == seen


# ---------------------------------------------------------------------------
# Metamorphic relations
# ---------------------------------------------------------------------------


def test_mc1_zero_length_removal():
    """MC1: deleting zero-length segments leaves the report bit-identical."""
    rng = random.Random(_SEED + 5)
    for _ in range(50):
        segs = _segments(rng, rng.randint(0, 12))
        cleaned = [(n, sx, sy, ex, ey) for n, sx, sy, ex, ey in segs
                   if not (sx == ex and sy == ey)]
        report_a = _measure_from_segments(segs, 2)
        report_b = _measure_from_segments(cleaned, 2)
        assert report_b["total_wirelength_mm"].hex() == report_a["total_wirelength_mm"].hex()
        assert report_b["net_lengths_mm"] == report_a["net_lengths_mm"]


def test_mc2_falsy_net_removal():
    """MC2: deleting falsy-net segments leaves the report bit-identical."""
    rng = random.Random(_SEED + 6)
    for _ in range(50):
        segs = _segments(rng, rng.randint(0, 12))
        cleaned = [s for s in segs if s[0]]
        report_a = _measure_from_segments(segs, 2)
        report_b = _measure_from_segments(cleaned, 2)
        assert report_b["total_wirelength_mm"].hex() == report_a["total_wirelength_mm"].hex()
        assert report_b["net_lengths_mm"] == report_a["net_lengths_mm"]


def test_mc3_via_count_passthrough():
    """MC3: via_count is echoed unchanged into the report dict."""
    rng = random.Random(_SEED + 7)
    for via_count in [0, 1, 7, 123]:
        segs = _segments(rng, 5)
        report = _measure_from_segments(segs, via_count)
        assert report["via_count"] == via_count


# ---------------------------------------------------------------------------
# G4 vacuity mutants — one per property.
# ---------------------------------------------------------------------------


def test_c1_fails_for_zero_total_kernel(_restore_kernels):
    """A kernel returning total 0.0 always breaks C1."""

    def zero_total(segments):
        return (0.0, _to.measure_copper_length(segments)[1])

    _kernels.measure = zero_total
    _assert_property_fails(test_c1_single_net_identity)


def test_c2_fails_for_counting_zero_length_kernel(_restore_kernels):
    """A kernel that lets zero-length segments contribute breaks C2."""

    def counting_zeros(segments):
        total, pairs = _to.measure_copper_length(segments)
        zeros = sum(1 for n, sx, sy, ex, ey in segments if sx == ex and sy == ey and n)
        return (total + zeros, pairs)

    _kernels.measure = counting_zeros
    _assert_property_fails(test_c2_zero_length_inertness)


def test_c3_fails_for_counting_falsy_kernel(_restore_kernels):
    """A kernel that lets falsy-net segments contribute breaks C3."""

    def counting_falsy(segments):
        total, pairs = _to.measure_copper_length(segments)
        falsy_len = sum(1 for n, *_ in segments if not n)
        return (total + falsy_len, pairs)

    _kernels.measure = counting_falsy
    _assert_property_fails(test_c3_falsy_net_inertness)


def test_c4_fails_for_negative_total_kernel(_restore_kernels):
    """A kernel returning a negative total breaks C4."""

    def negative_total(segments):
        total, pairs = _to.measure_copper_length(segments)
        return (total - 1.0, pairs)

    _kernels.measure = negative_total
    _assert_property_fails(test_c4_non_negativity)


def test_c5_fails_for_reordered_kernel(_restore_kernels):
    """A kernel that sorts the net-length pairs alphabetically breaks C5
    (first-seen order is the contract)."""

    def sorted_pairs(segments):
        total, pairs = _to.measure_copper_length(segments)
        return (total, sorted(pairs))

    _kernels.measure = sorted_pairs
    _assert_property_fails(test_c5_first_seen_order_and_distinct_count)
