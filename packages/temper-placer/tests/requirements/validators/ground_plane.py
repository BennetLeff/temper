"""
Ground plane continuity validation functions.

These functions check if a PCB layout meets EMC/EMI ground plane requirements
per REQ-EMC-01.
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass
class GroundPlaneViolation:
    """A ground plane continuity violation."""

    code: str
    message: str
    location: Optional[Tuple[float, float]] = None
    severity: str = "error"  # error, warning


@dataclass
class GroundPlaneResult:
    """Result of ground plane validation."""

    passed: bool
    violations: List[GroundPlaneViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def check_slot_lengths(ground_plane_geometry, max_slot_mm: float = 30.0) -> GroundPlaneResult:
    """
    Check that no slots in ground plane exceed maximum length.

    Slots act as antennas at frequencies where slot length ≈ λ/2.
    For 150 MHz harmonics (λ = 2m), slots >10cm are problematic.
    Conservative limit: 30mm.

    Args:
        ground_plane_geometry: Ground plane geometry (slots, cutouts)
        max_slot_mm: Maximum allowed slot length

    Returns:
        GroundPlaneResult with violations
    """
    # TODO: Implement slot detection and measurement
    raise NotImplementedError("Slot length checking not yet implemented")


def check_signal_ground_reference(traces, ground_plane) -> GroundPlaneResult:
    """
    Verify each signal trace has solid ground return path.

    Critical for EMI - signals without ground reference radiate.

    Args:
        traces: Signal trace geometry
        ground_plane: Ground plane geometry

    Returns:
        GroundPlaneResult with violations for traces without ground reference
    """
    # TODO: Implement trace-to-ground reference checking
    raise NotImplementedError("Signal ground reference checking not yet implemented")


def check_star_ground_point(ground_domains) -> GroundPlaneResult:
    """
    Verify single connection point between PGND and CGND (star ground).

    Multiple connections create ground loops and EMI issues.

    Args:
        ground_domains: Ground domain definitions (PGND, CGND, ISOGND)

    Returns:
        GroundPlaneResult with violations if multiple connection points found
    """
    # TODO: Implement star ground verification
    raise NotImplementedError("Star ground checking not yet implemented")


def check_via_stitching(boundary_geometry, max_spacing_mm: float = 5.0) -> GroundPlaneResult:
    """
    Check via stitching along ground plane split boundaries.

    Via stitching connects L2 and L4 ground pours to minimize impedance.

    Args:
        boundary_geometry: Ground split boundary geometry
        max_spacing_mm: Maximum spacing between stitching vias

    Returns:
        GroundPlaneResult with violations for gaps exceeding max spacing
    """
    # TODO: Implement via stitching verification
    raise NotImplementedError("Via stitching checking not yet implemented")
