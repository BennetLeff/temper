"""Coverage paydown v16: validation/rtd_safety, router_v6/constraints_spatial_index,
router_v6/constraints_design_rules (pure subset), validation/validation_gates.

Targets allowlist entries across:
- validation/rtd_safety.py (25): pure math, Rust-backed functions,
  dataclass logic
- router_v6/constraints_spatial_index.py (17): Pad, Track, Via, PCBGeometry,
  merge_collinear_tracks
- router_v6/constraints_design_rules.py (5): pure dict methods, factory
- validation/validation_gates.py (15): dataclass properties, ABC base,
  pure orchestration

All tests are pure Python (temper_thermal/temper_drc_rs Rust extensions
are pre-built and available); no fixtures, no temp files.
"""

from __future__ import annotations

import pytest

# ===========================================================================
# validation/rtd_safety.py
# ===========================================================================


class TestClassifyResistance:
    """Covers classify_resistance."""

    def test_short(self):
        from temper_placer.validation.rtd_safety import RtdStatus, classify_resistance

        assert classify_resistance(5.0) == RtdStatus.SHORT
        assert classify_resistance(0.0) == RtdStatus.SHORT

    def test_valid(self):
        from temper_placer.validation.rtd_safety import RtdStatus, classify_resistance

        assert classify_resistance(100.0) == RtdStatus.VALID
        assert classify_resistance(150.0) == RtdStatus.VALID
        assert classify_resistance(250.0) == RtdStatus.VALID

    def test_open(self):
        from temper_placer.validation.rtd_safety import RtdStatus, classify_resistance

        assert classify_resistance(301.0) == RtdStatus.OPEN
        assert classify_resistance(1000.0) == RtdStatus.OPEN


class TestClassifyCode:
    """Covers classify_code."""

    def test_short(self):
        from temper_placer.validation.rtd_safety import RtdStatus, classify_code

        assert classify_code(0, low=1000, high=10000) == RtdStatus.SHORT
        assert classify_code(1000, low=1000, high=10000) == RtdStatus.SHORT

    def test_valid(self):
        from temper_placer.validation.rtd_safety import RtdStatus, classify_code

        assert classify_code(5000, low=1000, high=10000) == RtdStatus.VALID
        assert classify_code(9999, low=1000, high=10000) == RtdStatus.VALID

    def test_open(self):
        from temper_placer.validation.rtd_safety import RtdStatus, classify_code

        assert classify_code(10000, low=1000, high=10000) == RtdStatus.OPEN
        assert classify_code(10001, low=1000, high=10000) == RtdStatus.OPEN


class TestResistanceToCode:
    """Covers resistance_to_code."""

    def test_zero(self):
        from temper_placer.validation.rtd_safety import resistance_to_code

        assert resistance_to_code(0.0) == 0

    def test_negative(self):
        from temper_placer.validation.rtd_safety import resistance_to_code

        assert resistance_to_code(-1.0) == 0

    def test_nominal(self):
        from temper_placer.validation.rtd_safety import resistance_to_code

        code = resistance_to_code(100.0)
        expected = int((100.0 / 430.0) * 32768)
        assert code == expected


class TestMax31865Current:
    """Covers max31865_rtd_current_a."""

    def test_nominal(self):
        from temper_placer.validation.rtd_safety import max31865_rtd_current_a

        current = max31865_rtd_current_a(100.0, vbias_v=2.0, rref_ohm=430.0)
        assert current > 0.0


class TestMax31865Voltage:
    """Covers max31865_rtd_voltage_v."""

    def test_nominal(self):
        from temper_placer.validation.rtd_safety import max31865_rtd_voltage_v

        voltage = max31865_rtd_voltage_v(100.0, vbias_v=2.0, rref_ohm=430.0)
        assert voltage > 0.0
        assert voltage < 2.0


class TestHardwareWindowVoltage:
    """Covers hardware_window_voltage."""

    def test_nominal(self):
        from temper_placer.validation.rtd_safety import hardware_window_voltage

        v = hardware_window_voltage(100.0, excitation_a=0.001)
        assert v == 0.1


class TestReferenceDividerVoltage:
    """Covers reference_divider_voltage_v."""

    def test_nominal(self):
        from temper_placer.validation.rtd_safety import reference_divider_voltage_v

        v = reference_divider_voltage_v(
            reference_v=1.25, top_ohm=61900.0, bottom_ohm=10000.0
        )
        expected = 1.25 * 10000.0 / (61900.0 + 10000.0)
        assert abs(v - expected) < 1e-6


class TestPopulatedWindowThresholds:
    """Covers populated_rtd_window_thresholds_v."""

    def test_defaults(self):
        from temper_placer.validation.rtd_safety import populated_rtd_window_thresholds_v

        low, high = populated_rtd_window_thresholds_v()
        assert low > 0.0
        assert high > low


class TestSpiRcRiseTime:
    """Covers spi_rc_rise_time_ns."""

    def test_nominal(self):
        from temper_placer.validation.rtd_safety import spi_rc_rise_time_ns

        t = spi_rc_rise_time_ns(
            driver_output_ohm=50.0,
            series_resistor_ohm=33.0,
            load_capacitance_pf=6.0,
        )
        assert t > 0.0


