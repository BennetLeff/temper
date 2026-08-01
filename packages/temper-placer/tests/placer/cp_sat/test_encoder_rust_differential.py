"""Differential tests: CP-SAT encoder pure compute in Rust
(temper_constraints.encoder, Wave 3 #4) vs the pre-migration pure-Python
implementations pinned verbatim as oracles.

The encoder surface's *pure numeric compute* — everything the constraint
handlers do with board geometry before/around the ortools calls — is:

  - ``mm_to_units`` / ``units_to_mm``  (``model.py::CpSatModel``) — the
    unit boundary every handler's margin math funnels through
    (separated/enclosing/onside/adjacent/aligned margins, keepout rect,
    courtyard edge margin).
  - ``courtyard_clearance_mm``          (``_encoder_solve.py``, C1) —
    the courtyard τ separated-constraint margin.
  - ``required_margin_mm``              (``domain_clearance.py``) — the
    domain-classification-derived per-pair margin (max of clearance and
    creepage minimums).
  - ``keepout_rect_units``              (``handlers/keepout.py``) — the
    margin-expanded keepout bbox in model units.

The ortools wiring (CpModel/IntVar construction, handler dispatch,
solver calls) stays Python; only these pure functions move to Rust.

Bit-exactness notes (learned in this repo):
  - Python ``round(x)`` (no ndigits) is round-half-even on the float, and
    ``int(round(x))`` raises OverflowError/ValueError on ±inf/NaN — the
    Rust port replicates both the tie behavior (``round_ties_even``) and
    the non-finite errors.
  - The even-parity adjustment ``raw - (raw % 2)`` uses Python's
    *floor* modulo, so a negative odd ``raw`` decrements by one (e.g.
    -15 -> -16); Rust's truncating ``%`` would give -14, so the port
    uses ``rem_euclid``.
  - ``keepout_rect_units``'s width/height convert the *difference*
    ``zx_max - zx_min`` (f64 subtraction first) before unit conversion —
    not ``mm_to_units(zx_max) - mm_to_units(zx_min)`` — order preserved
    exactly.

The direct ``temper_constraints`` pins fail first (the functions do not
exist yet); the module-level pins exercise the full delegation path once
wired.
"""

from __future__ import annotations

import random

import temper_constraints as _tc

from temper_placer.placer.cp_sat.domain_clearance import required_margin_mm
from temper_placer.placer.cp_sat.model import CpSatModel

# ---------------------------------------------------------------------------
# Oracles (pre-migration implementations, verbatim)
# ---------------------------------------------------------------------------


def _oracle_mm_to_units(mm: float, units_per_mm: int) -> int:
    raw = int(round(mm * units_per_mm))
    return raw - (raw % 2) if raw % 2 else raw


def _oracle_units_to_mm(units: int, units_per_mm: int) -> float:
    return units / units_per_mm


def _oracle_courtyard_clearance_mm(default_clearance_mm: float, mask_expansion_mm: float) -> float:
    return default_clearance_mm + 2 * mask_expansion_mm


def _oracle_required_margin_mm(clearance_mm: float, creepage_mm: float) -> float:
    return max(clearance_mm, creepage_mm)


def _oracle_keepout_rect_units(
    zx_min: float,
    zy_min: float,
    zx_max: float,
    zy_max: float,
    margin_mm: float,
    units_per_mm: int,
):
    margin_u = _oracle_mm_to_units(margin_mm, units_per_mm)
    kx_s = _oracle_mm_to_units(zx_min, units_per_mm) - margin_u
    ky_s = _oracle_mm_to_units(zy_min, units_per_mm) - margin_u
    kx_w = _oracle_mm_to_units(zx_max - zx_min, units_per_mm) + 2 * margin_u
    ky_h = _oracle_mm_to_units(zy_max - zy_min, units_per_mm) + 2 * margin_u
    return (kx_s, ky_s, kx_w, ky_h)


# ---------------------------------------------------------------------------
# Random helpers
# ---------------------------------------------------------------------------

