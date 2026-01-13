"""
Router V6 Feedback F.2: Identify Congested Regions

Analyzes routing results to identify congested regions.
Part of temper-jq8n (Feedback Loop & Co-Optimization)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from temper_placer.router_v6.routing_results import RoutingResults


class CongestionSeverity(Enum):
    """Congestion severity levels."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class CongestedRegion:
    """A congested region on the PCB."""

    center: tuple[float, float]  # Region center (x, y) in mm
    radius: float  # Region radius in mm
    severity: CongestionSeverity
    failed_net_count: int  # Number of failed nets in this region
    bottleneck_score: float  # 0.0-1.0, higher = worse congestion


@dataclass
class CongestionMap:
    """Map of congested regions across the PCB."""

    regions: list[CongestedRegion]

    @property
    def congested_region_count(self) -> int:
        """Number of congested regions."""
        return len(self.regions)

    @property
    def critical_region_count(self) -> int:
        """Number of critical congestion regions."""
        return sum(1 for r in self.regions if r.severity == CongestionSeverity.CRITICAL)

    def get_regions_by_severity(self, severity: CongestionSeverity) -> list[CongestedRegion]:
        """Get all regions with specified severity."""
        return [r for r in self.regions if r.severity == severity]


def identify_congested_regions(
    routing_results: RoutingResults,
    board_width: float,
    board_height: float,
    grid_size: float = 10.0,  # mm per grid cell
) -> CongestionMap:
    """
    Identify congested regions from routing results.

    Analyzes failed nets and routing density to identify areas
    that need placement adjustment or more routing resources.

    Args:
        routing_results: Routing results from Stage 4.9
        board_width: Board width (mm)
        board_height: Board height (mm)
        grid_size: Size of analysis grid cells (mm)

    Returns:
        CongestionMap with identified congested regions

    Example:
        >>> from temper_placer.router_v6.routing_results import RoutingResults
        >>> results = RoutingResults(compiled_routes={}, failed_nets=[])
        >>> congestion = identify_congested_regions(results, 100, 100)
        >>> congestion.congested_region_count >= 0
        True
    """
    # Create grid for congestion analysis
    grid_cells_x = int(board_width / grid_size) + 1
    grid_cells_y = int(board_height / grid_size) + 1

    # Initialize congestion grid
    congestion_grid = [[0.0 for _ in range(grid_cells_x)] for _ in range(grid_cells_y)]
    failed_net_grid = [[0 for _ in range(grid_cells_x)] for _ in range(grid_cells_y)]

    # Analyze failed nets
    for failed_net in routing_results.failed_nets:
        # Failed nets contribute to congestion
        # In practice, would use net pin locations
        # Simplified: assume center of board
        cx = int(board_width / 2 / grid_size)
        cy = int(board_height / 2 / grid_size)
        if 0 <= cx < grid_cells_x and 0 <= cy < grid_cells_y:
            failed_net_grid[cy][cx] += 1
            congestion_grid[cy][cx] += 0.5  # Failed net penalty

    # Analyze successful routes for density
    for net_name, compiled_route in routing_results.compiled_routes.items():
            # Extract coordinates (handle RoutePath and RoutePath3D)
            coords = []
            if hasattr(compiled_route.path, 'segments'):
                 coords = [c[:2] for c in compiled_route.path.segments]
            elif hasattr(compiled_route.path, 'coordinates'):
                 coords = compiled_route.path.coordinates
            
            for coord in coords:
                x, y = coord
                cell_x = int(x / grid_size)
                cell_y = int(y / grid_size)

                if 0 <= cell_x < grid_cells_x and 0 <= cell_y < grid_cells_y:
                    congestion_grid[cell_y][cell_x] += 0.1  # Route density contribution

    # Identify congested regions
    regions = []
    for y in range(grid_cells_y):
        for x in range(grid_cells_x):
            congestion = congestion_grid[y][x]
            failed_nets = failed_net_grid[y][x]

            # Only create region if significant congestion
            if congestion > 0.5 or failed_nets > 0:
                severity = _classify_congestion(congestion, failed_nets)

                # Convert grid coordinates to mm
                center_x = (x + 0.5) * grid_size
                center_y = (y + 0.5) * grid_size

                regions.append(CongestedRegion(
                    center=(center_x, center_y),
                    radius=grid_size / 2,
                    severity=severity,
                    failed_net_count=failed_nets,
                    bottleneck_score=min(1.0, congestion / 10.0),
                ))

    return CongestionMap(regions=regions)


def _classify_congestion(
    congestion_score: float,
    failed_net_count: int,
) -> CongestionSeverity:
    """
    Classify congestion severity.

    Args:
        congestion_score: Accumulated congestion score
        failed_net_count: Number of failed nets

    Returns:
        CongestionSeverity classification
    """
    # Failed nets are critical
    if failed_net_count >= 3:
        return CongestionSeverity.CRITICAL
    elif failed_net_count >= 1:
        return CongestionSeverity.HIGH

    # Based on congestion score
    if congestion_score > 5.0:
        return CongestionSeverity.HIGH
    elif congestion_score > 3.0:
        return CongestionSeverity.MEDIUM
    elif congestion_score > 1.0:
        return CongestionSeverity.LOW
    else:
        return CongestionSeverity.NONE
