"""Pipeline module for temper-placer.

Provides orchestration for the full placement pipeline:
    Input -> Semantic -> Topological -> Preflight -> Geometric -> Routing -> Refinement -> Output
"""

from temper_placer.pipeline.orchestrator import (
    PipelinePhase,
    PipelineConfig,
    PipelineState,
    PipelineError,
    PipelineOrchestrator,
)
from temper_placer.pipeline.convergence import (
    TerminationReason,
    ConvergenceCriteria,
    ConvergenceState,
    ConvergenceChecker,
)
from temper_placer.pipeline.feedback import (
    AdjustmentType,
    FeedbackAdjustment,
    FeedbackGenerator,
    AdjustmentApplier,
    FeedbackLoopConfig,
    FeedbackLoopResult,
    run_feedback_loop,
)
from temper_placer.pipeline.preflight import (
    PreflightResult,
    PreflightCheck,
    PreflightReport,
    PreflightChecker,
)
from temper_placer.pipeline.visualization import (
    ProgressCallback,
    TerminalProgress,
    RichDashboard,
    create_progress_display,
)

__all__ = [
    # Orchestrator
    "PipelinePhase",
    "PipelineConfig",
    "PipelineState",
    "PipelineError",
    "PipelineOrchestrator",
    # Convergence
    "TerminationReason",
    "ConvergenceCriteria",
    "ConvergenceState",
    "ConvergenceChecker",
    # Feedback
    "AdjustmentType",
    "FeedbackAdjustment",
    "FeedbackGenerator",
    "AdjustmentApplier",
    "FeedbackLoopConfig",
    "FeedbackLoopResult",
    "run_feedback_loop",
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
]
