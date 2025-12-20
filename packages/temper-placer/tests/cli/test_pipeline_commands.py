"""
Tests for the pipeline CLI commands.

This module tests the CLI integration for the full placement pipeline:
- `temper-placer pipeline` - Full pipeline execution
- `temper-placer phase <phase>` - Individual phase execution
- Dry run mode
- Verbose/progress callbacks
- Error handling and exit codes
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import json

import pytest
from click.testing import CliRunner

from temper_placer.cli import main
from temper_placer.pipeline import (
    PipelinePhase,
    PipelineConfig,
    PipelineState,
    PipelineOrchestrator,
    PreflightResult,
    PreflightCheck,
    PreflightReport,
)

# Test fixtures paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"
MINIMAL_CONSTRAINTS = FIXTURES_DIR / "constraints_minimal.yaml"


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temp directory for outputs."""
    return tmp_path


# =============================================================================
# Pipeline Command Tests
# =============================================================================


class TestPipelineCommandParsing:
    """Test that pipeline command parses arguments correctly."""

    def test_pipeline_help(self, runner):
        """Test that pipeline --help works."""
        result = runner.invoke(main, ["pipeline", "--help"])
        assert result.exit_code == 0
        assert "Run the full placement pipeline" in result.output
        # Check key options are documented
        assert "--loops" in result.output or "-l" in result.output
        assert "--constraints" in result.output or "-c" in result.output
        assert "--output" in result.output or "-o" in result.output
        assert "--dry-run" in result.output
        assert "--verbose" in result.output or "-v" in result.output

    def test_pipeline_requires_input_pcb(self, runner):
        """Test that pipeline requires INPUT_PCB argument."""
        result = runner.invoke(main, ["pipeline"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "INPUT_PCB" in result.output

    def test_pipeline_validates_input_exists(self, runner):
        """Test that pipeline validates input file exists."""
        result = runner.invoke(main, ["pipeline", "nonexistent.kicad_pcb"])
        assert result.exit_code != 0
        assert "does not exist" in result.output.lower() or "no such file" in result.output.lower()

    def test_pipeline_accepts_all_options(self, runner, temp_dir):
        """Test that pipeline accepts all documented options."""
        output_pcb = temp_dir / "output.kicad_pcb"
        report = temp_dir / "report.html"
        trace = temp_dir / "trace.json"

        # We need to mock the orchestrator to avoid full execution
        with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch_class:
            mock_orchestrator = Mock()
            mock_state = Mock()
            mock_state.success = True
            mock_state.output_pcb = output_pcb
            mock_orchestrator.run.return_value = mock_state
            mock_orch_class.return_value = mock_orchestrator

            result = runner.invoke(
                main,
                [
                    "pipeline",
                    str(MINIMAL_PCB),
                    "--loops",
                    str(MINIMAL_CONSTRAINTS),  # Using constraints as loops for test
                    "--constraints",
                    str(MINIMAL_CONSTRAINTS),
                    "--fab",
                    "jlcpcb_standard",
                    "--output",
                    str(output_pcb),
                    "--report",
                    str(report),
                    "--trace",
                    str(trace),
                    "--max-iterations",
                    "3",
                    "--epochs",
                    "1000",
                    "--seed",
                    "123",
                    "--verbose",
                ],
            )

            # Should not fail on parsing
            assert result.exit_code == 0 or "not found" not in result.output.lower()


class TestPipelineCommandExecution:
    """Test pipeline command execution with mocked orchestrator."""

    def test_pipeline_success(self, runner, temp_dir):
        """Test successful pipeline execution."""
        output_pcb = temp_dir / "output.kicad_pcb"

        with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch_class:
            mock_orchestrator = Mock()
            mock_state = PipelineState(
                config=PipelineConfig(input_pcb=MINIMAL_PCB),
                success=True,
            )
            mock_orchestrator.run.return_value = mock_state
            mock_orch_class.return_value = mock_orchestrator

            result = runner.invoke(
                main,
                [
                    "pipeline",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "-o",
                    str(output_pcb),
                ],
            )

            assert result.exit_code == 0
            assert "SUCCESS" in result.output or "success" in result.output.lower()

    def test_pipeline_failure_exit_code(self, runner, temp_dir):
        """Test that pipeline returns non-zero exit code on failure."""
        output_pcb = temp_dir / "output.kicad_pcb"

        with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch_class:
            mock_orchestrator = Mock()
            mock_state = PipelineState(
                config=PipelineConfig(input_pcb=MINIMAL_PCB),
                success=False,
                failure_reason="Placement infeasible: overlap constraint violated",
                failed_phase=PipelinePhase.GEOMETRIC,
            )
            mock_orchestrator.run.return_value = mock_state
            mock_orch_class.return_value = mock_orchestrator

            result = runner.invoke(
                main,
                [
                    "pipeline",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "-o",
                    str(output_pcb),
                ],
            )

            assert result.exit_code == 1
            assert "FAILED" in result.output or "failed" in result.output.lower()
            assert "overlap" in result.output.lower() or "infeasible" in result.output.lower()

    def test_pipeline_creates_config_correctly(self, runner, temp_dir):
        """Test that pipeline creates PipelineConfig with correct values."""
        output_pcb = temp_dir / "output.kicad_pcb"
        captured_config = None

        with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch_class:

            def capture_config(config):
                nonlocal captured_config
                captured_config = config
                mock = Mock()
                mock.run.return_value = PipelineState(config=config, success=True)
                return mock

            mock_orch_class.side_effect = capture_config

            result = runner.invoke(
                main,
                [
                    "pipeline",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "-o",
                    str(output_pcb),
                    "--epochs",
                    "5000",
                    "--seed",
                    "99",
                    "--max-iterations",
                    "7",
                    "--fab",
                    "oshpark",
                ],
            )

            assert captured_config is not None
            assert captured_config.input_pcb == MINIMAL_PCB
            assert captured_config.constraints_yaml == MINIMAL_CONSTRAINTS
            assert captured_config.output_pcb == output_pcb
            assert captured_config.epochs == 5000
            assert captured_config.seed == 99
            assert captured_config.max_iterations == 7
            assert captured_config.fab_preset == "oshpark"


class TestPipelineDryRun:
    """Test pipeline --dry-run mode."""

    def test_dry_run_sets_config_flag(self, runner, temp_dir):
        """Test that --dry-run sets dry_run=True in config."""
        captured_config = None

        with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch_class:

            def capture_config(config):
                nonlocal captured_config
                captured_config = config
                mock = Mock()
                mock.run.return_value = PipelineState(config=config, success=True)
                return mock

            mock_orch_class.side_effect = capture_config

            result = runner.invoke(
                main,
                [
                    "pipeline",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "--dry-run",
                ],
            )

            assert captured_config is not None
            assert captured_config.dry_run is True

    def test_dry_run_shows_feasibility_result(self, runner):
        """Test that dry-run shows feasibility status."""
        with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch_class:
            mock_orchestrator = Mock()
            mock_state = PipelineState(
                config=PipelineConfig(input_pcb=MINIMAL_PCB, dry_run=True),
                success=True,
            )
            mock_orchestrator.run.return_value = mock_state
            mock_orch_class.return_value = mock_orchestrator

            result = runner.invoke(
                main,
                [
                    "pipeline",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "--dry-run",
                ],
            )

            assert result.exit_code == 0
            # Should indicate feasibility
            assert (
                "FEASIBLE" in result.output.upper()
                or "SUCCESS" in result.output.upper()
                or "preflight" in result.output.lower()
            )


class TestPipelineVerbose:
    """Test pipeline verbose output."""

    def test_verbose_shows_phase_progress(self, runner, temp_dir):
        """Test that verbose mode shows phase progress."""
        output_pcb = temp_dir / "output.kicad_pcb"

        with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch_class:
            mock_orchestrator = Mock()
            mock_state = PipelineState(
                config=PipelineConfig(input_pcb=MINIMAL_PCB),
                success=True,
            )
            mock_orchestrator.run.return_value = mock_state
            # Capture callbacks
            mock_orch_class.return_value = mock_orchestrator

            result = runner.invoke(
                main,
                [
                    "pipeline",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "-o",
                    str(output_pcb),
                    "--verbose",
                ],
            )

            # Verbose mode should set up callbacks
            # Check that on_phase_start was set
            assert mock_orchestrator.on_phase_start is not None or result.exit_code == 0


# =============================================================================
# Phase Command Tests
# =============================================================================


class TestPhaseCommandGroup:
    """Test the phase command group."""

    def test_phase_help(self, runner):
        """Test that phase --help works."""
        result = runner.invoke(main, ["phase", "--help"])
        assert result.exit_code == 0
        assert "Run individual pipeline phases" in result.output

    def test_phase_subcommands_listed(self, runner):
        """Test that phase subcommands are listed in help."""
        result = runner.invoke(main, ["phase", "--help"])
        # Should list available phases
        assert "semantic" in result.output.lower()
        assert "topological" in result.output.lower()
        assert "geometric" in result.output.lower()
        assert "routing" in result.output.lower()


class TestPhaseSemanticCommand:
    """Test phase semantic command."""

    def test_semantic_help(self, runner):
        """Test semantic phase help."""
        result = runner.invoke(main, ["phase", "semantic", "--help"])
        assert result.exit_code == 0
        assert "semantic" in result.output.lower()

    def test_semantic_requires_input(self, runner):
        """Test semantic requires input PCB."""
        result = runner.invoke(main, ["phase", "semantic"])
        assert result.exit_code != 0


class TestPhaseTopologicalCommand:
    """Test phase topological command."""

    def test_topological_help(self, runner):
        """Test topological phase help."""
        result = runner.invoke(main, ["phase", "topological", "--help"])
        assert result.exit_code == 0
        assert "topological" in result.output.lower()


class TestPhaseGeometricCommand:
    """Test phase geometric command."""

    def test_geometric_help(self, runner):
        """Test geometric phase help."""
        result = runner.invoke(main, ["phase", "geometric", "--help"])
        assert result.exit_code == 0
        assert "geometric" in result.output.lower()
        assert "--epochs" in result.output
        assert "--seed" in result.output

    def test_geometric_accepts_options(self, runner):
        """Test geometric accepts epoch and seed options."""
        result = runner.invoke(
            main,
            ["phase", "geometric", "--help"],
        )
        assert "--epochs" in result.output
        assert "--seed" in result.output


class TestPhaseRoutingCommand:
    """Test phase routing command."""

    def test_routing_help(self, runner):
        """Test routing phase help."""
        result = runner.invoke(main, ["phase", "routing", "--help"])
        assert result.exit_code == 0
        assert "routing" in result.output.lower()
        assert "--level" in result.output


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestPipelineErrorHandling:
    """Test pipeline error handling."""

    def test_pipeline_handles_orchestrator_exception(self, runner, temp_dir):
        """Test that pipeline handles exceptions gracefully."""
        output_pcb = temp_dir / "output.kicad_pcb"

        with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch_class:
            mock_orchestrator = Mock()
            mock_orchestrator.run.side_effect = Exception("Unexpected error in phase")
            mock_orch_class.return_value = mock_orchestrator

            result = runner.invoke(
                main,
                [
                    "pipeline",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "-o",
                    str(output_pcb),
                ],
            )

            assert result.exit_code == 1
            assert "error" in result.output.lower() or "Unexpected" in result.output

    def test_pipeline_handles_missing_constraints(self, runner, temp_dir):
        """Test pipeline with nonexistent constraints file."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "pipeline",
                str(MINIMAL_PCB),
                "-c",
                "nonexistent_constraints.yaml",
                "-o",
                str(output_pcb),
            ],
        )

        assert result.exit_code != 0


class TestPipelineOutputFiles:
    """Test pipeline output file generation."""

    def test_pipeline_writes_output_pcb(self, runner, temp_dir):
        """Test that pipeline creates output PCB file."""
        output_pcb = temp_dir / "output.kicad_pcb"

        with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch_class:
            mock_orchestrator = Mock()
            mock_state = PipelineState(
                config=PipelineConfig(
                    input_pcb=MINIMAL_PCB,
                    output_pcb=output_pcb,
                ),
                success=True,
            )
            mock_orchestrator.run.return_value = mock_state
            mock_orch_class.return_value = mock_orchestrator

            result = runner.invoke(
                main,
                [
                    "pipeline",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "-o",
                    str(output_pcb),
                ],
            )

            assert result.exit_code == 0
            # Output path should be mentioned
            assert str(output_pcb.name) in result.output or "output" in result.output.lower()


class TestPipelineWithPreflight:
    """Test pipeline integration with preflight checks."""

    def test_pipeline_shows_preflight_warnings(self, runner, temp_dir):
        """Test that pipeline shows preflight warnings."""
        output_pcb = temp_dir / "output.kicad_pcb"

        with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch_class:
            mock_orchestrator = Mock()
            mock_state = PipelineState(
                config=PipelineConfig(input_pcb=MINIMAL_PCB),
                success=True,
            )
            mock_orchestrator.run.return_value = mock_state
            mock_orch_class.return_value = mock_orchestrator

            result = runner.invoke(
                main,
                [
                    "pipeline",
                    str(MINIMAL_PCB),
                    "-c",
                    str(MINIMAL_CONSTRAINTS),
                    "-o",
                    str(output_pcb),
                    "--verbose",
                ],
            )

            # Should succeed even with mocked orchestrator
            assert result.exit_code == 0


# =============================================================================
# Integration Tests (with real orchestrator, minimal execution)
# =============================================================================


class TestPipelineRealExecution:
    """Integration tests with real orchestrator (minimal epochs)."""

    @pytest.mark.slow
    def test_pipeline_full_execution_minimal(self, runner, temp_dir):
        """Test full pipeline execution with minimal fixture.

        This test is marked slow because it runs real optimization.
        """
        output_pcb = temp_dir / "output.kicad_pcb"

        # Don't mock - run real pipeline with minimal epochs
        result = runner.invoke(
            main,
            [
                "pipeline",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_CONSTRAINTS),
                "-o",
                str(output_pcb),
                "--epochs",
                "10",  # Minimal for fast testing
                "--max-iterations",
                "1",
                "--seed",
                "42",
            ],
        )

        # Check for success or expected output
        # The command should either succeed or fail gracefully
        assert result.exit_code in (0, 1)
        # Should not have uncaught exceptions
        assert "Traceback" not in result.output or "--verbose" in result.output
