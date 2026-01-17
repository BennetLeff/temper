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
from temper_placer.experiments.metrics_integration import (
    MetricsTrackingCallback,
    create_run_metrics,
    record_training_run,
    setup_metrics_tracking,
)
from temper_placer.experiments.proxy_correlation import (
    CorrelationResult,
    CorrelationSample,
    CorrelationTracker,
    track_proxy_actual,
)
from temper_placer.experiments.routing_correlation import (
    RoutingCorrelationStudy,
    PlacementRun,
    CorrelationResult as RoutingCorrelationResult,
    run_pilot_study,
    run_full_study,
    analyze_results,
)

__all__ = [
    "MetricsTracker",
    "RunMetrics",
    "create_run_id",
    "MetricsTrackingCallback",
    "create_run_metrics",
    "record_training_run",
    "setup_metrics_tracking",
    "CorrelationTracker",
    "CorrelationSample",
    "CorrelationResult",
    "track_proxy_actual",
    "RoutingCorrelationStudy",
    "PlacementRun",
    "run_pilot_study",
    "run_full_study",
    "analyze_results",
]
