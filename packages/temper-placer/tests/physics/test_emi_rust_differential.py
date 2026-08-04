"""Differential tests: temper-thermal Rust EMI kernels vs the pure-Python
reference (temper_placer/physics/emi.py, Wave 4 Phase 4).

The pre-migration implementation is pinned here as an oracle (verbatim
semantics, including the exact f64 operation order:
``(1.316e-14 * A * I * (f**2)) / d`` as a left-to-right chain with the
parenthesized ``f**2`` power evaluated before the multiply,
``e_uv_per_m = e_v_per_m * 1e6``, the ``e_uv_per_m <= 0`` guard, and the
final ``20 * math.log10(e_uv_per_m)``; ``check_emi_compliance`` is the
``"CISPR32_CLASS_A"`` → 50.0 / else 40.0 limit lookup with an IEEE
``<=`` comparison).  Any change to the Rust kernels
(packages/temper-thermal/src/emi.rs) or the Python delegation that
disagrees with the oracle fails here, bit-exactly.

Bit-exactness notes (Wave 4 catalog):

- **B1 (host libm via dlsym):** ``math.log10`` and ``frequency_mhz**2``
  resolve to the host Python runtime's libm; the Rust kernel uses the
  same host libm via ``dlsym`` (``host_math``), so outputs are
  bit-identical.  The ``**2`` is CPython ``float.__pow__`` → libm
  ``pow(x, 2.0)`` — NOT ``x * x`` (they differ on ~0.14% of random
  floats; pinned below by randomized pins).
- **B7 (f64 operation order):** the field chain keeps the oracle's exact
  op count, grouping (parenthesized ``f**2``), and left-to-right order;
  ``20 * math.log10(...)`` is the float-widened ``20.0 * log10(...)``.
- **Branch parity:** ``A <= 0 || I <= 0 || f <= 0`` and
  ``e_uv_per_m <= 0`` are IEEE comparisons — false for NaN (NaN flows
  through to a NaN result, as in the reference); the ``e_uv_per_m <= 0``
  guard catches ``0.0`` (returns 0.0, not ``log10(0) = -inf``).

The direct ``temper_thermal`` pins fail first (the crate is not yet
built with the new function); the module-level pins exercise the full
delegation path once wired.
"""

from __future__ import annotations

import math
import random
import struct

import pytest
import temper_thermal as _tt

from temper_placer.physics.emi import check_emi_compliance, predict_radiated_emissions

# ---------------------------------------------------------------------------
# Oracle (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------
# Do not edit these — they are the reference the migration is pinned to.


def _oracle_predict_radiated_emissions(
    loop_area_mm2: float,
    current_peak_a: float,
    frequency_mhz: float,
    distance_m: float = 3.0,
) -> float:
    """Verbatim pre-migration radiated-emissions estimator (dBµV/m)."""
    if loop_area_mm2 <= 0 or current_peak_a <= 0 or frequency_mhz <= 0:
        return 0.0

    # Calculate field in V/m
    e_v_per_m = (1.316e-14 * loop_area_mm2 * current_peak_a * (frequency_mhz**2)) / distance_m

    # Convert to µV/m
    e_uv_per_m = e_v_per_m * 1e6

    # Convert to dBµV/m
    if e_uv_per_m <= 0:
        return 0.0

    return 20 * math.log10(e_uv_per_m)


def _oracle_check_emi_compliance(field_strength_dbuv: float, standard: str = "CISPR32_CLASS_B") -> bool:
    """Verbatim pre-migration CISPR compliance check."""
    limit = 40.0
    if standard == "CISPR32_CLASS_A":
        limit = 50.0
    return field_strength_dbuv <= limit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bits(x: float) -> str:
    """Bit pattern of an f64, for precise mismatch reporting."""
    return struct.pack(">d", x).hex()


def _random_emi_params(rng):
    """Random scalar inputs spanning realistic and adversarial magnitudes
    (including the `<= 0` guard arms and NaN)."""
    area = rng.choice([100.0, 1e-4, 0.0, -1.0, rng.uniform(1e-4, 1e4)])
    cur = rng.choice([10.0, 1e-3, 0.0, rng.uniform(1e-3, 1e3)])
    freq = rng.choice([1.0, 1e2, 0.0, rng.uniform(1e-3, 1e3)])
    dist = rng.choice([3.0, 1.0, 10.0, rng.uniform(0.1, 30.0)])
    return area, cur, freq, dist


