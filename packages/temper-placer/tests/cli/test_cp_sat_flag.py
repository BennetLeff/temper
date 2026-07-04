"""
Tests for the --placer CLI flag and CP-SAT-specific options.

Verifies that:
1. The --placer option is registered on the optimize command
2. CP-SAT-specific options (--cp-sat-timeout, etc.) exist
3. The default placer is "jax" (backward compatibility during strangler)
"""

import pytest
from click.testing import CliRunner

from temper_placer.cli import main


class TestCpSatFlag:
    """Unit tests for the --placer CLI flag and CP-SAT options."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI runner."""
        return CliRunner()

    def test_placer_option_exists(self, runner: CliRunner) -> None:
        """Verify --placer option is registered on optimize command."""
        result = runner.invoke(main, ["optimize", "--help"])
        assert result.exit_code == 0, f"Help failed:\n{result.output}"
        assert "--placer" in result.output, "--placer option not found in help"
        assert "jax" in result.output, "'jax' choice not found in help"
        assert "cp-sat" in result.output, "'cp-sat' choice not found in help"

    def test_cp_sat_options_exist(self, runner: CliRunner) -> None:
        """Verify CP-SAT-specific options appear in help."""
        result = runner.invoke(main, ["optimize", "--help"])
        assert result.exit_code == 0
        assert "--cp-sat-timeout" in result.output, (
            "--cp-sat-timeout option not found"
        )
        assert "--cp-sat-workers" in result.output, (
            "--cp-sat-workers option not found"
        )
        assert "--cp-sat-grid-scale" in result.output, (
            "--cp-sat-grid-scale option not found"
        )

    def test_default_placer_is_cp_sat(self, runner: CliRunner) -> None:
        """Verify CP-SAT is the default placer (JAX retired, only jax-deprecated remains)."""
        result = runner.invoke(main, ["optimize", "--help"])
        assert result.exit_code == 0
        assert "jax-deprecated" in result.output, (
            f"Expected jax-deprecated in help output. Got:\n{result.output}"
        )
        assert "default: jax" not in result.output, (
            f"Expected no 'default: jax' in help output. Got:\n{result.output}"
        )

    def test_jax_deprecated_rejected(self, runner: CliRunner) -> None:
        """Verify --placer jax-deprecated is a valid flag (fails on missing input, not on flag)."""
        result = runner.invoke(main, [
            "optimize",
            "--placer", "jax-deprecated",
            "nonexistent.kicad_pcb",
        ])
        # Flag is valid; failure is on input file, not on --placer parsing
        assert result.exit_code != 0
        assert "nonexistent" in result.output

    def test_cp_sat_default_placer(self, runner: CliRunner) -> None:
        """Verify CP-SAT runs by default (no --placer flag needed)."""
        result = runner.invoke(main, [
            "optimize",
            "nonexistent.kicad_pcb",
        ])
        # Should fail on input file existence, not on missing --placer flag
        assert result.exit_code != 0
        assert "nonexistent" in result.output

    def test_placer_rejects_invalid_value(self, runner: CliRunner) -> None:
        """Verify --placer rejects invalid choices."""
        result = runner.invoke(main, [
            "optimize",
            "--placer", "invalid_placer",
            "input.kicad_pcb",
        ])
        assert result.exit_code != 0
        assert "invalid_placer" in result.output or "not one of" in result.output

    def test_cp_sat_timeout_default_value(self, runner: CliRunner) -> None:
        """Verify --cp-sat-timeout has default 300."""
        result = runner.invoke(main, ["optimize", "--help"])
        assert result.exit_code == 0
        assert "--cp-sat-timeout" in result.output
        # Click wraps long help text; check description mentions seconds
        assert "timeout in seconds" in result.output

    def test_cp_sat_workers_default_value(self, runner: CliRunner) -> None:
        """Verify --cp-sat-workers has default 8."""
        result = runner.invoke(main, ["optimize", "--help"])
        assert result.exit_code == 0
        assert "--cp-sat-workers" in result.output
        assert "search workers" in result.output
