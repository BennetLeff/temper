"""Differential test: deterministic via_placement compute, Rust vs oracle.

Wave 4, **Phase 5, first slice** (deterministic leaf stages). The pure
compute of ``temper_placer/deterministic/geometry/via_placement.py`` moves
to the ``temper-geometry`` crate; the Python module becomes a delegation
shim. The pre-migration implementation is pinned VERBATIM as the oracle
(``_via_placement_py_oracle.py``).

Bit-exactness conventions (R1a): floats compare via ``float.hex()``, every
non-float leaf carries its concrete type, ``canon`` canonicalizes.

Numerical traps pinned here:
- ``distance`` uses ``math.sqrt(dx ** 2 + dy ** 2)`` — ``** 2`` is libm
  ``pow`` (NOT ``x * x``), ``math.sqrt`` is correctly-rounded IEEE sqrt.
- ``math.radians(d)`` is ``d * (pi / 180.0)``; ``math.cos`` / ``math.sin``
  are the host libm's, resolved via ``dlsym``.
- ``place_via_with_clearance`` search order is deterministic: radius list
  order, then ``range(0, 360, 45)`` — the first valid candidate wins; the
  fixed radius list is iterated in order, with ``break`` on
  ``r > max_search_radius``.
- Empty pads -> every position valid; ``None`` returned when the spiral is
  exhausted (asserted explicitly).
"""

from __future__ import annotations

import math
import random

import pytest
import temper_geometry as _tg
import tests.deterministic._via_placement_py_oracle as _oracle
from tests.core._contract_canon import canon

RS_DISTANCE = _tg.via_distance
RS_IS_VALID = _tg.is_via_position_valid
RS_PLACE = _tg.place_via_with_clearance


def _rand_pads(n: int, seed: int = 0) -> list[_oracle.PadInfo]:
    rng = random.Random(seed)
    pads = []
    for _ in range(n):
        pads.append(
            _oracle.PadInfo(
                position=(rng.uniform(-10, 10), rng.uniform(-10, 10)),
                radius=rng.uniform(0.05, 1.0),
                mask_expansion=rng.uniform(0.0, 0.5),
            )
        )
    return pads


def _pads_to_args(pads: list[_oracle.PadInfo]) -> list[float]:
    out = []
    for p in pads:
        out.extend([p.position[0], p.position[1], p.radius, p.mask_expansion])
    return out


# ---------------------------------------------------------------------------
# distance
# ---------------------------------------------------------------------------

def test_distance_basic():
    assert RS_DISTANCE(0.0, 0.0, 3.0, 4.0).hex() == (5.0).hex()
    assert RS_DISTANCE(0.0, 0.0, 3.0, 4.0) == pytest.approx(5.0)


def test_distance_bit_exact_randomized():
    rng = random.Random(3)
    for _ in range(300):
        x1, y1, x2, y2 = (rng.uniform(-100, 100) for _ in range(4))
        exp = _oracle.distance((x1, y1), (x2, y2))
        got = RS_DISTANCE(x1, y1, x2, y2)
        assert exp.hex() == got.hex(), f"distance mismatch {(x1,y1,x2,y2)}"


def test_distance_zeros_and_negatives():
    for p in [(0, 0, 0, 0), (-1.5, 2.5, 1.5, -2.5), (1e-9, 0, 0, 0)]:
        assert _oracle.distance(p[:2], p[2:]).hex() == RS_DISTANCE(*p).hex()


def test_distance_subnormals():
    # 5e-324 is a subnormal; the sum must not flush inconsistently.
    assert _oracle.distance((5e-324, 0), (0, 0)).hex() == RS_DISTANCE(5e-324, 0.0, 0.0, 0.0).hex()
    assert _oracle.distance((0, 0), (0, 5e-324)).hex() == RS_DISTANCE(0.0, 0.0, 0.0, 5e-324).hex()


