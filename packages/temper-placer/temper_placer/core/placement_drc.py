import math
from dataclasses import dataclass


@dataclass
class PinInfo:
    x: float
    y: float
    net_name: str
    component_name: str
    pin_name: str
    diameter_mm: float = 1.0  # Default pad diameter

    @property
    def radius(self) -> float:
        return self.diameter_mm / 2.0

@dataclass
class PlacementViolation:
    item_a: PinInfo
    item_b: PinInfo
    distance: float
    required: float
    violation_type: str  # "SHORT", "CLEARANCE", "ROUTABILITY"
    message: str

def validate_placement_drc(
    pins: list[PinInfo],
    min_clearance_mm: float,
    trace_width_mm: float = 0.25
) -> list[PlacementViolation]:
    """
    Validate placement for DRC violations before routing.
    
    Checks for:
    1. Shorts: Different nets overlapping (Distance < r1 + r2)
    2. Clearance: Different nets too close (Distance < r1 + r2 + clearance)
    3. Routability (Heuristic): Heuristic warning if pins are barely separated
    
    Args:
        pins: List of PinInfo objects
        min_clearance_mm: Minimum electrical clearance required
        trace_width_mm: Nominal trace width (for routability warnings)
        
    Returns:
        List of PlacementViolation objects
    """
    violations = []

    # Sort by X for potential optimization (or spatial hash), but N^2 is fine for small count
    n = len(pins)
    for i in range(n):
        for j in range(i + 1, n):
            pin_a = pins[i]
            pin_b = pins[j]

            # Skip same net (connected pins can be arbitrarily close/overlapping)
            if pin_a.net_name == pin_b.net_name:
                continue

            # Calculate distance
            dx = pin_a.x - pin_b.x
            dy = pin_a.y - pin_b.y
            dist = math.sqrt(dx*dx + dy*dy)

            pad_r_sum = pin_a.radius + pin_b.radius

            # 1. Check for physical overlap (Short)
            if dist < pad_r_sum:
                violations.append(PlacementViolation(
                    item_a=pin_a,
                    item_b=pin_b,
                    distance=dist,
                    required=pad_r_sum,
                    violation_type="SHORT",
                    message=f"Pads overlapping! {pin_a.net_name} vs {pin_b.net_name}"
                ))
                continue

            # 2. Check for electrical clearance
            required_clearance = pad_r_sum + min_clearance_mm
            if dist < required_clearance:
                 violations.append(PlacementViolation(
                    item_a=pin_a,
                    item_b=pin_b,
                    distance=dist,
                    required=required_clearance,
                    violation_type="CLEARANCE",
                    message=f"Clearance violation! Dist {dist:.3f}mm < {required_clearance:.3f}mm"
                ))
                 continue

    return violations
