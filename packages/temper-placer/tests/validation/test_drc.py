"""
Tests for KiCad DRC validator (validation/drc.py).

These tests verify:
- KiCadDRCValidator availability detection
- DRC result parsing from JSON
- Violation classification by type and severity
- Penalty computation
- Error handling (missing kicad-cli, invalid PCB file)
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from temper_placer.validation.drc import (
    KiCadDRCValidator,
    DRCResult,
    DRCViolation,
    DRCSeverity,
    DRCViolationType,
    find_kicad_cli,
    KICAD_CLI_PATHS,
)
from temper_placer.validation.base import ValidationSeverity


class TestDRCViolation:
    """Tests for DRCViolation dataclass."""

    def test_basic_violation(self):
        """Test creating a basic violation."""
        violation = DRCViolation(
            severity=ValidationSeverity.ERROR,
            code="DRC_CLEARANCE",
            message="Clearance violation between U1 and C1",
            violation_type=DRCViolationType.CLEARANCE,
            position=(10.0, 20.0),
            affected_items=["U1", "C1"],
        )
        assert violation.severity == ValidationSeverity.ERROR
        assert violation.violation_type == DRCViolationType.CLEARANCE
        assert violation.position == (10.0, 20.0)
        assert "U1" in violation.affected_items

    def test_to_dict(self):
        """Test dictionary conversion."""
        violation = DRCViolation(
            severity=ValidationSeverity.WARNING,
            code="DRC_SILK_CLEARANCE",
            message="Silk clearance violation",
            violation_type=DRCViolationType.SILK_CLEARANCE,
            rule_name="silk_to_silk",
        )
        d = violation.to_dict()
        assert d["severity"] == "warning"  # name.lower()
        assert d["code"] == "DRC_SILK_CLEARANCE"
        assert d["violation_type"] == "silk_clearance"
        assert d["rule_name"] == "silk_to_silk"


class TestDRCResult:
    """Tests for DRCResult dataclass."""

    def test_success_result_no_violations(self):
        """Test successful DRC with no violations."""
        result = DRCResult(
            success=True,
            violations=[],
            error_count=0,
            warning_count=0,
            elapsed_ms=150.0,
        )
        assert result.success
        assert not result.has_errors
        assert result.total_violations == 0

    def test_result_with_errors(self):
        """Test DRC result with error violations."""
        result = DRCResult(
            success=True,
            violations=[
                DRCViolation(
                    severity=ValidationSeverity.ERROR,
                    code="DRC_CLEARANCE",
                    message="Clearance violation",
                    violation_type=DRCViolationType.CLEARANCE,
                )
            ],
            error_count=1,
            warning_count=0,
        )
        assert result.success
        assert result.has_errors
        assert result.total_violations == 1

    def test_result_with_mixed_violations(self):
        """Test DRC result with both errors and warnings."""
        result = DRCResult(
            success=True,
            error_count=2,
            warning_count=5,
        )
        assert result.total_violations == 7
        assert result.has_errors

    def test_failed_result(self):
        """Test failed DRC result."""
        result = DRCResult(
            success=False,
            raw_output="kicad-cli not found",
        )
        assert not result.success

    def test_summary(self):
        """Test summary generation."""
        result = DRCResult(
            success=True,
            violations=[
                DRCViolation(
                    severity=ValidationSeverity.ERROR,
                    code="DRC_CLEARANCE",
                    message="Clearance violation at U1",
                    violation_type=DRCViolationType.CLEARANCE,
                )
            ],
            error_count=1,
            warning_count=2,
            elapsed_ms=200.0,
        )
        summary = result.summary()
        assert "FAIL" in summary
        assert "1 errors" in summary
        assert "2 warnings" in summary
        assert "200.0ms" in summary


class TestFindKicadCli:
    """Tests for kicad-cli detection."""

    def test_find_in_path(self):
        """Test finding kicad-cli in PATH."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/kicad-cli"
            result = find_kicad_cli()
            assert result == "/usr/bin/kicad-cli"

    def test_find_in_standard_location(self):
        """Test finding kicad-cli in standard location."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            with patch("pathlib.Path.exists") as mock_exists:
                # Simulate finding at first standard location
                def exists_side_effect():
                    return True

                mock_exists.side_effect = [True]
                result = find_kicad_cli()
                # Should return first standard path that exists
                assert result is not None

    def test_not_found(self):
        """Test when kicad-cli is not found."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            with patch("pathlib.Path.exists") as mock_exists:
                mock_exists.return_value = False
                result = find_kicad_cli()
                assert result is None


