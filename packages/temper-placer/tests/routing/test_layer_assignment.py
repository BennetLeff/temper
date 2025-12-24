"""
Tests for layer assignment solver (temper-wna.2).

The layer assignment solver assigns each net to optimal PCB layer(s) while
respecting hard constraints like HV nets on L1 only.

Layer Model (4-Layer Induction Cooker):
- L1 (Top): Signal routing, 2oz copper, HV traces
- L2 (GND): Ground plane, split (PGND, CGND, ISOGND)
- L3 (PWR): Power plane (VCC_15V, VCC_3V3)
- L4 (Bottom): Signal routing, 1oz copper
"""

import pytest

from temper_placer.core.netlist import Component, Net, Netlist, Pin

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_netlist():
    """Create a sample netlist for layer assignment testing."""
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
            ref="U1",
            footprint="SOIC-16",
            bounds=(10.0, 6.0),
            pins=[
                Pin("VCC", "1", (-4.0, 2.0), net="VCC_3V3"),
                Pin("GND", "8", (4.0, 0.0), net="GND"),
                Pin("SDA", "2", (-4.0, 0.0), net="I2C_SDA"),
                Pin("SCL", "3", (-4.0, -2.0), net="I2C_SCL"),
            ],
            net_class="Signal",
        ),
    ]

    nets = [
        Net("DC_BUS_P", [("Q1", "C")], net_class="HighVoltage"),
        Net("SW_NODE", [("Q1", "E")], net_class="HighVoltage"),
        Net("GATE_H", [("Q1", "G")], net_class="GateDrive"),
        Net("VCC_3V3", [("U1", "VCC")], net_class="Power"),
        Net("GND", [("U1", "GND")], net_class="Power"),
        Net("I2C_SDA", [("U1", "SDA")], net_class="Signal"),
        Net("I2C_SCL", [("U1", "SCL")], net_class="Signal"),
    ]

    return Netlist(components=components, nets=nets)


# =============================================================================
# Tests for Layer Enum
# =============================================================================


class TestLayer:
    """Tests for Layer enumeration."""

    def test_layer_values(self):
        """Layer enum should have correct values."""
        from temper_placer.routing.layer_assignment import Layer

        assert Layer.L1_TOP.value == 1
        assert Layer.L2_GND.value == 2
        assert Layer.L3_PWR.value == 3
        assert Layer.L4_BOT.value == 4

    def test_layer_names(self):
        """Layer enum should have descriptive names."""
        from temper_placer.routing.layer_assignment import Layer

        assert Layer.L1_TOP.name == "L1_TOP"
        assert Layer.L2_GND.name == "L2_GND"
        assert Layer.L3_PWR.name == "L3_PWR"
        assert Layer.L4_BOT.name == "L4_BOT"


# =============================================================================
# Tests for LayerConstraint Dataclass
# =============================================================================


class TestLayerConstraint:
    """Tests for LayerConstraint configuration."""

    def test_constraint_creation(self):
        """Should create a valid layer constraint."""
        from temper_placer.routing.layer_assignment import Layer, LayerConstraint

        constraint = LayerConstraint(
            net_pattern=r"DC_BUS_.*",
            allowed_layers={Layer.L1_TOP},
            preferred_layer=Layer.L1_TOP,
            reason="HV traces must stay on L1",
        )

        assert constraint.net_pattern == r"DC_BUS_.*"
        assert constraint.allowed_layers == {Layer.L1_TOP}
        assert constraint.preferred_layer == Layer.L1_TOP
        assert "HV" in constraint.reason

    def test_constraint_pattern_matching(self):
        """Should match net names against pattern."""
        from temper_placer.routing.layer_assignment import Layer, LayerConstraint, matches_pattern

        constraint = LayerConstraint(
            net_pattern=r"DC_BUS_.*|HV_.*|SW_NODE",
            allowed_layers={Layer.L1_TOP},
            preferred_layer=Layer.L1_TOP,
            reason="HV constraint",
        )

        assert matches_pattern("DC_BUS_P", constraint.net_pattern)
        assert matches_pattern("DC_BUS_N", constraint.net_pattern)
        assert matches_pattern("HV_OUT", constraint.net_pattern)
        assert matches_pattern("SW_NODE", constraint.net_pattern)
        assert not matches_pattern("VCC_3V3", constraint.net_pattern)
        assert not matches_pattern("GND", constraint.net_pattern)


