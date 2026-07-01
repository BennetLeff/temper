"""Tests for --multi-seed CLI flag (U9)."""

import pytest
from click.testing import CliRunner

jax = pytest.importorskip("jax")

from temper_placer.cli import main  # noqa: E402

from pathlib import Path  # noqa: E402

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"
MINIMAL_CONSTRAINTS = FIXTURES_DIR / "constraints_minimal.yaml"


class TestMultiSeedCLI:
    """Tests for --multi-seed CLI flag."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        return tmp_path

    def test_multi_seed_flag_accepted(self, runner, temp_dir):
        """CLI accepts --multi-seed flag without error."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c", str(MINIMAL_CONSTRAINTS),
                "-o", str(output_pcb),
                "--multi-seed",
                "--epochs", "5",
            ],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output[:500]}"

    def test_without_flag_unchanged(self, runner, temp_dir):
        """Without --multi-seed, original behavior is unchanged."""
        output_pcb = temp_dir / "output_no_multi.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "optimize",
                str(MINIMAL_PCB),
                "-c", str(MINIMAL_CONSTRAINTS),
                "-o", str(output_pcb),
                "--epochs", "5",
            ],
        )
        assert result.exit_code == 0, f"CLI failed: {result.output[:500]}"
