"""
Tests for BusCohort and BusRegistry (temper-l4we.1).

Tests bus cohort data structure, registry, and automatic inference from netlists.
"""

import pytest

from temper_placer.core.bus_cohort import (
    BusCohortConstraint,
    BusRegistry,
)


class TestBusCohortConstraint:
    """Tests for BusCohortConstraint dataclass."""

    def test_bus_cohort_creation(self):
        """Should create a valid bus cohort."""
        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["SPI_CLK", "SPI_MOSI", "SPI_MISO", "SPI_CS"],
            pitch_mm=0.4,
            max_skew_mm=2.0,
        )

        assert bus.name == "SPI_BUS"
        assert len(bus.nets) == 4
        assert bus.pitch_mm == 0.4
        assert bus.max_skew_mm == 2.0
        assert bus.signal_count == 4

    def test_bus_cohort_defaults(self):
        """Should use default values when not specified."""
        bus = BusCohortConstraint(
            name="TEST_BUS",
            nets=["NET_A", "NET_B"],
        )

        assert bus.pitch_mm == 0.5
        assert bus.max_skew_mm == 2.0
        assert bus.allow_swapping is False

    def test_bus_cohort_validation_empty_nets(self):
        """Should raise error for empty nets."""
        with pytest.raises(ValueError, match="must contain at least one net"):
            BusCohortConstraint(name="EMPTY_BUS", nets=[])

    def test_bus_cohort_validation_negative_pitch(self):
        """Should raise error for negative pitch."""
        with pytest.raises(ValueError, match="pitch_mm must be positive"):
            BusCohortConstraint(
                name="INVALID_BUS",
                nets=["NET_A"],
                pitch_mm=-0.1,
            )

    def test_bus_cohort_validation_negative_skew(self):
        """Should raise error for negative skew."""
        with pytest.raises(ValueError, match="max_skew_mm must be non-negative"):
            BusCohortConstraint(
                name="INVALID_BUS",
                nets=["NET_A"],
                max_skew_mm=-1.0,
            )


class TestBusRegistry:
    """Tests for BusRegistry class."""

    def test_register_bus(self):
        """Should register a bus cohort."""
        registry = BusRegistry()
        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["SPI_CLK", "SPI_MOSI", "SPI_MISO"],
        )

        registry.register_bus(bus)

        assert "SPI_BUS" in registry.buses
        assert registry.buses["SPI_BUS"] is bus

    def test_get_bus_for_net_exists(self):
        """Should find bus containing the net."""
        registry = BusRegistry()
        bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["SPI_CLK", "SPI_MOSI", "SPI_MISO"],
        )
        registry.register_bus(bus)

        found = registry.get_bus_for_net("SPI_CLK")

        assert found is not None
        assert found.name == "SPI_BUS"
        assert "SPI_CLK" in found.nets

    def test_get_bus_for_net_not_exists(self):
        """Should return None for net not in any bus."""
        registry = BusRegistry()

        found = registry.get_bus_for_net("RANDOM_NET")

        assert found is None

    def test_reverse_lookup_populated(self):
        """Should populate reverse lookup map."""
        registry = BusRegistry()
        bus = BusCohortConstraint(
            name="I2C_BUS",
            nets=["I2C_SDA", "I2C_SCL"],
        )
        registry.register_bus(bus)

        assert registry._net_to_bus["I2C_SDA"] == "I2C_BUS"
        assert registry._net_to_bus["I2C_SCL"] == "I2C_BUS"


class TestBusInference:
    """Tests for automatic bus inference from netlists."""

    def test_infer_spi_bus(self):
        """Should detect SPI bus from net names."""
        registry = BusRegistry()
        nets = ["SPI_CLK", "SPI_MOSI", "SPI_MISO", "SPI_CS", "GND", "VCC"]

        inferred = registry.infer_buses_from_nets(nets)

        assert len(inferred) >= 1
        spi_bus = next((b for b in inferred if b.name == "SPI_BUS"), None)
        assert spi_bus is not None
        assert "SPI_CLK" in spi_bus.nets
        assert "SPI_MOSI" in spi_bus.nets
        assert "SPI_MISO" in spi_bus.nets
        assert "SPI_CS" in spi_bus.nets

    def test_infer_i2c_bus(self):
        """Should detect I2C bus from net names."""
        registry = BusRegistry()
        nets = ["I2C_SDA", "I2C_SCL", "GND", "VCC"]

        inferred = registry.infer_buses_from_nets(nets)

        assert len(inferred) >= 1
        i2c_bus = next((b for b in inferred if b.name == "I2C_BUS"), None)
        assert i2c_bus is not None
        assert "I2C_SDA" in i2c_bus.nets
        assert "I2C_SCL" in i2c_bus.nets

    def test_infer_jtag_bus(self):
        """Should detect JTAG bus from net names."""
        registry = BusRegistry()
        nets = ["JTAG_TCK", "JTAG_TMS", "JTAG_TDI", "JTAG_TDO", "GND"]

        inferred = registry.infer_buses_from_nets(nets)

        assert len(inferred) >= 1
        jtag_bus = next((b for b in inferred if b.name == "JTAG_BUS"), None)
        assert jtag_bus is not None
        assert len(jtag_bus.nets) == 4

    def test_infer_differential_pair(self):
        """Should detect differential pairs."""
        registry = BusRegistry()
        nets = ["USB_DP", "USB_DN", "HDMI_P", "HDMI_N"]

        inferred = registry.infer_buses_from_nets(nets)

        diff_buses = [b for b in inferred if b.name.startswith("DIFF_")]
        assert len(diff_buses) >= 2

    def test_infer_no_buses(self):
        """Should return empty list for non-bus nets."""
        registry = BusRegistry()
        nets = ["GND", "VCC", "NET_A", "NET_B"]

        inferred = registry.infer_buses_from_nets(nets)

        assert len(inferred) == 0

    def test_infer_single_spi_net(self):
        """Should not create SPI bus with only 1 SPI net."""
        registry = BusRegistry()
        nets = ["SPI_CLK", "GND", "VCC"]

        inferred = registry.infer_buses_from_nets(nets)

        spi_bus = next((b for b in inferred if b.name == "SPI_BUS"), None)
        assert spi_bus is None


class TestBusCohortIntegration:
    """Integration tests for bus cohort workflow."""

    def test_full_bus_workflow(self):
        """Test complete workflow: create bus, register, lookup."""
        registry = BusRegistry()

        spi_bus = BusCohortConstraint(
            name="SPI_BUS",
            nets=["SPI_CLK", "SPI_MOSI", "SPI_MISO", "SPI_CS"],
            pitch_mm=0.4,
            max_skew_mm=2.0,
        )

        registry.register_bus(spi_bus)

        for net in spi_bus.nets:
            found = registry.get_bus_for_net(net)
            assert found is not None
            assert found.name == "SPI_BUS"

        # Non-existent net
        assert registry.get_bus_for_net("RANDOM") is None

    def test_multiple_buses(self):
        """Should handle multiple bus types."""
        registry = BusRegistry()
        nets = [
            "SPI_CLK",
            "SPI_MOSI",
            "SPI_MISO",
            "I2C_SDA",
            "I2C_SCL",
            "GND",
            "VCC",
        ]

        inferred = registry.infer_buses_from_nets(nets)

        assert len(inferred) == 2
        bus_names = [b.name for b in inferred]
        assert "SPI_BUS" in bus_names
        assert "I2C_BUS" in bus_names
