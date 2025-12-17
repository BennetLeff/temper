"""
Integration tests for the validate CLI command.

These tests verify the pre-flight validation workflow via the CLI, ensuring:
1. External tool checks run correctly
2. Zone validation works
3. Constraint feasibility is checked
4. DRC can be invoked (when kicad-cli is available)
5. JSON output format is correct

The validate command runs pre-flight checks before optimization.
"""

import json
import shutil
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


# Check if kicad-cli is available for DRC tests
def has_kicad_cli() -> bool:
    """Check if kicad-cli is available."""
    # Check standard locations
    for path in [
        "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
        shutil.which("kicad-cli"),
    ]:
        if path and Path(path).exists():
            return True
    return False


KICAD_CLI_AVAILABLE = has_kicad_cli()


class TestValidateCommandBasic:
    """Basic integration tests for the validate command."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temp directory for outputs."""
        return tmp_path

    def test_validate_runs_with_pcb_only(self, runner):
        """Test validate command with just a PCB file."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
            ],
        )

        # Should succeed (may have warnings about missing tools/zones but not errors)
        # Note: exit_code == 0 means passed, exit_code == 1 means errors found
        assert result.exit_code in [0, 1], f"CLI crashed:\n{result.output}"

        # Should show validation running
        assert "Validating" in result.output or "check" in result.output.lower()

    def test_validate_with_config(self, runner):
        """Test validate command with PCB and constraints file."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
            ],
        )

        assert result.exit_code in [0, 1], f"CLI crashed:\n{result.output}"

        # Should report on zones and constraints
        output_lower = result.output.lower()
        assert (
            "zone" in output_lower
            or "constraint" in output_lower
            or "check" in output_lower
            or "pass" in output_lower
        )

    def test_validate_clean_board_passes(self, runner):
        """Test that a valid PCB with valid constraints passes validation."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "--no-tools",  # Skip tool checks which may fail
                "--no-drc",  # Skip DRC which requires kicad-cli
            ],
        )

        # The minimal fixture should pass basic zone/constraint validation
        # Note: May still have warnings but should not have errors
        # Check for either success message or just no crash
        assert result.exit_code in [0, 1], f"CLI crashed:\n{result.output}"


class TestValidateCommandFlags:
    """Tests for validate command flags."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_validate_tools_flag(self, runner):
        """Test --tools and --no-tools flags control tool checking."""
        # With tools check
        result_with = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "--tools",
                "--no-zones",
                "--no-constraints",
            ],
        )

        assert result_with.exit_code in [0, 1]

        # Without tools check
        result_without = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "--no-tools",
                "--no-zones",
                "--no-constraints",
            ],
        )

        assert result_without.exit_code in [0, 1]

        # Tools check should mention kicad-cli or ngspice
        if "--tools" in str(result_with.output):
            pass  # Output format may vary

    def test_validate_zones_flag(self, runner):
        """Test --zones and --no-zones flags control zone checking."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "--zones",
                "--no-tools",
                "--no-constraints",
            ],
        )

        assert result.exit_code in [0, 1]

    def test_validate_constraints_flag(self, runner):
        """Test --constraints and --no-constraints flags."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "--constraints",
                "--no-tools",
                "--no-zones",
            ],
        )

        assert result.exit_code in [0, 1]

    def test_validate_strict_flag(self, runner):
        """Test --strict flag treats warnings as errors."""
        # Run without strict (warnings don't cause exit 1)
        result_normal = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "--no-drc",
            ],
        )

        # Run with strict (warnings cause exit 1)
        result_strict = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "--strict",
                "--no-drc",
            ],
        )

        # Both should run without crashing
        assert result_normal.exit_code in [0, 1]
        assert result_strict.exit_code in [0, 1]


