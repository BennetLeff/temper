"""Tests for ConstraintBuilder fluent API."""

import pytest
import yaml
from temper_placer.constraints.builder import ConstraintBuilder
from temper_placer.io.config_loader import PlacementConstraints


class TestBasicBuilding:
    """Test basic builder functionality."""

    def test_empty_builder(self):
        """Empty builder should produce empty constraints."""
        builder = ConstraintBuilder()
        constraints = builder.build()

        assert len(constraints.component_spacing_rules) == 0
        assert len(constraints.component_groups) == 0
        assert len(constraints.escape_clearances) == 0

    def test_builder_with_base(self):
        """Builder should extend existing constraints."""
        base = PlacementConstraints()
        base.component_spacing_rules.append(
            None  # Placeholder - we'll add actual rule in real usage
        )

        builder = ConstraintBuilder(base)
        constraints = builder.build()

        assert constraints is base


class TestSpacingConstraints:
    """Test spacing constraint building."""

    def test_add_single_spacing(self):
        """Should add single spacing constraint."""
        constraints = ConstraintBuilder().add_spacing("Q1", "Q2", 15.0, tier="hard").build()

        assert len(constraints.component_spacing_rules) == 1
        rule = constraints.component_spacing_rules[0]
        assert rule.component_a == "Q1"
        assert rule.component_b == "Q2"
        assert rule.min_separation_mm == 15.0
        assert rule.tier == "hard"

    def test_add_multiple_spacing(self):
        """Should chain multiple spacing constraints."""
        constraints = (
            ConstraintBuilder()
            .add_spacing("Q1", "Q2", 15.0, tier="hard")
            .add_spacing("U1", "U2", 10.0, tier="soft")
            .build()
        )

        assert len(constraints.component_spacing_rules) == 2

    def test_spacing_defaults(self):
        """Spacing should use correct defaults."""
        constraints = ConstraintBuilder().add_spacing("A", "B", 10.0).build()

        rule = constraints.component_spacing_rules[0]
        assert rule.tier == "soft"
        assert rule.weight == 1.0
        assert rule.description == ""


class TestProximityConstraints:
    """Test proximity constraint building."""

    def test_add_proximity_creates_group(self):
        """Adding proximity should create component group."""
        constraints = ConstraintBuilder().add_proximity("U_GATE", "Q1", 8.0, tier="hard").build()

        assert len(constraints.component_groups) == 1
        group = constraints.component_groups[0]
        assert "U_GATE" in group.components
        assert "Q1" in group.components
        assert len(group.proximity_rules) == 1

        rule = group.proximity_rules[0]
        assert rule.component_a == "U_GATE"
        assert rule.component_b == "Q1"
        assert rule.max_distance_mm == 8.0
        assert rule.tier == "hard"

    def test_add_proximity_with_group_name(self):
        """Should add proximity to named group."""
        constraints = (
            ConstraintBuilder().add_proximity("A", "B", 10.0, group_name="test_group").build()
        )

        group = constraints.component_groups[0]
        assert group.name == "test_group"

    def test_multiple_proximity_same_group(self):
        """Multiple proximity rules can share a group."""
        constraints = (
            ConstraintBuilder()
            .add_proximity("A", "B", 10.0, group_name="grp")
            .add_proximity("B", "C", 10.0, group_name="grp")
            .build()
        )

        assert len(constraints.component_groups) == 1
        group = constraints.component_groups[0]
        assert len(group.proximity_rules) == 2
        assert set(group.components) == {"A", "B", "C"}


