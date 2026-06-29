import math
from dataclasses import dataclass


@dataclass
class PadInfo:
    position: tuple[float, float]
    radius: float
    mask_expansion: float

def distance(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def is_via_position_valid(
    pos: tuple[float, float],
    pads: list[PadInfo],
    via_mask_radius: float,
    min_clearance: float = 0.1
) -> bool:
    """Check if via at pos has sufficient mask clearance to all pads."""
    for pad in pads:
        pad_mask_radius = pad.radius + pad.mask_expansion
        required_distance = via_mask_radius + pad_mask_radius + min_clearance
        if distance(pos, pad.position) < required_distance:
            return False
    return True

def place_via_with_clearance(
    target_pos: tuple[float, float],
    pads: list[PadInfo],
    via_mask_radius: float,
    min_clearance: float = 0.1,
    max_search_radius: float = 2.0
) -> tuple[float, float] | None:
    """Find valid via position near target, respecting mask clearances."""

    # 1. Check if target position is already valid
    if is_via_position_valid(target_pos, pads, via_mask_radius, min_clearance):
        return target_pos

    # 2. Search in expanding spiral for valid position
    # Steps: 0.25mm increments up to max_search_radius
    # Directions: 8 angles (45 deg)
    for r in [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]:
        if r > max_search_radius:
            break
        for angle_deg in range(0, 360, 45):
            angle_rad = math.radians(angle_deg)
            candidate = (
                target_pos[0] + r * math.cos(angle_rad),
                target_pos[1] + r * math.sin(angle_rad)
            )
            if is_via_position_valid(candidate, pads, via_mask_radius, min_clearance):
                return candidate

    return None
