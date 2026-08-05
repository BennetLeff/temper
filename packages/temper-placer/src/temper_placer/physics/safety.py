"""
Safety-critical interlock timing and fault response estimation.

This module estimates the latency from a physical fault (OCP/OVP) to the
interlock triggering, based on filter parasitics and signal path.

Wave 4 Phase 4: the arithmetic delegates to the Rust kernels in
`temper-thermal` (`temper_thermal.estimate_filter_delay_py`,
`temper_thermal.estimate_fault_response_time_py`,
`temper_thermal.is_safety_timing_valid_py`).  Bit-identical parity
against the pre-migration implementation is pinned by
`tests/physics/test_safety_rust_differential.py`, including the CPython
`math.log` domain-error raise (`ValueError("math domain error")` for a
threshold >= 1.0 with strictly positive r and c) which the Rust bridge
reproduces exactly.
"""

from __future__ import annotations

import temper_thermal as _tt


def estimate_filter_delay(
    r_ohms: float,
    c_farads: float,
    threshold_fraction: float = 0.632,  # 1-1/e (one time constant)
) -> float:
    """
    Estimate the time delay of an RC low-pass filter.

    t = -RC * ln(1 - threshold)
    """
    return _tt.estimate_filter_delay_py(r_ohms, c_farads, threshold_fraction)


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
    return _tt.estimate_fault_response_time_py(
        _loop_inductance_nh, filter_delay_us, comparator_delay_ns, mcu_latency_ns
    )


def is_safety_timing_valid(response_time_us: float, max_limit_us: float = 10.0) -> bool:
    """Check if fault response is within safety limits."""
    return _tt.is_safety_timing_valid_py(response_time_us, max_limit_us)