class TestEscapeClearanceConstraints:
    """Test escape clearance building."""

    def test_add_escape_clearance(self):
        """Should add escape clearance constraint."""
        constraints = ConstraintBuilder().add_escape_clearance("U_MCU", 10.0, tier="hard").build()

        assert len(constraints.escape_clearances) == 1
        escape = constraints.escape_clearances[0]
        assert escape.component == "U_MCU"
        assert escape.clearance_mm == 10.0
        assert escape.tier == "hard"

    def test_escape_with_priority_sides(self):
        """Should support priority sides."""
        constraints = (
            ConstraintBuilder()
            .add_escape_clearance("U_MCU", priority_sides=["bottom", "right"])
            .build()
        )

        escape = constraints.escape_clearances[0]
        assert escape.priority_sides == ["bottom", "right"]

    def test_escape_auto_compute_clearance(self):
        """Should support None clearance for auto-compute."""
        constraints = (
            ConstraintBuilder()
            .add_escape_clearance("U_MCU")  # No clearance specified
            .build()
        )

        escape = constraints.escape_clearances[0]
        assert escape.clearance_mm is None


class TestRoutingCorridorConstraints:
    """Test routing corridor building."""

    def test_add_routing_corridor(self):
        """Should add routing corridor constraint."""
        constraints = (
            ConstraintBuilder().add_routing_corridor("usb_path", "J_USB", "U_MCU", 6.0).build()
        )

        assert len(constraints.routing_corridors) == 1
        corridor = constraints.routing_corridors[0]
        assert corridor.name == "usb_path"
        assert corridor.from_component == "J_USB"
        assert corridor.to_component == "U_MCU"
        assert corridor.width_mm == 6.0
        assert corridor.keep_clear is True
        assert corridor.tier == "hard"

    def test_corridor_with_nets(self):
        """Should support net list."""
        constraints = (
            ConstraintBuilder()
            .add_routing_corridor("diff_pair", "J1", "U1", 4.0, nets=["USB_D+", "USB_D-"])
            .build()
        )

        corridor = constraints.routing_corridors[0]
        assert corridor.nets == ["USB_D+", "USB_D-"]


class TestThermalConstraints:
    """Test thermal constraint building."""

    def test_add_thermal_constraint(self):
        """Should add thermal constraint."""
        constraints = ConstraintBuilder().add_thermal_constraint(["Q1", "Q2"]).build()

        assert len(constraints.thermal_constraints) == 1
        thermal = constraints.thermal_constraints[0]
        assert thermal.components == ["Q1", "Q2"]
        assert thermal.prefer_edge is True

    def test_thermal_with_custom_params(self):
        """Should support custom thermal parameters."""
        constraints = (
            ConstraintBuilder()
            .add_thermal_constraint(
                ["Q1"], prefer_edge=True, max_distance_from_edge_mm=15.0, min_spacing_mm=10.0
            )
            .build()
        )

        thermal = constraints.thermal_constraints[0]
        assert thermal.max_distance_from_edge_mm == 15.0
        assert thermal.min_spacing_mm == 10.0


class TestGroupConstraints:
    """Test component group building."""

    def test_add_group(self):
        """Should add component group."""
        constraints = ConstraintBuilder().add_group("mcu_subsystem", ["U_MCU", "C1", "C2"]).build()

        assert len(constraints.component_groups) == 1
        group = constraints.component_groups[0]
        assert group.name == "mcu_subsystem"
        assert group.components == ["U_MCU", "C1", "C2"]
        assert group.max_spread_mm == 30.0

    def test_group_with_zone(self):
        """Should support zone constraint."""
        constraints = ConstraintBuilder().add_group("power", ["Q1", "Q2"], zone="HV_zone").build()

        group = constraints.component_groups[0]
        assert group.zone == "HV_zone"


class TestComplexBuilding:
    """Test building complex constraint sets."""

    def test_mixed_constraints(self):
        """Should handle mix of different constraint types."""
        constraints = (
            ConstraintBuilder()
            .add_spacing("Q1", "Q2", 15.0, tier="hard")
            .add_proximity("U_GATE", "Q1", 8.0, tier="hard")
            .add_escape_clearance("U_MCU", 10.0)
            .add_routing_corridor("usb", "J_USB", "U_MCU", 6.0)
            .add_thermal_constraint(["Q1", "Q2"])
            .add_group("gate_drive", ["U_GATE", "Q1", "Q2"])
            .build()
        )

        assert len(constraints.component_spacing_rules) == 1
        assert len(constraints.component_groups) == 2  # proximity + explicit group
        assert len(constraints.escape_clearances) == 1
        assert len(constraints.routing_corridors) == 1
        assert len(constraints.thermal_constraints) == 1


