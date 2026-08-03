"""Differential test: the sanctioned pure-Python KiCad rotation convention
(``temper_placer.geometry.kicad_transform``) vs. the separately-maintained
Rust implementation of the same formula
(``packages/temper-geometry/src/transform.rs``'s ``transform_pin_position``/
``transform_pin_positions``, bound to Python as
``temper_placer.geometry.transform.transform_pin_position``).

Why two implementations exist
-------------------------------
``kicad_transform``'s own module docstring explains the decision: crossing
the pyo3 FFI boundary for a two-line scalar rotation formula on every call
(courtyard vertices, pad offsets, silkscreen labels, ...) is not worth the
coupling a pure-Python implementation would otherwise avoid, and (at the
time both were written) nothing in production actually calls the Rust
entry point -- it exists for the ``temper_geometry`` crate's own
consumers, not this repo's KiCad I/O paths. Rather than let the two
formulas silently drift apart (exactly the failure mode that put the same
formula, once wrong, in 12 independent places), this file pins them
together: any change to either implementation that disagrees with the
other fails here, not in a downstream PCB one day.

``temper_geometry`` is an unconditional, non-optional dependency of
``temper_placer.geometry`` (imported at that package's module level, with
no try/except fallback) -- unlike the optional Rust accelerators this repo
also has (``temper_drc_rs``, ``temper_rust_router``), there is no
skip-if-missing story for this one; if it is not importable, essentially
this entire package fails to import, so no skip guard is needed here.
"""

from __future__ import annotations

import math
import random

import pytest

from temper_placer.geometry.kicad_transform import place_local_to_world, rotate_local_to_world
from temper_placer.geometry.transform import transform_pin_position, transform_pin_positions


def test_zero_rotation():
    assert transform_pin_position(3.0, -2.0, 10.0, 20.0, 0.0) == pytest.approx(
        place_local_to_world(3.0, -2.0, 10.0, 20.0, 0.0)
    )


@pytest.mark.parametrize("angle_deg", [0.0, 90.0, 180.0, 270.0, -90.0, 45.0, 137.0])
def test_matches_at_various_angles(angle_deg):
    angle_rad = math.radians(angle_deg)
    comp_x, comp_y = 12.5, -7.25
    for pin_x, pin_y in [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (3.7, -2.1), (-5.0, 5.0)]:
        rust = transform_pin_position(pin_x, pin_y, comp_x, comp_y, angle_rad)
        python = place_local_to_world(pin_x, pin_y, comp_x, comp_y, angle_rad)
        assert rust[0] == pytest.approx(python[0], abs=1e-9)
        assert rust[1] == pytest.approx(python[1], abs=1e-9)


# The solver's finite angle set (plan 011 U2): the differential must pin the
# two sanctioned copies over the EXHAUSTIVE set, not just spot angles --
# every (angle, offset) pair in the enumeration.
_FINITE_ANGLE_SET_DEG = (0.0, 90.0, 180.0, 270.0)
_EXHAUSTIVE_OFFSETS = ((0.5, 0.3), (2.0, -1.0), (5.0, 0.0), (3.7, -2.1), (-5.0, 5.0))


@pytest.mark.parametrize("angle_deg", _FINITE_ANGLE_SET_DEG)
@pytest.mark.parametrize("offset", _EXHAUSTIVE_OFFSETS)
def test_matches_over_exhaustive_finite_angle_set(angle_deg, offset):
    """Python ``kicad_transform`` and Rust ``transform_pin_position`` agree
    for every (angle, offset) pair in the exhaustive enumeration of the
    solver's finite angle set {0, 90, 180, 270} x the offset set. A sign
    flip in either implementation fails here (the anchor values at 90/270
    with asymmetric offsets differ between R(-theta) and R(+theta))."""
    angle_rad = math.radians(angle_deg)
    comp_x, comp_y = 12.5, -7.25
    pin_x, pin_y = offset
    rust = transform_pin_position(pin_x, pin_y, comp_x, comp_y, angle_rad)
    python = place_local_to_world(pin_x, pin_y, comp_x, comp_y, angle_rad)
    assert rust[0] == pytest.approx(python[0], abs=1e-9), (angle_deg, offset)
    assert rust[1] == pytest.approx(python[1], abs=1e-9), (angle_deg, offset)


@pytest.mark.parametrize("angle_deg", _FINITE_ANGLE_SET_DEG)
def test_batch_matches_over_exhaustive_finite_angle_set(angle_deg):
    """The batch form (``transform_pin_positions``) agrees with Python over
    the same exhaustive enumeration."""
    angle_rad = math.radians(angle_deg)
    comp_x, comp_y = 12.5, -7.25
    pins = list(_EXHAUSTIVE_OFFSETS)
    flat = [c for p in pins for c in p]
    rust_flat = transform_pin_positions(flat, comp_x, comp_y, angle_rad)
    for i, (pin_x, pin_y) in enumerate(pins):
        python = place_local_to_world(pin_x, pin_y, comp_x, comp_y, angle_rad)
        assert rust_flat[2 * i] == pytest.approx(python[0], abs=1e-9), (angle_deg, (pin_x, pin_y))
        assert rust_flat[2 * i + 1] == pytest.approx(python[1], abs=1e-9), (
            angle_deg,
            (pin_x, pin_y),
        )


def test_matches_batch():
    comp_x, comp_y = 0.0, 0.0
    angle_rad = math.radians(37.0)
    pins = [(1.0, 0.0), (0.0, 1.0), (-3.0, 4.0), (2.5, -6.5)]
    flat = [c for p in pins for c in p]
    rust_flat = transform_pin_positions(flat, comp_x, comp_y, angle_rad)
    for i, (px, py) in enumerate(pins):
        python = place_local_to_world(px, py, comp_x, comp_y, angle_rad)
        assert rust_flat[2 * i] == pytest.approx(python[0], abs=1e-9)
        assert rust_flat[2 * i + 1] == pytest.approx(python[1], abs=1e-9)


@pytest.mark.parametrize("seed", range(20))
def test_random_property(seed):
    rng = random.Random(seed * 7919 + 1)
    angle_rad = rng.uniform(-4 * math.pi, 4 * math.pi)
    px, py = rng.uniform(-50, 50), rng.uniform(-50, 50)
    cx, cy = rng.uniform(-200, 200), rng.uniform(-200, 200)

    rust = transform_pin_position(px, py, cx, cy, angle_rad)
    python_rx, python_ry = rotate_local_to_world(px, py, angle_rad)
    python = (cx + python_rx, cy + python_ry)

    assert rust[0] == pytest.approx(python[0], abs=1e-9)
    assert rust[1] == pytest.approx(python[1], abs=1e-9)