class TestThresholdCodes:
    """Covers threshold_codes."""

    def test_defaults(self):
        from temper_placer.validation.rtd_safety import threshold_codes

        low, high = threshold_codes()
        assert low > 0
        assert high > low


class TestThresholdAdcCodes:
    """Covers threshold_adc_codes."""

    def test_defaults(self):
        from temper_placer.validation.rtd_safety import threshold_adc_codes

        low, high = threshold_adc_codes()
        assert isinstance(low, int)
        assert isinstance(high, int)
        assert low < high


class TestValidateRtdAvddMonitor:
    """Covers validate_rtd_avdd_monitor."""

    def test_valid(self):
        from temper_placer.validation.rtd_safety import (
            RtdAvddMonitorCorners,
            validate_rtd_avdd_monitor,
        )

        corners = RtdAvddMonitorCorners(
            trip_min_v=2.8, trip_max_v=2.9,
            comparator_min_supply_v=2.70, normal_rail_min_v=2.97,
        )
        validate_rtd_avdd_monitor(corners)  # should not raise

    def test_rejects_disordered(self):
        from temper_placer.validation.rtd_safety import (
            RtdAvddMonitorCorners,
            validate_rtd_avdd_monitor,
        )

        corners = RtdAvddMonitorCorners(
            trip_min_v=3.0, trip_max_v=3.1,
            comparator_min_supply_v=2.70, normal_rail_min_v=2.97,
        )
        with pytest.raises(ValueError):
            validate_rtd_avdd_monitor(corners)


class TestRtdAvddRailOk:
    """Covers rtd_avdd_rail_ok."""

    def test_ok(self):
        from temper_placer.validation.rtd_safety import (
            RtdAvddMonitorCorners,
            rtd_avdd_rail_ok,
        )

        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_avdd_rail_ok(rtd_avdd_v=3.0, trip_v=2.85, corners=corners) is True

    def test_not_ok(self):
        from temper_placer.validation.rtd_safety import (
            RtdAvddMonitorCorners,
            rtd_avdd_rail_ok,
        )

        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_avdd_rail_ok(rtd_avdd_v=2.5, trip_v=2.85, corners=corners) is False


class TestRtdHardwareFaultAsserted:
    """Covers rtd_hardware_fault_asserted."""

    def test_no_fault(self):
        from temper_placer.validation.rtd_safety import rtd_hardware_fault_asserted

        assert rtd_hardware_fault_asserted(
            comparator_fault=False, comparator_supply_present=True
        ) is False

    def test_comparator_fault(self):
        from temper_placer.validation.rtd_safety import rtd_hardware_fault_asserted

        assert rtd_hardware_fault_asserted(
            comparator_fault=True, comparator_supply_present=True
        ) is True

    def test_supply_loss(self):
        from temper_placer.validation.rtd_safety import rtd_hardware_fault_asserted

        assert rtd_hardware_fault_asserted(
            comparator_fault=False, comparator_supply_present=False
        ) is True


class TestRtdWindowFaultLineAsserted:
    """Covers rtd_window_fault_line_asserted."""

    def test_no_fault(self):
        from temper_placer.validation.rtd_safety import (
            RtdAvddMonitorCorners,
            rtd_window_fault_line_asserted,
        )

        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_window_fault_line_asserted(
            low_window_ok=True, high_window_ok=True,
            rtd_avdd_v=3.0, rail_monitor_trip_v=2.85,
            rail_monitor_corners=corners,
        ) is False

    def test_avdd_low(self):
        from temper_placer.validation.rtd_safety import (
            RtdAvddMonitorCorners,
            rtd_window_fault_line_asserted,
        )

        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_window_fault_line_asserted(
            low_window_ok=True, high_window_ok=True,
            rtd_avdd_v=2.5, rail_monitor_trip_v=2.85,
            rail_monitor_corners=corners,
        ) is True

    def test_window_not_ok(self):
        from temper_placer.validation.rtd_safety import (
            RtdAvddMonitorCorners,
            rtd_window_fault_line_asserted,
        )

        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_window_fault_line_asserted(
            low_window_ok=False, high_window_ok=True,
            rtd_avdd_v=3.0, rail_monitor_trip_v=2.85,
            rail_monitor_corners=corners,
        ) is True


class TestRtdHardwareShutdownAsserted:
    """Covers rtd_hardware_shutdown_asserted."""

    def test_safety_present_no_fault(self):
        from temper_placer.validation.rtd_safety import (
            RtdAvddMonitorCorners,
            rtd_hardware_shutdown_asserted,
        )

        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_hardware_shutdown_asserted(
            safety_3v3_present=True,
            low_window_ok=True, high_window_ok=True,
            rtd_avdd_v=3.0, rail_monitor_trip_v=2.85,
            rail_monitor_corners=corners,
        ) is False

    def test_no_safety_power(self):
        from temper_placer.validation.rtd_safety import (
            RtdAvddMonitorCorners,
            rtd_hardware_shutdown_asserted,
        )

        corners = RtdAvddMonitorCorners(trip_min_v=2.8, trip_max_v=2.9)
        assert rtd_hardware_shutdown_asserted(
            safety_3v3_present=False,
            low_window_ok=True, high_window_ok=True,
            rtd_avdd_v=3.0, rail_monitor_trip_v=2.85,
            rail_monitor_corners=corners,
        ) is True


