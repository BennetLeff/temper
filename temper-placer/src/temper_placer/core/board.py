"""
Board and Zone data structures.

This module defines the PCB board geometry and placement zones:
- Board: Overall board dimensions, outline, mounting holes
- Zone: Named regions for component placement constraints
- LayerStackup: Layer definitions for routing estimation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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

    position: Tuple[float, float]
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

    layers: List[Layer] = field(default_factory=list)
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

    def routable_layers(self, net_class: str = "Signal") -> List[int]:
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
            # Signal traces on any routable layer
            return [i for i, l in enumerate(self.layers) if l.is_routable]

    def tracks_per_cell(self, grid_size: float, net_class: str = "Signal") -> float:
        """
        Estimate routing tracks per grid cell for congestion modeling.

        Args:
            grid_size: Grid cell size in mm.
            net_class: Net class for determining trace width/clearance.

        Returns:
            Estimated number of tracks that fit in a grid cell.
        """
        # Typical trace widths and clearances by net class
        if net_class == "HighVoltage":
            trace_width = 1.0  # mm (wide for current)
            clearance = 2.0  # mm (HV clearance)
        elif net_class == "Power":
            trace_width = 0.5  # mm
            clearance = 0.3  # mm
        else:
            trace_width = 0.2  # mm
            clearance = 0.15  # mm

        pitch = trace_width + clearance
        n_routable = len(self.routable_layers(net_class))

        return (grid_size / pitch) * n_routable


@dataclass
class Zone:
    """
    A placement zone on the PCB.

    Zones define named regions where specific components should be placed.
    For example: "HV_ZONE" for high-voltage components, "MCU_ZONE" for
    microcontroller and peripherals.

    Attributes:
        name: Zone name (e.g., "HV_ZONE", "LV_ZONE", "MCU_ZONE").
        bounds: (x_min, y_min, x_max, y_max) rectangular bounds in mm.
        components: List of component refs that should be in this zone.
        net_classes: Allowed net classes in this zone.
        polygon: Optional polygon vertices for non-rectangular zones.
    """

    name: str
    bounds: Tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max)
    components: List[str] = field(default_factory=list)
    net_classes: List[str] = field(default_factory=lambda: ["Signal"])
    polygon: Optional[List[Tuple[float, float]]] = None

    @property
    def width(self) -> float:
        """Zone width in mm."""
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> float:
        """Zone height in mm."""
        return self.bounds[3] - self.bounds[1]

    @property
    def center(self) -> Tuple[float, float]:
        """Zone center point."""
        return (
            (self.bounds[0] + self.bounds[2]) / 2,
            (self.bounds[1] + self.bounds[3]) / 2,
        )

    @property
    def area(self) -> float:
        """Zone area in mm²."""
        return self.width * self.height

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is inside this zone."""
        x_min, y_min, x_max, y_max = self.bounds
        return x_min <= x <= x_max and y_min <= y <= y_max