def test_distance_pow_not_square():
    """`dx ** 2` is libm pow — a value where pow(x, 2.0) != x * x.

    Measured 2026-08-04: for x = -885681.5731814067, ``math.pow(x, 2.0)``
    = 0x1.6d47903ce22edp+39 but ``x * x`` = 0x1.6d47903ce22eep+39. Both arms
    must agree on this input (a Rust port using ``dx * dx`` would compute
    the second value internally). NOTE: the composed
    ``sqrt(pow(dx,2)+pow(dy,2))`` round-trips both squared values to the
    same output for THIS input — the y=0 composed distance washes the
    1-ulp inner difference out. The sqrt-composed flip is pinned
    separately by ``test_distance_sqrt_composed_discriminates_pow``.
    """
    x = -885681.5731814067
    exp = _oracle.distance((x, 0.0), (0.0, 0.0))
    got = RS_DISTANCE(x, 0.0, 0.0, 0.0)
    assert exp.hex() == got.hex()


def test_distance_sqrt_composed_discriminates_pow():
    """Fixed sqrt-composed discriminator for the ``x*x``-vs-``pow`` mutant.

    The y=0 composed distance round-trips the 1-ulp inner difference away
    (``test_distance_pow_not_square``), so the ``x*x`` mutant (M6) survives
    the fixed single-axis case AND the seed-3 randomized arm (0/1200 draws
    discriminate — the uniform(-100, 100) magnitude range never covers the
    pow-mismatch regime, which starts around |x| ~ 1e3). These pairs were
    found by scanning pow-mismatch magnitudes with a second coordinate:
    the inner sums differ by 1 ulp AND the outer ``** 0.5`` flip survives
    rounding. The oracle and kernel both call the platform libm, so the
    case discriminates wherever ``pow(x, 2.0) != x * x`` holds on the
    host, and passes vacuously on a platform where they are always equal.
    """
    cases = [
        (-122980.49419472546, 1459.765068127158),
        (3210473.261050392, 5530.1637132561655),
        (944.9477318182489, -809488.0638653971),
    ]
    for x, y in cases:
        exp = _oracle.distance((x, y), (0.0, 0.0))
        got = RS_DISTANCE(x, y, 0.0, 0.0)
        assert exp.hex() == got.hex(), f"composed pow discriminator {(x, y)}"
        # Sanity: the two inner squares must actually differ on this host,
        # or the case is vacuously passing (recorded in the docstring).
        assert math.pow(x, 2.0) != x * x or math.pow(y, 2.0) != y * y


# ---------------------------------------------------------------------------
# is_via_position_valid
# ---------------------------------------------------------------------------

def test_is_valid_no_pads_always_true():
    """Empty pads: every position valid (vacuity guard)."""
    for _ in range(20):
        x, y = random.uniform(-10, 10), random.uniform(-10, 10)
        assert _oracle.is_via_position_valid((x, y), [], 0.3) is True
        assert RS_IS_VALID(x, y, [], 0.3) is True


def _assert_valid_equal(pos, pads, via_mask, min_clearance):
    exp = _oracle.is_via_position_valid(pos, pads, via_mask, min_clearance)
    got = RS_IS_VALID(pos[0], pos[1], _pads_to_args(pads), via_mask, min_clearance)
    assert canon(exp) == canon(got), f"is_via_position_valid mismatch pos={pos}"


def test_is_valid_boundary_equality_not_less_than():
    """`< required_distance` is strict: exactly equal is VALID."""
    # Pad at origin with radius+expansion such that the required distance
    # equals the pad distance exactly.
    pad = _oracle.PadInfo(position=(0.5, 0.0), radius=0.2, mask_expansion=0.1)
    via_mask = 0.2
    min_clearance = 0.0
    # distance(0, 0 -> 0.5, 0) = 0.5 == via_mask + pad_mask + clearance
    _assert_valid_equal((0.0, 0.0), [pad], via_mask, min_clearance)


def test_is_valid_randomized():
    for seed in range(6):
        pads = _rand_pads(4, seed=seed)
        for _ in range(40):
            pos = (random.uniform(-10, 10), random.uniform(-10, 10))
            vmr = random.uniform(0.05, 0.5)
            mc = random.uniform(0.0, 0.3)
            _assert_valid_equal(pos, pads, vmr, mc)


