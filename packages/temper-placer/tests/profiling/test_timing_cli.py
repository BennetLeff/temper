"""Tests for timing CLI — baseline, check, and regenerate commands (U2, U4, U5)."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import click
import pytest
from click.testing import CliRunner

from temper_placer.cli.timing import timing


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_measure_all_stages():
    with patch(
        "temper_placer.profiling.timing_gate.measure_all_stages"
    ) as mock:
        from temper_placer.profiling.timing_gate import TimingResult

        mock.return_value = [
            TimingResult(
                board_id="temper_placed",
                pipeline="DeterministicPipeline",
                stage_name="zone_geometry",
                wall_ms=12.5,
                n_runs=3,
                individual_ms=[12.1, 12.5, 12.9],
            ),
            TimingResult(
                board_id="temper_placed",
                pipeline="DeterministicPipeline",
                stage_name="clearance_grid",
                wall_ms=45.2,
                n_runs=3,
                individual_ms=[44.0, 45.2, 46.4],
            ),
        ]
        yield mock


@pytest.fixture
def mock_measure_stage_timing():
    with patch(
        "temper_placer.profiling.timing_gate.measure_stage_timing"
    ) as mock:
        from temper_placer.profiling.timing_gate import TimingResult

        mock.return_value = TimingResult(
            board_id="temper_placed",
            pipeline="DeterministicPipeline",
            stage_name="zone_geometry",
            wall_ms=12.5,
            n_runs=3,
            individual_ms=[12.1, 12.5, 12.9],
        )
        yield mock


@pytest.fixture
def temp_baseline_yaml(tmp_path, monkeypatch):
    """Create a temporary timing_baselines.yaml for testing."""
    import sys

    timing_mod = sys.modules["temper_placer.cli.timing"]

    yaml_path = tmp_path / "power_pcb_dataset" / "timing_baselines.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        timing_mod,
        "_timing_baselines_path",
        lambda: yaml_path,
    )
    monkeypatch.setattr(
        timing_mod,
        "_repo_root",
        lambda: tmp_path,
    )
    return yaml_path


class TestTimingCLIHelp:
    def test_timing_group_help(self, runner):
        result = runner.invoke(timing, ["--help"])
        assert result.exit_code == 0
        assert "baseline" in result.output
        assert "check" in result.output
        assert "regenerate" in result.output

    def test_baseline_help(self, runner):
        result = runner.invoke(timing, ["baseline", "--help"])
        assert result.exit_code == 0
        assert "--board" in result.output

    def test_check_help(self, runner):
        result = runner.invoke(timing, ["check", "--help"])
        assert result.exit_code == 0
        assert "--margin" in result.output

    def test_regenerate_help(self, runner):
        result = runner.invoke(timing, ["regenerate", "--help"])
        assert result.exit_code == 0


class TestTimingBaselineCLI:
    def _setup_golden_manifest(self, tmp_path):
        import yaml

        golden_path = tmp_path / "power_pcb_dataset" / "golden_manifest.yaml"
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(
            yaml.dump(
                {
                    "version": 1,
                    "boards": [
                        {
                            "id": "temper_placed",
                            "path": "pcb/temper_placed.kicad_pcb",
                        }
                    ],
                }
            )
        )
        return golden_path

    def test_baseline_creates_yaml(
        self, runner, mock_measure_all_stages, temp_baseline_yaml, tmp_path
    ):
        import yaml

        self._setup_golden_manifest(tmp_path)

        result = runner.invoke(
            timing, ["baseline", "--board", "temper_placed", "--runs", "2"]
        )

        assert result.exit_code == 0
        assert mock_measure_all_stages.called
        assert temp_baseline_yaml.exists()
        content = yaml.safe_load(temp_baseline_yaml.read_text())
        assert content["format_version"] == 1
        assert len(content["stages"]) == 2

    def test_baseline_skips_existing_without_overwrite(
        self, runner, mock_measure_all_stages, temp_baseline_yaml, tmp_path
    ):
        import yaml

        self._setup_golden_manifest(tmp_path)

        existing = {
            "format_version": 1,
            "stages": [
                {
                    "board": "temper_placed",
                    "pipeline": "DeterministicPipeline",
                    "stage": "zone_geometry",
                    "wall_ms_mean": 10.0,
                    "wall_ms_p95": 12.0,
                    "n_runs": 3,
                    "individual_ms": [9.0, 10.0, 12.0],
                    "git_hash": "abc123",
                    "captured_at": "2026-01-01T00:00:00",
                }
            ],
        }
        temp_baseline_yaml.write_text(yaml.dump(existing))

        result = runner.invoke(
            timing, ["baseline", "--board", "temper_placed", "--runs", "2"]
        )

        assert result.exit_code == 0
        assert "SKIP" in result.output

    def test_baseline_overwrite_replaces(
        self, runner, mock_measure_all_stages, temp_baseline_yaml, tmp_path
    ):
        import yaml

        self._setup_golden_manifest(tmp_path)

        existing = {
            "format_version": 1,
            "stages": [
                {
                    "board": "temper_placed",
                    "pipeline": "DeterministicPipeline",
                    "stage": "zone_geometry",
                    "wall_ms_mean": 10.0,
                    "wall_ms_p95": 12.0,
                    "n_runs": 3,
                    "individual_ms": [9.0, 10.0, 12.0],
                    "git_hash": "abc123",
                    "captured_at": "2026-01-01T00:00:00",
                }
            ],
        }
        temp_baseline_yaml.write_text(yaml.dump(existing))

        result = runner.invoke(
            timing,
            ["baseline", "--board", "temper_placed", "--overwrite", "--runs", "2"],
        )

        assert result.exit_code == 0
        assert "UPDATED" in result.output
        content = yaml.safe_load(temp_baseline_yaml.read_text())
        assert content["stages"][0]["wall_ms_mean"] == 12.5

    def test_baseline_unknown_board_fails(self, runner, temp_baseline_yaml, tmp_path):
        self._setup_golden_manifest(tmp_path)
        result = runner.invoke(timing, ["baseline", "--board", "nonexistent"])
        assert result.exit_code == 1
        assert "ERROR" in result.output


class TestTimingCheckCLI:
    def test_check_empty_manifest(self, runner, temp_baseline_yaml):
        result = runner.invoke(timing, ["check"])
        assert result.exit_code == 0
        assert "No timing baselines" in result.output

    def test_check_json_empty_manifest(self, runner, temp_baseline_yaml):
        import json

        result = runner.invoke(timing, ["check", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["passed"] is True

    def test_check_all_pass(
        self, runner, mock_measure_all_stages, temp_baseline_yaml, tmp_path
    ):
        import yaml

        baseline = {
            "format_version": 1,
            "stages": [
                {
                    "board": "temper_placed",
                    "pipeline": "DeterministicPipeline",
                    "stage": "zone_geometry",
                    "wall_ms_mean": 12.5,
                    "wall_ms_p95": 13.0,
                    "n_runs": 3,
                    "individual_ms": [12.1, 12.5, 12.9],
                    "git_hash": "abc123",
                    "captured_at": "2026-01-01T00:00:00",
                },
            ],
        }
        temp_baseline_yaml.write_text(yaml.dump(baseline))

        result = runner.invoke(
            timing, ["check", "--board", "temper_placed"]
        )
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_check_failure_with_increased_timing(
        self, runner, temp_baseline_yaml, tmp_path
    ):
        import yaml

        baseline = {
            "format_version": 1,
            "stages": [
                {
                    "board": "temper_placed",
                    "pipeline": "DeterministicPipeline",
                    "stage": "zone_geometry",
                    "wall_ms_mean": 1.0,  # Very slow baseline to force fail
                    "wall_ms_p95": 1.5,
                    "n_runs": 3,
                    "individual_ms": [0.9, 1.0, 1.5],
                    "git_hash": "abc123",
                    "captured_at": "2026-01-01T00:00:00",
                },
            ],
        }
        temp_baseline_yaml.write_text(yaml.dump(baseline))

        from temper_placer.profiling.timing_gate import TimingResult

        slow_result = [
            TimingResult(
                board_id="temper_placed",
                pipeline="DeterministicPipeline",
                stage_name="zone_geometry",
                wall_ms=50.0,  # 50x baseline
                n_runs=3,
                individual_ms=[48.0, 50.0, 52.0],
            ),
        ]

        with patch(
            "temper_placer.profiling.timing_gate.measure_all_stages",
            return_value=slow_result,
        ):
            result = runner.invoke(
                timing, ["check", "--board", "temper_placed", "--margin", "0.20"]
            )

        assert result.exit_code == 1
        assert "FAIL" in result.output

    def test_check_json_output(self, runner, mock_measure_all_stages, temp_baseline_yaml):
        import yaml, json

        baseline = {
            "format_version": 1,
            "stages": [
                {
                    "board": "temper_placed",
                    "pipeline": "DeterministicPipeline",
                    "stage": "zone_geometry",
                    "wall_ms_mean": 12.5,
                    "wall_ms_p95": 13.0,
                    "n_runs": 3,
                    "individual_ms": [12.1, 12.5, 12.9],
                    "git_hash": "abc123",
                    "captured_at": "2026-01-01T00:00:00",
                },
            ],
        }
        temp_baseline_yaml.write_text(yaml.dump(baseline))

        result = runner.invoke(
            timing, ["check", "--board", "temper_placed", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["passed"] is True
        assert data["total_stages"] == 1


class TestTimingRegenerateCLI:
    def test_regenerate_prompts_without_force(
        self, runner, mock_measure_stage_timing, temp_baseline_yaml
    ):
        import yaml

        existing = {
            "format_version": 1,
            "stages": [
                {
                    "board": "temper_placed",
                    "pipeline": "DeterministicPipeline",
                    "stage": "zone_geometry",
                    "wall_ms_mean": 10.0,
                    "wall_ms_p95": 12.0,
                    "n_runs": 3,
                    "individual_ms": [9.0, 10.0, 12.0],
                    "git_hash": "abc123",
                    "captured_at": "2026-01-01T00:00:00",
                },
            ],
        }
        temp_baseline_yaml.write_text(yaml.dump(existing))

        result = runner.invoke(
            timing,
            ["regenerate", "--board", "temper_placed", "--stage", "zone_geometry"],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "Aborted" in result.output

    def test_regenerate_with_force(
        self, runner, mock_measure_stage_timing, temp_baseline_yaml
    ):
        result = runner.invoke(
            timing,
            [
                "regenerate",
                "--board",
                "temper_placed",
                "--stage",
                "zone_geometry",
                "--force",
            ],
        )
        assert result.exit_code == 0
        assert "Regenerated" in result.output
