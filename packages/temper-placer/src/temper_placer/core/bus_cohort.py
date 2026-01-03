"""
Bus cohort routing constraints.

This module defines constraints for routing multi-signal buses (e.g., SPI, I2C, Parallel)
as a single cohort to maintain parallel paths and minimize crossings.
"""

from dataclasses import dataclass, field


@dataclass
class BusCohortConstraint:
    """Constraint for routing a bus cohort.

    Defines requirements for routing a group of nets in parallel with 
    consistent spacing.

    Attributes:
        name: Name of the bus (e.g., 'SPI_BUS')
        nets: List of net names in the cohort (ordered).
        pitch_mm: Center-to-center spacing between traces in mm.
        max_skew_mm: Maximum length mismatch within the cohort in mm.
        allow_swapping: Whether signal order can be swapped to optimize routing.
    """

    name: str
    nets: list[str]
    pitch_mm: float = 0.5
    max_skew_mm: float = 2.0
    allow_swapping: bool = False

    def __post_init__(self):
        """Validate bus cohort parameters."""
        if not self.nets:
            raise ValueError("Bus cohort must contain at least one net.")
        if self.pitch_mm <= 0:
            raise ValueError(f"pitch_mm must be positive, got {self.pitch_mm}")
        if self.max_skew_mm < 0:
            raise ValueError(f"max_skew_mm must be non-negative, got {self.max_skew_mm}")

    @property
    def signal_count(self) -> int:
        """Total number of signals in the bus."""
        return len(self.nets)
