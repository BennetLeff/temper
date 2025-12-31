"""
Pin Ring Classifier for Escape Routing.

Classifies pins in a component footprint into concentric rings based on their
position relative to the component center. This enables the escape generator to
apply ring-specific strategies:
- Outer ring: Direct surface escape
- Inner rings: Via fanout (dog-bone)
- Center: Typically power/ground (no escape needed)
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple
import math


class PinRing(Enum):
    """Pin ring classification for BGA/QFN packages."""
    OUTER = 0      # Perimeter pins - direct escape on surface
    RING_2 = 1     # Second ring - short via fanout
    RING_3 = 2     # Third ring - longer via fanout  
    RING_4 = 3     # Fourth ring - complex fanout
    CENTER = 4     # Center pins - typically GND/VCC (no routing)


@dataclass
class PinClassification:
    """Result of classifying a single pin."""
    pin_name: str
    ring: PinRing
    distance_from_center: float  # mm
    angle: float  # radians, 0 = East, π/2 = North
    escape_direction: Tuple[float, float]  # Unit vector (dx, dy)


def classify_pin_rings(
    pin_positions: List[Tuple[str, float, float]],
    component_center: Tuple[float, float] = (0.0, 0.0),
    ring_thresholds: List[float] | None = None,
) -> List[PinClassification]:
    """Classify pins into concentric rings.
    
    Args:
        pin_positions: List of (pin_name, x, y) tuples in component-relative coords
        component_center: Center of component (default 0,0 for relative coords)
        ring_thresholds: Distance thresholds in mm. Default uses IPC-7095 guidelines:
                        [outer_boundary, ring2, ring3, center_boundary]
                        Default: [component_size * 0.45, 0.35, 0.25, 0.15]
                        
    Returns:
        List of PinClassification objects
        
    Example:
        >>> pins = [
        ...     ("A1", 7.5, 7.5),    # Outer corner
        ...     ("B2", 5.0, 5.0),    # Inner ring
        ...     ("C3", 0.0, 0.0),    # Center
        ... ]
        >>> results = classify_pin_rings(pins)
        >>> results[0].ring
        PinRing.OUTER
    """
    if not pin_positions:
        return []
    
    cx, cy = component_center
    
    # Compute distances for all pins
    pin_data = []
    for pin_name, px, py in pin_positions:
        dx = px - cx
        dy = py - cy
        distance = math.sqrt(dx**2 + dy**2)
        angle = math.atan2(dy, dx)  # Angle from center
        pin_data.append((pin_name, px, py, distance, angle, dx, dy))
    
    # Auto-compute ring thresholds if not provided
    if ring_thresholds is None:
        # Find component bounding box
        xs = [p[1] for p in pin_positions]
        ys = [p[2] for p in pin_positions]
        component_size = max(max(xs) - min(xs), max(ys) - min(ys))
        
        # IPC-7095 guidelines: outer 45%, ring2 35%, ring3 25%, center 15%
        max_dist = component_size / 2
        ring_thresholds = [
            max_dist * 0.85,  # Outer: >85% of max radius
            max_dist * 0.65,  # Ring 2: 65-85%
            max_dist * 0.40,  # Ring 3: 40-65%
            max_dist * 0.15,  # Center: <15%
        ]
    
    # Classify each pin
    results = []
    for pin_name, px, py, distance, angle, dx, dy in pin_data:
        # Determine ring
        if distance >= ring_thresholds[0]:
            ring = PinRing.OUTER
        elif distance >= ring_thresholds[1]:
            ring = PinRing.RING_2
        elif distance >= ring_thresholds[2]:
            ring = PinRing.RING_3
        elif distance >= ring_thresholds[3]:
            ring = PinRing.RING_4
        else:
            ring = PinRing.CENTER
        
        # Compute escape direction (unit vector away from center)
        if distance > 1e-6:  # Avoid division by zero
            escape_x = dx / distance
            escape_y = dy / distance
        else:
            # Pin at exact center - arbitrary direction
            escape_x, escape_y = 1.0, 0.0
        
        results.append(PinClassification(
            pin_name=pin_name,
            ring=ring,
            distance_from_center=distance,
            angle=angle,
            escape_direction=(escape_x, escape_y),
        ))
    
    return results


def get_ring_strategy(ring: PinRing) -> str:
    """Get recommended escape strategy for a ring.
    
    Returns:
        String describing the escape strategy
    """
    strategies = {
        PinRing.OUTER: "direct_surface",    # Route on surface layer, no via
        PinRing.RING_2: "short_fanout",     # Via at 1-2mm offset
        PinRing.RING_3: "medium_fanout",    # Via at 2-3mm offset
        PinRing.RING_4: "long_fanout",      # Via at 3-4mm offset
        PinRing.CENTER: "plane_connect",    # Typically GND/VCC, no routing
    }
    return strategies[ring]
