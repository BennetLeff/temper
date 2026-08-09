"""Tests for validation.rtd_safety module — pure math functions."""
import pytest

from temper_placer.validation.rtd_safety import (
    Max31865RtdHardwareWindow,
    Max31865RtdWindowCorners,
    RtdAvddMonitorCorners,
    RtdHardwareWindow,
    RtdStatus,
    RtdWindowCorners,
    SimulatedDigitalRtdService,
    classify_code,
    classify_resistance,
    derive_hardware_window,
    derive_max31865_hardware_window,
    hardware_window_voltage,
    max31865_rtd_current_a,
    max31865_rtd_voltage_v,
    populated_rtd_window_thresholds_v,
    reference_divider_voltage_v,
    resistance_to_code,
    rtd_avdd_rail_ok,
    rtd_hardware_fault_asserted,
    rtd_hardware_shutdown_asserted,
    rtd_window_fault_line_asserted,
    spi_rc_rise_time_ns,
    threshold_adc_codes,
    threshold_codes,
    validate_rtd_avdd_monitor,
)


class TestClassifyResistance:
    """Tests for classify_resistance."""

    def test_short(self):
        assert classify_resistance(5.0) == RtdStatus.SHORT
        assert classify_resistance(0.0) == RtdStatus.SHORT

    def test_valid(self):
        assert classify_resistance(100.0) == RtdStatus.VALID
        assert classify_resistance(150.0) == RtdStatus.VALID
        assert classify_resistance(250.0) == RtdStatus.VALID

    def test_open(self):
        assert classify_resistance(301.0) == RtdStatus.OPEN
        assert classify_resistance(1000.0) == RtdStatus.OPEN


class TestClassifyCode:
    """Tests for classify_code."""

    def test_short(self):
        assert classify_code(0, low=1000, high=10000) == RtdStatus.SHORT
        assert classify_code(999, low=1000, high=10000) == RtdStatus.SHORT
        assert classify_code(1000, low=1000, high=10000) == RtdStatus.SHORT  # <= low

    def test_valid(self):
        assert classify_code(1001, low=1000, high=10000) == RtdStatus.VALID
        assert classify_code(5000, low=1000, high=10000) == RtdStatus.VALID
        assert classify_code(9999, low=1000, high=10000) == RtdStatus.VALID

    def test_open(self):
        assert classify_code(10000, low=1000, high=10000) == RtdStatus.OPEN  # >= high
        assert classify_code(10001, low=1000, high=10000) == RtdStatus.OPEN


class TestResistanceToCode:
    """Tests for resistance_to_code."""

    def test_zero_resistance(self):
        assert resistance_to_code(0.0) == 0

    def test_negative_resistance(self):
        assert resistance_to_code(-1.0) == 0

    def test_nominal(self):
        code = resistance_to_code(100.0)
        # Expected: int((100/430)*32768) = int(7620.46...) = 7620
        expected = int((100.0 / 430.0) * 32768)
        assert code == expected


class TestMax31865Current:
    """Tests for max31865_rtd_current_a."""

    def test_nominal(self):
        current = max31865_rtd_current_a(100.0, vbias_v=2.0, rref_ohm=430.0)
        # I = VBIAS / (RREF + RTD) = 2.0 / (430 + 100) = ~0.00377 A
        assert current > 0.0


class TestMax31865Voltage:
    """Tests for max31865_rtd_voltage_v."""

    def test_nominal(self):
        voltage = max31865_rtd_voltage_v(100.0, vbias_v=2.0, rref_ohm=430.0)
        # V = VBIAS * RTD / (RREF + RTD) = 2.0 * 100 / 530 = ~0.377 V
        assert voltage > 0.0
        assert voltage < 2.0


class TestHardwareWindowVoltage:
    """Tests for hardware_window_voltage."""

    def test_nominal(self):
        v = hardware_window_voltage(100.0, excitation_a=0.001)
        assert v == 0.1  # 100 * 0.001 = 0.1


class TestReferenceDividerVoltage:
    """Tests for reference_divider_voltage_v."""

    def test_nominal(self):
        v = reference_divider_voltage_v(
            reference_v=1.25, top_ohm=61900.0, bottom_ohm=10000.0
        )
        # Divider: V * R_bottom / (R_top + R_bottom)
        expected = 1.25 * 10000.0 / (61900.0 + 10000.0)
        assert abs(v - expected) < 1e-6


