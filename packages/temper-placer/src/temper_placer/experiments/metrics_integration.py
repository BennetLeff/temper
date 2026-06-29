"""
Metrics tracking integration for the training workflow.

This module provides utilities for:
- Recording metrics from training runs using MetricsTracker
- Creating RunMetrics from TrainingResult
- Automatic integration with CLI training commands
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from temper_placer.core.netlist import Netlist
from temper_placer.experiments.metrics_tracker import (
    MetricsTracker,
    RunMetrics,
    create_run_id,
)


def create_run_metrics(
    result: Any,
    _netlist: Netlist,
    experiment_name: str,
    seed: int,
    config: dict[str, Any],
) -> RunMetrics:
    """
    Create RunMetrics from a TrainingResult.

    Args:
        result: TrainingResult from train() or train_multiphase()
        netlist: Component netlist used for training
        experiment_name: Name of the experiment
        seed: Random seed used
        config: Configuration dictionary

    Returns:
        RunMetrics ready for recording
    """
    config_hash = ""
    if config:
        config_hash = MetricsTracker("", "").get_config_hash(config)

    history = result.history
    final_metrics = history[-1] if history else None

    overlap_loss = 0.0
    boundary_loss = 0.0
    hpwl_mm = 0.0
    gate_loop_area = 0.0
    bootstrap_loop_area = 0.0
    commutation_loop_area = 0.0
    igbt_edge_distance = 0.0

    if final_metrics and final_metrics.loss_breakdown:
        overlap_loss = final_metrics.loss_breakdown.get("overlap", 0.0)
        boundary_loss = final_metrics.loss_breakdown.get("boundary", 0.0)
        hpwl_mm = final_metrics.loss_breakdown.get("wirelength", 0.0)
        gate_loop_area = final_metrics.loss_breakdown.get("gate_loop", 0.0)
        bootstrap_loop_area = final_metrics.loss_breakdown.get("bootstrap_loop", 0.0)
        commutation_loop_area = final_metrics.loss_breakdown.get("commutation_loop", 0.0)

    best_loss = getattr(result, "best_loss", result.final_loss)
    converged = getattr(result, "converged", False)
    total_epochs = getattr(result, "total_epochs", len(history) if history else 0)
    elapsed_seconds = getattr(result, "elapsed_seconds", 0.0)

    drc_errors = -1
    drc_warnings = -1
    routing_completion = -1.0

    validation_history = getattr(result, "validation_history", [])
    if validation_history:
        last_validation = validation_history[-1]
        drc_errors = getattr(last_validation, "drc_errors", -1)
        drc_warnings = getattr(last_validation, "drc_warnings", -1)

    run_id = create_run_id(experiment_name, seed)

    return RunMetrics(
        run_id=run_id,
        experiment_name=experiment_name,
        seed=seed,
        timestamp=datetime.now().isoformat(),
        config_hash=config_hash,
        overlap_loss=overlap_loss,
        boundary_loss=boundary_loss,
        hpwl_mm=hpwl_mm,
        gate_loop_area_mm2=gate_loop_area,
        bootstrap_loop_area_mm2=bootstrap_loop_area,
        commutation_loop_area_mm2=commutation_loop_area,
        igbt_edge_distance_mm=igbt_edge_distance,
        final_loss=result.final_loss,
        best_loss=best_loss,
        convergence_epoch=total_epochs if converged else 0,
        epochs_completed=total_epochs,
        elapsed_seconds=elapsed_seconds,
        drc_errors=drc_errors,
        drc_warnings=drc_warnings,
        routing_completion_percent=routing_completion,
    )


class MetricsTrackingCallback:
    """
    Callback for automatic metrics tracking during training.

    Usage:
        tracker = MetricsTracker(output_dir, experiment_name)
        callback = MetricsTrackingCallback(tracker, netlist, experiment_name, seed, config)

        result = train(..., callback=callback.on_metrics)
    """

    def __init__(
        self,
        tracker: MetricsTracker,
        netlist: Netlist,
        experiment_name: str,
        seed: int,
        config: dict[str, Any],
    ):
        self.tracker = tracker
        self.netlist = netlist
        self.experiment_name = experiment_name
        self.seed = seed
        self.config = config

    def on_metrics(self, metrics: Any) -> None:
        """
        Callback function to be passed to train().

        Args:
            metrics: TrainingMetrics from the training loop
        """
        pass

    def finalize(self, result: Any) -> None:
        """
        Finalize and record metrics when training completes.

        Args:
            result: TrainingResult from train()
        """
        run_metrics = create_run_metrics(
            result,
            self.netlist,
            self.experiment_name,
            self.seed,
            self.config,
        )
        self.tracker.record_run(run_metrics)


def setup_metrics_tracking(
    output_dir: Path | None,
    experiment_name: str,
) -> MetricsTracker | None:
    """
    Set up metrics tracking infrastructure.

    Args:
        output_dir: Directory to save metrics (None to disable tracking)
        experiment_name: Name of the experiment

    Returns:
        MetricsTracker if output_dir is provided, else None
    """
    if output_dir is None:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    return MetricsTracker(output_dir, experiment_name)


def record_training_run(
    tracker: MetricsTracker | None,
    result: Any,
    netlist: Netlist,
    experiment_name: str,
    seed: int,
    config: dict[str, Any],
) -> None:
    """
    Record a training run to the metrics tracker.

    Args:
        tracker: MetricsTracker or None (if tracking is disabled)
        result: TrainingResult from train()
        netlist: Component netlist used for training
        experiment_name: Name of the experiment
        seed: Random seed used
        config: Configuration dictionary
    """
    if tracker is None:
        return

    run_metrics = create_run_metrics(result, netlist, experiment_name, seed, config)
    tracker.record_run(run_metrics)
