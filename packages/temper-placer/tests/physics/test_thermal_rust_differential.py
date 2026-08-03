"""Differential tests: temper-thermal Rust junction-temperature kernel vs
the pure-Python reference (temper_placer/physics/thermal.py, Wave 4
Phase A #3 — the junction-temperature estimator).

The pre-migration implementation is pinned here as an oracle (verbatim
semantics, including the exact f64 operation order: the
``max(0.0, edge_distance_mm - 5.0) * 0.2`` edge penalty with the
constant as the FIRST ``max`` argument, the
``min(0.5, (copper_area_mm2 / 1000.0) * 0.1)`` copper benefit — division
then multiply then ``min`` with the constant first — the left-to-right
``Rjc + Rch + Rha_base + edge_penalty - copper_benefit`` resistance sum,
and the parenthesized ``ambient_C + (power_W * R_total)``).  Any change
to the Rust kernel (packages/temper-thermal/src/junction_temp.rs) or the
Python delegation that disagrees with the oracle fails here, bit-exactly.

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

from temper_placer.physics.thermal import estimate_junction_temp

# ---------------------------------------------------------------------------
# Oracle (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------
# Do not edit these — they are the reference the migration is pinned to.
# They are a copy of the module's arithmetic AS COMMITTED before the Rust
# kernel existed.


def _oracle_estimate_junction_temp(
    power_W,
    edge_distance_mm,
    copper_area_mm2=0.0,
    ambient_C=40.0,
    Rjc=0.6,
    Rch=0.25,
    Rha_base=1.0,
):
    """Verbatim scalar core of the pre-migration junction-temp model."""
    # 1. Edge Penalty
    # Effective Rha increases as component moves away from edge (mount point)
    # Heuristic: 0.2 K/W per mm beyond 5mm
    edge_penalty = max(0.0, edge_distance_mm - 5.0) * 0.2

    # 2. Copper Spreading Benefit
    # Larger copper pours help spread heat, reducing effective Rha
    # Heuristic: 0.1 K/W reduction per 1000mm², capped at 0.5 K/W
    copper_benefit = min(0.5, (copper_area_mm2 / 1000.0) * 0.1)

    # 3. Total Resistance
    R_total = Rjc + Rch + Rha_base + edge_penalty - copper_benefit

    # 4. Junction Temperature
    T_junction = ambient_C + (power_W * R_total)

    return float(T_junction)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bits(x: float) -> str:
    """Bit pattern of an f64, for precise mismatch reporting."""
    return struct.pack(">d", x).hex()


def _random_input(rng):
    """Random physically-meaningful inputs (plus a NaN arm for edge pins)."""
    power = rng.choice(
        [
            rng.uniform(0.0, 500.0),
            rng.choice([0.0, 0.5, 5.0, 15.0, 50.0, 250.0]),
        ]
    )
    edge = rng.uniform(-20.0, 60.0)
    copper = rng.uniform(0.0, 12000.0)
    ambient = rng.uniform(-40.0, 100.0)
    rjc = rng.uniform(0.0, 3.0)
    rch = rng.uniform(0.0, 2.0)
    rha = rng.uniform(0.0, 5.0)
    return power, edge, copper, ambient, rjc, rch, rha


# ---------------------------------------------------------------------------
# Direct Rust pins (bit-exact float equality)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(20))
def test_direct_kernel_bit_exact(seed):
    """Rust kernel == oracle, bit-exact, over randomized inputs."""
    rng = random.Random(seed)
    for _ in range(50):
        power, edge, copper, ambient, rjc, rch, rha = _random_input(rng)
        expected = _oracle_estimate_junction_temp(
            power, edge, copper, ambient, rjc, rch, rha
        )
        got = _tt.estimate_junction_temp_py(
            power, edge, copper, ambient, rjc, rch, rha
        )
        assert got == expected, (
            f"Tj mismatch on power={power!r} edge={edge!r} copper={copper!r} "
            f"ambient={ambient!r} Rjc={rjc!r} Rch={rch!r} Rha={rha!r}:\n"
            f"  rust   = {got!r}  ({_bits(got)})\n"
            f"  oracle = {expected!r}  ({_bits(expected)})"
        )


def test_direct_kernel_known_values():
    """Hand-computed values (exact f64 in both implementations).

    Mirrors the pre-existing test_thermal.py pins:
    Tj = 40 + 15 * (0.6 + 0.25 + 1.0) = 40 + 15 * 1.85 = 67.75
    """
    assert _tt.estimate_junction_temp_py(15.0, 5.0, 0.0, 40.0, 0.6, 0.25, 1.0) == 67.75
    # 5mm penalty: 15 * (1.85 + 1.0) → 82.75
    assert _tt.estimate_junction_temp_py(15.0, 10.0, 0.0, 40.0, 0.6, 0.25, 1.0) == 82.75
    # copper benefit 0.1: 40 + 15 * 1.75 → 66.25
    assert _tt.estimate_junction_temp_py(15.0, 5.0, 1000.0, 40.0, 0.6, 0.25, 1.0) == 66.25
    # 10mm penalty, 50W: 40 + 50 * 3.85 → 232.5
    assert _tt.estimate_junction_temp_py(50.0, 15.0, 0.0, 40.0, 0.6, 0.25, 1.0) == 232.5


def test_direct_edge_penalty_saturation():
    """edge_distance_mm <= 5.0 ⇒ penalty exactly 0.0 ⇒ Tj identical."""
    base = _tt.estimate_junction_temp_py(15.0, 5.0, 0.0, 40.0, 0.6, 0.25, 1.0)
    for edge in (-1e6, -1.0, 0.0, 2.5, 4.999, 5.0):
        assert (
            _tt.estimate_junction_temp_py(15.0, edge, 0.0, 40.0, 0.6, 0.25, 1.0)
            == base
        ), f"penalty not saturated at edge={edge!r}"


def test_direct_copper_benefit_saturation():
    """copper_area_mm2 >= 5000 ⇒ benefit exactly 0.5 ⇒ Tj identical."""
    base = _tt.estimate_junction_temp_py(15.0, 5.0, 5000.0, 40.0, 0.6, 0.25, 1.0)
    for copper in (5000.0, 5000.0001, 1e6, float("inf")):
        assert (
            _tt.estimate_junction_temp_py(15.0, 5.0, copper, 40.0, 0.6, 0.25, 1.0)
            == base
        ), f"benefit not saturated at copper={copper!r}"


def test_direct_nan_inf_semantics():
    """NaN/inf inputs take the same branches CPython takes.

    - max(0.0, NaN) == 0.0 (builtin max keeps the FIRST argument; the
      constant is first) → penalty 0.0.
    - min(0.5, NaN) == 0.5 (builtin min keeps the FIRST argument) →
      benefit 0.5.
    - inf edge distance → penalty inf → Tj == -inf + ambient... rather
      than guessing, pin against the oracle, which is the point.
    """
    cases = [
        # (power, edge, copper, ambient, Rjc, Rch, Rha)
        (15.0, float("nan"), 0.0, 40.0, 0.6, 0.25, 1.0),
        (15.0, 5.0, float("nan"), 40.0, 0.6, 0.25, 1.0),
        (float("nan"), 5.0, 0.0, 40.0, 0.6, 0.25, 1.0),
        (float("inf"), 5.0, 0.0, 40.0, 0.6, 0.25, 1.0),
        (15.0, float("inf"), 0.0, 40.0, 0.6, 0.25, 1.0),
        (15.0, -float("inf"), 0.0, 40.0, 0.6, 0.25, 1.0),
        (15.0, 5.0, float("inf"), 40.0, 0.6, 0.25, 1.0),
        (15.0, 5.0, 0.0, float("nan"), 0.6, 0.25, 1.0),
        (-15.0, 5.0, 0.0, 40.0, 0.6, 0.25, 1.0),
        (15.0, 5.0, 0.0, 40.0, float("nan"), 0.25, 1.0),
    ]
    for case in cases:
        expected = _oracle_estimate_junction_temp(*case)
        got = _tt.estimate_junction_temp_py(*case)
        assert got == expected or (math.isnan(got) and math.isnan(expected)), (
            f"NaN/inf mismatch on {case!r}: rust={got!r} oracle={expected!r}"
        )


def test_direct_nan_penalty_matches_py_max_first_arg():
    """max(0.0, NaN) keeps the constant: penalty must be exactly 0.0.

    This is the B5 catalog pin — Rust must replicate Python's
    first-argument NaN semantics (0.0.max(NaN)), not discard NaN the
    other way around.
    """
    got = _tt.estimate_junction_temp_py(15.0, float("nan"), 0.0, 40.0, 0.6, 0.25, 1.0)
    # edge_penalty = 0.0; R_total = 0.6+0.25+1.0+0.0-0.0 = 1.85;
    # Tj = 40.0 + 15.0*1.85 = 67.75
    assert got == 67.75


def test_direct_nan_copper_benefit_matches_py_min_first_arg():
    """min(0.5, NaN) keeps the constant: benefit must be exactly 0.5."""
    got = _tt.estimate_junction_temp_py(15.0, 5.0, float("nan"), 40.0, 0.6, 0.25, 1.0)
    # R_total = 1.85 - 0.5 = 1.35; Tj = 40.0 + 15.0*1.35 = 60.25
    assert got == 60.25


def test_direct_denormal_band_b8():
    """B8: denormal intermediates survive (no FTZ/DAZ/fast-math)."""
    rng = random.Random(0xB8)
    for _ in range(20):
        power = rng.choice([1e-310, 5e-310, 1e-315, 2.5e-309])
        expected = _oracle_estimate_junction_temp(
            power, 5.0, 0.0, 40.0, 0.6, 0.25, 1.0
        )
        got = _tt.estimate_junction_temp_py(
            power, 5.0, 0.0, 40.0, 0.6, 0.25, 1.0
        )
        assert got == expected, (
            f"denormal mismatch: rust={got!r} ({_bits(got)}) "
            f"oracle={expected!r} ({_bits(expected)})"
        )
    # The denormal product itself must be non-zero (i.e. actually in the
    # denormal band, proving the case exercises underflow handling).
    # R_total must be > 0 here (Rjc/Rch/Rha non-zero) — with an all-zero
    # resistance chain the product is 0.0 * 1e-310 == 0.0 and the case
    # degenerates to nothing.
    product = _oracle_estimate_junction_temp(
        1e-310, 5.0, 0.0, 0.0, 0.6, 0.25, 1.0
    )
    assert 0.0 < product < 2.2e-308


def test_direct_zero_power_is_ambient():
    """power_W == 0.0 ⇒ Tj == ambient, bit-exact (0.0 * R == 0.0)."""
    for ambient in (-40.0, 0.0, 25.0, 100.0):
        got = _tt.estimate_junction_temp_py(0.0, 25.0, 0.0, ambient, 0.6, 0.25, 1.0)
        assert got == ambient, f"zero-power Tj={got!r} != ambient={ambient!r}"


# ---------------------------------------------------------------------------
# Module-level pins (full delegation path)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_module_level_bit_exact(seed):
    """estimate_junction_temp (delegating) == oracle, default args too."""
    rng = random.Random(1000 + seed)
    for _ in range(25):
        power, edge, copper, ambient, rjc, rch, rha = _random_input(rng)
        expected = _oracle_estimate_junction_temp(
            power, edge, copper, ambient, rjc, rch, rha
        )
        got = estimate_junction_temp(
            power_W=power,
            edge_distance_mm=edge,
            copper_area_mm2=copper,
            ambient_C=ambient,
            Rjc=rjc,
            Rch=rch,
            Rha_base=rha,
        )
        assert got == expected, (
            f"module-level mismatch on power={power!r} edge={edge!r} "
            f"copper={copper!r} ambient={ambient!r}: rust={got!r} oracle={expected!r}"
        )


def test_module_level_defaults_bit_exact():
    """Default arguments (copper=0, ambient=40, Rjc=0.6, Rch=0.25,
    Rha=1.0) route through the kernel unchanged."""
    for power, edge in [(15.0, 5.0), (15.0, 10.0), (50.0, 15.0), (0.0, 3.0)]:
        expected = _oracle_estimate_junction_temp(power, edge)
        got = estimate_junction_temp(power_W=power, edge_distance_mm=edge)
        assert got == expected, f"defaults mismatch: {got!r} vs {expected!r}"


def test_module_level_custom_thermal_params():
    """Custom Rjc/Rch/Rha_base route through (thermal_potential.py call
    shape: ambient + Rjc only, defaults for the rest)."""
    expected = _oracle_estimate_junction_temp(
        12.0, 8.0, 0.0, 25.0, 0.9, 0.25, 1.0
    )
    got = estimate_junction_temp(
        power_W=12.0, edge_distance_mm=8.0, ambient_C=25.0, Rjc=0.9
    )
    assert got == expected
