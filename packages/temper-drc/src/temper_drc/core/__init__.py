"""Core abstractions for temper-drc."""

from temper_drc.core.check import Check, CompositeCheck
from temper_drc.core.fence import (
    DRCFence,
    FenceBudgetError,
    FenceResult,
    FenceViolation,
    FenceViolationError,
    InvariantSpec,
    _issue_fingerprint,
)
from temper_drc.core.metrics import CheckMetrics, MetricsSummary
from temper_drc.core.result import CheckResult, Issue, Location, RunResult
from temper_drc.core.runner import CheckRunner
from temper_drc.core.severity import Severity

__all__ = [
    "Check",
    "CompositeCheck",
    "CheckRunner",
    "CheckResult",
    "RunResult",
    "Issue",
    "Location",
    "Severity",
    "CheckMetrics",
    "MetricsSummary",
    "DRCFence",
    "FenceBudgetError",
    "FenceResult",
    "FenceViolation",
    "FenceViolationError",
    "InvariantSpec",
    "_issue_fingerprint",
]