class TestSimulatedDigitalRtdService:
    """Covers SimulatedDigitalRtdService.bootstrap,
    SimulatedDigitalRtdService.threshold_register_writes,
    SimulatedDigitalRtdService.control_tick."""

    def test_bootstrap_ready(self):
        from temper_placer.validation.rtd_safety import SimulatedDigitalRtdService

        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        assert svc.ready is True
        assert svc.bootstrap_failed is False

    def test_bootstrap_not_ready(self):
        from temper_placer.validation.rtd_safety import SimulatedDigitalRtdService

        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=False)
        assert svc.ready is False
        assert svc.bootstrap_failed is True

    def test_threshold_register_writes(self):
        from temper_placer.validation.rtd_safety import (
            MAX31865_CONFIG_AUTOMATIC_FAULT,
            SimulatedDigitalRtdService,
        )

        svc = SimulatedDigitalRtdService()
        result = svc.threshold_register_writes()
        assert isinstance(result, tuple)
        assert len(result) == 3
        low_addr, high_addr, config = result
        assert low_addr[0] == 0x03
        assert high_addr[0] == 0x05
        assert config == MAX31865_CONFIG_AUTOMATIC_FAULT

    def test_control_tick_no_drdy(self):
        from temper_placer.validation.rtd_safety import SimulatedDigitalRtdService

        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        result = svc.control_tick(drdy=False)
        assert result is None
        assert svc.drdy_wait_ticks == 1

    def test_control_tick_timeout(self):
        from temper_placer.validation.rtd_safety import (
            RTD_DRDY_TIMEOUT_CONTROL_TICKS,
            RtdStatus,
            SimulatedDigitalRtdService,
        )

        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        for _ in range(RTD_DRDY_TIMEOUT_CONTROL_TICKS):
            result = svc.control_tick(drdy=False)
        assert result == RtdStatus.OPEN

    def test_control_tick_low_fault(self):
        from temper_placer.validation.rtd_safety import (
            MAX31865_FAULT_LOW_THRESHOLD,
            RtdStatus,
            SimulatedDigitalRtdService,
        )

        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        result = svc.control_tick(
            drdy=True, fault_status=MAX31865_FAULT_LOW_THRESHOLD
        )
        assert result == RtdStatus.SHORT

    def test_control_tick_high_fault(self):
        from temper_placer.validation.rtd_safety import (
            MAX31865_FAULT_HIGH_THRESHOLD,
            RtdStatus,
            SimulatedDigitalRtdService,
        )

        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        result = svc.control_tick(
            drdy=True, fault_status=MAX31865_FAULT_HIGH_THRESHOLD
        )
        assert result == RtdStatus.OPEN

    def test_control_tick_read_fail(self):
        from temper_placer.validation.rtd_safety import (
            RtdStatus,
            SimulatedDigitalRtdService,
        )

        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        result = svc.control_tick(drdy=True, read_ok=False)
        assert result == RtdStatus.OPEN

    def test_control_tick_bootstrap_fail(self):
        from temper_placer.validation.rtd_safety import (
            RtdStatus,
            SimulatedDigitalRtdService,
        )

        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=False)
        result = svc.control_tick(drdy=True)
        assert result == RtdStatus.OPEN

    def test_control_tick_already_latched(self):
        from temper_placer.validation.rtd_safety import (
            RTD_DRDY_TIMEOUT_CONTROL_TICKS,
            RtdStatus,
            SimulatedDigitalRtdService,
        )

        svc = SimulatedDigitalRtdService()
        svc.bootstrap(transport_ready=True)
        for _ in range(RTD_DRDY_TIMEOUT_CONTROL_TICKS):
            svc.control_tick(drdy=False)
        # Already latched -- further ticks return same
        result = svc.control_tick(drdy=True)
        assert result == RtdStatus.OPEN


class TestVirtualRtdBoard:
    """Covers VirtualRtdBoard.bootstrap, VirtualRtdBoard.control_tick."""

    def test_bootstrap(self):
        from temper_placer.validation.rtd_safety import VirtualRtdBoard

        vb = VirtualRtdBoard()
        vb.bootstrap(transport_ready=True)
        assert vb.shutdown is False
        assert vb.shutdown_bar is True

    def test_control_tick_normal(self):
        from temper_placer.validation.rtd_safety import VirtualRtdBoard

        vb = VirtualRtdBoard()
        vb.bootstrap(transport_ready=True)
        state = vb.control_tick(
            drdy=False, comparator_fault=False, comparator_supply_present=True
        )
        assert state.mcu_gpio15 is False
        assert state.rtd_hardware_fault is False

    def test_control_tick_comparator_fault(self):
        from temper_placer.validation.rtd_safety import VirtualRtdBoard

        vb = VirtualRtdBoard()
        vb.bootstrap(transport_ready=True)
        state = vb.control_tick(comparator_fault=True)
        assert state.rtd_hardware_fault is True

    def test_control_tick_fault_triggers_shutdown(self):
        from temper_placer.validation.rtd_safety import VirtualRtdBoard

        vb = VirtualRtdBoard()
        vb.bootstrap(transport_ready=True)
        state = vb.control_tick(comparator_fault=True)
        assert state.shutdown is True


