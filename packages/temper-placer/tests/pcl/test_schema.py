"""
Tests for PCL JSON Schema validation.

This module validates that the PCL JSON Schema correctly enforces:
- Required fields (version, constraints, type, tier, because)
- Because field minimum length (10 characters)
- Tier range (1-3 only)
- Constraint-specific required fields
- Invalid constraint rejection

The schema enables IDE autocompletion and future CLI validation commands.
"""

import json
from pathlib import Path
import pytest
from jsonschema import validate, ValidationError, Draft202012Validator

# Path to schema and fixtures
SCHEMA_PATH = Path(__file__).parent.parent.parent / "configs" / "schemas" / "pcl.schema.json"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def schema():
    """Load PCL JSON schema."""
    with open(SCHEMA_PATH) as f:
        schema_data = json.load(f)
    # Validate that schema itself is valid
    Draft202012Validator.check_schema(schema_data)
    return schema_data


@pytest.fixture
def valid_half_bridge_data():
    """Load valid half_bridge.yaml fixture as dict."""
    import yaml

    with open(FIXTURES_DIR / "half_bridge.yaml") as f:
        return yaml.safe_load(f)


class TestSchemaStructure:
    """Test schema structure and validity."""

    def test_schema_is_valid_json_schema(self, schema):
        """Schema itself should be valid Draft 2020-12."""
        # check_schema raises exception if invalid
        Draft202012Validator.check_schema(schema)

    def test_schema_has_required_metadata(self, schema):
        """Schema should have ID, title, description."""
        assert "$schema" in schema
        assert "$id" in schema
        assert "title" in schema
        assert "description" in schema
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


class TestValidFixtures:
    """Test that valid YAML fixtures pass validation."""

    def test_half_bridge_fixture_validates(self, schema, valid_half_bridge_data):
        """Complete half_bridge.yaml fixture should validate."""
        validate(instance=valid_half_bridge_data, schema=schema)

    def test_all_constraint_types_present_in_fixture(self, valid_half_bridge_data):
        """Fixture should have examples of all constraint types."""
        constraint_types = {c["type"] for c in valid_half_bridge_data["constraints"]}
        expected_types = {
            "adjacent",
            "separated",
            "enclosing",
            "aligned",
            "on_side",
            "anchored",
            "loop_area",
        }
        assert constraint_types == expected_types


class TestRequiredFields:
    """Test that required fields are enforced."""

    def test_version_required(self, schema):
        """Version field is required at top level."""
        invalid = {"constraints": []}
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'version' is a required property" in str(exc_info.value)

    def test_constraints_required(self, schema):
        """Constraints field is required at top level."""
        invalid = {"version": "1.0"}
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'constraints' is a required property" in str(exc_info.value)

    def test_constraint_type_required(self, schema):
        """Each constraint must have type field."""
        invalid = {
            "version": "1.0",
            "constraints": [{"tier": 1, "because": "Some reason that is long enough"}],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)

    def test_constraint_tier_required(self, schema):
        """Each constraint must have tier field."""
        invalid = {
            "version": "1.0",
            "constraints": [{"type": "adjacent", "because": "Some reason that is long enough"}],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)

    def test_constraint_because_required(self, schema):
        """Each constraint must have because field."""
        invalid = {"version": "1.0", "constraints": [{"type": "adjacent", "tier": 1}]}
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)


class TestBecauseFieldValidation:
    """Test that 'because' field is properly enforced."""

    def test_because_too_short_rejected(self, schema):
        """Because field must be at least 10 characters."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "b": "Q2",
                    "max_distance_mm": 10,
                    "tier": 1,
                    "because": "Too short",  # Only 9 chars
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "too short" in str(exc_info.value).lower() or "minLength" in str(exc_info.value)

    def test_because_exactly_10_chars_accepted(self, schema):
        """Because field with exactly 10 characters should validate."""
        valid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "b": "Q2",
                    "max_distance_mm": 10,
                    "tier": 1,
                    "because": "1234567890",  # Exactly 10 chars
                }
            ],
        }
        validate(instance=valid, schema=schema)


class TestTierValidation:
    """Test that tier field is properly validated."""

    def test_tier_zero_rejected(self, schema):
        """Tier 0 is invalid."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "b": "Q2",
                    "max_distance_mm": 10,
                    "tier": 0,
                    "because": "Valid reason that is long enough",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "minimum" in str(exc_info.value).lower() or "0" in str(exc_info.value)

    def test_tier_four_rejected(self, schema):
        """Tier 4 is invalid."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "b": "Q2",
                    "max_distance_mm": 10,
                    "tier": 4,
                    "because": "Valid reason that is long enough",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "maximum" in str(exc_info.value).lower() or "4" in str(exc_info.value)

    def test_tier_negative_rejected(self, schema):
        """Negative tier is invalid."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "b": "Q2",
                    "max_distance_mm": 10,
                    "tier": -1,
                    "because": "Valid reason that is long enough",
                }
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)

    @pytest.mark.parametrize("tier", [1, 2, 3])
    def test_valid_tiers_accepted(self, schema, tier):
        """Tiers 1, 2, 3 are all valid."""
        valid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "b": "Q2",
                    "max_distance_mm": 10,
                    "tier": tier,
                    "because": "Valid reason that is long enough",
                }
            ],
        }
        validate(instance=valid, schema=schema)


