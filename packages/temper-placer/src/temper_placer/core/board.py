"""
Board and Zone data structures.

This module defines the PCB board geometry and placement zones:
- Board: Overall board dimensions, outline, mounting holes
- Zone: Named regions for component placement constraints
- LayerStackup: Layer definitions for routing estimation
"""

from __future__ import annotations

from dataclasses import dataclass, field

import jax.numpy as jnp
from jax import Array


@dataclass
class MountingHole:
    """
    A mounting hole on the PCB.

    Attributes:
        position: (x, y) center position in mm.
        diameter: Hole diameter in mm.
        keepout_radius: Radius of keepout zone around hole in mm.
    """

    position: tuple[float, float]
    diameter: float
    keepout_radius: float = 3.0  # Default 3mm keepout


@dataclass
class Layer:
    """
    A PCB layer definition.

    Attributes:
        name: Layer name (e.g., "F.Cu", "GND", "PWR", "B.Cu").
        layer_type: Type of layer ("signal", "plane", "mixed").
        copper_weight: Copper weight in oz (1oz, 2oz, etc.).
        is_routable: Whether traces can be routed on this layer.
    """

    name: str
    layer_type: str  # "signal", "plane", "mixed"
    copper_weight: float = 1.0  # oz
    is_routable: bool = True


@dataclass
class LayerStackup:
    """
    PCB layer stackup definition.

    For the Temper board (4-layer):
    - L1 (F.Cu): 2oz copper, signal/power, HV traces
    - L2 (In1.Cu): 1oz copper, GND plane
    - L3 (In2.Cu): 1oz copper, PWR plane
    - L4 (B.Cu): 1oz copper, signal

    Attributes:
        layers: List of layers from top to bottom.
        thickness: Total board thickness in mm.
    """

    layers: list[Layer] = field(default_factory=list)
    thickness: float = 1.6  # mm

    @classmethod
    def default_4layer(cls) -> LayerStackup:
        """Create default 4-layer stackup for Temper board."""
        return cls(
            layers=[
                Layer("F.Cu", "signal", copper_weight=2.0, is_routable=True),
                Layer("In1.Cu", "plane", copper_weight=1.0, is_routable=False),  # GND
                Layer("In2.Cu", "plane", copper_weight=1.0, is_routable=False),  # PWR
                Layer("B.Cu", "signal", copper_weight=1.0, is_routable=True),
            ],
            thickness=1.6,
        )

    def routable_layers(self, net_class: str = "Signal") -> list[int]:
        """
        Return layer indices where this net class can route.

        Args:
            net_class: Net class name ("HighVoltage", "Power", "Signal").

        Returns:
            List of layer indices (0-based) that can be used for routing.
        """
        if net_class == "HighVoltage":
            # HV traces only on L1 (2oz copper for current capacity)
            return [0]
        elif net_class == "Power":
            # Power traces on L1 or L4
            return [i for i, l in enumerate(self.layers) if l.is_routable]
        else:
            # Signal traces can route on any routable layer
            return [i for i, l in enumerate(self.layers) if l.is_routable]

    def tracks_per_cell(self, grid_size: float, net_class: str = "Signal") -> float:
        """
        Estimate routing capacity per routing cell.

        Args:
            grid_size: Size of routing estimation cell in mm.
            net_class: Net class being routed.

        Returns:
            Number of tracks that can cross a cell boundary.
        """
        # Minimum track width + spacing defaults (mm)
        # These would ideally come from KiCad net class constraints
        if net_class == "HighVoltage":
            width, space = 1.0, 1.0  # Wide HV traces
        elif net_class == "Power":
            width, space = 0.5, 0.3
        else:
            width, space = 0.2, 0.2

        pitch = width + space
        layers = len(self.routable_layers(net_class))

        # Tracks per layer = grid_size / pitch
        return (grid_size / pitch) * layers


@dataclass
class Zone:
    """
    A placement zone with specific constraints.

    Attributes:
        name: Unique zone name.
        bounds: (x_min, y_min, x_max, y_max) relative to board origin.
        net_classes: Allowed net classes in this zone.
        components: Mandatory components for this zone.
        weight: Priority weight for zone constraints.
    """

    name: str
    bounds: tuple[float, float, float, float]
    net_classes: list[str] = field(default_factory=lambda: ["Signal"])
    components: list[str] = field(default_factory=list)
    weight: float = 1.0

    @property
    def width(self) -> float:
        """Zone width in mm."""
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> float:
        """Zone height in mm."""
        return self.bounds[3] - self.bounds[1]

    @property
    def center(self) -> tuple[float, float]:
        """(x, y) center position of the zone."""
        return (
            (self.bounds[0] + self.bounds[2]) / 2,
            (self.bounds[1] + self.bounds[3]) / 2,
        )

    @property
    def area(self) -> float:
        """Zone area in mm²."""
        return self.width * self.height

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is within zone boundaries."""
        return self.bounds[0] <= x <= self.bounds[2] and self.bounds[1] <= y <= self.bounds[3]


@dataclass
class GroundDomain:
    """
    A ground plane domain (e.g., AGND, PGND).

    Used to detect and penalize traces crossing ground splits.

    Attributes:
        name: Domain name.
        bounds: Polygon or bounding box.
        star_point: (x, y) location where this domain connects to main GND.
    """

    name: str
    bounds: tuple[float, float, float, float]
    star_point: tuple[float, float] | None = None

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is within ground domain boundaries."""
        return self.bounds[0] <= x <= self.bounds[2] and self.bounds[1] <= y <= self.bounds[3]


