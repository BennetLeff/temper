import jax.numpy as jnp

from temper_placer.core.units import deg_to_rad


def test_deg_to_rad_consistency():
    """Verify deg_to_rad converts 90 to pi/2."""
    assert jnp.allclose(deg_to_rad(90.0), jnp.pi / 2)
    assert jnp.allclose(deg_to_rad(180.0), jnp.pi)
    assert jnp.allclose(deg_to_rad(270.0), 3 * jnp.pi / 2)
    assert jnp.allclose(deg_to_rad(360.0), 2 * jnp.pi)
