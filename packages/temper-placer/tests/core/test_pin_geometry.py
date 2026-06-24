"""Tests for the canonical pad-position helpers in core/pin_geometry.py."""

from __future__ import annotations

import math

from temper_placer.core.netlist import Component, Pin
from temper_placer.core.pin_geometry import (
    pin_world_layer,
    pin_world_position,
    pin_world_radius,
)


def _make_pin(px: float = 1.0, py: float = 0.0, layer: str = "F.Cu", width: float = 1.0, height: float = 1.0) -> Pin:
    return Pin(
        name="1",
        number="1",
        position=(px, py),
        net=None,
        width=width,
        height=height,
        layer=layer,
    )


def _make_comp(
    pos: tuple[float, float] | None = (10.0, 20.0),
    rotation: int | None = 0,
    side: int | None = 0,
) -> Component:
    return Component(
        ref="U1",
        footprint="Test",
        bounds=(1.0, 1.0),
        pins=[],
        net_class="Signal",
        initial_position=pos,
        initial_rotation=rotation,
        initial_side=side,
    )


class TestPinWorldGeometry:
    """Pins the four rotation/side combinations so the bug surface is testable."""

    def test_zero_rotation_top_side(self):
        pin = _make_pin(px=1.0, py=0.0)
        comp = _make_comp(pos=(10.0, 20.0), rotation=0, side=0)
        assert pin_world_position(pin, comp) == (11.0, 20.0)

    def test_90deg_rotation_top_side(self):
        # 90° CCW rotation: (1, 0) -> (0, 1)
        pin = _make_pin(px=1.0, py=0.0)
        comp = _make_comp(pos=(10.0, 20.0), rotation=1, side=0)
        assert pin_world_position(pin, comp) == (10.0, 21.0)

    def test_zero_rotation_bottom_side(self):
        # Bottom-side: X mirrored first, so (1, 0) -> (-1, 0) -> (9, 20)
        pin = _make_pin(px=1.0, py=0.0)
        comp = _make_comp(pos=(10.0, 20.0), rotation=0, side=1)
        assert pin_world_position(pin, comp) == (9.0, 20.0)

    def test_90deg_rotation_bottom_side(self):
        # Mirror X first: (1, 0) -> (-1, 0), then rotate 90°: (0, -1)
        # Result: (10 + 0, 20 + -1) = (10, 19)
        pin = _make_pin(px=1.0, py=0.0)
        comp = _make_comp(pos=(10.0, 20.0), rotation=1, side=1)
        assert pin_world_position(pin, comp) == (10.0, 19.0)

    def test_180deg_rotation(self):
        # 180°: (1, 0) -> (-1, 0); + comp_pos
        pin = _make_pin(px=1.0, py=0.0)
        comp = _make_comp(pos=(10.0, 20.0), rotation=2, side=0)
        assert pin_world_position(pin, comp) == (9.0, 20.0)

    def test_270deg_rotation(self):
        # 270° CCW (= 90° CW): (1, 0) -> (0, -1)
        pin = _make_pin(px=1.0, py=0.0)
        comp = _make_comp(pos=(10.0, 20.0), rotation=3, side=0)
        assert pin_world_position(pin, comp) == (10.0, 19.0)

    def test_none_position_treated_as_origin(self):
        pin = _make_pin(px=2.0, py=3.0)
        comp = _make_comp(pos=None, rotation=0, side=0)
        assert pin_world_position(pin, comp) == (2.0, 3.0)

    def test_none_rotation_treated_as_zero(self):
        pin = _make_pin(px=1.0, py=0.0)
        comp = _make_comp(rotation=None, side=0)
        assert pin_world_position(pin, comp) == (11.0, 20.0)

    def test_none_side_treated_as_top(self):
        pin = _make_pin(px=1.0, py=0.0)
        comp = _make_comp(side=None)
        assert pin_world_position(pin, comp) == (11.0, 20.0)

    def test_pin_offset_not_at_origin(self):
        # Pin at (1, 2) with 0 rotation: (10+1, 20+2) = (11, 22)
        pin = _make_pin(px=1.0, py=2.0)
        comp = _make_comp(rotation=0, side=0)
        assert pin_world_position(pin, comp) == (11.0, 22.0)


class TestPinWorldLayer:
    def test_returns_pin_layer(self):
        pin = _make_pin(layer="In1.Cu")
        assert pin_world_layer(pin) == "In1.Cu"

    def test_default_layer(self):
        pin = _make_pin()
        assert pin_world_layer(pin) == "F.Cu"

    def test_through_hole_layer(self):
        pin = _make_pin(layer="all")
        assert pin_world_layer(pin) == "all"


class TestPinWorldRadius:
    def test_equal_dimensions(self):
        pin = _make_pin(width=1.0, height=1.0)
        assert pin_world_radius(pin) == 0.5

    def test_asymmetric_dimensions(self):
        pin = _make_pin(width=2.0, height=1.0)
        assert pin_world_radius(pin) == 1.0
        pin = _make_pin(width=0.5, height=1.5)
        assert pin_world_radius(pin) == 0.75

    def test_zero_width_uses_height(self):
        pin = _make_pin(width=0.0, height=2.0)
        assert pin_world_radius(pin) == 1.0

    def test_both_zero(self):
        pin = _make_pin(width=0.0, height=0.0)
        assert pin_world_radius(pin) == 0.0


class TestPinAbsolutePositionDelegate:
    """Verify the existing Pin.absolute_position (R7) still produces
    the canonical result after the surface is introduced."""

    def test_matches_free_function(self):
        # Use the same canonical math directly via the class method.
        from temper_placer.core.units import Radians
        from temper_placer.core.netlist import Pin as PinClass
        pin = PinClass(name="1", number="1", position=(1.0, 0.0))
        comp = _make_comp(rotation=1, side=0)
        # Pin.absolute_position takes (component_pos, rotation_radians, side)
        result = pin.absolute_position(
            (10.0, 20.0), Radians(math.pi / 2.0), 0
        )
        # pin_world_position(pin, comp) uses rotation index 1 (= pi/2 rad)
        # The class method and free function should agree within float precision
        assert abs(result[0] - 10.0) < 1e-6
        assert abs(result[1] - 21.0) < 1e-6
