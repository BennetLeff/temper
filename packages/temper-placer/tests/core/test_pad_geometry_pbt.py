"""Property-based tests for the Rust pad-geometry core (Wave 2).

Five invariants (per the migration roadmap's R6 gate):

1. support_radius never under-reports the corner disk: r >= corner_radius
2. The isotropic bound is an upper bound: bounding_radius >=
   support_radius for ANY query direction (the load-bearing safety
   property the router's hot paths rely on)
3. support_radius is 2pi-periodic in rotation
4. support_radius is mirror-symmetric: r(direction) == r(-direction)
5. axis_radius never exceeds bounding_radius (axis extents stay inside
   the circumscribed disk)

The properties exercise the wrapper
(``temper_placer.core.pad_geometry``), the consumer surface the
isolation-barrier encoder and the keepout gates see.
"""

from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.pad_geometry import (
    pad_axis_radius,
    pad_bounding_radius,
    pad_corner_radius,
    pad_support_radius,
)

MAX_EXAMPLES = 150

_dim = st.floats(min_value=0.05, max_value=10.0, allow_nan=False, allow_infinity=False)
_angle = st.floats(
    min_value=-8 * math.pi, max_value=8 * math.pi, allow_nan=False, allow_infinity=False
)
_shape = st.sampled_from(["circle", "oval", "rect", "roundrect", "thru_hole"])
_ratio = st.floats(min_value=0.05, max_value=0.45, allow_nan=False, allow_infinity=False)


@given(_dim, _dim, _shape, _angle, _angle, _ratio)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_support_radius_never_under_reports_corner(
    w: float, h: float, shape: str, direction: float, rotation: float, ratio: float
) -> None:
    r = pad_corner_radius(w, h, shape, ratio)
    s = pad_support_radius(w, h, shape, direction, rotation, ratio)
    assert s >= r - 1e-12


@given(_dim, _dim, _shape, _angle, _angle, _ratio)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_bounding_radius_is_an_upper_bound(
    w: float, h: float, shape: str, direction: float, rotation: float, ratio: float
) -> None:
    b = pad_bounding_radius(w, h, shape, ratio)
    s = pad_support_radius(w, h, shape, direction, rotation, ratio)
    assert b >= s - 1e-12, f"bounding {b} < support {s}"


@given(_dim, _dim, _shape, _angle, _angle, _ratio)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_support_radius_periodic_in_rotation(
    w: float, h: float, shape: str, direction: float, rotation: float, ratio: float
) -> None:
    a = pad_support_radius(w, h, shape, direction, rotation, ratio)
    b = pad_support_radius(w, h, shape, direction, rotation + 2 * math.pi, ratio)
    # 2*pi is not representable, so rotation + 2*pi rounds differently and
    # cos/sin differ in the last ulp — assert closeness, not bit equality.
    assert abs(a - b) <= 1e-12 * max(1.0, abs(a))


@given(_dim, _dim, _shape, _angle, _angle, _ratio)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_support_radius_mirror_symmetric(
    w: float, h: float, shape: str, direction: float, rotation: float, ratio: float
) -> None:
    a = pad_support_radius(w, h, shape, direction, rotation, ratio)
    b = pad_support_radius(w, h, shape, -direction, -rotation, ratio)
    assert a == b


@given(_dim, _dim, _shape, _angle, _ratio)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_axis_radius_within_bounding_radius(
    w: float, h: float, shape: str, rotation: float, ratio: float
) -> None:
    b = pad_bounding_radius(w, h, shape, ratio)
    for axis in (0, 1):
        a = pad_axis_radius(w, h, shape, axis, rotation, ratio)
        assert b >= a - 1e-12, f"axis {axis} radius {a} > bounding {b}"
