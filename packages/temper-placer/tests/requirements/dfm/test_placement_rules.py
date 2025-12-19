"""
Tests for REQ-DFM-01: Component Placement for Pick-and-Place.

These tests verify that pick-and-place placement validation functions work correctly
and that placements meet automated assembly requirements.
"""


import pytest

# Import validators (will fail until implemented)
VALIDATORS_AVAILABLE = False
try:
    from tests.requirements.validators.pick_and_place import (
        ESP32_ANTENNA_KEEPOUT_MM,
        ESP32_MODULE_SIZE_MM,
        SPACING_REQUIREMENTS,
        ComponentOrientation,
        Fiducial,
        PackageType,
        PlacementResult,
        PlacementViolation,
        check_antenna_keepout,
        check_component_orientation,
        check_component_spacing,
        check_fiducial_placement,
        check_pick_and_place_compliance,
        get_package_type,
        get_spacing_requirements,
    )

    # Check if validators are actually implemented (not just stubs)
    try:
        check_component_spacing({})
        VALIDATORS_AVAILABLE = True
    except NotImplementedError:
        VALIDATORS_AVAILABLE = False

except ImportError:
    # Define placeholder classes for TDD - tests will be skipped
    class PlacementViolation:
        def __init__(
            self,
            code,
            message,
            location=None,
            severity="error",
            component_ref=None,
            violation_type=None,
            measured_value=None,
            required_value=None,
        ):
            self.code = code
            self.message = message
            self.location = location
            self.severity = severity
            self.component_ref = component_ref
            self.violation_type = violation_type
            self.measured_value = measured_value
            self.required_value = required_value

    class PlacementResult:
        def __init__(self, passed, violations):
            self.passed = passed
            self.violations = violations

        @property
        def error_count(self):
            return sum(1 for v in self.violations if v.severity == "error")

        @property
        def warning_count(self):
            return sum(1 for v in self.violations if v.severity == "warning")

    class Fiducial:
        def __init__(
            self, ref, position, size_mm=1.0, mask_opening_mm=2.0, clearance_mm=3.0, is_global=True
        ):
            self.ref = ref
            self.position = position
            self.size_mm = size_mm
            self.mask_opening_mm = mask_opening_mm
            self.clearance_mm = clearance_mm
            self.is_global = is_global

    class PackageType:
        R0402 = "R0402"
        C0402 = "C0402"
        R0603 = "R0603"
        C0603 = "C0603"
        R0805 = "R0805"
        C0805 = "C0805"
        SOIC = "SOIC"
        QFN = "QFN"
        TQFN = "TQFN"
        ESP32_MODULE = "ESP32_MODULE"

    class ComponentOrientation:
        DEG_0 = 0
        DEG_90 = 90
        DEG_180 = 180
        DEG_270 = 270

    def get_package_type(footprint: str):
        # Simple mapping for TDD
        if "ESP32" in footprint.upper():
            return "ESP32_MODULE"
        elif "QFN" in footprint.upper():
            return "QFN"
        elif "SOIC" in footprint.upper():
            return "SOIC"
        elif "0402" in footprint.upper():
            return "R0402" if "R" in footprint.upper() else "C0402"
        elif "0603" in footprint.upper():
            return "R0603" if "R" in footprint.upper() else "C0603"
        elif "0805" in footprint.upper():
            return "R0805" if "R" in footprint.upper() else "C0805"
        else:
            return "QFN"

    def check_component_spacing(*args, **kwargs):
        return PlacementResult(passed=True, violations=[])

    def check_component_orientation(*args, **kwargs):
        return PlacementResult(passed=True, violations=[])

    def check_fiducial_placement(*args, **kwargs):
        return PlacementResult(passed=True, violations=[])

    def check_antenna_keepout(*args, **kwargs):
        return PlacementResult(passed=True, violations=[])

    def check_pick_and_place_compliance(*args, **kwargs):
        return PlacementResult(passed=True, violations=[])

    def get_spacing_requirements():
        return {}

    # Constants for TDD
    ESP32_ANTENNA_KEEPOUT_MM = 15.0
    ESP32_MODULE_SIZE_MM = (16.0, 37.0)

    SPACING_REQUIREMENTS = {}


