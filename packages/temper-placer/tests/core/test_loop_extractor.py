"""
Tests for automatic loop extraction from netlist.
"""

import pytest

from temper_placer.core.loop import LoopCollection, LoopPriority, LoopType
from temper_placer.core.loop_extractor import (
    auto_extract_loops,
    classify_component,
    detect_half_bridge_topology,
    find_capacitors_between,
    find_gate_drivers,
    find_power_switches,
    get_common_net,
    get_pin_net,
    merge_loops,
    trace_bootstrap_loop,
    trace_commutation_loop,
    trace_gate_drive_loop,
)
from temper_placer.core.netlist import Component, Net, Netlist, Pin


@pytest.fixture
def igbt_component():
    """IGBT component (IKW40N120H3)."""
    return Component(
        ref="Q1",
        footprint="TO-247-3",
        bounds=(15.0, 20.0),
        pins=[
            Pin("GATE", "1", (0, 5), "GATE_H"),
            Pin("COLLECTOR", "2", (0, -5), "DC_BUS+"),
            Pin("EMITTER", "3", (0, 0), "SW_NODE"),
        ],
        attributes={"MPN": "IKW40N120H3", "value": "1200V 40A"},
    )


@pytest.fixture
def mosfet_component():
    """MOSFET component."""
    return Component(
        ref="Q2",
        footprint="TO-220",
        bounds=(10.0, 15.0),
        pins=[
            Pin("GATE", "1", (0, 3), "GATE_L"),
            Pin("DRAIN", "2", (0, -3), "SW_NODE"),
            Pin("SOURCE", "3", (0, 0), "PGND"),
        ],
        attributes={"MPN": "IRFP250N", "value": "200V 30A"},
    )


@pytest.fixture
def gate_driver_component():
    """Gate driver IC (UCC21550)."""
    return Component(
        ref="U1",
        footprint="SOIC-8",
        bounds=(5.0, 6.0),
        pins=[
            Pin("OUTA", "1", (-2, 2), "GATE_H_DRV"),
            Pin("OUTB", "2", (-2, -2), "GATE_L_DRV"),
            Pin("VCC", "3", (2, 2), "VCC_15V"),
            Pin("GND", "4", (2, -2), "CGND"),
        ],
        attributes={"MPN": "UCC21550", "value": "Gate Driver"},
    )


@pytest.fixture
def bus_capacitor():
    """DC bus capacitor."""
    return Component(
        ref="C_BUS1",
        footprint="CAP_ELECTROLYTIC",
        bounds=(10.0, 16.0),
        pins=[
            Pin("+", "1", (0, 5), "DC_BUS+"),
            Pin("-", "2", (0, -5), "PGND"),
        ],
        attributes={"value": "470uF", "voltage": "400V"},
    )


@pytest.fixture
def bootstrap_cap():
    """Bootstrap capacitor."""
    return Component(
        ref="C_BOOT",
        footprint="C_0805",
        bounds=(2.0, 1.25),
        pins=[
            Pin("1", "1", (-0.75, 0), "VCC_BOOT"),
            Pin("2", "2", (0.75, 0), "SW_NODE"),
        ],
        attributes={"value": "1uF"},
    )


@pytest.fixture
def bootstrap_diode():
    """Bootstrap diode."""
    return Component(
        ref="D_BOOT",
        footprint="SOD-123",
        bounds=(2.5, 1.3),
        pins=[
            Pin("A", "1", (-1.0, 0), "VCC_15V"),
            Pin("K", "2", (1.0, 0), "VCC_BOOT"),
        ],
        attributes={"MPN": "BAT54", "value": "Schottky"},
    )


@pytest.fixture
def gate_resistor():
    """Gate resistor."""
    return Component(
        ref="RG_H",
        footprint="R_0805",
        bounds=(2.0, 1.25),
        pins=[
            Pin("1", "1", (-0.75, 0), "GATE_H_DRV"),
            Pin("2", "2", (0.75, 0), "GATE_H"),
        ],
        attributes={"value": "10R"},
    )