class TestDeriveHardwareWindow:
    """Covers derive_hardware_window, RtdHardwareWindow.faulted."""

    @staticmethod
    def _safe_corners():
        from temper_placer.validation.rtd_safety import RtdWindowCorners

        return RtdWindowCorners(
            bias_current_min_a=0.9e-3,
            bias_current_max_a=1.1e-3,
            comparator_offset_abs_v=0.005,
            divider_tolerance_fraction=0.001,
            required_margin_fraction=0.10,
        )

    def test_derives_window(self):
        from temper_placer.validation.rtd_safety import (
            RtdHardwareWindow,
            derive_hardware_window,
        )

        corners = self._safe_corners()
        window = derive_hardware_window(corners)
        assert isinstance(window, RtdHardwareWindow)
        assert window.low_trip_voltage_v > 0
        assert window.high_trip_voltage_v > window.low_trip_voltage_v

    def test_faulted_short(self):
        from temper_placer.validation.rtd_safety import derive_hardware_window

        corners = self._safe_corners()
        window = derive_hardware_window(corners)
        assert window.faulted(5.0, excitation_a=1.0e-3) is True

    def test_faulted_valid(self):
        from temper_placer.validation.rtd_safety import derive_hardware_window

        corners = self._safe_corners()
        window = derive_hardware_window(corners)
        assert window.faulted(150.0, excitation_a=1.0e-3) is False

    def test_faulted_open(self):
        from temper_placer.validation.rtd_safety import derive_hardware_window

        corners = self._safe_corners()
        window = derive_hardware_window(corners)
        assert window.faulted(400.0, excitation_a=1.0e-3) is True

    def test_rejects_invalid(self):
        from temper_placer.validation.rtd_safety import (
            RtdWindowCorners,
            derive_hardware_window,
        )

        corners = RtdWindowCorners(
            bias_current_min_a=0.9e-3,
            bias_current_max_a=1.1e-3,
            comparator_offset_abs_v=0.20,
            divider_tolerance_fraction=0.10,
            required_margin_fraction=0.50,
        )
        with pytest.raises(ValueError):
            derive_hardware_window(corners)


class TestDeriveMax31865Window:
    """Covers derive_max31865_hardware_window,
    Max31865RtdHardwareWindow.faulted."""

    @staticmethod
    def _safe_corners():
        from temper_placer.validation.rtd_safety import Max31865RtdWindowCorners

        return Max31865RtdWindowCorners(
            comparator_offset_abs_v=0.005,
            divider_tolerance_fraction=0.001,
            required_margin_fraction=0.05,
        )

    def test_derives_window(self):
        from temper_placer.validation.rtd_safety import (
            Max31865RtdHardwareWindow,
            derive_max31865_hardware_window,
        )

        corners = self._safe_corners()
        window = derive_max31865_hardware_window(corners)
        assert isinstance(window, Max31865RtdHardwareWindow)
        assert window.low_trip_voltage_v > 0
        assert window.high_trip_voltage_v > window.low_trip_voltage_v

    def test_faulted_short(self):
        from temper_placer.validation.rtd_safety import derive_max31865_hardware_window

        corners = self._safe_corners()
        window = derive_max31865_hardware_window(corners)
        assert window.faulted(5.0, vbias_v=2.0, rref_ohm=430.0) is True

    def test_faulted_valid(self):
        from temper_placer.validation.rtd_safety import derive_max31865_hardware_window

        corners = self._safe_corners()
        window = derive_max31865_hardware_window(corners)
        assert window.faulted(150.0, vbias_v=2.0, rref_ohm=430.0) is False

    def test_faulted_open(self):
        from temper_placer.validation.rtd_safety import derive_max31865_hardware_window

        corners = self._safe_corners()
        window = derive_max31865_hardware_window(corners)
        assert window.faulted(500.0, vbias_v=2.0, rref_ohm=430.0) is True

    def test_rejects_invalid(self):
        from temper_placer.validation.rtd_safety import (
            Max31865RtdWindowCorners,
            derive_max31865_hardware_window,
        )

        corners = Max31865RtdWindowCorners(
            comparator_offset_abs_v=0.20,
            divider_tolerance_fraction=0.10,
            required_margin_fraction=0.90,
        )
        with pytest.raises(ValueError):
            derive_max31865_hardware_window(corners)


# ===========================================================================
# router_v6/constraints_spatial_index.py
# ===========================================================================


