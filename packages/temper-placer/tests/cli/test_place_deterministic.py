import pytest
from click.testing import CliRunner
from temper_placer.cli import main
from pathlib import Path
from unittest.mock import MagicMock, patch

def test_place_deterministic_cli_args():
    runner = CliRunner()
    
    # Test argument parsing without running actual pipeline
    with patch("temper_placer.cli.PipelineOrchestrator") as mock_orch, \
         patch("temper_placer.io.config_loader.load_constraints"), \
         patch("temper_placer.io.kicad_parser.parse_kicad_pcb"):
        
        # Create dummy files
        with runner.isolated_filesystem():
            Path("input.kicad_pcb").touch()
            Path("config.yaml").touch()
            
            result = runner.invoke(main, [
                "place-deterministic", 
                "input.kicad_pcb", 
                "-c", "config.yaml",
                "-o", "output.kicad_pcb",
                "--max-iterations", "3",
                "--max-movement", "2.5"
            ])
            
            # Should have initialized orchestrator with correct config
            args, kwargs = mock_orch.call_args
            config = args[0]
            assert config.max_iterations == 3
            assert config.max_movement_mm == 2.5
            assert str(config.output_pcb) == "output.kicad_pcb"

def test_place_deterministic_help():
    runner = CliRunner()
    result = runner.invoke(main, ["place-deterministic", "--help"])
    assert result.exit_code == 0
    assert "hierarchical deterministic pipeline" in result.output
    assert "--routability-threshold" in result.output
    assert "--max-movement" in result.output