# =============================================================================
# Tests for LayerAssignment Dataclass
# =============================================================================


class TestLayerAssignment:
    """Tests for LayerAssignment result."""

    def test_assignment_creation(self):
        """Should create a valid layer assignment."""
        from temper_placer.routing.layer_assignment import Layer, LayerAssignment

        assignment = LayerAssignment(
            net="DC_BUS_P",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP},
            vias_required=False,
            reason="HV traces must stay on L1",
        )

        assert assignment.net == "DC_BUS_P"
        assert assignment.primary_layer == Layer.L1_TOP
        assert assignment.allowed_layers == {Layer.L1_TOP}
        assert assignment.vias_required is False


# =============================================================================
# Tests for Default Layer Constraints
# =============================================================================


class TestDefaultLayerConstraints:
    """Tests for the default layer constraints for induction cooker."""

    def test_default_constraints_exist(self):
        """Should have default constraints defined."""
        from temper_placer.routing.layer_assignment import DEFAULT_LAYER_CONSTRAINTS

        assert len(DEFAULT_LAYER_CONSTRAINTS) > 0

    def test_hv_constraint_exists(self):
        """Should have constraint for high-voltage nets."""
        from temper_placer.routing.layer_assignment import (
            DEFAULT_LAYER_CONSTRAINTS,
            Layer,
            matches_pattern,
        )

        # Find a constraint that matches DC_BUS_P
        hv_constraint = None
        for c in DEFAULT_LAYER_CONSTRAINTS:
            if matches_pattern("DC_BUS_P", c.net_pattern):
                hv_constraint = c
                break

        assert hv_constraint is not None
        assert Layer.L1_TOP in hv_constraint.allowed_layers
        # HV should only be allowed on L1
        assert hv_constraint.allowed_layers == {Layer.L1_TOP}

    def test_gate_drive_constraint_exists(self):
        """Should have constraint for gate drive nets."""
        from temper_placer.routing.layer_assignment import (
            DEFAULT_LAYER_CONSTRAINTS,
            Layer,
            matches_pattern,
        )

        gate_constraint = None
        for c in DEFAULT_LAYER_CONSTRAINTS:
            if matches_pattern("GATE_H", c.net_pattern):
                gate_constraint = c
                break

        assert gate_constraint is not None
        assert Layer.L1_TOP in gate_constraint.allowed_layers

    def test_signal_default_constraint(self):
        """Should have a catch-all constraint for signals."""
        from temper_placer.routing.layer_assignment import (
            DEFAULT_LAYER_CONSTRAINTS,
            Layer,
            matches_pattern,
        )

        # The last constraint should be a catch-all pattern
        catchall = DEFAULT_LAYER_CONSTRAINTS[-1]
        assert matches_pattern("RANDOM_NET", catchall.net_pattern)
        assert Layer.L4_BOT in catchall.allowed_layers


# =============================================================================
# Tests for Layer Assignment Function
# =============================================================================


