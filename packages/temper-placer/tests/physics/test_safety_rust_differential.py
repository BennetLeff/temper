"""Differential tests: temper-thermal Rust safety-timing kernels vs the
pure-Python reference (temper_placer/physics/safety.py, Wave 4 Phase 4).

The pre-migration implementation is pinned here as an oracle (verbatim
semantics, including the exact f64 operation order:
``tau = r * c`` then ``(-tau) * log(1.0 - threshold)`` with the unary
minus bound before the multiply; ``(comparator_delay_ns +
mcu_latency_ns) * 1e-3`` with the parenthesized sum before the
multiply, then ``filter_delay_us + digital_delay_us``; the ``<=``
comparison of ``is_safety_timing_valid``).  Any change to the Rust
kernels (packages/temper-thermal/src/safety.rs) or the Python
delegation that disagrees with the oracle fails here, bit-exactly.

Bit-exactness notes (Wave 4 catalog):

- **B1 (host libm via dlsym):** ``math.log`` resolves to the host
  Python runtime's libm; the Rust kernel uses the same host libm via
  ``dlsym`` (``host_math``).
- **B7 (f64 operation order):** every chain keeps the oracle's exact op
  count, grouping, and left-to-right order — no reassociation, no
  fusing.
- **Branch parity:** the ``r <= 0 || c <= 0`` guard is IEEE — false for
  NaN (NaN flows through); ``is_safety_timing_valid`` is a plain IEEE
  ``<=``.

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

# The delegation shim temper_placer/physics/safety.py was deleted (pure
# delegation to temper_thermal; defaults lived in the shim signature). The
# module-level pins below now call the Rust kernels directly, passing the
# former shim defaults explicitly (0.632 / 150.0+200.0 / 10.0) so the
# default-path behavior is still pinned bit-exactly against the oracle.

# ---------------------------------------------------------------------------
# Oracle (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------


def _oracle_estimate_filter_delay(
    r_ohms: float,
    c_farads: float,
    threshold_fraction: float = 0.632,
) -> float:
    """Verbatim pre-migration RC filter delay estimator."""
    if r_ohms <= 0 or c_farads <= 0:
        return 0.0
    tau = r_ohms * c_farads
    return -tau * math.log(1.0 - threshold_fraction)


def _oracle_estimate_fault_response_time(
    _loop_inductance_nh: float,
    filter_delay_us: float,
    comparator_delay_ns: float = 150.0,
    mcu_latency_ns: float = 200.0,
) -> float:
    """Verbatim pre-migration interlock response-time estimator."""
    digital_delay_us = (comparator_delay_ns + mcu_latency_ns) * 1e-3
    return filter_delay_us + digital_delay_us


def _oracle_is_safety_timing_valid(response_time_us: float, max_limit_us: float = 10.0) -> bool:
    """Verbatim pre-migration safety-limit check."""
    return response_time_us <= max_limit_us


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bits(x: float) -> str:
    return struct.pack(">d", x).hex()


def _random_delay_params(rng):
    r = rng.choice([1e3, 1.0, 0.0, -1.0, rng.uniform(1e-6, 1e6)])
    c = rng.choice([1e-6, 1e-9, 0.0, rng.uniform(1e-12, 1e-3)])
    thr = rng.choice([0.632, 0.9, 0.5, rng.uniform(0.0, 0.999)])
    return r, c, thr


# ---------------------------------------------------------------------------
# Direct kernel pins (bit-exact)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(20))
def test_direct_randomized_bit_exact(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(50):
        r, c, thr = _random_delay_params(rng)
        got = _tt.estimate_filter_delay_py(r, c, thr)
        want = _oracle_estimate_filter_delay(r, c, thr)
        assert _bits(got) == _bits(want), (
            f"delay seed={seed} r={r} c={c} thr={thr}: "
            f"rust={got!r} ({_bits(got)}) oracle={want!r} ({_bits(want)})"
        )


def test_direct_one_time_constant() -> None:
    # threshold = 1 - 1/e → t = RC exactly (log(1/e) = -1).
    thr = 1.0 - 1.0 / math.e
    got = _tt.estimate_filter_delay_py(1000.0, 1e-6, thr)
    want = _oracle_estimate_filter_delay(1000.0, 1e-6, thr)
    assert _bits(got) == _bits(want)
    assert got == 1e-3


def test_direct_zero_guard_arms() -> None:
    for r, c in [(0.0, 1e-6), (1e3, 0.0), (-1.0, 1e-6), (1e3, -1e-9)]:
        got = _tt.estimate_filter_delay_py(r, c, 0.632)
        want = _oracle_estimate_filter_delay(r, c, 0.632)
        assert _bits(got) == _bits(want) and got == 0.0


def test_direct_nan_inf_semantics() -> None:
    for args in [
        (float("nan"), 1e-6, 0.632),
        (1e3, float("nan"), 0.632),
        (1e3, 1e-6, float("nan")),
        (float("inf"), 1e-6, 0.632),
    ]:
        got = _tt.estimate_filter_delay_py(*args)
        want = _oracle_estimate_filter_delay(*args)
        assert _bits(got) == _bits(want), f"args={args} rust={got!r} oracle={want!r}"


def test_direct_threshold_extremes() -> None:
    # threshold = 0 → log(1) = 0 → delay 0.  threshold >= 1.0 → CPython
    # math.log(1 - thr) hits the domain (x <= 0) and RAISES
    # ValueError("math domain error") — the Rust bridge must raise the
    # same error, and the guard order (r <= 0 returns 0.0 first) must
    # hold.  NaN threshold → math.log(NaN) = NaN, no raise.
    got = _tt.estimate_filter_delay_py(1000.0, 1e-6, 0.0)
    want = _oracle_estimate_filter_delay(1000.0, 1e-6, 0.0)
    assert _bits(got) == _bits(want)
    assert got == 0.0

    # Domain-error arms: 1 - thr <= 0 → CPython math.log raises; the
    # bridge must raise identically.  (thr = -0.0 does NOT raise:
    # 1.0 - (-0.0) = 1.0, a positive log argument.)
    for thr in (1.0, 1.0000001, 2.0):
        with pytest.raises(ValueError, match="math domain error"):
            _tt.estimate_filter_delay_py(1000.0, 1e-6, thr)
        with pytest.raises(ValueError, match="math domain error"):
            _oracle_estimate_filter_delay(1000.0, 1e-6, thr)
    # Guard-order parity: r <= 0 returns 0.0 WITHOUT raising even at
    # thr=1.0 (the log is never reached in the reference).
    got = _tt.estimate_filter_delay_py(0.0, 1e-6, 1.0)
    want = _oracle_estimate_filter_delay(0.0, 1e-6, 1.0)
    assert _bits(got) == _bits(want) and got == 0.0
    # NaN threshold flows through (log(NaN) = NaN, no raise).
    got = _tt.estimate_filter_delay_py(1000.0, 1e-6, float("nan"))
    want = _oracle_estimate_filter_delay(1000.0, 1e-6, float("nan"))
    assert _bits(got) == _bits(want)
    assert math.isnan(got)


def test_direct_fault_response_bit_exact() -> None:
    rng = random.Random(5)
    for _ in range(200):
        ind = rng.uniform(0.0, 100.0)
        fd = rng.choice([0.0, 2.5, rng.uniform(0.0, 100.0)])
        cd = rng.choice([150.0, 0.0, rng.uniform(0.0, 1000.0)])
        ml = rng.choice([200.0, 0.0, rng.uniform(0.0, 1000.0)])
        got = _tt.estimate_fault_response_time_py(ind, fd, cd, ml)
        want = _oracle_estimate_fault_response_time(ind, fd, cd, ml)
        assert _bits(got) == _bits(want), f"ind={ind} fd={fd} cd={cd} ml={ml}"


def test_direct_fault_response_known_value() -> None:
    got = _tt.estimate_fault_response_time_py(10.0, 2.5, 150.0, 200.0)
    assert _bits(got) == _bits(2.85)


def test_direct_safety_timing_valid() -> None:
    rng = random.Random(9)
    for _ in range(500):
        rt = rng.uniform(-10.0, 20.0)
        ml = rng.uniform(0.0, 15.0)
        got = _tt.is_safety_timing_valid_py(rt, ml)
        want = _oracle_is_safety_timing_valid(rt, ml)
        assert got is want, f"rt={rt} ml={ml}: got {got} want {want}"
    assert _tt.is_safety_timing_valid_py(float("nan"), 10.0) is False


# ---------------------------------------------------------------------------
# Module-level delegation pins
# ---------------------------------------------------------------------------


def test_module_delegation_defaults() -> None:
    got = _tt.estimate_filter_delay_py(1000.0, 1e-6, 0.632)
    want = _oracle_estimate_filter_delay(1000.0, 1e-6)
    assert _bits(got) == _bits(want)

    got = _tt.estimate_fault_response_time_py(10.0, 2.5, 150.0, 200.0)
    want = _oracle_estimate_fault_response_time(10.0, 2.5)
    assert _bits(got) == _bits(want)

    assert _tt.is_safety_timing_valid_py(10.0, 10.0) is _oracle_is_safety_timing_valid(10.0)
    assert _tt.is_safety_timing_valid_py(10.5, 10.0) is _oracle_is_safety_timing_valid(10.5)


def test_module_delegation_randomized() -> None:
    rng = random.Random(13)
    for _ in range(50):
        r, c, thr = _random_delay_params(rng)
        got = _tt.estimate_filter_delay_py(r, c, thr)
        want = _oracle_estimate_filter_delay(r, c, thr)
        assert _bits(got) == _bits(want)

    for _ in range(50):
        fd = rng.uniform(0.0, 100.0)
        got = _tt.estimate_fault_response_time_py(rng.uniform(0.0, 100.0), fd, 150.0, 200.0)
        want = _oracle_estimate_fault_response_time(rng.uniform(0.0, 100.0), fd)
        assert _bits(got) == _bits(want)