class TestAdjacentConstraint:
    """Test adjacent constraint validation."""

    def test_adjacent_missing_a_rejected(self, schema):
        """Adjacent constraint requires 'a' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "b": "Q2",
                    "max_distance_mm": 10,
                    "tier": 1,
                    "because": "Valid reason here",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'a' is a required property" in str(exc_info.value)

    def test_adjacent_missing_b_rejected(self, schema):
        """Adjacent constraint requires 'b' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "max_distance_mm": 10,
                    "tier": 1,
                    "because": "Valid reason here",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'b' is a required property" in str(exc_info.value)

    def test_adjacent_missing_max_distance_rejected(self, schema):
        """Adjacent constraint requires 'max_distance_mm' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "b": "Q2",
                    "tier": 1,
                    "because": "Valid reason here",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'max_distance_mm' is a required property" in str(exc_info.value)

    def test_adjacent_negative_distance_rejected(self, schema):
        """Max distance must be non-negative."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "b": "Q2",
                    "max_distance_mm": -5,
                    "tier": 1,
                    "because": "Valid reason here",
                }
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)

    def test_adjacent_with_optional_fields_accepted(self, schema):
        """Adjacent constraint with optional metric and pins should validate."""
        valid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "b": "Q2",
                    "max_distance_mm": 10,
                    "metric": "pin_to_pin",
                    "pin_a": "OUT_HS",
                    "pin_b": "GATE",
                    "tier": 1,
                    "because": "Valid reason here",
                }
            ],
        }
        validate(instance=valid, schema=schema)


class TestSeparatedConstraint:
    """Test separated constraint validation."""

    def test_separated_missing_min_distance_rejected(self, schema):
        """Separated constraint requires 'min_distance_mm' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "separated",
                    "a": "HV_ZONE",
                    "b": "MCU_ZONE",
                    "tier": 1,
                    "because": "Safety isolation required",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'min_distance_mm' is a required property" in str(exc_info.value)

    def test_separated_valid(self, schema):
        """Valid separated constraint should pass."""
        valid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "separated",
                    "a": "HV_ZONE",
                    "b": "MCU_ZONE",
                    "min_distance_mm": 10,
                    "tier": 1,
                    "because": "IEC 60335-1 reinforced isolation requirement",
                }
            ],
        }
        validate(instance=valid, schema=schema)


class TestEnclosingConstraint:
    """Test enclosing constraint validation."""

    def test_enclosing_missing_outer_rejected(self, schema):
        """Enclosing constraint requires 'outer' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "enclosing",
                    "inner": ["Q1", "Q2"],
                    "tier": 1,
                    "because": "Components must stay in zone",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'outer' is a required property" in str(exc_info.value)

    def test_enclosing_missing_inner_rejected(self, schema):
        """Enclosing constraint requires 'inner' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "enclosing",
                    "outer": "HV_ZONE",
                    "tier": 1,
                    "because": "Components must stay in zone",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'inner' is a required property" in str(exc_info.value)

    def test_enclosing_empty_inner_rejected(self, schema):
        """Inner array must have at least one component."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "enclosing",
                    "outer": "HV_ZONE",
                    "inner": [],
                    "tier": 1,
                    "because": "Components must stay in zone",
                }
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)

    def test_enclosing_valid_with_margin(self, schema):
        """Valid enclosing constraint with optional margin."""
        valid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "enclosing",
                    "outer": "HV_ZONE",
                    "inner": ["Q1", "Q2", "D1", "C_DC"],
                    "margin_mm": 2,
                    "tier": 1,
                    "because": "All high voltage components must stay in HV safety zone with clearance",
                }
            ],
        }
        validate(instance=valid, schema=schema)


class TestAlignedConstraint:
    """Test aligned constraint validation."""

    def test_aligned_missing_axis_rejected(self, schema):
        """Aligned constraint requires 'axis' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "aligned",
                    "components": ["C1", "C2", "C3"],
                    "tier": 3,
                    "because": "Visual consistency",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'axis' is a required property" in str(exc_info.value)

    def test_aligned_single_component_rejected(self, schema):
        """Components array must have at least 2 items."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "aligned",
                    "components": ["C1"],
                    "axis": "x",
                    "tier": 3,
                    "because": "Visual consistency",
                }
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)

    def test_aligned_valid(self, schema):
        """Valid aligned constraint."""
        valid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "aligned",
                    "components": ["C1", "C2", "C3", "C4"],
                    "axis": "x",
                    "tolerance_mm": 0.5,
                    "tier": 3,
                    "because": "Align decoupling capacitors for visual consistency and routing",
                }
            ],
        }
        validate(instance=valid, schema=schema)


