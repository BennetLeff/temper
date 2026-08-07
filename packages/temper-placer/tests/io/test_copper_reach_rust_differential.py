"""Differential: `_copper_reach_mm` oracle vs the temper_geometry kernel.

The NaN cases are the point of this suite. The reference is CPython's builtin
`max()`, which keeps the FIRST NaN and lets nothing displace it; `f64::max`
discards NaN and would report a finite reach for a component whose pad offset
is unparseable. That difference is reachable from real boards, not theoretical,
so it is pinned here rather than left to a property test to stumble on.
"""

from __future__ import annotations

import math

import pytest
from temper_placer.core.pad_geometry import shape_code
from temper_placer.io import real_board as shipped

from tests.io import _copper_reach_py_oracle as oracle

pytest.importorskip("temper_geometry")
import temper_geometry as _tg  # noqa: E402


def _wire(pads):
    """The kernel's row contract: (ox, oy, w, h, shape_code, roundrect_ratio)."""
    return [
        (
            p["offset"][0],
            p["offset"][1],
            p["width"],
            p["height"],
            shape_code(p["shape"]),
            p["roundrect_ratio"],
        )
        for p in pads
    ]


def _pad(ox, oy, w=1.0, h=2.0, shape="rect", ratio=0.25):
    return {
        "offset": (ox, oy),
        "width": w,
        "height": h,
        "shape": shape,
        "roundrect_ratio": ratio,
    }


CASES = {
    "empty": [],
    "single_at_origin": [_pad(0.0, 0.0)],
    "single_offset": [_pad(3.0, 4.0)],
    "two_pads_second_further": [_pad(1.0, 0.0), _pad(10.0, 0.0)],
    "two_pads_first_further": [_pad(10.0, 0.0), _pad(1.0, 0.0)],
    "negative_offsets": [_pad(-3.0, -4.0)],
    "circle_shape": [_pad(1.0, 1.0, shape="circle")],
    "oval_shape": [_pad(1.0, 1.0, shape="oval")],
    "roundrect_shape": [_pad(1.0, 1.0, shape="roundrect", ratio=0.4)],
    "unknown_shape_falls_back": [_pad(1.0, 1.0, shape="not-a-shape")],
    "zero_size_pad": [_pad(2.0, 0.0, w=0.0, h=0.0)],
    "tie_between_pads": [_pad(3.0, 4.0), _pad(4.0, 3.0)],
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_matches_oracle(name):
    pads = CASES[name]
    assert _tg.copper_reach_mm_py(_wire(pads)) == oracle.copper_reach_mm(pads, 0.0)


def test_nan_offset_is_kept_not_discarded():
    """CPython `max` keeps the first NaN; `f64::max` would discard it."""
    pads = [_pad(math.nan, 0.0), _pad(10.0, 0.0)]
    want = oracle.copper_reach_mm(pads, 0.0)
    got = _tg.copper_reach_mm_py(_wire(pads))
    assert math.isnan(want), "oracle should produce NaN here"
    assert math.isnan(got), "kernel discarded a NaN CPython's max would keep"


def test_nan_arriving_second_does_not_displace_a_finite_max():
    """A NaN AFTER the running max loses the `>` test, in both languages."""
    pads = [_pad(10.0, 0.0), _pad(math.nan, 0.0)]
    want = oracle.copper_reach_mm(pads, 0.0)
    got = _tg.copper_reach_mm_py(_wire(pads))
    assert (math.isnan(want) and math.isnan(got)) or want == got


def test_infinity_beats_nan():
    """py_hypot returns inf as soon as a coordinate is infinite, even with NaN."""
    pads = [_pad(math.inf, math.nan)]
    assert _tg.copper_reach_mm_py(_wire(pads)) == oracle.copper_reach_mm(pads, 0.0)


def test_shipped_module_delegates_to_rust():
    """The SHIPPED entry point must reach Rust, not just the differential.

    A green differential compares the oracle against the kernel and passes
    whether or not production delegates -- this is the assertion that catches
    the RUST-EXISTS-UNWIRED state.
    """
    pads = [_pad(3.0, 4.0)]
    sentinel = RuntimeError("REACHED_RUST")

    def boom(*_a, **_k):
        raise sentinel

    original = _tg.copper_reach_mm_py
    _tg.copper_reach_mm_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST"):
            shipped._copper_reach_mm(pads, 0.0)
    finally:
        _tg.copper_reach_mm_py = original
