"""Differential oracle tests: pin_geometry.py.

Wave 4 fan-out — the Python orchestration surface of
``temper_placer/core/pin_geometry.py`` migrated to pyfunctions in
``temper-geometry`` (home crate: ``packages/temper-geometry``).
The arithmetic kernels were already migrated in the ``core_graph_cluster``
unit (see ``test_core_graph_cluster_rust_differential.py``); this migration
moves the remaining Python orchestration (attribute access, None-handling,
shim logic) to Rust pyfunctions, leaving ``pin_geometry.py`` a pure-
delegation shim.

G1 (TDD): the oracle blocks below are verbatim copies of the pre-migration
implementation (origin/main, before this migration) — DO NOT EDIT, they are
the reference. The production imports are the delegation shim; after the
migration they call the Rust pyfunctions, and every assertion drives
IDENTICAL inputs through both sides.

Comparison conventions:
- scalar floats compared via ``float.hex()`` — bit-exact;
- point tuples compared coordinate-by-coordinate via ``float.hex()``.

Gates G1–G8 as applicable (see ``docs/wave4-discipline-contract.md`` §1):
- G1 (TDD): this file is written before the Rust pyfunctions (red → green).
- G2 (Behavioral A/B): bit-exact parity on randomized + edge-case inputs.
- G3 (Performance A/B): N/A — pure-delegation shim, no hot compute.
- G4–G8: assessed in the verification unit documentation.
"""

from __future__ import annotations

import math
import random

import pytest

# ============================================================================
# Oracle block — verbatim copy of `temper_placer/core/pin_geometry.py`
# (origin/main, pre-migration). DO NOT EDIT — these are the reference
# implementations.
# ============================================================================

import temper_geometry as _tg


def _oracle_normalize_rotation(rotation):
    """Normalize a rotation value to radians.

    int values are treated as rotation indices (0-3 -> 0/90/180/270 deg),
    matching the convention used by Component.initial_rotation.
    float values are treated as radians and used as-is.
    None is treated as 0 (no rotation).
    """
    if rotation is None:
        return 0.0
    if isinstance(rotation, int):
        return _tg.normalize_rotation_index_py(rotation)
    return float(rotation)


def _oracle_pin_world_position_at(pin, comp, pos_override=None, rotation_override=None):
    """Return the world (x, y) position of a pin, with optional overrides.

    Like :func:`pin_world_position` but accepts an explicit `pos_override`
    for the component's board position and/or `rotation_override` for the
    component's rotation index (0-3). When an override is provided, it
    replaces the corresponding ``comp.initial_*`` attribute.
    When None, falls back to ``comp.initial_*``.

    This is the canonical implementation; `pin_world_position` delegates to it.

    Args:
        pin: The pin whose world position to compute.
        comp: The component the pin belongs to.
        pos_override: Optional (x, y) tuple overriding the component position.
            When None, uses ``comp.initial_position``.
        rotation_override: Optional rotation index (0-3) overriding
            ``comp.initial_rotation``. When None, uses ``comp.initial_rotation``.

    Returns:
        (x, y) tuple in mm, in board coordinates.
    """
    rot_source = rotation_override if rotation_override is not None else comp.initial_rotation
    rotation_rad = _oracle_normalize_rotation(rot_source)
    side = comp.initial_side or 0

    px, py = pin.position

    # Add component position (use override if provided)
    cpos = pos_override if pos_override is not None else comp.initial_position or (0.0, 0.0)

    # Rust kernel: mirror X if bottom side (KiCad behavior), then rotate with
    # KiCad's R(-theta) convention, then translate. Mirror + rotation + the
    # additions all happen inside the kernel in the oracle's exact order.
    return _tg.pin_world_position_kernel_py(
        px, py, side, rotation_rad, cpos[0], cpos[1]
    )


def _oracle_pin_world_layer(pin):
    """Return the layer a pin lives on.

    Returns `pin.layer` if set, otherwise `"F.Cu"` (the default for
    surface-mount pads on the top layer).
    """
    return getattr(pin, "layer", None) or "F.Cu"


def _oracle_pin_world_radius(pin):
    """Return the effective pad radius for a pin -- a fast, rotation-invariant
    conservative bound for the router's hot paths (A* grid cell sizing,
    congestion, obstacle-map fallback, escape-via clearance), NOT a
    shape-agnostic circle.
    """
    from temper_placer.core.pad_geometry import DEFAULT_ROUNDRECT_RATIO, pad_bounding_radius

    w = getattr(pin, "width", 0.0) or 0.0
    h = getattr(pin, "height", 0.0) or 0.0
    if w == 0.0 and h == 0.0:
        return 0.5
    shape = getattr(pin, "shape", None) or "rect"
    ratio = getattr(pin, "roundrect_ratio", None) or DEFAULT_ROUNDRECT_RATIO
    return pad_bounding_radius(w, h, shape, ratio)