_UNIT_GRIDS = [1, 10, 50, 100, 101, 1000]


def _random_mm(rng) -> float:
    return rng.uniform(-100.0, 100.0)


def _random_zone(rng):
    x0, y0 = rng.uniform(-100.0, 100.0), rng.uniform(-100.0, 100.0)
    w, h = rng.uniform(0.0, 100.0), rng.uniform(0.0, 100.0)
    return (x0, y0, x0 + w, y0 + h)


# ---------------------------------------------------------------------------
# mm_to_units parity
# ---------------------------------------------------------------------------


def test_mm_to_units_rust_direct_pin():
    """Direct Rust pin — fails before the crate exposes mm_to_units_py."""
    rng = random.Random(20260731)
    for _ in range(400):
        mm, u = _random_mm(rng), rng.choice(_UNIT_GRIDS)
        assert _tc.mm_to_units_py(mm, u) == _oracle_mm_to_units(mm, u)


def test_mm_to_units_matches_oracle_bit_exact():
    rng = random.Random(20260731)
    for _ in range(500):
        mm, u = _random_mm(rng), rng.choice(_UNIT_GRIDS)
        model = CpSatModel(units_per_mm=u)
        assert model.mm_to_units(mm) == _oracle_mm_to_units(mm, u)


def test_mm_to_units_exact_binary_ties():
    """mm*u exactly k+0.5 (mm = m/8, m odd) → round-half-even, then parity."""
    # m=1: 12.5 -> 12 (tie to even); m=3: 37.5 -> 38; m=5: 62.5 -> 62.
    assert _tc.mm_to_units_py(0.125, 100) == 12
    assert _tc.mm_to_units_py(0.375, 100) == 38
    assert _tc.mm_to_units_py(0.625, 100) == 62
    assert _oracle_mm_to_units(0.125, 100) == 12
    assert _oracle_mm_to_units(0.375, 100) == 38
    assert _oracle_mm_to_units(0.625, 100) == 62


def test_mm_to_units_odd_raw_even_adjusted():
    """Non-tie odd raw (e.g. 31.25 -> 31) is forced even (31 -> 30)."""
    assert _tc.mm_to_units_py(0.3125, 100) == 30
    assert _oracle_mm_to_units(0.3125, 100) == 30
    # Computed-value path: 0.155*100 rounds to exactly 15.5 -> tie to even
    # -> 16 (no adjustment needed; pins the f64 product, not the decimal).
    assert _tc.mm_to_units_py(0.155, 100) == _oracle_mm_to_units(0.155, 100)
    assert _tc.mm_to_units_py(0.155, 100) == 16


def test_mm_to_units_negative_floor_modulo():
    """Negative odd raw decrements by one (Python floor-mod semantics):
    -15 -> -16, never -14 (Rust truncating % would give the latter)."""
    assert _tc.mm_to_units_py(-0.155, 100) == -16
    assert _oracle_mm_to_units(-0.155, 100) == -16
    assert _tc.mm_to_units_py(-0.125, 100) == -12  # tie to even
    assert _oracle_mm_to_units(-0.125, 100) == -12
    assert _tc.mm_to_units_py(-3.0, 100) == -300
    assert _oracle_mm_to_units(-3.0, 100) == -300


def test_mm_to_units_zero_and_small():
    assert _tc.mm_to_units_py(0.0, 100) == 0
    assert _tc.mm_to_units_py(0.001, 100) == _oracle_mm_to_units(0.001, 100)
    assert _tc.mm_to_units_py(1e-9, 100) == 0
    assert _oracle_mm_to_units(1e-9, 100) == 0


def test_mm_to_units_non_finite_raises_like_python():
    """int(round(inf)) -> OverflowError; int(round(nan)) -> ValueError."""
    import pytest

    for bad in (float("inf"), float("-inf")):
        with pytest.raises(OverflowError):
            _tc.mm_to_units_py(bad, 100)
    with pytest.raises(ValueError):
        _tc.mm_to_units_py(float("nan"), 100)


# ---------------------------------------------------------------------------
# units_to_mm parity
# ---------------------------------------------------------------------------


