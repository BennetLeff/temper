"""
Design rules for PCB routing.

This module provides net class and design rule specifications for
controlling trace widths, clearances, and via sizes during routing.
"""

from dataclasses import dataclass, field


@dataclass
class NetClassRules:
    """Routing rules for a net class.

    Defines the physical parameters for traces in a given net class,
    including width, clearance, and via specifications.

    Attributes:
        name: Net class name (e.g., 'Power', 'Signal', 'HighSpeed')
        trace_width: Trace width in mm
        clearance: Minimum clearance to other traces in mm
        via_diameter: Via pad diameter in mm
        via_drill: Via drill diameter in mm
        target_impedance: Target impedance in ohms (for controlled impedance)
    """

    name: str
    trace_width: float  # mm
    clearance: float  # mm
    via_diameter: float = 0.6  # mm
    via_drill: float = 0.3  # mm
    target_impedance: float | None = None  # ohms


@dataclass
class DesignRules:
    """PCB design rules with net class support.

    Provides default routing parameters and net-class-specific overrides.
    Supports looking up rules by net name or net class.

    Attributes:
        default_trace_width: Default trace width in mm
        default_clearance: Default clearance in mm
        default_via_diameter: Default via diameter in mm
        default_via_drill: Default via drill diameter in mm
        net_classes: Dictionary of net class name -> NetClassRules
        net_overrides: Dictionary of net name -> NetClassRules for per-net overrides
    """

    default_trace_width: float = 0.2
    default_clearance: float = 0.2
    default_via_diameter: float = 0.6
    default_via_drill: float = 0.3
    net_classes: dict[str, NetClassRules] = field(default_factory=dict)
    net_overrides: dict[str, NetClassRules] = field(default_factory=dict)

    def get_rules_for_net(
        self, net_name: str, net_class: str | None = None
    ) -> NetClassRules:
        """Get routing rules for a specific net.

        Lookup priority:
        1. Per-net override (net_overrides[net_name])
        2. Net class rules (net_classes[net_class])
        3. Default rules

        Args:
            net_name: Net name (e.g., 'VCC', 'NET1')
            net_class: Optional net class name (e.g., 'Power', 'Signal')

        Returns:
            NetClassRules for this net
        """
        # Check net-specific override first
        if net_name in self.net_overrides:
            return self.net_overrides[net_name]

        # Then check net class
        if net_class and net_class in self.net_classes:
            return self.net_classes[net_class]

        # Check if net name matches a known power net pattern
        if self._is_power_net(net_name):
            if "Power" in self.net_classes:
                return self.net_classes["Power"]
            if "GND" in self.net_classes and "GND" in net_name.upper():
                return self.net_classes["GND"]

        # Return default rules
        return NetClassRules(
            name="Default",
            trace_width=self.default_trace_width,
            clearance=self.default_clearance,
            via_diameter=self.default_via_diameter,
            via_drill=self.default_via_drill,
        )

    def _is_power_net(self, net_name: str) -> bool:
        """Check if net name matches common power net patterns."""
        upper = net_name.upper()
        power_patterns = [
            "VCC", "VDD", "V+", "V-", "VBAT", "VIN", "VOUT",
            "GND", "GROUND", "VSS", "AGND", "DGND", "PGND",
            "+5V", "+3.3V", "+12V", "-12V", "+3V3", "+5V0",
        ]
        for pattern in power_patterns:
            if pattern in upper or upper.startswith(pattern):
                return True
        return False


# =============================================================================
# Standard Net Classes for Temper Project
# =============================================================================

TEMPER_NET_CLASSES = {
    "Power": NetClassRules(
        name="Power",
        trace_width=1.0,  # 1mm for high current
        clearance=0.5,  # Extra clearance for safety
        via_diameter=1.0,
        via_drill=0.5,
    ),
    "GND": NetClassRules(
        name="GND",
        trace_width=1.0,  # Wide ground traces
        clearance=0.3,
        via_diameter=1.0,
        via_drill=0.5,
    ),
    "HighSpeed": NetClassRules(
        name="HighSpeed",
        trace_width=0.15,  # Controlled impedance
        clearance=0.2,
        via_diameter=0.4,
        via_drill=0.2,
        target_impedance=50.0,  # 50 ohm
    ),
    "Signal": NetClassRules(
        name="Signal",
        trace_width=0.2,  # Standard signal traces
        clearance=0.15,
        via_diameter=0.6,
        via_drill=0.3,
    ),
    "HighCurrent": NetClassRules(
        name="HighCurrent",
        trace_width=2.0,  # 2mm for very high current
        clearance=0.5,
        via_diameter=1.2,
        via_drill=0.6,
    ),
}


def create_temper_design_rules() -> DesignRules:
    """Create design rules with Temper-specific net classes.

    Returns:
        DesignRules configured for Temper project requirements
    """
    return DesignRules(
        default_trace_width=0.2,
        default_clearance=0.15,
        default_via_diameter=0.6,
        default_via_drill=0.3,
        net_classes=dict(TEMPER_NET_CLASSES),
    )