class TestYAMLSerialization:
    """Test YAML serialization."""

    def test_to_yaml_spacing(self):
        """Should serialize spacing rules to YAML."""
        builder = ConstraintBuilder().add_spacing("A", "B", 10.0, tier="hard")
        yaml_str = builder.to_yaml()

        data = yaml.safe_load(yaml_str)
        assert "minimum_spacing" in data
        assert len(data["minimum_spacing"]) == 1
        assert data["minimum_spacing"][0]["components"] == ["A", "B"]
        assert data["minimum_spacing"][0]["min_separation_mm"] == 10.0
        assert data["minimum_spacing"][0]["tier"] == "hard"

    def test_to_yaml_escape_clearance(self):
        """Should serialize escape clearances to YAML."""
        builder = ConstraintBuilder().add_escape_clearance("U_MCU", 10.0)
        yaml_str = builder.to_yaml()

        data = yaml.safe_load(yaml_str)
        assert "escape_clearances" in data
        assert len(data["escape_clearances"]) == 1
        assert data["escape_clearances"][0]["component"] == "U_MCU"

    def test_to_yaml_corridor(self):
        """Should serialize corridors to YAML."""
        builder = ConstraintBuilder().add_routing_corridor("test", "A", "B", 5.0)
        yaml_str = builder.to_yaml()

        data = yaml.safe_load(yaml_str)
        assert "routing_corridors" in data
        assert len(data["routing_corridors"]) == 1
        assert data["routing_corridors"][0]["name"] == "test"

    def test_to_yaml_group_with_proximity(self):
        """Should serialize groups with proximity rules."""
        builder = ConstraintBuilder().add_proximity("A", "B", 10.0, group_name="test")
        yaml_str = builder.to_yaml()

        data = yaml.safe_load(yaml_str)
        assert "groups" in data
        assert len(data["groups"]) == 1
        group = data["groups"][0]
        assert group["name"] == "test"
        assert "proximity" in group
        assert len(group["proximity"]) == 1


class TestValidation:
    """Test constraint validation."""

    def test_validate_with_valid_constraints(self):
        """Should return no errors for valid constraints."""
        builder = ConstraintBuilder().add_spacing("Q1", "Q2", 10.0)

        errors = builder.validate(
            board_width=100.0,
            board_height=100.0,
            available_components=["Q1", "Q2", "U1"],
        )

        assert len(errors) == 0

    def test_validate_catches_missing_component(self):
        """Should catch reference to missing component."""
        builder = ConstraintBuilder().add_escape_clearance("MISSING")

        errors = builder.validate(
            board_width=100.0,
            board_height=100.0,
            available_components=["Q1", "Q2"],
        )

        assert len(errors) > 0
        assert any("MISSING" in err for err in errors)


class TestRoundtrip:
    """Test YAML roundtrip (Python -> YAML -> Python)."""

    def test_spacing_roundtrip(self):
        """Spacing rules should survive roundtrip."""
        original = ConstraintBuilder().add_spacing("A", "B", 10.0, tier="hard").build()

        # Serialize to YAML
        builder = ConstraintBuilder(original)
        yaml_str = builder.to_yaml()

        # Parse back
        data = yaml.safe_load(yaml_str)

        # Verify structure
        assert len(data["minimum_spacing"]) == 1
        assert data["minimum_spacing"][0]["components"] == ["A", "B"]
        assert data["minimum_spacing"][0]["min_separation_mm"] == 10.0
        assert data["minimum_spacing"][0]["tier"] == "hard"
