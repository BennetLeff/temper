"""
Router V6 Feedback F.2: Identify Congested Regions

Analyzes routing results to identify congested regions.
Part of temper-jq8n (Feedback Loop & Co-Optimization)

Wave 4 Phase B: ``identify_congested_regions`` and ``_classify_congestion``
delegate to ``temper_geometry`` (``congestion_identify_regions_py`` /
``congestion_classify_severity_py``). The route-coordinate extraction
(``hasattr(path, "segments")`` vs ``"coordinates"``) stays Python -- the
kernel accepts already-extracted ``(x, y)`` lists, not a ``CompiledRoute``,
so that duck-typed dispatch has to happen on this side of the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import temper_geometry as _tg

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
    # Extract route coordinates (handle RoutePath and RoutePath3D) -- this
    # duck-typed dispatch is a Python-side seam; the kernel takes the
    # already-extracted (x, y) lists.
    routes: dict[str, list[tuple[float, float]]] = {}
    for net_name, compiled_route in routing_results.compiled_routes.items():
        coords: list[tuple[float, float]] = []
        if hasattr(compiled_route.path, "segments"):
            coords = [c[:2] for c in compiled_route.path.segments]
        elif hasattr(compiled_route.path, "coordinates"):
            coords = compiled_route.path.coordinates
        routes[net_name] = list(coords)

    region_rows = _tg.congestion_identify_regions_py(
        list(routing_results.failed_nets),
        routes,
        board_width,
        board_height,
        grid_size,
        False,
    )

    regions = [
        CongestedRegion(
            center=center,
            radius=radius,
            severity=CongestionSeverity(severity),
            failed_net_count=failed_net_count,
            bottleneck_score=bottleneck_score,
        )
        for (center, radius, severity, failed_net_count, bottleneck_score) in region_rows
    ]

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
    return CongestionSeverity(_tg.congestion_classify_severity_py(congestion_score, failed_net_count))
