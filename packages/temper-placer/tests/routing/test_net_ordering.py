"""
Tests for net ordering algorithm (temper-wna.1).

The net ordering algorithm determines the order in which nets should be routed.
This is critical for deterministic routing - same inputs must produce same ordering.

Priority order (highest to lowest):
1. Loop membership: Nets in critical loops route first
2. Net class: HV > Power > GateDrive > Signal
3. Pin count: Fewer pins = higher priority (easier to route)
4. Bounding box area: Smaller = higher priority
5. Alphabetical: Final deterministic tie-breaker
"""

import pytest

from temper_placer.core.loop import Loop, LoopCollection, LoopPriority, LoopType
from temper_placer.core.netlist import Component, Net, Netlist, Pin

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_netlist():
    """Create a sample netlist for testing net ordering."""
    components = [
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(16.0, 20.0),
            pins=[
                Pin("G", "1", (-5.0, 0.0), net="GATE_H"),
                Pin("C", "2", (0.0, 0.0), net="DC_BUS_P"),
                Pin("E", "3", (5.0, 0.0), net="SW_NODE"),
            ],
            net_class="HighVoltage",
        ),
        Component(
            ref="Q2",
            footprint="TO-247",
            bounds=(16.0, 20.0),
            pins=[
                Pin("G", "1", (-5.0, 0.0), net="GATE_L"),
                Pin("C", "2", (0.0, 0.0), net="SW_NODE"),
                Pin("E", "3", (5.0, 0.0), net="DC_BUS_N"),
            ],
            net_class="HighVoltage",
        ),
        Component(
            ref="U_GATE",
            footprint="SOIC-16",
            bounds=(10.0, 6.0),
            pins=[
                Pin("VCC", "1", (-4.0, 2.0), net="VCC_15V"),
                Pin("OUTH", "2", (-4.0, 0.0), net="GATE_H"),
                Pin("OUTL", "3", (-4.0, -2.0), net="GATE_L"),
                Pin("GND", "8", (4.0, 0.0), net="GND"),
            ],
            net_class="Signal",
        ),
        Component(
            ref="C1",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[
                Pin("1", "1", (-0.9, 0.0), net="VCC_15V"),
                Pin("2", "2", (0.9, 0.0), net="GND"),
            ],
            net_class="Signal",
        ),
        Component(
            ref="R1",
            footprint="0603",
            bounds=(1.6, 0.8),
            pins=[
                Pin("1", "1", (-0.75, 0.0), net="SENSE_IN"),
                Pin("2", "2", (0.75, 0.0), net="SENSE_OUT"),
            ],
            net_class="Signal",
        ),
    ]

    nets = [
        Net("DC_BUS_P", [("Q1", "C")], net_class="HighVoltage", weight=2.0),
        Net("DC_BUS_N", [("Q2", "E")], net_class="HighVoltage", weight=2.0),
        Net("SW_NODE", [("Q1", "E"), ("Q2", "C")], net_class="HighVoltage", weight=2.0),
        Net("GATE_H", [("Q1", "G"), ("U_GATE", "OUTH")], net_class="GateDrive", weight=1.5),
        Net("GATE_L", [("Q2", "G"), ("U_GATE", "OUTL")], net_class="GateDrive", weight=1.5),
        Net("VCC_15V", [("U_GATE", "VCC"), ("C1", "1")], net_class="Power", weight=1.0),
        Net("GND", [("U_GATE", "GND"), ("C1", "2")], net_class="Power", weight=1.0),
        Net("SENSE_IN", [("R1", "1")], net_class="Signal", weight=1.0),
        Net("SENSE_OUT", [("R1", "2")], net_class="Signal", weight=1.0),
    ]

    return Netlist(components=components, nets=nets)


@pytest.fixture
def sample_loops():
    """Create sample loops for testing loop-aware net ordering."""
    collection = LoopCollection()

    # Critical commutation loop
    collection.add_loop(
        Loop(
            name="commutation",
            loop_type=LoopType.COMMUTATION,
            description="Main half-bridge commutation loop",
            components=["Q1", "Q2"],
            nets=["DC_BUS_P", "SW_NODE", "DC_BUS_N"],
            max_area_mm2=200,
            priority=LoopPriority.CRITICAL,
        )
    )

    # High-priority gate drive loop
    collection.add_loop(
        Loop(
            name="gate_drive_high",
            loop_type=LoopType.GATE_DRIVE_HIGH,
            description="High-side gate drive loop",
            components=["U_GATE", "Q1"],
            nets=["GATE_H", "SW_NODE"],
            max_area_mm2=50,
            priority=LoopPriority.HIGH,
        )
    )

    return collection