# ---------------------------------------------------------------------------
# Direct kernel pins (bit-exact)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(20))
def test_direct_randomized_bit_exact(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(50):
        area, cur, freq, dist = _random_emi_params(rng)
        got = _tt.predict_radiated_emissions_py(area, cur, freq, dist)
        want = _oracle_predict_radiated_emissions(area, cur, freq, dist)
        assert _bits(got) == _bits(want), (
            f"emi seed={seed} A={area} I={cur} f={freq} d={dist}: "
            f"rust={got!r} ({_bits(got)}) oracle={want!r} ({_bits(want)})"
        )


def test_direct_known_value() -> None:
    # A=100 mm², I=10 A, f=1 MHz, d=3 m → e_v = 1.316e-14*100*10*1/3
    got = _tt.predict_radiated_emissions_py(100.0, 10.0, 1.0, 3.0)
    want = _oracle_predict_radiated_emissions(100.0, 10.0, 1.0, 3.0)
    assert _bits(got) == _bits(want)


def test_direct_pow_vs_mul_discriminator() -> None:
    # `f ** 2` must be libm pow, never f*f: find a value where they
    # differ and pin the oracle's choice.
    rng = random.Random(42)
    found = None
    for _ in range(200000):
        f = rng.uniform(-1e3, 1e3)
        if struct.pack(">d", f**2) != struct.pack(">d", f * f):
            found = f
            break
    assert found is not None, "failed to find a pow-vs-mul discriminator"
    got = _tt.predict_radiated_emissions_py(100.0, 10.0, found, 3.0)
    want = _oracle_predict_radiated_emissions(100.0, 10.0, found, 3.0)
    assert _bits(got) == _bits(want)


def test_direct_zero_guard_arms() -> None:
    for area, cur, freq in [(0.0, 1.0, 1.0), (1.0, 0.0, 1.0), (1.0, 1.0, 0.0), (-5.0, 1.0, 1.0)]:
        got = _tt.predict_radiated_emissions_py(area, cur, freq, 3.0)
        want = _oracle_predict_radiated_emissions(area, cur, freq, 3.0)
        assert _bits(got) == _bits(want) and got == 0.0


def test_direct_tiny_output_guards_zero() -> None:
    # e_uv_per_m rounds to 0.0 → both return 0.0, never log10(0) = -inf.
    # (1e-300-scale inputs: the field chain underflows through the
    # denormal band to exactly 0.0, exercising the B8 denormal path AND
    # the e_uv <= 0 guard in one case.)
    got = _tt.predict_radiated_emissions_py(1e-300, 1e-300, 1e-300, 30.0)
    want = _oracle_predict_radiated_emissions(1e-300, 1e-300, 1e-300, 30.0)
    assert _bits(got) == _bits(want) and got == 0.0


def test_direct_nan_inf_semantics() -> None:
    # NaN comparisons are false in IEEE, so NaN inputs flow through.
    for args in [
        (float("nan"), 1.0, 1.0, 3.0),
        (1.0, float("nan"), 1.0, 3.0),
        (1.0, 1.0, float("nan"), 3.0),
        (1.0, 1.0, 1.0, float("nan")),
        (float("inf"), 1.0, 1.0, 3.0),
        (1.0, 1.0, float("inf"), 3.0),
    ]:
        got = _tt.predict_radiated_emissions_py(*args)
        want = _oracle_predict_radiated_emissions(*args)
        assert _bits(got) == _bits(want), f"args={args} rust={got!r} oracle={want!r}"


def test_direct_denormal_band_bit_exact() -> None:
    # B8: the field chain lands in the denormal band but stays NON-zero
    # (e_uv ≈ 4.4e-312); default IEEE semantics must not flush it, and
    # log10 of the denormal must match bit-for-bit.
    got = _tt.predict_radiated_emissions_py(1e-100, 1e-100, 1e-51, 30.0)
    want = _oracle_predict_radiated_emissions(1e-100, 1e-100, 1e-51, 30.0)
    assert _bits(got) == _bits(want)
    assert got != 0.0 and not math.isinf(got)


def test_direct_compliance_limits() -> None:
    for db, std, want in [
        (39.9, "CISPR32_CLASS_B", True),
        (40.1, "CISPR32_CLASS_B", False),
        (49.9, "CISPR32_CLASS_A", True),
        (50.1, "CISPR32_CLASS_A", False),
        (45.0, "CISPR32_CLASS_B", False),
        (45.0, "CISPR32_CLASS_A", True),
        (41.0, "OTHER", False),
        (float("nan"), "CISPR32_CLASS_B", False),
    ]:
        got = _tt.check_emi_compliance_py(db, std)
        assert got is want, f"db={db} std={std}: got {got} want {want}"


def test_direct_compliance_randomized() -> None:
    rng = random.Random(7)
    for _ in range(500):
        db = rng.uniform(-200.0, 200.0)
        std = rng.choice(["CISPR32_CLASS_A", "CISPR32_CLASS_B", "OTHER", ""])
        got = _tt.check_emi_compliance_py(db, std)
        want = _oracle_check_emi_compliance(db, std)
        assert got is want, f"db={db} std={std}: got {got} want {want}"


# ---------------------------------------------------------------------------
# Module-level delegation pins
# ---------------------------------------------------------------------------


def test_module_delegation_defaults() -> None:
    # The module keeps the public signature with the default distance_m=3.0.
    got = predict_radiated_emissions(100.0, 10.0, 1.0)
    want = _oracle_predict_radiated_emissions(100.0, 10.0, 1.0)
    assert _bits(got) == _bits(want)


def test_module_delegation_known_path() -> None:
    rng = random.Random(11)
    for _ in range(50):
        area, cur, freq, dist = _random_emi_params(rng)
        got = predict_radiated_emissions(area, cur, freq, dist)
        want = _oracle_predict_radiated_emissions(area, cur, freq, dist)
        assert _bits(got) == _bits(want)


def test_module_compliance_delegation() -> None:
    assert check_emi_compliance(39.9) is _oracle_check_emi_compliance(39.9)
    assert check_emi_compliance(41.0, "CISPR32_CLASS_A") is _oracle_check_emi_compliance(41.0, "CISPR32_CLASS_A")
    assert check_emi_compliance(41.0, "CISPR32_CLASS_B") is _oracle_check_emi_compliance(41.0, "CISPR32_CLASS_B")
