"""Per-parameter tolerance model for manufacturing variability (Level 2).

This module provides detailed tolerance analysis that applies different
tolerances to different feature types, recognizing that:
- Fine traces (< 0.2mm) have tighter tolerance requirements
- Large traces are less sensitive
- Inner layers vs outer layers differ
- Different copper weights have different etch factors

Example:
    >>> from temper_placer.manufacturing.tolerances import (
    ...     ToleranceAnalyzer, ToleranceTable, CopperWeight, LayerType
    ... )
    >>> analyzer = ToleranceAnalyzer()
    >>> result = analyzer.analyze_clearance(0.2, CopperWeight.ONE_OZ, LayerType.OUTER)
    >>> print(f"Worst-case clearance: {result.worst_case_min:.3f}mm")
    Worst-case clearance: 0.050mm

Related issues: temper-6vj.2, temper-6vj (Epic 6: Manufacturing Variability Model)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class CopperWeight(Enum):
    """Standard copper weight options for PCB manufacturing.

    Values represent ounces per square foot, which corresponds to:
    - 0.5 oz = 17µm copper thickness
    - 1.0 oz = 35µm copper thickness
    - 2.0 oz = 70µm copper thickness

    Heavier copper has larger etch tolerance due to longer etch time.
    """

    HALF_OZ = 0.5  # 17µm - fine pitch, tighter tolerance
    ONE_OZ = 1.0  # 35µm - standard, moderate tolerance
    TWO_OZ = 2.0  # 70µm - high current, larger tolerance


class LayerType(Enum):
    """PCB layer types with different registration tolerances.

    Outer layers have better registration because they're imaged directly.
    Inner layers require layer-to-layer alignment which adds tolerance.
    """

    OUTER = "outer"  # Top/bottom layers - better registration
    INNER = "inner"  # Internal layers - worse registration


class DrillSize(Enum):
    """Drill hole size categories with different tolerances.

    Smaller holes require more precise drilling and have tighter tolerances.
    Micro vias use laser drilling with different characteristics.
    """

    MICRO = "micro"  # < 0.3mm - laser drilled, tightest tolerance
    SMALL = "small"  # 0.3-0.6mm - mechanical drill, tight tolerance
    STANDARD = "standard"  # 0.6-1.0mm - standard mechanical drill
    LARGE = "large"  # > 1.0mm - large mechanical drill, loosest tolerance

    @classmethod
    def from_diameter(cls, diameter_mm: float) -> DrillSize:
        """Determine drill size category from hole diameter.

        Args:
            diameter_mm: Hole diameter in millimeters

        Returns:
            Appropriate DrillSize enum value
        """
        if diameter_mm < 0.3:
            return cls.MICRO
        elif diameter_mm < 0.6:
            return cls.SMALL
        elif diameter_mm < 1.0:
            return cls.STANDARD
        else:
            return cls.LARGE


@dataclass
class ToleranceTable:
    """Per-feature tolerance specifications for manufacturing.

    This table holds tolerances for different feature types, allowing
    accurate worst-case analysis. Values are based on typical PCB fab
    capabilities (JLCPCB standard process as baseline).

    All tolerances are in millimeters unless otherwise noted.

    Attributes:
        etch_tolerance: Tolerance by copper weight (mm). Heavier copper
            requires longer etching, leading to more undercut.
        drill_tolerance: Tolerance by hole size category (mm).
        registration: Layer-to-layer registration by layer type (mm).
        solder_mask_registration: Solder mask to copper registration (mm).
        silkscreen_resolution: Minimum silkscreen feature size (mm).
    """

    # Etch tolerance by copper weight (mm)
    # Heavier copper = more etch time = more undercut
    etch_tolerance: Dict[CopperWeight, float] = field(
        default_factory=lambda: {
            CopperWeight.HALF_OZ: 0.025,  # 17µm copper - minimal undercut
            CopperWeight.ONE_OZ: 0.050,  # 35µm copper - standard
            CopperWeight.TWO_OZ: 0.075,  # 70µm copper - significant undercut
        }
    )

    # Drill tolerance by hole size (mm)
    # Smaller holes have tighter requirements
    drill_tolerance: Dict[DrillSize, float] = field(
        default_factory=lambda: {
            DrillSize.MICRO: 0.050,  # Laser drill - very precise
            DrillSize.SMALL: 0.075,  # Small mechanical
            DrillSize.STANDARD: 0.100,  # Standard mechanical
            DrillSize.LARGE: 0.150,  # Large mechanical - more play
        }
    )

    # Layer-to-layer registration by layer type (mm)
    registration: Dict[LayerType, float] = field(
        default_factory=lambda: {
            LayerType.OUTER: 0.100,  # Direct imaging - better alignment
            LayerType.INNER: 0.150,  # Requires lamination alignment
        }
    )

    # Solder mask registration to copper features (mm)
    solder_mask_registration: float = 0.075

    # Minimum silkscreen feature size (mm)
    silkscreen_resolution: float = 0.150

    def get_etch_tolerance(self, copper_weight: CopperWeight) -> float:
        """Get etch tolerance for a copper weight.

        Args:
            copper_weight: Copper weight enum value

        Returns:
            Etch tolerance in mm
        """
        return self.etch_tolerance.get(copper_weight, 0.050)

    def get_drill_tolerance(self, hole_diameter_mm: float) -> float:
        """Get drill tolerance for a hole diameter.

        Args:
            hole_diameter_mm: Hole diameter in mm

        Returns:
            Drill tolerance in mm
        """
        drill_size = DrillSize.from_diameter(hole_diameter_mm)
        return self.drill_tolerance.get(drill_size, 0.100)

    def get_registration(self, layer_type: LayerType) -> float:
        """Get registration tolerance for a layer type.

        Args:
            layer_type: Layer type enum value

        Returns:
            Registration tolerance in mm
        """
        return self.registration.get(layer_type, 0.100)


@dataclass
class FeatureTolerance:
    """Tolerance analysis result for a specific PCB feature.

    Represents the nominal value and tolerance bounds for a feature,
    allowing worst-case analysis for manufacturing.

    Attributes:
        feature_type: Type of feature (clearance, trace_width, via, etc.)
        nominal_value: Design (nominal) value in mm
        tolerance_plus: Maximum positive deviation from nominal (mm)
        tolerance_minus: Maximum negative deviation from nominal (mm)
        worst_case_min: Smallest possible value (nominal - tolerance_minus)
        worst_case_max: Largest possible value (nominal + tolerance_plus)
    """

    feature_type: str
    nominal_value: float
    tolerance_plus: float
    tolerance_minus: float
    worst_case_min: float
    worst_case_max: float

    @property
    def total_tolerance(self) -> float:
        """Total tolerance range (worst_case_max - worst_case_min)."""
        return self.tolerance_plus + self.tolerance_minus

    @property
    def tolerance_pct(self) -> float:
        """Tolerance as percentage of nominal value."""
        if self.nominal_value == 0:
            return 0.0
        return (self.total_tolerance / self.nominal_value) * 100.0

    def meets_requirement(self, min_required: float) -> bool:
        """Check if worst-case value meets minimum requirement.

        Args:
            min_required: Minimum required value (e.g., safety clearance)

        Returns:
            True if worst_case_min >= min_required
        """
        return self.worst_case_min >= min_required

    def margin_to_requirement(self, min_required: float) -> float:
        """Calculate margin to minimum requirement.

        Args:
            min_required: Minimum required value

        Returns:
            Margin in mm (positive = passes, negative = fails)
        """
        return self.worst_case_min - min_required

    @classmethod
    def from_clearance(
        cls, nominal: float, copper_weight: CopperWeight, table: ToleranceTable
    ) -> FeatureTolerance:
        """Create tolerance analysis for a clearance feature.

        Clearance worst-case is SMALLER due to etch undercut expanding
        traces into the gap from both sides.

        Args:
            nominal: Nominal clearance in mm
            copper_weight: Copper weight for etch tolerance
            table: Tolerance table to use

        Returns:
            FeatureTolerance with worst-case clearance (smaller)
        """
        etch = table.get_etch_tolerance(copper_weight)
        # Clearance shrinks by 2x etch (both traces expand into gap)
        total_shrink = 2 * etch

        return cls(
            feature_type="clearance",
            nominal_value=nominal,
            tolerance_plus=0.0,  # Clearance doesn't grow
            tolerance_minus=total_shrink,
            worst_case_min=max(0.0, nominal - total_shrink),
            worst_case_max=nominal,
        )

    @classmethod
    def from_trace_width(
        cls, nominal: float, copper_weight: CopperWeight, table: ToleranceTable
    ) -> FeatureTolerance:
        """Create tolerance analysis for a trace width feature.

        Trace width can vary in both directions due to etch variation.
        Over-etching shrinks traces, under-etching expands them.

        Args:
            nominal: Nominal trace width in mm
            copper_weight: Copper weight for etch tolerance
            table: Tolerance table to use

        Returns:
            FeatureTolerance with symmetric tolerance
        """
        etch = table.get_etch_tolerance(copper_weight)

        return cls(
            feature_type="trace_width",
            nominal_value=nominal,
            tolerance_plus=etch,
            tolerance_minus=etch,
            worst_case_min=max(0.0, nominal - etch),
            worst_case_max=nominal + etch,
        )

    @classmethod
    def from_via_annular_ring(
        cls,
        pad_diameter: float,
        hole_diameter: float,
        copper_weight: CopperWeight,
        layer_type: LayerType,
        table: ToleranceTable,
    ) -> FeatureTolerance:
        """Create tolerance analysis for via annular ring.

        Annular ring is affected by:
        - Drill tolerance (hole can be larger)
        - Etch tolerance (pad can be smaller)
        - Registration (hole can be offset from pad center)

        Args:
            pad_diameter: Via pad diameter in mm
            hole_diameter: Via hole diameter in mm
            copper_weight: Copper weight for etch tolerance
            layer_type: Layer type for registration tolerance
            table: Tolerance table to use

        Returns:
            FeatureTolerance for worst-case annular ring
        """
        nominal_ring = (pad_diameter - hole_diameter) / 2

        etch = table.get_etch_tolerance(copper_weight)
        drill = table.get_drill_tolerance(hole_diameter)
        registration = table.get_registration(layer_type)

        # Worst case: hole larger, pad smaller, misregistered
        # Annular ring shrinks by: etch + drill/2 + registration
        total_shrink = etch + drill / 2 + registration

        return cls(
            feature_type="annular_ring",
            nominal_value=nominal_ring,
            tolerance_plus=0.0,  # Ring doesn't grow in worst case
            tolerance_minus=total_shrink,
            worst_case_min=max(0.0, nominal_ring - total_shrink),
            worst_case_max=nominal_ring,
        )


class ToleranceAnalyzer:
    """Analyzer for manufacturing tolerance effects on PCB features.

    Provides methods to analyze various PCB features and determine
    worst-case dimensions considering manufacturing tolerances.

    Example:
        >>> analyzer = ToleranceAnalyzer()
        >>> clearance = analyzer.analyze_clearance(0.2, CopperWeight.ONE_OZ, LayerType.OUTER)
        >>> print(f"Passes 0.15mm requirement: {clearance.meets_requirement(0.15)}")
        Passes 0.15mm requirement: False
    """

    def __init__(self, table: Optional[ToleranceTable] = None):
        """Initialize analyzer with tolerance table.

        Args:
            table: ToleranceTable to use. If None, uses default values.
        """
        self.table = table or ToleranceTable()

    def analyze_clearance(
        self,
        clearance_mm: float,
        copper_weight: CopperWeight,
        layer_type: LayerType,
    ) -> FeatureTolerance:
        """Analyze tolerance for a clearance between copper features.

        Considers:
        - Etch undercut from both sides (2x etch tolerance)
        - Layer registration if clearance crosses layers

        Args:
            clearance_mm: Nominal clearance in mm
            copper_weight: Copper weight of the layer
            layer_type: Type of layer (outer/inner)

        Returns:
            FeatureTolerance with worst-case (smaller) clearance
        """
        etch = self.table.get_etch_tolerance(copper_weight)
        registration = self.table.get_registration(layer_type)

        # Clearance shrinks by 2x etch + registration
        total_shrink = 2 * etch + registration

        return FeatureTolerance(
            feature_type="clearance",
            nominal_value=clearance_mm,
            tolerance_plus=0.0,
            tolerance_minus=total_shrink,
            worst_case_min=max(0.0, clearance_mm - total_shrink),
            worst_case_max=clearance_mm,
        )

    def analyze_trace_width(
        self,
        width_mm: float,
        copper_weight: CopperWeight,
    ) -> FeatureTolerance:
        """Analyze tolerance for trace width.

        Trace width can vary symmetrically due to etch variation.

        Args:
            width_mm: Nominal trace width in mm
            copper_weight: Copper weight of the layer

        Returns:
            FeatureTolerance with symmetric tolerance
        """
        return FeatureTolerance.from_trace_width(width_mm, copper_weight, self.table)

    def analyze_via(
        self,
        pad_diameter_mm: float,
        hole_diameter_mm: float,
        copper_weight: CopperWeight,
        layer_type: LayerType,
    ) -> FeatureTolerance:
        """Analyze tolerance for via annular ring.

        Args:
            pad_diameter_mm: Via pad diameter in mm
            hole_diameter_mm: Via hole diameter in mm
            copper_weight: Copper weight of the layer
            layer_type: Type of layer for registration

        Returns:
            FeatureTolerance for worst-case annular ring
        """
        return FeatureTolerance.from_via_annular_ring(
            pad_diameter_mm,
            hole_diameter_mm,
            copper_weight,
            layer_type,
            self.table,
        )

    def analyze_solder_mask_opening(
        self,
        pad_diameter_mm: float,
        mask_opening_mm: float,
    ) -> FeatureTolerance:
        """Analyze tolerance for solder mask opening.

        Solder mask registration affects the margin between
        mask opening and copper pad.

        Args:
            pad_diameter_mm: Copper pad diameter in mm
            mask_opening_mm: Solder mask opening diameter in mm

        Returns:
            FeatureTolerance for mask-to-pad margin
        """
        nominal_margin = (mask_opening_mm - pad_diameter_mm) / 2
        registration = self.table.solder_mask_registration

        return FeatureTolerance(
            feature_type="solder_mask_margin",
            nominal_value=nominal_margin,
            tolerance_plus=registration,
            tolerance_minus=registration,
            worst_case_min=max(0.0, nominal_margin - registration),
            worst_case_max=nominal_margin + registration,
        )

    def check_clearance_requirement(
        self,
        clearance_mm: float,
        required_mm: float,
        copper_weight: CopperWeight,
        layer_type: LayerType,
    ) -> tuple[bool, float]:
        """Check if a clearance meets requirement after tolerance.

        Args:
            clearance_mm: Nominal clearance in mm
            required_mm: Required minimum clearance in mm
            copper_weight: Copper weight of the layer
            layer_type: Type of layer

        Returns:
            Tuple of (passes, margin_mm) where margin is positive if passing
        """
        tolerance = self.analyze_clearance(clearance_mm, copper_weight, layer_type)
        passes = tolerance.meets_requirement(required_mm)
        margin = tolerance.margin_to_requirement(required_mm)
        return passes, margin