def test_units_to_mm_rust_direct_pin():
    rng = random.Random(20260731)
    for _ in range(300):
        units, u = rng.randint(-10_000, 10_000), rng.choice(_UNIT_GRIDS)
        assert _tc.units_to_mm_py(units, u) == _oracle_units_to_mm(units, u)


def test_units_to_mm_matches_oracle_bit_exact():
    rng = random.Random(20260731)
    for _ in range(300):
        units, u = rng.randint(-10_000, 10_000), rng.choice(_UNIT_GRIDS)
        model = CpSatModel(units_per_mm=u)
        assert model.units_to_mm(units) == _oracle_units_to_mm(units, u)


def test_units_to_mm_known_points():
    assert _tc.units_to_mm_py(1000, 100) == 10.0
    assert _tc.units_to_mm_py(0, 100) == 0.0
    assert _tc.units_to_mm_py(-1000, 100) == -10.0
    assert _tc.units_to_mm_py(1, 100) == 0.01
    assert _tc.units_to_mm_py(100, 100) == 1.0


# ---------------------------------------------------------------------------
# courtyard_clearance_mm parity (C1, _encoder_solve.py)
# ---------------------------------------------------------------------------


def test_courtyard_clearance_rust_direct_pin():
    rng = random.Random(20260731)
    for _ in range(300):
        d = rng.uniform(0.0, 5.0)
        e = rng.uniform(0.0, 1.0)
        assert _tc.courtyard_clearance_mm_py(d, e) == _oracle_courtyard_clearance_mm(d, e)


def test_courtyard_clearance_known_points():
    # The production operating point: default 0.2mm + 2 * 0.1mm mask expansion.
    assert _tc.courtyard_clearance_mm_py(0.2, 0.1) == 0.4
    assert _oracle_courtyard_clearance_mm(0.2, 0.1) == 0.4
    assert _tc.courtyard_clearance_mm_py(0.0, 0.0) == 0.0
    assert _tc.courtyard_clearance_mm_py(1.0, 0.25) == 1.5


def test_courtyard_clearance_strict_plus_not_max():
    """τ uses + (mask apertures must not touch) — an exactly-zero margin
    input must still yield a strictly positive τ when expansion > 0."""
    assert _tc.courtyard_clearance_mm_py(0.0, 0.1) == 0.2
    assert _tc.courtyard_clearance_mm_py(0.0, 0.1) > 0.0


def test_courtyard_clearance_matches_module_level():
    """Module-level delegation: _encoder_solve.courtyard_clearance_mm is
    the τ (C1) the solver feeds EncoderContext.courtyard_clearance_mm."""
    from temper_placer.placer.cp_sat._encoder_solve import (
        MASK_EXPANSION_MM,
        courtyard_clearance_mm,
    )

    assert MASK_EXPANSION_MM == 0.1
    assert courtyard_clearance_mm(0.2) == _oracle_courtyard_clearance_mm(0.2, MASK_EXPANSION_MM)
    assert courtyard_clearance_mm(0.2) == 0.4
    rng = random.Random(20260731)
    for _ in range(100):
        d = rng.uniform(0.0, 5.0)
        assert courtyard_clearance_mm(d) == _oracle_courtyard_clearance_mm(d, MASK_EXPANSION_MM)


# ---------------------------------------------------------------------------
# required_margin_mm parity (domain_clearance.py)
# ---------------------------------------------------------------------------


def test_required_margin_rust_direct_pin():
    rng = random.Random(20260731)
    for _ in range(300):
        c = rng.uniform(0.0, 20.0)
        k = rng.uniform(0.0, 20.0)
        assert _tc.required_margin_mm_py(c, k) == _oracle_required_margin_mm(c, k)


def test_required_margin_matches_oracle_bit_exact():
    rng = random.Random(20260731)
    for _ in range(300):
        c = rng.uniform(0.0, 20.0)
        k = rng.uniform(0.0, 20.0)
        req = {"min_clearance_mm": c, "min_creepage_mm": k}
        assert required_margin_mm(req) == _oracle_required_margin_mm(c, k)


