"""
Tests for component-to-loop ownership mapping.
"""

import pytest

from temper_placer.core.loop import (
    Loop,
    LoopCollection,
    LoopEvent,
    LoopPin,
    LoopPriority,
    LoopType,
)
from temper_placer.core.loop_ownership import (
    ComponentLoopInfo,
    LoopMembership,
    LoopOwnershipMap,
    build_ownership_map,
    classify_role,
)
from temper_placer.core.netlist import Component, Net, Netlist, Pin


@pytest.fixture
def simple_netlist():
    """Simple half-bridge netlist."""
    return Netlist(
        components=[
            Component(
                ref="Q1",
                footprint="TO-247",
                bounds=(15, 20),
                pins=[
                    Pin("GATE", "1", (0, 5), "GATE_H"),
                    Pin("COLLECTOR", "2", (0, -5), "DC+"),
                    Pin("EMITTER", "3", (0, 0), "SW_NODE"),
                ],
                attributes={"MPN": "IKW40N120H3"},
            ),
            Component(
                ref="Q2",
                footprint="TO-220",
                bounds=(10, 15),
                pins=[
                    Pin("GATE", "1", (0, 3), "GATE_L"),
                    Pin("DRAIN", "2", (0, -3), "SW_NODE"),
                    Pin("SOURCE", "3", (0, 0), "PGND"),
                ],
                attributes={"MPN": "IRFP250N"},
            ),
            Component(
                ref="C_BUS",
                footprint="CAP",
                bounds=(10, 16),
                pins=[Pin("+", "1", (0, 5), "DC+"), Pin("-", "2", (0, -5), "PGND")],
                attributes={"value": "470uF"},
            ),
            Component(
                ref="U1",
                footprint="SOIC-8",
                bounds=(5, 6),
                pins=[
                    Pin("OUTA", "1", (-2, 2), "GATE_H_DRV"),
                    Pin("OUTB", "2", (-2, -2), "GATE_L_DRV"),
                ],
                attributes={"MPN": "UCC21550"},
            ),
            Component(
                ref="C_BOOT",
                footprint="C_0805",
                bounds=(2, 1.25),
                pins=[Pin("1", "1", (-0.75, 0), "VCC_BOOT"), Pin("2", "2", (0.75, 0), "SW_NODE")],
                attributes={"value": "1uF"},
            ),
            Component(
                ref="D_BOOT",
                footprint="SOD-123",
                bounds=(2.5, 1.3),
                pins=[Pin("A", "1", (-1, 0), "VCC"), Pin("K", "2", (1, 0), "VCC_BOOT")],
                attributes={"value": "Schottky"},
            ),
        ]
    )


@pytest.fixture
def loop_collection():
    """Collection of loops for half-bridge."""
    commutation_loop = Loop(
        name="commutation",
        loop_type=LoopType.COMMUTATION,
        description="Main commutation loop",
        components=["Q1", "Q2", "C_BUS"],
        pins=[
            LoopPin("C_BUS", "+", "DC+"),
            LoopPin("Q1", "COLLECTOR", "DC+"),
            LoopPin("Q1", "EMITTER", "SW_NODE"),
            LoopPin("Q2", "DRAIN", "SW_NODE"),
            LoopPin("Q2", "SOURCE", "PGND"),
            LoopPin("C_BUS", "-", "PGND"),
        ],
        priority=LoopPriority.CRITICAL,
        max_area_mm2=500.0,
    )

    gate_high_loop = Loop(
        name="gate_drive_high",
        loop_type=LoopType.GATE_DRIVE_HIGH,
        description="High-side gate drive",
        components=["U1", "Q1"],
        pins=[
            LoopPin("U1", "OUTA", "GATE_H_DRV"),
            LoopPin("Q1", "GATE", "GATE_H"),
        ],
        priority=LoopPriority.CRITICAL,
        max_area_mm2=100.0,
    )

    gate_low_loop = Loop(
        name="gate_drive_low",
        loop_type=LoopType.GATE_DRIVE_LOW,
        description="Low-side gate drive",
        components=["U1", "Q2"],
        priority=LoopPriority.CRITICAL,
        max_area_mm2=100.0,
    )

    bootstrap_loop = Loop(
        name="bootstrap",
        loop_type=LoopType.BOOTSTRAP,
        description="Bootstrap charging",
        components=["D_BOOT", "C_BOOT"],
        priority=LoopPriority.HIGH,
        max_area_mm2=50.0,
    )

    return LoopCollection(loops=[commutation_loop, gate_high_loop, gate_low_loop, bootstrap_loop])


