"""Property-based + metamorphic tests for the migrated zone_geometry compute.

Wave 4, Phase 5, first slice (deterministic leaf stages). These properties
exercise the migrated
``temper_design_bundle_python.deterministic_stages.define_zone_layout`` /
``scale_zone_bounds`` (the delegation shim
``deterministic/stages/zone_geometry.py`` calls them); bit-identical parity
is asserted separately by ``test_zone_geometry_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Tiling: the four zones cover ``[0, w]`` contiguously in ``x`` with
  ``HV.x_min == 0`` and ``MCU.x_max == w``, and no overlap.
- P2. Fractions: HV/Power/Signal widths are exactly ``0.3w`` and MCU's is
  ``0.1w`` (the products are pinned bit-exactly by the differential).
- P3. Y-extent: every zone spans exactly ``(0, h)``.
- P4. Non-empty: for positive ``w`` the MCU zone has positive width
  (``0.9w < w``).
- P5. Bounds ratio scale: ``scale_zone_bounds`` with ratio
  ``(a, b, c, d)`` returns exactly ``(a*w, b*h, c*w, d*h)`` (the dict-branch
  math).

Three metamorphic relations (R1d):

- MR1. Power-of-two scale: ``define_zone_layout(2^n w, 2^n h)`` is
  ``2^n``-scaled, bit-exactly.
- MR2. X depends only on width: layouts with the same ``w`` but different
  ``h`` have identical ``x`` boundaries for every zone.
- MR3. Y depends only on height: layouts with the same ``h`` but different
  ``w`` have identical ``y`` extents for every zone.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

_RS = _tdb.deterministic_stages

_DIM = st.floats(min_value=1e-6, max_value=1e6, allow_nan=False, allow_infinity=False)


def _layout(w, h):
    return list(_RS.define_zone_layout(w, h))  # (name, xmin, ymin, xmax, ymax)


@given(_DIM, _DIM)
@settings(max_examples=100, deadline=None)
def test_p1_tiling(w, h):
    zones = _layout(w, h)
    assert [z[0] for z in zones] == ["HV", "Power", "Signal", "MCU"]
    assert zones[0][1] == 0.0
    assert zones[-1][3] == w
    for (_, _, _, a2, _), (_, a1, _, _, _) in zip(zones, zones[1:]):
        assert a2 == a1  # contiguous, no gap/overlap


@given(_DIM, _DIM)
@settings(max_examples=100, deadline=None)
def test_p2_fractions(w, h):
    zones = _layout(w, h)
    # The boundaries are the oracle's exact products (not differences).
    assert zones[0][3] == 0.3 * w
    assert zones[1][1] == 0.3 * w  # power_x_min = hv_x_max (reused value)
    assert zones[1][3] == 0.6 * w
    assert zones[2][1] == 0.6 * w  # signal_x_min = power_x_max
    assert zones[2][3] == 0.9 * w
    assert zones[3][1] == 0.9 * w  # mcu_x_min = signal_x_max
    assert zones[3][3] == w


@given(_DIM, _DIM)
@settings(max_examples=100, deadline=None)
def test_p3_y_extent(w, h):
    zones = _layout(w, h)
    for _, _, ymin, _, ymax in zones:
        assert ymin == 0.0
        assert ymax == h


@given(_DIM, _DIM)
@settings(max_examples=100, deadline=None)
def test_p4_nonempty(w, h):
    zones = _layout(w, h)
    assert zones[3][3] - zones[3][1] > 0.0  # 0.9w < w for w > 0


@given(_DIM, _DIM)
@settings(max_examples=100, deadline=None)
def test_p5_bounds_ratio_scale(w, h):
    a, b, c, d = 0.1, 0.2, 0.7, 0.8
    got = _RS.scale_zone_bounds("Z", a, b, c, d, w, h)
    assert got == (a * w, b * h, c * w, d * h)
    # Exact bit comparison through hex.
    assert got[0].hex() == (a * w).hex()
    assert got[1].hex() == (b * h).hex()
    assert got[2].hex() == (c * w).hex()
    assert got[3].hex() == (d * h).hex()


@given(_DIM, _DIM, st.integers(min_value=-8, max_value=8))
@settings(max_examples=100, deadline=None)
def test_mr1_pow2_scale(w, h, n):
    k = 2.0**n
    base = _layout(w, h)
    scaled = _layout(k * w, k * h)
    assert len(base) == len(scaled)
    for (name, x1, y1, x2, y2), (sname, sx1, sy1, sx2, sy2) in zip(base, scaled):
        assert name == sname
        # HV.x_min and every y_min are Python `int` 0 in both arms (the
        # oracle stores ((0, 0), ...)); float() hexifies them bit-exactly
        # (0 == 0.0 numerically, and (k * 0) is exactly 0.0).
        assert (
            float(sx1).hex() == (k * float(x1)).hex() and float(sx2).hex() == (k * float(x2)).hex()
        )
        assert (
            float(sy1).hex() == (k * float(y1)).hex() and float(sy2).hex() == (k * float(y2)).hex()
        )


@given(_DIM, _DIM, _DIM)
@settings(max_examples=100, deadline=None)
def test_mr2_x_depends_only_on_width(w, h1, h2):
    a = _layout(w, h1)
    b = _layout(w, h2)
    # Row layout is (name, xmin, ymin, xmax, ymax): compare the x pair
    # (positions 1 and 3); ymax (position 4) legitimately varies with h.
    for (_, x1a, _, x2a, _), (_, x1b, _, x2b, _) in zip(a, b):
        assert x1a == x1b and x2a == x2b


@given(_DIM, _DIM, _DIM)
@settings(max_examples=100, deadline=None)
def test_mr3_y_depends_only_on_height(w1, w2, h):
    a = _layout(w1, h)
    b = _layout(w2, h)
    for (_, _, y1a, _, y2a), (_, _, y1b, _, y2b) in zip(a, b):
        assert y1a == y1b and y2a == y2b
