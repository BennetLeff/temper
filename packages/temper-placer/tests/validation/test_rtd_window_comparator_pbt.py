"""Property tests for the independent, fail-safe PT100 comparator path.

The model deliberately proves the interval contract before a comparator circuit
is selected: every permitted analogue corner has to retain a valid window.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.validation.rtd_safety import (
    MAX31865_VBIAS_MAX_V,
    MAX31865_VBIAS_MIN_V,
    REF2025_VBIAS_NOMINAL_V,
    REF2025_VBIAS_TOLERANCE_FRACTION,
    RTD_AVDD_NORMAL_MIN_V,
    RTD_HIGH_WINDOW_BOTTOM_OHM,
    RTD_HIGH_WINDOW_TOP_OHM,
    RTD_LOW_WINDOW_BOTTOM_OHM,
    RTD_LOW_WINDOW_TOP_OHM,
    RTD_WINDOW_COMPARATOR_MIN_SUPPLY_V,
    RTD_WINDOW_RESISTOR_TOLERANCE_FRACTION,
    Max31865RtdWindowCorners,
    RtdAvddMonitorCorners,
    RtdHardwareWindow,
    RtdWindowCorners,
    derive_hardware_window,
    derive_max31865_hardware_window,
    max31865_rtd_voltage_v,
    populated_rtd_window_thresholds_v,
    rtd_hardware_shutdown_asserted,
    rtd_window_fault_line_asserted,
    validate_rtd_avdd_monitor,
)

# These are modelling inputs, not asserted MAX31865 specifications.  The
# measured current-corner values must replace them before a physical comparator
# is selected.  Their generous separation lets the tests exercise offset and
# divider-tolerance handling independently of that measurement campaign.
_SAFE_CORNERS = RtdWindowCorners(
    bias_current_min_a=490e-6,
    bias_current_max_a=510e-6,
    short_max_ohm=10.0,
    valid_min_ohm=100.0,
    valid_max_ohm=194.1,
    open_min_ohm=300.0,
    comparator_offset_abs_v=1e-3,
    divider_tolerance_fraction=0.01,
    required_margin_fraction=0.20,
    supply_loss_fault=True,
)


def _safe_window() -> RtdHardwareWindow:
    return derive_hardware_window(_SAFE_CORNERS)


@given(
    resistance_ohm=st.floats(min_value=100.0, max_value=194.1),
    excitation_a=st.floats(min_value=490e-6, max_value=510e-6),
    comparator_offset_v=st.floats(min_value=-1e-3, max_value=1e-3),
    divider_error_fraction=st.floats(min_value=-0.01, max_value=0.01),
)
@settings(max_examples=200, deadline=10_000)
def test_every_valid_pt100_corner_remains_inside_hardware_window(
    resistance_ohm: float,
    excitation_a: float,
    comparator_offset_v: float,
    divider_error_fraction: float,
) -> None:
    """A component corner must never turn a valid PT100 into a hardware trip."""

    assert not _safe_window().faulted(
        resistance_ohm,
        excitation_a,
        supply_present=True,
        comparator_offset_v=comparator_offset_v,
        divider_error_fraction=divider_error_fraction,
    )


@given(
    resistance_ohm=st.floats(min_value=0.0, max_value=10.0),
    excitation_a=st.floats(min_value=490e-6, max_value=510e-6),
    comparator_offset_v=st.floats(min_value=-1e-3, max_value=1e-3),
    divider_error_fraction=st.floats(min_value=-0.01, max_value=0.01),
)
@settings(max_examples=200, deadline=10_000)
def test_hard_short_asserts_at_every_analogue_corner(
    resistance_ohm: float,
    excitation_a: float,
    comparator_offset_v: float,
    divider_error_fraction: float,
) -> None:
    assert _safe_window().faulted(
        resistance_ohm,
        excitation_a,
        supply_present=True,
        comparator_offset_v=comparator_offset_v,
        divider_error_fraction=divider_error_fraction,
    )


@given(
    resistance_ohm=st.floats(min_value=300.0, max_value=10_000.0),
    excitation_a=st.floats(min_value=490e-6, max_value=510e-6),
    comparator_offset_v=st.floats(min_value=-1e-3, max_value=1e-3),
    divider_error_fraction=st.floats(min_value=-0.01, max_value=0.01),
)
@settings(max_examples=200, deadline=10_000)
def test_open_or_out_of_range_rtd_asserts_at_every_analogue_corner(
    resistance_ohm: float,
    excitation_a: float,
    comparator_offset_v: float,
    divider_error_fraction: float,
) -> None:
    assert _safe_window().faulted(
        resistance_ohm,
        excitation_a,
        supply_present=True,
        comparator_offset_v=comparator_offset_v,
        divider_error_fraction=divider_error_fraction,
    )


@given(
    resistance_ohm=st.floats(min_value=0.0, max_value=10_000.0),
    excitation_a=st.floats(min_value=0.0, max_value=1e-3),
)
@settings(max_examples=100, deadline=10_000)
def test_comparator_supply_loss_is_an_unconditional_fault(
    resistance_ohm: float, excitation_a: float
) -> None:
    """An unpowered comparator must not deassert the fault OR/latch input."""

    assert _safe_window().faulted(
        resistance_ohm,
        excitation_a,
        supply_present=False,
        comparator_offset_v=0.0,
        divider_error_fraction=0.0,
    )


def test_design_rejects_a_supply_loss_that_could_deassert_fault() -> None:
    """Fail-safe wiring is a design precondition, not an optional runtime mode."""

    with pytest.raises(ValueError, match="supply loss"):
        derive_hardware_window(
            RtdWindowCorners(
                bias_current_min_a=490e-6,
                bias_current_max_a=510e-6,
                comparator_offset_abs_v=1e-3,
                divider_tolerance_fraction=0.01,
                supply_loss_fault=False,
            )
        )


def test_overlapping_short_and_valid_ranges_are_rejected() -> None:
    """No selectable divider can distinguish an overlapping electrical input."""

    with pytest.raises(ValueError, match="window|overlap|margin"):
        derive_hardware_window(
            RtdWindowCorners(
                bias_current_min_a=490e-6,
                bias_current_max_a=510e-6,
                short_max_ohm=100.0,
                valid_min_ohm=100.0,
                valid_max_ohm=194.1,
                open_min_ohm=300.0,
                comparator_offset_abs_v=1e-3,
                divider_tolerance_fraction=0.01,
                required_margin_fraction=0.20,
                supply_loss_fault=True,
            )
        )


def test_insufficient_component_margin_is_rejected() -> None:
    """A non-overlapping nominal range is still unsafe when its guard band vanishes."""

    with pytest.raises(ValueError, match="window|overlap|margin"):
        derive_hardware_window(
            RtdWindowCorners(
                bias_current_min_a=490e-6,
                bias_current_max_a=510e-6,
                short_max_ohm=99.9,
                valid_min_ohm=100.0,
                valid_max_ohm=194.1,
                open_min_ohm=194.2,
                comparator_offset_abs_v=1e-3,
                divider_tolerance_fraction=0.01,
                required_margin_fraction=0.20,
                supply_loss_fault=True,
            )
        )


@given(
    resistance_ohm=st.one_of(
        st.floats(min_value=0.0, max_value=10.0),
        st.floats(min_value=100.0, max_value=194.1),
        st.floats(min_value=300.0, max_value=1_000.0),
    ),
    vbias_v=st.floats(min_value=MAX31865_VBIAS_MIN_V, max_value=MAX31865_VBIAS_MAX_V),
    rref_scale=st.floats(min_value=0.999, max_value=1.001),
    comparator_offset_v=st.floats(min_value=-0.004, max_value=0.004),
    divider_error_fraction=st.floats(min_value=-0.01, max_value=0.01),
)
@settings(max_examples=250, deadline=10_000)
def test_max31865_divider_window_separates_rtd_fault_corners(
    resistance_ohm: float,
    vbias_v: float,
    rref_scale: float,
    comparator_offset_v: float,
    divider_error_fraction: float,
) -> None:
    """TLV3201 4 mV offset plus 1% dividers retain a 20% input margin."""

    window = derive_max31865_hardware_window(
        Max31865RtdWindowCorners(
            comparator_offset_abs_v=0.004,
            divider_tolerance_fraction=0.01,
        )
    )
    faulted = window.faulted(
        resistance_ohm,
        vbias_v=vbias_v,
        rref_ohm=430.0 * rref_scale,
        comparator_offset_v=comparator_offset_v,
        divider_error_fraction=divider_error_fraction,
    )
    if resistance_ohm <= 10.0 or resistance_ohm >= 300.0:
        assert faulted
    else:
        assert not faulted


@given(
    resistance_ohm=st.one_of(
        st.floats(min_value=0.0, max_value=10.0),
        st.floats(min_value=100.0, max_value=194.1),
        st.floats(min_value=300.0, max_value=1_000.0),
    ),
    vbias_v=st.floats(min_value=MAX31865_VBIAS_MIN_V, max_value=MAX31865_VBIAS_MAX_V),
    rref_scale=st.floats(min_value=0.999, max_value=1.001),
    reference_scale=st.floats(
        min_value=1.0 - REF2025_VBIAS_TOLERANCE_FRACTION,
        max_value=1.0 + REF2025_VBIAS_TOLERANCE_FRACTION,
    ),
    low_top_scale=st.floats(
        min_value=1.0 - RTD_WINDOW_RESISTOR_TOLERANCE_FRACTION,
        max_value=1.0 + RTD_WINDOW_RESISTOR_TOLERANCE_FRACTION,
    ),
    low_bottom_scale=st.floats(
        min_value=1.0 - RTD_WINDOW_RESISTOR_TOLERANCE_FRACTION,
        max_value=1.0 + RTD_WINDOW_RESISTOR_TOLERANCE_FRACTION,
    ),
    high_top_scale=st.floats(
        min_value=1.0 - RTD_WINDOW_RESISTOR_TOLERANCE_FRACTION,
        max_value=1.0 + RTD_WINDOW_RESISTOR_TOLERANCE_FRACTION,
    ),
    high_bottom_scale=st.floats(
        min_value=1.0 - RTD_WINDOW_RESISTOR_TOLERANCE_FRACTION,
        max_value=1.0 + RTD_WINDOW_RESISTOR_TOLERANCE_FRACTION,
    ),
    comparator_offset_v=st.floats(min_value=-0.004, max_value=0.004),
)
@settings(max_examples=300, deadline=10_000)
def test_captured_ref2025_divider_network_separates_every_rtd_corner(
    resistance_ohm: float,
    vbias_v: float,
    rref_scale: float,
    reference_scale: float,
    low_top_scale: float,
    low_bottom_scale: float,
    high_top_scale: float,
    high_bottom_scale: float,
    comparator_offset_v: float,
) -> None:
    """The placed reference/divider values preserve the RTD safety window."""

    low_threshold_v, high_threshold_v = populated_rtd_window_thresholds_v(
        reference_v=REF2025_VBIAS_NOMINAL_V * reference_scale,
        low_top_ohm=RTD_LOW_WINDOW_TOP_OHM * low_top_scale,
        low_bottom_ohm=RTD_LOW_WINDOW_BOTTOM_OHM * low_bottom_scale,
        high_top_ohm=RTD_HIGH_WINDOW_TOP_OHM * high_top_scale,
        high_bottom_ohm=RTD_HIGH_WINDOW_BOTTOM_OHM * high_bottom_scale,
    )
    sensed_v = max31865_rtd_voltage_v(
        resistance_ohm, vbias_v=vbias_v, rref_ohm=430.0 * rref_scale
    )
    faulted = sensed_v <= low_threshold_v + comparator_offset_v or sensed_v >= (
        high_threshold_v + comparator_offset_v
    )
    if resistance_ohm <= 10.0 or resistance_ohm >= 300.0:
        assert faulted
    else:
        assert not faulted


# This is intentionally a complete-trip window rather than a nominal divider.
# The selected divider, reference, offset, and temperature errors are bounded
# into these limits; the single-channel UV monitor makes no hysteresis claim.
_RTD_AVDD_MONITOR = RtdAvddMonitorCorners(trip_min_v=2.766, trip_max_v=2.870)


def test_rtd_avdd_uv_monitor_has_no_undefined_brownout_gap() -> None:
    """The UV trip precedes TLV3201's 2.7 V minimum without false trips."""

    validate_rtd_avdd_monitor(_RTD_AVDD_MONITOR)
    assert _RTD_AVDD_MONITOR.trip_min_v > RTD_WINDOW_COMPARATOR_MIN_SUPPLY_V
    assert _RTD_AVDD_MONITOR.trip_max_v < RTD_AVDD_NORMAL_MIN_V


