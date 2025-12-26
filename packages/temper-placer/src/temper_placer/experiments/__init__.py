"""
Experimental modules for temper-placer research and optimization.

This package contains:
- MetricsTracker: Systematic metrics collection and tracking
- Weight search and hyperparameter tuning
- Comparative analysis across PCB datasets
- Correlation studies between loss functions and DRC
"""

from temper_placer.experiments.metrics_tracker import (
    MetricsTracker,
    RunMetrics,
    create_run_id,
)

__all__ = [
    "MetricsTracker",
    "RunMetrics",
    "create_run_id",
]
