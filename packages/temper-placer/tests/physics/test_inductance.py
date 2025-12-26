"""
Tests for parasitic inductance models.
"""

from __future__ import annotations

import pytest
from temper_placer.physics.inductance import estimate_loop_inductance, estimate_gate_inductance


def test_estimate_loop_inductance_base():
    """Test standard loop inductance calculation."""
    # 100mm2 area, 40mm perimeter, 0.4mm height
    # L_area = 314 nH (from description)
    # L_self = 40 * 0.2 = 8 nH
    # L_total = (314 * 0.5 + 8) * 1.2 = (157 + 8) * 1.2 = 165 * 1.2 = 198 nH
    l = estimate_loop_inductance(loop_area_mm2=100.0, perimeter_mm=40.0)
    assert l == pytest.approx(198.1, abs=0.1)


def test_estimate_gate_inductance():
    """Test rule-of-thumb gate inductance calculation."""
    # 10mm trace, 10mm return
    # L = (10 + 10 + 5) * 0.8 = 25 * 0.8 = 20 nH
    l = estimate_gate_inductance(source_to_gate_dist_mm=10.0, return_dist_mm=10.0)
    assert l == pytest.approx(20.0)