@given(
    low_window_ok=st.booleans(),
    high_window_ok=st.booleans(),
    rtd_avdd_v=st.floats(min_value=0.0, max_value=3.4),
    trip_v=st.floats(min_value=2.766, max_value=2.870),
)
@settings(max_examples=200, deadline=10_000)
def test_default_high_rtd_fault_line_requires_every_normal_permission(
    low_window_ok: bool,
    high_window_ok: bool,
    rtd_avdd_v: float,
    trip_v: float,
) -> None:
    """The open-drain NAND may sink the fault line only in the safe window."""

    fault = rtd_window_fault_line_asserted(
        low_window_ok=low_window_ok,
        high_window_ok=high_window_ok,
        rtd_avdd_v=rtd_avdd_v,
        rail_monitor_trip_v=trip_v,
        rail_monitor_corners=_RTD_AVDD_MONITOR,
    )
    assert fault is (not (low_window_ok and high_window_ok and rtd_avdd_v > trip_v))


@given(
    low_window_ok=st.booleans(),
    high_window_ok=st.booleans(),
    rtd_avdd_v=st.floats(min_value=0.0, max_value=2.70),
    trip_v=st.floats(min_value=2.766, max_value=2.870),
)
@settings(max_examples=150, deadline=10_000)
def test_rtd_avdd_loss_always_releases_hardware_fault(
    low_window_ok: bool,
    high_window_ok: bool,
    rtd_avdd_v: float,
    trip_v: float,
) -> None:
    """No post-rail comparator state can mask loss below its rated supply."""

    assert rtd_window_fault_line_asserted(
        low_window_ok=low_window_ok,
        high_window_ok=high_window_ok,
        rtd_avdd_v=rtd_avdd_v,
        rail_monitor_trip_v=trip_v,
        rail_monitor_corners=_RTD_AVDD_MONITOR,
    )


@given(
    safety_3v3_present=st.booleans(),
    low_window_ok=st.booleans(),
    high_window_ok=st.booleans(),
    rtd_avdd_v=st.floats(min_value=0.0, max_value=3.4),
    trip_v=st.floats(min_value=2.766, max_value=2.870),
)
@settings(max_examples=200, deadline=10_000)
def test_global_safety_rail_loss_is_gate_driver_disable(
    safety_3v3_present: bool,
    low_window_ok: bool,
    high_window_ok: bool,
    rtd_avdd_v: float,
    trip_v: float,
) -> None:
    """A floating UCC21550 DIS is safe even if the latch loses 3.3 V."""

    shutdown = rtd_hardware_shutdown_asserted(
        safety_3v3_present=safety_3v3_present,
        low_window_ok=low_window_ok,
        high_window_ok=high_window_ok,
        rtd_avdd_v=rtd_avdd_v,
        rail_monitor_trip_v=trip_v,
        rail_monitor_corners=_RTD_AVDD_MONITOR,
    )
    if not safety_3v3_present:
        assert shutdown