class TestOnSideConstraint:
    """Test on_side constraint validation."""

    def test_on_side_missing_side_rejected(self, schema):
        """OnSide constraint requires 'side' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "on_side",
                    "components": ["J_AC"],
                    "edge": "flush",
                    "tier": 1,
                    "because": "Connector access",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'side' is a required property" in str(exc_info.value)

    def test_on_side_missing_edge_rejected(self, schema):
        """OnSide constraint requires 'edge' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "on_side",
                    "components": ["J_AC"],
                    "side": "left",
                    "tier": 1,
                    "because": "Connector access",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'edge' is a required property" in str(exc_info.value)

    def test_on_side_valid(self, schema):
        """Valid on_side constraint."""
        valid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "on_side",
                    "components": ["J_AC", "J_COIL"],
                    "side": "left",
                    "edge": "flush",
                    "max_distance_mm": 2,
                    "tier": 1,
                    "because": "AC and coil connectors must be on left edge for enclosure access",
                }
            ],
        }
        validate(instance=valid, schema=schema)


class TestAnchoredConstraint:
    """Test anchored constraint validation."""

    def test_anchored_missing_component_rejected(self, schema):
        """Anchored constraint requires 'component' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "anchored",
                    "region": [20, 20, 40, 40],
                    "tier": 2,
                    "because": "Centered for routing",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'component' is a required property" in str(exc_info.value)

    def test_anchored_needs_region_or_position(self, schema):
        """Anchored constraint requires either region or position."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "anchored",
                    "component": "U_MCU",
                    "tier": 2,
                    "because": "Centered for routing",
                }
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)

    def test_anchored_with_region_valid(self, schema):
        """Anchored constraint with region."""
        valid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "anchored",
                    "component": "U_MCU",
                    "region": [20, 20, 40, 40],
                    "tier": 2,
                    "because": "MCU centered in MCU zone for antenna clearance and routing",
                }
            ],
        }
        validate(instance=valid, schema=schema)

    def test_anchored_with_position_valid(self, schema):
        """Anchored constraint with position."""
        valid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "anchored",
                    "component": "U_MCU",
                    "position": [30, 30],
                    "tier": 2,
                    "because": "MCU centered in MCU zone for antenna clearance and routing",
                }
            ],
        }
        validate(instance=valid, schema=schema)


class TestLoopAreaConstraint:
    """Test loop_area constraint validation."""

    def test_loop_area_missing_loop_name_rejected(self, schema):
        """LoopArea constraint requires 'loop_name' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {"type": "loop_area", "max_area_mm2": 500, "tier": 2, "because": "Minimize EMI"}
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'loop_name' is a required property" in str(exc_info.value)

    def test_loop_area_missing_max_area_rejected(self, schema):
        """LoopArea constraint requires 'max_area_mm2' field."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "loop_area",
                    "loop_name": "commutation",
                    "tier": 2,
                    "because": "Minimize EMI",
                }
            ],
        }
        with pytest.raises(ValidationError) as exc_info:
            validate(instance=invalid, schema=schema)
        assert "'max_area_mm2' is a required property" in str(exc_info.value)

    def test_loop_area_valid(self, schema):
        """Valid loop_area constraint."""
        valid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "loop_area",
                    "loop_name": "commutation",
                    "max_area_mm2": 500,
                    "tier": 2,
                    "because": "Minimize commutation loop to reduce voltage overshoot and EMI",
                }
            ],
        }
        validate(instance=valid, schema=schema)


class TestEnumValidation:
    """Test that enum values are properly validated."""

    def test_invalid_metric_rejected(self, schema):
        """Invalid metric enum value should be rejected."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "adjacent",
                    "a": "Q1",
                    "b": "Q2",
                    "max_distance_mm": 10,
                    "metric": "invalid_metric",
                    "tier": 1,
                    "because": "Valid reason here",
                }
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)

    def test_invalid_axis_rejected(self, schema):
        """Invalid axis enum value should be rejected."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "aligned",
                    "components": ["C1", "C2"],
                    "axis": "diagonal",
                    "tier": 3,
                    "because": "Valid reason here",
                }
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)

    def test_invalid_side_rejected(self, schema):
        """Invalid side enum value should be rejected."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "on_side",
                    "components": ["J_AC"],
                    "side": "middle",
                    "edge": "flush",
                    "tier": 1,
                    "because": "Valid reason here",
                }
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)

    def test_invalid_edge_rejected(self, schema):
        """Invalid edge enum value should be rejected."""
        invalid = {
            "version": "1.0",
            "constraints": [
                {
                    "type": "on_side",
                    "components": ["J_AC"],
                    "side": "left",
                    "edge": "somewhere",
                    "tier": 1,
                    "because": "Valid reason here",
                }
            ],
        }
        with pytest.raises(ValidationError):
            validate(instance=invalid, schema=schema)
