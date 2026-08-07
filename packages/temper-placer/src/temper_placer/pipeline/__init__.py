"""Pipeline module for temper-placer.

Provides orchestration for the full placement pipeline:
    Input -> Semantic -> Topological -> Preflight -> Geometric -> Routing -> Refinement -> Output
"""

from temper_placer.pipeline.convergence import (
    ConvergenceChecker,
    ConvergenceCriteria,
    ConvergenceState,
    TerminationReason,
)
from temper_placer.pipeline.metrics_observer import (
    CanaryCheckError,
    CrossValidationError,
    MetricsObserver,
)
from temper_placer.pipeline.preflight import (
    PreflightCheck,
    PreflightChecker,
    PreflightReport,
    PreflightResult,
)
from temper_placer.pipeline.state import (
    PipelineConfig,
    PipelineError,
    PipelinePhase,
    PipelineState,
)
from temper_placer.pipeline.visualization import (
    ProgressCallback,
    RichDashboard,
    TerminalProgress,
    create_progress_display,
)

__all__ = [
    # Orchestrator
    "PipelineConfig",
    "PipelineError",
    "PipelinePhase",
    "PipelineState",
    # Convergence
    "TerminationReason",
    "ConvergenceCriteria",
    "ConvergenceState",
    "ConvergenceChecker",
    # Preflight
    "PreflightResult",
    "PreflightCheck",
    "PreflightReport",
    "PreflightChecker",
    # Visualization
    "ProgressCallback",
    "TerminalProgress",
    "RichDashboard",
    "create_progress_display",
    # Metrics observer
    "CanaryCheckError",
    "CrossValidationError",
    "MetricsObserver",
]
