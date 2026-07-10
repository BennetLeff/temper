import numpy as np

from temper_placer.core.units import deg_to_rad


def test_deg_to_rad_consistency():
    """Verify deg_to_rad converts 90 to pi/2."""
    assert np.allclose(deg_to_rad(90.0), np.pi / 2)
    assert np.allclose(deg_to_rad(180.0), np.pi)
    assert np.allclose(deg_to_rad(270.0), 3 * np.pi / 2)
    assert np.allclose(deg_to_rad(360.0), 2 * np.pi)