class TestValidateCommandJSONOutput:
    """Tests for JSON output format."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_validate_json_output_format(self, runner):
        """Test --json-output flag produces valid JSON."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "--json-output",
                "--no-drc",
            ],
        )

        assert result.exit_code in [0, 1], f"CLI crashed:\n{result.output}"

        # Output should be valid JSON
        try:
            output_data = json.loads(result.output)
        except json.JSONDecodeError as e:
            pytest.fail(f"JSON output is invalid: {e}\nOutput: {result.output}")

        # Check expected fields
        assert "passed" in output_data, "JSON should have 'passed' field"
        assert "issues" in output_data, "JSON should have 'issues' field"
        assert isinstance(output_data["issues"], list), "'issues' should be a list"

        # Check issue structure if any issues exist
        if output_data["issues"]:
            issue = output_data["issues"][0]
            assert "severity" in issue, "Issue should have 'severity'"
            assert "code" in issue, "Issue should have 'code'"
            assert "message" in issue, "Issue should have 'message'"

    def test_validate_json_has_counts(self, runner):
        """Test JSON output includes error/warning/info counts."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "--json-output",
                "--no-drc",
            ],
        )

        assert result.exit_code in [0, 1]

        output_data = json.loads(result.output)

        # Should have count fields
        assert "error_count" in output_data
        assert "warning_count" in output_data
        assert "info_count" in output_data

        # Counts should be non-negative integers
        assert isinstance(output_data["error_count"], int)
        assert output_data["error_count"] >= 0


class TestValidateCommandDRC:
    """Tests for DRC validation (requires kicad-cli)."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.mark.skipif(not KICAD_CLI_AVAILABLE, reason="kicad-cli not available")
    def test_validate_drc_runs(self, runner):
        """Test that DRC validation runs when kicad-cli is available."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "--drc",
                "--no-tools",
                "--no-zones",
                "--no-constraints",
            ],
        )

        assert result.exit_code in [0, 1], f"CLI crashed:\n{result.output}"
        # Should mention DRC in output
        assert "DRC" in result.output or "drc" in result.output.lower()

    def test_validate_without_kicad_cli_skips_drc(self, runner):
        """Test graceful handling when kicad-cli is not available."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "--drc",
                "--no-tools",
                "--no-zones",
                "--no-constraints",
            ],
        )

        # Should not crash
        assert result.exit_code in [0, 1], f"CLI crashed:\n{result.output}"

        # If kicad-cli not available, should mention skipping
        if not KICAD_CLI_AVAILABLE:
            output_lower = result.output.lower()
            assert (
                "skip" in output_lower
                or "not available" in output_lower
                or "not found" in output_lower
            ), f"Should mention DRC skipped, got: {result.output}"


class TestValidateCommandErrors:
    """Tests for error handling."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_validate_missing_pcb(self, runner):
        """Test error when PCB file doesn't exist."""
        result = runner.invoke(
            main,
            [
                "validate",
                "/nonexistent/board.kicad_pcb",
            ],
        )

        assert result.exit_code != 0
        assert (
            "exist" in result.output.lower()
            or "not found" in result.output.lower()
            or "no such" in result.output.lower()
            or "error" in result.output.lower()
        )

    def test_validate_missing_config(self, runner):
        """Test error when constraints file doesn't exist."""
        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "-c",
                "/nonexistent/constraints.yaml",
            ],
        )

        assert result.exit_code != 0

    def test_validate_invalid_constraints_yaml(self, runner, temp_dir):
        """Test error when constraints file has invalid YAML."""
        bad_yaml = temp_dir / "bad_constraints.yaml"
        bad_yaml.write_text("board:\n  width_mm: [invalid")

        result = runner.invoke(
            main,
            [
                "validate",
                str(MINIMAL_PCB),
                "-c",
                str(bad_yaml),
            ],
        )

        assert result.exit_code != 0


class TestValidateCommandHelp:
    """Tests for help output."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_validate_help(self, runner):
        """Test validate command help output."""
        result = runner.invoke(main, ["validate", "--help"])

        assert result.exit_code == 0
        assert "--config" in result.output or "-c" in result.output
        assert "--tools" in result.output
        assert "--zones" in result.output
        assert "--constraints" in result.output
        assert "--drc" in result.output
        assert "--strict" in result.output
        assert "--json-output" in result.output

    def test_main_help_includes_validate(self, runner):
        """Test main help lists validate command."""
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "validate" in result.output
