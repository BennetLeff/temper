"""
Router V6 Stage 1.2: Classify Pads by Escape Need

Categorizes component pads based on escape routing requirements.
Part of temper-qvpt (Stage 1 - Pin Escape Planning)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.dense_package_detection import DensePackage


class EscapeClass(Enum):
    """Classification of pad escape requirements."""

    PERIPHERAL = "peripheral"  # Edge pads - can route directly
    INTERIOR = "interior"  # Inner pads - need escape vias
    THERMAL_PAD = "thermal_pad"  # Thermal/ground pad - special handling


@dataclass
class ClassifiedPad:
    """A component pad with escape classification."""

    pin: Pin
    component_ref: str
    escape_class: EscapeClass
    distance_to_edge_mm: float  # Distance from pad to component edge

    @property
    def needs_escape_via(self) -> bool:
        """True if this pad requires an escape via."""
        return self.escape_class == EscapeClass.INTERIOR


def classify_pads_by_escape_need(
    dense_packages: list[DensePackage],
    interior_threshold_mm: float = 1.0,
) -> list[ClassifiedPad]:
    """
    Classify component pads based on escape routing requirements.

    Pads are classified as:
    - PERIPHERAL: Edge pads that can route directly out
    - INTERIOR: Inner pads requiring escape vias (distance > threshold from edge)
    - THERMAL_PAD: Thermal/ground pads (typically center pad in QFN)

    Args:
        dense_packages: List of DensePackage instances from Stage 1.1
        interior_threshold_mm: Distance from edge to be considered interior (default 1.0mm)

    Returns:
        List of ClassifiedPad instances with escape classifications.

    Example:
        >>> comp = Component(ref="U1", footprint="QFN-48", bounds=(7, 7), pins=[...])
        >>> pkg = DensePackage(component=comp, pin_count=48, pitch_mm=0.5, ...)
        >>> classified = classify_pads_by_escape_need([pkg])
        >>> interior = [p for p in classified if p.needs_escape_via]
        >>> len(interior) > 0  # QFN has interior pads
        True
    """
    classified_pads = []

    for dense_pkg in dense_packages:
        comp = dense_pkg.component
        comp_width, comp_height = comp.bounds

        for pin in comp.pins:
            # Calculate distance to nearest edge
            pin_x, pin_y = pin.position
            
            # Distance to each edge
            dist_left = abs(pin_x)
            dist_right = abs(comp_width - pin_x)
            dist_bottom = abs(pin_y)
            dist_top = abs(comp_height - pin_y)
            
            # Minimum distance to any edge
            distance_to_edge = min(dist_left, dist_right, dist_bottom, dist_top)

            # Classify based on position and net
            if _is_thermal_pad(pin, comp):
                escape_class = EscapeClass.THERMAL_PAD
            elif distance_to_edge > interior_threshold_mm:
                escape_class = EscapeClass.INTERIOR
            else:
                escape_class = EscapeClass.PERIPHERAL

            classified_pads.append(
                ClassifiedPad(
                    pin=pin,
                    component_ref=comp.ref,
                    escape_class=escape_class,
                    distance_to_edge_mm=distance_to_edge,
                )
            )

    return classified_pads


def _is_thermal_pad(pin: Pin, comp: Component) -> bool:
    """
    Detect if a pin is a thermal/ground pad.

    Thermal pads are typically:
    - Named "PAD", "EPAD", "THERMAL", "GND", "EP"
    - In the center of the component
    - Larger than signal pads

    Args:
        pin: Pin instance
        comp: Component instance

    Returns:
        True if this is likely a thermal pad.
    """
    # Check pin name
    pin_name_upper = pin.name.upper()
    thermal_names = ["PAD", "EPAD", "THERMAL", "EP", "GND", "VSSA", "VSS"]
    
    if any(name in pin_name_upper for name in thermal_names):
        return True

    # Check if pin is in center of component
    comp_width, comp_height = comp.bounds
    pin_x, pin_y = pin.position
    
    center_x = comp_width / 2
    center_y = comp_height / 2
    
    # Distance from center
    dist_from_center = ((pin_x - center_x)**2 + (pin_y - center_y)**2)**0.5
    
    # If very close to center (< 10% of component size), likely thermal pad
    max_comp_dim = max(comp_width, comp_height)
    if dist_from_center < (max_comp_dim * 0.1):
        # Also check if it's larger than average pad
        avg_pad_area = sum(p.width * p.height for p in comp.pins) / len(comp.pins)
        this_pad_area = pin.width * pin.height
        
        if this_pad_area > avg_pad_area * 2:  # 2x larger than average
            return True

    return False