class TestKiCadDRCValidator:
    """Tests for KiCadDRCValidator class."""

    def test_is_available_when_kicad_missing(self):
        """Test availability check when kicad-cli is not installed."""
        validator = KiCadDRCValidator(kicad_cli_path="/nonexistent/kicad-cli")
        assert not validator.is_available()

    def test_name_property(self):
        """Test validator name property."""
        validator = KiCadDRCValidator()
        assert validator.name == "KiCadDRCValidator"

    def test_run_drc_kicad_not_available(self):
        """Test run_drc when kicad-cli is not available."""
        validator = KiCadDRCValidator(kicad_cli_path="/nonexistent/kicad-cli")
        result = validator.run_drc(Path("/some/board.kicad_pcb"))
        assert not result.success
        assert "kicad-cli not available" in result.raw_output

    def test_run_drc_pcb_not_found(self):
        """Test run_drc when PCB file doesn't exist."""
        # Mock kicad-cli as available
        with patch.object(KiCadDRCValidator, "is_available", return_value=True):
            validator = KiCadDRCValidator(kicad_cli_path="/fake/kicad-cli")
            result = validator.run_drc(Path("/nonexistent/board.kicad_pcb"))
            assert not result.success
            assert "not found" in result.raw_output

    def test_default_severity_weights(self):
        """Test default severity weights."""
        validator = KiCadDRCValidator()
        assert validator.severity_weights["error"] == 10.0
        assert validator.severity_weights["warning"] == 1.0
        assert validator.severity_weights["exclusion"] == 0.0

    def test_custom_severity_weights(self):
        """Test custom severity weights."""
        validator = KiCadDRCValidator(severity_weights={"error": 20.0, "warning": 5.0})
        assert validator.severity_weights["error"] == 20.0
        assert validator.severity_weights["warning"] == 5.0


class TestDRCViolationParsing:
    """Tests for DRC violation parsing."""

    @pytest.fixture
    def validator(self):
        return KiCadDRCValidator()

    def test_parse_clearance_violation(self, validator):
        """Test parsing a clearance violation."""
        drc_data = {
            "violations": [
                {
                    "type": "clearance",
                    "severity": "error",
                    "description": "Clearance violation between U1 pad 1 and C1",
                    "pos": {"x": 100.5, "y": 50.25},
                    "items": [{"reference": "U1"}, {"reference": "C1"}],
                    "rule": "clearance_default",
                }
            ]
        }
        violations = validator._parse_violations(drc_data)
        assert len(violations) == 1
        v = violations[0]
        assert v.violation_type == DRCViolationType.CLEARANCE
        assert v.severity == ValidationSeverity.ERROR
        assert v.position == (100.5, 50.25)
        assert "U1" in v.affected_items
        assert "C1" in v.affected_items

    def test_parse_warning_violation(self, validator):
        """Test parsing a warning-level violation."""
        drc_data = {
            "violations": [
                {
                    "type": "silk_clearance",
                    "severity": "warning",
                    "description": "Silkscreen overlap on R1",
                }
            ]
        }
        violations = validator._parse_violations(drc_data)
        assert len(violations) == 1
        assert violations[0].severity == ValidationSeverity.WARNING
        assert violations[0].violation_type == DRCViolationType.SILK_CLEARANCE

    def test_parse_unknown_violation_type(self, validator):
        """Test parsing unknown violation type falls back to OTHER."""
        drc_data = {
            "violations": [
                {
                    "type": "some_new_check",
                    "severity": "error",
                    "description": "Some new check failed",
                }
            ]
        }
        violations = validator._parse_violations(drc_data)
        assert len(violations) == 1
        assert violations[0].violation_type == DRCViolationType.OTHER

    def test_parse_multiple_violations(self, validator):
        """Test parsing multiple violations."""
        drc_data = {
            "violations": [
                {"type": "clearance", "severity": "error", "description": "V1"},
                {"type": "track_width", "severity": "warning", "description": "V2"},
                {"type": "courtyard_overlap", "severity": "error", "description": "V3"},
            ]
        }
        violations = validator._parse_violations(drc_data)
        assert len(violations) == 3

    def test_parse_empty_violations(self, validator):
        """Test parsing empty violations list."""
        drc_data = {"violations": []}
        violations = validator._parse_violations(drc_data)
        assert len(violations) == 0

    def test_parse_missing_violations_key(self, validator):
        """Test parsing data without violations key."""
        drc_data = {"something_else": "data"}
        violations = validator._parse_violations(drc_data)
        assert len(violations) == 0