class TestTrack:
    """Covers Track.is_diff_pair_with, Track.midpoint, Track.to_segment."""

    def test_is_diff_pair_with(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import Track

        t1 = Track(Point(0, 0), Point(10, 0), 0.2, "N1", 0)
        t2 = Track(
            Point(0, 0), Point(10, 0), 0.2, "N2", 0,
            diff_pair_companion="N1",
        )
        t3 = Track(
            Point(0, 0), Point(10, 0), 0.2, "N3", 0,
            diff_pair_companion="N2",
        )
        # t1 has no companion -> cannot be a diff pair with anything
        assert t1.is_diff_pair_with(t2) is False
        # t2's companion is "N1", not "N3"
        assert t2.is_diff_pair_with(t3) is False
        # t3's companion is "N2" -> is_diff_pair_with(t2)
        assert t3.is_diff_pair_with(t2) is True

    def test_midpoint(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import Track

        t = Track(Point(0, 0), Point(10, 4), 0.2, "N1", 0)
        mid = t.midpoint()
        assert mid.x == 5.0
        assert mid.y == 2.0

    def test_to_segment(self):
        from temper_placer.router_v6.constraints_geometry import LineSegment, Point
        from temper_placer.router_v6.constraints_spatial_index import Track

        t = Track(Point(1, 2), Point(3, 4), 0.2, "N1", 0)
        seg = t.to_segment()
        assert isinstance(seg, LineSegment)
        assert seg.start.x == 1 and seg.start.y == 2
        assert seg.end.x == 3 and seg.end.y == 4


class TestPad:
    """Covers Pad.radius, Pad.rot_rect, Pad.conductive_layers."""

    @staticmethod
    def _make_pad(**kw):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import Pad

        defaults = dict(
            center=Point(5, 5), shape="rect", size=(2.0, 3.0),
            net="N1", layer=0,
        )
        defaults.update(kw)
        return Pad(**defaults)

    def test_radius(self):
        pad = self._make_pad()
        expected = (2.0**2 + 3.0**2) ** 0.5 / 2
        assert abs(pad.radius - expected) < 1e-9

    def test_rot_rect(self):
        from temper_placer.router_v6.constraints_geometry import RotatedRect

        pad = self._make_pad()
        rr = pad.rot_rect
        assert isinstance(rr, RotatedRect)

    def test_conductive_layers_not_pth(self):
        pad = self._make_pad()
        layers_set = {0, 1, 2, 3}
        assert pad.conductive_layers(layers_set) == frozenset({0})

    def test_conductive_layers_pth(self):
        pad = self._make_pad(is_pth=True)
        layers_set = {0, 1, 2, 3}
        assert pad.conductive_layers(layers_set) == frozenset(layers_set)

    def test_conductive_layers_explicit(self):
        pad = self._make_pad(layers=frozenset({0, 2}))
        layers_set = {0, 1, 2, 3}
        assert pad.conductive_layers(layers_set) == frozenset({0, 2})


class TestVia:
    """Covers Via.conductive_layers."""

    def test_legacy_through_via(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import Via

        v = Via(Point(5, 5), 0.6, 0.3, "N1")
        layers_set = {0, 1, 2, 3}
        assert v.conductive_layers(layers_set) == frozenset(layers_set)

    def test_explicit_layers(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import Via

        v = Via(Point(5, 5), 0.6, 0.3, "N1", layers=frozenset({0, 1}))
        layers_set = {0, 1, 2, 3}
        assert v.conductive_layers(layers_set) == frozenset({0, 1})


class TestPCBGeometry:
    """Covers PCBGeometry.add_pad, add_track, add_via, clear,
    get_geometry_by_id, rebuild_index, query_tracks_near, query_vias_near,
    query_pads_near."""

    @staticmethod
    def _make_track(x1=0, y1=0, x2=10, y2=0, net="N1", layer=0):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import Track

        return Track(Point(x1, y1), Point(x2, y2), 0.2, net, layer)

    @staticmethod
    def _make_via(x=5, y=5, net="N1"):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import Via

        return Via(Point(x, y), 0.6, 0.3, net)

    @staticmethod
    def _make_pad(x=5, y=5, net="N1", layer=0):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import Pad

        return Pad(Point(x, y), "rect", (2.0, 3.0), net, layer)

    def test_add_track(self):
        from temper_placer.router_v6.constraints_spatial_index import PCBGeometry

        pg = PCBGeometry()
        t = self._make_track()
        tid = pg.add_track(t)
        assert tid.startswith("track_")
        assert len(pg.tracks) == 1
        assert pg.tracks[0] is t

    def test_add_via(self):
        from temper_placer.router_v6.constraints_spatial_index import PCBGeometry

        pg = PCBGeometry()
        v = self._make_via()
        vid = pg.add_via(v)
        assert vid.startswith("via_")
        assert len(pg.vias) == 1

    def test_add_pad(self):
        from temper_placer.router_v6.constraints_spatial_index import PCBGeometry

        pg = PCBGeometry()
        p = self._make_pad()
        pid = pg.add_pad(p)
        assert pid.startswith("pad_")
        assert len(pg.pads) == 1

    def test_get_geometry_by_id(self):
        from temper_placer.router_v6.constraints_spatial_index import PCBGeometry

        pg = PCBGeometry()
        t = self._make_track()
        tid = pg.add_track(t)
        assert pg.get_geometry_by_id(tid) is t
        assert pg.get_geometry_by_id("nonexistent") is None

    def test_clear(self):
        from temper_placer.router_v6.constraints_spatial_index import PCBGeometry

        pg = PCBGeometry()
        pg.add_track(self._make_track())
        pg.add_via(self._make_via())
        pg.add_pad(self._make_pad())
        pg.clear()
        assert len(pg.tracks) == 0
        assert len(pg.vias) == 0
        assert len(pg.pads) == 0

    def test_rebuild_index_and_query_tracks(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import PCBGeometry

        pg = PCBGeometry()
        t1 = self._make_track(0, 0, 10, 0, "N1", 0)
        t2 = self._make_track(100, 100, 110, 100, "N2", 0)
        pg.add_track(t1)
        pg.add_track(t2)
        pg.rebuild_index()

        near = pg.query_tracks_near(Point(0, 0), 15.0)
        assert t1 in near
        assert t2 not in near

    def test_query_vias_near(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import PCBGeometry

        pg = PCBGeometry()
        v1 = self._make_via(5, 5, "N1")
        v2 = self._make_via(100, 100, "N2")
        pg.add_via(v1)
        pg.add_via(v2)
        pg.rebuild_index()

        near = pg.query_vias_near(Point(5, 5), 10.0)
        assert v1 in near
        assert v2 not in near

    def test_query_pads_near(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import PCBGeometry

        pg = PCBGeometry()
        p1 = self._make_pad(5, 5, "N1", 0)
        p2 = self._make_pad(100, 100, "N2", 0)
        pg.add_pad(p1)
        pg.add_pad(p2)
        pg.rebuild_index()

        near = pg.query_pads_near(Point(5, 5), 10.0)
        assert p1 in near
        assert p2 not in near


class TestMergeCollinearTracks:
    """Covers merge_collinear_tracks."""

    def test_empty(self):
        from temper_placer.router_v6.constraints_spatial_index import (
            merge_collinear_tracks,
        )

        assert merge_collinear_tracks([]) == []

    def test_merge_horizontal(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import (
            Track,
            merge_collinear_tracks,
        )

        tracks = [
            Track(Point(0, 0), Point(5, 0), 0.2, "N1", 0),
            Track(Point(5, 0), Point(10, 0), 0.2, "N1", 0),
        ]
        merged = merge_collinear_tracks(tracks)
        assert len(merged) == 1
        assert merged[0].start.x == 0
        assert merged[0].end.x == 10

    def test_merge_vertical(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import (
            Track,
            merge_collinear_tracks,
        )

        tracks = [
            Track(Point(0, 0), Point(0, 5), 0.2, "N1", 0),
            Track(Point(0, 5), Point(0, 10), 0.2, "N1", 0),
        ]
        merged = merge_collinear_tracks(tracks)
        assert len(merged) == 1
        assert merged[0].start.y == 0
        assert merged[0].end.y == 10

    def test_no_merge_different_nets(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import (
            Track,
            merge_collinear_tracks,
        )

        tracks = [
            Track(Point(0, 0), Point(5, 0), 0.2, "N1", 0),
            Track(Point(5, 0), Point(10, 0), 0.2, "N2", 0),
        ]
        merged = merge_collinear_tracks(tracks)
        assert len(merged) == 2

    def test_preserves_diagonal(self):
        from temper_placer.router_v6.constraints_geometry import Point
        from temper_placer.router_v6.constraints_spatial_index import (
            Track,
            merge_collinear_tracks,
        )

        tracks = [
            Track(Point(0, 0), Point(5, 5), 0.2, "N1", 0),
        ]
        merged = merge_collinear_tracks(tracks)
        assert len(merged) == 1


# ===========================================================================
# router_v6/constraints_design_rules.py
# ===========================================================================


class TestClearanceMatrix:
    """Covers ClearanceMatrix.set_net_class, add_net_class_rules,
    set_class_to_class_clearance, add_differential_pair, can_route_at,
    get_clearance, get_track_width, get_via_diameter, get_via_drill,
    is_differential_pair."""

    @staticmethod
    def _setup_matrix():
        from temper_placer.core.design_rules import NetClassRules
        from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

        m = ClearanceMatrix()
        rules = NetClassRules(
            name="Power", trace_width=0.5, clearance=0.8,
            via_diameter=1.0, via_drill=0.5, dru_priority=1,
        )
        m.add_net_class_rules(rules)
        m.set_net_class("NET1", "Power")
        m.set_net_class("NET2", "Signal")
        m.set_class_to_class_clearance("Power", "Signal", 1.0)
        return m

    def test_set_net_class(self):
        from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

        m = ClearanceMatrix()
        m.set_net_class("NET1", "Power")
        assert m._net_to_class["NET1"] == "Power"

    def test_add_net_class_rules(self):
        from temper_placer.core.design_rules import NetClassRules
        from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

        m = ClearanceMatrix()
        rules = NetClassRules(
            name="Power", trace_width=0.5, clearance=0.8,
            via_diameter=1.0, via_drill=0.5, dru_priority=1,
        )
        m.add_net_class_rules(rules)
        assert "Power" in m._net_class_rules
        assert m._net_class_rules["Power"].clearance == 0.8

    def test_set_class_to_class_clearance(self):
        from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

        m = ClearanceMatrix()
        m.set_class_to_class_clearance("Power", "Signal", 0.5)
        assert m._clearances[("Power", "Signal")] == 0.5
        assert m._clearances[("Signal", "Power")] == 0.5

    def test_add_differential_pair(self):
        m = self._setup_matrix()
        m.add_differential_pair("DP1", "DP2", 0.3)
        pair_key = frozenset(["DP1", "DP2"])
        assert pair_key in m._differential_pairs

    def test_can_route_at_no_zones(self):
        from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

        m = ClearanceMatrix()
        assert m.can_route_at("ANY_NET", 10.0, 20.0) is True

    def test_get_track_width(self):
        m = self._setup_matrix()
        assert m.get_track_width("NET1") == 0.5
        # Unknown net falls back to default
        assert m.get_track_width("UNKNOWN") == 0.2

    def test_get_via_diameter(self):
        m = self._setup_matrix()
        assert m.get_via_diameter("NET1") == 1.0

    def test_get_via_drill(self):
        m = self._setup_matrix()
        assert m.get_via_drill("NET1") == 0.5

    def test_is_differential_pair(self):
        m = self._setup_matrix()
        m.add_differential_pair("DP1", "DP2", 0.3)
        assert m.is_differential_pair("DP1", "DP2") is True
        assert m.is_differential_pair("DP1", "DP3") is False

    def test_get_clearance_baseline(self):
        m = self._setup_matrix()
        # NET1=Power, NET2=Signal, class-to-class clearance set to 1.0
        cl = m.get_clearance("NET1", "NET2")
        assert cl == 1.0

    def test_get_clearance_same_net(self):
        m = self._setup_matrix()
        cl = m.get_clearance("NET1", "NET1")
        assert cl >= 0


class TestZoneManager:
    """Covers ZoneManager.get_zone_at, get_clearance, can_route_net_at."""

    @staticmethod
    def _setup():
        from temper_placer.core.design_rules import NetClassRules
        from temper_placer.router_v6.constraints_design_rules import (
            ClearanceMatrix,
            RoutingZone,
            ZoneManager,
        )

        zones = [
            RoutingZone(
                name="TestZone",
                polygon=[(0, 0), (10, 0), (10, 10), (0, 10)],
                clearance_mm=0.5,
                allowed_net_classes={"Signal"},
            ),
        ]
        zm = ZoneManager(zones)
        m = ClearanceMatrix()
        rules = NetClassRules(
            name="Signal", trace_width=0.3, clearance=0.3,
            via_diameter=0.6, via_drill=0.3, dru_priority=0,
        )
        m.add_net_class_rules(rules)
        m.set_net_class("NET_SIG", "Signal")
        m.set_net_class("NET_PWR", "Power")
        return zm, m

    def test_get_zone_at_hit(self):
        zm, _ = self._setup()
        zone = zm.get_zone_at(5.0, 5.0)
        assert zone is not None
        assert zone.name == "TestZone"

    def test_get_zone_at_miss(self):
        zm, _ = self._setup()
        zone = zm.get_zone_at(100.0, 100.0)
        assert zone is None

    def test_get_clearance_in_zone(self):
        zm, m = self._setup()
        # In zone, clearance should be max(base, zone_clearance)
        cl = zm.get_clearance(5.0, 5.0, "NET_SIG", "NET_PWR", m)
        assert cl >= 0.3

    def test_get_clearance_outside_zone(self):
        zm, m = self._setup()
        cl = zm.get_clearance(100.0, 100.0, "NET_SIG", "NET_PWR", m)
        # Outside zone: just the baseline
        assert cl >= 0

    def test_can_route_net_at_allowed(self):
        zm, m = self._setup()
        # Signal net in Signal zone
        assert zm.can_route_net_at(5.0, 5.0, "NET_SIG", m) is True

    def test_can_route_net_at_denied(self):
        zm, m = self._setup()
        # Power net in Signal-only zone
        assert zm.can_route_net_at(5.0, 5.0, "NET_PWR", m) is False

    def test_can_route_net_at_unzoned(self):
        zm, m = self._setup()
        # Outside any zone -> allowed
        assert zm.can_route_net_at(100.0, 100.0, "NET_PWR", m) is True


class TestDesignRulesParserCreateDefault:
    """Covers DesignRulesParser.create_default."""

    def test_creates_default_matrix(self):
        from temper_placer.router_v6.constraints_design_rules import (
            ClearanceMatrix,
            DesignRulesParser,
        )

        dm = DesignRulesParser.create_default()
        assert isinstance(dm, ClearanceMatrix)
        assert len(dm._net_class_rules) > 0


# ===========================================================================
# validation/validation_gates.py
# ===========================================================================


class TestGateResult:
    """Covers GateResult.passed."""

    def test_passed_true(self):
        from temper_placer.validation.validation_gates import GateResult, GateStatus

        g = GateResult(gate_name="test", status=GateStatus.PASS)
        assert g.passed is True

    def test_passed_false(self):
        from temper_placer.validation.validation_gates import GateResult, GateStatus

        g = GateResult(gate_name="test", status=GateStatus.FAIL)
        assert g.passed is False

    def test_passed_skip(self):
        from temper_placer.validation.validation_gates import GateResult, GateStatus

        g = GateResult(gate_name="test", status=GateStatus.SKIP)
        assert g.passed is False

    def test_passed_pending(self):
        from temper_placer.validation.validation_gates import GateResult, GateStatus

        g = GateResult(gate_name="test", status=GateStatus.PENDING)
        assert g.passed is False


class TestValidationGateBase:
    """Covers ValidationGate.name, required_metrics, check."""

    def test_name(self):
        from temper_placer.validation.validation_gates import ValidationGate

        assert ValidationGate().name == "ValidationGate"

    def test_required_metrics(self):
        from temper_placer.validation.validation_gates import ValidationGate

        assert ValidationGate().required_metrics == []

    def test_check_raises(self):
        from temper_placer.validation.validation_gates import ValidationGate

        with pytest.raises(NotImplementedError):
            ValidationGate().check(None)


class TestPlacementCompleteGate:
    """Covers PlacementCompleteGate.name, required_metrics."""

    def test_name(self):
        from temper_placer.validation.validation_gates import PlacementCompleteGate

        assert PlacementCompleteGate().name == "placement_complete"

    def test_required_metrics(self):
        from temper_placer.validation.validation_gates import PlacementCompleteGate

        assert PlacementCompleteGate().required_metrics == [
            "overlap_loss", "boundary_loss",
            "hv_clearance_violations", "zone_violations",
        ]


class TestRoutingCompleteGate:
    """Covers RoutingCompleteGate.name, required_metrics."""

    def test_name(self):
        from temper_placer.validation.validation_gates import RoutingCompleteGate

        assert RoutingCompleteGate().name == "routing_complete"

    def test_required_metrics(self):
        from temper_placer.validation.validation_gates import RoutingCompleteGate

        assert RoutingCompleteGate().required_metrics == [
            "routing_completion_percent", "drc_errors",
        ]


class TestProductionReadyGate:
    """Covers ProductionReadyGate.name, required_metrics."""

    def test_name(self):
        from temper_placer.validation.validation_gates import ProductionReadyGate

        assert ProductionReadyGate().name == "production_ready"

    def test_required_metrics(self):
        from temper_placer.validation.validation_gates import ProductionReadyGate

        assert ProductionReadyGate().required_metrics == [
            "overlap_loss", "boundary_loss", "hv_clearance_violations",
            "zone_violations", "routing_completion_percent", "drc_errors",
            "creepage_estimate", "spice_gate_overshoot", "spice_power_ripple",
        ]


class TestValidatedGate:
    """Covers ValidatedGate.name, required_metrics."""

    def test_name(self):
        from temper_placer.validation.validation_gates import ValidatedGate

        assert ValidatedGate().name == "validated"

    def test_required_metrics(self):
        from temper_placer.validation.validation_gates import ValidatedGate

        assert ValidatedGate().required_metrics == [
            "failure_rate", "loss_cv",
        ]


class TestValidationGatesResult:
    """Covers ValidationGatesResult.all_passed, summary."""

    def test_all_passed_with_nones(self):
        from temper_placer.validation.validation_gates import ValidationGatesResult

        r = ValidationGatesResult()
        assert r.all_passed is False  # None = not passed

    def test_all_passed_true(self):
        from temper_placer.validation.validation_gates import (
            GateResult,
            GateStatus,
            ValidationGatesResult,
        )

        r = ValidationGatesResult(
            placement_complete=GateResult("pc", GateStatus.PASS),
            routing_complete=GateResult("rc", GateStatus.PASS),
            production_ready=GateResult("pr", GateStatus.PASS),
            validated=GateResult("v", GateStatus.PASS),
        )
        assert r.all_passed is True

    def test_all_passed_one_fail(self):
        from temper_placer.validation.validation_gates import (
            GateResult,
            GateStatus,
            ValidationGatesResult,
        )

        r = ValidationGatesResult(
            placement_complete=GateResult("pc", GateStatus.PASS),
            routing_complete=GateResult("rc", GateStatus.FAIL, message="fail"),
            production_ready=GateResult("pr", GateStatus.PASS),
            validated=GateResult("v", GateStatus.PASS),
        )
        assert r.all_passed is False

    def test_summary(self):
        from temper_placer.validation.validation_gates import (
            GateResult,
            GateStatus,
            ValidationGatesResult,
        )

        r = ValidationGatesResult(
            placement_complete=GateResult("pc", GateStatus.PASS),
            routing_complete=GateResult(
                "rc", GateStatus.FAIL, message="fail msg"
            ),
        )
        s = r.summary()
        assert "Placement Complete" in s
        assert "Routing Complete" in s
        assert "fail msg" in s
        assert "not checked" in s  # for the None entries


class TestCheckGate:
    """Covers check_gate (unknown name returns None)."""

    def test_unknown_name(self):
        from temper_placer.validation.validation_gates import check_gate

        assert check_gate(None, "nonexistent") is None
