"""Experiment runner for ablation study framework."""

import logging
import pickle
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import jax

from temper_placer.ablation.config import (
    AblationStudyConfig,
    ExperimentConfig,
)
from temper_placer.ablation.registry import (
    HeuristicRegistry,
    LossRegistry,
    TechniqueApplicator,
)


@dataclass
class ExperimentRun:
    """Result from a single experiment run (one config × seed × test_case)."""

    # Identifiers
    experiment_name: str
    """Name of the experiment configuration"""

    seed: int
    """Random seed used for this run"""

    test_case: str
    """Path to test case file"""

    # Training results
    final_loss: float
    """Loss value at final epoch"""

    best_loss: float
    """Best loss achieved during training"""

    convergence_epoch: int | None
    """Epoch when convergence was detected (if early stopped)"""

    epochs_completed: int
    """Total number of epochs completed"""

    # Quality metrics
    quality_metrics: dict[str, float]
    """Computed quality metrics (wirelength, loop_area, etc.)"""

    # DRC validation
    drc_error_count: int
    """Number of DRC errors (-1 if DRC unavailable)"""

    drc_warning_count: int
    """Number of DRC warnings (-1 if DRC unavailable)"""

    # Timing
    elapsed_seconds: float
    """Wall clock time for this experiment run"""

    # State
    final_state: Any
    """Final placement state"""

    checkpoint_path: Path | None
    """Path to saved checkpoint (or None if not saved)"""

    # Metadata
    timestamp: datetime
    """When this run was executed"""

    config_hash: str
    """SHA256 hash of experiment configuration (first 12 chars)"""


@dataclass
class ExperimentCheckpoint:
    """Checkpoint for resuming interrupted ablation studies."""

    study_name: str
    """Name of the study"""

    completed_runs: list[tuple[str, int, str]]
    """List of (exp_name, seed, test_case) that completed successfully"""

    failed_runs: list[tuple[str, int, str, str]]
    """List of (exp_name, seed, test_case, error_message) that failed"""

    results: list[ExperimentRun]
    """List of all ExperimentRun results so far"""

    timestamp: datetime
    """When this checkpoint was created"""

    config_hash: str
    """SHA256 hash of study configuration"""

    def save(self, path: Path) -> None:
        """Save checkpoint to file.

        Args:
            path: Path to save checkpoint pickle
        """
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: Path) -> "ExperimentCheckpoint":
        """Load checkpoint from file.

        Args:
            path: Path to checkpoint pickle

        Returns:
            Loaded ExperimentCheckpoint
        """
        with open(path, "rb") as f:
            return pickle.load(f)


