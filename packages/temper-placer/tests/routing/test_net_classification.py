"""Tests for the canonical net classification helpers in routing/net_classification.py."""

from __future__ import annotations

from temper_placer.routing.net_classification import (
    GROUND_NET_PATTERNS,
    GROUND_PIN_PATTERNS,
    HV_NET_PATTERNS,
    HV_PIN_PATTERNS,
    POWER_NET_PATTERNS,
    POWER_PIN_PATTERNS,
    CLOCK_PIN_PATTERNS,
    classify_net_type,
    is_ground_net,
    is_ground_pin,
    is_hv_net,
    is_hv_pin,
    is_power_net,
    is_power_pin,
    is_signal_net,
    is_clock_pin,
)


class TestNetClassification:
    def test_is_ground_net_canonical_patterns(self):
        for name in ["GND", "PGND", "CGND", "AGND", "DGND", "VSS"]:
            assert is_ground_net(name), f"{name} should be ground"

    def test_is_ground_net_substring_match(self):
        # Pin names, slashes, mixed case
        assert is_ground_net("/GND_NET/")
        assert is_ground_net("gnd")
        assert is_ground_net("VSS_internal")

    def test_is_ground_net_negative(self):
        for name in ["+3V3", "VCC", "DATA1", "AC_L", "CLK"]:
            assert not is_ground_net(name), f"{name} should NOT be ground"

    def test_is_power_net_canonical_patterns(self):
        for name in ["+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"]:
            assert is_power_net(name), f"{name} should be power"

    def test_is_power_net_negative(self):
        for name in ["GND", "PGND", "DATA1", "AC_L"]:
            assert not is_power_net(name)

    def test_is_hv_net_canonical_patterns(self):
        for name in ["AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"]:
            assert is_hv_net(name)

    def test_is_hv_net_negative(self):
        for name in ["GND", "+3V3", "DATA1"]:
            assert not is_hv_net(name)

    def test_is_signal_net_is_inverse(self):
        # Anything that isn't ground/power/hv is signal
        for name in ["DATA1", "RX", "TX", "USB_DP", "I2C_SDA"]:
            assert is_signal_net(name)
        # But the canonical patterns are NOT signal
        for name in ["GND", "+3V3", "AC_L"]:
            assert not is_signal_net(name)

    def test_classify_net_type_precedence(self):
        # ground > power > hv > signal
        assert classify_net_type("GND") == "ground"
        assert classify_net_type("+3V3") == "power"
        assert classify_net_type("AC_L") == "hv"
        assert classify_net_type("DATA1") == "signal"
        # Ground wins over power when both match (e.g., "GND_VCC")
        assert classify_net_type("GND_VCC") == "ground"
        # Power wins over hv (e.g., "+3V3_HV" — hypothetical)
        assert classify_net_type("+3V3_HV") == "power"

    def test_classify_net_type_case_insensitive(self):
        assert classify_net_type("gnd") == "ground"
        assert classify_net_type("vcc") == "power"

    def test_classify_net_type_substring(self):
        # "GND" is a substring of "GND_PROBE"
        assert classify_net_type("GND_PROBE") == "ground"


class TestPinClassification:
    def test_is_ground_pin(self):
        for name in ["GND", "VSS", "AGND", "DGND", "PGND", "CGND"]:
            assert is_ground_pin(name)

    def test_is_power_pin(self):
        for name in ["VCC", "VDD", "VIN", "VOUT", "PVCC", "VBUS", "PWR"]:
            assert is_power_pin(name)

    def test_is_hv_pin(self):
        for name in ["AC_L", "AC_N", "PE", "HV", "MAINS", "RECT"]:
            assert is_hv_pin(name)

    def test_is_clock_pin(self):
        for name in ["CLK", "CLOCK", "XTAL1", "XTAL2", "OSC_IN", "OSC_OUT"]:
            assert is_clock_pin(name)

    def test_pin_names_distinct_from_net_names(self):
        # Pin names like "VCC" are power; net names like "+3V3" are power.
        # The patterns are intentionally different: pin names are short
        # (VCC, GND, CLK); net names have rail prefixes (+3V3, +15V).
        # Verify that pin "VCC" is power but net "VCC" is also power (overlap
        # is fine — substring match).
        assert is_power_pin("VCC")
        assert is_power_net("VCC")
        # But the inverse: net "+3V3" is power; pin "+3V3" is NOT (no pin
        # would be named "+3V3"; the pin would be "VCC" or "3V3").
        assert is_power_net("+3V3")
        assert not is_power_pin("+3V3")


class TestPatternSets:
    """Verify the pattern sets are immutable (frozenset) and match the
    canonical source in `core/net_types.py:284-288`."""

    def test_ground_net_patterns_match_canonical(self):
        assert GROUND_NET_PATTERNS == frozenset(
            {"GND", "PGND", "CGND", "AGND", "DGND", "VSS"}
        )

    def test_power_net_patterns_match_canonical(self):
        assert POWER_NET_PATTERNS == frozenset(
            {"+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"}
        )

    def test_hv_net_patterns_match_canonical(self):
        assert HV_NET_PATTERNS == frozenset(
            {"AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"}
        )

    def test_pin_patterns_are_frozensets(self):
        assert isinstance(GROUND_PIN_PATTERNS, frozenset)
        assert isinstance(POWER_PIN_PATTERNS, frozenset)
        assert isinstance(HV_PIN_PATTERNS, frozenset)
        assert isinstance(CLOCK_PIN_PATTERNS, frozenset)
