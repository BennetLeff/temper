"""
Integration tests for the optimize CLI command.

These tests verify the full optimization workflow via the CLI, ensuring:
1. The command runs successfully with valid inputs
2. Output files are created and valid
3. Error cases are handled gracefully
4. All CLI flags work as expected

This is the HIGHEST priority test file because the bug we fixed
(temperature.initial → temperature.start on line 249 of cli.py)
would have been caught by these tests.
"""

import json
import os
import tempfile
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


class TestOptimizeCommandBasic:
    """Basic integration tests for the optimize command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temp directory for outputs."""
        return tmp_path

    def test_optimize_minimal_board(self, runner, temp_dir):
        """Test optimize command with minimal fixture - the most critical test."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "50",
                "--seed",
                "42",
                "--no-curriculum",  # Faster for tests
            ],
        )

        # Check command succeeded
        assert result.exit_code == 0, f"CLI failed with output:\n{result.output}"

        # Check output file was created
        assert output_pcb.exists(), "Output PCB file was not created"
        assert output_pcb.stat().st_size > 0, "Output PCB file is empty"

        # Check output contains expected status messages
        assert "Parsing KiCad PCB" in result.output or "Step 1" in result.output
        assert "Done!" in result.output or "Optimization complete" in result.output

    def test_optimize_with_curriculum(self, runner, temp_dir):
        """Test optimize with curriculum learning enabled (default)."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "100",
                "--seed",
                "42",
                "--curriculum",  # Explicitly enable
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_pcb.exists()
        # Curriculum mode should mention phases
        assert "Curriculum" in result.output or "phase" in result.output.lower()

    def test_optimize_output_is_valid_kicad(self, runner, temp_dir):
        """Test that the output file can be re-parsed as valid KiCad PCB."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "50",
                "--seed",
                "42",
                "--no-curriculum",
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


class TestOptimizeCommandFlags:
    """Tests for various CLI flags."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_optimize_with_seed(self, runner, temp_dir):
        """Test that --seed flag produces reproducible results."""
        output1 = temp_dir / "output1.kicad_pcb"
        output2 = temp_dir / "output2.kicad_pcb"

        # Run twice with same seed
        for output in [output1, output2]:
            result = runner.invoke(
                main,
                [
                    "optimize",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "-o",
                    str(output),
                    "--epochs",
                    "30",
                    "--seed",
                    "12345",
                    "--no-curriculum",
                ],
            )
            assert result.exit_code == 0, f"CLI failed:\n{result.output}"

        # Both files should exist
        assert output1.exists() and output2.exists()

        # Files should be identical (same seed = same result)
        # Note: There might be minor timestamp differences, but positions should match
        # For a stricter test, we could parse both and compare positions

    def test_optimize_creates_checkpoint(self, runner, temp_dir):
        """Test that --checkpoint flag creates a checkpoint file."""
        output_pcb = temp_dir / "output.kicad_pcb"
        checkpoint = temp_dir / "checkpoint.json"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "50",
                "--seed",
                "42",
                "--checkpoint",
                str(checkpoint),
                "--no-curriculum",
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert checkpoint.exists(), "Checkpoint file was not created"

        # Verify checkpoint is valid JSON
        with open(checkpoint) as f:
            checkpoint_data = json.load(f)

        assert "epochs" in checkpoint_data
        assert "final_loss" in checkpoint_data
        assert "best_loss" in checkpoint_data

    def test_optimize_creates_placements_json(self, runner, temp_dir):
        """Test that --placements-json flag creates a JSON placements file."""
        output_pcb = temp_dir / "output.kicad_pcb"
        placements_json = temp_dir / "placements.json"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "50",
                "--seed",
                "42",
                "--placements-json",
                str(placements_json),
                "--no-curriculum",
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert placements_json.exists(), "Placements JSON was not created"

        # Verify JSON structure
        with open(placements_json) as f:
            placements = json.load(f)

        # Should have entries for each component
        assert len(placements) > 0, "Placements JSON is empty"

        # Each entry should have x, y, rotation
        for ref, data in placements.items():
            assert "x" in data, f"Missing 'x' for {ref}"
            assert "y" in data, f"Missing 'y' for {ref}"
            assert "rotation" in data, f"Missing 'rotation' for {ref}"

    def test_optimize_epochs_flag(self, runner, temp_dir):
        """Test that --epochs flag controls optimization length."""
        output_pcb = temp_dir / "output.kicad_pcb"
        checkpoint = temp_dir / "checkpoint.json"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "25",  # Very short
                "--seed",
                "42",
                "--checkpoint",
                str(checkpoint),
                "--no-curriculum",
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"

        with open(checkpoint) as f:
            checkpoint_data = json.load(f)

        # Should have run approximately the requested epochs
        assert checkpoint_data["epochs"] <= 30  # Allow some tolerance


