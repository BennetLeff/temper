"""Differential tests: temper-thermal Rust parasitic-loop-inductance kernels
vs the pure-Python reference (temper_placer/physics/inductance.py, Wave 4
Phase A #4).

The pre-migration implementation is pinned here as an oracle (verbatim
semantics, including the exact f64 operation order: ``MU_0 = 4 * math.pi
* 1e-7`` as a three-op left-to-right chain, ``area_m2 = loop_area_mm2 *
1e-6``, ``h_m = layer_separation_mm * 1e-3``, the ``(MU_0 * area_m2 /
h_m) if h_m > 0 else 0`` conditional area term, ``L_area_H * 1e9``,
``perimeter_mm * 0.2``, and the final ``(L_area_nH * 0.5 + L_self_nH) *
routing_factor`` with the parenthesized sum evaluated before the
multiply; ``estimate_gate_inductance`` is the ``(a + b + 5.0) * 0.8``
left-to-right chain).  Any change to the Rust kernels
(packages/temper-thermal/src/inductance.rs) or the Python delegation that
disagrees with the oracle fails here, bit-exactly.

Bit-exactness notes (Wave 4 catalog):

- **B2 (math.pi family):** the oracle uses the NAMED constant
  ``math.pi`` (0x400921FB54442D18), which is the correctly-rounded
  53-bit double closest to pi — bit-identical to Rust's
  ``std::f64::consts::PI``.  The B2 pitfall (``PI / 2.0`` vs
  ``FRAC_PI_2``) does NOT arise here because no division of pi occurs;
  ``4 * math.pi * 1e-7`` is pinned bit-exactly below (direct pin
  ``test_direct_mu0_chain_bit_exact``).
- **B7 (f64 operation order):** every chain keeps the oracle's exact
  op count, grouping, and left-to-right order — no reassociation, no
  fusing (see the module docstring of ``inductance.rs``).
- **B8 (denormal underflow):** ``MU_0 * area_m2`` for a denormal-band
  loop area lands in the denormal range and must NOT be flushed to
  zero (default IEEE semantics on both sides); pinned by
  ``test_direct_denormal_band_bit_exact``.
- **Branch parity:** ``h_m > 0`` is the same IEEE comparison in both
  languages — false for 0.0, negative, and NaN, selecting the ``0``
  area term identically.

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

from temper_placer.physics.inductance import (
    estimate_gate_inductance,
    estimate_loop_inductance,
)

# ---------------------------------------------------------------------------
# Oracle (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------
# Do not edit these — they are the reference the migration is pinned to.
# They are a copy of the module's arithmetic AS COMMITTED before the Rust
# kernels existed.


def _oracle_estimate_loop_inductance(
    loop_area_mm2: float,
    perimeter_mm: float,
    layer_separation_mm: float = 0.4,
    routing_factor: float = 1.2,
) -> float:
    """Verbatim pre-migration parasitic loop inductance estimator (nH)."""
    MU_0 = 4 * math.pi * 1e-7  # H/m (Permeability of free space)

    # 1. Area-based term (Planar loop above ground plane)
    # L_area = μ₀ * Area / h
    area_m2 = loop_area_mm2 * 1e-6
    h_m = layer_separation_mm * 1e-3
    L_area_H = (MU_0 * area_m2 / h_m) if h_m > 0 else 0
    L_area_nH = L_area_H * 1e9

    # 2. Self-inductance of conductor (simplified)
    # L_self ≈ 0.2 nH/mm for typical PCB traces
    L_self_nH = perimeter_mm * 0.2

    # 3. Combined Model with Calibration
    # For small loops (gate drive), the self-inductance and return path dominate.
    # For large loops, the area-based term dominates.
    L_total_nH = (L_area_nH * 0.5 + L_self_nH) * routing_factor

    return float(L_total_nH)


def _oracle_estimate_gate_inductance(
    source_to_gate_dist_mm: float,
    return_dist_mm: float,
) -> float:
    """Verbatim pre-migration gate-drive loop inductance estimator (nH)."""
    # Assuming tight coupling (back-to-back or over ground plane)
    perimeter = source_to_gate_dist_mm + return_dist_mm + 5.0  # +5mm for internal
    # Rough rule of thumb: 0.8 nH/mm for PCB loops over ground plane
    return perimeter * 0.8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bits(x: float) -> str:
    """Bit pattern of an f64, for precise mismatch reporting."""
    return struct.pack(">d", x).hex()


def _random_loop_params(rng):
    """Random loop-geometry scalars spanning realistic and adversarial
    magnitudes (including the h <= 0 degenerate arm)."""
    area = rng.choice([100.0, 1e-6, rng.uniform(1e-6, 1e4)])
    perim = rng.choice([40.0, 1e-3, rng.uniform(1e-3, 500.0)])
    h = rng.choice([0.4, 0.0, -0.1, rng.uniform(1e-6, 3.0)])
    rf = rng.choice([1.2, 1.0, rng.uniform(0.5, 4.0)])
    return area, perim, h, rf


# ---------------------------------------------------------------------------
# Direct Rust pins (bit-exact float equality)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(25))
def test_direct_loop_inductance_bit_exact(seed):
    """Rust kernel == oracle, bit-exact, over random loop geometries
    (area term present, h == 0, h < 0, varied routing factors)."""
    rng = random.Random(seed)
    for _ in range(40):
        area, perim, h, rf = _random_loop_params(rng)
        expected = _oracle_estimate_loop_inductance(area, perim, h, rf)
        got = _tt.estimate_loop_inductance_py(area, perim, h, rf)
        assert got == expected, (
            f"L mismatch (area={area!r} perim={perim!r} h={h!r} rf={rf!r}): "
            f"rust={got!r} ({_bits(got)}) oracle={expected!r} ({_bits(expected)})"
        )


@pytest.mark.parametrize("seed", range(15))
def test_direct_gate_inductance_bit_exact(seed):
    """Rust gate-drive kernel == oracle, bit-exact, over random distances."""
    rng = random.Random(1000 + seed)
    for _ in range(40):
        a = rng.choice([10.0, 0.0, rng.uniform(0.0, 50.0)])
        b = rng.choice([10.0, 0.0, rng.uniform(0.0, 50.0)])
        expected = _oracle_estimate_gate_inductance(a, b)
        got = _tt.estimate_gate_inductance_py(a, b)
        assert got == expected, (
            f"gate L mismatch (a={a!r} b={b!r}): "
            f"rust={got!r} ({_bits(got)}) oracle={expected!r} ({_bits(expected)})"
        )


def test_direct_known_values():
    """Hand-computed values (exact f64 in both implementations)."""
    # 100 mm², 40 mm perimeter, 0.4 mm height: L_area = 314 nH
    # (μ₀·100e-6/0.4e-3 = 1.2566e-6·1e-4/4e-4 = 3.14e-7 H = 314 nH),
    # L_self = 8 nH → L_total = (157 + 8) * 1.2 = 198 nH.
    assert _tt.estimate_loop_inductance_py(100.0, 40.0, 0.4, 1.2) == pytest.approx(198.0, abs=0.1)
    # Gate drive: (10 + 10 + 5) * 0.8 = 20.0 exactly.
    assert _tt.estimate_gate_inductance_py(10.0, 10.0) == 20.0


def test_direct_mu0_chain_bit_exact():
    """The ``4 * math.pi * 1e-7`` chain is bit-identical to Rust's
    ``4.0 * PI * 1e-7`` (B2 note: the NAMED constant math.pi == Rust PI
    bit-for-bit; the B2 division pitfall does not arise).  Pin it so a
    future reassociation or a ``FRAC_PI_2``-style substitution cannot
    slip in undetected."""
    mu_0_py = 4 * math.pi * 1e-7
    # The Rust kernel's internal mu_0 is exercised through a full call:
    # with area = 1.0 mm², h = 1.0 mm, the area term equals
    # mu_0 * 1e-6 / 1e-3 * 1e9 = mu_0 * 1e6 (nH), and the L_total chain
    # is (that * 0.5 + 0.0) * 1.0.
    got = _tt.estimate_loop_inductance_py(1.0, 0.0, 1.0, 1.0)
    expected = (mu_0_py * 1e-6 / 1e-3 * 1e9 * 0.5) * 1.0
    assert got == expected, (
        f"mu_0 chain: rust={got!r} ({_bits(got)}) python={expected!r} ({_bits(expected)})"
    )
    # And the two constants themselves must be bit-identical doubles.
    import struct as _s

    assert _s.pack(">d", mu_0_py) == _s.pack(">d", 4.0 * math.pi * 1e-7)


def test_direct_denormal_band_bit_exact():
    """B8 (denormal underflow): a denormal-band loop area must NOT be
    flushed to zero.  area = 1e-300 mm² → area_m2 = 1e-306;
    mu_0 * area_m2 ≈ 1.26e-312, inside the f64 denormal band
    (min normal ≈ 2.2e-308).  With h = 1.0 mm the quotient and the
    *1e9 term stay tiny; both implementations must agree bit-for-bit."""
    area = 1e-300
    perim = 0.0
    expected = _oracle_estimate_loop_inductance(area, perim, 1.0, 1.0)
    got = _tt.estimate_loop_inductance_py(area, perim, 1.0, 1.0)
    assert got == expected, f"denormal band: rust={got!r} oracle={expected!r}"
    assert 0.0 < got < 1e-280, "expected a denormal-range result, not 0.0"


def test_direct_nan_inf_semantics():
    """Non-finite parity: NaN and inf inputs follow the same branch rules
    in both implementations (NaN comparisons are false; arithmetic with
    NaN/inf propagates)."""
    # NaN h_m selects the 0 area term in BOTH implementations.
    exp = _oracle_estimate_loop_inductance(100.0, 10.0, float("nan"), 1.2)
    got = _tt.estimate_loop_inductance_py(100.0, 10.0, float("nan"), 1.2)
    assert got == exp, f"nan h: rust={got!r} oracle={exp!r}"
    # -inf h_m also selects the 0 area term.
    exp = _oracle_estimate_loop_inductance(100.0, 10.0, float("-inf"), 1.2)
    got = _tt.estimate_loop_inductance_py(100.0, 10.0, float("-inf"), 1.2)
    assert got == exp, f"-inf h: rust={got!r} oracle={exp!r}"
    # +inf h_m: area term = mu_0 * area_m2 / inf = 0.0 (finite numerator).
    exp = _oracle_estimate_loop_inductance(100.0, 10.0, float("inf"), 1.2)
    got = _tt.estimate_loop_inductance_py(100.0, 10.0, float("inf"), 1.2)
    assert got == exp, f"+inf h: rust={got!r} oracle={exp!r}"
    # NaN area propagates into the area term (h > 0), NaN perim into L_self.
    exp = _oracle_estimate_loop_inductance(float("nan"), 10.0, 1.0, 1.2)
    got = _tt.estimate_loop_inductance_py(float("nan"), 10.0, 1.0, 1.2)
    assert math.isnan(exp) and math.isnan(got), f"nan area: rust={got!r} oracle={exp!r}"
    # Gate drive with NaN distance propagates identically.
    exp = _oracle_estimate_gate_inductance(float("nan"), 10.0)
    got = _tt.estimate_gate_inductance_py(float("nan"), 10.0)
    assert math.isnan(exp) and math.isnan(got), f"nan gate: rust={got!r} oracle={exp!r}"


def test_direct_zero_height_edge():
    """h_m == 0.0 exactly is the 0-area-term branch; a single epsilon-away
    value flips to the division (branch pin)."""
    exp_zero = _oracle_estimate_loop_inductance(100.0, 10.0, 0.0, 1.2)
    exp_eps = _oracle_estimate_loop_inductance(100.0, 10.0, 1e-300, 1.2)
    assert _tt.estimate_loop_inductance_py(100.0, 10.0, 0.0, 1.2) == exp_zero
    assert _tt.estimate_loop_inductance_py(100.0, 10.0, 1e-300, 1.2) == exp_eps
    assert exp_zero != exp_eps, "expected the branch flip to change the result"


# ---------------------------------------------------------------------------
# Module-level pins (full delegation path)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_module_level_loop_inductance_bit_exact(seed):
    """estimate_loop_inductance (delegating) == oracle, bit-exact."""
    rng = random.Random(2000 + seed)
    for _ in range(25):
        area, perim, h, rf = _random_loop_params(rng)
        expected = _oracle_estimate_loop_inductance(area, perim, h, rf)
        got = estimate_loop_inductance(
            loop_area_mm2=area,
            perimeter_mm=perim,
            layer_separation_mm=h,
            routing_factor=rf,
        )
        assert got == expected, (
            f"delegation mismatch (area={area!r} perim={perim!r} h={h!r} "
            f"rf={rf!r}): rust={got!r} oracle={expected!r}"
        )


@pytest.mark.parametrize("seed", range(5))
def test_module_level_gate_inductance_bit_exact(seed):
    """estimate_gate_inductance (delegating) == oracle, bit-exact."""
    rng = random.Random(3000 + seed)
    for _ in range(25):
        a = rng.uniform(0.0, 50.0)
        b = rng.uniform(0.0, 50.0)
        expected = _oracle_estimate_gate_inductance(a, b)
        got = estimate_gate_inductance(source_to_gate_dist_mm=a, return_dist_mm=b)
        assert got == expected, (
            f"gate delegation mismatch (a={a!r} b={b!r}): rust={got!r} oracle={expected!r}"
        )


def test_module_level_defaults_bit_exact():
    """Default-argument parity: the module's defaults (h=0.4, rf=1.2)
    flow through the delegation exactly."""
    expected = _oracle_estimate_loop_inductance(100.0, 40.0)
    got = estimate_loop_inductance(loop_area_mm2=100.0, perimeter_mm=40.0)
    assert got == expected, f"defaults: rust={got!r} oracle={expected!r}"
    assert got == pytest.approx(198.0, abs=0.1)