# ---------------------------------------------------------------------------
# place_via_with_clearance
# ---------------------------------------------------------------------------

def test_place_empty_pads_returns_target():
    """Empty pads -> target position is valid -> returned unchanged."""
    for _ in range(20):
        pos = (random.uniform(-10, 10), random.uniform(-10, 10))
        assert canon(_oracle.place_via_with_clearance(pos, [], 0.3)) == canon(
            RS_PLACE(pos[0], pos[1], [], 0.3)
        )


def test_place_returns_none_when_no_candidate():
    """A pad everywhere within the search radius -> spiral exhausts -> None."""
    # A pad far larger than any candidate clearance: the whole 2mm spiral is
    # inside the pad's required distance (required = via_mask + 3.0 covers
    # the farthest candidate at distance ~2.83 from the pad center).
    pad_big = _oracle.PadInfo(position=(0.0, 0.0), radius=3.0, mask_expansion=0.0)
    exp = _oracle.place_via_with_clearance((0.0, 0.0), [pad_big], 0.2, 0.0, 2.0)
    assert exp is None
    got = RS_PLACE(0.0, 0.0, _pads_to_args([pad_big]), 0.2, 0.0, 2.0)
    assert got is None


def test_place_max_search_radius_respected():
    """Candidates at radius > max_search_radius are skipped (break)."""
    # Target invalid (distance 0 < 0.1 + 1.0). Every candidate at r <= 1.0
    # is within 1.0 mm of the pad center -> required 1.1 -> invalid; the
    # r = 1.25 candidate (distance 1.25 >= 1.1) would be valid but is
    # beyond max_search_radius=1.0 -> both arms return None.
    pad = _oracle.PadInfo(position=(0.0, 0.0), radius=1.0, mask_expansion=0.0)
    exp = _oracle.place_via_with_clearance((0.0, 0.0), [pad], 0.1, 0.0, 1.0)
    got = RS_PLACE(0.0, 0.0, _pads_to_args([pad]), 0.1, 0.0, 1.0)
    assert canon(exp) == canon(got)
    assert exp is None
    # Widening max_search_radius to 1.25 reaches the valid r=1.25 candidate.
    exp2 = _oracle.place_via_with_clearance((0.0, 0.0), [pad], 0.1, 0.0, 1.25)
    got2 = RS_PLACE(0.0, 0.0, _pads_to_args([pad]), 0.1, 0.0, 1.25)
    assert canon(exp2) == canon(got2)
    assert exp2 == (1.25, 0.0)


def _assert_place_equal(pos, pads, vmr, mc, msr):
    exp = _oracle.place_via_with_clearance(pos, pads, vmr, mc, msr)
    got = RS_PLACE(pos[0], pos[1], _pads_to_args(pads), vmr, mc, msr)
    assert canon(exp) == canon(got), f"place mismatch pos={pos} pads={pads}"


def test_place_randomized_against_oracle():
    for seed in range(8):
        pads = _rand_pads(3, seed=seed)
        for _ in range(50):
            pos = (random.uniform(-6, 6), random.uniform(-6, 6))
            vmr = random.uniform(0.05, 0.4)
            mc = random.uniform(0.0, 0.2)
            msr = random.choice([0.25, 0.5, 1.0, 1.75, 2.0])
            _assert_place_equal(pos, pads, vmr, mc, msr)


def test_place_exhaustive_angle_sweep_determinism():
    """For an identical input the Rust result is exactly reproducible."""
    pads = _rand_pads(2, seed=42)
    pos = (0.3, -0.7)
    a = RS_PLACE(pos[0], pos[1], _pads_to_args(pads), 0.2, 0.05, 2.0)
    b = RS_PLACE(pos[0], pos[1], _pads_to_args(pads), 0.2, 0.05, 2.0)
    assert canon(a) == canon(b)
