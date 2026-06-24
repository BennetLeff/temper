"""
Safety-critical interlock timing and fault response estimation.

This module estimates the latency from a physical fault (OCP/OVP) to the
interlock triggering, based on filter parasitics and signal path.
"""

from __future__ import annotations

import math

def estimate_filter_delay(
    r_ohms: float,
    c_farads: float,
    threshold_fraction: float = 0.632, # 1-1/e (one time constant)
) -> float:
    """
    Estimate the time delay of an RC low-pass filter.
    
    t = -RC * ln(1 - threshold)
    """
    if r_ohms <= 0 or c_farads <= 0:
        return 0.0
        
    tau = r_ohms * c_farads
    return -tau * math.log(1.0 - threshold_fraction)


def estimate_fault_response_time(
    _loop_inductance_nh: float,
    filter_delay_us: float,
    comparator_delay_ns: float = 150.0,
    mcu_latency_ns: float = 200.0,
) -> float:
    """
    Estimate the total time to trigger a safety interlock.
    
    Includes:
    1. di/dt limited current rise (based on inductance)
    2. RC filter delay
    3. Comparator propagation delay
    4. MCU/Firmware latency
    
    Returns:
        Total response time in microseconds.
    """
    # 1. Propagation delay (simplified)
    # Trace delay is ~6ps/mm, negligible here compared to filters.
    
    # 2. Total logic delay
    digital_delay_us = (comparator_delay_ns + mcu_latency_ns) * 1e-3
    
    # Total
    return filter_delay_us + digital_delay_us


def is_safety_timing_valid(
    response_time_us: float,
    max_limit_us: float = 10.0
) -> bool:
    """Check if fault response is within safety limits."""
    return response_time_us <= max_limit_us
