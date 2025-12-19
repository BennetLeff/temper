"""
TDD Tests for REQ-DFM-03: Assembly Documentation Package.

Tests validation of BOM, CPL, Gerber files, and DNP consistency
as required for PCB assembly documentation.
"""


import pytest

from tests.requirements.validators.documentation import (
    BOMEntry,
    CPLEntry,
    DocumentationValidationResult,
    GerberLayer,
    GerberLayerType,
    check_dnp_consistency,
    validate_bom_completeness,
    validate_cpl_coordinates,
    validate_gerber_layers,
)

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_bom_entries():
    """Create sample BOM entries for testing."""
    return [
        BOMEntry(
            item=1, qty=1, reference="U1", value="ESP32-S3",
            package="QFN-56", description="MCU",
            manufacturer="Espressif", mpn="ESP32-S3-WROOM-1",
            supplier="DigiKey", supplier_pn="1234-5678",
            dnp=False, notes=""
        ),
        BOMEntry(
            item=2, qty=3, reference="R1,R2,R3", value="10k",
            package="0603", description="Resistor",
            manufacturer="Yageo", mpn="RC0603FR-0710KL",
            supplier="DigiKey", supplier_pn="311-10KHRCT-ND",
            dnp=False, notes=""
        ),
        BOMEntry(
            item=3, qty=2, reference="C1,C2", value="100nF",
            package="0603", description="Capacitor",
            manufacturer="Samsung", mpn="CL10B104KB8NNNC",
            supplier="DigiKey", supplier_pn="1276-1000-1-ND",
            dnp=False, notes=""
        ),
    ]


@pytest.fixture
def sample_cpl_entries():
    """Create sample CPL entries for testing."""
    return [
        CPLEntry(designator="U1", mid_x=50.0, mid_y=40.0, layer="Top", rotation=0.0),
        CPLEntry(designator="R1", mid_x=30.0, mid_y=20.0, layer="Top", rotation=90.0),
        CPLEntry(designator="R2", mid_x=35.0, mid_y=20.0, layer="Top", rotation=90.0),
        CPLEntry(designator="R3", mid_x=40.0, mid_y=20.0, layer="Top", rotation=90.0),
        CPLEntry(designator="C1", mid_x=55.0, mid_y=45.0, layer="Top", rotation=0.0),
        CPLEntry(designator="C2", mid_x=55.0, mid_y=35.0, layer="Top", rotation=0.0),
    ]


@pytest.fixture
def sample_netlist_refs():
    """Create sample netlist component references."""
    return {"U1", "R1", "R2", "R3", "C1", "C2"}


@pytest.fixture
def sample_placement_positions():
    """Create sample placement positions matching CPL."""
    return {
        "U1": (50.0, 40.0),
        "R1": (30.0, 20.0),
        "R2": (35.0, 20.0),
        "R3": (40.0, 20.0),
        "C1": (55.0, 45.0),
        "C2": (55.0, 35.0),
    }


@pytest.fixture
def complete_gerber_layers():
    """Create complete set of required Gerber layers."""
    return [
        GerberLayer(GerberLayerType.TOP_COPPER, "board.GTL"),
        GerberLayer(GerberLayerType.GROUND_PLANE, "board.G2L"),
        GerberLayer(GerberLayerType.POWER_PLANE, "board.G3L"),
        GerberLayer(GerberLayerType.BOTTOM_COPPER, "board.GBL"),
        GerberLayer(GerberLayerType.TOP_SOLDER_MASK, "board.GTS"),
        GerberLayer(GerberLayerType.BOTTOM_SOLDER_MASK, "board.GBS"),
        GerberLayer(GerberLayerType.TOP_SILKSCREEN, "board.GTO"),
        GerberLayer(GerberLayerType.BOTTOM_SILKSCREEN, "board.GBO"),
        GerberLayer(GerberLayerType.BOARD_OUTLINE, "board.GKO"),
        GerberLayer(GerberLayerType.DRILL_FILE, "board.TXT"),
    ]


# =============================================================================
# TestValidateBomCompleteness
# =============================================================================