@dataclass
class Board:
    """
    The PCB board geometry and constraints.

    Attributes:
        width: Board width in mm.
        height: Board height in mm.
        origin: (x, y) origin point in mm (for absolute coordinates).
        zones: List of placement zones.
        mounting_holes: List of mounting holes (keep-outs).
        ground_domains: List of ground plane domains.
        layer_stackup: Layer definition.
        outline_polygon: Optional list of (x, y) points for non-rectangular boards.
    """

    width: float
    height: float
    origin: tuple[float, float] = (0.0, 0.0)
    zones: list[Zone] = field(default_factory=list)
    mounting_holes: list[MountingHole] = field(default_factory=list)
    keepout_regions: list[tuple[float, float, float, float]] = field(default_factory=list)  # (x_min, y_min, x_max, y_max)
    ground_domains: list[GroundDomain] = field(default_factory=list)
    layer_stackup: LayerStackup | None = None
    outline_polygon: list[tuple[float, float]] | None = None

    # Fast lookup caches
    _zone_map: dict[str, Zone] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize caches and defaults."""
        if not self.layer_stackup:
            self.layer_stackup = LayerStackup.default_4layer()
        self.build_indices()

    def build_indices(self) -> None:
        """Build name -> object map for zones."""
        self._zone_map = {z.name: z for z in self.zones}

    @property
    def has_polygon_outline(self) -> bool:
        """True if the board has a non-rectangular outline."""
        return self.outline_polygon is not None and len(self.outline_polygon) > 2

    def polygon_array(self) -> Array | None:
        """Get outline as a (P, 2) JAX array."""
        if not self.outline_polygon:
            return None
        return jnp.array(self.outline_polygon, dtype=jnp.float32)

    @classmethod
    def from_polygon(
        cls,
        polygon: list[tuple[float, float]],
        origin: tuple[float, float] = (0.0, 0.0),
    ) -> Board:
        """
        Create a board from an arbitrary polygon outline.

        Automatically computes width and height from polygon bounds.

        Args:
            polygon: List of (x, y) vertices.
            origin: Board origin in mm.

        Returns:
            Initialized Board instance.
        """
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        return cls(
            width=x_max - x_min,
            height=y_max - y_min,
            origin=origin,
            outline_polygon=polygon,
        )

    @classmethod
    def temper_default(cls) -> Board:
        """Create a default board matching the Temper induction cooker specs."""
        return cls(
            width=100.0,
            height=150.0,
            origin=(0.0, 0.0),
            mounting_holes=[
                MountingHole((5, 5), 3.2),
                MountingHole((95, 5), 3.2),
                MountingHole((5, 145), 3.2),
                MountingHole((95, 145), 3.2),
            ],
        )

    def get_zone(self, name: str) -> Zone:
        """Get zone by name."""
        return self._zone_map[name]

    def get_zone_for_point(self, x: float, y: float) -> Zone | None:
        """Find the first zone that contains the given point."""
        for zone in self.zones:
            if zone.contains_point(x, y):
                return zone
        return None

    def get_ground_domain(self, x: float, y: float) -> GroundDomain | None:
        """Find the ground domain at the given point."""
        for domain in self.ground_domains:
            if domain.contains_point(x, y):
                return domain
        return None

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is within the board boundaries."""
        return 0 <= x - self.origin[0] <= self.width and 0 <= y - self.origin[1] <= self.height

    def point_in_keepout(self, x: float, y: float) -> bool:
        """
        Check if a point is inside a restricted keep-out area.

        Includes mounting holes and user-defined keep-out zones.

        Args:
            x, y: Point to check.

        Returns:
            True if the point is restricted.
        """
        # Check mounting holes
        for hole in self.mounting_holes:
            dist_sq = (x - hole.position[0]) ** 2 + (y - hole.position[1]) ** 2
            if dist_sq < hole.keepout_radius**2:
                return True
        return False

    def get_bounds_array(self) -> Array:
        """Get [x_min, y_min, x_max, y_max] absolute board bounds."""
        ox, oy = self.origin
        return jnp.array([ox, oy, ox + self.width, oy + self.height], dtype=jnp.float32)

    @property
    def area(self) -> float:
        """Total board area in mm²."""
        return self.width * self.height
