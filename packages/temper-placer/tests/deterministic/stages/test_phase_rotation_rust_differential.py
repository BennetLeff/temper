"""Differential test: deterministic _phase_rotation compute, Rust vs oracle.

Wave 4, **Phase 5, final leaves**. The ``_PhaseHVMixin._effective_ghost_pad_radius``
U2 isolation-slot reduction kernel of
``temper_placer/deterministic/stages/_phase_rotation.py`` moves to the
``temper-design-bundle`` crate (``temper_design_bundle_python.deterministic_phase``);
the Python method becomes a delegation shim. The pre-migration implementation
is pinned VERBATIM as the oracle (``_phase_rotation_py_oracle.py``).

Numerical traps pinned here:
- ``math.hypot`` is CPython's Dekker double-double ``vector_norm`` (NOT libm
  ``hypot``); the Rust side uses ``host_math::hypot`` and the differential
  includes the known last-ulp divergence operand pair.
- ``max(0.0, base_radius - reduction)`` is Python ``max`` — first argument
  on ties (a ``-0.0`` sum must come back as ``+0.0``).
- the unit vector ``(dx / d_len, dy / d_len)`` and naive ``reduction +=
  projection`` accumulation are pinned exactly; ``projection > 0.0`` is strict
  (a zero-projection slot contributes nothing).
"""

from __future__ import annotations

import random

import temper_design_bundle_python as _tdb
import tests.deterministic.stages._phase_rotation_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbol under test -- must exist or this file fails to collect (RED).
_DP = _tdb.deterministic_phase
RS_RADIUS = _DP.effective_ghost_pad_radius_py


class _FakeSlot:
    def __init__(self, start_offset, end_offset):
        self.start_offset = start_offset
        self.end_offset = end_offset


def _flat_slots(slots):
    out = []
    for s in slots:
        sx0, sy0 = s.start_offset
        sx1, sy1 = s.end_offset
        out.append((sx0, sy0, sx1, sy1))
    return out


def _assert_equal(base_radius, current, nearest, slots):
    exp = _oracle.effective_ghost_pad_radius(base_radius, current, nearest, slots)
    got = RS_RADIUS(base_radius, current, nearest, _flat_slots(slots))
    assert canon(got) == canon(exp), (
        f"radius divergence base={base_radius} current={current} "
        f"nearest={nearest} slots={[s.start_offset + s.end_offset for s in slots]}: "
        f"{canon(got)} vs {canon(exp)}"
    )


def _slot(a, b):
    return _FakeSlot(a, b)


def test_radius_basic_aligned():
    # Slot 1..6 along +x; other pin at (3, 4) (5mm away at angle 53deg).
    _assert_equal(6.0, (0.0, 0.0), (3.0, 4.0), [_slot((1.0, 0.0), (6.0, 0.0))])


def test_radius_perpendicular_slot_no_reduction():
    # Slot vertical, creepage direction horizontal -> projection 0 -> full radius.
    _assert_equal(6.0, (0.0, 0.0), (3.0, 0.0), [_slot((1.0, -2.0), (1.0, 2.0))])


def test_radius_anti_aligned_slot_reclaims_nothing():
    # Slot pointing AWAY from the other pin -> negative projection -> clamped.
    _assert_equal(6.0, (0.0, 0.0), (5.0, 0.0), [_slot((0.0, 0.0), (-4.0, 0.0))])


def test_radius_reduction_exceeds_base_clamps_to_zero():
    # Slot longer than the base radius -> max(0, negative) -> 0.0.
    got = RS_RADIUS(6.0, (0.0, 0.0), (1.0, 0.0), [(0.0, 0.0, 10.0, 0.0)])
    exp = _oracle.effective_ghost_pad_radius(
        6.0, (0.0, 0.0), (1.0, 0.0), [_slot((0.0, 0.0), (10.0, 0.0))]
    )
    assert canon(got) == canon(exp)
    assert canon(got) == ("float", "0x0.0p+0")


def test_radius_coincident_pins_early_out():
    """d_len <= 0.0 -> return base_radius unchanged (no division by zero)."""
    _assert_equal(6.0, (2.0, 3.0), (2.0, 3.0), [_slot((0.0, 0.0), (4.0, 0.0))])


def test_radius_multiple_slots_accumulate():
    _assert_equal(
        6.0,
        (0.0, 0.0),
        (4.0, 3.0),
        [
            _slot((1.0, 0.0), (3.0, 0.0)),
            _slot((0.0, 1.0), (0.0, 4.0)),
            _slot((0.0, -1.0), (0.0, -3.0)),
        ],
    )


def test_radius_hypot_last_ulp_divergence_pair():
    """The known vector_norm-vs-libm-hypot divergence: libm hypot gives a
    different last ulp than math.hypot (Dekker vector_norm). The Rust kernel
    must use host_math::hypot (the vector_norm port), not f64::hypot."""
    dx = 0x5f08330e0b997a2c  # via from_bits
    dy = 0xdf134c2707315642
    import struct

    dx = struct.unpack(">d", bytes.fromhex("5f08330e0b997a2c"))[0]
    dy = struct.unpack(">d", bytes.fromhex("df134c2707315642"))[0]
    # math.hypot(dx, dy) == 0x5f16c6eee8dc9d68 (vector_norm); libm == ...d67.
    _assert_equal(6.0, (0.0, 0.0), (dx, dy), [_slot((1.0, 0.0), (6.0, 0.0))])


def test_radius_negative_zero_tie_py_max():
    """base_radius - reduction == -0.0 (exact), and max(0.0, -0.0) == 0.0:
    py_max keeps the FIRST argument on ties, so a `-0.0` from Rust's f64::max
    would fail the bit-exact canon."""
    # Slot exactly base_radius long aligned -> reduction == base_radius exactly.
    exp = _oracle.effective_ghost_pad_radius(
        4.0, (0.0, 0.0), (1.0, 0.0), [_slot((0.0, 0.0), (4.0, 0.0))]
    )
    got = RS_RADIUS(4.0, (0.0, 0.0), (1.0, 0.0), [(0.0, 0.0, 4.0, 0.0)])
    assert canon(got) == canon(exp)
    assert canon(got) == ("float", "0x0.0p+0")


def test_radius_randomized():
    rng = random.Random(11)
    for _ in range(150):
        base = rng.uniform(0.5, 12.0)
        cx, cy = rng.uniform(-10, 10), rng.uniform(-10, 10)
        # Avoid the d_len<=0 early-out so the projection path is exercised.
        nx, ny = cx + rng.uniform(0.1, 15), cy + rng.uniform(0.1, 15)
        slots = []
        for _ in range(rng.randint(0, 4)):
            sx0, sy0 = rng.uniform(-5, 5), rng.uniform(-5, 5)
            sx1, sy1 = rng.uniform(-5, 5), rng.uniform(-5, 5)
            slots.append(_slot((sx0, sy0), (sx1, sy1)))
        _assert_equal(base, (cx, cy), (nx, ny), slots)


def test_radius_empty_slot_list():
    _assert_equal(6.0, (0.0, 0.0), (3.0, 4.0), [])
