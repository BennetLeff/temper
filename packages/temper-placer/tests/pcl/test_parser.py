"""
Tests for PCL parser and YAML loader.

Tests cover:
- Parsing individual constraints from dicts
- Loading constraints from YAML files
- Distance unit conversion (mm, mil, in, cm)
- Tier parsing (integer and string)
- Type dispatch for all constraint types
- Error handling for invalid inputs
- Component reference validation
- ConstraintCollection methods
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from temper_placer.pcl import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    Axis,
    BoardSide,
    ConstraintTier,
    ConstraintType,
    DistanceMetric,
    EdgeType,
    EnclosingConstraint,
    LoopAreaConstraint,
    OnSideConstraint,
    PCLParseError,
    SeparatedConstraint,
    load_pcl_collection,
    parse_constraint_dict,
    parse_pcl_file,
)

# ============================================================================
# Distance Parsing Tests
# ============================================================================


def test_distance_parsing_plain_number():
    """Test parsing plain number as mm."""
    constraint_data = {
        "type": "adjacent",
        "a": "Q1",
        "b": "Q2",
        "max_distance_mm": 10.5,
        "tier": 1,
        "because": "Test constraint",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert constraint.max_distance_mm == 10.5


def test_distance_parsing_mm_unit():
    """Test parsing distance with 'mm' unit."""
    constraint_data = {
        "type": "adjacent",
        "a": "Q1",
        "b": "Q2",
        "max_distance_mm": "15mm",
        "tier": 1,
        "because": "Test constraint",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert constraint.max_distance_mm == 15.0


def test_distance_parsing_mil_unit():
    """Test parsing distance with 'mil' unit."""
    constraint_data = {
        "type": "adjacent",
        "a": "Q1",
        "b": "Q2",
        "max_distance_mm": "100mil",  # 100 mil = 2.54 mm
        "tier": 1,
        "because": "Test constraint",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert constraint.max_distance_mm == pytest.approx(2.54, abs=0.01)


def test_distance_parsing_inch_unit():
    """Test parsing distance with 'in' unit."""
    constraint_data = {
        "type": "adjacent",
        "a": "Q1",
        "b": "Q2",
        "max_distance_mm": "0.5in",  # 0.5 in = 12.7 mm
        "tier": 1,
        "because": "Test constraint",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert constraint.max_distance_mm == pytest.approx(12.7, abs=0.1)


def test_distance_parsing_cm_unit():
    """Test parsing distance with 'cm' unit."""
    constraint_data = {
        "type": "adjacent",
        "a": "Q1",
        "b": "Q2",
        "max_distance_mm": "2.5cm",  # 2.5 cm = 25 mm
        "tier": 1,
        "because": "Test constraint",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert constraint.max_distance_mm == 25.0


def test_distance_parsing_invalid_unit():
    """Test that invalid unit raises error."""
    constraint_data = {
        "type": "adjacent",
        "a": "Q1",
        "b": "Q2",
        "max_distance_mm": "10furlongs",
        "tier": 1,
        "because": "Test constraint",
    }

    with pytest.raises(PCLParseError, match="Unknown distance unit"):
        parse_constraint_dict(constraint_data)


# ============================================================================
# Tier Parsing Tests
# ============================================================================


def test_tier_parsing_integer():
    """Test parsing tier from integer."""
    for tier_val, expected in [
        (1, ConstraintTier.HARD),
        (2, ConstraintTier.STRONG),
        (3, ConstraintTier.SOFT),
    ]:
        constraint_data = {
            "type": "adjacent",
            "a": "Q1",
            "b": "Q2",
            "max_distance_mm": 10,
            "tier": tier_val,
            "because": "Test constraint",
        }

        constraint = parse_constraint_dict(constraint_data)
        assert constraint.tier == expected


def test_tier_parsing_string():
    """Test parsing tier from string."""
    for tier_str, expected in [
        ("HARD", ConstraintTier.HARD),
        ("strong", ConstraintTier.STRONG),
        ("Soft", ConstraintTier.SOFT),
    ]:
        constraint_data = {
            "type": "adjacent",
            "a": "Q1",
            "b": "Q2",
            "max_distance_mm": 10,
            "tier": tier_str,
            "because": "Test constraint",
        }

        constraint = parse_constraint_dict(constraint_data)
        assert constraint.tier == expected


def test_tier_parsing_invalid():
    """Test that invalid tier raises error."""
    constraint_data = {
        "type": "adjacent",
        "a": "Q1",
        "b": "Q2",
        "max_distance_mm": 10,
        "tier": 99,
        "because": "Test constraint",
    }

    with pytest.raises(PCLParseError, match="Invalid tier"):
        parse_constraint_dict(constraint_data)


# ============================================================================
# Constraint Type Parsing Tests
# ============================================================================


def test_parse_adjacent_constraint():
    """Test parsing adjacent constraint from dict."""
    constraint_data = {
        "type": "adjacent",
        "a": "Q1",
        "b": "Q2",
        "max_distance_mm": 10,
        "metric": "center_to_center",
        "pin_a": "DRAIN",
        "pin_b": "SOURCE",
        "tier": 1,
        "because": "Minimize commutation loop",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert isinstance(constraint, AdjacentConstraint)
    assert constraint.a == "Q1"
    assert constraint.b == "Q2"
    assert constraint.max_distance_mm == 10
    assert constraint.metric == DistanceMetric.CENTER_TO_CENTER
    assert constraint.pin_a == "DRAIN"
    assert constraint.pin_b == "SOURCE"


def test_parse_separated_constraint():
    """Test parsing separated constraint from dict."""
    constraint_data = {
        "type": "separated",
        "a": "HV_ZONE",
        "b": "MCU_ZONE",
        "min_distance_mm": 10,
        "tier": 1,
        "because": "Safety isolation",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert isinstance(constraint, SeparatedConstraint)
    assert constraint.a == "HV_ZONE"
    assert constraint.b == "MCU_ZONE"
    assert constraint.min_distance_mm == 10


def test_parse_enclosing_constraint():
    """Test parsing enclosing constraint from dict."""
    constraint_data = {
        "type": "enclosing",
        "outer": "HV_ZONE",
        "inner": ["Q1", "Q2", "D1"],
        "margin_mm": 2.0,
        "tier": 1,
        "because": "HV components in zone",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert isinstance(constraint, EnclosingConstraint)
    assert constraint.outer == "HV_ZONE"
    assert constraint.inner == ["Q1", "Q2", "D1"]
    assert constraint.margin_mm == 2.0


def test_parse_aligned_constraint():
    """Test parsing aligned constraint from dict."""
    constraint_data = {
        "type": "aligned",
        "components": ["C1", "C2", "C3"],
        "axis": "horizontal",  # Should parse to X
        "tolerance_mm": 1.0,
        "tier": 3,
        "because": "Align capacitors",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert isinstance(constraint, AlignedConstraint)
    assert constraint.components == ["C1", "C2", "C3"]
    assert constraint.axis == Axis.X  # "horizontal" -> X
    assert constraint.tolerance_mm == 1.0


def test_parse_on_side_constraint():
    """Test parsing on-side constraint from dict."""
    constraint_data = {
        "type": "on_side",
        "components": ["J1", "J2"],
        "side": "left",
        "edge": "flush",
        "max_distance_mm": 2,
        "tier": 1,
        "because": "Connectors on edge",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert isinstance(constraint, OnSideConstraint)
    assert constraint.components == ["J1", "J2"]
    assert constraint.side == BoardSide.LEFT
    assert constraint.edge == EdgeType.FLUSH


def test_parse_anchored_constraint_with_region():
    """Test parsing anchored constraint with region."""
    constraint_data = {
        "type": "anchored",
        "component": "U_MCU",
        "region": [20, 20, 40, 40],
        "tier": 2,
        "because": "MCU centered",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert isinstance(constraint, AnchoredConstraint)
    assert constraint.component == "U_MCU"
    assert constraint.region == (20, 20, 40, 40)
    assert constraint.position is None


def test_parse_anchored_constraint_with_position():
    """Test parsing anchored constraint with position."""
    constraint_data = {
        "type": "anchored",
        "component": "DISPLAY",
        "position": [50, 50],
        "tier": 1,
        "because": "Display centered",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert isinstance(constraint, AnchoredConstraint)
    assert constraint.position == (50, 50)
    assert constraint.region is None


def test_parse_loop_area_constraint():
    """Test parsing loop area constraint from dict."""
    constraint_data = {
        "type": "loop_area",
        "loop_name": "commutation",
        "max_area_mm2": 500.0,
        "tier": 2,
        "because": "Minimize loop area",
    }

    constraint = parse_constraint_dict(constraint_data)
    assert isinstance(constraint, LoopAreaConstraint)
    assert constraint.loop_name == "commutation"
    assert constraint.max_area_mm2 == 500.0


def test_parse_unknown_constraint_type():
    """Test that unknown constraint type raises error."""
    constraint_data = {"type": "magic", "tier": 1, "because": "Test constraint"}

    with pytest.raises(PCLParseError, match="Unknown constraint type"):
        parse_constraint_dict(constraint_data)


# ============================================================================
# Required Field Validation
# ============================================================================


def test_missing_type_field():
    """Test that missing 'type' field raises error."""
    constraint_data = {"a": "Q1", "b": "Q2", "tier": 1, "because": "Test"}

    with pytest.raises(PCLParseError, match="missing required field: 'type'"):
        parse_constraint_dict(constraint_data)


def test_missing_tier_field():
    """Test that missing 'tier' field raises error."""
    constraint_data = {"type": "adjacent", "a": "Q1", "b": "Q2", "because": "Test"}

    with pytest.raises(PCLParseError, match="missing required field: 'tier'"):
        parse_constraint_dict(constraint_data)


def test_missing_because_field():
    """Test that missing 'because' field raises error."""
    constraint_data = {"type": "adjacent", "a": "Q1", "b": "Q2", "tier": 1}

    with pytest.raises(PCLParseError, match="missing required field: 'because'"):
        parse_constraint_dict(constraint_data)


# ============================================================================
# File Loading Tests
# ============================================================================


def test_parse_pcl_file():
    """Test loading constraints from YAML file."""
    # Use the test fixture
    fixture_path = Path(__file__).parent / "fixtures" / "half_bridge.yaml"

    collection = parse_pcl_file(fixture_path)

    assert len(collection) == 8  # 8 constraints in fixture
    assert collection.version == "1.0"
    assert "description" in collection.metadata
    assert collection.metadata["description"] == "Half-bridge induction cooker constraints"


def test_parse_pcl_file_not_found():
    """Test that missing file raises error."""
    with pytest.raises(PCLParseError, match="File not found"):
        parse_pcl_file("nonexistent.yaml")


def test_parse_pcl_file_invalid_yaml():
    """Test that invalid YAML raises error."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("invalid: yaml: content: [")
        f.flush()

        with pytest.raises(PCLParseError, match="YAML parse error"):
            parse_pcl_file(f.name)


def test_parse_pcl_file_missing_constraints_key():
    """Test that missing 'constraints' key raises error."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"version": "1.0"}, f)
        f.flush()

        with pytest.raises(PCLParseError, match="constraints"):
            parse_pcl_file(f.name)


# ============================================================================
# ConstraintCollection Tests
# ============================================================================


def test_constraint_collection_by_type():
    """Test filtering constraints by type."""
    fixture_path = Path(__file__).parent / "fixtures" / "half_bridge.yaml"
    collection = parse_pcl_file(fixture_path)

    adjacent = collection.by_type(ConstraintType.ADJACENT)
    assert len(adjacent) == 2  # 2 adjacent constraints in fixture
    assert all(isinstance(c, AdjacentConstraint) for c in adjacent)


def test_constraint_collection_by_tier():
    """Test filtering constraints by tier."""
    fixture_path = Path(__file__).parent / "fixtures" / "half_bridge.yaml"
    collection = parse_pcl_file(fixture_path)

    hard = collection.by_tier(ConstraintTier.HARD)
    assert len(hard) == 4  # 4 HARD constraints in fixture
    assert all(c.tier == ConstraintTier.HARD for c in hard)


def test_constraint_collection_involving_component():
    """Test finding constraints involving a component."""
    fixture_path = Path(__file__).parent / "fixtures" / "half_bridge.yaml"
    collection = parse_pcl_file(fixture_path)

    q1_constraints = collection.involving_component("Q1")
    assert len(q1_constraints) >= 2  # At least adjacent and enclosing
    assert all(c.involves_component("Q1") for c in q1_constraints)


def test_constraint_collection_validate_component_refs():
    """Test validating component references."""
    fixture_path = Path(__file__).parent / "fixtures" / "half_bridge.yaml"
    collection = parse_pcl_file(fixture_path)

    # All refs exist
    valid_refs = [
        "Q1",
        "Q2",
        "D1",
        "C_DC",
        "U_GATE_DRV",
        "C1",
        "C2",
        "C3",
        "C4",
        "J_AC",
        "J_COIL",
        "U_MCU",
    ]
    errors = collection.validate_component_refs(valid_refs)
    assert len(errors) == 0

    # Some refs missing
    partial_refs = ["Q1", "Q2"]
    errors = collection.validate_component_refs(partial_refs)
    assert len(errors) > 0  # Should have errors for missing components


def test_constraint_collection_skips_zone_validation():
    """Test that zone references (uppercase with _ZONE) are skipped."""
    fixture_path = Path(__file__).parent / "fixtures" / "half_bridge.yaml"
    collection = parse_pcl_file(fixture_path)

    # Provide no zone refs, only component refs
    component_refs = [
        "Q1",
        "Q2",
        "D1",
        "C_DC",
        "U_GATE_DRV",
        "C1",
        "C2",
        "C3",
        "C4",
        "J_AC",
        "J_COIL",
        "U_MCU",
    ]
    errors = collection.validate_component_refs(component_refs)

    # Should not complain about HV_ZONE or MCU_ZONE since they're zones
    assert not any("ZONE" in err for err in errors)


# ============================================================================
# Directory Loading Tests
# ============================================================================


def test_load_pcl_collection_from_directory():
    """Test loading all YAML files from a directory."""
    fixtures_dir = Path(__file__).parent / "fixtures"

    collection = load_pcl_collection(fixtures_dir)

    assert len(collection) >= 8  # At least the 8 from half_bridge.yaml
    assert "sources" in collection.metadata


def test_load_pcl_collection_directory_not_found():
    """Test that missing directory raises error."""
    with pytest.raises(PCLParseError, match="Directory not found"):
        load_pcl_collection("nonexistent_dir")


def test_load_pcl_collection_not_a_directory():
    """Test that file path raises error."""
    fixture_path = Path(__file__).parent / "fixtures" / "half_bridge.yaml"

    with pytest.raises(PCLParseError, match="Not a directory"):
        load_pcl_collection(fixture_path)
