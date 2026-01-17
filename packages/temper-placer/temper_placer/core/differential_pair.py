"""
Differential pair routing constraints.

This module defines constraints for routing differential pairs (e.g., USB D+/D-)
to maintain coupling and controlled impedance.
"""

from dataclasses import dataclass


@dataclass
class DifferentialPairConstraint:
    """Constraint for differential pair routing.

    Defines requirements for routing a differential pair with maintained
    coupling and length matching.

    Attributes:
        net_pos: Positive net name (e.g., 'USB_D+')
        net_neg: Negative net name (e.g., 'USB_D-')
        spacing_mm: Nominal gap between traces in mm
        coupling_tolerance_mm: Maximum deviation from nominal spacing in mm
        impedance_ohm: Target differential impedance (optional)
        max_skew_mm: Maximum length mismatch for length matching in mm
    """

    net_pos: str
    net_neg: str
    spacing_mm: float = 0.2
    coupling_tolerance_mm: float = 0.5
    impedance_ohm: float | None = None
    max_skew_mm: float = 0.5

    def __post_init__(self):
        """Validate differential pair parameters."""
        if self.spacing_mm <= 0:
            raise ValueError(f"spacing_mm must be positive, got {self.spacing_mm}")
        if self.coupling_tolerance_mm < 0:
            raise ValueError(
                f"coupling_tolerance_mm must be non-negative, got {self.coupling_tolerance_mm}"
            )
        if self.max_skew_mm < 0:
            raise ValueError(f"max_skew_mm must be non-negative, got {self.max_skew_mm}")
        if self.impedance_ohm is not None and self.impedance_ohm <= 0:
            raise ValueError(
                f"impedance_ohm must be positive if specified, got {self.impedance_ohm}"
            )
