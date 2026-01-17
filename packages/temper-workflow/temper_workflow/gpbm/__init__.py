# GPBM Tools Package
# Gather-Plan-Build-Measure workflow utilities
#
# Extended with scientific method phases:
# - HYPOTHESIZE: Pre-register predictions before experiments
# - ANALYZE: Compare results against predictions with statistical rigor

from .gather import GatherPhase, GatherContext
from .plan import PlanPhase
from .measure import MeasurementRunner, MeasurementResult
from .hypothesize import HypothesizePhase, Hypothesis, ValidationResult
from .analyze import AnalyzePhase, AnalysisResult, ConfidenceInterval

__all__ = [
    # Original GPBM
    "GatherPhase",
    "GatherContext",
    "PlanPhase",
    "MeasurementRunner",
    "MeasurementResult",
    # Scientific method extensions
    "HypothesizePhase",
    "Hypothesis",
    "ValidationResult",
    "AnalyzePhase",
    "AnalysisResult",
    "ConfidenceInterval",
]
