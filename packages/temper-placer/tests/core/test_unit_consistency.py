import jax.numpy as jnp

from temper_placer.core.netlist import Pin
from temper_placer.core.units import Radians, deg_to_rad


def test_pin_absolute_position_90_deg():
    """Test that 90 degree rotation correctly transforms pin positions."""
    # Pin at (1.0, 0.0) relative to component center
    pin = Pin(name="1", number="1", position=(1.0, 0.0))

    # Component at (10.0, 10.0)
    comp_pos = (10.0, 10.0)

    # 0 degrees: should be (11.0, 10.0)
    pos_0 = pin.absolute_position(comp_pos, Radians(0.0))
    assert jnp.allclose(jnp.array(pos_0), jnp.array([11.0, 10.0]))

    # 90 degrees (pi/2): should be (10.0, 11.0)
    # (1, 0) rotated 90 deg CCW is (0, 1)
    # (10, 10) + (0, 1) = (10, 11)
    pos_90 = pin.absolute_position(comp_pos, Radians(jnp.pi / 2))
    assert jnp.allclose(jnp.array(pos_90), jnp.array([10.0, 11.0]))

    # 180 degrees (pi): should be (9.0, 10.0)
    pos_180 = pin.absolute_position(comp_pos, Radians(jnp.pi))
    assert jnp.allclose(jnp.array(pos_180), jnp.array([9.0, 10.0]))

    # 270 degrees (3pi/2): should be (10.0, 9.0)
    pos_270 = pin.absolute_position(comp_pos, Radians(3 * jnp.pi / 2))
    assert jnp.allclose(jnp.array(pos_270), jnp.array([10.0, 9.0]))

def test_pin_absolute_position_unit_mismatch():
    """Prove that passing degrees to absolute_position causes significant errors (57x)."""
    pin = Pin(name="1", number="1", position=(1.0, 0.0))
    comp_pos = (0.0, 0.0)

    # Correct: 90 degrees as radians
    expected = jnp.array([0.0, 1.0])
    actual_correct = pin.absolute_position(comp_pos, Radians(jnp.pi / 2))
    assert jnp.allclose(jnp.array(actual_correct), expected, atol=1e-5)

    # WRONG: passing 90.0 (degrees) as the angle
    # cos(90 rad) approx -0.448
    # sin(90 rad) approx 0.894
    actual_wrong = pin.absolute_position(comp_pos, Radians(90.0))

    # Verify it's NOT (0, 1)
    assert not jnp.allclose(jnp.array(actual_wrong), expected, atol=1e-1)

    print(f"\nCorrect (pi/2 rad): {actual_correct}")
    print(f"Wrong (90 rad): {actual_wrong}")

def test_deg_to_rad_consistency():
    """Verify deg_to_rad converts 90 to pi/2."""
    assert jnp.allclose(deg_to_rad(90.0), jnp.pi / 2)
    assert jnp.allclose(deg_to_rad(180.0), jnp.pi)
    assert jnp.allclose(deg_to_rad(270.0), 3 * jnp.pi / 2)
    assert jnp.allclose(deg_to_rad(360.0), 2 * jnp.pi)
