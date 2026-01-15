"""
Channel capacity tracking for Router V6.

Tracks channel utilization during routing to enable precise failure diagnostics
for Benders decomposition cut generation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING


@dataclass
class ChannelState:
    """
    State of a routing channel during A* pathfinding.
    
    A channel is a routing region between components where traces can be placed.
    Tracking utilization allows precise failure diagnostics.
    """
    
    channel_id: str
    capacity: int  # Number of tracks that fit
    used: int  # Tracks currently routed
    nets_using: list[str]  # Which nets are using this channel
    bounding_components: tuple[str, str]  # Components defining channel width
    position: tuple[float, float]  # Center of channel (mm)
    width_mm: float  # Current channel width (mm)
    
    @property
    def available(self) -> int:
        """Number of tracks still available."""
        return max(0, self.capacity - self.used)
    
    @property
    def utilization(self) -> float:
        """Channel utilization as fraction (0.0-1.0)."""
        if self.capacity == 0:
            return 1.0  # Empty channel is "full"
        return min(1.0, self.used / self.capacity)
    
    @property
    def is_full(self) -> bool:
        """Check if channel is at capacity."""
        return self.used >= self.capacity
    
    @property
    def is_congested(self) -> bool:
        """Check if channel is >80% utilized."""
        return self.utilization > 0.8
    
    def __repr__(self) -> str:
        return (
            f"ChannelState({self.channel_id}, "
            f"{self.used}/{self.capacity} tracks, "
            f"{self.utilization:.0%} utilized)"
        )


def estimate_required_spacing(
    tracks_needed: int,
    tracks_available: int,
    trace_width_mm: float,
    clearance_mm: float,
    safety_margin: float = 1.5,
) -> float:
    """
    Estimate additional spacing needed to fit required tracks.
    
    Args:
        tracks_needed: Total tracks needed for routing
        tracks_available: Tracks currently available in channel
        trace_width_mm: Trace width (mm)
        clearance_mm: Clearance between traces (mm)
        safety_margin: Multiplier for safety (default 1.5 = 50% margin)
        
    Returns:
        Additional spacing needed (mm)
    """
    if tracks_needed <= tracks_available:
        return 0.0
    
    additional_tracks = tracks_needed - tracks_available
    track_pitch = trace_width_mm + clearance_mm
    
    return additional_tracks * track_pitch * safety_margin


def identify_blocking_components(
    failure_grid_pos: tuple[int, int],
    occupied_cells: dict[tuple[int, int], str],
    search_radius: int = 2,
) -> list[str]:
    """
    Identify components blocking routing at failure location.
    
    Args:
        failure_grid_pos: Grid coordinates where A* failed (x, y)
        occupied_cells: Map of grid_pos -> "Component.Pin"
        search_radius: How many cells to search around failure point
        
    Returns:
        List of component references blocking the path
    """
    fx, fy = failure_grid_pos
    blocking_components = set()
    
    # Search in radius around failure point
    for dx in range(-search_radius, search_radius + 1):
        for dy in range(-search_radius, search_radius + 1):
            cell = (fx + dx, fy + dy)
            if cell in occupied_cells:
                # Extract component reference from "Component.Pin"
                occupant = occupied_cells[cell]
                if '.' in occupant:
                    component = occupant.split('.')[0]
                    blocking_components.add(component)
    
    return sorted(blocking_components)


def compute_failure_confidence(
    channel_utilization: float | None,
    blocking_components_count: int,
    has_exact_location: bool,
    has_channel_data: bool,
) -> float:
    """
    Compute confidence score for failure diagnosis.
    
    Higher confidence means we have strong evidence about what's blocking.
    
    Args:
        channel_utilization: Channel utilization (0.0-1.0) or None
        blocking_components_count: Number of blocking components identified
        has_exact_location: Whether we have exact (x,y) of failure
        has_channel_data: Whether we have channel capacity data
        
    Returns:
        Confidence score (0.0-1.0)
    """
    confidence = 0.0
    
    # Channel data contributes most
    if has_channel_data and channel_utilization is not None:
        if channel_utilization >= 1.0:
            confidence += 0.5  # Channel definitely full
        elif channel_utilization >= 0.8:
            confidence += 0.3  # Channel congested
        else:
            confidence += 0.1  # Channel has space (weak evidence)
    
    # Blocking components identified
    if blocking_components_count > 0:
        confidence += min(0.3, blocking_components_count * 0.15)
    
    # Exact location helps
    if has_exact_location:
        confidence += 0.1
    
    # Cap at 0.95 (never 100% certain)
    return min(0.95, confidence)