# =============================================================================
# Tests for NetClass Enum
# =============================================================================


class TestNetClass:
    """Tests for NetClass enumeration and ordering."""

    def test_net_class_ordering(self):
        """NetClass should have correct ordering: HV > Power > GateDrive > Signal."""
        from temper_placer.routing.net_ordering import NetClass

        assert NetClass.HIGH_VOLTAGE < NetClass.POWER
        assert NetClass.POWER < NetClass.GATE_DRIVE
        assert NetClass.GATE_DRIVE < NetClass.SIGNAL

    def test_net_class_values(self):
        """NetClass should have integer values for sorting."""
        from temper_placer.routing.net_ordering import NetClass

        assert NetClass.HIGH_VOLTAGE.value == 0
        assert NetClass.POWER.value == 1
        assert NetClass.GATE_DRIVE.value == 2
        assert NetClass.SIGNAL.value == 3


# =============================================================================
# Tests for NetPriority Dataclass
# =============================================================================


class TestNetPriority:
    """Tests for NetPriority composite priority key."""

    def test_priority_comparison_by_loop_criticality(self):
        """Loop criticality should be the first tiebreaker."""
        from temper_placer.routing.net_ordering import NetClass, NetPriority

        # Critical loop net beats non-critical
        critical = NetPriority(
            loop_criticality=0,  # critical
            net_class=NetClass.SIGNAL,
            pin_count=10,
            bbox_area=1000.0,
            name="NET_A",
        )
        non_critical = NetPriority(
            loop_criticality=3,  # low
            net_class=NetClass.HIGH_VOLTAGE,  # Higher net class
            pin_count=2,
            bbox_area=10.0,
            name="NET_B",
        )

        assert critical < non_critical

    def test_priority_comparison_by_net_class(self):
        """Net class should be the second tiebreaker (after loop criticality)."""
        from temper_placer.routing.net_ordering import NetClass, NetPriority

        hv_net = NetPriority(
            loop_criticality=2,
            net_class=NetClass.HIGH_VOLTAGE,
            pin_count=10,
            bbox_area=1000.0,
            name="NET_HV",
        )
        signal_net = NetPriority(
            loop_criticality=2,  # Same criticality
            net_class=NetClass.SIGNAL,
            pin_count=2,  # Fewer pins (would win if net class didn't matter)
            bbox_area=10.0,
            name="NET_SIG",
        )

        assert hv_net < signal_net

    def test_priority_comparison_by_pin_count(self):
        """Fewer pins should route first (same loop criticality and net class)."""
        from temper_placer.routing.net_ordering import NetClass, NetPriority

        few_pins = NetPriority(
            loop_criticality=2,
            net_class=NetClass.SIGNAL,
            pin_count=2,
            bbox_area=1000.0,  # Larger area
            name="NET_A",
        )
        many_pins = NetPriority(
            loop_criticality=2,
            net_class=NetClass.SIGNAL,
            pin_count=10,
            bbox_area=10.0,
            name="NET_B",
        )

        assert few_pins < many_pins

    def test_priority_comparison_by_bbox_area(self):
        """Smaller bounding box should route first (after pin count)."""
        from temper_placer.routing.net_ordering import NetClass, NetPriority

        small_bbox = NetPriority(
            loop_criticality=2,
            net_class=NetClass.SIGNAL,
            pin_count=4,
            bbox_area=100.0,
            name="NET_B",  # Alphabetically later
        )
        large_bbox = NetPriority(
            loop_criticality=2,
            net_class=NetClass.SIGNAL,
            pin_count=4,
            bbox_area=500.0,
            name="NET_A",
        )

        assert small_bbox < large_bbox

    def test_priority_comparison_alphabetical_tiebreaker(self):
        """Alphabetical order is the final tiebreaker."""
        from temper_placer.routing.net_ordering import NetClass, NetPriority

        net_a = NetPriority(
            loop_criticality=2,
            net_class=NetClass.SIGNAL,
            pin_count=4,
            bbox_area=100.0,
            name="NET_A",
        )
        net_b = NetPriority(
            loop_criticality=2,
            net_class=NetClass.SIGNAL,
            pin_count=4,
            bbox_area=100.0,
            name="NET_B",
        )

        assert net_a < net_b

    def test_priority_equality(self):
        """Identical priorities should be equal."""
        from temper_placer.routing.net_ordering import NetClass, NetPriority

        p1 = NetPriority(
            loop_criticality=1,
            net_class=NetClass.POWER,
            pin_count=3,
            bbox_area=50.0,
            name="VCC",
        )
        p2 = NetPriority(
            loop_criticality=1,
            net_class=NetClass.POWER,
            pin_count=3,
            bbox_area=50.0,
            name="VCC",
        )

        assert not (p1 < p2)
        assert not (p2 < p1)