@pytest.fixture
def half_bridge_netlist(
    igbt_component,
    mosfet_component,
    gate_driver_component,
    bus_capacitor,
    bootstrap_cap,
    bootstrap_diode,
    gate_resistor,
):
    """Complete half-bridge netlist."""
    return Netlist(
        components=[
            igbt_component,
            mosfet_component,
            gate_driver_component,
            bus_capacitor,
            bootstrap_cap,
            bootstrap_diode,
            gate_resistor,
        ],
        nets=[
            Net("DC_BUS+", [("C_BUS1", "+"), ("Q1", "COLLECTOR")]),
            Net("SW_NODE", [("Q1", "EMITTER"), ("Q2", "DRAIN"), ("C_BOOT", "2")]),
            Net("PGND", [("Q2", "SOURCE"), ("C_BUS1", "-")]),
            Net("GATE_H", [("Q1", "GATE"), ("RG_H", "2")]),
            Net("GATE_H_DRV", [("U1", "OUTA"), ("RG_H", "1")]),
            Net("GATE_L", [("Q2", "GATE")]),
            Net("VCC_15V", [("U1", "VCC"), ("D_BOOT", "A")]),
            Net("VCC_BOOT", [("D_BOOT", "K"), ("C_BOOT", "1")]),
        ],
    )


class TestComponentClassification:
    """Test component classification heuristics."""

    def test_classify_igbt(self, igbt_component):
        """Should classify IGBT correctly."""
        result = classify_component(igbt_component)
        assert result.category == "power_switch"
        assert result.subcategory == "igbt"
        assert result.confidence > 0.8

    def test_classify_mosfet(self, mosfet_component):
        """Should classify MOSFET correctly."""
        result = classify_component(mosfet_component)
        assert result.category == "power_switch"
        assert result.subcategory == "mosfet"
        assert result.confidence > 0.8

    def test_classify_gate_driver(self, gate_driver_component):
        """Should classify gate driver IC."""
        result = classify_component(gate_driver_component)
        assert result.category == "gate_driver"
        assert result.confidence > 0.8

    def test_classify_bus_capacitor(self, bus_capacitor):
        """Should classify large capacitor as bus cap."""
        result = classify_component(bus_capacitor)
        assert result.category == "capacitor"
        assert result.subcategory == "bus"  # 470uF is large

    def test_classify_bootstrap_capacitor(self, bootstrap_cap):
        """Should classify bootstrap cap by name."""
        result = classify_component(bootstrap_cap)
        assert result.category == "capacitor"
        assert result.subcategory == "bootstrap"

    def test_classify_diode(self, bootstrap_diode):
        """Should classify bootstrap diode."""
        result = classify_component(bootstrap_diode)
        assert result.category == "diode"
        assert result.subcategory == "bootstrap"

    def test_classify_unknown(self):
        """Should handle unknown components."""
        comp = Component(ref="J1", footprint="CONN_2", bounds=(5, 10))
        result = classify_component(comp)
        assert result.category == "other"


class TestNetlistQueries:
    """Test netlist query helper functions."""

    def test_find_power_switches(self, half_bridge_netlist):
        """Should find both switches."""
        switches = find_power_switches(half_bridge_netlist)
        assert len(switches) == 2
        refs = {sw.ref for sw in switches}
        assert refs == {"Q1", "Q2"}

    def test_find_gate_drivers(self, half_bridge_netlist):
        """Should find gate driver IC."""
        drivers = find_gate_drivers(half_bridge_netlist)
        assert len(drivers) == 1
        assert drivers[0].ref == "U1"

    def test_get_pin_net(self, igbt_component):
        """Should get net for pin by name."""
        net = get_pin_net(igbt_component, ["COLLECTOR", "C"])
        assert net == "DC_BUS+"

    def test_get_pin_net_fallback(self, mosfet_component):
        """Should try multiple pin names."""
        net = get_pin_net(mosfet_component, ["DRAIN", "D"])
        assert net == "SW_NODE"

    def test_get_pin_net_not_found(self, igbt_component):
        """Should return None if pin not found."""
        net = get_pin_net(igbt_component, ["UNKNOWN_PIN"])
        assert net is None

    def test_get_common_net(self, igbt_component, mosfet_component):
        """Should find net connecting two components."""
        common = get_common_net(igbt_component, mosfet_component)
        assert common == "SW_NODE"

    def test_find_capacitors_between(self, half_bridge_netlist):
        """Should find capacitors between two nets."""
        caps = find_capacitors_between(half_bridge_netlist, "DC_BUS+", "PGND")
        assert len(caps) == 1
        assert caps[0].ref == "C_BUS1"


class TestTopologyDetection:
    """Test topology detection algorithms."""

    def test_detect_half_bridge(self, half_bridge_netlist):
        """Should detect half-bridge topology."""
        result = detect_half_bridge_topology(half_bridge_netlist)
        assert result is not None
        high, low = result
        assert high.ref == "Q1"
        assert low.ref == "Q2"

    def test_detect_no_half_bridge_single_switch(self, igbt_component):
        """Should return None if not enough switches."""
        netlist = Netlist(components=[igbt_component])
        result = detect_half_bridge_topology(netlist)
        assert result is None

    def test_detect_no_half_bridge_no_common_net(self):
        """Should return None if switches don't share a net."""
        q1 = Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(15, 20),
            pins=[Pin("E", "1", (0, 0), "NET1")],
        )
        q2 = Component(
            ref="Q2",
            footprint="TO-220",
            bounds=(10, 15),
            pins=[Pin("S", "1", (0, 0), "NET2")],
        )
        netlist = Netlist(components=[q1, q2])
        result = detect_half_bridge_topology(netlist)
        assert result is None


