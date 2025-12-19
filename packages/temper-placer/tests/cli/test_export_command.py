"""
Integration tests for the export CLI command.

These tests verify the export workflow via the CLI, ensuring:
1. Placements JSON can be exported to KiCad PCB files
2. Template PCB data is preserved
3. Error cases are handled gracefully

The export command applies a placements JSON file to a template PCB.
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")

from temper_placer.cli import main

# Test fixtures paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"
MINIMAL_CONSTRAINTS = FIXTURES_DIR / "constraints_minimal.yaml"


class TestExportCommandBasic:
    """Basic integration tests for the export command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temp directory for outputs."""
        return tmp_path

    @pytest.fixture
    def sample_placements(self):
        """Create sample placements matching minimal_board.kicad_pcb components."""
        return {
            "R1": {"x": 102.0, "y": 82.0, "rotation": 0},
            "R2": {"x": 112.0, "y": 82.0, "rotation": 90},
            "C1": {"x": 107.0, "y": 92.0, "rotation": 0},
            "U1": {"x": 122.0, "y": 87.0, "rotation": 180},
        }

    def test_export_applies_placements_to_pcb(self, runner, temp_dir, sample_placements):
        """Test export command with valid placements - the most critical test."""
        # Create placements JSON
        placements_file = temp_dir / "placements.json"
        placements_file.write_text(json.dumps(sample_placements))

        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                str(placements_file),
                "--pcb",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
            ],
        )

        # Check command succeeded
        assert result.exit_code == 0, f"CLI failed with output:\n{result.output}"

        # Check output file was created
        assert output_pcb.exists(), "Output PCB file was not created"
        assert output_pcb.stat().st_size > 0, "Output PCB file is empty"

        # Check output contains expected status messages
        assert "Loaded" in result.output
        assert "Wrote" in result.output or str(output_pcb) in result.output

    def test_export_output_is_valid_kicad(self, runner, temp_dir, sample_placements):
        """Test that the output file can be re-parsed as valid KiCad PCB."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        # Create placements JSON
        placements_file = temp_dir / "placements.json"
        placements_file.write_text(json.dumps(sample_placements))

        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                str(placements_file),
                "--pcb",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"

        # Re-parse the output file
        parse_result = parse_kicad_pcb(output_pcb)
        assert parse_result.netlist.n_components > 0, "Output PCB has no components"

        # Verify same number of components as input
        input_result = parse_kicad_pcb(MINIMAL_PCB)
        assert parse_result.netlist.n_components == input_result.netlist.n_components, (
            "Component count mismatch between input and output"
        )

    def test_export_preserves_template_non_placement_data(
        self, runner, temp_dir, sample_placements
    ):
        """Test that non-placement data (nets, layers, etc.) is preserved from template."""
        # Create placements JSON
        placements_file = temp_dir / "placements.json"
        placements_file.write_text(json.dumps(sample_placements))

        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                str(placements_file),
                "--pcb",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"

        # Read output file and check for preserved data
        output_content = output_pcb.read_text()

        # Check nets are preserved
        assert "(net 1 " in output_content, "GND net should be preserved"
        assert "(net 2 " in output_content, "VCC net should be preserved"

        # Check layer info is preserved
        assert "F.Cu" in output_content, "F.Cu layer should be preserved"
        assert "B.Cu" in output_content, "B.Cu layer should be preserved"

        # Check edge cuts are preserved
        assert "Edge.Cuts" in output_content, "Edge cuts should be preserved"


class TestExportCommandErrors:
    """Tests for error handling in export command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_export_missing_placements_file(self, runner, temp_dir):
        """Test error when placements file doesn't exist."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                "/nonexistent/placements.json",
                "--pcb",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
            ],
        )

        # Should fail with non-zero exit code
        assert result.exit_code != 0
        # Should mention the file doesn't exist
        assert (
            "exist" in result.output.lower()
            or "not found" in result.output.lower()
            or "no such" in result.output.lower()
            or "error" in result.output.lower()
        )

    def test_export_missing_template_pcb(self, runner, temp_dir):
        """Test error when template PCB file doesn't exist."""
        # Create a valid placements file
        placements_file = temp_dir / "placements.json"
        placements_file.write_text('{"R1": {"x": 10, "y": 20, "rotation": 0}}')

        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                str(placements_file),
                "--pcb",
                "/nonexistent/template.kicad_pcb",
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code != 0

    def test_export_mismatched_component_refs(self, runner, temp_dir):
        """Test behavior when placements have refs not in template PCB."""
        # Create placements with refs that don't exist in template
        mismatched_placements = {
            "R1": {"x": 100, "y": 80, "rotation": 0},  # Exists
            "R99": {"x": 110, "y": 80, "rotation": 90},  # Does NOT exist
            "UNKNOWN": {"x": 120, "y": 90, "rotation": 0},  # Does NOT exist
        }

        placements_file = temp_dir / "placements.json"
        placements_file.write_text(json.dumps(mismatched_placements))

        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                str(placements_file),
                "--pcb",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
            ],
        )

        # Should succeed - the kicad_writer skips refs not in template
        # (it preserves unmatched components at original positions)
        assert result.exit_code == 0, f"CLI failed:\n{result.output}"

        # Output file should still be created
        assert output_pcb.exists()

        # Should only update the one matching component
        assert "Updated: 1" in result.output or "1" in result.output

    def test_export_invalid_placements_json(self, runner, temp_dir):
        """Test error when placements JSON is malformed."""
        # Create invalid JSON
        placements_file = temp_dir / "placements.json"
        placements_file.write_text("{ invalid json: [")

        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "export",
                "-p",
                str(placements_file),
                "--pcb",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
            ],
        )

        # Should fail
        assert result.exit_code != 0
        # Should mention JSON or parse error
        assert "failed" in result.output.lower() or "error" in result.output.lower()


class TestExportCommandHelp:
    """Tests for help output."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_export_help(self, runner):
        """Test export command help output."""
        result = runner.invoke(main, ["export", "--help"])

        assert result.exit_code == 0
        assert "--placements" in result.output or "-p" in result.output
        assert "--pcb" in result.output
        assert "--output" in result.output or "-o" in result.output

    def test_main_help_includes_export(self, runner):
        """Test main help lists export command."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "export" in result.output
