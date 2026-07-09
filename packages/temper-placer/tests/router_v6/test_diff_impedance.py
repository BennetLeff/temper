"""Tests for the edge-coupled microstrip differential impedance module.

Part of W2/U5 — JLC04161H-7628 functional stackup.
"""

from __future__ import annotations

import math

import pytest

from temper_placer.router_v6.diff_impedance import (
    USB_PREDICTED_ZDIFF,
    USB_S_MM,
    USB_W_MM,
    edge_coupled_microstrip_geometry,
    edge_coupled_microstrip_z0,
)

# ---------------------------------------------------------------------------
# edge_coupled_microstrip_z0 tests
# ---------------------------------------------------------------------------


def test_z0_known_geometry_usb_jlc():
    """USB pair on JLC04161H-7628: w=0.3, s=0.2, h=0.2, er=4.2."""
    z = edge_coupled_microstrip_z0(0.3, 0.2, 0.2, 4.2)
    # Should be within +-10% of 90R.
    assert 81.0 <= z <= 99.0, f"Zdiff={z:.1f} not in [81.0, 99.0]"


def test_z0_wider_traces_lower_impedance():
    """Wider traces → lower single-ended Z0 → lower differential Z0."""
    z_narrow = edge_coupled_microstrip_z0(0.2, 0.2, 0.5, 4.2)
    z_wide = edge_coupled_microstrip_z0(0.6, 0.2, 0.5, 4.2)
    assert z_wide < z_narrow, (
        f"Expected wider (0.6mm) < narrower (0.2mm), "
        f"got {z_wide:.1f} >= {z_narrow:.1f}"
    )


def test_z0_wider_spacing_higher_impedance():
    """Larger spacing → less coupling → Zdiff approaches 2*Z0."""
    z_tight = edge_coupled_microstrip_z0(0.3, 0.1, 0.5, 4.2)
    z_loose = edge_coupled_microstrip_z0(0.3, 0.6, 0.5, 4.2)
    assert z_loose > z_tight, (
        f"Expected loose spacing > tight spacing, "
        f"got {z_loose:.1f} <= {z_tight:.1f}"
    )


def test_z0_thinner_dielectric_lower_impedance():
    """Thinner dielectric → lower Z0."""
    z_thin = edge_coupled_microstrip_z0(0.3, 0.2, 0.1, 4.2)
    z_thick = edge_coupled_microstrip_z0(0.3, 0.2, 0.5, 4.2)
    assert z_thin < z_thick, (
        f"Expected thin dielectric < thick, "
        f"got {z_thin:.1f} >= {z_thick:.1f}"
    )


def test_z0_higher_er_lower_impedance():
    """Higher er → lower impedance."""
    z_low_er = edge_coupled_microstrip_z0(0.3, 0.2, 0.2, 3.5)
    z_high_er = edge_coupled_microstrip_z0(0.3, 0.2, 0.2, 5.0)
    assert z_high_er < z_low_er, (
        f"Expected high er < low er, "
        f"got {z_high_er:.1f} >= {z_low_er:.1f}"
    )


def test_z0_monotonic_in_w():
    """Zdiff decreases monotonically as width increases."""
    prev = math.inf
    for w in [w / 100.0 for w in range(10, 61)]:  # 0.1..0.6 mm
        z = edge_coupled_microstrip_z0(w, 0.2, 0.3, 4.2)
        assert z < prev, f"Zdiff={z:.1f} >= prev={prev:.1f} at w={w:.3f}"
        prev = z


def test_z0_positive():
    """All valid inputs produce positive impedance."""
    for w in [0.1, 0.3, 1.0, 3.0]:
        for s in [0.1, 0.3, 1.0]:
            for h in [0.1, 0.2, 0.5, 1.6]:
                for er in [3.5, 4.2, 4.8]:
                    z = edge_coupled_microstrip_z0(w, s, h, er)
                    assert z > 0, f"Non-positive Zdiff at ({w},{s},{h},{er})"


# ---------------------------------------------------------------------------
# edge_coupled_microstrip_geometry tests
# ---------------------------------------------------------------------------


def test_geometry_roundtrip_approx():
    """Search returns geometry whose impedance is within +-15% of target."""
    h, er = 0.3, 4.2
    z_target = 90.0
    w, s = edge_coupled_microstrip_geometry(z_target, h, er)
    z_actual = edge_coupled_microstrip_z0(w, s, h, er)
    # Relaxed tolerance for the search's limited resolution.
    assert abs(z_actual - z_target) <= 0.15 * z_target, (
        f"Roundtrip error too large: w={w:.3f} s={s:.3f} "
        f"Ztarget={z_target:.1f} Zactual={z_actual:.1f}"
    )


def test_geometry_positive_output():
    """Returns positive width and spacing."""
    w, s = edge_coupled_microstrip_geometry(100.0, 0.2, 4.2)
    assert w > 0
    assert s > 0


def test_geometry_different_targets():
    """Higher impedance target → wider traces or spacing."""
    w1, s1 = edge_coupled_microstrip_geometry(50.0, 0.3, 4.2)
    w2, s2 = edge_coupled_microstrip_geometry(100.0, 0.3, 4.2)
    # At least one of width or spacing should be larger for higher Z.
    assert (w2 > w1) or (s2 > s1), (
        f"Higher target not reflected: 50R→({w1:.3f},{s1:.3f}) "
        f"100R→({w2:.3f},{s2:.3f})"
    )


# ---------------------------------------------------------------------------
# Pre-computed USB constants
# ---------------------------------------------------------------------------


def test_usb_precomputed_constants():
    assert USB_W_MM > 0
    assert USB_S_MM > 0
    assert USB_PREDICTED_ZDIFF > 0


def test_usb_geometry_within_tolerance():
    """Pre-computed USB geometry lands within +-10% of 90R."""
    z = edge_coupled_microstrip_z0(USB_W_MM, USB_S_MM, 0.2, 4.2)
    assert 81.0 <= z <= 99.0, f"USB Zdiff={z:.1f} not in [81.0, 99.0]"
    assert abs(USB_PREDICTED_ZDIFF - z) < 1e-3
