"""
Force calculation for geometric nudging.

Calculates repulsive forces based on DRC violations.
"""

from dataclasses import dataclass
import math

from temper_placer.routing.constraints.drc_oracle import DRCOracle, Violation
from temper_placer.routing.constraints.geometry import Point, LineSegment


@dataclass
class ForceVector:
    fx: float
    fy: float
    magnitude: float

    @staticmethod
    def zero() -> "ForceVector":
        return ForceVector(0.0, 0.0, 0.0)

    def __add__(self, other: "ForceVector") -> "ForceVector":
        return ForceVector(
            self.fx + other.fx,
            self.fy + other.fy,
            self.magnitude + other.magnitude
        )



from temper_placer.routing.constraints.geometry import (
    closest_points_segment_segment,
    point_to_segment_distance,
    Point
)


from temper_placer.routing.constraints.spatial_index import Track, Via, Pad

def calculate_repulsive_force(
    violation: Violation,
    target_id: str,
    oracle: DRCOracle,
    stiffness: float = 1.0
) -> ForceVector:
    """Calculate repulsive force vector to resolve a violation.
    
    Args:
        violation: The DRC violation
        target_id: The ID of the object we want to move
        oracle: DRCOracle instance for geometry lookup
        stiffness: Spring stiffness coefficient
        
    Returns:
        ForceVector pushing the object away from the violation
    """
    # Force magnitude is proportional to violation depth
    violation_depth = violation.clearance_required - violation.clearance_actual
    if violation_depth <= 0:
        return ForceVector.zero()
        
    force_magnitude = stiffness * violation_depth
    
    # Identify "us" (target) and "them" (obstacle)
    if violation.geometry_a_id == target_id:
        my_id = violation.geometry_a_id
        other_id = violation.geometry_b_id
    elif violation.geometry_b_id == target_id:
        my_id = violation.geometry_b_id
        other_id = violation.geometry_a_id
    else:
        return ForceVector.zero()
        
    me = oracle.geometry.get_geometry_by_id(my_id)
    other = oracle.geometry.get_geometry_by_id(other_id)
    
    if not me or not other:
        return ForceVector.zero()
        
    # Calculate vector from "them" to "us"
    dx, dy = 0.0, 0.0
    
    # Case 1: Track-Track
    if isinstance(me, Track) and isinstance(other, Track):
        p_me, p_other = closest_points_segment_segment(me.to_segment(), other.to_segment())
        dx = p_me.x - p_other.x
        dy = p_me.y - p_other.y
        
    # Case 2: Via-Via
    elif isinstance(me, Via) and isinstance(other, Via):
        dx = me.center.x - other.center.x
        dy = me.center.y - other.center.y
        
    # Case 3: Track-Via / Via-Track / Track-Pad / Via-Pad
    # We treat "other" as a point-like or segment-like obstacle
    else:
        # Simplified: Use conflict location from violation as a proxy for "them"
        # But violation.location isn't precise enough for vector direction often.
        # Let's try to do better if possible.
        
        center_me = me.midpoint() if isinstance(me, Track) else me.center
        center_other = other.midpoint() if isinstance(other, Track) else other.center
        
        dx = center_me.x - center_other.x
        dy = center_me.y - center_other.y

    # Normalize and scale
    dist = math.sqrt(dx*dx + dy*dy)
    if dist < 1e-6:
        # Coincident? Push in random direction or X direction
        dx, dy = 1.0, 0.0
        dist = 1.0
        
    fx = (dx / dist) * force_magnitude
    fy = (dy / dist) * force_magnitude
    
    return ForceVector(fx, fy, force_magnitude)


def compute_forces(oracle: DRCOracle, geometry_ids: list[str]) -> dict[str, ForceVector]:
    """Compute independent net forces on a set of geometry items based on current violations."""
    forces = {gid: ForceVector.zero() for gid in geometry_ids}
    
    # Get all active violations
    # Note: validate_all() is O(N^2), might be slow for huge boards. 
    # But we run this iteratively.
    violations = oracle.validate_all()
    
    for v in violations:
        # Apply force to A if we are moving A
        if v.geometry_a_id in forces:
            f = calculate_repulsive_force(v, v.geometry_a_id, oracle)
            forces[v.geometry_a_id] = forces[v.geometry_a_id] + f
            
        # Apply force to B if we are moving B
        if v.geometry_b_id in forces:
            f = calculate_repulsive_force(v, v.geometry_b_id, oracle)
            forces[v.geometry_b_id] = forces[v.geometry_b_id] + f
            
    return forces