def test_required_margin_known_points():
    assert _tc.required_margin_mm_py(6.0, 8.0) == 8.0
    assert _tc.required_margin_mm_py(8.0, 6.0) == 8.0
    assert _tc.required_margin_mm_py(6.0, 6.0) == 6.0
    assert required_margin_mm({"min_clearance_mm": 6.0, "min_creepage_mm": 8.0}) == 8.0


def test_required_margin_nan_python_builtin_max_semantics():
    """Python builtin max(NaN, x) == NaN but max(x, NaN) == x; the Rust
    port must replicate the builtin (f64::max would discard NaN)."""
    import math

    nan = float("nan")
    assert math.isnan(_tc.required_margin_mm_py(nan, 8.0))
    assert math.isnan(_oracle_required_margin_mm(nan, 8.0))
    # Builtin max(x, NaN) returns x when x > NaN is False.
    assert _tc.required_margin_mm_py(8.0, nan) == 8.0
    assert _oracle_required_margin_mm(8.0, nan) == 8.0


# ---------------------------------------------------------------------------
# keepout_rect_units parity (handlers/keepout.py)
# ---------------------------------------------------------------------------


def test_keepout_rect_rust_direct_pin():
    rng = random.Random(20260731)
    for _ in range(400):
        z = _random_zone(rng)
        margin = rng.uniform(0.0, 5.0)
        u = rng.choice(_UNIT_GRIDS)
        assert _tc.keepout_rect_units_py(*z, margin, u) == _oracle_keepout_rect_units(*z, margin, u)


def test_keepout_rect_known_points():
    # Zone (10,10)-(20,20)mm, margin 0.5mm, u=100.
    got = _tc.keepout_rect_units_py(10.0, 10.0, 20.0, 20.0, 0.5, 100)
    assert got == _oracle_keepout_rect_units(10.0, 10.0, 20.0, 20.0, 0.5, 100)
    assert got == (1000 - 50, 1000 - 50, 1000 + 100, 1000 + 100)  # (950, 950, 1100, 1100)
    # Zero margin: rect == converted zone.
    assert _tc.keepout_rect_units_py(10.0, 10.0, 20.0, 20.0, 0.0, 100) == (1000, 1000, 1000, 1000)
    assert _tc.keepout_rect_units_py(0.0, 0.0, 0.0, 0.0, 0.5, 100) == (
        _oracle_keepout_rect_units(0.0, 0.0, 0.0, 0.0, 0.5, 100)
    )


def test_keepout_rect_difference_before_conversion():
    """The width converts zx_max - zx_min (f64 difference first), NOT
    mm_to_units(zx_max) - mm_to_units(zx_min) — the two disagree at
    rounding boundaries (measured pair below: diff_first=-90,
    diff_later=-88)."""
    zx_min, zx_max = 0.11599784954941361, 1.0148714663788405
    margin, u = 0.0, 100
    got = _tc.keepout_rect_units_py(zx_min, 0.0, zx_max, 0.0, margin, u)
    expected = _oracle_keepout_rect_units(zx_min, 0.0, zx_max, 0.0, margin, u)
    assert got == expected
    # The two conversion orders genuinely disagree on this input:
    diff_first = _oracle_mm_to_units(zx_max - zx_min, u)
    diff_later = _oracle_mm_to_units(zx_max, u) - _oracle_mm_to_units(zx_min, u)
    assert diff_first != diff_later
    assert got[2] == diff_first


def test_keepout_rect_negative_floor_modulo():
    # A negative raw in the conversion path must floor-mod (see
    # test_mm_to_units_negative_floor_modulo): -0.155 -> -16, so
    # kx_s for a negative-cornered zone decrements, not increments.
    got = _tc.keepout_rect_units_py(-0.155, 0.0, 1.0, 1.0, 0.0, 100)
    assert got == _oracle_keepout_rect_units(-0.155, 0.0, 1.0, 1.0, 0.0, 100)
    assert got[0] == -16