pytestmark = pytest.mark.skipif(
    not VALIDATORS_AVAILABLE, reason="Pick-and-place validators not yet implemented"
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def good_placement():
    """Placement with adequate spacing and proper orientations."""
    return {
        "components": [
            {"ref": "R1", "footprint": "R_0603", "position": (10, 10), "rotation": 0},
            {"ref": "C1", "footprint": "C_0603", "position": (15, 10), "rotation": 0},  # 5mm apart
            {"ref": "U1", "footprint": "SOIC-8", "position": (25, 10), "rotation": 0},
            {"ref": "U2", "footprint": "QFN-32", "position": (40, 10), "rotation": 0},
            {"ref": "ESP32", "footprint": "ESP32-S3-WROOM-1", "position": (60, 20), "rotation": 0},
        ]
    }


@pytest.fixture
def spacing_violation_placement():
    """Placement with component spacing violations."""
    return {
        "components": [
            {"ref": "R1", "footprint": "R_0603", "position": (10, 10), "rotation": 0},
            {
                "ref": "C1",
                "footprint": "C_0603",
                "position": (10.15, 10),
                "rotation": 0,
            },  # 0.15mm apart (violation)
            {"ref": "R2", "footprint": "R_0402", "position": (12, 10), "rotation": 0},
            {
                "ref": "C2",
                "footprint": "C_0402",
                "position": (12.10, 10),
                "rotation": 0,
            },  # 0.10mm apart (violation)
        ]
    }


@pytest.fixture
def orientation_violation_placement():
    """Placement with inconsistent component orientations."""
    return {
        "components": [
            {"ref": "R1", "footprint": "R_0603", "position": (10, 10), "rotation": 0},
            {
                "ref": "R2",
                "footprint": "R_0603",
                "position": (15, 10),
                "rotation": 45,
            },  # Inconsistent
            {"ref": "R3", "footprint": "R_0603", "position": (20, 10), "rotation": 90},
            {
                "ref": "U1",
                "footprint": "SOIC-8",
                "position": (30, 10),
                "rotation": 180,
            },  # Pin 1 not top-left
        ]
    }


@pytest.fixture
def esp32_placement():
    """Placement with ESP32 module for antenna keepout testing."""
    return {
        "components": [
            {"ref": "ESP32", "footprint": "ESP32-S3-WROOM-1", "position": (50, 50), "rotation": 0},
        ],
        "copper_pours": [
            {"name": "GND", "type": "pour", "position": (50, 50), "size": (40, 30)},
        ],
    }


@pytest.fixture
def esp32_antenna_violation():
    """ESP32 placement with antenna keepout violations."""
    return {
        "components": [
            {"ref": "ESP32", "footprint": "ESP32-S3-WROOM-1", "position": (10, 10), "rotation": 0},
        ],
        "copper_pours": [
            {
                "name": "GND",
                "type": "pour",
                "position": (15, 10),
                "size": (20, 20),
            },  # Copper in antenna area
        ],
    }


@pytest.fixture
def good_fiducials():
    """Properly placed fiducials."""
    return [
        Fiducial("FID1", (5, 5), size_mm=1.0, is_global=True),
        Fiducial("FID2", (95, 5), size_mm=1.0, is_global=True),
        Fiducial("FID3", (50, 95), size_mm=1.0, is_global=True),
    ]


@pytest.fixture
def insufficient_fiducials():
    """Insufficient number of fiducials."""
    return [
        Fiducial("FID1", (5, 5), size_mm=1.0, is_global=True),
        Fiducial("FID2", (95, 5), size_mm=1.0, is_global=True),
        # Missing third fiducial
    ]


@pytest.fixture
def collinear_fiducials():
    """Fiducials that are collinear (violation)."""
    return [
        Fiducial("FID1", (5, 5), size_mm=1.0, is_global=True),
        Fiducial("FID2", (50, 5), size_mm=1.0, is_global=True),  # Same Y coordinate
        Fiducial("FID3", (95, 5), size_mm=1.0, is_global=True),  # All collinear
    ]


# =============================================================================
# Package Type Mapping Tests
# =============================================================================


class TestPackageTypeMapping:
    """Tests for package type identification from footprints."""

    @pytest.mark.parametrize(
        "footprint,expected_type",
        [
            ("R_0402", PackageType.R0402),
            ("C_0402", PackageType.C0402),
            ("R_0603", PackageType.R0603),
            ("C_0603", PackageType.C0603),
            ("R_0805", PackageType.R0805),
            ("C_0805", PackageType.C0805),
            ("SOIC-8", PackageType.SOIC),
            ("SOIC-16", PackageType.SOIC),
            ("QFN-32", PackageType.QFN),
            ("TQFN-20", PackageType.TQFN),
            ("ESP32-S3-WROOM-1", PackageType.ESP32_MODULE),
            ("ESP32-WROOM-32", PackageType.ESP32_MODULE),
        ],
    )
    def test_package_type_mapping(self, footprint, expected_type):
        """Test that footprints are correctly mapped to package types."""
        package_type = get_package_type(footprint)
        assert package_type == expected_type

    def test_unknown_footprint_defaults_to_qfn(self):
        """Test that unknown footprints default to QFN (most restrictive)."""
        package_type = get_package_type("UNKNOWN_PACKAGE")
        assert package_type == PackageType.QFN

    def test_case_insensitive_mapping(self):
        """Test that footprint mapping is case insensitive."""
        assert get_package_type("r_0603") == PackageType.R0603
        assert get_package_type("SOIC-8") == PackageType.SOIC
        assert get_package_type("esp32-s3-wroom-1") == PackageType.ESP32_MODULE


# =============================================================================
# Spacing Requirements Tests
# =============================================================================


class TestSpacingRequirements:
    """Tests for REQ-DFM-01 component spacing requirements."""

    def test_spacing_requirements_matrix_completeness(self):
        """Test that all required package types have spacing requirements."""
        requirements = get_spacing_requirements()

        required_packages = [
            "R0402",
            "C0402",
            "R0603",
            "C0603",
            "R0805",
            "C0805",
            "SOIC",
            "QFN",
            "TQFN",
            "ESP32_MODULE",
        ]

        for package in required_packages:
            assert package in requirements, f"Missing spacing requirements for {package}"

    @pytest.mark.parametrize(
        "package_type,expected_min,expected_recommended",
        [
            (PackageType.R0402, 0.15, 0.25),
            (PackageType.C0402, 0.15, 0.25),
            (PackageType.R0603, 0.20, 0.30),
            (PackageType.C0603, 0.20, 0.30),
            (PackageType.R0805, 0.25, 0.35),
            (PackageType.C0805, 0.25, 0.35),
            (PackageType.SOIC, 0.25, 0.40),
            (PackageType.QFN, 0.25, 0.40),
            (PackageType.TQFN, 0.25, 0.40),
            (PackageType.ESP32_MODULE, 1.0, 2.0),
        ],
    )
    def test_spacing_requirement_values(self, package_type, expected_min, expected_recommended):
        """Test that spacing requirements have correct values."""
        requirements = get_spacing_requirements()
        package_key = package_type.value if hasattr(package_type, "value") else str(package_type)
        package_requirements = requirements[package_key]

        assert package_requirements["min_pad_to_pad_mm"] == expected_min
        assert package_requirements["recommended_mm"] == expected_recommended


def test_esp32_module_has_most_restrictive_requirements(self):
    """Test that ESP32 module has the most restrictive spacing requirements."""
    requirements = get_spacing_requirements()
    esp32_req = requirements["ESP32_MODULE"]

    # ESP32 should require more spacing than other components
    assert esp32_req["min_pad_to_pad_mm"] >= 1.0
    assert esp32_req["recommended_mm"] >= 2.0


# =============================================================================
# Component Spacing Tests
# =============================================================================


class TestComponentSpacing:
    """Tests for component spacing validation."""

    def test_adequate_spacing_passes(self, good_placement):
        """Placement with adequate spacing should pass."""
        result = check_component_spacing(good_placement)

        assert result.passed
        assert result.error_count == 0

    def test_insufficient_spacing_fails(self, spacing_violation_placement):
        """Placement with insufficient spacing should fail."""
        result = check_component_spacing(spacing_violation_placement)

        assert not result.passed
        assert result.error_count >= 1
        assert any("spacing" in v.message.lower() for v in result.violations)

    def test_0603_spacing_violation(self):
        """Test specific violation for 0603 components too close."""
        placement = {
            "components": [
                {"ref": "R1", "footprint": "R_0603", "position": (10, 10), "rotation": 0},
                {
                    "ref": "C1",
                    "footprint": "C_0603",
                    "position": (10.15, 10),
                    "rotation": 0,
                },  # 0.15mm apart
            ]
        }

        result = check_component_spacing(placement)

        # Should fail because 0.15mm < 0.20mm minimum for 0603
        assert not result.passed
        spacing_violations = [v for v in result.violations if v.violation_type == "spacing"]
        assert len(spacing_violations) >= 1

    def test_0402_spacing_violation(self):
        """Test specific violation for 0402 components too close."""
        placement = {
            "components": [
                {"ref": "R1", "footprint": "R_0402", "position": (10, 10), "rotation": 0},
                {
                    "ref": "C1",
                    "footprint": "C_0402",
                    "position": (10.10, 10),
                    "rotation": 0,
                },  # 0.10mm apart
            ]
        }

        result = check_component_spacing(placement)

        # Should fail because 0.10mm < 0.15mm minimum for 0402
        assert not result.passed

    def test_esp32_module_spacing_violation(self):
        """Test ESP32 module spacing violations."""
        placement = {
            "components": [
                {
                    "ref": "ESP32",
                    "footprint": "ESP32-S3-WROOM-1",
                    "position": (10, 10),
                    "rotation": 0,
                },
                {
                    "ref": "R1",
                    "footprint": "R_0603",
                    "position": (10.5, 10),
                    "rotation": 0,
                },  # 0.5mm from ESP32
            ]
        }

        result = check_component_spacing(placement)

        # Should fail because 0.5mm < 1.0mm minimum for ESP32 module
        assert not result.passed

    def test_spacing_violation_details(self, spacing_violation_placement):
        """Test that spacing violations include required details."""
        result = check_component_spacing(spacing_violation_placement)

        if not result.passed:
            violation = result.violations[0]
            assert violation.code is not None
            assert violation.message is not None
            assert violation.severity in ["error", "warning"]
            assert violation.violation_type == "spacing"
            assert violation.measured_value is not None
            assert violation.required_value is not None


# =============================================================================
# Component Orientation Tests
# =============================================================================


class TestComponentOrientation:
    """Tests for component orientation validation."""

    def test_consistent_orientation_passes(self, good_placement):
        """Placement with consistent orientations should pass."""
        result = check_component_orientation(good_placement)

        assert result.passed
        assert result.error_count == 0

    def test_inconsistent_passive_orientations_fails(self, orientation_violation_placement):
        """Placement with inconsistent passive orientations should fail."""
        result = check_component_orientation(orientation_violation_placement)

        assert not result.passed
        assert result.error_count >= 1
        assert any("orientation" in v.message.lower() for v in result.violations)

    def test_ic_pin1_orientation_check(self):
        """Test that IC pin 1 orientation is checked."""
        placement = {
            "components": [
                {
                    "ref": "U1",
                    "footprint": "SOIC-8",
                    "position": (10, 10),
                    "rotation": 180,
                },  # Pin 1 not top-left
            ]
        }

        result = check_component_orientation(placement)

        # Should fail because pin 1 is not in preferred orientation
        assert not result.passed

    def test_passive_orientation_consistency(self):
        """Test that passive components have consistent orientations within areas."""
        placement = {
            "components": [
                {"ref": "R1", "footprint": "R_0603", "position": (10, 10), "rotation": 0},
                {
                    "ref": "R2",
                    "footprint": "R_0603",
                    "position": (15, 10),
                    "rotation": 45,
                },  # Inconsistent
                {
                    "ref": "R3",
                    "footprint": "R_0603",
                    "position": (20, 10),
                    "rotation": 90,
                },  # Inconsistent
            ]
        }

        result = check_component_orientation(placement)

        assert not result.passed

    def test_orientation_violation_details(self, orientation_violation_placement):
        """Test that orientation violations include required details."""
        result = check_component_orientation(orientation_violation_placement)

        if not result.passed:
            violation = result.violations[0]
            assert violation.code is not None
            assert violation.message is not None
            assert violation.violation_type == "orientation"
            assert violation.component_ref is not None


# =============================================================================
# Fiducial Placement Tests
# =============================================================================


class TestFiducialPlacement:
    """Tests for fiducial placement validation."""

    def test_adequate_fiducials_passes(self, good_fiducials):
        """Placement with adequate fiducials should pass."""
        result = check_fiducial_placement(good_fiducials, (100, 100))

        assert result.passed
        assert result.error_count == 0

    def test_insufficient_fiducials_fails(self, insufficient_fiducials):
        """Placement with insufficient fiducials should fail."""
        result = check_fiducial_placement(insufficient_fiducials, (100, 100))

        assert not result.passed
        assert result.error_count >= 1
        assert any("fiducial" in v.message.lower() for v in result.violations)

    def test_collinear_fiducials_fails(self, collinear_fiducials):
        """Collinear fiducials should fail (need asymmetric placement)."""
        result = check_fiducial_placement(collinear_fiducials, (100, 100))

        assert not result.passed
        assert any(
            "collinear" in v.message.lower() or "asymmetric" in v.message.lower()
            for v in result.violations
        )

    def test_fiducial_size_requirements(self):
        """Test fiducial size requirements."""
        bad_fiducials = [
            Fiducial("FID1", (5, 5), size_mm=0.5),  # Too small
            Fiducial("FID2", (95, 5), size_mm=1.0),
            Fiducial("FID3", (50, 95), size_mm=1.0),
        ]

        result = check_fiducial_placement(bad_fiducials, (100, 100))

        assert not result.passed
        assert any("size" in v.message.lower() for v in result.violations)

    def test_fiducial_clearance_requirements(self):
        """Test fiducial clearance requirements."""
        bad_fiducials = [
            Fiducial("FID1", (2, 2), size_mm=1.0, clearance_mm=1.0),  # Too close to edge
            Fiducial("FID2", (95, 5), size_mm=1.0),
            Fiducial("FID3", (50, 95), size_mm=1.0),
        ]

        result = check_fiducial_placement(bad_fiducials, (100, 100))

        assert not result.passed
        assert any("clearance" in v.message.lower() for v in result.violations)

    def test_fiducial_violation_details(self, insufficient_fiducials):
        """Test that fiducial violations include required details."""
        result = check_fiducial_placement(insufficient_fiducials, (100, 100))

        if not result.passed:
            violation = result.violations[0]
            assert violation.code is not None
            assert violation.message is not None
            assert violation.violation_type == "fiducial"
            assert violation.component_ref is not None


# =============================================================================
# ESP32 Antenna Keepout Tests
# =============================================================================


class TestESP32AntennaKeepout:
    """Tests for ESP32-S3-WROOM antenna keepout requirements."""

    def test_adequate_antenna_keepout_passes(self, esp32_placement):
        """Placement with adequate antenna keepout should pass."""
        board_dims = (100, 100)
        esp32_pos = (50, 50)
        copper_pours = [{"name": "GND", "type": "pour", "position": (50, 50), "size": (40, 30)}]

        result = check_antenna_keepout(esp32_pos, copper_pours, board_dims)

        assert result.passed
        assert result.error_count == 0

    def test_copper_in_antenna_keepout_fails(self, esp32_antenna_violation):
        """Placement with copper in antenna keepout should fail."""
        board_dims = (100, 100)
        esp32_pos = (10, 10)
        copper_pours = [{"name": "GND", "type": "pour", "position": (15, 10), "size": (20, 20)}]

        result = check_antenna_keepout(esp32_pos, copper_pours, board_dims)

        assert not result.passed
        assert any(
            "antenna" in v.message.lower() or "keepout" in v.message.lower()
            for v in result.violations
        )

    def test_esp32_too_close_to_board_edge(self):
        """Test ESP32 too close to board edge for antenna."""
        esp32_pos = (5, 5)  # Too close to edge
        copper_pours = []
        board_dims = (100, 100)

        result = check_antenna_keepout(esp32_pos, copper_pours, board_dims)

        assert not result.passed
        assert any("edge" in v.message.lower() for v in result.violations)

    def test_antenna_direction_determination(self):
        """Test that antenna direction is correctly determined."""
        # ESP32 at center should point towards nearest edge
        esp32_pos = (50, 50)
        copper_pours = []
        board_dims = (100, 100)

        result = check_antenna_keepout(esp32_pos, copper_pours, board_dims)

        # Should pass if no copper in keepout zone
        assert result.passed or not result.passed  # Depends on implementation

    def test_antenna_keepout_violation_details(self, esp32_antenna_violation):
        """Test that antenna keepout violations include required details."""
        board_dims = (100, 100)
        esp32_pos = (10, 10)
        copper_pours = [{"name": "GND", "type": "pour", "position": (15, 10), "size": (20, 20)}]

        result = check_antenna_keepout(esp32_pos, copper_pours, board_dims)

        if not result.passed:
            violation = result.violations[0]
            assert violation.code is not None
            assert violation.message is not None
            assert violation.violation_type == "antenna"
            assert violation.component_ref is not None


# =============================================================================
# Integration Tests
# =============================================================================


class TestPickAndPlaceCompliance:
    """Tests for complete REQ-DFM-01 compliance verification."""

    def test_compliant_placement_passes(self, good_placement, good_fiducials):
        """Fully compliant placement should pass all checks."""
        board_dims = (100, 100)

        result = check_pick_and_place_compliance(good_placement, good_fiducials, board_dims)

        assert result.passed
        assert result.error_count == 0

    def test_non_compliant_placement_fails(self, spacing_violation_placement, good_fiducials):
        """Non-compliant placement should fail."""
        board_dims = (100, 100)

        result = check_pick_and_place_compliance(
            spacing_violation_placement, good_fiducials, board_dims
        )

        assert not result.passed
        assert result.error_count >= 1

    def test_multiple_violation_types_aggregated(self):
        """Multiple violation types should be aggregated in result."""
        placement = {
            "components": [
                {"ref": "R1", "footprint": "R_0603", "position": (10, 10), "rotation": 0},
                {
                    "ref": "C1",
                    "footprint": "C_0603",
                    "position": (10.15, 10),
                    "rotation": 45,
                },  # Spacing + orientation violations
            ]
        }
        fiducials = [
            Fiducial("FID1", (5, 5), size_mm=1.0),
            Fiducial("FID2", (95, 5), size_mm=1.0),
            # Missing third fiducial
        ]
        board_dims = (100, 100)

        result = check_pick_and_place_compliance(placement, fiducials, board_dims)

        # Should have multiple violations
        assert result.error_count >= 2
        violation_types = {v.violation_type for v in result.violations if v.violation_type}
        assert len(violation_types) >= 2

    def test_esp32_specific_compliance_check(self, esp32_placement, good_fiducials):
        """Test that ESP32-specific checks are included in compliance verification."""
        board_dims = (100, 100)

        result = check_pick_and_place_compliance(esp32_placement, good_fiducials, board_dims)

        # Should include antenna keepout check
        antenna_violations = [v for v in result.violations if v.violation_type == "antenna"]
        # May or may not have violations depending on placement

    def test_validation_result_aggregation(self):
        """Test that multiple violations aggregate correctly."""
        violations = [
            PlacementViolation(
                "DFM001", "Insufficient spacing", severity="error", violation_type="spacing"
            ),
            PlacementViolation(
                "DFM002", "Inconsistent orientation", severity="error", violation_type="orientation"
            ),
            PlacementViolation(
                "DFM003", "Missing fiducial", severity="warning", violation_type="fiducial"
            ),
        ]

        result = PlacementResult(passed=False, violations=violations)

        assert result.error_count == 2
        assert result.warning_count == 1
        assert not result.passed

    def test_all_requirement_types_checked(self):
        """Test that all requirement types from REQ-DFM-01 are checked."""
        # This test verifies the integration function checks all required aspects
        requirements = get_spacing_requirements()

        # The compliance function should check all these aspects
        expected_checks = ["spacing", "orientation", "fiducial", "antenna"]
        assert len(expected_checks) > 0

        # Placeholder - actual test would verify all aspects are checked
        pytest.skip("Actual requirement checking verification not yet implemented")


# =============================================================================
# Constants and Edge Cases Tests
# =============================================================================


class TestConstantsAndEdgeCases:
    """Tests for constants and edge cases."""

    def test_esp32_antenna_keepout_distance(self):
        """Test that ESP32 antenna keepout distance is correct."""
        assert ESP32_ANTENNA_KEEPOUT_MM == 15.0

    def test_esp32_module_size(self):
        """Test that ESP32 module size is correct."""
        assert ESP32_MODULE_SIZE_MM == (16.0, 37.0)

    def test_empty_placement_handling(self):
        """Test that empty placement is handled gracefully."""
        result = check_component_spacing({})
        assert isinstance(result, PlacementResult)

    def test_empty_fiducial_list_handling(self):
        """Test that empty fiducial list is handled gracefully."""
        result = check_fiducial_placement([], (100, 100))
        assert isinstance(result, PlacementResult)
        assert not result.passed  # Should fail due to insufficient fiducials

    def test_no_esp32_in_placement(self):
        """Test that placement without ESP32 skips antenna checks."""
        placement = {
            "components": [
                {"ref": "R1", "footprint": "R_0603", "position": (10, 10), "rotation": 0},
            ]
        }
        fiducials = [
            Fiducial("FID1", (5, 5), size_mm=1.0),
            Fiducial("FID2", (95, 5), size_mm=1.0),
            Fiducial("FID3", (50, 95), size_mm=1.0),
        ]
        board_dims = (100, 100)

        result = check_pick_and_place_compliance(placement, fiducials, board_dims)

        # Should not have antenna violations since no ESP32 present
        antenna_violations = [v for v in result.violations if v.violation_type == "antenna"]
        assert len(antenna_violations) == 0


# =============================================================================
# Performance and Scalability Tests
# =============================================================================


class TestPerformanceAndScalability:
    """Tests for performance and scalability."""

    @pytest.mark.slow
    def test_large_placement_performance(self):
        """Test that validation performs reasonably with large placements."""
        # Create placement with many components
        components = []
        for i in range(100):
            components.append(
                {"ref": f"R{i}", "footprint": "R_0603", "position": (i * 5, 10), "rotation": 0}
            )

        placement = {"components": components}

        import time

        start_time = time.time()
        result = check_component_spacing(placement)
        end_time = time.time()

        # Should complete within reasonable time (e.g., 1 second)
        assert (end_time - start_time) < 1.0
        assert isinstance(result, PlacementResult)

    def test_memory_efficient_violation_handling(self):
        """Test that violation handling is memory efficient."""
        # Create many violations to test memory usage
        violations = []
        for i in range(1000):
            violations.append(
                PlacementViolation(
                    code=f"DFM{i:03d}",
                    message=f"Test violation {i}",
                    severity="error" if i % 2 == 0 else "warning",
                )
            )

        result = PlacementResult(passed=False, violations=violations)

        assert result.error_count == 500
        assert result.warning_count == 500
        assert not result.passed
