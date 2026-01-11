"""
Router V6 Stage 1.1: Identify Dense Packages

Identifies high-pin-count components requiring escape routing strategies.
Part of temper-wpwf (Stage 1 - Pin Escape Planning)
"""

from __future__ import annotations

from dataclasses import dataclass

from temper_placer.core.netlist import Component


@dataclass
class DensePackage:
    """A high-pin-count component requiring escape routing."""

    component: Component
    pin_count: int
    pitch_mm: float  # Pin-to-pin spacing
    package_type: str  # "QFN", "BGA", "TQFP", "SOIC", etc.
    requires_escape: bool  # True if pitch < 0.5mm (dense)

    @property
    def is_bga(self) -> bool:
        """True if this is a BGA (Ball Grid Array) package."""
        return "BGA" in self.package_type.upper()

    @property
    def is_qfn(self) -> bool:
        """True if this is a QFN (Quad Flat No-lead) package."""
        return "QFN" in self.package_type.upper()


def identify_dense_packages(
    components: list[Component],
    dense_threshold_mm: float = 0.5,
    min_pin_count: int = 16,
) -> list[DensePackage]:
    """
    Identify components requiring escape routing strategies.

    A package is considered "dense" if:
    - Pin pitch < threshold (default 0.5mm = fine pitch)
    - Pin count >= min_pin_count (default 16 pins)

    Args:
        components: List of Component instances from ParsedPCB
        dense_threshold_mm: Maximum pitch considered "dense" (default 0.5mm)
        min_pin_count: Minimum pins to be considered (default 16)

    Returns:
        List of DensePackage instances requiring escape planning.

    Example:
        >>> comp = Component(ref="U1", footprint="QFN-48_0.5mm", bounds=(7, 7), pins=[...])
        >>> dense = identify_dense_packages([comp])
        >>> dense[0].requires_escape
        True
    """
    dense_packages = []

    for comp in components:
        # Skip components with too few pins
        pin_count = len(comp.pins)
        if pin_count < min_pin_count:
            continue

        # Estimate pitch from footprint name or calculate from geometry
        pitch_mm = _estimate_pitch(comp)
        
        # Infer package type from footprint name
        package_type = _infer_package_type(comp)

        # Determine if escape routing is required
        requires_escape = pitch_mm <= dense_threshold_mm or package_type in ["BGA", "FBGA", "LFBGA"]

        dense_packages.append(
            DensePackage(
                component=comp,
                pin_count=pin_count,
                pitch_mm=pitch_mm,
                package_type=package_type,
                requires_escape=requires_escape,
            )
        )

    return dense_packages


def _estimate_pitch(comp: Component) -> float:
    """
    Estimate pin pitch from footprint name or pin positions.

    Tries in order:
    1. Parse from footprint name (e.g., "QFN-48_0.5mm" -> 0.5mm)
    2. Calculate from actual pin positions

    Args:
        comp: Component instance

    Returns:
        Estimated pitch in mm (default 0.65mm if unknown)
    """
    import re

    # Try to parse pitch from footprint name
    # Common patterns: QFN-48_0.5mm, TQFP-100_0.4mm, BGA-256_0.8mm
    footprint_upper = comp.footprint.upper()
    
    # Pattern: _0.5MM or _0.5
    match = re.search(r'[_-](\d+\.?\d*)\s*MM', footprint_upper)
    if match:
        return float(match.group(1))
    
    match = re.search(r'[_P](\d+\.?\d*)(?:[_-]|$)', comp.footprint)
    if match:
        pitch_str = match.group(1)
        try:
            pitch = float(pitch_str)
            # If it's > 10, it's probably in mil (e.g., _50 = 50mil = 1.27mm)
            if pitch > 10:
                pitch = pitch * 0.0254  # mil to mm
            return pitch
        except ValueError:
            pass

    # Fallback: Calculate from pin positions
    if len(comp.pins) >= 4:
        # Find minimum distance between adjacent pins
        pin_positions = [p.position for p in comp.pins]
        min_dist = float('inf')
        
        for i, (x1, y1) in enumerate(pin_positions):
            for j, (x2, y2) in enumerate(pin_positions):
                if i >= j:
                    continue
                dist = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
                if dist > 0.01:  # Ignore near-zero distances (same pin)
                    min_dist = min(min_dist, dist)
        
        if min_dist != float('inf'):
            return min_dist

    # Default: 0.65mm (common SOIC/TQFP pitch)
    return 0.65


def _infer_package_type(comp: Component) -> str:
    """
    Infer package type from footprint name.

    Args:
        comp: Component instance

    Returns:
        Package type string ("QFN", "BGA", "TQFP", "SOIC", etc.)
    """
    footprint_upper = comp.footprint.upper()

    # Check for common package types
    package_types = [
        "BGA", "FBGA", "LFBGA", "TFBGA",  # Ball grid arrays
        "QFN", "DFN", "SON",  # Quad flat no-lead
        "TQFP", "LQFP", "QFP",  # Quad flat packages
        "SOIC", "SOP", "SSOP", "TSSOP",  # Small outline
        "TO-", "SOT-",  # Transistor outlines
    ]

    for pkg_type in package_types:
        if pkg_type in footprint_upper:
            # Return the base type (e.g., "BGA" not "FBGA")
            if "BGA" in pkg_type:
                return "BGA"
            elif "QFN" in pkg_type or "DFN" in pkg_type or "SON" in pkg_type:
                return "QFN"
            elif "QFP" in pkg_type:
                return "TQFP"
            elif "SOIC" in pkg_type or "SOP" in pkg_type:
                return "SOIC"
            elif "TO-" in pkg_type or "SOT-" in pkg_type:
                return "SOT"
            return pkg_type

    # Default: Unknown
    return "UNKNOWN"