class TestLoopMembership:
    """Test LoopMembership data structure."""

    def test_create_membership(self):
        """Should create membership with loop name and role."""
        membership = LoopMembership(
            loop_name="commutation",
            role="switch",
            pins_in_loop=["COLLECTOR", "EMITTER"],
        )
        assert membership.loop_name == "commutation"
        assert membership.role == "switch"
        assert len(membership.pins_in_loop) == 2

    def test_membership_default_pins(self):
        """Should have empty pins list by default."""
        membership = LoopMembership(loop_name="test", role="switch")
        assert membership.pins_in_loop == []


class TestComponentLoopInfo:
    """Test ComponentLoopInfo aggregation."""

    def test_create_component_info(self):
        """Should create ComponentLoopInfo with memberships."""
        info = ComponentLoopInfo(
            component_ref="Q1",
            memberships=[
                LoopMembership("commutation", "switch"),
                LoopMembership("gate_drive_high", "switch"),
            ],
        )
        assert info.component_ref == "Q1"
        assert len(info.memberships) == 2

    def test_loop_names_property(self):
        """Should extract loop names from memberships."""
        info = ComponentLoopInfo(
            component_ref="Q1",
            memberships=[
                LoopMembership("commutation", "switch"),
                LoopMembership("gate_drive_high", "switch"),
            ],
        )
        names = info.loop_names
        assert len(names) == 2
        assert "commutation" in names
        assert "gate_drive_high" in names

    def test_is_in_critical_loop_heuristic(self):
        """Should detect critical loops by name."""
        # Component in commutation loop
        info1 = ComponentLoopInfo(
            component_ref="Q1",
            memberships=[LoopMembership("commutation", "switch")],
        )
        assert info1.is_in_critical_loop

        # Component in gate drive loop
        info2 = ComponentLoopInfo(
            component_ref="Q1",
            memberships=[LoopMembership("gate_drive_high", "switch")],
        )
        assert info2.is_in_critical_loop

        # Component not in critical loop
        info3 = ComponentLoopInfo(
            component_ref="C1",
            memberships=[LoopMembership("decoupling", "capacitor")],
        )
        assert not info3.is_in_critical_loop

    def test_get_priority_weight(self, loop_collection):
        """Should calculate priority weight based on loop priorities."""
        # Component in CRITICAL loop
        info_critical = ComponentLoopInfo(
            component_ref="Q1",
            memberships=[LoopMembership("commutation", "switch")],
        )
        weight = info_critical.get_priority_weight(loop_collection)
        assert weight == 1.0

        # Component in HIGH loop
        info_high = ComponentLoopInfo(
            component_ref="C_BOOT",
            memberships=[LoopMembership("bootstrap", "bootstrap_capacitor")],
        )
        weight = info_high.get_priority_weight(loop_collection)
        assert weight == 0.7

        # Component in multiple loops - should get max priority
        info_multi = ComponentLoopInfo(
            component_ref="Q1",
            memberships=[
                LoopMembership("commutation", "switch"),
                LoopMembership("gate_drive_high", "switch"),
            ],
        )
        weight = info_multi.get_priority_weight(loop_collection)
        assert weight == 1.0  # Both are CRITICAL

    def test_get_priority_weight_empty(self):
        """Should return 0.0 for component not in any loops."""
        info = ComponentLoopInfo(component_ref="J1", memberships=[])
        loops = LoopCollection(loops=[])
        weight = info.get_priority_weight(loops)
        assert weight == 0.0


