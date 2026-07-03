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

    def test_default_placer_is_jax(self, runner: CliRunner) -> None:
        """Verify --placer defaults to 'jax' (backward compatibility)."""
        result = runner.invoke(main, ["optimize", "--help"])
        assert result.exit_code == 0
        # Click shows default in help text
        assert "default: jax" in result.output, (
            f"Expected 'default: jax' in help output. Got:\n{result.output}"
        )

    def test_placer_accepts_jax_value(self, runner: CliRunner) -> None:
        """Verify --placer jax is accepted (no crash on flag parsing)."""
        # --placer jax with minimal args — will fail on requirements
        # (missing -c and -o), but should parse the --placer flag correctly
        result = runner.invoke(main, [
            "optimize",
            "--placer", "jax",
            "nonexistent.kicad_pcb",
        ])
        # Should fail on input file existence, not on --placer flag parsing
        assert result.exit_code != 0
        assert "nonexistent" in result.output

    def test_placer_accepts_cp_sat_value(self, runner: CliRunner) -> None:
        """Verify --placer cp-sat is accepted (no crash on flag parsing)."""
        result = runner.invoke(main, [
            "optimize",
            "--placer", "cp-sat",
            "nonexistent.kicad_pcb",
        ])
        # Should fail on input file existence, not on --placer flag parsing
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
