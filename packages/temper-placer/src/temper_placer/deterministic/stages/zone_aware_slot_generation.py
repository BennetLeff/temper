"""
Zone-aware slot generation for the DeterministicPipeline.

Extends SlotGenerationStage to avoid placing components in areas
covered by copper zones (GND/VCC fill), which would block routing channels.
"""

from dataclasses import replace
from typing import List, Tuple, Optional
import logging

from ..state import BoardState
from .base import Stage
from .slot_generation import SlotGenerationStage

logger = logging.getLogger(__name__)

# Common power net names that indicate copper fill zones
POWER_NET_NAMES = {
    "GND",
    "PGND",
    "AGND",
    "DGND",
    "CGND",
    "SGND",
    "VCC",
    "VDD",
    "VSS",
    "VBUS",
    "VIN",
    "VOUT",
    "+3V3",
    "+3.3V",
    "3V3",
    "3.3V",
    "+5V",
    "5V",
    "+12V",
    "12V",
    "+15V",
    "15V",
    "+24V",
    "24V",
    "V+",
    "V-",
}


def _point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
    """
    Check if point (x, y) is inside polygon using ray casting algorithm.

    Args:
        x, y: Point coordinates
        polygon: List of (x, y) vertices

    Returns:
        True if point is inside polygon
    """
    if len(polygon) < 3:
        return False

    n = len(polygon)
    inside = False

    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    else:
                        xinters = x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside


def _get_copper_zones(board, yaml_zones: Optional[List] = None) -> List:
    """
    Extract copper zones from board and/or YAML configuration.

    Copper zones are different from placement zones - they are
    filled areas (GND plane, VCC plane) that block routing.

    Args:
        board: Board object with zones attribute
        yaml_zones: Optional list of zones from YAML config (supplements PCB zones)

    Returns:
        List of copper zone objects with polygon data
    """
    if board is None and not yaml_zones:
        return []

    copper_zones = []

    # Add YAML-defined zones first (if provided)
    if yaml_zones:
        copper_zones.extend(yaml_zones)
        logger.debug(f"Added {len(yaml_zones)} copper zones from YAML config")

    if board is None:
        return copper_zones

    # Option 1: board.copper_zones (explicit copper zone list)
    if hasattr(board, "copper_zones") and board.copper_zones:
        copper_zones.extend(board.copper_zones)
        logger.debug(f"Added {len(board.copper_zones)} from board.copper_zones")

    # Option 2: board.zones (may contain both placement and copper zones)
    if hasattr(board, "zones") and board.zones:
        for zone in board.zones:
            # Filter for copper zones (have net_classes like GND, VCC, etc.)
            if hasattr(zone, "net_classes") and zone.net_classes:
                # Check if any net class matches power nets
                for net_class in zone.net_classes:
                    if net_class.upper() in POWER_NET_NAMES:
                        copper_zones.append(zone)
                        logger.debug(
                            f"Found copper zone: {zone.name if hasattr(zone, 'name') else 'unnamed'} with net_classes={zone.net_classes}"
                        )
                        break
            # Fallback: check for polygon attribute (copper zones have fill polygons)
            elif hasattr(zone, "polygon") and zone.polygon:
                # Only add if not already added
                if zone not in copper_zones:
                    copper_zones.append(zone)
                    logger.debug(
                        f"Found copper zone with polygon: {zone.name if hasattr(zone, 'name') else 'unnamed'}"
                    )

    return copper_zones


