import math
import pytest
from temper_placer.physics.emi import predict_radiated_emissions, check_emi_compliance
from temper_placer.physics.safety import estimate_filter_delay, estimate_fault_response_time

def test_emi_prediction():
    """Verify EMI prediction logic."""
    # Area = 100mm2, Current = 10A, Freq = 50MHz, Dist = 3m
    # E_v = 1.316e-14 * 100 * 10 * (50^2) / 3 
    #     = 1.316e-14 * 1000 * 2500 / 3
    #     = 3.29e-8 / 3 = 1.096e-8 V/m
    # E_uv = 0.01096 uV/m
    # dBuv = 20 * log10(0.01096) = -39.2 dBuv
    dbuv = predict_radiated_emissions(100.0, 10.0, 50.0)
    assert -40.0 < dbuv < -38.0
    assert check_emi_compliance(dbuv) == True

def test_emi_scaling():
    """EMI should scale with square of frequency."""
    e1 = predict_radiated_emissions(100.0, 1.0, 30.0)
    e2 = predict_radiated_emissions(100.0, 1.0, 60.0)
    # 20 * log10( (60/30)^2 ) = 20 * log10(4) = 12.04 dB increase
    assert math.isclose(e2 - e1, 12.04, rel_tol=1e-2)

def test_safety_delay():
    """Verify RC delay calculation."""
    # R=1k, C=10nF -> Tau = 10us
    delay = estimate_filter_delay(1000.0, 10e-9)
    assert math.isclose(delay * 1e6, 10.0, rel_tol=1e-3)

def test_total_response_time():
    """Verify total response time summation."""
    # filter = 5us, logic = 350ns
    res = estimate_fault_response_time(100.0, 5.0)
    assert math.isclose(res, 5.35)
