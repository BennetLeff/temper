"""
Tests for thermal physics models.

Defaults are the IKW40N120H3 datasheet values (Rjc = 0.31 K/W, Rch = 0.20
K/W TIM, Rha = 0.45 K/W HS1-with-fan) — see
`temper_placer.physics.thermal` and
`docs/evidence/2026-08-15-thermal-threshold-decision.md` §3.2. The 150 °C
family was retired (it was the datasheet's storage temperature, not a
junction limit); the junction limits are 125 °C design-for / 175 °C
absolute survival.
"""

from __future__ import annotations

import pytest

from temper_placer.physics.thermal import estimate_junction_temp


def test_estimate_junction_temp_base():
    """Test junction temperature at ideal edge mounting."""
    # 15W at 5mm from edge (no penalty)
    # Rjc=0.31 (IKW40N120H3 datasheet), Rch=0.20 (TIM), Rha=0.45 (HS1 w/ fan).
    # Tj = 40 + 15 * (0.31 + 0.20 + 0.45) = 40 + 15 * 0.96 = 40 + 14.4 = 54.4
    tj = estimate_junction_temp(power_W=15.0, edge_distance_mm=5.0, ambient_C=40.0)
    assert tj == pytest.approx(54.4)


def test_estimate_junction_temp_penalty():
    """Test junction temperature with edge distance penalty."""
    # 15W at 10mm from edge (5mm penalty)
    # Penalty = 5 * 0.2 = 1.0 K/W
    # Tj = 40 + 15 * (0.96 + 1.0) = 40 + 15 * 1.96 = 40 + 29.4 = 69.4
    tj = estimate_junction_temp(power_W=15.0, edge_distance_mm=10.0, ambient_C=40.0)
    assert tj == pytest.approx(69.4)


def test_estimate_junction_temp_copper():
    """Test junction temperature with copper spreading benefit."""
    # 15W at 5mm from edge, 1000mm2 copper
    # Benefit = 0.1 K/W
    # Tj = 40 + 15 * (0.96 - 0.1) = 40 + 15 * 0.86 = 40 + 12.9 = 52.9
    tj = estimate_junction_temp(
        power_W=15.0, edge_distance_mm=5.0, copper_area_mm2=1000.0, ambient_C=40.0
    )
    assert tj == pytest.approx(52.9)


def test_estimate_junction_temp_overheat():
    """Test model detection of overheating conditions."""
    # 50W at 15mm from edge (10mm penalty)
    # Penalty = 10 * 0.2 = 2.0 K/W
    # Tj = 40 + 50 * (0.96 + 2.0) = 40 + 50 * 2.96 = 40 + 148.0 = 188.0
    tj = estimate_junction_temp(power_W=50.0, edge_distance_mm=15.0, ambient_C=40.0)
    # Exceeds the 175 °C absolute survival limit (Tvj(max) datasheet).
    assert tj > 175.0


def test_estimate_junction_temp_design_limit_ambient():
    """Default ambient is the 60 °C design-limit (ENVIRONMENTAL_SPEC.md)."""
    from temper_placer.physics.thermal import DEFAULT_AMBIENT_C

    assert DEFAULT_AMBIENT_C == 60.0
    # No power → junction sits at the ambient default.
    tj = estimate_junction_temp(power_W=0.0, edge_distance_mm=5.0)
    assert tj == pytest.approx(60.0)
