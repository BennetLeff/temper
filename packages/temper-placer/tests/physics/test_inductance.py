import math
import pytest
from temper_placer.physics.inductance import (
    estimate_loop_inductance, 
    estimate_partial_inductance
)

def test_loop_inductance_basic():
    """Verify loop inductance calculation for a known case."""
    # Area = 100 mm², h = 0.4 mm
    # L = 4π*10^-7 * 100*10^-6 / 0.0004 = 3.14 * 10^-7 H = 314 nH
    # factor = 1.0
    l = estimate_loop_inductance(100.0, layer_separation_mm=0.4, routing_factor=1.0)
    assert math.isclose(l, 314.159, rel_tol=1e-3)

def test_loop_inductance_scaling():
    """Inductance should scale linearly with area and inversely with separation."""
    l1 = estimate_loop_inductance(100.0, layer_separation_mm=0.4)
    l2 = estimate_loop_inductance(200.0, layer_separation_mm=0.4)
    assert math.isclose(l2, 2 * l1)
    
    l3 = estimate_loop_inductance(100.0, layer_separation_mm=0.8)
    assert math.isclose(l3, 0.5 * l1)

def test_partial_inductance():
    """Verify partial inductance estimate for a trace."""
    # length = 10mm, width = 1mm, thick = 0.035mm
    # L ≈ 0.2 * 10 * (ln(20/1.035) + 0.5)
    #   ≈ 2 * (2.96 + 0.5) ≈ 6.9 nH
    l = estimate_partial_inductance(10.0, 1.0)
    assert 6.0 < l < 8.0

def test_zero_cases():
    """Handle edge cases gracefully."""
    assert estimate_loop_inductance(0.0) == 0.0
    assert estimate_partial_inductance(0.0, 1.0) == 0.0