# ============================================================================
# Production imports (the delegation shim — after migration, these call the
# Rust pyfunctions)
# ============================================================================

from temper_placer.core.pin_geometry import (  # noqa: E402
    _normalize_rotation,
    pin_world_position,
    pin_world_position_at,
    pin_world_layer,
    pin_world_radius,
)


# ============================================================================
# Bit-exact comparison helpers
# ============================================================================


def _assert_float_bit_exact(a, b):
    assert float(a).hex() == float(b).hex(), f"{a!r} != {b!r}"


def _assert_point_bit_exact(pa, pb):
    _assert_float_bit_exact(pa[0], pb[0])
    _assert_float_bit_exact(pa[1], pb[1])


# ============================================================================
# Test fixtures
# ============================================================================


class _PinStub:
    """Minimal pin duck-type for the functions that read pin attributes."""

    def __init__(self, position, *, layer=None, width=0.0, height=0.0,
                 shape="rect", roundrect_ratio=None):
        self.position = position
        self.layer = layer
        self.width = width
        self.height = height
        self.shape = shape
        self.roundrect_ratio = roundrect_ratio


class _CompStub:
    """Minimal component duck-type for the functions that read comp attributes."""

    def __init__(self, initial_position=None, initial_rotation=None, initial_side=None):
        self.initial_position = initial_position
        self.initial_rotation = initial_rotation
        self.initial_side = initial_side


