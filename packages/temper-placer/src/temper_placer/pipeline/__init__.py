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
from temper_placer.pipeline.feedback import (
    AdjustmentApplier,
    AdjustmentType,
    FeedbackAdjustment,
    FeedbackGenerator,
    FeedbackLoopConfig,
    FeedbackLoopResult,
    run_feedback_loop,
)
from temper_placer.pipeline.orchestrator import (
    PipelineOrchestrator,
)
from temper_placer.pipeline.state import (
    PipelineConfig,
    PipelineError,
    PipelinePhase,
    PipelineState,
)
from temper_placer.pipeline.preflight import (
    PreflightCheck,
    PreflightChecker,
    PreflightReport,
    PreflightResult,
)
from temper_placer.pipeline.visualization import (
    ProgressCallback,
    RichDashboard,
    TerminalProgress,
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
