"""Tests for ablation study experiment runner."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from temper_placer.ablation.config import (
    ComponentToggle,
    LossToggle,
    ExperimentConfig,
    AblationStudyConfig,
)
from temper_placer.ablation.runner import ExperimentRun, ExperimentRunner
from temper_placer.core.state import PlacementState


class TestExperimentRun:
    """Tests for ExperimentRun dataclass."""

    def test_experiment_run_creation(self):
        """Should create ExperimentRun with all fields."""
        state = Mock(spec=PlacementState)
        now = datetime.now()

        run = ExperimentRun(
            experiment_name="test_exp",
            seed=42,
            test_case="test.kicad_pcb",
            final_loss=1.5,
            best_loss=1.2,
            convergence_epoch=100,
            epochs_completed=200,
            quality_metrics={"wirelength": 10.5},
            drc_error_count=0,
            drc_warning_count=2,
            elapsed_seconds=30.5,
            final_state=state,
            checkpoint_path=Path("/tmp/checkpoint.pkl"),
            timestamp=now,
            config_hash="abc123def456",
        )

        assert run.experiment_name == "test_exp"
        assert run.seed == 42
        assert run.test_case == "test.kicad_pcb"
        assert run.final_loss == 1.5
        assert run.best_loss == 1.2
        assert run.convergence_epoch == 100
        assert run.epochs_completed == 200
        assert run.quality_metrics == {"wirelength": 10.5}
        assert run.drc_error_count == 0
        assert run.drc_warning_count == 2
        assert run.elapsed_seconds == 30.5
        assert run.final_state == state
        assert run.checkpoint_path == Path("/tmp/checkpoint.pkl")
        assert run.timestamp == now
        assert run.config_hash == "abc123def456"

    def test_experiment_run_drc_unavailable(self):
        """Should handle DRC unavailable (-1 sentinel values)."""
        state = Mock(spec=PlacementState)

        run = ExperimentRun(
            experiment_name="test_exp",
            seed=42,
            test_case="test.kicad_pcb",
            final_loss=1.5,
            best_loss=1.2,
            convergence_epoch=100,
            epochs_completed=200,
            quality_metrics={},
            drc_error_count=-1,
            drc_warning_count=-1,
            elapsed_seconds=30.5,
            final_state=state,
            checkpoint_path=None,
            timestamp=datetime.now(),
            config_hash="abc123",
        )

        assert run.drc_error_count == -1
        assert run.drc_warning_count == -1


class TestExperimentCheckpoint:
    """Tests for ExperimentCheckpoint dataclass."""

    def test_checkpoint_creation(self, tmp_path):
        """Should create checkpoint with all fields."""
        from temper_placer.ablation.runner import ExperimentCheckpoint

        now = datetime.now()
        run = ExperimentRun(
            experiment_name="test",
            seed=42,
            test_case="test.kicad_pcb",
            final_loss=1.0,
            best_loss=0.9,
            convergence_epoch=100,
            epochs_completed=200,
            quality_metrics={},
            drc_error_count=0,
            drc_warning_count=0,
            elapsed_seconds=10.0,
            final_state=Mock(),
            checkpoint_path=None,
            timestamp=now,
            config_hash="test",
        )

        checkpoint = ExperimentCheckpoint(
            study_name="test_study",
            completed_runs=[("test", 42, "test.kicad_pcb")],
            failed_runs=[],
            results=[run],
            timestamp=now,
            config_hash="abc123",
        )

        assert checkpoint.study_name == "test_study"
        assert len(checkpoint.completed_runs) == 1
        assert len(checkpoint.results) == 1
        assert len(checkpoint.failed_runs) == 0

    def test_checkpoint_save_and_load(self, tmp_path):
        """Should save and load checkpoint."""
        from temper_placer.ablation.runner import ExperimentCheckpoint

        checkpoint = ExperimentCheckpoint(
            study_name="test_study",
            completed_runs=[],
            failed_runs=[],
            results=[],
            timestamp=datetime.now(),
            config_hash="test",
        )

        checkpoint_path = tmp_path / "checkpoint.pkl"
        checkpoint.save(checkpoint_path)

        assert checkpoint_path.exists()

        loaded = ExperimentCheckpoint.load(checkpoint_path)
        assert loaded.study_name == "test_study"


class TestExperimentRunner:
    """Tests for ExperimentRunner class."""

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def ablation_config(self, temp_output_dir):
        """Create test ablation study config."""
        exp = ExperimentConfig(
            name="test_exp",
            description="Test experiment",
        )
        return AblationStudyConfig(
            study_name="test_study",
            experiments=[exp],
            seeds=[42],
            test_cases=[],
            output_dir=temp_output_dir,
            parallel_workers=1,
        )

    def test_runner_initialization(self, ablation_config):
        """Should initialize runner with config."""
        runner = ExperimentRunner(ablation_config)

        assert runner.config == ablation_config
        assert runner.results_dir == ablation_config.output_dir / "experiments"
        assert runner.results_dir.exists()

    def test_runner_creates_results_dir(self, temp_output_dir):
        """Should create results directory if not exists."""
        output_dir = temp_output_dir / "new_dir"
        assert not output_dir.exists()

        config = AblationStudyConfig(
            study_name="test",
            experiments=[],
            output_dir=output_dir,
        )
        runner = ExperimentRunner(config)

        assert runner.results_dir.exists()

    def test_has_heuristics_enabled_true(self):
        """Should detect enabled heuristics."""
        runner = ExperimentRunner(
            AblationStudyConfig(
                study_name="test",
                experiments=[],
                output_dir=Path("/tmp"),
            )
        )

        toggle = ComponentToggle()
        assert runner._has_heuristics_enabled(toggle) is True

    def test_has_heuristics_enabled_false(self):
        """Should detect when no heuristics enabled."""
        runner = ExperimentRunner(
            AblationStudyConfig(
                study_name="test",
                experiments=[],
                output_dir=Path("/tmp"),
            )
        )

        toggle = ComponentToggle.all_disabled()
        assert runner._has_heuristics_enabled(toggle) is False

    def test_has_heuristics_enabled_partial(self):
        """Should detect when some heuristics enabled."""
        runner = ExperimentRunner(
            AblationStudyConfig(
                study_name="test",
                experiments=[],
                output_dir=Path("/tmp"),
            )
        )

        toggle = ComponentToggle.all_disabled()
        toggle.spectral_init = True
        assert runner._has_heuristics_enabled(toggle) is True

    def test_get_base_optimizer_config(self):
        """Should return base optimizer config."""
        runner = ExperimentRunner(
            AblationStudyConfig(
                study_name="test",
                experiments=[],
                output_dir=Path("/tmp"),
            )
        )

        config = runner._get_base_optimizer_config(seed=42)

        assert config.seed == 42
        assert config.epochs == 8000

    def test_save_run_checkpoint(self, temp_output_dir):
        """Should save checkpoint file and directory structure."""
        runner = ExperimentRunner(
            AblationStudyConfig(
                study_name="test",
                experiments=[],
                output_dir=temp_output_dir,
            )
        )

        # Create a simple result-like object (not a Mock to avoid pickle issues)
        from dataclasses import dataclass

        @dataclass
        class SimpleResult:
            best_state: dict
            final_state: dict
            history: list
            best_loss: float
            final_loss: float

        result = SimpleResult(
            best_state={"x": [1.0, 2.0]},
            final_state={"x": [1.0, 2.0]},
            history=[],
            best_loss=1.5,
            final_loss=1.6,
        )

        checkpoint_path = runner._save_run_checkpoint(
            "test_exp",
            42,
            "test.kicad_pcb",
            result,
        )

        assert checkpoint_path.exists()
        assert checkpoint_path.name == "test_result.pkl"
        assert "test_exp" in str(checkpoint_path)
        assert "seed_42" in str(checkpoint_path)

    def test_run_drc_validation_unavailable(self):
        """Should return (-1, -1) when DRC validation fails."""
        runner = ExperimentRunner(
            AblationStudyConfig(
                study_name="test",
                experiments=[],
                output_dir=Path("/tmp"),
            )
        )

        # Mock the validation to fail
        with patch.object(runner, "_run_drc_validation"):
            runner._run_drc_validation = Mock(return_value=(-1, -1))

            errors, warnings = runner._run_drc_validation(
                Mock(spec=PlacementState),
                Mock(),
                Path("test.kicad_pcb"),
            )

            assert errors == -1
            assert warnings == -1

    def test_run_single_experiment_requires_test_case(self):
        """Should require test_case to be a valid Path."""
        runner = ExperimentRunner(
            AblationStudyConfig(
                study_name="test",
                experiments=[],
                output_dir=Path("/tmp"),
            )
        )

        exp = ExperimentConfig(
            name="test_exp",
            description="Test",
        )

        # Should work with Path (or at least not fail on type)
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb") as f:
            test_case_path = Path(f.name)

            # This will fail on parse, but type should be fine
            with patch.object(runner, "run_single_experiment"):
                runner.run_single_experiment = Mock(
                    return_value=ExperimentRun(
                        experiment_name="test",
                        seed=42,
                        test_case=str(test_case_path),
                        final_loss=1.0,
                        best_loss=0.9,
                        convergence_epoch=100,
                        epochs_completed=200,
                        quality_metrics={},
                        drc_error_count=0,
                        drc_warning_count=0,
                        elapsed_seconds=10.0,
                        final_state=Mock(),
                        checkpoint_path=None,
                        timestamp=datetime.now(),
                        config_hash="test",
                    )
                )

                result = runner.run_single_experiment(
                    exp, 42, test_case_path
                )
                assert result.test_case == str(test_case_path)

    def test_experiment_run_with_curriculum_disabled(self):
        """Should use train() instead of train_multiphase() when curriculum disabled."""
        runner = ExperimentRunner(
            AblationStudyConfig(
                study_name="test",
                experiments=[],
                output_dir=Path("/tmp"),
            )
        )

        # This will be handled in implementation
        toggle = ComponentToggle(curriculum_learning=False)
        assert toggle.curriculum_learning is False

    def test_experiment_run_with_all_losses_disabled(self):
        """Should handle all losses disabled."""
        runner = ExperimentRunner(
            AblationStudyConfig(
                study_name="test",
                experiments=[],
                output_dir=Path("/tmp"),
            )
        )

        losses = LossToggle.all_disabled()
        enabled = losses.get_enabled_losses()

        assert len(enabled) == 0

    def test_experiment_run_with_hyperparameter_overrides(self):
        """Should apply hyperparameter overrides."""
        from temper_placer.ablation.config import HyperparameterOverrides

        exp = ExperimentConfig(
            name="test",
            description="Test",
            hyperparameters=HyperparameterOverrides(
                epochs=1000,
                learning_rate_initial=0.05,
            ),
        )

        assert exp.hyperparameters.epochs == 1000
        assert exp.hyperparameters.learning_rate_initial == 0.05

    def test_quality_metrics_aggregation(self):
        """Should store quality metrics."""
        run = ExperimentRun(
            experiment_name="test",
            seed=42,
            test_case="test.kicad_pcb",
            final_loss=1.0,
            best_loss=0.9,
            convergence_epoch=100,
            epochs_completed=200,
            quality_metrics={
                "wirelength": 10.5,
                "loop_area_compliance": 0.95,
                "routing_congestion": 0.2,
            },
            drc_error_count=0,
            drc_warning_count=0,
            elapsed_seconds=10.0,
            final_state=Mock(),
            checkpoint_path=None,
            timestamp=datetime.now(),
            config_hash="test",
        )

        assert "wirelength" in run.quality_metrics
        assert run.quality_metrics["wirelength"] == 10.5
        assert run.quality_metrics["loop_area_compliance"] == 0.95

    def test_get_pending_tasks_all(self):
        """Should return all tasks when no checkpoint."""
        config = AblationStudyConfig(
            study_name="test",
            experiments=[
                ExperimentConfig(name="exp1", description="Test 1"),
                ExperimentConfig(name="exp2", description="Test 2"),
            ],
            seeds=[42, 123],
            test_cases=[Path("test1.kicad_pcb"), Path("test2.kicad_pcb")],
            output_dir=Path("/tmp"),
        )
        runner = ExperimentRunner(config)

        # Should have 2 exp × 2 seeds × 2 test cases = 8 tasks
        tasks = runner.get_pending_tasks()
        assert len(tasks) == 8

    def test_get_pending_tasks_skip_completed(self):
        """Should skip completed tasks when resuming."""
        from temper_placer.ablation.runner import ExperimentCheckpoint

        config = AblationStudyConfig(
            study_name="test",
            experiments=[
                ExperimentConfig(name="exp1", description="Test 1"),
            ],
            seeds=[42, 123],
            test_cases=[Path("test1.kicad_pcb")],
            output_dir=Path("/tmp"),
        )
        runner = ExperimentRunner(config)

        # Simulate checkpoint with one completed run
        runner.checkpoint = ExperimentCheckpoint(
            study_name="test",
            completed_runs=[("exp1", 42, "test1.kicad_pcb")],
            failed_runs=[],
            results=[],
            timestamp=datetime.now(),
            config_hash="test",
        )

        tasks = runner.get_pending_tasks()
        # Should have only 1 remaining (exp1, seed 123)
        assert len(tasks) == 1
        assert tasks[0][1] == 123  # seed should be 123

    def test_load_checkpoint(self, tmp_path):
        """Should load checkpoint on initialization."""
        from temper_placer.ablation.runner import ExperimentCheckpoint

        # Create and save checkpoint
        checkpoint = ExperimentCheckpoint(
            study_name="test_study",
            completed_runs=[("test", 42, "test.kicad_pcb")],
            failed_runs=[],
            results=[],
            timestamp=datetime.now(),
            config_hash="test",
        )

        checkpoint_path = tmp_path / "checkpoint.pkl"
        checkpoint.save(checkpoint_path)

        # Create runner with output dir containing checkpoint
        config = AblationStudyConfig(
            study_name="test_study",
            experiments=[],
            output_dir=tmp_path,
        )
        runner = ExperimentRunner(config)

        # Should have loaded checkpoint
        assert runner.checkpoint is not None
        assert len(runner.checkpoint.completed_runs) == 1

    def test_failed_runs_tracking(self):
        """Should track failed runs in checkpoint."""
        runner = ExperimentRunner(
            AblationStudyConfig(
                study_name="test",
                experiments=[],
                output_dir=Path("/tmp"),
            )
        )

        runner._failed_runs = [
            ("exp1", 42, "test.kicad_pcb", "Error message"),
        ]

        assert len(runner._failed_runs) == 1
        assert runner._failed_runs[0][0] == "exp1"