class TestValidateBomCompleteness:
    """Tests for validate_bom_completeness function."""

    def test_valid_bom_all_components_present(self, sample_bom_entries, sample_netlist_refs):
        """All netlist components in BOM, should pass."""
        result = validate_bom_completeness(sample_bom_entries, sample_netlist_refs)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.missing_components) == 0
        assert len(result.extra_components) == 0

    def test_missing_components_in_bom(self, sample_bom_entries, sample_netlist_refs):
        """Netlist has components not in BOM, should fail with errors."""
        # Add extra component to netlist that's not in BOM
        netlist_with_missing = sample_netlist_refs | {"U2", "R4"}
        result = validate_bom_completeness(sample_bom_entries, netlist_with_missing)

        assert result.valid is False
        assert len(result.errors) > 0
        assert "U2" in result.missing_components
        assert "R4" in result.missing_components
        assert "missing from BOM" in result.errors[0]

    def test_extra_components_in_bom(self, sample_bom_entries, sample_netlist_refs):
        """BOM has components not in netlist, should pass with warnings."""
        # Add extra component to BOM that's not in netlist
        extra_bom = sample_bom_entries + [
            BOMEntry(
                item=4, qty=1, reference="U2", value="LM7805",
                package="SOT-223", description="Voltage Regulator",
                manufacturer="Texas Instruments", mpn="LM7805CT",
                supplier="DigiKey", supplier_pn="LM7805CT-ND",
                dnp=False, notes=""
            )
        ]
        result = validate_bom_completeness(extra_bom, sample_netlist_refs)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) > 0
        assert "U2" in result.extra_components
        assert "not in netlist" in result.warnings[0]

    def test_empty_bom_with_netlist(self, sample_netlist_refs):
        """Empty BOM with non-empty netlist, should fail."""
        empty_bom = []
        result = validate_bom_completeness(empty_bom, sample_netlist_refs)

        assert result.valid is False
        assert len(result.errors) > 0
        assert len(result.missing_components) == len(sample_netlist_refs)

    def test_empty_netlist_with_bom(self, sample_bom_entries):
        """Non-empty BOM with empty netlist, should pass with warnings."""
        empty_netlist = set()
        result = validate_bom_completeness(sample_bom_entries, empty_netlist)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) > 0
        assert len(result.extra_components) > 0

    def test_bom_with_comma_separated_refs(self, sample_netlist_refs):
        """BOM entry like "R1,R2,R3" should expand correctly."""
        bom_with_comma_refs = [
            BOMEntry(
                item=1, qty=1, reference="U1", value="ESP32-S3",
                package="QFN-56", description="MCU",
                manufacturer="Espressif", mpn="ESP32-S3-WROOM-1",
                supplier="DigiKey", supplier_pn="1234-5678",
                dnp=False, notes=""
            ),
            BOMEntry(
                item=2, qty=3, reference="R1,R2,R3", value="10k",
                package="0603", description="Resistor",
                manufacturer="Yageo", mpn="RC0603FR-0710KL",
                supplier="DigiKey", supplier_pn="311-10KHRCT-ND",
                dnp=False, notes=""
            ),
        ]
        result = validate_bom_completeness(bom_with_comma_refs, sample_netlist_refs)

        assert result.valid is True
        assert len(result.errors) == 0
        # Should find all individual refs from comma-separated entry
        assert "R1" in result.extra_components or "R1" in result.missing_components

    def test_missing_required_bom_fields(self, sample_netlist_refs):
        """BOM entry missing manufacturer/MPN/etc should error."""
        incomplete_bom = [
            BOMEntry(
                item=1, qty=1, reference="U1", value="ESP32-S3",
                package="QFN-56", description="MCU",
                manufacturer="", mpn="ESP32-S3-WROOM-1",  # Missing manufacturer
                supplier="DigiKey", supplier_pn="1234-5678",
                dnp=False, notes=""
            ),
            BOMEntry(
                item=2, qty=3, reference="R1,R2,R3", value="10k",
                package="0603", description="Resistor",
                manufacturer="Yageo", mpn="",  # Missing MPN
                supplier="DigiKey", supplier_pn="311-10KHRCT-ND",
                dnp=False, notes=""
            ),
        ]
        result = validate_bom_completeness(incomplete_bom, sample_netlist_refs)

        assert result.valid is False
        assert len(result.errors) > 0
        assert any("Missing required field 'manufacturer'" in error for error in result.errors)
        assert any("Missing required field 'mpn'" in error for error in result.errors)

    def test_bom_with_dnp_components(self, sample_netlist_refs):
        """DNP components should still be validated."""
        bom_with_dnp = [
            BOMEntry(
                item=1, qty=1, reference="U1", value="ESP32-S3",
                package="QFN-56", description="MCU",
                manufacturer="Espressif", mpn="ESP32-S3-WROOM-1",
                supplier="DigiKey", supplier_pn="1234-5678",
                dnp=False, notes=""
            ),
            BOMEntry(
                item=2, qty=1, reference="R4", value="0R",
                package="0603", description="DNP Resistor",
                manufacturer="Yageo", mpn="RC0603FR-070RL",
                supplier="DigiKey", supplier_pn="311-0.0RCT-ND",
                dnp=True, notes="Not populated"
            ),
        ]
        # Add DNP component to netlist
        netlist_with_dnp = sample_netlist_refs | {"R4"}
        result = validate_bom_completeness(bom_with_dnp, netlist_with_dnp)

        assert result.valid is True
        assert len(result.errors) == 0
        assert "R4" in result.missing_components or "R4" in result.extra_components


