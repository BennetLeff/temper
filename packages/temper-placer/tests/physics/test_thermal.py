"""
Tests for thermal physics models.
"""

from __future__ import annotations

import pytest

from temper_placer.physics.thermal import estimate_junction_temp


def test_estimate_junction_temp_base():
    """Test junction temperature at ideal edge mounting."""
    # 15W at 5mm from edge (no penalty)
    # Rha_base is 1.0 K/W (real Wakefield 694-100 extrusion, de-rated;
    # commit 56ce82da/#142 replaced the 2.0 K/W placeholder).
    # Tj = 40 + 15 * (0.6 + 0.25 + 1.0) = 40 + 15 * 1.85 = 40 + 27.75 = 67.75
    tj = estimate_junction_temp(power_W=15.0, edge_distance_mm=5.0, ambient_C=40.0)
    assert tj == pytest.approx(67.75)


def test_estimate_junction_temp_penalty():
    """Test junction temperature with edge distance penalty."""
    # 15W at 10mm from edge (5mm penalty)
    # Penalty = 5 * 0.2 = 1.0 K/W
    # Tj = 40 + 15 * (1.85 + 1.0) = 40 + 15 * 2.85 = 40 + 42.75 = 82.75
    tj = estimate_junction_temp(power_W=15.0, edge_distance_mm=10.0, ambient_C=40.0)
    assert tj == pytest.approx(82.75)


def test_estimate_junction_temp_copper():
    """Test junction temperature with copper spreading benefit."""
    # 15W at 5mm from edge, 1000mm2 copper
    # Benefit = 0.1 K/W
    # Tj = 40 + 15 * (1.85 - 0.1) = 40 + 15 * 1.75 = 40 + 26.25 = 66.25
    tj = estimate_junction_temp(
        power_W=15.0, edge_distance_mm=5.0, copper_area_mm2=1000.0, ambient_C=40.0
    )
    assert tj == pytest.approx(66.25)


def test_estimate_junction_temp_overheat():
    """Test model detection of overheating conditions."""
    # 50W at 15mm from edge (10mm penalty)
    # Penalty = 10 * 0.2 = 2.0 K/W
    # Tj = 40 + 50 * (1.85 + 2.0) = 40 + 50 * 3.85 = 40 + 192.5 = 232.5
    tj = estimate_junction_temp(power_W=50.0, edge_distance_mm=15.0, ambient_C=40.0)
    assert tj > 150.0
