"""
Data structures for router failure analysis and mapping to ILP cuts.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.router_v6.astar_pathfinding import RoutingFailureReport


@dataclass
class BlockingPair:
    """
    A pair of components that need more spacing to enable routing.
    
    Generated from routing failures - identifies which components
    are blocking a net from routing successfully.
    """
    
    component_a: str  # First component reference (e.g., "U1")
    component_b: str  # Second component reference (e.g., "R5")
    failed_net: str  # Net that failed to route
    current_spacing: float  # Current distance between components (mm)
    required_spacing: float  # Estimated required spacing (mm)
    confidence: float  # Confidence score [0.0-1.0] that this pair is the blocker
    reason: str  # Why we think this pair is blocking
    
    def __repr__(self) -> str:
        return (
            f"BlockingPair({self.component_a} ↔ {self.component_b}, "
            f"net={self.failed_net}, "
            f"current={self.current_spacing:.1f}mm, "
            f"need={self.required_spacing:.1f}mm, "
            f"confidence={self.confidence:.0%})"
        )


@dataclass
class SpatialFailureInfo:
    """
    Extended failure information with spatial data for mapping to components.
    
    Augments RoutingFailureReport with geometric information needed
    to identify blocking component pairs.
    """
    
    base_report: RoutingFailureReport
    
    # Spatial information
    failed_segment: tuple[str, str] | None = None  # (from_pad, to_pad) e.g., ("U1.5", "R3.1")
    blocking_region: tuple[float, float, float, float] | None = None  # (x1, y1, x2, y2)
    attempted_layers: list[str] | None = None  # Layers tried ["F.Cu", "B.Cu"]
    
    # Component proximity data
    nearby_components: list[tuple[str, float]] | None = None  # [(ref, distance), ...]
    
    @property
    def net_name(self) -> str:
        return self.base_report.net_name
    
    @property
    def failure_reason(self) -> str:
        return self.base_report.failure_reason
    
    @property
    def blocking_nets(self) -> list[str]:
        return self.base_report.blocking_nets
    
    def __repr__(self) -> str:
        region_str = "unknown"
        if self.blocking_region:
            x1, y1, x2, y2 = self.blocking_region
            region_str = f"({x1:.1f},{y1:.1f})-({x2:.1f},{y2:.1f})"
        
        return (
            f"SpatialFailureInfo({self.net_name}, "
            f"reason={self.failure_reason}, "
            f"region={region_str}, "
            f"blockers={len(self.blocking_nets)})"
        )
