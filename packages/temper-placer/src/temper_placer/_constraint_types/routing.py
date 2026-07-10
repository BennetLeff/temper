from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RoutingCorridor:
    """Preserve routing channel between components.

    Used to keep paths clear for critical nets like USB, SPI.
    """

    name: str
    from_component: str  # Source component ref
    to_component: str  # Target component ref
    width_mm: float  # Corridor width
    keep_clear: bool = True  # If True, don't place components in corridor
    nets: list[str] = field(default_factory=list)  # Associated nets
    tier: str = "soft"
    description: str = ""


@dataclass
class PlacementProximityConstraint:
    """Constraint ensuring a component output pin is close to a target input pin.

    This is a more specific version of ProximityRule that operates on pins
    rather than component centers, which is critical for gate drive circuits.

    Attributes:
        name: Unique identifier
        from_component: Source component ref
        from_pin: Pin on source component
        to_component: Target component ref
        to_pin: Pin on target component
        max_distance_mm: Maximum pin-to-pin distance
        tier: "hard" or "soft"
        description: Human-readable description
    """

    name: str
    from_component: str
    from_pin: str
    to_component: str
    to_pin: str
    max_distance_mm: float = 15.0
    tier: str = "hard"
    description: str = ""


@dataclass
class HVExclusionZone:
    """Defines a rectangular zone around HV components that signals must avoid.

    Used by the ClearanceGridStage to block low-voltage signal routing near
    HV pins. This forces the router to find paths around the HV zone.

    EXP-13: HV exclusion zones for gate signal routing safety.

    Attributes:
        name: Unique identifier
        center: (x, y) center position in mm
        size: (width, height) in mm
        clearance_mm: Required clearance (creepage distance)
        excluded_nets: List of net names that must avoid this zone
        component_refdes: Optional parent component refdes. When set, all pads
            of that component are identified as HV pads and receive the
            pre-route creepage expansion. When unset, the closest component to
            the zone center is used.
        description: Human-readable description
    """

    name: str
    center: tuple[float, float]
    size: tuple[float, float]
    clearance_mm: float = 6.0  # allow-safety-constant: HV exclusion zone default
    excluded_nets: list[str] = field(default_factory=list)
    component_refdes: str | None = None
    description: str = ""


@dataclass
class IsolationSlot:
    """Defines a PCB slot for creepage isolation between HV and LV pins.

    Slots are routed cutouts in the PCB substrate that force the creepage
    path around them, effectively multiplying the creepage distance.

    EXP-15: Automated slot isolation for IEC 60335-1 compliance.

    For TO-247 packages where gate pin (5.45mm from HV) cannot meet 6mm creepage:
    - A 1-2mm wide slot between gate and collector pins
    - Forces creepage path around slot (12-15mm effective distance)

    Attributes:
        name: Unique identifier for the slot
        component_ref: Component reference (e.g., "Q1") - slot positioned relative to component
        start_offset: (dx, dy) offset from component origin to slot start
        end_offset: (dx, dy) offset from component origin to slot end
        width_mm: Slot width (typically 1.0-2.0mm for routing)
        lv_pin: Low-voltage pin number being isolated (e.g., "1" for gate)
        hv_pin: High-voltage pin number (e.g., "2" for collector)
        description: Human-readable description
    """

    name: str
    component_ref: str
    start_offset: tuple[float, float]  # Relative to component position
    end_offset: tuple[float, float]  # Relative to component position
    width_mm: float = 1.5
    lv_pin: str = ""
    hv_pin: str = ""
    description: str = ""