class TestPenaltyComputation:
    """Tests for DRC penalty computation."""

    @pytest.fixture
    def validator(self):
        return KiCadDRCValidator()

    def test_penalty_no_violations(self, validator):
        """Test penalty is 0 for clean DRC."""
        result = DRCResult(success=True, violations=[])
        penalty = validator.compute_penalty(result)
        assert penalty == 0.0

    def test_penalty_failed_drc(self, validator):
        """Test high penalty for failed DRC."""
        result = DRCResult(success=False)
        penalty = validator.compute_penalty(result)
        assert penalty == 100.0

    def test_penalty_error_violations(self, validator):
        """Test penalty for error violations."""
        result = DRCResult(
            success=True,
            violations=[
                DRCViolation(
                    severity=ValidationSeverity.ERROR,
                    code="DRC_CLEARANCE",
                    message="Test",
                    violation_type=DRCViolationType.CLEARANCE,
                )
            ],
        )
        penalty = validator.compute_penalty(result)
        # error weight (10) * clearance weight (2.0) = 20
        assert penalty == 20.0

    def test_penalty_warning_violations(self, validator):
        """Test penalty for warning violations."""
        result = DRCResult(
            success=True,
            violations=[
                DRCViolation(
                    severity=ValidationSeverity.WARNING,
                    code="DRC_SILK",
                    message="Test",
                    violation_type=DRCViolationType.SILK_CLEARANCE,
                )
            ],
        )
        penalty = validator.compute_penalty(result)
        # warning weight (1) * silk weight (0.5) = 0.5
        assert penalty == 0.5

    def test_penalty_multiple_violations(self, validator):
        """Test penalty for multiple violations."""
        result = DRCResult(
            success=True,
            violations=[
                DRCViolation(
                    severity=ValidationSeverity.ERROR,
                    code="DRC_CLEARANCE",
                    message="Test1",
                    violation_type=DRCViolationType.CLEARANCE,
                ),
                DRCViolation(
                    severity=ValidationSeverity.ERROR,
                    code="DRC_CLEARANCE",
                    message="Test2",
                    violation_type=DRCViolationType.CLEARANCE,
                ),
                DRCViolation(
                    severity=ValidationSeverity.WARNING,
                    code="DRC_SILK",
                    message="Test3",
                    violation_type=DRCViolationType.SILK_CLEARANCE,
                ),
            ],
        )
        penalty = validator.compute_penalty(result)
        # 2 * (10 * 2.0) + 1 * (1 * 0.5) = 40 + 0.5 = 40.5
        assert penalty == 40.5


class TestValidatorInterface:
    """Test the Validator interface implementation."""

    def test_validate_returns_result(self):
        """Test that validate() returns ValidationResult."""
        from temper_placer.core.state import PlacementState
        from temper_placer.core.netlist import Netlist
        from temper_placer.core.board import Board
        import jax.numpy as jnp

        validator = KiCadDRCValidator()

        # Create minimal test objects
        state = PlacementState(
            positions=jnp.zeros((1, 2)),
            rotation_logits=jnp.zeros((1, 4)),
        )
        netlist = Netlist(
            components=[],
            nets=[],
        )
        board = Board(width=100.0, height=100.0)

        result = validator.validate(state, netlist, board)

        # Should return a ValidationResult
        from temper_placer.validation.base import ValidationResult

        assert isinstance(result, ValidationResult)
        assert result.validator_name == "KiCadDRCValidator"


class TestToValidationResult:
    """Tests for converting DRCResult to ValidationResult."""

    def test_convert_successful_drc(self):
        """Test converting successful DRC result."""
        validator = KiCadDRCValidator()
        drc_result = DRCResult(
            success=True,
            violations=[
                DRCViolation(
                    severity=ValidationSeverity.ERROR,
                    code="DRC_CLEARANCE",
                    message="Test",
                    violation_type=DRCViolationType.CLEARANCE,
                )
            ],
            error_count=1,
            warning_count=0,
            elapsed_ms=100.0,
        )

        val_result = validator.to_validation_result(drc_result)

        assert not val_result.valid  # Has errors
        assert val_result.metrics["drc_errors"] == 1.0
        assert val_result.metrics["drc_warnings"] == 0.0
        assert val_result.metrics["drc_penalty"] > 0
        assert len(val_result.issues) == 1

    def test_convert_clean_drc(self):
        """Test converting clean DRC result."""
        validator = KiCadDRCValidator()
        drc_result = DRCResult(
            success=True,
            violations=[],
            error_count=0,
            warning_count=0,
        )

        val_result = validator.to_validation_result(drc_result)

        assert val_result.valid
        assert val_result.metrics["drc_errors"] == 0.0
        assert val_result.metrics["drc_penalty"] == 0.0