@dataclass
class GroundDomain:
    """
    A ground domain region for split-ground designs.

    The Temper board has multiple ground domains:
    - PGND: Power ground (HV section)
    - CGND: Control ground (LV digital)
    - ISOGND: Isolated ground (gate driver)

    Signals should not cross between domains except at the star ground point.

    Attributes:
        name: Domain name (e.g., "PGND", "CGND", "ISOGND").
        bounds: (x_min, y_min, x_max, y_max) rectangular bounds.
        star_point: Optional (x, y) location of star ground connection.
    """

    name: str
    bounds: Tuple[float, float, float, float]
    star_point: Optional[Tuple[float, float]] = None

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is inside this ground domain."""
        x_min, y_min, x_max, y_max = self.bounds
        return x_min <= x <= x_max and y_min <= y <= y_max


@dataclass
class Board:
    """
    PCB board definition.

    Attributes:
        width: Board width in mm.
        height: Board height in mm.
        origin: (x, y) origin offset in mm (typically (0, 0)).
        corner_radius: Corner radius for rounded boards in mm.
        mounting_holes: List of mounting holes.
        layer_stackup: Layer stackup definition.
        zones: List of placement zones.
        ground_domains: List of ground domains for split-ground designs.
        keepout_regions: List of (x_min, y_min, x_max, y_max) keepout areas.
    """

    width: float
    height: float
    origin: Tuple[float, float] = (0.0, 0.0)
    corner_radius: float = 0.0
    mounting_holes: List[MountingHole] = field(default_factory=list)
    layer_stackup: LayerStackup = field(default_factory=LayerStackup.default_4layer)
    zones: List[Zone] = field(default_factory=list)
    ground_domains: List[GroundDomain] = field(default_factory=list)
    keepout_regions: List[Tuple[float, float, float, float]] = field(default_factory=list)

    # Zone index (populated by build_indices)
    _zone_index: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """Build indices after initialization."""
        self.build_indices()

    def build_indices(self) -> None:
        """Build lookup indices."""
        self._zone_index = {z.name: i for i, z in enumerate(self.zones)}

    @classmethod
    def temper_default(cls) -> Board:
        """Create default board for Temper induction cooker."""
        return cls(
            width=100.0,  # mm
            height=150.0,  # mm
            origin=(0.0, 0.0),
            corner_radius=3.0,
            mounting_holes=[
                MountingHole((5.0, 5.0), 3.2, keepout_radius=5.0),
                MountingHole((95.0, 5.0), 3.2, keepout_radius=5.0),
                MountingHole((5.0, 145.0), 3.2, keepout_radius=5.0),
                MountingHole((95.0, 145.0), 3.2, keepout_radius=5.0),
            ],
            layer_stackup=LayerStackup.default_4layer(),
            zones=[
                Zone("HV_ZONE", (0, 0, 50, 80), net_classes=["HighVoltage", "Power"]),
                Zone("LV_ZONE", (50, 0, 100, 80), net_classes=["Signal", "Power"]),
                Zone("MCU_ZONE", (50, 80, 100, 150), net_classes=["Signal"]),
                Zone("INTERFACE_ZONE", (0, 80, 50, 150), net_classes=["Signal"]),
            ],
            ground_domains=[
                GroundDomain("PGND", (0, 0, 50, 80)),
                GroundDomain("CGND", (50, 0, 100, 150), star_point=(50, 40)),
            ],
        )

    def get_zone(self, name: str) -> Zone:
        """Get a zone by name."""
        return self.zones[self._zone_index[name]]

    def get_zone_for_point(self, x: float, y: float) -> Optional[Zone]:
        """Get the zone containing a point, or None if outside all zones."""
        for zone in self.zones:
            if zone.contains_point(x, y):
                return zone
        return None

    def get_ground_domain(self, x: float, y: float) -> Optional[GroundDomain]:
        """Get the ground domain containing a point."""
        for domain in self.ground_domains:
            if domain.contains_point(x, y):
                return domain
        return None

    def contains_point(self, x: float, y: float) -> bool:
        """Check if a point is within board bounds."""
        ox, oy = self.origin
        return ox <= x <= ox + self.width and oy <= y <= oy + self.height

    def point_in_keepout(self, x: float, y: float) -> bool:
        """Check if a point is in a keepout region."""
        # Check mounting hole keepouts
        for hole in self.mounting_holes:
            hx, hy = hole.position
            dist_sq = (x - hx) ** 2 + (y - hy) ** 2
            if dist_sq < hole.keepout_radius**2:
                return True

        # Check rectangular keepouts
        for x_min, y_min, x_max, y_max in self.keepout_regions:
            if x_min <= x <= x_max and y_min <= y <= y_max:
                return True

        return False

    def get_bounds_array(self) -> Array:
        """Get board bounds as JAX array: [x_min, y_min, x_max, y_max]."""
        ox, oy = self.origin
        return jnp.array([ox, oy, ox + self.width, oy + self.height], dtype=jnp.float32)

    @property
    def area(self) -> float:
        """Board area in mm²."""
        return self.width * self.height
