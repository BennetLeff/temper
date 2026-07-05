"""Integration tests for the --placer CLI flag (U8).

Verifies:
1. --placer jax-deprecated prints deprecation warning to stderr, exits 0
2. --placer jax-deprecated output is byte-different from --placer cp-sat (A/B divergence)
3. --placer cp-sat (default) proceeds with CP-SAT path
4. Flag is visible in --help output
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

from temper_placer.cli import main

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"
MINIMAL_CONSTRAINTS = FIXTURES_DIR / "constraints_minimal.yaml"


@pytest.fixture
def runner():
    return CliRunner()


class TestPlacerFlag:
    """Tests for the --placer CLI flag."""

    def test_jax_deprecated_prints_warning_to_stderr(self, runner, tmp_path):
        """--placer jax-deprecated prints deprecation warning and exits 0."""
        output = tmp_path / "out.kicad_pcb"
        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output),
                "--placer",
                "jax-deprecated",
            ],
        )
        assert result.exit_code == 0
        assert "JAX placer has been removed" in result.stderr
        assert "CP-SAT is the sole placer" in result.stderr

    def test_jax_deprecated_output_differs_from_cp_sat(self, runner, tmp_path):
        """A/B divergence: --placer jax-deprecated output differs from cp-sat."""
        output_jax = tmp_path / "out_jax.kicad_pcb"
        result_jax = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_jax),
                "--placer",
                "jax-deprecated",
            ],
        )
        output_cpsat = tmp_path / "out_cpsat.kicad_pcb"
        result_cpsat = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_cpsat),
                "--placer",
                "cp-sat",
            ],
        )
        assert result_jax.exit_code == 0
        assert result_cpsat.exit_code == 0
        assert result_jax.stderr != result_cpsat.stderr
        assert result_jax.stdout != result_cpsat.stdout

    def test_cp_sat_is_default(self, runner, tmp_path):
        """Default (no --placer) uses cp-sat path."""
        output = tmp_path / "out.kicad_pcb"
        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output),
            ],
        )
        assert result.exit_code == 0
        assert "CP-SAT placer selected" in result.stdout

    def test_placer_flag_visible_in_help(self, runner):
        """--placer flag appears in optimize --help."""
        result = runner.invoke(main, ["optimize", "--help"])
        assert result.exit_code == 0
        assert "--placer" in result.stdout
        assert "cp-sat" in result.stdout
        assert "jax-deprecated" in result.stdout