# =============================================================================
# TestValidateCplCoordinates
# =============================================================================

class TestValidateCplCoordinates:
    """Tests for validate_cpl_coordinates function."""

    def test_valid_cpl_coordinates_match(self, sample_cpl_entries, sample_placement_positions):
        """CPL matches placement within tolerance, should pass."""
        result = validate_cpl_coordinates(sample_cpl_entries, sample_placement_positions)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.coordinate_mismatches) == 0

    def test_cpl_coordinate_mismatch(self, sample_cpl_entries, sample_placement_positions):
        """CPL coordinates differ from placement, should fail."""
        # Modify one coordinate to be outside tolerance
        modified_positions = sample_placement_positions.copy()
        modified_positions["U1"] = (100.0, 100.0)  # Far from CPL coordinate (50.0, 40.0)

        result = validate_cpl_coordinates(sample_cpl_entries, modified_positions)

        assert result.valid is False
        assert len(result.coordinate_mismatches) > 0
        assert any("U1" in mismatch[0] for mismatch in result.coordinate_mismatches)

    def test_missing_cpl_entries(self, sample_cpl_entries, sample_placement_positions):
        """Placement has components not in CPL, should fail."""
        # Add extra component to placement that's not in CPL
        extra_positions = sample_placement_positions.copy()
        extra_positions["U2"] = (60.0, 50.0)

        result = validate_cpl_coordinates(sample_cpl_entries, extra_positions)

        assert result.valid is False
        assert len(result.errors) > 0
        assert "missing from CPL" in result.errors[0]

    def test_extra_cpl_entries(self, sample_cpl_entries, sample_placement_positions):
        """CPL has components not in placement, should warn."""
        # Add extra component to CPL that's not in placement
        extra_cpl = sample_cpl_entries + [
            CPLEntry(designator="U2", mid_x=60.0, mid_y=50.0, layer="Top", rotation=0.0)
        ]

        result = validate_cpl_coordinates(extra_cpl, sample_placement_positions)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) > 0
        assert "not in placement" in result.warnings[0]

    def test_cpl_coordinate_tolerance(self, sample_cpl_entries, sample_placement_positions):
        """Coordinates within 0.1mm tolerance should pass."""
        # Modify coordinates to be just within tolerance
        within_tolerance_positions = sample_placement_positions.copy()
        within_tolerance_positions["U1"] = (50.05, 40.05)  # 0.05mm difference

        result = validate_cpl_coordinates(sample_cpl_entries, within_tolerance_positions)

        assert result.valid is True
        assert len(result.coordinate_mismatches) == 0

    def test_cpl_coordinate_outside_tolerance(self, sample_cpl_entries, sample_placement_positions):
        """Coordinates outside 0.1mm should fail."""
        # Modify coordinates to be just outside tolerance
        outside_tolerance_positions = sample_placement_positions.copy()
        outside_tolerance_positions["U1"] = (50.15, 40.15)  # 0.15mm difference

        result = validate_cpl_coordinates(sample_cpl_entries, outside_tolerance_positions)

        assert result.valid is False
        assert len(result.coordinate_mismatches) > 0

    def test_invalid_layer_value(self, sample_placement_positions):
        """Layer not "Top" or "Bottom" should error."""
        invalid_layer_cpl = [
            CPLEntry(designator="U1", mid_x=50.0, mid_y=40.0, layer="Middle", rotation=0.0)
        ]

        result = validate_cpl_coordinates(invalid_layer_cpl, sample_placement_positions)

        assert result.valid is False
        assert len(result.errors) > 0
        assert any("Invalid layer" in error for error in result.errors)

    def test_missing_rotation_value(self, sample_placement_positions):
        """Missing rotation should error."""
        # Create CPL entry with None rotation
        cpl_with_none_rotation = [
            CPLEntry(designator="U1", mid_x=50.0, mid_y=40.0, layer="Top", rotation=None)
        ]

        result = validate_cpl_coordinates(cpl_with_none_rotation, sample_placement_positions)

        assert result.valid is False
        assert len(result.errors) > 0
        assert any("Missing rotation" in error for error in result.errors)

    def test_missing_designator(self, sample_placement_positions):
        """Missing designator should error."""
        # Create CPL entry with empty designator
        cpl_with_empty_designator = [
            CPLEntry(designator="", mid_x=50.0, mid_y=40.0, layer="Top", rotation=0.0)
        ]

        result = validate_cpl_coordinates(cpl_with_empty_designator, sample_placement_positions)

        assert result.valid is False
        assert len(result.errors) > 0
        assert any("Missing designator" in error for error in result.errors)


