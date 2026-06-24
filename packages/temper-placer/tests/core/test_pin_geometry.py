"""Tests for core.pin_geometry module."""

import math

import pytest

from temper_placer.core.netlist import Component, Pin
from temper_placer.core.pin_geometry import (
    pin_world_layer,
    pin_world_position,
    pin_world_radius,
)


class TestPinWorldGeometry:
    """Tests for the canonical pad-position free functions."""

    # ------------------------------------------------------------------
    # pin_world_position — four rotation/side combinations (R9)
    # ------------------------------------------------------------------

    def test_zero_rotation_top_side(self):
        """Zero rotation, top side: pin offset added directly."""
        pin = Pin("1", "1", (1.0, 0.0))
        comp = Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(10.0, 10.0),
            initial_position=(10.0, 20.0),
            initial_rotation=0,
            initial_side=0,
        )
        x, y = pin_world_position(pin, comp)
        assert x == pytest.approx(11.0, abs=1e-6)
        assert y == pytest.approx(20.0, abs=1e-6)

    def test_90deg_rotation_top_side(self):
        """90° rotation (index 1), top side: pin offset rotated CCW."""
        pin = Pin("1", "1", (1.0, 0.0))
        comp = Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(10.0, 10.0),
            initial_position=(10.0, 20.0),
            initial_rotation=1,
            initial_side=0,
        )
        x, y = pin_world_position(pin, comp)
        # Pin at (1,0) rotated 90° CCW → (0, 1)
        # World: (10+0, 20+1) = (10, 21)
        assert x == pytest.approx(10.0, abs=1e-6)
        assert y == pytest.approx(21.0, abs=1e-6)

    def test_zero_rotation_bottom_side(self):
        """Zero rotation, bottom side: pin X mirrored."""
        pin = Pin("1", "1", (1.0, 0.0))
        comp = Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(10.0, 10.0),
            initial_position=(10.0, 20.0),
            initial_rotation=0,
            initial_side=1,
        )
        x, y = pin_world_position(pin, comp)
        # Pin at (1,0) on bottom: X mirrored → (-1, 0)
        # Zero rotation → world: (10-1, 20+0) = (9, 20)
        assert x == pytest.approx(9.0, abs=1e-6)
        assert y == pytest.approx(20.0, abs=1e-6)

    def test_90deg_rotation_bottom_side(self):
        """90° rotation (index 1), bottom side: X mirrored then rotated."""
        import jax.numpy as jnp

        pin = Pin("1", "1", (1.0, 0.0))
        comp = Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(10.0, 10.0),
            initial_position=(10.0, 20.0),
            initial_rotation=1,
            initial_side=1,
        )
        x, y = pin_world_position(pin, comp)
        # Pin at (1,0), bottom-side: X mirrored → (-1, 0)
        # Rotated 90° CCW: rx = 0, ry = -1
        # World: (10+0, 20-1) = (10, 19)
        # Verify against the reference implementation (Pin.absolute_position)
        ref_x, ref_y = pin.absolute_position((10.0, 20.0), jnp.pi / 2, side=1)
        assert x == pytest.approx(float(ref_x), abs=1e-6)
        assert y == pytest.approx(float(ref_y), abs=1e-6)

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_none_rotation_treated_as_zero(self):
        """None rotation is treated as 0 (no rotation)."""
        pin = Pin("1", "1", (1.0, 0.0))
        comp = Component(
            ref="U1",
            footprint="SOT-23",
            bounds=(3.0, 3.0),
            initial_position=(10.0, 20.0),
            initial_rotation=None,
            initial_side=0,
        )
        x, y = pin_world_position(pin, comp)
        assert x == pytest.approx(11.0, abs=1e-6)
        assert y == pytest.approx(20.0, abs=1e-6)

    def test_none_side_treated_as_zero(self):
        """None side is treated as 0 (top)."""
        pin = Pin("1", "1", (1.0, 0.0))
        comp = Component(
            ref="U1",
            footprint="SOT-23",
            bounds=(3.0, 3.0),
            initial_position=(10.0, 20.0),
            initial_rotation=0,
            initial_side=None,
        )
        x, y = pin_world_position(pin, comp)
        assert x == pytest.approx(11.0, abs=1e-6)

    def test_none_position_treated_as_zero(self):
        """None initial_position is treated as (0, 0)."""
        pin = Pin("1", "1", (1.0, 0.0))
        comp = Component(
            ref="U1",
            footprint="SOT-23",
            bounds=(3.0, 3.0),
            initial_position=None,
            initial_rotation=0,
            initial_side=0,
        )
        x, y = pin_world_position(pin, comp)
        assert x == pytest.approx(1.0, abs=1e-6)
        assert y == pytest.approx(0.0, abs=1e-6)

    # ------------------------------------------------------------------
    # pin_world_layer
    # ------------------------------------------------------------------

    def test_pin_world_layer_default(self):
        """Pin without an explicit layer returns 'F.Cu'."""
        pin = Pin("1", "1", (0.0, 0.0))
        assert pin_world_layer(pin) == "F.Cu"

    # ------------------------------------------------------------------
    # pin_world_radius
    # ------------------------------------------------------------------

    def test_pin_world_radius_from_dimensions(self):
        """Radius is max(width, height) / 2."""
        pin = Pin("1", "1", (0.0, 0.0), width=2.0, height=1.0)
        assert pin_world_radius(pin) == pytest.approx(1.0, abs=1e-6)

    def test_pin_world_radius_zero_dimensions(self):
        """Zero dimensions default to radius 0.5."""
        pin = Pin("1", "1", (0.0, 0.0), width=0.0, height=0.0)
        assert pin_world_radius(pin) == pytest.approx(0.5, abs=1e-6)


class TestPinAbsolutePositionDelegation:
    """Verify Pin.absolute_position still produces correct values post-refactor."""

    def test_no_rotation_matches_free_function(self):
        """Class method matches free function for zero rotation, top side."""
        pin = Pin("1", "1", (1.0, 0.0))
        comp = Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(10.0, 10.0),
            initial_position=(10.0, 20.0),
            initial_rotation=0,
            initial_side=0,
        )
        from_method = pin.absolute_position((10.0, 20.0), 0.0, side=0)
        from_free = pin_world_position(pin, comp)
        assert from_method[0] == pytest.approx(from_free[0], abs=1e-6)
        assert from_method[1] == pytest.approx(from_free[1], abs=1e-6)

    def test_rotated_matches_free_function(self):
        """Class method matches free function for 90° rotation."""
        import jax.numpy as jnp

        pin = Pin("1", "1", (1.0, 0.0))
        comp = Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(10.0, 10.0),
            initial_position=(10.0, 20.0),
            initial_rotation=1,
            initial_side=0,
        )
        from_method = pin.absolute_position((10.0, 20.0), jnp.pi / 2, side=0)
        from_free = pin_world_position(pin, comp)
        assert from_method[0] == pytest.approx(from_free[0], abs=1e-6)
        assert from_method[1] == pytest.approx(from_free[1], abs=1e-6)
