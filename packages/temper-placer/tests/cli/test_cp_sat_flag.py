"""
Tests for the --placer CLI flag and CP-SAT-specific options.

Verifies that:
1. The --placer option is registered on the optimize command
2. CP-SAT tuning flags (--cp-sat-timeout, etc.) are NOT currently exposed
   (removed in a later refactor; see test_cp_sat_tuning_flags_not_currently_exposed)
3. CP-SAT is the default placer (JAX retired, only jax-deprecated remains)
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

    def test_cp_sat_tuning_flags_not_currently_exposed(self, runner: CliRunner) -> None:
        """--cp-sat-timeout/-workers/-grid-scale do not exist on `optimize`.

        VERIFIED 2026-07-18: these three flags were added in 2f3d4601
        ("add CP-SAT feasibility-first placer (U0-U8)") but are absent
        from the current `optimize` command entirely -- confirmed via
        `grep` across cli/__init__.py. `solve_placement()`'s underlying
        signature (placer/cp_sat/encoder.py) still accepts a `timeout_ms`
        parameter, but the CLI's call site
        (`solve_placement(netlist=..., board=..., ...)`) never passes it,
        silently relying on the function's own 1000ms default -- there is
        currently no way for a CLI user to control CP-SAT solve time.
        `--cp-sat-workers` and `--cp-sat-grid-scale` have no underlying
        parameter at all anymore; `solve_placement()`'s signature has no
        `workers` or `grid_scale` argument to wire to. This test
        previously asserted all three flags were present and had been
        silently broken (never actually run in CI) since whichever
        refactor removed them -- see docs/solutions/logic-errors/
        cli-cp-sat-tuning-flags-removed-stale-test.md.
        """
        result = runner.invoke(main, ["optimize", "--help"])
        assert result.exit_code == 0
        for flag in ("--cp-sat-timeout", "--cp-sat-workers", "--cp-sat-grid-scale"):
            assert flag not in result.output, (
                f"{flag} reappeared in `optimize --help` -- if this was "
                "intentionally restored, replace this test with a "
                "positive existence check instead of deleting it silently."
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
        result = runner.invoke(
            main,
            [
                "optimize",
                "--placer",
                "jax-deprecated",
                "nonexistent.kicad_pcb",
            ],
        )
        # Flag is valid; failure is on input file, not on --placer parsing
        assert result.exit_code != 0
        assert "nonexistent" in result.output

    def test_cp_sat_default_placer(self, runner: CliRunner) -> None:
        """Verify CP-SAT runs by default (no --placer flag needed)."""
        result = runner.invoke(
            main,
            [
                "optimize",
                "nonexistent.kicad_pcb",
            ],
        )
        # Should fail on input file existence, not on missing --placer flag
        assert result.exit_code != 0
        assert "nonexistent" in result.output

    def test_placer_rejects_invalid_value(self, runner: CliRunner) -> None:
        """Verify --placer rejects invalid choices."""
        result = runner.invoke(
            main,
            [
                "optimize",
                "--placer",
                "invalid_placer",
                "input.kicad_pcb",
            ],
        )
        assert result.exit_code != 0
        assert "invalid_placer" in result.output or "not one of" in result.output

    # test_cp_sat_timeout_default_value and test_cp_sat_workers_default_value
    # removed 2026-07-18: both asserted default values for flags that no
    # longer exist on `optimize` (see
    # test_cp_sat_tuning_flags_not_currently_exposed above, which already
    # covers their absence across all three flags in one place).
