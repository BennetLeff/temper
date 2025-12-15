"""
Validation module for temper-placer.

This module provides multiple validation strategies for optimized placements:

1. **Geometric Validation** - Pure Python checks for overlap, boundary, clearance
2. **Quality Metrics** - Placement quality scores (wirelength, congestion, etc.)
3. **ngspice Validation** - Electrical validation via SPICE simulation
4. **KiCad DRC** - Design rule checking via kicad-cli (when available)
5. **File Validation** - PCB file integrity checks

Validation can be run:
- After optimization to verify results
- During optimization (validation-in-the-loop) for penalty feedback
- As standalone checks via CLI
"""

from temper_placer.validation.geometric import (
    GeometricValidator,
    GeometricViolation,
    ViolationType,
    validate_placement,
)
from temper_placer.validation.metrics import (
    PlacementMetrics,
    compute_metrics,
)
from temper_placer.validation.base import (
    ValidationResult,
    ValidationSeverity,
    Validator,
)

__all__ = [
    # Base
    "ValidationResult",
    "ValidationSeverity",
    "Validator",
    # Geometric
    "GeometricValidator",
    "GeometricViolation",
    "ViolationType",
    "validate_placement",
    # Metrics
    "PlacementMetrics",
    "compute_metrics",
]
