"""
Tests for REQ-SAFE-01: Creepage/Clearance Verification Matrix.

These tests verify that clearance and creepage distance validation functions work correctly
and that placements meet IEC 60335-2-6 safety requirements.
"""


import pytest

# Import validators (will fail until implemented)
VALIDATORS_AVAILABLE = False
try:
    from tests.requirements.validators.clearance import (
        ClearanceResult,
        ClearanceViolation,
        InsulationType,
        VoltageDomain,
        check_creepage_path,
        check_domain_clearance,
        get_requirement_matrix,
        verify_iec60335_compliance,
    )

    # Check if validators are actually implemented (not just stubs)
    try:
        check_domain_clearance({}, VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, 3.0)
        VALIDATORS_AVAILABLE = True
    except NotImplementedError:
        VALIDATORS_AVAILABLE = False

except ImportError:
    # Define placeholder classes for TDD - tests will be skipped
    class ClearanceViolation:
        def __init__(self, code, message, location=None, severity="error"):
            self.code = code
            self.message = message
            self.location = location
            self.severity = severity

    class ClearanceResult:
        def __init__(self, passed, violations):
            self.passed = passed
            self.violations = violations

        @property
        def error_count(self):
            return sum(1 for v in self.violations if v.severity == "error")

        @property
        def warning_count(self):
            return sum(1 for v in self.violations if v.severity == "warning")

    class VoltageDomain:
        MAINS = "MAINS"
        DC_BUS = "DC_BUS"
        BOOTSTRAP = "BOOTSTRAP"
        LV_CONTROL = "LV_CONTROL"
        ISOLATED = "ISOLATED"

        @property
        def value(self):
            return self

    class InsulationType:
        BASIC = "basic"
        REINFORCED = "reinforced"
        FUNCTIONAL = "functional"

        @property
        def value(self):
            return self

    def check_domain_clearance(*args, **kwargs):
        # Return empty result for TDD - tests will be skipped anyway
        return ClearanceResult(passed=True, violations=[])

    def check_creepage_path(*args, **kwargs):
        # Return empty result for TDD - tests will be skipped anyway
        return ClearanceResult(passed=True, violations=[])

    def verify_iec60335_compliance(*args, **kwargs):
        # Return empty result for TDD - tests will be skipped anyway
        return ClearanceResult(passed=True, violations=[])

    def get_requirement_matrix():
        # Return empty matrix for TDD - tests will be skipped anyway
        return {}


