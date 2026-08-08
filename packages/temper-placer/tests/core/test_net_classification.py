"""Tests for core.net_classification module."""

import pytest

from temper_placer.core.net_classification import (
    GROUND_NET_PATTERNS,
    GROUND_PIN_PATTERNS,
    HV_NET_PATTERNS,
    HV_PIN_PATTERNS,
    POWER_NET_PATTERNS,
    POWER_PIN_PATTERNS,
    classify_net_type,
    is_clock_pin,
    is_ground_net,
    is_ground_pin,
    is_hv_net,
    is_hv_pin,
    is_power_net,
    is_power_pin,
    is_signal_net,
)


class TestNetClassification:
    """Tests for net classification predicates."""

    def test_is_ground_net_gnd(self):
        assert is_ground_net("GND") is True

    def test_is_ground_net_pgnd(self):
        assert is_ground_net("PGND") is True

    def test_is_ground_net_not_ground(self):
        assert is_ground_net("+5V") is False

    def test_is_power_net_vcc(self):
        assert is_power_net("VCC") is True

    def test_is_power_net_5v(self):
        assert is_power_net("+5V") is True

    def test_is_power_net_not_power(self):
        assert is_power_net("GND") is False

    def test_is_hv_net_ac_l(self):
        assert is_hv_net("AC_L") is True

    def test_is_hv_net_pe(self):
        assert is_hv_net("PE") is True

    def test_is_hv_net_not_hv(self):
        assert is_hv_net("+3V3") is False

    def test_is_signal_net(self):
        assert is_signal_net("SPI_MOSI") is True

    def test_is_signal_net_not_signal(self):
        assert is_signal_net("GND") is False

    def test_classify_net_type_ground(self):
        assert classify_net_type("GND") == "ground"

    def test_classify_net_type_power(self):
        assert classify_net_type("+5V") == "power"

    def test_classify_net_type_hv(self):
        assert classify_net_type("AC_L") == "hv"

    def test_classify_net_type_signal(self):
        assert classify_net_type("SPI_SCK") == "signal"

    def test_classify_net_type_precedence_ground_over_power(self):
        # GND patterns match before POWER patterns
        assert classify_net_type("GND") == "ground"


class TestPinClassification:
    """Tests for pin classification predicates."""

    def test_is_ground_pin_gnd(self):
        assert is_ground_pin("GND") is True

    def test_is_ground_pin_vss(self):
        assert is_ground_pin("VSS") is True

    def test_is_ground_pin_not_ground(self):
        assert is_ground_pin("VCC") is False

    def test_is_power_pin_vcc(self):
        assert is_power_pin("VCC") is True

    def test_is_power_pin_vin(self):
        assert is_power_pin("VIN") is True

    def test_is_power_pin_not_power(self):
        assert is_power_pin("GND") is False

    def test_is_hv_pin_ac_l(self):
        assert is_hv_pin("AC_L") is True

    def test_is_hv_pin_mains(self):
        assert is_hv_pin("MAINS") is True

    def test_is_hv_pin_not_hv(self):
        assert is_hv_pin("VCC") is False

    def test_is_clock_pin_clk(self):
        assert is_clock_pin("CLK") is True

    def test_is_clock_pin_xtal1(self):
        assert is_clock_pin("XTAL1") is True

    def test_is_clock_pin_not_clock(self):
        assert is_clock_pin("VCC") is False


class TestPatternConstants:
    """Verify the pattern constants exist and are non-empty."""

    def test_ground_net_patterns_nonempty(self):
        assert len(GROUND_NET_PATTERNS) > 0

    def test_power_net_patterns_nonempty(self):
        assert len(POWER_NET_PATTERNS) > 0

    def test_hv_net_patterns_nonempty(self):
        assert len(HV_NET_PATTERNS) > 0

    def test_ground_pin_patterns_nonempty(self):
        assert len(GROUND_PIN_PATTERNS) > 0

    def test_power_pin_patterns_nonempty(self):
        assert len(POWER_PIN_PATTERNS) > 0

    def test_hv_pin_patterns_nonempty(self):
        assert len(HV_PIN_PATTERNS) > 0
