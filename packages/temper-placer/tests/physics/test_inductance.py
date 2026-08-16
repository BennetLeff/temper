"""
Tests for parasitic inductance models (Rust kernels in temper_thermal).
"""

from __future__ import annotations

import pytest

from temper_thermal import (
    estimate_gate_inductance_py,
    estimate_loop_inductance_py,
)


def test_estimate_loop_inductance_base():
    """Test standard loop inductance calculation."""
    # 100mm2 area, 40mm perimeter, 0.4mm height
    # L_area = 314 nH (from description)
    # L_self = 40 * 0.2 = 8 nH
    # L_total = (314 * 0.5 + 8) * 1.2 = (157 + 8) * 1.2 = 165 * 1.2 = 198 nH
    # (former shim defaults: layer_separation 0.4 mm, routing_factor 1.2)
    ind = estimate_loop_inductance_py(100.0, 40.0, 0.4, 1.2)
    assert ind == pytest.approx(198.1, abs=0.1)


def test_estimate_gate_inductance():
    """Test rule-of-thumb gate inductance calculation."""
    # 10mm trace, 10mm return
    # L = (10 + 10 + 5) * 0.8 = 25 * 0.8 = 20 nH
    ind = estimate_gate_inductance_py(10.0, 10.0)
    assert ind == pytest.approx(20.0)
