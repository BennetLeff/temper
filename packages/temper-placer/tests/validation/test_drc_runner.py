"""
Tests for kicad-cli DRC runner.

TDD Task: temper-1my.5.1
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from temper_placer.validation.drc_runner import (
    DrcError,
    DrcResult,
    DrcRunnerError,
    DrcWarning,
    is_kicad_cli_available,
    run_drc,
)


class TestDrcRunnerBasics:
    """Test basic DRC runner functionality."""

    def test_drc_result_dataclass(self) -> None:
        """DrcResult should hold error count, warning count, and lists."""
        result = DrcResult(
            error_count=2,
            warning_count=1,
            errors=[
                DrcError(
                    rule="clearance",
                    severity="error",
                    location=(10.0, 20.0),
                    message="Clearance violation",
                    components=["U1", "U2"],
                )
            ],
            warnings=[],
        )

        assert result.error_count == 2
        assert result.warning_count == 1
        assert len(result.errors) == 1
        assert result.errors[0].rule == "clearance"
        assert result.errors[0].location == (10.0, 20.0)

    def test_drc_error_dataclass(self) -> None:
        """DrcError should hold rule, severity, location, message, components."""
        error = DrcError(
            rule="courtyard_overlap",
            severity="error",
            location=(15.5, 30.2),
            message="Footprint courtyards overlap",
            components=["R1", "C1"],
        )

        assert error.rule == "courtyard_overlap"
        assert error.severity == "error"
        assert error.location[0] == pytest.approx(15.5)
        assert error.location[1] == pytest.approx(30.2)
        assert "R1" in error.components

    def test_drc_warning_dataclass(self) -> None:
        """DrcWarning should have same structure as DrcError."""
        warning = DrcWarning(
            rule="silk_over_pads",
            severity="warning",
            location=(5.0, 10.0),
            message="Silkscreen over pad",
            components=["Q1"],
        )

        assert warning.severity == "warning"


class TestKicadCliAvailability:
    """Test kicad-cli detection."""

    def test_is_kicad_cli_available_returns_bool(self) -> None:
        """is_kicad_cli_available should return a boolean."""
        result = is_kicad_cli_available()
        assert isinstance(result, bool)

    @patch("shutil.which")
    def test_is_available_when_in_path(self, mock_which: MagicMock) -> None:
        """Should return True when kicad-cli is in PATH."""
        mock_which.return_value = "/usr/local/bin/kicad-cli"
        assert is_kicad_cli_available() == True

    @patch("shutil.which")
    def test_not_available_when_not_in_path(self, mock_which: MagicMock) -> None:
        """Should return False when kicad-cli is not found."""
        mock_which.return_value = None
        assert is_kicad_cli_available() == False


class TestDrcRunner:
    """Test DRC execution and result parsing."""

    @pytest.fixture
    def mock_clean_drc_output(self) -> dict:
        """Mock kicad-cli DRC JSON output for a clean board."""
        return {
            "source": "/path/to/board.kicad_pcb",
            "date": "2025-12-16",
            "kicad_version": "8.0.0",
            "violations": [],
        }

    @pytest.fixture
    def mock_error_drc_output(self) -> dict:
        """Mock kicad-cli DRC JSON output with errors."""
        return {
            "source": "/path/to/board.kicad_pcb",
            "date": "2025-12-16",
            "kicad_version": "8.0.0",
            "violations": [
                {
                    "type": "clearance",
                    "severity": "error",
                    "description": "Clearance violation (0.15mm < 0.2mm)",
                    "pos": {"x": 25.0, "y": 30.0},
                    "items": [
                        {"reference": "U1", "description": "Pad 1"},
                        {"reference": "U2", "description": "Pad 3"},
                    ],
                },
                {
                    "type": "courtyard_overlap",
                    "severity": "error",
                    "description": "Footprint courtyards overlap",
                    "pos": {"x": 50.0, "y": 60.0},
                    "items": [
                        {"reference": "R1", "description": "Footprint"},
                        {"reference": "C1", "description": "Footprint"},
                    ],
                },
            ],
        }

    @patch("subprocess.run")
    def test_drc_on_clean_board(
        self, mock_run: MagicMock, mock_clean_drc_output: dict, tmp_path: Path
    ) -> None:
        """Clean board should return 0 errors."""
        import json

        # Create mock PCB file
        pcb_file = tmp_path / "clean_board.kicad_pcb"
        pcb_file.write_text("(kicad_pcb)")

        # Create mock JSON output file
        json_file = tmp_path / "drc_report.json"
        json_file.write_text(json.dumps(mock_clean_drc_output))

        # Mock subprocess.run to simulate kicad-cli execution
        mock_run.return_value = MagicMock(returncode=0)

        with patch(
            "temper_placer.validation.drc_runner._get_drc_json_path", return_value=json_file
        ), patch(
            "temper_placer.validation.drc_runner.is_kicad_cli_available", return_value=True
        ):
            result = run_drc(pcb_file)

        assert result.error_count == 0
        assert result.warning_count == 0
        assert len(result.errors) == 0

    @patch("subprocess.run")
    def test_drc_detects_overlap(
        self, mock_run: MagicMock, mock_error_drc_output: dict, tmp_path: Path
    ) -> None:
        """Board with overlapping footprints should have errors."""
        import json

        pcb_file = tmp_path / "overlap_board.kicad_pcb"
        pcb_file.write_text("(kicad_pcb)")

        json_file = tmp_path / "drc_report.json"
        json_file.write_text(json.dumps(mock_error_drc_output))

        mock_run.return_value = MagicMock(returncode=0)

        with patch(
            "temper_placer.validation.drc_runner._get_drc_json_path", return_value=json_file
        ), patch(
            "temper_placer.validation.drc_runner.is_kicad_cli_available", return_value=True
        ):
            result = run_drc(pcb_file)

        assert result.error_count == 2

        # Find courtyard overlap error
        courtyard_errors = [e for e in result.errors if e.rule == "courtyard_overlap"]
        assert len(courtyard_errors) == 1
        assert "R1" in courtyard_errors[0].components

    @patch("subprocess.run")
    def test_drc_detects_clearance(
        self, mock_run: MagicMock, mock_error_drc_output: dict, tmp_path: Path
    ) -> None:
        """Board with clearance violations should have errors."""
        import json

        pcb_file = tmp_path / "clearance_board.kicad_pcb"
        pcb_file.write_text("(kicad_pcb)")

        json_file = tmp_path / "drc_report.json"
        json_file.write_text(json.dumps(mock_error_drc_output))

        mock_run.return_value = MagicMock(returncode=0)

        with patch(
            "temper_placer.validation.drc_runner._get_drc_json_path", return_value=json_file
        ), patch(
            "temper_placer.validation.drc_runner.is_kicad_cli_available", return_value=True
        ):
            result = run_drc(pcb_file)

        # Find clearance error
        clearance_errors = [e for e in result.errors if e.rule == "clearance"]
        assert len(clearance_errors) == 1
        assert clearance_errors[0].location[0] == pytest.approx(25.0)

    def test_drc_on_nonexistent_file(self, tmp_path: Path) -> None:
        """Non-existent PCB file should raise FileNotFoundError."""
        pcb_file = tmp_path / "nonexistent.kicad_pcb"

        with pytest.raises(FileNotFoundError):
            run_drc(pcb_file)

    @patch("temper_placer.validation.drc_runner.is_kicad_cli_available", return_value=False)
    def test_drc_without_kicad_cli(self, mock_available: MagicMock, tmp_path: Path) -> None:
        """Running DRC without kicad-cli should raise DrcRunnerError."""
        pcb_file = tmp_path / "board.kicad_pcb"
        pcb_file.write_text("(kicad_pcb)")

        with pytest.raises(DrcRunnerError) as exc_info:
            run_drc(pcb_file)

        assert "kicad-cli" in str(exc_info.value).lower()


@pytest.mark.skipif(not is_kicad_cli_available(), reason="kicad-cli not installed")
class TestDrcRunnerIntegration:
    """Integration tests requiring actual kicad-cli installation."""

    def test_real_drc_on_minimal_board(self, tmp_path: Path) -> None:
        """Run real DRC on a minimal valid board."""
        # Create a minimal valid KiCad PCB file
        pcb_content = """(kicad_pcb (version 20240108) (generator "test")
  (general (thickness 1.6))
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
  )
  (setup)
  (net 0 "")
)"""
        pcb_file = tmp_path / "minimal.kicad_pcb"
        pcb_file.write_text(pcb_content)

        result = run_drc(pcb_file)

        # Minimal board should have few/no errors
        assert isinstance(result, DrcResult)
        # Note: May have warnings about missing items, but should parse