class ExperimentRunner:
    """Executes ablation study experiments with support for parallelization."""

    def __init__(self, config: AblationStudyConfig):
        """Initialize runner with study configuration.

        Args:
            config: AblationStudyConfig defining experiments, seeds, test cases
        """
        self.config = config
        self.results_dir = config.output_dir / "experiments"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = config.output_dir / "checkpoint.pkl"

        self.logger = logging.getLogger(__name__)

        # Checkpoint state
        self.checkpoint: ExperimentCheckpoint | None = None
        self._failed_runs: list[tuple[str, int, str, str]] = []
        self._load_checkpoint()

    def _load_checkpoint(self) -> None:
        """Load existing checkpoint if present."""
        if self.checkpoint_path.exists():
            try:
                self.checkpoint = ExperimentCheckpoint.load(self.checkpoint_path)
                self.logger.info(
                    f"Loaded checkpoint with {len(self.checkpoint.completed_runs)} "
                    f"completed runs"
                )
            except Exception as e:
                self.logger.warning(f"Failed to load checkpoint: {e}")
                self.checkpoint = None

    def _save_checkpoint(self, results: list[ExperimentRun]) -> None:
        """Save checkpoint with current progress.

        Args:
            results: List of ExperimentRun results to save
        """
        completed = [
            (r.experiment_name, r.seed, r.test_case) for r in results
        ]
        checkpoint = ExperimentCheckpoint(
            study_name=self.config.study_name,
            completed_runs=completed,
            failed_runs=self._failed_runs,
            results=results,
            timestamp=datetime.now(),
            config_hash=self._compute_study_hash(),
        )
        checkpoint.save(self.checkpoint_path)

    def _compute_study_hash(self) -> str:
        """Compute hash of study configuration.

        Returns:
            SHA256 hash (first 12 chars)
        """
        import hashlib
        import json

        config_data = {
            "study_name": self.config.study_name,
            "n_experiments": len(self.config.experiments),
            "n_seeds": len(self.config.seeds),
            "n_test_cases": len(self.config.test_cases),
        }
        config_str = json.dumps(config_data, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:12]

    def get_pending_tasks(self) -> list[tuple[ExperimentConfig, int, Path]]:
        """Get list of tasks that haven't been completed yet.

        Returns:
            List of (experiment, seed, test_case) tuples to run
        """
        all_tasks = [
            (exp, seed, tc)
            for exp in self.config.experiments
            for seed in self.config.seeds
            for tc in self.config.test_cases
        ]

        if self.checkpoint:
            completed_keys = set(self.checkpoint.completed_runs)
            all_tasks = [
                t
                for t in all_tasks
                if (t[0].name, t[1], str(t[2])) not in completed_keys
            ]

        return all_tasks

    def _run_single_experiment_wrapper(
        self,
        experiment: ExperimentConfig,
        seed: int,
        test_case: Path,
    ) -> ExperimentRun:
        """Wrapper for run_single_experiment for ProcessPoolExecutor.

        This function is called in a separate process. Each worker has
        its own JAX context which is initialized automatically.

        Args:
            experiment: Experiment configuration
            seed: Random seed
            test_case: Path to test case

        Returns:
            ExperimentRun result
        """
        return self.run_single_experiment(experiment, seed, test_case)

    def run_all(
        self,
        resume: bool = True,
        retry_failed: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[ExperimentRun]:
        """Run all experiments across all seeds and test cases.

        Args:
            resume: If True, skip completed runs from checkpoint
            retry_failed: If True, retry previously failed runs
            progress_callback: Called with (completed, total) after each run

        Returns:
            List of all ExperimentRun results
        """
        # Initialize tracking
        self._failed_runs = []

        # Get tasks to run
        if resume and self.checkpoint:
            results = list(self.checkpoint.results)
            all_tasks = self.get_pending_tasks()

            if retry_failed:
                # Add failed tasks back to retry
                failed_keys = {
                    (f[0], f[1], f[2]) for f in self.checkpoint.failed_runs
                }
                for exp in self.config.experiments:
                    for seed in self.config.seeds:
                        for tc in self.config.test_cases:
                            if (exp.name, seed, str(tc)) in failed_keys:
                                all_tasks.append((exp, seed, tc))
        else:
            results = []
            all_tasks = [
                (exp, seed, tc)
                for exp in self.config.experiments
                for seed in self.config.seeds
                for tc in self.config.test_cases
            ]

        total = len(all_tasks)
        completed = 0

        if total == 0:
            self.logger.info("No pending tasks to run")
            return results

        self.logger.info(
            f"Running {total} experiment tasks with "
            f"{self.config.parallel_workers} workers"
        )

        # Execute in parallel
        with ProcessPoolExecutor(
            max_workers=self.config.parallel_workers
        ) as executor:
            # Submit all tasks
            futures = {
                executor.submit(
                    self._run_single_experiment_wrapper, exp, seed, tc
                ): (exp, seed, tc)
                for exp, seed, tc in all_tasks
            }

            # Process as completed
            for future in as_completed(futures):
                task = futures[future]
                exp, seed, tc = task

                try:
                    result = future.result()
                    results.append(result)
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, total)

                    self.logger.info(
                        f"[{completed}/{total}] Completed: {exp.name}, "
                        f"seed={seed}, loss={result.best_loss:.4f}"
                    )

                except Exception as e:
                    self._failed_runs.append((exp.name, seed, str(tc), str(e)))
                    self.logger.error(
                        f"[{completed}/{total}] Failed: {exp.name}, "
                        f"seed={seed}, error={e}"
                    )

                # Checkpoint periodically
                if completed % self.config.checkpoint_interval == 0:
                    self._save_checkpoint(results)
                    self.logger.debug(f"Checkpoint saved at {completed} runs")

        # Final checkpoint
        self._save_checkpoint(results)

        # Summary
        n_failed = len(self._failed_runs)
        self.logger.info(f"Completed {len(results)} runs, {n_failed} failed")

        return results

    def _has_heuristics_enabled(self, toggle) -> bool:
        """Check if any heuristics are enabled in the toggle.

        Args:
            toggle: ComponentToggle to check

        Returns:
            True if at least one heuristic is enabled
        """
        return len(toggle.get_enabled_heuristics()) > 0

    def _get_base_optimizer_config(self, seed: int):
        """Get base optimizer configuration with standard settings.

        Args:
            seed: Random seed for reproducibility

        Returns:
            OptimizerConfig with default settings
        """
        from temper_placer.optimizer.config import (
            LearningRateSchedule,
            OptimizerConfig,
            TemperatureSchedule,
        )

        return OptimizerConfig(
            epochs=8000,
            seed=seed,
            temperature=TemperatureSchedule(start=5.0, end=0.1),
            learning_rate=LearningRateSchedule(
                initial=0.1,
                final=0.01,
                warmup_epochs=100,
                decay_type="exponential",
            ),
            curriculum_phases=[],
            gradient_clip_norm=1.0,
            use_centrality_weighting=False,
        )

    def _save_run_checkpoint(
        self,
        exp_name: str,
        seed: int,
        test_case: str,
        result: Any,
    ) -> Path:
        """Save checkpoint for this run.

        Args:
            exp_name: Experiment name
            seed: Random seed
            test_case: Test case path
            result: Training result object

        Returns:
            Path to saved checkpoint
        """
        checkpoint_dir = self.results_dir / exp_name / f"seed_{seed}"
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        test_case_name = Path(test_case).stem
        checkpoint_path = checkpoint_dir / f"{test_case_name}_result.pkl"

        checkpoint_data = {
            "best_state": result.best_state,
            "final_state": result.final_state if hasattr(result, "final_state") else None,
            "history": result.history if hasattr(result, "history") else [],
            "best_loss": result.best_loss,
            "final_loss": result.final_loss,
            "convergence_epoch": result.convergence_epoch if hasattr(result, "convergence_epoch") else None,
        }

        with open(checkpoint_path, "wb") as f:
            pickle.dump(checkpoint_data, f)

        return checkpoint_path

    def _run_drc_validation(
        self,
        state: Any,
        netlist: Any,
        original_pcb: Path,
    ) -> tuple[int, int]:
        """Run KiCad DRC validation on placement.

        Args:
            state: PlacementState to validate
            netlist: Netlist
            original_pcb: Original PCB path

        Returns:
            Tuple of (error_count, warning_count), or (-1, -1) if unavailable
        """
        try:
            # Try to import and run DRC if available
            from temper_placer.io.kicad_writer import export_placements
            from temper_placer.validation.drc import KiCadDRCValidator

            with tempfile.NamedTemporaryFile(
                suffix=".kicad_pcb", delete=False
            ) as f:
                temp_pcb = Path(f.name)

            try:
                # Need component refs for export_placements
                component_refs = [c.ref for c in netlist.components]
                export_placements(
                    template_pcb=original_pcb,
                    output_pcb=temp_pcb,
                    state=state,
                    component_refs=component_refs
                )
                validator = KiCadDRCValidator()
                drc_result = validator.run_drc(temp_pcb)
                return (drc_result.error_count, drc_result.warning_count)
            finally:
                temp_pcb.unlink(missing_ok=True)

        except ImportError:
            self.logger.debug("DRC validation not available")
            return (-1, -1)
        except Exception as e:
            self.logger.warning(f"DRC validation failed: {e}")
            return (-1, -1)

    def run_single_experiment(
        self,
        experiment: ExperimentConfig,
        seed: int,
        test_case: Path,
    ) -> ExperimentRun:
        """Run one experiment configuration with one seed on one test case.

        Args:
            experiment: Configuration for this experiment
            seed: Random seed for reproducibility
            test_case: Path to KiCad PCB file

        Returns:
            ExperimentRun with all results and metrics
        """
        start_time = time.time()

        self.logger.info(
            f"Starting: {experiment.name}, seed={seed}, test_case={test_case.name}"
        )

        try:
            # ========================
            # 1. PARSE TEST CASE
            # ========================
            from temper_placer.io.kicad_parser import parse_kicad_pcb

            parse_result = parse_kicad_pcb(test_case)
            netlist = parse_result.netlist
            board = parse_result.board
            if board is None:
                raise ValueError(f"No board geometry found in {test_case}")

            # Load constraints if available
            from temper_placer.io.config_loader import PlacementConstraints, load_constraints
            constraints_path = test_case.with_suffix(".yaml")
            if constraints_path.exists():
                try:
                    constraints = load_constraints(constraints_path)
                except Exception as e:
                    self.logger.warning(f"Failed to load constraints from {constraints_path}: {e}")
                    constraints = PlacementConstraints()
            else:
                constraints = PlacementConstraints()

            # ========================
            # 2. RUN HEURISTIC INITIALIZATION
            # ========================
            initial_state = None
            if self._has_heuristics_enabled(experiment.components):
                self.logger.debug("Running heuristic initialization")
                try:
                    pipeline = HeuristicRegistry.create_pipeline(
                        experiment.components, constraints=constraints
                    )
                    key = jax.random.PRNGKey(seed)
                    heuristic_result = pipeline.run(board, netlist, constraints, key)
                    initial_state = heuristic_result.state
                except Exception as e:
                    self.logger.warning(f"Heuristic initialization failed: {e}")
                    initial_state = None

            # ========================
            # 3. BUILD OPTIMIZER CONFIG
            # ========================
            base_config = self._get_base_optimizer_config(seed)

            # Apply hyperparameter overrides
            if experiment.hyperparameters.epochs:
                base_config.epochs = experiment.hyperparameters.epochs
            if experiment.hyperparameters.learning_rate_initial:
                base_config.learning_rate.initial = (
                    experiment.hyperparameters.learning_rate_initial
                )
            if experiment.hyperparameters.learning_rate_final:
                base_config.learning_rate.final = (
                    experiment.hyperparameters.learning_rate_final
                )
            if experiment.hyperparameters.temperature_start:
                base_config.temperature.start = experiment.hyperparameters.temperature_start
            if experiment.hyperparameters.temperature_end:
                base_config.temperature.end = experiment.hyperparameters.temperature_end

            # Apply technique toggles
            optimizer_config = TechniqueApplicator.apply_toggles(
                base_config, experiment.components
            )

            # ========================
            # 4. BUILD COMPOSITE LOSS
            # ========================
            weights = (
                experiment.hyperparameters.loss_weights
                or LossRegistry.get_default_weights()
            )
            composite_loss = LossRegistry.create_composite_loss(
                experiment.losses, weights
            )

            # ========================
            # 5. BUILD LOSS CONTEXT
            # ========================
            try:
                from temper_placer.losses.base import LossContext

                context = LossContext.from_netlist_and_board(
                    netlist,
                    board,
                    constraints=constraints,
                    use_centrality_weighting=experiment.components.centrality_gradient_scaling,
                )
            except Exception as e:
                self.logger.warning(f"LossContext creation failed: {e}")
                # Fallback to creating context without constraints if signature is still old
                # (to debug why the kwarg is failing)
                try:
                    context = LossContext.from_netlist_and_board(
                        netlist,
                        board,
                        use_centrality_weighting=experiment.components.centrality_gradient_scaling,
                    )
                except Exception:
                    context = None

            if context is None:
                raise RuntimeError("Failed to create LossContext")

            # ========================
            # 6. RUN TRAINING
            # ========================
            self.logger.debug(f"Starting training for {optimizer_config.epochs} epochs")

            try:
                if experiment.components.curriculum_learning:
                    from temper_placer.optimizer.train import train_multiphase

                    training_result = train_multiphase(
                        netlist,
                        board,
                        loss_factory=lambda w: LossRegistry.create_composite_loss(
                            experiment.losses, w
                        ),
                        context=context,
                        config=optimizer_config,
                        initial_state=initial_state,
                    )
                else:
                    from temper_placer.optimizer.train import train

                    training_result = train(
                        netlist,
                        board,
                        composite_loss=composite_loss,
                        context=context,
                        config=optimizer_config,
                        initial_state=initial_state,
                    )
            except Exception as e:
                self.logger.error(f"Training failed: {e}", exc_info=True)
                raise

            elapsed = time.time() - start_time
            self.logger.info(f"Training completed in {elapsed:.1f}s")

            # ========================
            # 7. COMPUTE QUALITY METRICS
            # ========================
            quality_metrics = {}
            try:
                from temper_placer.metrics.quality import compute_quality_report

                best_state = training_result.best_state
                if best_state is not None:
                    quality_metrics = compute_quality_report(
                        best_state, netlist, board, context, {}
                    )
            except Exception as e:
                self.logger.warning(f"Quality metrics computation failed: {e}")

            # ========================
            # 8. RUN DRC VALIDATION
            # ========================
            drc_errors, drc_warnings = self._run_drc_validation(
                training_result.best_state, netlist, test_case
            )

            # ========================
            # 9. SAVE CHECKPOINT
            # ========================
            checkpoint_path = None
            try:
                checkpoint_path = self._save_run_checkpoint(
                    experiment.name, seed, str(test_case), training_result
                )
            except Exception as e:
                self.logger.warning(f"Checkpoint save failed: {e}")

            # ========================
            # 10. RETURN RESULT
            # ========================
            return ExperimentRun(
                experiment_name=experiment.name,
                seed=seed,
                test_case=str(test_case),
                final_loss=float(training_result.final_loss),
                best_loss=float(training_result.best_loss),
                convergence_epoch=getattr(training_result, "convergence_epoch", None),
                epochs_completed=getattr(training_result, "total_epochs", optimizer_config.epochs),
                quality_metrics=quality_metrics,
                drc_error_count=drc_errors,
                drc_warning_count=drc_warnings,
                elapsed_seconds=elapsed,
                final_state=training_result.best_state,
                checkpoint_path=checkpoint_path,
                timestamp=datetime.now(),
                config_hash=experiment.get_config_hash(),
            )

        except Exception as e:
            self.logger.error(
                f"Experiment failed: {experiment.name}, seed={seed}, "
                f"test_case={test_case}: {e}",
                exc_info=True,
            )
            raise
