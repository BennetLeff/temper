"""
Unit tests for synthetic netlist generation (temper-1my.3.3).

Tests cover:
- 200-component netlist generation
- Component distribution (resistors, caps, ICs, etc.)
- Connectivity patterns (power, signal, bus nets)
- Realistic fanout and net topology
"""

import pytest
from temper_placer.fixtures.synthetic import (
    generate_200_component_netlist,
    ComponentDistribution,
    NetTopology,
)


# =============================================================================
# Component Distribution Tests
# =============================================================================


class TestGenerate200ComponentNetlist:
    """Tests for 200-component netlist generator."""

    def test_component_count(self):
        """Test that exactly 200 components are generated."""
        netlist = generate_200_component_netlist(seed=42)

        assert len(netlist.components) == 200

    def test_component_distribution(self):
        """Test component type distribution matches spec."""
        netlist = generate_200_component_netlist(seed=42)

        # Count by footprint type
        resistors = [c for c in netlist.components if c.footprint in ["0603", "0805", "2512"]]
        capacitors = [c for c in netlist.components if c.footprint in ["C_0603", "C_0805", "C_1206"]]
        ics = [c for c in netlist.components if c.footprint in ["QFN-56", "SOIC-8", "TSSOP-20"]]
        inductors = [c for c in netlist.components if "Inductor" in c.footprint or c.footprint in ["L_0805", "L_1210"]]
        connectors = [c for c in netlist.components if "Connector" in c.footprint or "JST" in c.footprint]
        discretes = [c for c in netlist.components if c.footprint in ["SOT-23", "SOD-123", "TO-220-3"]]

        # Expected distribution: 80 resistors, 50 caps, 25 ICs, 10 inductors, 15 connectors, 20 discretes
        assert 75 <= len(resistors) <= 85, f"Expected ~80 resistors, got {len(resistors)}"
        assert 45 <= len(capacitors) <= 55, f"Expected ~50 caps, got {len(capacitors)}"
        assert 20 <= len(ics) <= 30, f"Expected ~25 ICs, got {len(ics)}"
        assert 8 <= len(inductors) <= 12, f"Expected ~10 inductors, got {len(inductors)}"
        assert 12 <= len(connectors) <= 18, f"Expected ~15 connectors, got {len(connectors)}"
        assert 15 <= len(discretes) <= 25, f"Expected ~20 discretes, got {len(discretes)}"

    def test_component_refs_unique(self):
        """Test all component refs are unique."""
        netlist = generate_200_component_netlist(seed=42)

        refs = [c.ref for c in netlist.components]
        assert len(refs) == len(set(refs)), "Component refs must be unique"

    def test_component_refs_follow_convention(self):
        """Test component refs follow naming conventions (R1, C1, U1, etc.)."""
        netlist = generate_200_component_netlist(seed=42)

        for comp in netlist.components:
            # Should start with letter followed by number
            assert len(comp.ref) >= 2
            assert comp.ref[0].isalpha()
            assert comp.ref[1:].isdigit()

    def test_all_components_have_valid_footprints(self, footprint_library):
        """Test all components use footprints from library."""
        netlist = generate_200_component_netlist(seed=42)

        for comp in netlist.components:
            assert comp.footprint in footprint_library, \
                f"Component {comp.ref} has unknown footprint: {comp.footprint}"

    def test_all_components_have_bounds(self):
        """Test all components have valid bounds."""
        netlist = generate_200_component_netlist(seed=42)

        for comp in netlist.components:
            assert comp.bounds is not None
            assert len(comp.bounds) == 2
            assert comp.bounds[0] > 0  # width > 0
            assert comp.bounds[1] > 0  # height > 0


# =============================================================================
# Connectivity Tests
# =============================================================================