# =============================================================================
# Tests for Net Ordering Function
# =============================================================================


class TestNetOrdering:
    """Tests for the order_nets function."""

    def test_order_nets_deterministic(self, sample_netlist, sample_loops):
        """Same inputs should always produce same ordering."""
        from temper_placer.routing.net_ordering import order_nets

        order1 = order_nets(sample_netlist, sample_loops)
        order2 = order_nets(sample_netlist, sample_loops)
        order3 = order_nets(sample_netlist, sample_loops)

        assert order1 == order2 == order3

    def test_order_nets_critical_loop_first(self, sample_netlist, sample_loops):
        """Nets in critical loops should be ordered first."""
        from temper_placer.routing.net_ordering import order_nets

        ordered = order_nets(sample_netlist, sample_loops)

        # Find positions of critical loop nets vs non-critical
        critical_nets = {"DC_BUS_P", "SW_NODE", "DC_BUS_N"}  # commutation loop
        non_critical_nets = {"SENSE_IN", "SENSE_OUT"}

        for critical_net in critical_nets:
            if critical_net in ordered:
                critical_pos = ordered.index(critical_net)
                for non_critical_net in non_critical_nets:
                    if non_critical_net in ordered:
                        non_critical_pos = ordered.index(non_critical_net)
                        assert critical_pos < non_critical_pos, (
                            f"Critical net {critical_net} should come before {non_critical_net}"
                        )

    def test_order_nets_respects_net_class(self, sample_netlist):
        """Without loops, net class should determine order."""
        from temper_placer.routing.net_ordering import order_nets

        # Empty loop collection - only net class matters
        ordered = order_nets(sample_netlist, LoopCollection())

        # Find a HighVoltage net and a Signal net
        hv_nets = [n.name for n in sample_netlist.nets if n.net_class == "HighVoltage"]
        signal_nets = [n.name for n in sample_netlist.nets if n.net_class == "Signal"]

        for hv_net in hv_nets:
            if hv_net in ordered:
                hv_pos = ordered.index(hv_net)
                for sig_net in signal_nets:
                    if sig_net in ordered:
                        sig_pos = ordered.index(sig_net)
                        assert hv_pos < sig_pos, (
                            f"HV net {hv_net} should come before Signal net {sig_net}"
                        )

    def test_order_nets_returns_all_nets(self, sample_netlist, sample_loops):
        """Ordering should include all nets from netlist."""
        from temper_placer.routing.net_ordering import order_nets

        ordered = order_nets(sample_netlist, sample_loops)

        expected_names = {n.name for n in sample_netlist.nets}
        assert set(ordered) == expected_names

    def test_order_nets_no_duplicates(self, sample_netlist, sample_loops):
        """Each net should appear exactly once in ordering."""
        from temper_placer.routing.net_ordering import order_nets

        ordered = order_nets(sample_netlist, sample_loops)

        assert len(ordered) == len(set(ordered))

    def test_order_nets_empty_netlist(self):
        """Empty netlist should return empty ordering."""
        from temper_placer.routing.net_ordering import order_nets

        empty_netlist = Netlist(components=[], nets=[])
        ordered = order_nets(empty_netlist, LoopCollection())

        assert ordered == []

    def test_order_nets_single_net(self):
        """Single net should return that net."""
        from temper_placer.routing.net_ordering import order_nets

        netlist = Netlist(
            components=[
                Component(
                    ref="R1",
                    footprint="0603",
                    bounds=(1.6, 0.8),
                    pins=[Pin("1", "1", (-0.75, 0.0), net="NET1")],
                )
            ],
            nets=[Net("NET1", [("R1", "1")], net_class="Signal")],
        )

        ordered = order_nets(netlist, LoopCollection())
        assert ordered == ["NET1"]