class TestPopulatedWindowThresholds:
    """Tests for populated_rtd_window_thresholds_v."""

    def test_returns_tuple(self):
        low, high = populated_rtd_window_thresholds_v()
        assert low > 0.0
        assert high > low

    def test_scaled_reference(self):
        low, high = populated_rtd_window_thresholds_v(reference_v=2.0)
        assert low > 0.0


class TestSpiRcRiseTime:
    """Tests for spi_rc_rise_time_ns."""

    def test_nominal(self):
        t = spi_rc_rise_time_ns(
            driver_output_ohm=50.0,
            series_resistor_ohm=33.0,
            load_capacitance_pf=6.0,
        )
        # 2.2 * R * C = 2.2 * (50+33) * 6e-12 = 2.2 * 83 * 6 ps
        # ps to ns: / 1000
        assert t > 0.0


class TestThresholdCodes:
    """Tests for threshold_codes."""

    def test_returns_tuple(self):
        low, high = threshold_codes()
        assert low > 0
        assert high > low

    def test_custom_params(self):
        low, high = threshold_codes(
            rref_ohm=400.0, short_ohm=10.0, open_ohm=300.0
        )
        assert low > 0
        assert high > low


class TestThresholdAdcCodes:
    """Tests for threshold_adc_codes."""

    def test_returns_ints(self):
        low, high = threshold_adc_codes()
        assert isinstance(low, int)
        assert isinstance(high, int)
        assert low < high


class TestRtdAvddMonitor:
    """Tests for validate_rtd_avdd_monitor and rtd_avdd_rail_ok."""

    def test_valid_monitor(self):
        corners = RtdAvddMonitorCorners(
            trip_min_v=2.8,
            trip_max_v=2.9,
            comparator_min_supply_v=2.70,
            normal_rail_min_v=2.97,
        )
        validate_rtd_avdd_monitor(corners)  # should not raise

    def test_invalid_monitor_disordered_limits(self):
        corners = RtdAvddMonitorCorners(
            trip_min_v=3.0,  # trip > normal rail min
            trip_max_v=3.1,
            comparator_min_supply_v=2.70,
            normal_rail_min_v=2.97,
        )
        with pytest.raises(ValueError):
            validate_rtd_avdd_monitor(corners)

    def test_rail_ok(self):
        corners = RtdAvddMonitorCorners(
            trip_min_v=2.8,
            trip_max_v=2.9,
        )
        assert rtd_avdd_rail_ok(rtd_avdd_v=3.0, trip_v=2.85, corners=corners) is True

    def test_rail_not_ok(self):
        corners = RtdAvddMonitorCorners(
            trip_min_v=2.8,
            trip_max_v=2.9,
        )
        assert rtd_avdd_rail_ok(rtd_avdd_v=2.5, trip_v=2.85, corners=corners) is False


class TestRtdFaultSignals:
    """Tests for fault signal functions."""

    def test_hardware_fault_not_asserted(self):
        assert rtd_hardware_fault_asserted(
            comparator_fault=False, comparator_supply_present=True
        ) is False

    def test_hardware_fault_comparator_fault(self):
        assert rtd_hardware_fault_asserted(
            comparator_fault=True, comparator_supply_present=True
        ) is True

    def test_hardware_fault_supply_loss(self):
        assert rtd_hardware_fault_asserted(
            comparator_fault=False, comparator_supply_present=False
        ) is True

    def test_window_fault_no_fault(self):
        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_window_fault_line_asserted(
            low_window_ok=True,
            high_window_ok=True,
            rtd_avdd_v=3.0,
            rail_monitor_trip_v=2.85,
            rail_monitor_corners=corners,
        ) is False

    def test_window_fault_avdd_low(self):
        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_window_fault_line_asserted(
            low_window_ok=True,
            high_window_ok=True,
            rtd_avdd_v=2.5,
            rail_monitor_trip_v=2.85,
            rail_monitor_corners=corners,
        ) is True

    def test_shutdown_with_safety_power(self):
        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_hardware_shutdown_asserted(
            safety_3v3_present=True,
            low_window_ok=True,
            high_window_ok=True,
            rtd_avdd_v=3.0,
            rail_monitor_trip_v=2.85,
            rail_monitor_corners=corners,
        ) is False

    def test_shutdown_no_safety_power(self):
        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_hardware_shutdown_asserted(
            safety_3v3_present=False,
            low_window_ok=True,
            high_window_ok=True,
            rtd_avdd_v=3.0,
            rail_monitor_trip_v=2.85,
            rail_monitor_corners=corners,
        ) is True


