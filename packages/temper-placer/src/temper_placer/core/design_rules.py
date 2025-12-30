"""
Design rules for PCB routing.

This module provides net class and design rule specifications for
controlling trace widths, clearances, and via sizes during routing.
"""

from copy import deepcopy
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

        # Check if net name matches a known ground net pattern (before power)
        if self._is_ground_net(net_name) and "GND" in self.net_classes:
            return self.net_classes["GND"]

        # Check if net name matches a known power net pattern
        if self._is_power_net(net_name) and "Power" in self.net_classes:
            return self.net_classes["Power"]

        # Check if net name implies Gate Drive (GATE, PWM)
        if self._is_gate_net(net_name) and "GateDrive" in self.net_classes:
            return self.net_classes["GateDrive"]

        # Check if net name implies High Current (SW, AC, BUS)
        if self._is_high_current_net(net_name) and "HighCurrent" in self.net_classes:
            # If not explicitly matched as Power, or if we want to upgrade Power to HighCurrent
            # Actually, Power handled most VCCs. HighCurrent handles SW_NODE etc.
            return self.net_classes["HighCurrent"]

        # Return default rules
        return NetClassRules(
            name="Default",
            trace_width=self.default_trace_width,
            clearance=self.default_clearance,
            via_diameter=self.default_via_diameter,
            via_drill=self.default_via_drill,
        )

    def get_class_for_net(self, net_name: str) -> str:
        """Get the net class name for a specific net."""
        return self.get_rules_for_net(net_name).name

    def _is_ground_net(self, net_name: str) -> bool:
        """Check if net name matches common ground net patterns."""
        upper = net_name.upper()
        ground_patterns = ["GND", "GROUND", "VSS", "AGND", "DGND", "PGND"]
        for pattern in ground_patterns:
            if pattern in upper or upper.startswith(pattern):
                return True
        return False

    def _is_power_net(self, net_name: str) -> bool:
        """Check if net name matches common power net patterns (excluding ground)."""
        upper = net_name.upper()
        # Exclude ground nets - they are handled separately
        if self._is_ground_net(net_name):
            return False
        power_patterns = [
            "VCC", "VDD", "V+", "V-", "VBAT", "VIN", "VOUT",
            "+5V", "+3.3V", "+12V", "-12V", "+3V3", "+5V0",
        ]
        for pattern in power_patterns:
            if pattern in upper or upper.startswith(pattern):
                return True
        return False

    def _is_gate_net(self, net_name: str) -> bool:
        """Check if net belongs to Gate Drive circuitry."""
        upper = net_name.upper()
        # GATE_H, GATE_L, PWM_H, PWM_L, SW_NODE (ref for gate)
        patterns = ["GATE", "PWM", "SW_NODE"]
        for p in patterns:
            if p in upper:
                return True
        return False

    def _is_high_current_net(self, net_name: str) -> bool:
        """Check if net carries high switching current."""
        upper = net_name.upper()
        # DC_BUS+, AC_L, AC_N, COIL
        patterns = ["DC_BUS", "AC_L", "AC_N", "COIL"]
        for p in patterns:
            if p in upper:
                return True
        return False


# =============================================================================
# Standard Net Classes for Temper Project
# =============================================================================

TEMPER_NET_CLASSES = {
    "Power": NetClassRules(
        name="Power",
        trace_width=0.5,  # Reduced from 1.0mm to fit ESP32 pitch
        clearance=0.25,   # Reduced from 0.5mm
        via_diameter=0.8,
        via_drill=0.4,
    ),
    "GateDrive": NetClassRules(
        name="GateDrive",
        trace_width=0.4,  # Robust drive trace
        clearance=0.25,  # Increased clearance for transient safety
        via_diameter=0.8,
        via_drill=0.4,
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
        trace_width=0.5,  # Minimized for routability verification
        clearance=0.2,    # Minimized
        via_diameter=0.8,
        via_drill=0.4,
    ),
}


def create_temper_design_rules() -> DesignRules:
    """Create design rules with Temper-specific net classes.

    Returns:
        DesignRules configured for Temper project requirements
    """
    return DesignRules(
        default_trace_width=0.2,
        default_clearance=0.2,  # Aligned with KiCad minimal accepted clearance
        default_via_diameter=0.6,
        default_via_drill=0.3,
        net_classes=deepcopy(TEMPER_NET_CLASSES),
    )