# =============================================================================
# Tests for Net Class Mapping
# =============================================================================


class TestNetClassMapping:
    """Tests for mapping netlist net classes to NetClass enum."""

    def test_string_to_netclass_mapping(self):
        """Should correctly map string net classes to NetClass enum."""
        from temper_placer.routing.net_ordering import NetClass, get_net_class_from_string

        assert get_net_class_from_string("HighVoltage") == NetClass.HIGH_VOLTAGE
        assert get_net_class_from_string("Power") == NetClass.POWER
        assert get_net_class_from_string("GateDrive") == NetClass.GATE_DRIVE
        assert get_net_class_from_string("Signal") == NetClass.SIGNAL

    def test_unknown_net_class_defaults_to_signal(self):
        """Unknown net class strings should default to Signal."""
        from temper_placer.routing.net_ordering import NetClass, get_net_class_from_string

        assert get_net_class_from_string("Unknown") == NetClass.SIGNAL
        assert get_net_class_from_string("") == NetClass.SIGNAL
        assert get_net_class_from_string("custom_class") == NetClass.SIGNAL


# =============================================================================
# Tests for Loop Criticality
# =============================================================================


class TestLoopCriticality:
    """Tests for computing loop criticality of nets."""

    def test_critical_loop_net_has_criticality_0(self, sample_loops):
        """Nets in CRITICAL loops should have criticality 0."""
        from temper_placer.routing.net_ordering import get_loop_criticality

        # DC_BUS_P is in the critical commutation loop
        criticality = get_loop_criticality("DC_BUS_P", sample_loops)
        assert criticality == 0

    def test_high_priority_loop_net_has_criticality_1(self, sample_loops):
        """Nets in HIGH priority loops should have criticality 1."""
        from temper_placer.routing.net_ordering import get_loop_criticality

        # GATE_H is in the high-priority gate drive loop
        criticality = get_loop_criticality("GATE_H", sample_loops)
        assert criticality == 1

    def test_no_loop_net_has_criticality_3(self, sample_loops):
        """Nets not in any loop should have criticality 3 (low)."""
        from temper_placer.routing.net_ordering import get_loop_criticality

        # SENSE_IN is not in any loop
        criticality = get_loop_criticality("SENSE_IN", sample_loops)
        assert criticality == 3

    def test_multi_loop_net_uses_highest_priority(self, sample_loops):
        """Nets in multiple loops should use the highest priority."""
        from temper_placer.routing.net_ordering import get_loop_criticality

        # SW_NODE is in both commutation (critical) and gate_drive_high (high)
        criticality = get_loop_criticality("SW_NODE", sample_loops)
        assert criticality == 0  # Should use critical priority


# =============================================================================
# Tests for Bounding Box Calculation
# =============================================================================


class TestBoundingBox:
    """Tests for computing net bounding box area."""

    def test_single_pin_net_has_zero_area(self, sample_netlist):
        """Single-pin nets should have zero bounding box area."""
        from temper_placer.routing.net_ordering import compute_bbox_area

        # DC_BUS_P has only one pin
        area = compute_bbox_area("DC_BUS_P", sample_netlist)
        assert area == 0.0

    def test_two_pin_net_bbox_area(self):
        """Two-pin net should have correct bounding box area."""
        from temper_placer.routing.net_ordering import compute_bbox_area

        # Create a simple netlist with known positions
        netlist = Netlist(
            components=[
                Component(
                    ref="C1",
                    footprint="0805",
                    bounds=(2.0, 1.0),
                    pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
                    initial_position=(0.0, 0.0),
                ),
                Component(
                    ref="C2",
                    footprint="0805",
                    bounds=(2.0, 1.0),
                    pins=[Pin("1", "1", (0.0, 0.0), net="NET1")],
                    initial_position=(10.0, 5.0),
                ),
            ],
            nets=[Net("NET1", [("C1", "1"), ("C2", "1")])],
        )

        # With positions at (0,0) and (10,5), bbox is 10x5 = 50 mm^2
        area = compute_bbox_area("NET1", netlist)
        assert area == pytest.approx(50.0, rel=0.01)

    def test_nonexistent_net_returns_zero(self, sample_netlist):
        """Non-existent nets should return zero area."""
        from temper_placer.routing.net_ordering import compute_bbox_area

        area = compute_bbox_area("NONEXISTENT_NET", sample_netlist)
        assert area == 0.0