class TestDeriveHardwareWindow:
    """Tests for derive_hardware_window."""

    def test_derives_default_window(self):
        """Use default corner values known to satisfy margins."""
        corners = RtdWindowCorners(
            bias_current_min_a=0.9e-3,
            bias_current_max_a=1.1e-3,
            comparator_offset_abs_v=0.005,  # tighter offset
            divider_tolerance_fraction=0.001,  # tighter tolerance
            required_margin_fraction=0.10,  # lower margin requirement
        )
        window = derive_hardware_window(corners)
        assert isinstance(window, RtdHardwareWindow)
        assert window.low_trip_voltage_v > 0
        assert window.high_trip_voltage_v > window.low_trip_voltage_v

    def test_fault_short(self):
        corners = RtdWindowCorners(
            bias_current_min_a=0.9e-3,
            bias_current_max_a=1.1e-3,
            comparator_offset_abs_v=0.005,
            divider_tolerance_fraction=0.001,
            required_margin_fraction=0.10,
        )
        window = derive_hardware_window(corners)
        assert window.faulted(5.0, excitation_a=1.0e-3) is True

    def test_rejects_invalid(self):
        """Invalid corners should raise ValueError."""
        corners = RtdWindowCorners(
            bias_current_min_a=0.9e-3,
            bias_current_max_a=1.1e-3,
            comparator_offset_abs_v=0.20,  # very loose, margin will fail
            divider_tolerance_fraction=0.10,
            required_margin_fraction=0.50,
        )
        with pytest.raises(ValueError):
            derive_hardware_window(corners)


class TestDeriveMax31865Window:
    """Tests for derive_max31865_hardware_window."""

    def test_derives_max31865_window(self):
        corners = Max31865RtdWindowCorners(
            comparator_offset_abs_v=0.005,
            divider_tolerance_fraction=0.001,
            required_margin_fraction=0.05,
        )
        window = derive_max31865_hardware_window(corners)
        assert isinstance(window, Max31865RtdHardwareWindow)
        assert window.low_trip_voltage_v > 0
        assert window.high_trip_voltage_v > window.low_trip_voltage_v

    def test_fault_valid(self):
        corners = Max31865RtdWindowCorners(
            comparator_offset_abs_v=0.005,
            divider_tolerance_fraction=0.001,
            required_margin_fraction=0.05,
        )
        window = derive_max31865_hardware_window(corners)
        assert window.faulted(
            150.0, vbias_v=2.0, rref_ohm=430.0
        ) is False

    def test_rejects_invalid_margin(self):
        corners = Max31865RtdWindowCorners(
            comparator_offset_abs_v=0.20,
            divider_tolerance_fraction=0.10,
            required_margin_fraction=0.90,
        )
        with pytest.raises(ValueError):
            derive_max31865_hardware_window(corners)


class TestSimulatedDigitalRtdService:
    """Tests for SimulatedDigitalRtdService."""

    def test_bootstrap_ready(self):
        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        assert svc.ready is True
        assert svc.bootstrap_failed is False

    def test_bootstrap_not_ready(self):
        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=False)
        assert svc.ready is False
        assert svc.bootstrap_failed is True

    def test_threshold_register_writes(self):
        svc = SimulatedDigitalRtdService()
        result = svc.threshold_register_writes()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_control_tick_drdy(self):
        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        result = svc.control_tick(drdy=True)
        assert result is None  # no fault yet

    def test_control_tick_timeout(self):
        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        # Tick until timeout
        for _ in range(10):
            result = svc.control_tick(drdy=False)
        assert result == RtdStatus.OPEN

    def test_control_tick_already_latched(self):
        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        # latch a fault
        for _ in range(10):
            svc.control_tick(drdy=False)
        # further ticks should return same fault
        result = svc.control_tick(drdy=True)
        assert result == RtdStatus.OPEN