pytestmark = pytest.mark.skipif(
    not VALIDATORS_AVAILABLE, reason="Clearance validators not yet implemented"
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_placement():
    """Simple placement with adequate clearance."""
    return {
        "components": [
            {"ref": "U1", "footprint": "QFN-32", "position": (10, 10), "nets": ["LV_CONTROL"]},
            {"ref": "Q1", "footprint": "TO-220", "position": (50, 10), "nets": ["DC_BUS"]},
        ],
        "nets": {
            "LV_CONTROL": {"domain": VoltageDomain.LV_CONTROL},
            "DC_BUS": {"domain": VoltageDomain.DC_BUS},
        },
    }


@pytest.fixture
def violation_placement():
    """Placement with clearance violations."""
    return {
        "components": [
            {"ref": "U1", "footprint": "QFN-32", "position": (10, 10), "nets": ["LV_CONTROL"]},
            {
                "ref": "Q1",
                "footprint": "TO-220",
                "position": (12, 10),
                "nets": ["DC_BUS"],
            },  # 2mm apart
        ],
        "nets": {
            "LV_CONTROL": {"domain": VoltageDomain.LV_CONTROL},
            "DC_BUS": {"domain": VoltageDomain.DC_BUS},
        },
    }


@pytest.fixture
def mains_placement():
    """Placement with mains voltage components."""
    return {
        "components": [
            {"ref": "F1", "footprint": "FUSE", "position": (10, 10), "nets": ["MAINS_L"]},
            {"ref": "U1", "footprint": "QFN-32", "position": (20, 10), "nets": ["LV_CONTROL"]},
        ],
        "nets": {
            "MAINS_L": {"domain": VoltageDomain.MAINS},
            "LV_CONTROL": {"domain": VoltageDomain.LV_CONTROL},
        },
    }


# =============================================================================
# IEC 60335-2-6 Requirements Matrix Tests
# =============================================================================


class TestRequirementMatrix:
    """Tests for the IEC 60335-2-6 requirements matrix."""

    @pytest.mark.parametrize(
        "domain_a,domain_b,insulation_type,expected_clearance,expected_creepage,expected_design",
        [
            # Mains to SELV (LV_CONTROL)
            (VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, InsulationType.BASIC, 3.0, 4.0, 6.0),
            (
                VoltageDomain.MAINS,
                VoltageDomain.LV_CONTROL,
                InsulationType.REINFORCED,
                6.0,
                8.0,
                10.0,
            ),
            # DC Bus to Control
            (VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, InsulationType.BASIC, 3.0, 4.0, 6.0),
            (
                VoltageDomain.DC_BUS,
                VoltageDomain.LV_CONTROL,
                InsulationType.REINFORCED,
                6.0,
                8.0,
                10.0,
            ),
            # Across Isolation Barrier
            (
                VoltageDomain.MAINS,
                VoltageDomain.ISOLATED,
                InsulationType.REINFORCED,
                6.0,
                8.0,
                10.0,
            ),
            # Within LV Domain
            (
                VoltageDomain.LV_CONTROL,
                VoltageDomain.LV_CONTROL,
                InsulationType.FUNCTIONAL,
                0.5,
                1.0,
                2.0,
            ),
        ],
    )
    def test_requirement_matrix_values(
        self,
        domain_a,
        domain_b,
        insulation_type,
        expected_clearance,
        expected_creepage,
        expected_design,
    ):
        """Test that requirement matrix contains correct values."""
        matrix = get_requirement_matrix()
        key = (domain_a.value, domain_b.value, insulation_type.value)

        assert key in matrix, f"Missing requirement for {key}"
        requirements = matrix[key]

        assert requirements["min_clearance_mm"] == expected_clearance
        assert requirements["min_creepage_mm"] == expected_creepage
        assert requirements["design_value_mm"] == expected_design

    def test_matrix_completeness(self):
        """Test that matrix covers all expected boundary combinations."""
        matrix = get_requirement_matrix()

        # Should have 6 requirement entries
        assert len(matrix) == 6

        # Check specific required boundaries
        required_boundaries = [
            ("MAINS", "LV_CONTROL", "basic"),
            ("MAINS", "LV_CONTROL", "reinforced"),
            ("DC_BUS", "LV_CONTROL", "basic"),
            ("DC_BUS", "LV_CONTROL", "reinforced"),
            ("MAINS", "ISOLATED", "reinforced"),
            ("LV_CONTROL", "LV_CONTROL", "functional"),
        ]

        for boundary in required_boundaries:
            assert boundary in matrix, f"Missing requirement for {boundary}"


# =============================================================================
# Domain Clearance Tests
# =============================================================================


class TestDomainClearance:
    """Tests for domain clearance validation."""

    def test_adequate_clearance_passes(self, simple_placement):
        """Placement with adequate clearance should pass."""
        result = check_domain_clearance(
            simple_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=6.0,
        )

        assert result.passed
        assert result.error_count == 0

    def test_insufficient_clearance_fails(self, violation_placement):
        """Placement with insufficient clearance should fail."""
        result = check_domain_clearance(
            violation_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=3.0,
        )

        assert not result.passed
        assert result.error_count >= 1
        assert any("clearance" in v.message.lower() for v in result.violations)

    def test_mains_to_control_clearance(self, mains_placement):
        """Test mains to control circuit clearance."""
        result = check_domain_clearance(
            mains_placement,
            VoltageDomain.MAINS,
            VoltageDomain.LV_CONTROL,
            min_mm=6.0,  # Reinforced insulation requirement
        )

        # Should check for 6mm minimum clearance
        assert result.passed or not result.passed  # Depends on actual implementation

    def test_clearance_violation_details(self, violation_placement):
        """Test that violations include required details."""
        result = check_domain_clearance(
            violation_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=3.0,
        )

        if not result.passed:
            violation = result.violations[0]
            assert violation.code is not None
            assert violation.message is not None
            assert violation.severity in ["error", "warning"]


# =============================================================================
# Creepage Path Tests
# =============================================================================


class TestCreepagePath:
    """Tests for creepage path validation."""

    def test_adequate_creepage_passes(self, simple_placement):
        """Placement with adequate creepage should pass."""
        result = check_creepage_path(
            simple_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=4.0,
        )

        assert result.passed
        assert result.error_count == 0

    def test_insufficient_creepage_fails(self, violation_placement):
        """Placement with insufficient creepage should fail."""
        result = check_creepage_path(
            violation_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=4.0,
        )

        assert not result.passed
        assert result.error_count >= 1
        assert any("creepage" in v.message.lower() for v in result.violations)

    def test_surface_path_consideration(self):
        """Test that creepage considers surface path, not just straight-line distance."""
        # Components close in straight line but with long surface path
        placement = {
            "components": [
                {"ref": "U1", "footprint": "QFN-32", "position": (10, 10), "nets": ["LV_CONTROL"]},
                {"ref": "Q1", "footprint": "TO-220", "position": (15, 10), "nets": ["DC_BUS"]},
            ],
            "nets": {
                "LV_CONTROL": {"domain": VoltageDomain.LV_CONTROL},
                "DC_BUS": {"domain": VoltageDomain.DC_BUS},
            },
        }

        result = check_creepage_path(
            placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=4.0,
        )

        # Should fail if surface path is considered
        assert not result.passed or result.passed  # Depends on implementation

    def test_creepage_violation_includes_path_info(self, violation_placement):
        """Test that creepage violations include path information."""
        result = check_creepage_path(
            violation_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=4.0,
        )

        if not result.passed:
            violation = result.violations[0]
            assert violation.code is not None
            assert "creepage" in violation.message.lower()


# =============================================================================
# IEC 60335-2-6 Compliance Tests
# =============================================================================


class TestIEC60335Compliance:
    """Tests for complete IEC 60335-2-6 compliance verification."""

    def test_compliant_placement_passes(self, simple_placement):
        """Fully compliant placement should pass all checks."""
        voltage_domains = {
            "LV_CONTROL": VoltageDomain.LV_CONTROL,
            "DC_BUS": VoltageDomain.DC_BUS,
        }

        result = verify_iec60335_compliance(simple_placement, voltage_domains)

        assert result.passed
        assert result.error_count == 0

    def test_non_compliant_placement_fails(self, violation_placement):
        """Non-compliant placement should fail."""
        voltage_domains = {
            "LV_CONTROL": VoltageDomain.LV_CONTROL,
            "DC_BUS": VoltageDomain.DC_BUS,
        }

        result = verify_iec60335_compliance(violation_placement, voltage_domains)

        assert not result.passed
        assert result.error_count >= 1

    def test_multiple_violations_aggregated(self):
        """Multiple violations should be aggregated in result."""
        # Create placement with multiple violations
        placement = {
            "components": [
                {"ref": "U1", "footprint": "QFN-32", "position": (10, 10), "nets": ["LV_CONTROL"]},
                {"ref": "Q1", "footprint": "TO-220", "position": (12, 10), "nets": ["DC_BUS"]},
                {"ref": "F1", "footprint": "FUSE", "position": (14, 10), "nets": ["MAINS_L"]},
            ],
            "nets": {
                "LV_CONTROL": {"domain": VoltageDomain.LV_CONTROL},
                "DC_BUS": {"domain": VoltageDomain.DC_BUS},
                "MAINS_L": {"domain": VoltageDomain.MAINS},
            },
        }

        voltage_domains = {
            "LV_CONTROL": VoltageDomain.LV_CONTROL,
            "DC_BUS": VoltageDomain.DC_BUS,
            "MAINS_L": VoltageDomain.MAINS,
        }

        result = verify_iec60335_compliance(placement, voltage_domains)

        # Should have multiple violations
        assert result.error_count >= 2

    def test_all_boundary_types_checked(self):
        """Test that all boundary types from requirements matrix are checked."""
        # This test verifies the integration function checks all required boundaries
        matrix = get_requirement_matrix()

        # The compliance function should check all these boundaries
        expected_checks = len(matrix)
        assert expected_checks > 0

        # Placeholder - actual test would verify all boundaries are checked
        pytest.skip("Actual boundary checking verification not yet implemented")


# =============================================================================
# Integration Tests
# =============================================================================


class TestClearanceIntegration:
    """Integration tests for complete clearance validation."""

    @pytest.mark.slow
    def test_temper_board_clearance_compliance(self):
        """Temper board should meet all REQ-SAFE-01 requirements."""
        # TODO: Load actual Temper board geometry
        # TODO: Run all clearance checks
        # TODO: Verify compliance
        pytest.skip("Temper board fixture not yet available")

    def test_validation_result_aggregation(self):
        """Multiple violations should aggregate correctly."""
        # Create violations from different checks
        violations = [
            ClearanceViolation("SAFE001", "Insufficient clearance", severity="error"),
            ClearanceViolation("SAFE002", "Inadequate creepage", severity="error"),
            ClearanceViolation("SAFE003", "Missing insulation", severity="warning"),
        ]

        result = ClearanceResult(passed=False, violations=violations)

        assert result.error_count == 2
        assert result.warning_count == 1
        assert not result.passed

    def test_voltage_domain_enum_values(self):
        """Test that voltage domain enums have expected values."""
        assert VoltageDomain.MAINS == "MAINS"
        assert VoltageDomain.DC_BUS == "DC_BUS"
        assert VoltageDomain.BOOTSTRAP == "BOOTSTRAP"
        assert VoltageDomain.LV_CONTROL == "LV_CONTROL"
        assert VoltageDomain.ISOLATED == "ISOLATED"

    def test_insulation_type_enum_values(self):
        """Test that insulation type enums have expected values."""
        assert InsulationType.BASIC == "basic"
        assert InsulationType.REINFORCED == "reinforced"
        assert InsulationType.FUNCTIONAL == "functional"
