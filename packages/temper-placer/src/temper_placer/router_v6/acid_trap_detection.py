"""
Router V6 Stage 5.1: Detect and Fix Acid Traps

Detects acute angles in traces that can trap etchant during manufacturing.
Part of temper-vm3g (Stage 5 - Manufacturing DRC)
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from temper_placer.router_v6.routing_results import RoutingResults


@dataclass
class AcidTrap:
    """An acid trap location in a trace."""

    net_name: str
    position: tuple[float, float]  # (x, y) of acute angle
    angle_degrees: float  # Angle at this vertex
    severity: str  # "low", "medium", "high"


@dataclass
class AcidTrapReport:
    """Report of all detected acid traps."""

    acid_traps: list[AcidTrap]
    
    @property
    def trap_count(self) -> int:
        """Total number of acid traps."""
        return len(self.acid_traps)
    
    @property
    def critical_count(self) -> int:
        """Number of critical acid traps (< 45°)."""
        return sum(1 for trap in self.acid_traps if trap.severity == "high")


def detect_acid_traps(
    routing_results: RoutingResults,
    min_angle_threshold: float = 90.0,
) -> AcidTrapReport:
    """
    Detect acid traps in routed traces.

    Acid traps are acute angles (< 90°) that can trap etchant
    during PCB manufacturing, leading to over-etching.

    Args:
        routing_results: Compiled routing results from Stage 4.9
        min_angle_threshold: Minimum acceptable angle (degrees)

    Returns:
        AcidTrapReport with all detected acid traps

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> report = detect_acid_traps(results)
        >>> report.trap_count >= 0
        True
    """
    acid_traps = []
    
    for net_name, compiled_route in routing_results.compiled_routes.items():
        # Analyze path for acute angles
        path_coords = compiled_route.path.coordinates
        
        if len(path_coords) < 3:
            # Need at least 3 points to form an angle
            continue
        
        # Check angles at each vertex
        for i in range(1, len(path_coords) - 1):
            prev_point = path_coords[i - 1]
            curr_point = path_coords[i]
            next_point = path_coords[i + 1]
            
            angle = _calculate_angle(prev_point, curr_point, next_point)
            
            if angle < min_angle_threshold:
                # This is an acid trap
                severity = _classify_severity(angle)
                
                acid_traps.append(AcidTrap(
                    net_name=net_name,
                    position=curr_point,
                    angle_degrees=angle,
                    severity=severity,
                ))
    
    return AcidTrapReport(acid_traps=acid_traps)


def _calculate_angle(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> float:
    """
    Calculate angle at p2 formed by p1-p2-p3.

    Args:
        p1: First point
        p2: Vertex point
        p3: Third point

    Returns:
        Angle in degrees (0-180)
    """
    # Vectors from p2 to p1 and p3
    v1 = (p1[0] - p2[0], p1[1] - p2[1])
    v2 = (p3[0] - p2[0], p3[1] - p2[1])
    
    # Calculate dot product and magnitudes
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
    mag2 = math.sqrt(v2[0]**2 + v2[1]**2)
    
    if mag1 == 0 or mag2 == 0:
        return 180.0  # Degenerate case
    
    # Calculate angle
    cos_angle = dot / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))  # Clamp to [-1, 1]
    
    angle_rad = math.acos(cos_angle)
    angle_deg = math.degrees(angle_rad)
    
    return angle_deg


def _classify_severity(angle: float) -> str:
    """
    Classify acid trap severity based on angle.

    Args:
        angle: Angle in degrees

    Returns:
        Severity: "low", "medium", or "high"
    """
    if angle < 45:
        return "high"  # Very acute - critical
    elif angle < 60:
        return "medium"  # Moderate concern
    else:
        return "low"  # Minor issue
