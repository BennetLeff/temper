"""
Design rules parsing and clearance matrix for DRC.

Extends core.design_rules with KiCad PCB parsing and clearance matrix
for net-class-aware constraint checking.

Part of temper-lueu.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from shapely.geometry import MultiPoint, Point, Polygon
from shapely.strtree import STRtree

from temper_placer.core.design_rules import (
    NetClassRules,
    create_temper_design_rules,
)

if TYPE_CHECKING:
    from kiutils.board import Board


@dataclass
class RoutingZone:
    """A polygon region on the board with its own routing rules.

    Attributes:
        name: Unique name for the zone (e.g., "HV", "Signal")
        polygon: List of (x, y) vertices in mm
        clearance_mm: Default clearance enforced within this zone
        allowed_net_classes: Set of net classes allowed to route here
        layer_restrictions: Optional list of allowed layer names
    """

    name: str
    polygon: list[tuple[float, float]]
    clearance_mm: float
    allowed_net_classes: set[str]
    layer_restrictions: list[str] | None = None


class ZoneManager:
    """Manages routing zones and provides fast spatial lookups.

    Uses an R-tree (via shapely STRtree) for O(log n) point-in-zone queries.
    """

    def __init__(self, zones: list[RoutingZone]):
        self.zones = zones
        self._polygons = [Polygon(z.polygon) for z in zones]
        self._tree = STRtree(self._polygons)

    def get_zone_at(self, x: float, y: float) -> RoutingZone | None:
        """Return the zone containing this point, or None if unzoned.

        Args:
            x, y: Board coordinates in mm

        Returns:
            RoutingZone containing the point, or None
        """
        point = Point(x, y)
        # Query tree for polygons whose bounding box intersects the point
        possible_indices = self._tree.query(point)

        # Check actual containment (STRtree query is based on envelopes)
        # Note: query returns a scalar if one result, or array if multiple in some versions.
        # Shapely 2.0 query(point) returns an array of indices.
        if isinstance(possible_indices, np.ndarray):
            for idx in possible_indices:
                if self._polygons[idx].contains(point):
                    return self.zones[idx]
        elif possible_indices is not None:
            # Older shapely or single result
            idx = int(possible_indices)
            if self._polygons[idx].contains(point):
                return self.zones[idx]

        return None

    def get_clearance(
        self, x: float, y: float, net_a: str, net_b: str, matrix: ClearanceMatrix
    ) -> float:
        """Return clearance requirement at this location for these nets.

        Args:
            x, y: Board coordinates in mm
            net_a, net_b: Net names
            matrix: Global clearance matrix for baseline rules

        Returns:
            Required clearance in mm
        """
        zone = self.get_zone_at(x, y)
        base_clearance = matrix.get_clearance(net_a, net_b)

        if zone:
            # Zone rules override if they are stricter
            return max(base_clearance, zone.clearance_mm)

        return base_clearance

    def can_route_net_at(self, x: float, y: float, net: str, matrix: ClearanceMatrix) -> bool:
        """Check if this net is allowed in the zone at this location.

        Args:
            x, y: Board coordinates in mm
            net: Net name
            matrix: Global clearance matrix for net-class lookup

        Returns:
            True if routing is allowed
        """
        zone = self.get_zone_at(x, y)
        if not zone:
            return True  # Unzoned areas allow everything

        net_class = matrix._net_to_class.get(net, "Default")
        return net_class in zone.allowed_net_classes


@dataclass
class ClearanceMatrix:
    """Net-class-aware clearance lookup table.

    Provides O(1) clearance lookups between any two net classes.
    Falls back to default clearance for unknown net classes.
    Supports optional RoutingZones for spatial overrides.
    Handles differential pairs with reduced clearance requirements.
    """

    # Clearance between net classes: (class_a, class_b) -> clearance_mm
    _clearances: dict[tuple[str, str], float] = field(default_factory=dict)
    default_clearance: float = 0.2  # mm
    default_track_width: float = 0.2  # mm
    default_via_diameter: float = 0.6  # mm
    default_via_drill: float = 0.3  # mm

    # Per-net-class rules
    _net_class_rules: dict[str, NetClassRules] = field(default_factory=dict)

    # Net to net-class mapping
    _net_to_class: dict[str, str] = field(default_factory=dict)

    # Optional spatial zone manager
    zone_manager: ZoneManager | None = None

    # Differential pairs: maps frozenset({net_a, net_b}) -> configured_spacing_mm
    # For diff pairs, this spacing is the required center-to-center distance
    _differential_pairs: dict[frozenset, float] = field(default_factory=dict)

    def is_differential_pair(self, net_a: str, net_b: str) -> bool:
        """Check if two nets are a registered differential pair.

        Args:
            net_a: First net name
            net_b: Second net name

        Returns:
            True if the nets are a registered differential pair
        """
        return frozenset([net_a, net_b]) in self._differential_pairs

    def get_clearance(
        self, net_a: str, net_b: str, x: float | None = None, y: float | None = None
    ) -> float:
        """Get required clearance between two nets.

        Args:
            net_a: First net name
            net_b: Second net name
            x, y: Optional board coordinates for spatial overrides

        Returns:
            Required clearance in mm (center-to-center for diff pairs, edge-to-edge otherwise)
        """
        # 0. Check if this is a differential pair - if so, return configured spacing
        # Differential pairs have relaxed clearance requirements (intentionally routed close)
        pair_key = frozenset([net_a, net_b])
        if pair_key in self._differential_pairs:
            return self._differential_pairs[pair_key]

        # 1. Start with class-based baseline
        base_clearance = self._get_base_clearance(net_a, net_b)

        # 2. Apply spatial override if coordinates and zone manager are provided
        if x is not None and y is not None and self.zone_manager:
            zone = self.zone_manager.get_zone_at(x, y)
            if zone:
                # Only apply zone clearance if at least one net is of a hazard class
                # for this zone. E.g., HV zone clearance only applies when routing
                # near HV nets, not for signal-to-signal routing that happens to
                # pass through the HV region.
                class_a = self._net_to_class.get(net_a, "Default")
                class_b = self._net_to_class.get(net_b, "Default")

                # Check if either net requires this zone's clearance
                # HV zone applies to HighVoltage nets
                # Signal zone doesn't need special handling (uses base clearance)
                zone_applies = False
                if zone.name == "HV":
                    zone_applies = class_a == "HighVoltage" or class_b == "HighVoltage"

                if zone_applies:
                    return max(base_clearance, zone.clearance_mm)

        return base_clearance

    def _get_base_clearance(self, net_a: str, net_b: str) -> float:
        """Baseline class-to-class clearance without spatial overrides."""
        class_a = self._net_to_class.get(net_a, "Default")
        class_b = self._net_to_class.get(net_b, "Default")

        # Try both orderings (matrix is symmetric)
        key1 = (class_a, class_b)
        key2 = (class_b, class_a)

        if key1 in self._clearances:
            return self._clearances[key1]
        if key2 in self._clearances:
            return self._clearances[key2]

        # Fall back to max of individual class clearances
        clear_a = self._get_class_clearance(class_a)
        clear_b = self._get_class_clearance(class_b)
        return max(clear_a, clear_b)

    def can_route_at(self, net: str, x: float, y: float) -> bool:
        """Check if a net is allowed to route at this spatial location.

        Args:
            net: Net name
            x, y: Board coordinates in mm

        Returns:
            True if routing is allowed
        """
        if not self.zone_manager:
            return True

        return self.zone_manager.can_route_net_at(x, y, net, self)

    def get_track_width(self, net: str) -> float:
        """Get required track width for a net.

        Args:
            net: Net name

        Returns:
            Track width in mm
        """
        net_class = self._net_to_class.get(net, "Default")
        if net_class in self._net_class_rules:
            return self._net_class_rules[net_class].trace_width
        return self.default_track_width

    def get_via_diameter(self, net: str) -> float:
        """Get via diameter for a net.

        Args:
            net: Net name

        Returns:
            Via pad diameter in mm
        """
        net_class = self._net_to_class.get(net, "Default")
        if net_class in self._net_class_rules:
            return self._net_class_rules[net_class].via_diameter
        return self.default_via_diameter

    def get_via_drill(self, net: str) -> float:
        """Get via drill diameter for a net.

        Args:
            net: Net name

        Returns:
            Via drill diameter in mm
        """
        net_class = self._net_to_class.get(net, "Default")
        if net_class in self._net_class_rules:
            return self._net_class_rules[net_class].via_drill
        return self.default_via_drill

    def _get_class_clearance(self, net_class: str) -> float:
        """Get clearance for a specific net class."""
        if net_class in self._net_class_rules:
            return self._net_class_rules[net_class].clearance
        return self.default_clearance

    def set_net_class(self, net: str, net_class: str) -> None:
        """Assign a net to a net class.

        Args:
            net: Net name
            net_class: Net class name
        """
        self._net_to_class[net] = net_class

    def add_net_class_rules(self, rules: NetClassRules) -> None:
        """Add rules for a net class.

        Args:
            rules: Net class rules
        """
        self._net_class_rules[rules.name] = rules

    def add_differential_pair(self, net_a: str, net_b: str, spacing_mm: float) -> None:
        """Register a differential pair with its configured center-to-center spacing.

        Differential pairs are intentionally routed close together for signal integrity.
        This method tells the DRC system that these two nets should use the configured
        spacing instead of standard clearance rules.

        The DRC system validates clearance as:
            actual_gap >= required + (width_a/2) + (width_b/2)

        For a differential pair with center-to-center spacing S and track width W:
            edge_to_edge = S - W/2 - W/2 = S - W
            We want: edge_to_edge >= required + W/2 + W/2
            So: S - W >= required + W
            Therefore: required = S - 2W

        Args:
            net_a: First net in the differential pair (e.g., 'USB_D+')
            net_b: Second net in the differential pair (e.g., 'USB_D-')
            spacing_mm: Required center-to-center spacing in mm

        Example:
            # USB diff pair: 0.25mm center-to-center, 0.15mm track width
            # Edge-to-edge: 0.25 - 0.15 = 0.10mm
            # Required: 0.25 - 2*0.15 = -0.05mm (DRC adds 0.15mm back)
            matrix.add_differential_pair('USB_D+', 'USB_D-', 0.25)
        """
        # Get track width for the differential pair nets (assume both have same width)
        track_width = self.get_track_width(net_a)

        # Calculate required clearance value that DRC system expects
        # DRC will add track widths back, so we subtract them here
        required_clearance = spacing_mm - (2 * track_width)

        pair_key = frozenset([net_a, net_b])
        self._differential_pairs[pair_key] = required_clearance

        pair_key = frozenset([net_a, net_b])
        self._differential_pairs[pair_key] = required_clearance

    def set_class_to_class_clearance(self, class_a: str, class_b: str, clearance: float) -> None:
        """Set clearance between two net classes.

        Args:
            class_a: First net class
            class_b: Second net class
            clearance: Required clearance in mm
        """
        self._clearances[(class_a, class_b)] = clearance
        self._clearances[(class_b, class_a)] = clearance

    @classmethod
    def parse(cls, board) -> ClearanceMatrix:
        """Parse ClearanceMatrix from a KiCad board or Board object.

        This is the primary entry point for creating a ClearanceMatrix from
        board data. It delegates to DesignRulesParser for the actual parsing.

        Args:
            board: Either a kiutils.board.Board object (KiCad native) or a
                  temper_placer.core.board.Board object (our internal format).
                  For our internal Board, returns default rules (zones are
                  managed separately).

        Returns:
            ClearanceMatrix with parsed rules and optional zone manager

        Example:
            from temper_placer.io.kicad_parser import parse_kicad_pcb
            board = parse_kicad_pcb("path/to/board.kicad_pcb")
            matrix = ClearanceMatrix.parse(board)
        """
        # Check if this is a kiutils Board (has netClasses attribute)
        if hasattr(board, "netClasses"):
            # KiCad native board - use full parser
            return DesignRulesParser.parse(board)

        # Otherwise, it's our internal Board
        matrix = DesignRulesParser.create_default()

        # Extract zones if present (temper-d6kv.4)
        if hasattr(board, "zones") and board.zones:
            from temper_placer.router_v6.constraints_design_rules import RoutingZone, ZoneManager

            routing_zones = []
            for z in board.zones:
                # Use polygon if available, otherwise use bounds
                poly = z.polygon
                if not poly and hasattr(z, "bounds"):
                    poly = [
                        (z.bounds[0], z.bounds[1]),
                        (z.bounds[2], z.bounds[1]),
                        (z.bounds[2], z.bounds[3]),
                        (z.bounds[0], z.bounds[3]),
                    ]

                if poly:
                    clearance = 0.2
                    if "HV" in z.name.upper():
                        clearance = 3.0  # Standard HV clearance for Temper

                    routing_zones.append(
                        RoutingZone(
                            name=z.name,
                            polygon=poly,
                            clearance_mm=clearance,
                            allowed_net_classes=set(z.net_classes) if z.net_classes else {"Signal"},
                        )
                    )

            if routing_zones:
                matrix.zone_manager = ZoneManager(routing_zones)

        return matrix


class DesignRulesParser:
    """Extract design rules from KiCad PCB file.

    Uses kiutils to parse .kicad_pcb files and extract:
    - Net class definitions
    - Clearance rules
    - Track width constraints
    - Via specifications
    """

    @staticmethod
    def parse(pcb: Board) -> ClearanceMatrix:
        """Parse design rules from a KiCad board.

        Args:
            pcb: kiutils Board object

        Returns:
            ClearanceMatrix with parsed rules
        """
        matrix = ClearanceMatrix()

        # Start with Temper defaults
        temper_rules = create_temper_design_rules()
        for _name, rules in temper_rules.net_classes.items():
            matrix.add_net_class_rules(rules)

        # Extract setup rules from board
        if pcb.setup is not None:
            # Default clearance from board setup
            # kiutils stores this in stackup or design rules section
            pass

        # Parse net classes from board
        if hasattr(pcb, "netClasses") and pcb.netClasses:
            for nc in pcb.netClasses:
                rules = NetClassRules(
                    name=nc.name,
                    trace_width=nc.traceWidth if hasattr(nc, "traceWidth") else 0.2,
                    clearance=nc.clearance if hasattr(nc, "clearance") else 0.2,
                    via_diameter=nc.viaDia if hasattr(nc, "viaDia") else 0.6,
                    via_drill=nc.viaDrill if hasattr(nc, "viaDrill") else 0.3,
                    dru_priority=getattr(nc, "druPriority", 0),
                )
                matrix.add_net_class_rules(rules)

                # Map nets to this class
                if hasattr(nc, "nets"):
                    for net_name in nc.nets:
                        matrix.set_net_class(net_name, nc.name)

        # Parse nets from board to auto-classify
        if hasattr(pcb, "nets") and pcb.nets:
            for net in pcb.nets:
                net_name = net.name if hasattr(net, "name") else str(net)
                if net_name not in matrix._net_to_class:
                    # Auto-classify based on name patterns
                    class_name = DesignRulesParser._classify_net(net_name)
                    matrix.set_net_class(net_name, class_name)

        return matrix

    @staticmethod
    def parse_from_file(pcb_path: str) -> ClearanceMatrix:
        """Parse design rules from a KiCad PCB file path.

        Args:
            pcb_path: Path to .kicad_pcb file

        Returns:
            ClearanceMatrix with parsed rules
        """
        from kiutils.board import Board

        pcb = Board.from_file(pcb_path)
        return DesignRulesParser.parse(pcb)

    @staticmethod
    def _classify_net(net_name: str) -> str:
        """Auto-classify net based on name patterns.

        Args:
            net_name: Net name to classify

        Returns:
            Net class name
        """
        from temper_placer.core.net_classification import (
            is_ground_net,
            is_power_net,
        )

        if is_ground_net(net_name):
            return "GND"
        if is_power_net(net_name):
            return "Power"

        # High-speed patterns
        high_speed_patterns = ["CLK", "CLOCK", "SPI_", "I2C_", "USB", "JTAG"]
        for pattern in high_speed_patterns:
            if pattern in net_name.upper():
                return "HighSpeed"

        return "Signal"

    @staticmethod
    def infer_zones(pcb: Board, matrix: ClearanceMatrix) -> list[RoutingZone]:
        """Infer routing zones from board components and net classes.

        Args:
            pcb: kiutils Board object
            matrix: ClearanceMatrix for net-class lookup

        Returns:
            List of RoutingZone objects
        """
        # 1. Identify HV and Signal Components
        hv_points = []
        signal_points = []

        for fp in pcb.footprints:
            is_hv = False
            is_signal = False

            # Check pads for net classes
            for pad in fp.pads:
                net_name = pad.net.name if pad.net and hasattr(pad.net, "name") else ""
                net_class = matrix._net_to_class.get(net_name, "Default")

                if net_class == "HighVoltage":
                    is_hv = True
                elif net_class in ["Signal", "HighSpeed"]:
                    is_signal = True

            # Also check ref patterns for power switching components
            ref = fp.properties.get("Reference", "")
            if any(p in ref for p in ["Q", "D", "J_AC"]):
                is_hv = True

            if fp.position:
                pos = (fp.position.X, fp.position.Y)
                if is_hv:
                    hv_points.append(pos)
                elif is_signal:
                    signal_points.append(pos)

        zones = []

        # 2. Create HV Zone (Convex Hull + 5mm buffer)
        if hv_points:
            hull = MultiPoint(hv_points).convex_hull
            # If hull is a point or line, buffer still works
            hv_poly = hull.buffer(5.0)

            if hasattr(hv_poly, "exterior"):
                coords = list(hv_poly.exterior.coords)
                zones.append(
                    RoutingZone(
                        name="HV",
                        polygon=coords,
                        clearance_mm=3.0,
                        allowed_net_classes={"HighVoltage", "GND", "Power"},
                    )
                )

        # 3. Create Signal Zone (Convex Hull + 3mm buffer)
        if signal_points:
            hull = MultiPoint(signal_points).convex_hull
            sig_poly = hull.buffer(3.0)

            if hasattr(sig_poly, "exterior"):
                coords = list(sig_poly.exterior.coords)
                zones.append(
                    RoutingZone(
                        name="Signal",
                        polygon=coords,
                        clearance_mm=0.2,
                        allowed_net_classes={"Signal", "HighSpeed", "GND", "Power"},
                    )
                )

        return zones

    @staticmethod
    def create_default() -> ClearanceMatrix:
        """Create a ClearanceMatrix with Temper default rules.

        Returns:
            ClearanceMatrix with standard Temper project rules
        """
        matrix = ClearanceMatrix()
        temper_rules = create_temper_design_rules()

        for _name, rules in temper_rules.net_classes.items():
            matrix.add_net_class_rules(rules)

        # Set default cross-class clearances
        matrix.set_class_to_class_clearance("Power", "Power", 0.5)
        matrix.set_class_to_class_clearance("Power", "Signal", 0.3)
        matrix.set_class_to_class_clearance("GND", "Power", 0.3)
        matrix.set_class_to_class_clearance("HighSpeed", "HighSpeed", 0.2)

        return matrix