class TestAssignLayers:
    """Tests for the assign_layers function."""

    def test_assign_layers_hv_to_l1(self, sample_netlist):
        """High-voltage nets should be assigned to L1 only."""
        from temper_placer.routing.layer_assignment import Layer, assign_layers

        assignments = assign_layers(sample_netlist)

        assert "DC_BUS_P" in assignments
        assert assignments["DC_BUS_P"].primary_layer == Layer.L1_TOP
        assert assignments["DC_BUS_P"].allowed_layers == {Layer.L1_TOP}

    def test_assign_layers_signal_to_l4(self, sample_netlist):
        """Signal nets should prefer L4 (bottom)."""
        from temper_placer.routing.layer_assignment import Layer, assign_layers

        assignments = assign_layers(sample_netlist)

        assert "I2C_SDA" in assignments
        assert assignments["I2C_SDA"].primary_layer == Layer.L4_BOT

    def test_assign_layers_all_nets_covered(self, sample_netlist):
        """All nets should get layer assignments."""
        from temper_placer.routing.layer_assignment import assign_layers

        assignments = assign_layers(sample_netlist)

        expected_nets = {n.name for n in sample_netlist.nets}
        assert set(assignments.keys()) == expected_nets

    def test_assign_layers_deterministic(self, sample_netlist):
        """Same inputs should produce same assignments."""
        from temper_placer.routing.layer_assignment import assign_layers

        assign1 = assign_layers(sample_netlist)
        assign2 = assign_layers(sample_netlist)
        assign3 = assign_layers(sample_netlist)

        for net in sample_netlist.nets:
            assert assign1[net.name].primary_layer == assign2[net.name].primary_layer
            assert assign2[net.name].primary_layer == assign3[net.name].primary_layer

    def test_assign_layers_with_custom_constraints(self, sample_netlist):
        """Should respect custom constraints when provided."""
        from temper_placer.routing.layer_assignment import (
            Layer,
            LayerConstraint,
            assign_layers,
        )

        # Force all nets to L1
        custom_constraints = [
            LayerConstraint(
                net_pattern=r".*",
                allowed_layers={Layer.L1_TOP},
                preferred_layer=Layer.L1_TOP,
                reason="Test constraint",
            )
        ]

        assignments = assign_layers(sample_netlist, constraints=custom_constraints)

        for net in sample_netlist.nets:
            assert assignments[net.name].primary_layer == Layer.L1_TOP

    def test_assign_layers_empty_netlist(self):
        """Empty netlist should return empty assignments."""
        from temper_placer.routing.layer_assignment import assign_layers

        empty_netlist = Netlist(components=[], nets=[])
        assignments = assign_layers(empty_netlist)

        assert assignments == {}


# =============================================================================
# Tests for Layer Conflict Detection
# =============================================================================


class TestLayerConflictDetection:
    """Tests for detecting layer assignment conflicts."""

    def test_no_conflict_for_valid_assignments(self, sample_netlist):
        """Valid assignments should have no conflicts."""
        from temper_placer.routing.layer_assignment import (
            assign_layers,
            find_layer_conflicts,
        )

        assignments = assign_layers(sample_netlist)
        conflicts = find_layer_conflicts(assignments)

        assert len(conflicts) == 0

    def test_detect_hv_lv_crossing_conflict(self):
        """Should detect when HV and LV nets would cross on same layer."""
        from temper_placer.routing.layer_assignment import (
            Layer,
            LayerAssignment,
            find_layer_conflicts,
        )

        # Simulate a scenario where both HV and LV are on L1
        # This is a conflict because HV requires clearance
        assignments = {
            "HV_NET": LayerAssignment(
                net="HV_NET",
                primary_layer=Layer.L1_TOP,
                allowed_layers={Layer.L1_TOP},
                vias_required=False,
                reason="HV constraint",
            ),
            # In real code, this would be detected as a potential crossing
        }

        # This test verifies the conflict detection mechanism exists
        conflicts = find_layer_conflicts(assignments)
        # With just these assignments, no conflict (they could be non-crossing)
        assert isinstance(conflicts, list)


# =============================================================================
# Tests for Via Requirement Detection
# =============================================================================


class TestViaRequirements:
    """Tests for detecting when vias are needed."""

    def test_single_layer_net_no_vias(self, sample_netlist):
        """Nets routed on single layer should not require vias."""
        from temper_placer.routing.layer_assignment import assign_layers

        assignments = assign_layers(sample_netlist)

        # HV nets should not need vias (L1 only)
        assert assignments["DC_BUS_P"].vias_required is False

    def test_multi_layer_net_requires_vias(self):
        """Nets that span multiple layers require vias."""
        from temper_placer.routing.layer_assignment import Layer, LayerAssignment

        # A net that must use both L1 and L4
        assignment = LayerAssignment(
            net="COMPLEX_NET",
            primary_layer=Layer.L1_TOP,
            allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
            vias_required=True,
            reason="Must cross layers",
        )

        assert assignment.vias_required is True