class TestLoopOwnershipMap:
    """Test LoopOwnershipMap bidirectional queries."""

    def test_create_empty_map(self):
        """Should create empty ownership map."""
        ownership = LoopOwnershipMap()
        assert len(ownership.component_to_loops) == 0
        assert len(ownership.loop_to_components) == 0

    def test_get_component_info(self):
        """Should retrieve component loop info."""
        info = ComponentLoopInfo("Q1", [LoopMembership("loop1", "switch")])
        ownership = LoopOwnershipMap(component_to_loops={"Q1": info})

        result = ownership.get_component_info("Q1")
        assert result is not None
        assert result.component_ref == "Q1"

    def test_get_component_info_not_found(self):
        """Should return None for unknown component."""
        ownership = LoopOwnershipMap()
        result = ownership.get_component_info("UNKNOWN")
        assert result is None

    def test_get_loop_components(self):
        """Should retrieve components in a loop."""
        ownership = LoopOwnershipMap(loop_to_components={"commutation": ["Q1", "Q2", "C_BUS"]})

        components = ownership.get_loop_components("commutation")
        assert len(components) == 3
        assert "Q1" in components
        assert "Q2" in components
        assert "C_BUS" in components

    def test_get_loop_components_not_found(self):
        """Should return empty list for unknown loop."""
        ownership = LoopOwnershipMap()
        components = ownership.get_loop_components("UNKNOWN")
        assert components == []

    def test_get_shared_loops(self):
        """Should find loops shared by two components."""
        ownership = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo(
                    "Q1",
                    [
                        LoopMembership("commutation", "switch"),
                        LoopMembership("gate_drive_high", "switch"),
                    ],
                ),
                "Q2": ComponentLoopInfo(
                    "Q2",
                    [
                        LoopMembership("commutation", "switch"),
                        LoopMembership("gate_drive_low", "switch"),
                    ],
                ),
            }
        )

        shared = ownership.get_shared_loops("Q1", "Q2")
        assert len(shared) == 1
        assert "commutation" in shared

    def test_get_shared_loops_no_overlap(self):
        """Should return empty list if no shared loops."""
        ownership = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("loop1", "switch")]),
                "C1": ComponentLoopInfo("C1", [LoopMembership("loop2", "capacitor")]),
            }
        )

        shared = ownership.get_shared_loops("Q1", "C1")
        assert shared == []

    def test_get_shared_loops_component_not_found(self):
        """Should return empty list if component not in map."""
        ownership = LoopOwnershipMap()
        shared = ownership.get_shared_loops("Q1", "Q2")
        assert shared == []

    def test_components_share_loop(self):
        """Should check if components share any loop."""
        ownership = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")]),
                "Q2": ComponentLoopInfo("Q2", [LoopMembership("commutation", "switch")]),
            }
        )

        assert ownership.components_share_loop("Q1", "Q2")
        assert not ownership.components_share_loop("Q1", "C1")

    def test_components_share_critical_loop(self, loop_collection):
        """Should check if components share CRITICAL loop."""
        ownership = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")]),
                "Q2": ComponentLoopInfo("Q2", [LoopMembership("commutation", "switch")]),
                "C1": ComponentLoopInfo("C1", [LoopMembership("bootstrap", "capacitor")]),
            }
        )

        # Q1 and Q2 share commutation (CRITICAL)
        assert ownership.components_share_critical_loop("Q1", "Q2", loop_collection)

        # Q1 and C1 don't share any loop
        assert not ownership.components_share_critical_loop("Q1", "C1", loop_collection)


class TestRoleClassification:
    """Test component role classification in loops."""

    def test_classify_power_switch(self, simple_netlist, loop_collection):
        """Should classify power switches."""
        q1 = simple_netlist.get_component("Q1")
        commutation = loop_collection.loops[0]

        role = classify_role(q1, commutation)
        assert role == "switch"

    def test_classify_bus_capacitor(self, simple_netlist, loop_collection):
        """Should classify large capacitor as bus_capacitor."""
        c_bus = simple_netlist.get_component("C_BUS")
        commutation = loop_collection.loops[0]

        role = classify_role(c_bus, commutation)
        assert role == "bus_capacitor"

    def test_classify_bootstrap_capacitor(self, simple_netlist, loop_collection):
        """Should classify bootstrap cap."""
        c_boot = simple_netlist.get_component("C_BOOT")
        bootstrap = loop_collection.loops[3]

        role = classify_role(c_boot, bootstrap)
        assert role == "bootstrap_capacitor"

    def test_classify_gate_driver(self, simple_netlist, loop_collection):
        """Should classify gate driver IC."""
        u1 = simple_netlist.get_component("U1")
        gate_loop = loop_collection.loops[1]

        role = classify_role(u1, gate_loop)
        assert role == "driver"

    def test_classify_diode(self, simple_netlist, loop_collection):
        """Should classify bootstrap diode."""
        d_boot = simple_netlist.get_component("D_BOOT")
        bootstrap = loop_collection.loops[3]

        role = classify_role(d_boot, bootstrap)
        assert role == "bootstrap_diode"


