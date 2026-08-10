"""Differential tests: ``temper-geometry`` mm/mil/inch kernels vs the pinned
reference.

Wave 4 Phase A (plan ``docs/plans/2026-08-09-001-feat-rust-orchestration-engine-plan.md``,
``core/units.py`` row: ``Mm``, ``Mil``, ``Inch`` newtype wrappers over f64).

The six length-unit conversion kernels migrate to
``packages/temper-geometry/src/units.rs`` and are pinned here bit-for-bit
against the reference expressions below.

**Why "reference", not "pre-migration":** these kernels are NEW — nothing in
the Python tree converts mil/inch↔mm at runtime today (the existing
``core/units.py`` conversions are already Rust-backed via ``temper-io-types``
and are pinned by the ``tests/wave4_phase2`` suite). The conversion factors
are not invented: they are the same IEEE-754 doubles the repo's mil/inch
parser already pins (``packages/temper-design-bundle/src/pcl_parse.rs``:
``number * 0.0254`` for mil→mm, ``number * 25.4`` for in→cm — bit patterns
pinned in that module's unit tests). The oracle below is the verbatim
reference expression each kernel must reproduce — a single rounding op, no
reassociation, no ``x * 40.0``-style shortcut (bit-exactness catalog B7).

All comparisons use ``float.hex()`` bit-identity, which distinguishes
``-0.0``/``+0.0`` and collapses both NaNs to the string ``'nan'`` (payload
independent).

The kernels under test are reached directly as ``temper_geometry.<name>``,
the crate's established differential pattern.
"""

from __future__ import annotations

import math
import random

import pytest

import temper_geometry as _tg

# ---------------------------------------------------------------------------
# Verbatim reference oracles — do not edit, they are the reference. Each
# oracle is the exact expression the kernel must reproduce bit-for-bit.
# ---------------------------------------------------------------------------

# The exact IEEE-754 doubles the repo's mil/inch parser pins
# (packages/temper-design-bundle/src/pcl_parse.rs): 0x1.a027525460aa6p-6 and
# 0x1.9666666666666p+4.
_MIL_TO_MM = 0.0254
_IN_TO_MM = 25.4


def _oracle_mil_to_mm(mil):
    """Reference: ``mil * 0.0254``."""
    return mil * _MIL_TO_MM


def _oracle_mm_to_mil(mm):
    """Reference: ``mm / 0.0254``."""
    return mm / _MIL_TO_MM


def _oracle_inch_to_mm(inch):
    """Reference: ``inch * 25.4``."""
    return inch * _IN_TO_MM


def _oracle_mm_to_inch(mm):
    """Reference: ``mm / 25.4``."""
    return mm / _IN_TO_MM


def _oracle_mil_to_inch(mil):
    """Reference: ``mil / 1000.0``."""
    return mil / 1000.0


def _oracle_inch_to_mil(inch):
    """Reference: ``inch * 1000.0``."""
    return inch * 1000.0


_KERNEL_NAMES = (
    "mil_to_mm",
    "mm_to_mil",
    "inch_to_mm",
    "mm_to_inch",
    "mil_to_inch",
    "inch_to_mil",
)

_ORACLES = {name: globals()[f"_oracle_{name}"] for name in _KERNEL_NAMES}


def _hex(value: float) -> str:
    return float(value).hex()


# ---------------------------------------------------------------------------
# Input corpus: crafted edge cases + randomized bit patterns spanning the
# whole representable f64 range (including the denormal band, B8).
# ---------------------------------------------------------------------------

_EDGES = [
    0.0,
    -0.0,
    1.0,
    -1.0,
    0.0254,  # 1 mil
    -0.0254,
    25.4,  # 1 inch
    -25.4,
    0.127,  # 5 mil
    2.54,  # 100 mil / 0.1 in
    1000.0,  # 1000 mil == 1 in
    -1000.0,
    0.1,
    0.2,
    0.3,
    -0.1,
    123.456,
    -9876.54321,
    3.141592653589793,
    1e-6,
    -1e-6,
    1e6,
    1e12,
    -1e12,
    1e-12,
    1e-300,
    1e300,
    1e-310,  # subnormal
    5.0e-324,  # smallest subnormal
    2.2250738585072014e-308,  # smallest normal
    1.7976931348623157e308,  # largest finite
    float("inf"),
    float("-inf"),
    float("nan"),
]


def _bit_pattern_values(n: int = 1500, seed: int = 0xBEEF):
    """Random values across the full exponent range, mantissa uniform in
    [1, 2). Covers normals and the subnormal band; underflow yields 0.0,
    which is a legitimate input too."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        mantissa = rng.uniform(1.0, 2.0)
        exp = rng.randint(-1074, 1023)
        value = math.ldexp(mantissa, exp)
        if rng.random() < 0.5:
            value = -value
        out.append(value)
    return out


# ---------------------------------------------------------------------------
# Differential assertions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", _KERNEL_NAMES)
@pytest.mark.parametrize("value", _EDGES)
def test_edge_bit_identical(name: str, value: float) -> None:
    got = getattr(_tg, name)(value)
    want = _ORACLES[name](value)
    assert _hex(got) == _hex(want), (
        f"{name}({value!r}): rust {got!r} ({_hex(got)}) "
        f"vs oracle {want!r} ({_hex(want)})"
    )


@pytest.mark.parametrize("name", _KERNEL_NAMES)
def test_random_sweep_bit_identical(name: str) -> None:
    oracle = _ORACLES[name]
    for value in _bit_pattern_values():
        got = getattr(_tg, name)(value)
        want = oracle(value)
        assert _hex(got) == _hex(want), (
            f"{name}({value!r}): rust {got!r} ({_hex(got)}) "
            f"vs oracle {want!r} ({_hex(want)})"
        )


def test_anchor_equivalences() -> None:
    """The canonical mil/inch identities, asserted exactly."""
    assert _tg.mil_to_mm(5.0) == 0.127  # 5 mil == 0.127 mm
    assert _tg.inch_to_mm(0.1) == 2.54  # 0.1 in == 2.54 mm
    assert _tg.mil_to_inch(1000.0) == 1.0  # 1000 mil == 1 in
    assert _tg.mm_to_inch(25.4) == 1.0  # 25.4 mm == 1 in
    assert _tg.inch_to_mm(1.0) == 25.4
    assert _tg.mm_to_mil(25.4) == 1000.0


def test_factor_bit_patterns_pinned() -> None:
    """The conversion factors are the exact doubles pcl_parse.rs pins."""
    assert (0.0254).hex() == "0x1.a027525460aa6p-6"
    assert (25.4).hex() == "0x1.9666666666666p+4"


def test_oracle_discriminates_wrong_scale() -> None:
    """Vacuity guard: the oracle is not trivially satisfied. The natural
    shortcut ``mm * 40.0`` for mm→mil is NOT the reference ``mm / 0.0254``
    — every randomized sample disagrees, so a kernel built on the shortcut
    would fail the differential."""
    disagreements = sum(
        1 for v in _bit_pattern_values(n=1000) if (v * 40.0) != (v / 0.0254)
    )
    assert disagreements > 0
    assert getattr(_tg, "mm_to_mil")(1.0) == _ORACLES["mm_to_mil"](1.0)