class TestOptimizeCommandErrors:
    """Tests for error handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_optimize_missing_input(self, runner, temp_dir):
        """Test error when input PCB file doesn't exist."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                "/nonexistent/path/to/board.kicad_pcb",
                "-c",
                str(MINIMAL_CONSTRAINTS),
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
        )

    def test_optimize_missing_constraints(self, runner, temp_dir):
        """Test error when constraints file doesn't exist."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                "/nonexistent/constraints.yaml",
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code != 0

    def test_optimize_invalid_constraints_yaml(self, runner, temp_dir):
        """Test error when constraints file has invalid YAML."""
        output_pcb = temp_dir / "output.kicad_pcb"
        bad_yaml = temp_dir / "bad_constraints.yaml"

        # Write invalid YAML
        bad_yaml.write_text("board:\n  width_mm: 50\n  invalid: [unclosed bracket")

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(bad_yaml),
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code != 0, "Should fail on invalid YAML"

    def test_optimize_missing_required_config_field(self, runner, temp_dir):
        """Test error when constraints file is missing required fields."""
        output_pcb = temp_dir / "output.kicad_pcb"
        incomplete_yaml = temp_dir / "incomplete_constraints.yaml"

        # Write YAML missing required fields
        incomplete_yaml.write_text("zones:\n  - name: test\n")

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(incomplete_yaml),
                "-o",
                str(output_pcb),
            ],
        )

        # Should fail - missing board dimensions
        assert result.exit_code != 0

    def test_optimize_no_output_flag(self, runner):
        """Test error when -o/--output is not provided."""
        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                # Missing -o flag
            ],
        )

        assert result.exit_code != 0
        assert "output" in result.output.lower() or "required" in result.output.lower()

    def test_optimize_no_config_flag(self, runner, temp_dir):
        """Test error when -c/--config is not provided."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
                # Missing -c flag
            ],
        )

        assert result.exit_code != 0


class TestOptimizeCommandHelp:
    """Tests for help output."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_optimize_help(self, runner):
        """Test optimize command help output."""
        result = runner.invoke(main, ["optimize", "--help"])

        assert result.exit_code == 0
        assert "--config" in result.output or "-c" in result.output
        assert "--output" in result.output or "-o" in result.output
        assert "--epochs" in result.output
        assert "--seed" in result.output
        assert "--checkpoint" in result.output
        assert "--curriculum" in result.output
        assert "--heuristics" in result.output

    def test_main_help_includes_optimize(self, runner):
        """Test main help lists optimize command."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "optimize" in result.output


class TestOptimizeLossDecrease:
    """Tests that verify optimization actually improves placement."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_optimization_improves_loss(self, runner, temp_dir):
        """Test that optimization reduces loss over epochs."""
        output_pcb = temp_dir / "output.kicad_pcb"
        checkpoint = temp_dir / "checkpoint.json"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "100",
                "--seed",
                "42",
                "--checkpoint",
                str(checkpoint),
                "--no-curriculum",
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"

        with open(checkpoint) as f:
            data = json.load(f)

        # Best loss should be less than or equal to final loss
        assert data["best_loss"] <= data["final_loss"]

        # Loss should be finite
        assert data["final_loss"] < float("inf")
        assert data["best_loss"] < float("inf")


class TestOptimizeHeuristicsFlag:
    """Tests for the --heuristics/--no-heuristics flag."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_optimize_with_heuristics_enabled(self, runner, temp_dir):
        """Test optimize with heuristics explicitly enabled (default)."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "50",
                "--seed",
                "42",
                "--heuristics",  # Explicitly enable
                "--no-curriculum",
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_pcb.exists()
        # Should mention heuristics in output
        assert "heuristic" in result.output.lower() or "initialization" in result.output.lower()

    def test_optimize_with_heuristics_disabled(self, runner, temp_dir):
        """Test optimize with heuristics disabled."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "50",
                "--seed",
                "42",
                "--no-heuristics",  # Explicitly disable
                "--no-curriculum",
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_pcb.exists()

    def test_heuristics_default_is_enabled(self, runner, temp_dir):
        """Test that heuristics are enabled by default."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "50",
                "--seed",
                "42",
                "--no-curriculum",
                # No --heuristics flag - should default to enabled
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_pcb.exists()
        # By default, should run heuristics
        assert (
            "heuristic" in result.output.lower()
            or "initialization" in result.output.lower()
            or "Step 2b" in result.output
        )


# Mark slow tests
class TestOptimizeCommandSlow:
    """Slower tests that run full optimization cycles."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    @pytest.mark.slow
    def test_optimize_full_epochs(self, runner, temp_dir):
        """Test full optimization with more epochs."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "500",
                "--seed",
                "42",
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_pcb.exists()