class TestNetlistConnectivity:
    """Tests for netlist connectivity patterns."""

    def test_has_power_nets(self):
        """Test that power nets exist (GND, VCC, etc.)."""
        netlist = generate_200_component_netlist(seed=42)

        net_names = [net.name for net in netlist.nets]

        # Should have ground and power rails
        assert "GND" in net_names
        assert any("VCC" in name or "+3V3" in name or "+5V" in name for name in net_names)

    def test_power_nets_high_fanout(self):
        """Test that power nets have high fanout (many connections)."""
        netlist = generate_200_component_netlist(seed=42)

        gnd_net = next((net for net in netlist.nets if net.name == "GND"), None)
        assert gnd_net is not None

        # GND should connect to many components (at least 40 out of 200)
        assert len(gnd_net.pins) >= 40, \
            f"GND should have high fanout, got {len(gnd_net.pins)} pins"

    def test_signal_nets_low_fanout(self):
        """Test that signal nets have low fanout (2-4 pins)."""
        netlist = generate_200_component_netlist(seed=42)

        signal_nets = [net for net in netlist.nets if net.name.startswith("SIG_")]

        # Most signal nets should have 2-4 pins
        low_fanout_count = sum(1 for net in signal_nets if 2 <= len(net.pins) <= 4)

        assert low_fanout_count >= len(signal_nets) * 0.8, \
            "At least 80% of signal nets should have 2-4 pins"

    def test_has_bus_nets(self):
        """Test that bus nets exist (I2C, SPI)."""
        netlist = generate_200_component_netlist(seed=42)

        net_names = [net.name for net in netlist.nets]

        # Should have I2C bus
        assert "I2C_SDA" in net_names or "SDA" in net_names
        assert "I2C_SCL" in net_names or "SCL" in net_names

    def test_bus_nets_medium_fanout(self):
        """Test that bus nets have medium fanout (5-10 pins)."""
        netlist = generate_200_component_netlist(seed=42)

        i2c_nets = [net for net in netlist.nets
                    if "I2C" in net.name or "SDA" in net.name or "SCL" in net.name]

        for net in i2c_nets:
            assert 5 <= len(net.pins) <= 15, \
                f"Bus net {net.name} should have 5-15 pins, got {len(net.pins)}"

    def test_all_components_connected(self):
        """Test that all components are connected to at least one net."""
        netlist = generate_200_component_netlist(seed=42)

        # Get all component refs mentioned in nets
        connected_refs = set()
        for net in netlist.nets:
            for comp_ref, _ in net.pins:
                connected_refs.add(comp_ref)

        component_refs = {c.ref for c in netlist.components}

        # Most components should be connected (allow some unconnected test points)
        connection_rate = len(connected_refs) / len(component_refs)
        assert connection_rate >= 0.9, \
            f"At least 90% of components should be connected, got {connection_rate:.1%}"

    def test_net_count_reasonable(self):
        """Test that number of nets is reasonable for 200 components."""
        netlist = generate_200_component_netlist(seed=42)

        # Rule of thumb: nets ~= components / 2 (very rough estimate)
        # For 200 components, expect 80-120 nets
        assert 80 <= len(netlist.nets) <= 120, \
            f"Expected 80-120 nets for 200 components, got {len(netlist.nets)}"


# =============================================================================
# Determinism and Seeding Tests
# =============================================================================


class TestNetlistDeterminism:
    """Tests for reproducibility with seeds."""

    def test_same_seed_same_netlist(self):
        """Test that same seed produces identical netlist."""
        netlist1 = generate_200_component_netlist(seed=42)
        netlist2 = generate_200_component_netlist(seed=42)

        # Same number of components
        assert len(netlist1.components) == len(netlist2.components)

        # Same component refs
        refs1 = [c.ref for c in netlist1.components]
        refs2 = [c.ref for c in netlist2.components]
        assert refs1 == refs2

        # Same number of nets
        assert len(netlist1.nets) == len(netlist2.nets)

    def test_different_seed_different_netlist(self):
        """Test that different seeds produce different netlists."""
        netlist1 = generate_200_component_netlist(seed=42)
        netlist2 = generate_200_component_netlist(seed=123)

        # Component refs are deterministic, but net connectivity should differ
        # Check that net pin assignments differ
        net1_pins = {net.name: sorted(net.pins) for net in netlist1.nets}
        net2_pins = {net.name: sorted(net.pins) for net in netlist2.nets}

        # At least some nets should have different pin assignments
        assert net1_pins != net2_pins


# =============================================================================
# Board Dimensions Tests
# =============================================================================


class TestBoardDimensions:
    """Tests for board dimensions returned with netlist."""

    def test_returns_board(self):
        """Test that generator returns board along with netlist."""
        result = generate_200_component_netlist(seed=42, return_board=True)

        assert hasattr(result, 'netlist')
        assert hasattr(result, 'board')

    def test_board_dimensions(self):
        """Test that board has correct dimensions (150mm x 100mm)."""
        result = generate_200_component_netlist(seed=42, return_board=True)

        assert result.board.width == pytest.approx(150.0, abs=1.0)
        assert result.board.height == pytest.approx(100.0, abs=1.0)


# =============================================================================
# Component Pin Tests
# =============================================================================


class TestComponentPins:
    """Tests for component pins in generated netlist."""

    def test_components_have_pins(self):
        """Test that components have at least minimal pins."""
        netlist = generate_200_component_netlist(seed=42)

        # Most components should have at least 2 pins
        components_with_pins = [c for c in netlist.components if len(c.pins) >= 2]

        assert len(components_with_pins) >= len(netlist.components) * 0.8, \
            "At least 80% of components should have 2+ pins"

    def test_pin_positions_within_bounds(self):
        """Test that pin positions are within component bounds."""
        netlist = generate_200_component_netlist(seed=42)

        for comp in netlist.components:
            for pin in comp.pins:
                # Pin offset should be within component bounds
                assert abs(pin.position[0]) <= comp.width / 2 + 1.0, \
                    f"{comp.ref} pin {pin.name} x-offset too large"
                assert abs(pin.position[1]) <= comp.height / 2 + 1.0, \
                    f"{comp.ref} pin {pin.name} y-offset too large"

    def test_pins_assigned_to_nets(self):
        """Test that pins are assigned to nets."""
        netlist = generate_200_component_netlist(seed=42)

        # Count pins with net assignments
        total_pins = sum(len(c.pins) for c in netlist.components)
        pins_with_nets = sum(1 for c in netlist.components for p in c.pins if p.net is not None)

        # At least 50% of pins should be assigned to nets
        # (ICs have many pins, not all can be connected with limited nets)
        assignment_rate = pins_with_nets / total_pins if total_pins > 0 else 0
        assert assignment_rate >= 0.5, \
            f"At least 50% of pins should be assigned to nets, got {assignment_rate:.1%}"