class ZoneAwareSlotGenerationStage(SlotGenerationStage):
    """
    Slot generation that avoids copper zone coverage.

    Slots are not generated within copper fill zones (GND/VCC planes)
    to preserve routing channels and avoid congestion.

    Attributes:
        slot_spacing_mm: Spacing between slots in mm
        copper_zone_margin: Additional margin around copper zones (mm)
        min_routing_channel: Minimum gap required for routing (mm)
    """

    def __init__(
        self,
        slot_spacing_mm: float = 5.0,
        copper_zone_margin: float = 2.0,
        min_routing_channel: float = 3.0,
        yaml_copper_zones: Optional[List] = None,
    ):
        super().__init__(slot_spacing_mm=slot_spacing_mm)
        self.copper_zone_margin = copper_zone_margin
        self.min_routing_channel = min_routing_channel
        self.yaml_copper_zones = yaml_copper_zones or []

    @property
    def name(self) -> str:
        return "zone_aware_slot_generation"

    def run(self, state: BoardState) -> BoardState:
        """Generate slots, filtering out those covered by copper zones."""
        if not state.zones:
            return state

        # Get copper zones from board AND YAML config
        copper_zones = _get_copper_zones(state.board, self.yaml_copper_zones)

        if not copper_zones:
            # No copper zones - fall back to standard slot generation
            logger.info("No copper zones found, using standard slot generation")
            return super().run(state)

        logger.info(f"Found {len(copper_zones)} copper zones, filtering slots")

        # Log which zones apply to F.Cu (placement layer)
        fcu_zones = []
        other_zones = []
        for cz in copper_zones:
            zone_name = getattr(cz, "name", "unnamed")
            zone_layers = getattr(cz, "layers", None)
            if zone_layers:
                if isinstance(zone_layers, str):
                    zone_layers = [zone_layers]
                if "F.Cu" in zone_layers:
                    fcu_zones.append(zone_name)
                else:
                    other_zones.append(f"{zone_name}({zone_layers})")
            else:
                fcu_zones.append(f"{zone_name}(no layer)")

        if other_zones:
            logger.info(f"Skipping {len(other_zones)} copper zones not on F.Cu: {other_zones}")
        if fcu_zones:
            logger.info(f"Filtering slots for {len(fcu_zones)} F.Cu copper zones: {fcu_zones}")

        # Build list of (zone_name, tuple_of_slots) for storage
        zone_slots_list = []
        total_slots = 0
        filtered_slots = 0

        for zone in state.zones:
            all_slots = self._generate_slots_for_zone(zone, self.slot_spacing_mm)

            # Filter out slots covered by copper zones
            valid_slots = []
            for slot in all_slots:
                if not self._is_slot_in_copper_zone(slot, copper_zones):
                    valid_slots.append(slot)
                else:
                    filtered_slots += 1

            total_slots += len(all_slots)
            zone_slots_list.append((zone.name, tuple(valid_slots)))

        logger.info(
            f"Slot filtering: {filtered_slots}/{total_slots} slots removed "
            f"({100 * filtered_slots / max(1, total_slots):.1f}% in copper zones)"
        )

        return replace(state, zone_slots=frozenset(zone_slots_list))

    def _is_slot_in_copper_zone(
        self,
        slot: Tuple[float, float],
        copper_zones: List,
        placement_layer: str = "F.Cu",
    ) -> bool:
        """
        Check if a slot position falls within any copper zone on the placement layer.

        Args:
            slot: (x, y) position
            copper_zones: List of copper zone objects
            placement_layer: The layer where components are placed (default: "F.Cu")

        Returns:
            True if slot is covered by a copper zone on the same layer
        """
        x, y = slot

        for zone in copper_zones:
            # Skip zones that are not on the placement layer
            # Copper zones on internal/bottom layers don't block top-layer placement
            if hasattr(zone, "layers") and zone.layers:
                zone_layers = zone.layers
                # Handle both list and string formats
                if isinstance(zone_layers, str):
                    zone_layers = [zone_layers]
                # Skip if placement layer is not in zone's layers
                if placement_layer not in zone_layers:
                    continue

            # Check polygon containment
            if hasattr(zone, "polygon") and zone.polygon:
                if _point_in_polygon(x, y, zone.polygon):
                    return True

            # Check bounding box containment (fallback)
            elif hasattr(zone, "bounds") and zone.bounds:
                bounds = zone.bounds
                if len(bounds) == 4:
                    # (x_min, y_min, x_max, y_max) format
                    x_min, y_min, x_max, y_max = bounds
                elif len(bounds) == 2:
                    # ((x_min, y_min), (x_max, y_max)) format
                    (x_min, y_min), (x_max, y_max) = bounds
                else:
                    continue

                # Add margin
                x_min -= self.copper_zone_margin
                y_min -= self.copper_zone_margin
                x_max += self.copper_zone_margin
                y_max += self.copper_zone_margin

                if x_min <= x <= x_max and y_min <= y <= y_max:
                    return True

        return False


