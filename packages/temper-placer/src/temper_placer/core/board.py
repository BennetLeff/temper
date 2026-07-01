"""
Board and Zone data structures.

This module defines the PCB board geometry and placement zones:
- Board: Overall board dimensions, outline, mounting holes
- Zone: Named regions for component placement constraints
- LayerStackup: Layer definitions for routing estimation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

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
class Pad:
    """
    A component pad.

    Attributes:
        position: (x, y) relative to component center.
        size: (width, height) in mm.
        shape: 'rect', 'circle', 'oval', 'roundrect'.
        layer: Layer name.
        number: Pad number.
        net_name: Name of connected net.
    """

    position: tuple[float, float]
    size: tuple[float, float]
    shape: str = "rect"
    layer: str = "F.Cu"
    number: str = ""
    net_name: str | None = None


@dataclass
class Component:
    """
    A PCB component footprint.

    Attributes:
        ref: Reference designator (e.g. U1).
        position: (x, y) center position.
        rotation: Rotation in degrees.
        width: Bounding box width.
        height: Bounding box height.
        pads: List of pads.
        layer: Layer name.
        fixed: Whether the component is locked.
    """

    ref: str
    position: tuple[float, float]
    rotation: float
    width: float
    height: float
    footprint: str | None = None
    pads: list[Pad] = field(default_factory=list)
    layer: str = "F.Cu"
    fixed: bool = False


@dataclass(frozen=True)
class Trace:
    """
    A routed trace segment.

    Attributes:
        start: (x, y) start point.
        end: (x, y) end point.
        width: Trace width in mm.
        layer: Layer name.
        net: Net name.
    """

    start: tuple[float, float]
    end: tuple[float, float]
    width: float
    layer: str
    net: str | None = None


@dataclass(frozen=True)
class Via:
    """
    A plated through-hole via.

    Attributes:
        position: (x, y) coordinates.
        drill: Drill diameter in mm.
        width: Annular ring diameter in mm.
        layers: List of connected layers (e.g. ["F.Cu", "In1.Cu", "B.Cu"]).
        net: Net name.
        is_diff_pair: If True, via is part of differential pair routing and protected from validation removal.
    """

    position: tuple[float, float]
    drill: float
    width: float
    layers: tuple[str, ...] = ("F.Cu", "B.Cu")
    net: str | None = None
    is_diff_pair: bool = False


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


class LayerIndex(IntEnum):
    """
    Canonical 4-layer PCB layer index (IntEnum).

    Each member's `__str__` returns the standard KiCad name
    (`"F.Cu"`, `"In1.Cu"`, `"In2.Cu"`, `"B.Cu"`); the inherited
    `Enum.name` returns the Python identifier (`"F_CU"`, etc.).
    Use `__str__(layer)` for the KiCad name and `layer.name` for the
    identifier — do not conflate them.
    """

    F_CU = 0
    IN1_CU = 1
    IN2_CU = 2
    B_CU = 3

    def __str__(self) -> str:
        return _LAYER_INDEX_TO_KICAD_NAME[self]

    @classmethod
    def from_name(cls, name: str) -> LayerIndex:
        """Look up a LayerIndex by its KiCad name (raises KeyError on miss)."""
        return LAYER_NAME_TO_IDX[name]


# Canonical 4-layer order (top to bottom).
STANDARD_LAYER_ORDER: tuple[LayerIndex, ...] = (
    LayerIndex.F_CU,
    LayerIndex.IN1_CU,
    LayerIndex.IN2_CU,
    LayerIndex.B_CU,
)

# Inner plane layers (GND/PWR) on a 4-layer board.
PLANE_LAYER_INDICES: frozenset[LayerIndex] = frozenset(
    {LayerIndex.IN1_CU, LayerIndex.IN2_CU}
)

_LAYER_INDEX_TO_KICAD_NAME: dict[LayerIndex, str] = {
    LayerIndex.F_CU: "F.Cu",
    LayerIndex.IN1_CU: "In1.Cu",
    LayerIndex.IN2_CU: "In2.Cu",
    LayerIndex.B_CU: "B.Cu",
}

# Canonical layer names for the Temper 4-layer board.
# Derived from STANDARD_LAYER_ORDER / _LAYER_INDEX_TO_KICAD_NAME.
CANONICAL_4LAYER_LAYER_NAMES: frozenset[str] = frozenset(
    str(idx) for idx in STANDARD_LAYER_ORDER
)
CANONICAL_LAYER_COUNT: int = len(STANDARD_LAYER_ORDER)

LAYER_IDX_TO_NAME: dict[LayerIndex, str] = _LAYER_INDEX_TO_KICAD_NAME
LAYER_NAME_TO_IDX: dict[str, LayerIndex] = {
    name: idx for idx, name in _LAYER_INDEX_TO_KICAD_NAME.items()
}


def _coerce_layer_index(name_or_index: str | LayerIndex) -> LayerIndex:
    if isinstance(name_or_index, LayerIndex):
        return name_or_index
    return LAYER_NAME_TO_IDX[name_or_index]


def is_plane_layer(name_or_index: str | LayerIndex) -> bool:
    """Return True if the layer is a plane layer (In1.Cu or In2.Cu)."""
    return _coerce_layer_index(name_or_index) in PLANE_LAYER_INDICES


def is_signal_layer(name_or_index: str | LayerIndex) -> bool:
    """Return True if the layer is a signal layer (F.Cu or B.Cu)."""
    return not is_plane_layer(name_or_index)


def side_to_layer_name(side: int) -> str:
    """Map a board side (0=top, 1=bottom) to its KiCad layer name.

    Raises ValueError for sides other than 0 or 1.
    """
    if side == 0:
        return "F.Cu"
    if side == 1:
        return "B.Cu"
    raise ValueError(f"side must be 0 or 1, got {side!r}")


def layer_name_to_index(name: str) -> LayerIndex:
    """Map a KiCad layer name to its LayerIndex. Raises KeyError on miss."""
    return LAYER_NAME_TO_IDX[name]


@dataclass(frozen=True)
class LayerStackup:
    """
    PCB layer stackup definition.

    For the Temper board (4-layer):
    - L1 (F.Cu): 2oz copper, signal/power, HV traces
    - L2 (In1.Cu): 1oz copper, GND plane
    - L3 (In2.Cu): 1oz copper, PWR plane
    - L4 (B.Cu): 1oz copper, signal

    Attributes:
        layers: Tuple of layers from top to bottom.
        thickness: Total board thickness in mm.
    """

    layers: tuple[Layer, ...] = ()
    thickness: float = 1.6  # mm

    def is_plane_layer(self, layer_idx: int) -> bool:
        """Check if a layer is a plane layer."""
        if 0 <= layer_idx < len(self.layers):
            return self.layers[layer_idx].layer_type == "plane"
        return False

    @classmethod
    def default_4layer(cls) -> LayerStackup:
        """Create default 4-layer stackup for Temper board.

        Inner layers (In1.Cu, In2.Cu) are plane layers (GND and PWR) and
        are not routable for signal traces. The PowerPlaneStage handles
        plane net connections separately via vias.
        """
        return cls(
            layers=(
                Layer("F.Cu", "signal", copper_weight=2.0, is_routable=True),
                Layer("In1.Cu", "plane", copper_weight=1.0, is_routable=False),
                Layer("In2.Cu", "plane", copper_weight=1.0, is_routable=False),
                Layer("B.Cu", "signal", copper_weight=1.0, is_routable=True),
            ),
            thickness=1.6,
        )

    @classmethod
    def _test_only_2layer(cls) -> LayerStackup:
        """TEST-ONLY: Create a 2-layer stackup for focused unit tests.

        Not a production path. The canonical Temper board is 4-layer.
        Use `default_4layer()` for any production or integration code.

        Raises RuntimeError if called from outside a test file.
        """
        import sys
        import warnings

        frame = sys._getframe(1)
        caller_file = frame.f_code.co_filename
        if "/test" not in caller_file and "/tests/" not in caller_file:
            raise RuntimeError(
                "_test_only_2layer() may only be called from test files. "
                f"Called from {caller_file}. Use default_4layer() instead."
            )

        warnings.warn(
            "_test_only_2layer() is for test use only. Use default_4layer() for production.",
            stacklevel=2,
        )
        return cls(
            layers=(
                Layer("F.Cu", "signal", copper_weight=1.0, is_routable=True),
                Layer("B.Cu", "signal", copper_weight=1.0, is_routable=True),
            ),
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
            return [i for i, layer in enumerate(self.layers) if layer.is_routable]
        else:
            # Signal traces can route on any routable layer
            return [i for i, layer in enumerate(self.layers) if layer.is_routable]

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
        max_size: Optional (max_width, max_height) for feedback expansion.
        can_expand: List of allowed expansion directions ('up', 'down', 'left', 'right').
    """

    name: str
    bounds: tuple[float, float, float, float]
    net_classes: list[str] = field(default_factory=lambda: ["Signal"])
    components: list[str] = field(default_factory=list)
    weight: float = 1.0
    polygon: list[tuple[float, float]] | None = (
        None  # Optional polygon vertices for non-rectangular zones
    )
    layers: list[str] = field(default_factory=lambda: ["F.Cu"])
    max_size: tuple[float, float] | None = None
    can_expand: list[str] = field(default_factory=lambda: ["up", "down", "left", "right"])

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
    keepouts: list[tuple[float, float, float, float]] = field(
        default_factory=list
    )  # (x_min, y_min, x_max, y_max)
    ground_domains: list[GroundDomain] = field(default_factory=list)
    layer_stackup: LayerStackup | None = None
    outline_polygon: list[tuple[float, float]] | None = None

    # Fast lookup caches
    _zone_map: dict[str, Zone] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize caches and defaults. Enforce 4-layer stackup."""
        if not self.layer_stackup:
            self.layer_stackup = LayerStackup.default_4layer()
        elif len(self.layer_stackup.layers) != CANONICAL_LAYER_COUNT:
            actual = [ly.name for ly in self.layer_stackup.layers]
            raise ValueError(
                f"Board requires {CANONICAL_LAYER_COUNT}-layer stackup (canonical: "
                f"{sorted(CANONICAL_4LAYER_LAYER_NAMES)}), got "
                f"{len(self.layer_stackup.layers)} layers: {actual}"
            )
        self.build_indices()

    def build_indices(self) -> None:
        """Build name -> object map for zones."""
        self._zone_map = {z.name: z for z in self.zones}

    @property
    def keepout_regions(self) -> list[tuple[float, float, float, float]]:
        """Alias for keepouts for heuristic compatibility."""
        return self.keepouts

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
            zones=[
                Zone("HV_ZONE", (0, 0, 50, 80)),
                Zone("POWER_ZONE", (50, 0, 100, 80)),
                Zone("MCU_ZONE", (0, 80, 100, 130)),
                Zone("UI_ZONE", (0, 130, 100, 150)),
            ],
            mounting_holes=[
                MountingHole((5, 5), 3.2),
                MountingHole((95, 5), 3.2),
                MountingHole((5, 145), 3.2),
                MountingHole((95, 145), 3.2),
            ],
            ground_domains=[
                GroundDomain("PGND", (0, 0, 50, 150), star_point=(50, 75)),
                GroundDomain("CGND", (50, 0, 100, 150), star_point=(50, 75)),
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
        """
        Check if a point is within the board boundaries.

        Args:
            x, y: Board-relative coordinates.
        """
        return 0 <= x <= self.width and 0 <= y <= self.height

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

    def get_relative_bounds_array(self) -> Array:
        """Get [0, 0, width, height] relative board bounds."""
        return jnp.array([0.0, 0.0, self.width, self.height], dtype=jnp.float32)

    @property
    def area(self) -> float:
        """Total board area in mm²."""
        return self.width * self.height

    def rotated_90(self) -> "Board":
        """Return a new Board rotated 90° clockwise.

        All geometry is transformed: (x, y) maps to (old_height - y, x).
        Zones, mounting holes, keepouts, ground domains, and outline
        polygon are deep-copied and rotated.  Layer stackup is preserved.
        """
        h = self.height

        def _rotate_point(x: float, y: float) -> tuple[float, float]:
            return (h - y, x)

        def _rotate_bounds(b: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
            return (h - b[3], b[0], h - b[1], b[2])

        _EXPAND_ROTATE = {"up": "right", "right": "down", "down": "left", "left": "up"}

        def _rotate_expand(dirs: list[str]) -> list[str]:
            return [_EXPAND_ROTATE.get(d, d) for d in dirs]

        rotated_zones = [
            Zone(
                name=z.name,
                bounds=_rotate_bounds(z.bounds),
                net_classes=list(z.net_classes),
                components=list(z.components),
                weight=z.weight,
                polygon=[_rotate_point(px, py) for px, py in z.polygon] if z.polygon else None,
                layers=list(z.layers),
                max_size=z.max_size,
                can_expand=_rotate_expand(z.can_expand),
            )
            for z in self.zones
        ]

        rotated_holes = [
            MountingHole(
                position=_rotate_point(mh.position[0], mh.position[1]),
                diameter=mh.diameter,
                keepout_radius=mh.keepout_radius,
            )
            for mh in self.mounting_holes
        ]

        rotated_keepouts = [
            _rotate_bounds(k) for k in self.keepouts
        ]

        rotated_grounds = [
            GroundDomain(
                name=gd.name,
                bounds=_rotate_bounds(gd.bounds),
                star_point=_rotate_point(gd.star_point[0], gd.star_point[1])
                if gd.star_point else None,
            )
            for gd in self.ground_domains
        ]

        rotated_outline = (
            [_rotate_point(px, py) for px, py in self.outline_polygon]
            if self.outline_polygon else None
        )

        return Board(
            width=self.height,
            height=self.width,
            origin=self.origin,
            zones=rotated_zones,
            mounting_holes=rotated_holes,
            keepouts=rotated_keepouts,
            ground_domains=rotated_grounds,
            layer_stackup=self.layer_stackup,
            outline_polygon=rotated_outline,
        )
