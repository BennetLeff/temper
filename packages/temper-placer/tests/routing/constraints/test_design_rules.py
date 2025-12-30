"""Tests for design rules parsing and ClearanceMatrix.

Part of temper-lueu.1
"""

import pytest

from temper_placer.routing.constraints.design_rules import (
    ClearanceMatrix,
    DesignRulesParser,
)
from temper_placer.core.design_rules import NetClassRules


class TestClearanceMatrix:
    """Tests for ClearanceMatrix."""

    def test_default_clearance(self):
        """Test default clearance for unknown nets."""
        matrix = ClearanceMatrix()
        clearance = matrix.get_clearance("UNKNOWN_NET1", "UNKNOWN_NET2")
        assert clearance == 0.2  # default

    def test_net_class_clearance(self):
        """Test clearance with net class rules."""
        matrix = ClearanceMatrix()
        power_rules = NetClassRules(name="Power", trace_width=1.0, clearance=0.5)
        matrix.add_net_class_rules(power_rules)
        matrix.set_net_class("VCC", "Power")
        matrix.set_net_class("VDD", "Power")

        clearance = matrix.get_clearance("VCC", "VDD")
        assert clearance == 0.5

    def test_class_to_class_clearance(self):
        """Test explicit class-to-class clearance."""
        matrix = ClearanceMatrix()

        power_rules = NetClassRules(name="Power", trace_width=1.0, clearance=0.5)
        signal_rules = NetClassRules(name="Signal", trace_width=0.2, clearance=0.15)

        matrix.add_net_class_rules(power_rules)
        matrix.add_net_class_rules(signal_rules)
        matrix.set_class_to_class_clearance("Power", "Signal", 0.4)

        matrix.set_net_class("VCC", "Power")
        matrix.set_net_class("SIG1", "Signal")

        clearance = matrix.get_clearance("VCC", "SIG1")
        assert clearance == 0.4

    def test_symmetric_clearance(self):
        """Test clearance is symmetric."""
        matrix = ClearanceMatrix()
        matrix.set_class_to_class_clearance("A", "B", 0.35)

        matrix.set_net_class("NET_A", "A")
        matrix.set_net_class("NET_B", "B")

        c1 = matrix.get_clearance("NET_A", "NET_B")
        c2 = matrix.get_clearance("NET_B", "NET_A")
        assert c1 == c2 == 0.35

    def test_track_width_lookup(self):
        """Test track width lookup."""
        matrix = ClearanceMatrix()
        power_rules = NetClassRules(name="Power", trace_width=1.0, clearance=0.5)
        matrix.add_net_class_rules(power_rules)
        matrix.set_net_class("VCC", "Power")

        width = matrix.get_track_width("VCC")
        assert width == 1.0

    def test_default_track_width(self):
        """Test default track width for unknown nets."""
        matrix = ClearanceMatrix()
        width = matrix.get_track_width("UNKNOWN_NET")
        assert width == 0.2

    def test_via_diameter_lookup(self):
        """Test via diameter lookup."""
        matrix = ClearanceMatrix()
        power_rules = NetClassRules(
            name="Power",
            trace_width=1.0,
            clearance=0.5,
            via_diameter=1.0,
            via_drill=0.5,
        )
        matrix.add_net_class_rules(power_rules)
        matrix.set_net_class("VCC", "Power")

        diameter = matrix.get_via_diameter("VCC")
        drill = matrix.get_via_drill("VCC")
        assert diameter == 1.0
        assert drill == 0.5


class TestDesignRulesParserClassification:
    """Tests for net auto-classification."""

    def test_ground_net_classification(self):
        """Test ground nets are correctly classified."""
        ground_nets = ["GND", "AGND", "DGND", "PGND", "VSS", "GROUND"]
        for net in ground_nets:
            assert DesignRulesParser._classify_net(net) == "GND"

    def test_power_net_classification(self):
        """Test power nets are correctly classified."""
        power_nets = ["VCC", "VDD", "+3.3V", "+5V", "+12V", "VBAT", "VIN"]
        for net in power_nets:
            assert DesignRulesParser._classify_net(net) == "Power"

    def test_high_speed_classification(self):
        """Test high-speed nets are correctly classified."""
        hs_nets = ["SPI_CLK", "SPI_MOSI", "I2C_SDA", "USB_D+", "JTAG_TCK"]
        for net in hs_nets:
            assert DesignRulesParser._classify_net(net) == "HighSpeed"

    def test_signal_default_classification(self):
        """Test unknown nets default to Signal."""
        signal_nets = ["NET1", "RANDOM_SIGNAL", "GPIO_5"]
        for net in signal_nets:
            assert DesignRulesParser._classify_net(net) == "Signal"


class TestDesignRulesParserDefaults:
    """Tests for default rules creation."""

    def test_create_default_matrix(self):
        """Test creating default ClearanceMatrix."""
        matrix = DesignRulesParser.create_default()

        assert isinstance(matrix, ClearanceMatrix)
        # Should have Temper net classes
        assert "Power" in matrix._net_class_rules
        assert "GND" in matrix._net_class_rules
        assert "Signal" in matrix._net_class_rules

    def test_default_cross_class_clearances(self):
        """Test default class-to-class clearances are set."""
        matrix = DesignRulesParser.create_default()

        matrix.set_net_class("VCC", "Power")
        matrix.set_net_class("VDD", "Power")

        # Power-to-Power should have explicit clearance
        clearance = matrix.get_clearance("VCC", "VDD")
        assert clearance == 0.5
