"""Tests for validation.drc module — KiCadDRCValidator pure methods."""
import pytest

from temper_placer.validation.base import ValidationSeverity
from temper_placer.validation.drc import (
    DRCResult,
    DRCViolation,
    DRCViolationType,
    KiCadDRCValidator,
    find_kicad_cli,
)


class TestFindKicadCli:
    """Tests for find_kicad_cli."""

    def test_returns_path_or_none(self):
        result = find_kicad_cli()
        # Either returns a path (if kicad-cli installed) or None
        assert result is None or isinstance(result, str)

    def test_is_callable(self):
        # Just verify the function exists and is callable
        assert callable(find_kicad_cli)


class TestKiCadDRCValidatorPure:
    """Tests for KiCadDRCValidator pure methods that don't need kicad-cli."""

    def test_name(self):
        v = KiCadDRCValidator()
        assert v.name == "KiCadDRCValidator"

    def test_is_available_no_cli(self):
        v = KiCadDRCValidator(kicad_cli_path="/nonexistent/kicad-cli")
        assert v.is_available() is False

    def test_is_available_none(self):
        v = KiCadDRCValidator(kicad_cli_path=None)
        assert v.is_available() is False

    def test_get_version_not_available(self):
        v = KiCadDRCValidator(kicad_cli_path="/nonexistent/kicad-cli")
        assert v.get_version() == "unknown"

    def test_compute_penalty_failed_run(self):
        v = KiCadDRCValidator()
        result = DRCResult(success=False)
        penalty = v.compute_penalty(result)
        assert penalty == 100.0  # High penalty for failed DRC

    def test_compute_penalty_no_violations(self):
        v = KiCadDRCValidator()
        result = DRCResult(success=True, violations=[], error_count=0, warning_count=0)
        penalty = v.compute_penalty(result)
        assert penalty == 0.0  # No violations -> 0 penalty

    def test_to_validation_result_no_errors(self):
        v = KiCadDRCValidator()
        drc_result = DRCResult(success=True, error_count=0, warning_count=0)
        val_result = v.to_validation_result(drc_result)
        assert val_result.valid is True
        assert val_result.validator_name == "KiCadDRCValidator"

    def test_to_validation_result_with_errors(self):
        v = KiCadDRCValidator()
        drc_result = DRCResult(success=True, error_count=2, warning_count=1)
        val_result = v.to_validation_result(drc_result)
        assert val_result.valid is False
        assert "drc_errors" in val_result.metrics
        assert val_result.metrics["drc_errors"] == 2.0
        assert val_result.metrics["drc_warnings"] == 1.0

    def test_validate_not_available(self):
        v = KiCadDRCValidator(kicad_cli_path=None)
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Netlist
        from temper_placer.core.state import PlacementState
        import numpy as np
        state = PlacementState(
            positions=np.zeros((1, 2), dtype=np.float32),
            rotation_logits=np.zeros((1, 4), dtype=np.float32),
        )
        netlist = Netlist(components=[], nets=[])
        board = Board(width=100.0, height=100.0)
        result = v.validate(state, netlist, board)
        # Should be valid (skipped, not failed)
        assert result.valid is True
        assert result.validator_name == "KiCadDRCValidator"