def _random_pin_geometry(rng):
    """Generate random pin/component/override configuration."""
    pos = (round(rng.uniform(-10.0, 10.0), 6), round(rng.uniform(-10.0, 10.0), 6))
    pin = _PinStub(
        pos,
        layer=rng.choice([None, "F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]),
        width=round(rng.uniform(0.0, 5.0), 6),
        height=round(rng.uniform(0.0, 5.0), 6),
        shape=rng.choice(["rect", "round", "oval", "custom"]),
        roundrect_ratio=(round(rng.uniform(0.0, 1.0), 6)
                         if rng.random() < 0.3 else None),
    )
    cpos = (round(rng.uniform(-50.0, 50.0), 6), round(rng.uniform(-50.0, 50.0), 6))
    comp = _CompStub(
        initial_position=None if rng.random() < 0.2 else cpos,
        initial_rotation=rng.choice([None, 0, 1, 2, 3]),
        initial_side=rng.choice([None, 0, 1]),
    )
    rot_override = rng.choice([None, 0, 1, 2, 3])
    # float rotation source (radians, per _normalize_rotation)
    float_rot = rng.choice([None, None, round(rng.uniform(-6.0, 6.0), 6)])
    pos_override = (
        None if rng.random() < 0.4
        else (round(rng.uniform(-50.0, 50.0), 6), round(rng.uniform(-50.0, 50.0), 6))
    )
    return pin, comp, rot_override, pos_override, float_rot


# ============================================================================
# _normalize_rotation
# ============================================================================


def test_normalize_rotation_bit_exact_edges():
    """Edge cases: None, int 0-3, negative int, out-of-range int, float, nan, inf."""
    for value in [None, 0, 1, 2, 3, -1, 7, 0.0, 1.5, math.pi, -2.75,
                  float("inf"), float("nan"), float("-inf")]:
        got = _normalize_rotation(value)
        want = _oracle_normalize_rotation(value)
        if isinstance(value, float) and math.isnan(value):
            assert math.isnan(got) and math.isnan(want)
        elif isinstance(value, float) and math.isinf(value):
            assert math.isinf(got) and math.isinf(want)
        else:
            _assert_float_bit_exact(got, want)


def test_normalize_rotation_bit_exact_random():
    """Randomized int and float rotation values."""
    rng = random.Random(20260810)
    for _ in range(40):
        kind = rng.choice(["int", "float", "none"])
        if kind == "int":
            val = rng.randint(-10, 10)
        elif kind == "float":
            val = round(rng.uniform(-20.0, 20.0), 6)
        else:
            val = None
        got = _normalize_rotation(val)
        want = _oracle_normalize_rotation(val)
        if isinstance(val, float) and math.isnan(val):
            assert math.isnan(got) and math.isnan(want)
        elif isinstance(val, float) and math.isinf(val):
            assert math.isinf(got) and math.isinf(want)
        else:
            _assert_float_bit_exact(got, want)


def test_normalize_rotation_int_preserves_type_semantics():
    """int(0) -> 0.0, not float(0) with different repr."""
    got = _normalize_rotation(0)
    want = _oracle_normalize_rotation(0)
    _assert_float_bit_exact(got, want)
    assert got == 0.0


# ============================================================================
# pin_world_position / pin_world_position_at
# ============================================================================


def test_pin_world_position_bit_exact_random():
    """Randomized pin/component/override configurations."""
    rng = random.Random(31337)
    for _ in range(50):
        pin, comp, rot_override, pos_override, float_rot = _random_pin_geometry(rng)
        kwargs = {}
        if rot_override is not None:
            kwargs["rotation_override"] = rot_override
        if float_rot is not None:
            kwargs["rotation_override"] = float_rot
        if pos_override is not None:
            kwargs["pos_override"] = pos_override
        got = pin_world_position_at(pin, comp, **kwargs)
        want = _oracle_pin_world_position_at(pin, comp, **kwargs)
        _assert_point_bit_exact(got, want)


def test_pin_world_position_all_quadrants_sides():
    """Exhaustive quadrant (0-3) × side (0,1) × random positions."""
    rng = random.Random(5)
    for rot in [0, 1, 2, 3]:
        for side in [0, 1]:
            for _ in range(5):
                pos = (round(rng.uniform(-5, 5), 6), round(rng.uniform(-5, 5), 6))
                pin = _PinStub(pos)
                cpos = (round(rng.uniform(-20, 20), 6), round(rng.uniform(-20, 20), 6))
                comp = _CompStub(
                    initial_position=cpos,
                    initial_rotation=rot,
                    initial_side=side,
                )
                got = pin_world_position_at(pin, comp)
                want = _oracle_pin_world_position_at(pin, comp)
                _assert_point_bit_exact(got, want)


def test_pin_world_position_delegates_to_at():
    """pin_world_position(pin, comp) === pin_world_position_at(pin, comp)."""
    rng = random.Random(42)
    for _ in range(20):
        pin, comp, _, _, _ = _random_pin_geometry(rng)
        got = pin_world_position(pin, comp)
        want = pin_world_position_at(pin, comp)
        _assert_point_bit_exact(got, want)


def test_pin_world_position_none_overrides():
    """Explicit pos_override=None and rotation_override=None fall back to comp attrs."""
    pin = _PinStub((1.0, 2.0))
    comp = _CompStub(
        initial_position=(10.0, 20.0),
        initial_rotation=2,
        initial_side=0,
    )
    # None overrides should behave identically to no overrides
    got_no_override = pin_world_position_at(pin, comp)
    got_none_pos = pin_world_position_at(pin, comp, pos_override=None)
    got_none_rot = pin_world_position_at(pin, comp, rotation_override=None)
    _assert_point_bit_exact(got_no_override, got_none_pos)
    _assert_point_bit_exact(got_no_override, got_none_rot)


def test_pin_world_position_comp_none_attrs():
    """Component with None initial_position / initial_rotation / initial_side."""
    pin = _PinStub((1.0, 0.0))
    comp = _CompStub(
        initial_position=None,
        initial_rotation=None,
        initial_side=None,
    )
    # None initial_position -> (0.0, 0.0), None initial_rotation -> 0.0 rad,
    # None initial_side -> 0 (top)
    got = pin_world_position_at(pin, comp)
    want = _oracle_pin_world_position_at(pin, comp)
    _assert_point_bit_exact(got, want)


def test_pin_world_position_origin():
    """Pin at origin on unrotated component at origin -> (0, 0)."""
    pin = _PinStub((0.0, 0.0))
    comp = _CompStub(
        initial_position=(0.0, 0.0),
        initial_rotation=0,
        initial_side=0,
    )
    got = pin_world_position_at(pin, comp)
    want = _oracle_pin_world_position_at(pin, comp)
    _assert_point_bit_exact(got, want)
    assert got == (0.0, 0.0)


# ============================================================================
# pin_world_layer
# ============================================================================


def test_pin_world_layer_default():
    """Pin without layer attribute -> 'F.Cu'."""
    pin = _PinStub((0.0, 0.0))
    got = pin_world_layer(pin)
    want = _oracle_pin_world_layer(pin)
    assert got == want == "F.Cu"


def test_pin_world_layer_explicit():
    """Pin with explicit layer -> that layer."""
    for layer in ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]:
        pin = _PinStub((0.0, 0.0), layer=layer)
        got = pin_world_layer(pin)
        want = _oracle_pin_world_layer(pin)
        assert got == want == layer


def test_pin_world_layer_none_layer():
    """Pin with layer=None -> 'F.Cu' (falsy fallback)."""
    pin = _PinStub((0.0, 0.0), layer=None)
    got = pin_world_layer(pin)
    want = _oracle_pin_world_layer(pin)
    assert got == want == "F.Cu"


def test_pin_world_layer_empty_string():
    """Pin with layer='' -> 'F.Cu' (falsy fallback)."""
    pin = _PinStub((0.0, 0.0), layer="")
    got = pin_world_layer(pin)
    want = _oracle_pin_world_layer(pin)
    assert got == want == "F.Cu"


# ============================================================================
# pin_world_radius
# ============================================================================


def test_pin_world_radius_rect():
    """Rectangular pad: radius = pad_bounding_radius(1.0, 1.0, 'rect', ratio)."""
    pin = _PinStub((0.0, 0.0), width=1.0, height=1.0, shape="rect")
    got = pin_world_radius(pin)
    want = _oracle_pin_world_radius(pin)
    _assert_float_bit_exact(got, want)


def test_pin_world_radius_round():
    """Round pad: radius = pad_bounding_radius(1.0, 1.0, 'round', ratio)."""
    pin = _PinStub((0.0, 0.0), width=1.0, height=1.0, shape="round")
    got = pin_world_radius(pin)
    want = _oracle_pin_world_radius(pin)
    _assert_float_bit_exact(got, want)


def test_pin_world_radius_zero_dimensions():
    """Zero width and height -> 0.5 mm default."""
    pin = _PinStub((0.0, 0.0), width=0.0, height=0.0)
    got = pin_world_radius(pin)
    want = _oracle_pin_world_radius(pin)
    _assert_float_bit_exact(got, want)
    assert got == want == 0.5


def test_pin_world_radius_none_attributes():
    """None width/height -> treated as 0.0 -> 0.5 mm default."""
    pin = _PinStub((0.0, 0.0), width=None, height=None, shape=None, roundrect_ratio=None)
    got = pin_world_radius(pin)
    want = _oracle_pin_world_radius(pin)
    _assert_float_bit_exact(got, want)
    assert got == want == 0.5


def test_pin_world_radius_random():
    """Randomized pad dimensions and shapes."""
    rng = random.Random(1004)
    for _ in range(30):
        w = round(rng.uniform(0.0, 10.0), 6)
        h = round(rng.uniform(0.0, 10.0), 6)
        shape = rng.choice(["rect", "round", "oval", "custom"])
        ratio = round(rng.uniform(0.0, 1.0), 6) if rng.random() < 0.5 else None
        pin = _PinStub((0.0, 0.0), width=w, height=h, shape=shape, roundrect_ratio=ratio)
        got = pin_world_radius(pin)
        want = _oracle_pin_world_radius(pin)
        _assert_float_bit_exact(got, want)


def test_pin_world_radius_elongated():
    """Elongated pad: 5.0 x 1.0 rect."""
    pin = _PinStub((0.0, 0.0), width=5.0, height=1.0, shape="rect")
    got = pin_world_radius(pin)
    want = _oracle_pin_world_radius(pin)
    _assert_float_bit_exact(got, want)


# ============================================================================
# Cross-function consistency
# ============================================================================


def test_pin_world_position_ignores_radius_attrs():
    """pin_world_position_at only reads pin.position and comp attrs."""
    rng = random.Random(99)
    for _ in range(10):
        # Radius-relevant attributes should not affect position
        pin = _PinStub(
            (round(rng.uniform(-5, 5), 6), round(rng.uniform(-5, 5), 6)),
            width=round(rng.uniform(0.5, 3.0), 6),
            height=round(rng.uniform(0.5, 3.0), 6),
            shape="rect",
        )
        comp = _CompStub(
            initial_position=(round(rng.uniform(-20, 20), 6), round(rng.uniform(-20, 20), 6)),
            initial_rotation=rng.choice([0, 1, 2, 3]),
            initial_side=rng.choice([0, 1]),
        )
        got = pin_world_position_at(pin, comp)
        want = _oracle_pin_world_position_at(pin, comp)
        _assert_point_bit_exact(got, want)