# =============================================================================
# TestValidateGerberLayers
# =============================================================================

class TestValidateGerberLayers:
    """Tests for validate_gerber_layers function."""

    def test_all_required_layers_present(self, complete_gerber_layers):
        """All 10 required layers present, should pass."""
        result = validate_gerber_layers(complete_gerber_layers)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.missing_layers) == 0

    def test_missing_top_copper(self, complete_gerber_layers):
        """Missing GTL layer should fail."""
        # Remove TOP_COPPER layer
        missing_top_copper = [
            layer for layer in complete_gerber_layers
            if layer.layer_type != GerberLayerType.TOP_COPPER
        ]

        result = validate_gerber_layers(missing_top_copper)

        assert result.valid is False
        assert len(result.missing_layers) > 0
        assert GerberLayerType.TOP_COPPER in result.missing_layers
        assert "GTL" in result.errors[0]

    def test_missing_drill_file(self, complete_gerber_layers):
        """Missing drill file should fail."""
        # Remove DRILL_FILE layer
        missing_drill = [
            layer for layer in complete_gerber_layers
            if layer.layer_type != GerberLayerType.DRILL_FILE
        ]

        result = validate_gerber_layers(missing_drill)

        assert result.valid is False
        assert len(result.missing_layers) > 0
        assert GerberLayerType.DRILL_FILE in result.missing_layers

    def test_missing_multiple_layers(self, complete_gerber_layers):
        """Missing several layers should list all in error."""
        # Remove multiple layers
        missing_multiple = [
            layer for layer in complete_gerber_layers
            if layer.layer_type not in [GerberLayerType.TOP_COPPER, GerberLayerType.BOTTOM_COPPER]
        ]

        result = validate_gerber_layers(missing_multiple)

        assert result.valid is False
        assert len(result.missing_layers) >= 2
        assert GerberLayerType.TOP_COPPER in result.missing_layers
        assert GerberLayerType.BOTTOM_COPPER in result.missing_layers

    def test_duplicate_layer_types(self, complete_gerber_layers):
        """Two GTL files should error."""
        # Add duplicate TOP_COPPER layer
        duplicate_layers = complete_gerber_layers + [
            GerberLayer(GerberLayerType.TOP_COPPER, "board2.GTL")
        ]

        result = validate_gerber_layers(duplicate_layers)

        assert result.valid is False
        assert len(result.errors) > 0
        assert any("Duplicate layer types" in error for error in result.errors)

    def test_wrong_file_extension_warning(self, complete_gerber_layers):
        """Wrong extension should warn but not fail."""
        # Modify one layer to have wrong extension
        wrong_extension = complete_gerber_layers.copy()
        wrong_extension[0] = GerberLayer(GerberLayerType.TOP_COPPER, "board.GTLX")

        result = validate_gerber_layers(wrong_extension)

        assert result.valid is True  # Should still be valid
        assert len(result.warnings) > 0
        assert any("Unexpected file extension" in warning for warning in result.warnings)

    def test_empty_gerber_list(self):
        """Empty list should fail with all layers missing."""
        empty_gerbers = []

        result = validate_gerber_layers(empty_gerbers)

        assert result.valid is False
        assert len(result.missing_layers) == 10  # All required layers missing

    def test_layer_exists_false(self, complete_gerber_layers):
        """Layer with exists=False should be treated as missing."""
        # Set one layer to not exist
        layer_not_exists = complete_gerber_layers.copy()
        layer_not_exists[0] = GerberLayer(GerberLayerType.TOP_COPPER, "board.GTL", exists=False)

        result = validate_gerber_layers(layer_not_exists)

        assert result.valid is False
        assert GerberLayerType.TOP_COPPER in result.missing_layers