class TestBuildOwnershipMap:
    """Test building ownership map from loops and netlist."""

    def test_build_from_simple_netlist(self, simple_netlist, loop_collection):
        """Should build complete ownership map."""
        ownership = build_ownership_map(loop_collection, simple_netlist)

        # Check component -> loops mapping
        assert "Q1" in ownership.component_to_loops
        assert "Q2" in ownership.component_to_loops
        assert "C_BUS" in ownership.component_to_loops
        assert "U1" in ownership.component_to_loops

        # Q1 should be in commutation and gate_drive_high
        q1_info = ownership.get_component_info("Q1")
        assert q1_info is not None
        assert len(q1_info.memberships) == 2
        loop_names = q1_info.loop_names
        assert "commutation" in loop_names
        assert "gate_drive_high" in loop_names

        # Q2 should be in commutation and gate_drive_low
        q2_info = ownership.get_component_info("Q2")
        assert q2_info is not None
        assert len(q2_info.memberships) == 2
        assert "commutation" in q2_info.loop_names
        assert "gate_drive_low" in q2_info.loop_names

    def test_build_loop_to_components_mapping(self, simple_netlist, loop_collection):
        """Should build loop -> components mapping."""
        ownership = build_ownership_map(loop_collection, simple_netlist)

        # Check commutation loop components
        commutation_comps = ownership.get_loop_components("commutation")
        assert len(commutation_comps) == 3
        assert "Q1" in commutation_comps
        assert "Q2" in commutation_comps
        assert "C_BUS" in commutation_comps

        # Check bootstrap loop components
        bootstrap_comps = ownership.get_loop_components("bootstrap")
        assert len(bootstrap_comps) == 2
        assert "D_BOOT" in bootstrap_comps
        assert "C_BOOT" in bootstrap_comps

    def test_build_with_pins_in_loop(self, simple_netlist, loop_collection):
        """Should track which pins participate in each loop."""
        ownership = build_ownership_map(loop_collection, simple_netlist)

        q1_info = ownership.get_component_info("Q1")
        assert q1_info is not None

        # Find commutation membership
        commutation_membership = next(
            m for m in q1_info.memberships if m.loop_name == "commutation"
        )
        assert "COLLECTOR" in commutation_membership.pins_in_loop
        assert "EMITTER" in commutation_membership.pins_in_loop

    def test_build_assigns_roles(self, simple_netlist, loop_collection):
        """Should assign roles to components in loops."""
        ownership = build_ownership_map(loop_collection, simple_netlist)

        q1_info = ownership.get_component_info("Q1")
        assert q1_info is not None
        for membership in q1_info.memberships:
            assert membership.role == "switch"

        c_bus_info = ownership.get_component_info("C_BUS")
        assert c_bus_info is not None
        assert c_bus_info.memberships[0].role == "bus_capacitor"

    def test_build_empty_loops(self):
        """Should handle empty loop collection."""
        netlist = Netlist()
        loops = LoopCollection(loops=[])

        ownership = build_ownership_map(loops, netlist)
        assert len(ownership.component_to_loops) == 0
        assert len(ownership.loop_to_components) == 0

    def test_build_with_missing_component(self, loop_collection):
        """Should handle loops referencing missing components gracefully."""
        # Netlist missing some components from loops
        partial_netlist = Netlist(
            components=[
                Component(
                    ref="Q1",
                    footprint="TO-247",
                    bounds=(15, 20),
                    attributes={"MPN": "IKW40N120H3"},
                )
            ]
        )

        ownership = build_ownership_map(loop_collection, partial_netlist)

        # Q1 should be present
        assert "Q1" in ownership.component_to_loops

        # Missing components should be skipped (not crash)
        assert "Q2" not in ownership.component_to_loops


class TestIntegrationQueries:
    """Test complex queries across ownership map."""

    def test_find_all_critical_components(self, simple_netlist, loop_collection):
        """Should find all components in critical loops."""
        ownership = build_ownership_map(loop_collection, simple_netlist)

        critical_components = []
        for ref, info in ownership.component_to_loops.items():
            if info.is_in_critical_loop:
                critical_components.append(ref)

        # Q1, Q2, U1, C_BUS should all be in critical loops
        assert "Q1" in critical_components
        assert "Q2" in critical_components
        assert "U1" in critical_components
        assert "C_BUS" in critical_components

        # Bootstrap components are HIGH, not CRITICAL
        assert "D_BOOT" not in critical_components
        assert "C_BOOT" not in critical_components

    def test_adjacency_recommendations(self, simple_netlist, loop_collection):
        """Should recommend which components should be adjacent."""
        ownership = build_ownership_map(loop_collection, simple_netlist)

        # Q1 and Q2 share commutation loop - should be adjacent
        assert ownership.components_share_critical_loop("Q1", "Q2", loop_collection)

        # Q1 and U1 share gate drive - should be adjacent
        assert ownership.components_share_critical_loop("Q1", "U1", loop_collection)

        # D_BOOT and C_BOOT share bootstrap but it's HIGH priority
        assert ownership.components_share_loop("D_BOOT", "C_BOOT")
        assert not ownership.components_share_critical_loop("D_BOOT", "C_BOOT", loop_collection)

    def test_priority_weights(self, simple_netlist, loop_collection):
        """Should calculate priority weights correctly."""
        ownership = build_ownership_map(loop_collection, simple_netlist)

        # Critical components
        q1_info = ownership.get_component_info("Q1")
        assert q1_info is not None
        assert q1_info.get_priority_weight(loop_collection) == 1.0

        # High priority components
        c_boot_info = ownership.get_component_info("C_BOOT")
        assert c_boot_info is not None
        assert c_boot_info.get_priority_weight(loop_collection) == 0.7

        # Component not in ownership map
        unknown_info = ownership.get_component_info("J1")
        assert unknown_info is None
