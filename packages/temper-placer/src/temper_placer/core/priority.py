"""
Priority classification for placement and routing.

Defines priority levels that mirror the professional PCB design workflow:
1. Power stage (template-based, fixed)
2. Gate drivers (proximity-constrained)
3. High-speed interfaces (zone-constrained)
4. Auto-place (full optimization)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist


class PlacementPriority(IntEnum):
    """Placement priority levels (lower = placed first)."""
    
    POWER = 1       # IGBTs, bus caps, diodes - template/fixed
    DRIVER = 2      # Gate drivers, bootstrap - proximity to power
    HIGH_SPEED = 3  # MCU, oscillators - zone-constrained
    ANALOG = 4      # Sensors, opamps - isolated
    DIGITAL = 5     # Passives, connectors - auto-place


class RoutingPriority(IntEnum):
    """Routing priority levels (lower = routed first)."""
    
    POWER = 1       # Wide traces, short paths, single layer
    GATE_DRIVE = 2  # Controlled impedance, matched length
    HIGH_SPEED = 3  # Length matching, impedance control
    ANALOG = 4      # Shielded, away from noise
    DIGITAL = 5     # Standard routing
    AUTO = 10       # Everything else


@dataclass
class PlacementPhaseConfig:
    """Configuration for a placement phase."""
    
    name: str
    priority: PlacementPriority
    components: list[str] = field(default_factory=list)
    method: str = "optimize"  # "template", "proximity", "optimize"
    
    # Template method options
    template: str | None = None
    anchor: tuple[float, float] | None = None
    
    # Proximity method options
    reference: str | None = None
    max_distance_mm: float = 20.0
    
    # Zone constraint
    zone: str | None = None


@dataclass
class RoutingPhaseConfig:
    """Configuration for a routing phase."""
    
    name: str
    priority: RoutingPriority
    nets: list[str] = field(default_factory=list)
    trace_width_mm: float = 0.25
    via_cost: float = 1.0
    allow_layer_change: bool = True
    max_length_mm: float | None = None  # For length matching


@dataclass
class PriorityConfig:
    """Complete priority configuration for placement and routing."""
    
    placement_phases: list[PlacementPhaseConfig] = field(default_factory=list)
    routing_phases: list[RoutingPhaseConfig] = field(default_factory=list)
    
    def get_placement_phase(self, priority: PlacementPriority) -> PlacementPhaseConfig | None:
        """Get placement phase config by priority."""
        for phase in self.placement_phases:
            if phase.priority == priority:
                return phase
        return None
    
    def get_routing_phase(self, priority: RoutingPriority) -> RoutingPhaseConfig | None:
        """Get routing phase config by priority."""
        for phase in self.routing_phases:
            if phase.priority == priority:
                return phase
        return None
    
    def classify_component(
        self, 
        ref: str, 
        netlist: "Netlist"
    ) -> PlacementPriority:
        """Classify a component into a placement priority."""
        # Check explicit assignments first
        for phase in self.placement_phases:
            if ref in phase.components:
                return phase.priority
        
        # Default classification by prefix
        prefix = ref.rstrip("0123456789")
        
        if prefix in ("Q", "D", "C_BUS"):
            return PlacementPriority.POWER
        elif prefix in ("U_GATE", "R_GATE", "C_BOOT", "C_VCC"):
            return PlacementPriority.DRIVER
        elif prefix in ("U_MCU", "Y", "X"):
            return PlacementPriority.HIGH_SPEED
        elif prefix in ("U_OPAMP", "U_CT", "R_BURDEN"):
            return PlacementPriority.ANALOG
        else:
            return PlacementPriority.DIGITAL
    
    def classify_net(self, net_name: str) -> RoutingPriority:
        """Classify a net into a routing priority."""
        # Check explicit assignments first
        for phase in self.routing_phases:
            for pattern in phase.nets:
                if pattern.endswith("*"):
                    if net_name.startswith(pattern[:-1]):
                        return phase.priority
                elif net_name == pattern:
                    return phase.priority
        
        # Default classification by net name
        upper = net_name.upper()
        
        if any(x in upper for x in ("BUS", "340V", "HV", "SW_NODE")):
            return RoutingPriority.POWER
        elif any(x in upper for x in ("GATE", "+15V", "CGND")):
            return RoutingPriority.GATE_DRIVE
        elif any(x in upper for x in ("SPI", "I2C", "USB", "CLK")):
            return RoutingPriority.HIGH_SPEED
        elif any(x in upper for x in ("SENSE", "NTC", "RTD")):
            return RoutingPriority.ANALOG
        else:
            return RoutingPriority.DIGITAL


# Pre-defined power stage templates
POWER_STAGE_TEMPLATES = {
    "half_bridge_vertical": {
        # Relative offsets from anchor (x, y) in mm
        "Q1": (0, 5),      # High-side IGBT
        "Q2": (0, -5),     # Low-side IGBT
        "D1": (-8, 5),     # High-side diode
        "D2": (-8, -5),    # Low-side diode
        "C_BUS1": (8, 5),  # Bus cap near Q1
        "C_BUS2": (8, -5), # Bus cap near Q2
    },
    "half_bridge_horizontal": {
        "Q1": (-5, 0),
        "Q2": (5, 0),
        "D1": (-5, -8),
        "D2": (5, -8),
        "C_BUS1": (-5, 8),
        "C_BUS2": (5, 8),
    },
    "full_bridge": {
        "Q1": (-10, 5),   # High-side A
        "Q2": (-10, -5),  # Low-side A
        "Q3": (10, 5),    # High-side B
        "Q4": (10, -5),   # Low-side B
        "C_BUS1": (0, 8),
        "C_BUS2": (0, -8),
    },
}