# =============================================================================
# TestCheckDnpConsistency
# =============================================================================

class TestCheckDnpConsistency:
    """Tests for check_dnp_consistency function."""

    def test_consistent_dnp_flags(self, sample_bom_entries, sample_cpl_entries):
        """Same DNP flags in BOM and CPL, should pass."""
        # Add DNP flags to CPL entries to match BOM
        cpl_with_dnp = []
        for entry in sample_cpl_entries:
            # Check if this designator is in BOM and if it's DNP
            dnp_value = False
            for bom_entry in sample_bom_entries:
                if entry.designator in bom_entry.reference:
                    dnp_value = bom_entry.dnp
                    break
            # Create a modified CPL entry with DNP attribute
            cpl_entry_dict = {
                'designator': entry.designator,
                'mid_x': entry.mid_x,
                'mid_y': entry.mid_y,
                'layer': entry.layer,
                'rotation': entry.rotation,
                'dnp': dnp_value
            }
            cpl_with_dnp.append(type('CPLEntry', (), cpl_entry_dict)())

        result = check_dnp_consistency(sample_bom_entries, cpl_with_dnp)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.dnp_inconsistencies) == 0

    def test_dnp_mismatch_bom_true_cpl_false(self, sample_bom_entries, sample_cpl_entries):
        """BOM says DNP, CPL says populate, should fail."""
        # Create BOM with DNP component
        bom_with_dnp = sample_bom_entries + [
            BOMEntry(
                item=4, qty=1, reference="R4", value="0R",
                package="0603", description="DNP Resistor",
                manufacturer="Yageo", mpn="RC0603FR-070RL",
                supplier="DigiKey", supplier_pn="311-0.0RCT-ND",
                dnp=True, notes="Not populated"
            )
        ]

        # Create CPL with same component but not DNP
        cpl_with_r4 = sample_cpl_entries + [
            CPLEntry(designator="R4", mid_x=45.0, mid_y=20.0, layer="Top", rotation=90.0)
        ]
        # Add DNP attribute to CPL entry
        cpl_with_r4[-1].dnp = False

        result = check_dnp_consistency(bom_with_dnp, cpl_with_r4)

        assert result.valid is False
        assert len(result.dnp_inconsistencies) > 0
        assert any("R4" in inconsistency[0] for inconsistency in result.dnp_inconsistencies)

    def test_dnp_mismatch_bom_false_cpl_true(self, sample_bom_entries, sample_cpl_entries):
        """BOM says populate, CPL says DNP, should fail."""
        # Create BOM with non-DNP component
        bom_normal = sample_bom_entries + [
            BOMEntry(
                item=4, qty=1, reference="R4", value="10k",
                package="0603", description="Resistor",
                manufacturer="Yageo", mpn="RC0603FR-0710KL",
                supplier="DigiKey", supplier_pn="311-10KHRCT-ND",
                dnp=False, notes=""
            )
        ]

        # Create CPL with same component but DNP
        cpl_with_r4 = sample_cpl_entries + [
            CPLEntry(designator="R4", mid_x=45.0, mid_y=20.0, layer="Top", rotation=90.0)
        ]
        # Add DNP attribute to CPL entry
        cpl_with_r4[-1].dnp = True

        result = check_dnp_consistency(bom_normal, cpl_with_r4)

        assert result.valid is False
        assert len(result.dnp_inconsistencies) > 0
        assert any("R4" in inconsistency[0] for inconsistency in result.dnp_inconsistencies)

    def test_multiple_dnp_inconsistencies(self, sample_bom_entries, sample_cpl_entries):
        """Multiple mismatches should all be reported."""
        # Create BOM with multiple DNP components
        bom_multiple_dnp = sample_bom_entries + [
            BOMEntry(
                item=4, qty=1, reference="R4", value="0R",
                package="0603", description="DNP Resistor",
                manufacturer="Yageo", mpn="RC0603FR-070RL",
                supplier="DigiKey", supplier_pn="311-0.0RCT-ND",
                dnp=True, notes="Not populated"
            ),
            BOMEntry(
                item=5, qty=1, reference="C3", value="10pF",
                package="0603", description="DNP Capacitor",
                manufacturer="Samsung", mpn="CL10B100KAC8NNNC",
                supplier="DigiKey", supplier_pn="1276-100-1-ND",
                dnp=True, notes="Not populated"
            )
        ]

        # Create CPL with mismatched DNP flags
        cpl_multiple = sample_cpl_entries + [
            CPLEntry(designator="R4", mid_x=45.0, mid_y=20.0, layer="Top", rotation=90.0),
            CPLEntry(designator="C3", mid_x=60.0, mid_y=30.0, layer="Top", rotation=0.0)
        ]
        # Set DNP flags opposite to BOM
        cpl_multiple[-2].dnp = False  # R4 should be DNP in BOM
        cpl_multiple[-1].dnp = False  # C3 should be DNP in BOM

        result = check_dnp_consistency(bom_multiple_dnp, cpl_multiple)

        assert result.valid is False
        assert len(result.dnp_inconsistencies) >= 2
        assert any("R4" in inconsistency[0] for inconsistency in result.dnp_inconsistencies)
        assert any("C3" in inconsistency[0] for inconsistency in result.dnp_inconsistencies)

    def test_dnp_component_with_coordinates_warning(self, sample_bom_entries, sample_cpl_entries):
        """DNP component with non-zero coords should warn."""
        # Create BOM with DNP component
        bom_with_dnp = sample_bom_entries + [
            BOMEntry(
                item=4, qty=1, reference="R4", value="0R",
                package="0603", description="DNP Resistor",
                manufacturer="Yageo", mpn="RC0603FR-070RL",
                supplier="DigiKey", supplier_pn="311-0.0RCT-ND",
                dnp=True, notes="Not populated"
            )
        ]

        # Create CPL with DNP component having precise coordinates
        cpl_with_dnp_coords = sample_cpl_entries + [
            CPLEntry(designator="R4", mid_x=45.123, mid_y=20.456, layer="Top", rotation=90.0)
        ]
        cpl_with_dnp_coords[-1].dnp = True

        result = check_dnp_consistency(bom_with_dnp, cpl_with_dnp_coords)

        assert result.valid is True  # Should be valid (only warning)
        assert len(result.warnings) > 0
        assert any("non-zero placement coordinates" in warning for warning in result.warnings)

    def test_all_dnp_components(self, sample_cpl_entries):
        """All components DNP should pass if consistent."""
        # Create BOM with all DNP components
        bom_all_dnp = [
            BOMEntry(
                item=1, qty=1, reference="U1", value="ESP32-S3",
                package="QFN-56", description="MCU",
                manufacturer="Espressif", mpn="ESP32-S3-WROOM-1",
                supplier="DigiKey", supplier_pn="1234-5678",
                dnp=True, notes="Not populated"
            ),
            BOMEntry(
                item=2, qty=3, reference="R1,R2,R3", value="10k",
                package="0603", description="Resistor",
                manufacturer="Yageo", mpn="RC0603FR-0710KL",
                supplier="DigiKey", supplier_pn="311-10KHRCT-ND",
                dnp=True, notes="Not populated"
            ),
        ]

        # Create CPL with all DNP components
        cpl_all_dnp = []
        for entry in sample_cpl_entries:
            cpl_dict = {
                'designator': entry.designator,
                'mid_x': entry.mid_x,
                'mid_y': entry.mid_y,
                'layer': entry.layer,
                'rotation': entry.rotation,
                'dnp': True
            }
            cpl_all_dnp.append(type('CPLEntry', (), cpl_dict)())

        result = check_dnp_consistency(bom_all_dnp, cpl_all_dnp)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.dnp_inconsistencies) == 0

    def test_no_dnp_components(self, sample_bom_entries, sample_cpl_entries):
        """No DNP components should pass."""
        # All BOM entries have dnp=False
        # All CPL entries have dnp=False (default)
        result = check_dnp_consistency(sample_bom_entries, sample_cpl_entries)

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.dnp_inconsistencies) == 0


