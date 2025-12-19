"""Tests for ablation study CLI commands."""


import yaml
from click.testing import CliRunner

from temper_placer.cli import main


class TestAblateCommand:
    """Tests for 'ablate' command group."""

    def test_ablate_help(self):
        """Should show help for ablate command group."""
        runner = CliRunner()
        result = runner.invoke(main, ["ablate", "--help"])

        assert result.exit_code == 0
        assert "run" in result.output
        assert "report" in result.output

    def test_ablate_run_help(self):
        """Should show help for ablate run command."""
        runner = CliRunner()
        result = runner.invoke(main, ["ablate", "run", "--help"])

        assert result.exit_code == 0
        assert "CONFIG_FILE" in result.output
        assert "--parallel" in result.output

    def test_ablate_run_missing_config(self):
        """Should fail if config file missing."""
        runner = CliRunner()
        result = runner.invoke(main, ["ablate", "run", "nonexistent.yaml"])

        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_ablate_run_basic(self, tmp_path):
        """Should attempt to run a minimal ablation study."""
        # Create a dummy PCB and config
        pcb_file = tmp_path / "test.kicad_pcb"
        pcb_file.write_text("(kicad_pcb (version 20211014) (generator pcbnew) (general (thickness 1.6)))")

        study_config = {
            "study_name": "test_study",
            "experiments": [
                {
                    "name": "baseline",
                    "description": "Baseline experiment",
                    "components": {},
                    "losses": {},
                    "tags": ["baseline"]
                }
            ],
            "seeds": [42],
            "test_cases": [str(pcb_file)],
            "output_dir": str(tmp_path / "results"),
            "parallel_workers": 1
        }

        config_file = tmp_path / "study.yaml"
        config_file.write_text(yaml.dump(study_config))

        runner = CliRunner()
        # Mocking the actual execution might be hard, but let's see if it gets past loading
        result = runner.invoke(main, ["ablate", "run", str(config_file), "--no-report"])

        # It might fail during execution because test.kicad_pcb is empty/invalid,
        # but it should at least load the config.
        assert "Study: test_study" in result.output
        assert "Experiments: 1" in result.output

    def test_ablate_report_missing_dir(self):
        """Should fail if results directory missing."""
        runner = CliRunner()
        result = runner.invoke(main, ["ablate", "report", "nonexistent_dir"])

        assert result.exit_code != 0
        assert "does not exist" in result.output

    def test_ablate_report_basic(self, tmp_path):
        """Should attempt to generate report from checkpoint."""
        import pickle

        from temper_placer.ablation.runner import ExperimentCheckpoint

        results_dir = tmp_path / "results"
        results_dir.mkdir()

        checkpoint = ExperimentCheckpoint(
            study_name="test",
            completed_runs=[],
            failed_runs=[],
            results=[],
            timestamp=None,
            config_hash="abc"
        )

        with open(results_dir / "checkpoint.pkl", "wb") as f:
            pickle.dump(checkpoint, f)

        runner = CliRunner()
        result = runner.invoke(main, ["ablate", "report", str(results_dir)])

        assert "Generating Ablation Report" in result.output
        # Since results list is empty, it might fail or produce empty report