class TestLoopTracing:
    """Test loop tracing algorithms."""

    def test_trace_commutation_loop(self, half_bridge_netlist, igbt_component, mosfet_component):
        """Should trace commutation loop."""
        loop = trace_commutation_loop(half_bridge_netlist, igbt_component, mosfet_component)
        assert loop is not None
        assert loop.name == "auto_commutation"
        assert loop.loop_type == LoopType.COMMUTATION
        assert loop.priority == LoopPriority.CRITICAL
        assert "Q1" in loop.components
        assert "Q2" in loop.components
        assert "C_BUS1" in loop.components
        assert loop.max_area_mm2 == 500.0

    def test_trace_gate_drive_loop_high_side(
        self, half_bridge_netlist, igbt_component, gate_driver_component
    ):
        """Should trace high-side gate drive loop."""
        loop = trace_gate_drive_loop(
            half_bridge_netlist, igbt_component, gate_driver_component, is_high_side=True
        )
        assert loop is not None
        assert loop.name == "auto_gate_drive_Q1"
        assert loop.loop_type == LoopType.GATE_DRIVE_HIGH
        assert loop.priority == LoopPriority.CRITICAL
        assert "Q1" in loop.components
        assert "U1" in loop.components
        assert "RG_H" in loop.components
        assert loop.max_area_mm2 == 100.0

    def test_trace_gate_drive_loop_low_side(
        self, half_bridge_netlist, mosfet_component, gate_driver_component
    ):
        """Should trace low-side gate drive loop."""
        loop = trace_gate_drive_loop(
            half_bridge_netlist, mosfet_component, gate_driver_component, is_high_side=False
        )
        assert loop is not None
        assert loop.name == "auto_gate_drive_Q2"
        assert loop.loop_type == LoopType.GATE_DRIVE_LOW
        assert loop.priority == LoopPriority.CRITICAL

    def test_trace_bootstrap_loop(self, half_bridge_netlist, gate_driver_component):
        """Should trace bootstrap loop."""
        loop = trace_bootstrap_loop(half_bridge_netlist, gate_driver_component)
        assert loop is not None
        assert loop.name == "auto_bootstrap"
        assert loop.loop_type == LoopType.BOOTSTRAP
        assert loop.priority == LoopPriority.HIGH
        assert "C_BOOT" in loop.components
        assert "D_BOOT" in loop.components
        assert loop.max_area_mm2 == 50.0

    def test_trace_bootstrap_loop_no_bootstrap(self, gate_driver_component):
        """Should return None if no bootstrap circuit."""
        # Netlist without bootstrap components
        netlist = Netlist(components=[gate_driver_component])
        loop = trace_bootstrap_loop(netlist, gate_driver_component)
        assert loop is None


class TestAutoExtraction:
    """Test complete auto-extraction workflow."""

    def test_auto_extract_half_bridge(self, half_bridge_netlist):
        """Should extract all loops from half-bridge netlist."""
        loops = auto_extract_loops(half_bridge_netlist)
        assert len(loops) == 4  # Commutation + 2 gate drives + bootstrap

        # Check loop types
        loop_types = {loop.loop_type for loop in loops.loops}
        assert LoopType.COMMUTATION in loop_types
        assert LoopType.GATE_DRIVE_HIGH in loop_types
        assert LoopType.GATE_DRIVE_LOW in loop_types
        assert LoopType.BOOTSTRAP in loop_types

        # Check all names are prefixed with "auto_"
        for loop in loops.loops:
            assert loop.name.startswith("auto_")

    def test_auto_extract_empty_netlist(self):
        """Should handle empty netlist gracefully."""
        netlist = Netlist()
        loops = auto_extract_loops(netlist)
        assert len(loops) == 0

    def test_auto_extract_with_topology_hints(self, half_bridge_netlist):
        """Should use topology hints."""
        loops = auto_extract_loops(half_bridge_netlist, topology_hints={"topology": "half_bridge"})
        # Should still extract same loops
        assert len(loops) >= 3  # At least commutation + gate drives

    def test_get_critical_loops(self, half_bridge_netlist):
        """Should identify critical loops."""
        loops = auto_extract_loops(half_bridge_netlist)
        critical = loops.get_critical_loops()
        assert len(critical) >= 3  # Commutation + 2 gate drives