class RoutingChannelAwareSlotStage(ZoneAwareSlotGenerationStage):
    """
    Extended slot generation that also ensures routing channels remain open.

    In addition to avoiding copper zones, this stage ensures that slots
    are not placed in critical routing corridors between components.
    """

    def __init__(
        self,
        slot_spacing_mm: float = 5.0,
        copper_zone_margin: float = 2.0,
        min_routing_channel: float = 3.0,
        channel_density_threshold: float = 0.6,
    ):
        super().__init__(
            slot_spacing_mm=slot_spacing_mm,
            copper_zone_margin=copper_zone_margin,
            min_routing_channel=min_routing_channel,
        )
        self.channel_density_threshold = channel_density_threshold

    @property
    def name(self) -> str:
        return "routing_channel_aware_slot_generation"

    def _compute_slot_routing_cost(
        self,
        slot: Tuple[float, float],
        copper_zones: List,
        board_width: float,
        board_height: float,
    ) -> float:
        """
        Compute routing cost for a slot position.

        Higher cost = less desirable for placement due to routing impact.

        Factors:
        - Distance to copper zone boundaries (closer = more congested)
        - Distance to board edges (too close = no routing room)
        - Density of nearby slots (clustering = congestion)

        Args:
            slot: (x, y) position
            copper_zones: List of copper zones
            board_width, board_height: Board dimensions

        Returns:
            Cost value (0 = ideal, 1 = avoid)
        """
        x, y = slot
        cost = 0.0

        # Penalize positions near board edges
        edge_margin = self.min_routing_channel
        if x < edge_margin or x > board_width - edge_margin:
            cost += 0.3
        if y < edge_margin or y > board_height - edge_margin:
            cost += 0.3

        # Penalize positions near copper zone boundaries
        for zone in copper_zones:
            if hasattr(zone, "polygon") and zone.polygon:
                # Find minimum distance to zone boundary
                min_dist = self._min_distance_to_polygon(x, y, zone.polygon)
                if min_dist < self.min_routing_channel:
                    # Closer to boundary = higher cost
                    cost += 0.4 * (1 - min_dist / self.min_routing_channel)

        return min(1.0, cost)

    def _min_distance_to_polygon(
        self,
        x: float,
        y: float,
        polygon: List[Tuple[float, float]],
    ) -> float:
        """Compute minimum distance from point to polygon boundary."""
        if len(polygon) < 2:
            return float("inf")

        min_dist = float("inf")
        n = len(polygon)

        for i in range(n):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % n]

            # Distance to line segment
            dist = self._point_to_segment_distance(x, y, p1, p2)
            min_dist = min(min_dist, dist)

        return min_dist

    def _point_to_segment_distance(
        self,
        px: float,
        py: float,
        p1: Tuple[float, float],
        p2: Tuple[float, float],
    ) -> float:
        """Compute distance from point (px, py) to line segment p1-p2."""
        x1, y1 = p1
        x2, y2 = p2

        # Vector from p1 to p2
        dx = x2 - x1
        dy = y2 - y1

        # Length squared
        l2 = dx * dx + dy * dy

        if l2 == 0:
            # Segment is a point
            return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5

        # Project point onto line
        t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / l2))

        # Closest point on segment
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy

        return ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5
