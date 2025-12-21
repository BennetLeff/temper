"""Manufacturing variability models for PCB design validation.

This package provides tolerance analysis for manufacturing variability:
- Level 1: Simple inflation (in core/manufacturing.py)
- Level 2: Per-parameter tolerance model (tolerances.py)
- Level 3: Monte Carlo analysis (future)
"""

from temper_placer.manufacturing.tolerances import (
    CopperWeight,
    LayerType,
    DrillSize,
    ToleranceTable,
    FeatureTolerance,
    ToleranceAnalyzer,
)

__all__ = [
    "CopperWeight",
    "LayerType",
    "DrillSize",
    "ToleranceTable",
    "FeatureTolerance",
    "ToleranceAnalyzer",
]