# =============================================================================
# TestDocumentationValidationResult
# =============================================================================

class TestDocumentationValidationResult:
    """Tests for DocumentationValidationResult dataclass."""

    def test_valid_result_properties(self):
        """Valid result has valid=True, empty errors."""
        result = DocumentationValidationResult(
            valid=True,
            errors=[],
            warnings=[],
            missing_components=set(),
            extra_components=set(),
            coordinate_mismatches=[],
            missing_layers=[],
            dnp_inconsistencies=[],
        )

        assert result.valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert len(result.missing_components) == 0
        assert len(result.extra_components) == 0
        assert len(result.coordinate_mismatches) == 0
        assert len(result.missing_layers) == 0
        assert len(result.dnp_inconsistencies) == 0

    def test_invalid_result_properties(self):
        """Invalid result has valid=False, non-empty errors."""
        result = DocumentationValidationResult(
            valid=False,
            errors=["Missing component U1", "Invalid layer"],
            warnings=["Extra component R1"],
            missing_components={"U1"},
            extra_components={"R1"},
            coordinate_mismatches=[("U1", "Coordinate mismatch")],
            missing_layers=[GerberLayerType.TOP_COPPER],
            dnp_inconsistencies=[("R1", "DNP mismatch")],
        )

        assert result.valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1
        assert "U1" in result.missing_components
        assert "R1" in result.extra_components
        assert len(result.coordinate_mismatches) == 1
        assert len(result.missing_layers) == 1
        assert len(result.dnp_inconsistencies) == 1

    def test_result_with_warnings_still_valid(self):
        """Warnings don't make result invalid."""
        result = DocumentationValidationResult(
            valid=True,
            errors=[],
            warnings=["Some warning", "Another warning"],
            missing_components=set(),
            extra_components=set(),
            coordinate_mismatches=[],
            missing_layers=[],
            dnp_inconsistencies=[],
        )

        assert result.valid is True
        assert len(result.warnings) == 2
        assert len(result.errors) == 0

    def test_result_aggregates_all_issues(self):
        """Result contains all issue types."""
        result = DocumentationValidationResult(
            valid=False,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1", "Warning 2"],
            missing_components={"U1", "U2"},
            extra_components={"R1", "C1"},
            coordinate_mismatches=[("U1", "Coord error"), ("R1", "Coord error")],
            missing_layers=[GerberLayerType.TOP_COPPER, GerberLayerType.BOTTOM_COPPER],
            dnp_inconsistencies=[("R1", "DNP error"), ("C1", "DNP error")],
        )

        # Verify all issue types are present
        assert len(result.errors) == 2
        assert len(result.warnings) == 2
        assert len(result.missing_components) == 2
        assert len(result.extra_components) == 2
        assert len(result.coordinate_mismatches) == 2
        assert len(result.missing_layers) == 2
        assert len(result.dnp_inconsistencies) == 2

        # Verify specific content
        assert "U1" in result.missing_components
        assert "R1" in result.extra_components
        assert result.coordinate_mismatches[0][0] == "U1"
        assert GerberLayerType.TOP_COPPER in result.missing_layers
        assert result.dnp_inconsistencies[0][0] == "R1"