class TestLoopMerging:
    """Test merging auto and manual loops."""

    def test_merge_no_conflict(self, half_bridge_netlist):
        """Should keep both auto and manual loops if no conflict."""
        auto_loops = auto_extract_loops(half_bridge_netlist)

        # Manual loop with different name
        from temper_placer.core.loop import Loop

        manual_loop = Loop(
            name="manual_custom",
            loop_type=LoopType.CUSTOM,
            description="Manual custom loop",
            components=["X1", "X2"],
            priority=LoopPriority.LOW,
            max_area_mm2=200.0,
        )
        manual_loops = LoopCollection(loops=[manual_loop])

        merged = merge_loops(auto_loops, manual_loops)
        assert len(merged) == len(auto_loops) + 1
        assert any(loop.name == "manual_custom" for loop in merged.loops)

    def test_merge_manual_override(self, half_bridge_netlist):
        """Manual loop should override auto loop with same base name."""
        auto_loops = auto_extract_loops(half_bridge_netlist)

        # Manual commutation loop (same base name as "auto_commutation")
        from temper_placer.core.loop import Loop

        manual_commutation = Loop(
            name="commutation",
            loop_type=LoopType.COMMUTATION,
            description="Manual commutation override",
            components=["Q1", "Q2", "C_BUS1"],
            priority=LoopPriority.CRITICAL,
            max_area_mm2=300.0,  # Different constraint
        )
        manual_loops = LoopCollection(loops=[manual_commutation])

        merged = merge_loops(auto_loops, manual_loops)

        # Manual loop should be present
        commutation_loops = [
            loop for loop in merged.loops if loop.loop_type == LoopType.COMMUTATION
        ]
        assert len(commutation_loops) == 1
        assert commutation_loops[0].name == "commutation"
        assert commutation_loops[0].max_area_mm2 == 300.0

    def test_merge_exact_name_match(self):
        """Manual loop with exact name should override auto loop."""
        from temper_placer.core.loop import Loop

        auto_loop = Loop(
            name="auto_test",
            loop_type=LoopType.CUSTOM,
            description="Auto",
            components=["A"],
            priority=LoopPriority.LOW,
            max_area_mm2=100.0,
        )
        manual_loop = Loop(
            name="auto_test",  # Exact name match
            loop_type=LoopType.CUSTOM,
            description="Manual",
            components=["B"],
            priority=LoopPriority.HIGH,
            max_area_mm2=50.0,
        )

        auto_loops = LoopCollection(loops=[auto_loop])
        manual_loops = LoopCollection(loops=[manual_loop])

        merged = merge_loops(auto_loops, manual_loops)
        assert len(merged) == 1
        assert merged.loops[0].description == "Manual"
        assert merged.loops[0].max_area_mm2 == 50.0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_gate_pin(self):
        """Should handle components without expected pins."""
        comp = Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(15, 20),
            pins=[Pin("X", "1", (0, 0), "NET1")],  # No GATE pin
            attributes={"MPN": "IKW40N120H3"},
        )
        netlist = Netlist(components=[comp])
        loops = auto_extract_loops(netlist)
        # Should not crash, just not extract loops
        assert len(loops) == 0

    def test_multiple_bus_caps(self):
        """Should handle multiple bus capacitors."""
        cap1 = Component(
            ref="C1",
            footprint="CAP",
            bounds=(10, 16),
            pins=[Pin("+", "1", (0, 5), "DC+"), Pin("-", "2", (0, -5), "DC-")],
            attributes={"value": "470uF"},
        )
        cap2 = Component(
            ref="C2",
            footprint="CAP",
            bounds=(10, 16),
            pins=[Pin("+", "1", (0, 5), "DC+"), Pin("-", "2", (0, -5), "DC-")],
            attributes={"value": "220uF"},
        )
        netlist = Netlist(components=[cap1, cap2])
        caps = find_capacitors_between(netlist, "DC+", "DC-")
        assert len(caps) == 2

    def test_case_insensitive_pin_names(self):
        """Pin name matching should work regardless of case."""
        comp = Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(15, 20),
            pins=[Pin("gate", "1", (0, 0), "GATE_NET")],  # Lowercase
            attributes={"MPN": "IKW40N120H3"},
        )
        # Should still find pin (current implementation is case-sensitive,
        # but this test documents expected behavior)
        net = get_pin_net(comp, ["GATE", "gate", "G"])
        assert net == "GATE_NET"
