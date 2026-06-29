"""
Manufacturing tolerance models for PCB production.

This module provides tools to analyze the impact of manufacturing variability
(etching, drilling, layer registration) on the design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CopperWeight(Enum):
    """Copper weight in ounces per square foot (oz/ft²)."""
    HALF_OZ = 0.5    # ~17um
    ONE_OZ = 1.0     # ~35um
    TWO_OZ = 2.0     # ~70um


class LayerType(Enum):
    """Type of PCB layer."""
    OUTER = 'outer'
    INNER = 'inner'


@dataclass
class ToleranceTable:
    """Per-feature tolerance specifications."""

    # Etch tolerance by copper weight (mm)
    # Reflects the lateral etching (undercut) during production
    etch_tolerance: dict[CopperWeight, float] = field(default_factory=lambda: {
        CopperWeight.HALF_OZ: 0.025,
        CopperWeight.ONE_OZ: 0.05,
        CopperWeight.TWO_OZ: 0.075,
    })

    # Registration by layer type (mm)
    # Reflects layer-to-layer alignment accuracy
    registration: dict[LayerType, float] = field(default_factory=lambda: {
        LayerType.OUTER: 0.1,
        LayerType.INNER: 0.15,
    })

    # Solder mask registration (mm)
    solder_mask_registration: float = 0.075


@dataclass
class FeatureTolerance:
    """Tolerance analysis for a specific feature."""
    feature_type: str
    nominal_value: float
    tolerance_plus: float
    tolerance_minus: float
    worst_case_min: float
    worst_case_max: float


class ToleranceAnalyzer:
    """Analyze tolerances for a design based on manufacturing capabilities."""

    def __init__(self, table: ToleranceTable = ToleranceTable()):
        self.table = table

    def analyze_clearance(
        self,
        clearance_mm: float,
        copper_weight: CopperWeight,
        layer_type: LayerType
    ) -> FeatureTolerance:
        """
        Calculate tolerance for a clearance (gap) between copper features.

        Clearance is reduced by:
        1. Etching: Copper expands laterally (etch factor).
           Gap decreases by 2 * etch (one from each side).
        2. Registration: Layers can shift relative to each other.
        """
        etch = self.table.etch_tolerance.get(copper_weight, 0.05)
        reg = self.table.registration.get(layer_type, 0.1)

        total_minus = 2 * etch + reg

        return FeatureTolerance(
            feature_type='clearance',
            nominal_value=clearance_mm,
            tolerance_plus=0.0,
            tolerance_minus=total_minus,
            worst_case_min=clearance_mm - total_minus,
            worst_case_max=clearance_mm
        )

    def analyze_trace(
        self,
        width_mm: float,
        copper_weight: CopperWeight
    ) -> FeatureTolerance:
        """
        Calculate tolerance for trace width.

        Trace width changes primarily due to etching.
        """
        etch = self.table.etch_tolerance.get(copper_weight, 0.05)

        return FeatureTolerance(
            feature_type='trace_width',
            nominal_value=width_mm,
            tolerance_plus=etch,
            tolerance_minus=etch,
            worst_case_min=width_mm - etch,
            worst_case_max=width_mm + etch
        )
