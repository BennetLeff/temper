import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from temper_placer.cli import main

# Test fixtures paths
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"
MINIMAL_CONSTRAINTS = FIXTURES_DIR / "constraints_minimal.yaml"
MINIMAL_PCL = FIXTURES_DIR / "pcl_minimal.yaml"

class TestPipelineCommands:
    """Integration tests for the pipeline CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create a CLI runner."""
        return CliRunner()

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temp directory for outputs."""
        return tmp_path

    def test_pipeline_dry_run(self, runner, temp_dir):
        """Test pipeline command with --dry-run."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "pipeline",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_PCL),
                "-o",
                str(output_pcb),
                "--dry-run"
            ],
        )

        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert "SUCCESS" in result.output

    def test_pipeline_full(self, runner, temp_dir):
        """Test full pipeline execution."""
        output_pcb = temp_dir / "output.kicad_pcb"

        result = runner.invoke(
            main,
            [
                "pipeline",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_PCL),
                "-o",
                str(output_pcb),
                "--epochs",
                "10", # Short epochs for test
                "--seed",
                "42"
            ],
        )
        
        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_pcb.exists(), "Output PCB was not created"
        assert "SUCCESS" in result.output

    def test_phase_semantic(self, runner, temp_dir):
        """Test semantic phase command."""
        output_json = temp_dir / "semantic.json"
        
        result = runner.invoke(
            main,
            [
                "phase",
                "semantic",
                str(MINIMAL_PCB),
                "-o",
                str(output_json)
            ]
        )
        
        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_json.exists()
        
        with open(output_json) as f:
            data = json.load(f)
        assert "success" in data

    def test_phase_topological(self, runner, temp_dir):
        """Test topological phase command."""
        output_json = temp_dir / "topological.json"
        
        result = runner.invoke(
            main,
            [
                "phase",
                "topological",
                str(MINIMAL_PCB),
                "-c",
                str(MINIMAL_PCL),
                "-o",
                str(output_json)
            ]
        )
        
        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_json.exists()

    def test_phase_geometric(self, runner, temp_dir):
        """Test geometric phase command."""
        output_pcb = temp_dir / "geometric.kicad_pcb"
        
        result = runner.invoke(
            main,
            [
                "phase",
                "geometric",
                str(MINIMAL_PCB),
                "-o",
                str(output_pcb),
                "--epochs",
                "10",
                "--seed",
                "42"
            ]
        )
        
        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        assert output_pcb.exists()

    def test_phase_routing(self, runner, temp_dir):
        """Test routing phase command."""
        output_report = temp_dir / "routing_report.txt"
        
        result = runner.invoke(
            main,
            [
                "phase",
                "routing",
                str(MINIMAL_PCB),
                "-o",
                str(output_report)
            ]
        )
        
        assert result.exit_code == 0, f"CLI failed:\n{result.output}"
        if output_report.exists():
             assert output_report.stat().st_size > 0