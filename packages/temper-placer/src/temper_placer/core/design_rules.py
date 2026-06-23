"""
Design rules for PCB routing.

This module provides net class and design rule specifications for
controlling trace widths, clearances, and via sizes during routing.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict

from temper_placer.core.differential_pair import DifferentialPairConstraint
from temper_placer.core.bus_cohort import BusCohortConstraint
from temper_placer.core.net_graph import NetGraph


@dataclass
class ViaTemplate:
    """Via array template for high-current routing.

    Defines a grid pattern of vias for nets requiring higher current capacity
    than a single via can provide (e.g., power nets, high-current traces).

    Attributes:
        name: Template identifier (e.g., 'Via1x1', 'Via2x2', 'Via3x3')
        rows: Number of vias in vertical direction
        cols: Number of vias in horizontal direction
        via_diameter_mm: Individual via pad diameter in mm
        via_drill_mm: Individual via drill diameter in mm
        pitch_mm: Center-to-center spacing between vias in mm

    Example:
        >>> template = ViaTemplate("Via2x2", 2, 2, 0.6, 0.3, 1.2)
        >>> width, height = template.get_footprint_bbox()
        >>> print(f"2x2 array footprint: {width}x{height}mm")
    """

    name: str
    rows: int
    cols: int
    via_diameter_mm: float
    via_drill_mm: float
    pitch_mm: float

    def get_footprint_bbox(self) -> tuple[float, float]:
        """Calculate bounding box (width, height) of via array.

        Returns:
            Tuple of (width_mm, height_mm) for the entire via array footprint
        """
        width = (self.cols - 1) * self.pitch_mm + self.via_diameter_mm
        height = (self.rows - 1) * self.pitch_mm + self.via_diameter_mm
        return (width, height)

    @property
    def via_count(self) -> int:
        """Total number of vias in array."""
        return self.rows * self.cols

    def get_via_positions(self, center_x: float, center_y: float) -> list[tuple[float, float]]:
        """
        Calculate via positions in array centered at (center_x, center_y).

        Args:
            center_x: Array center X coordinate (mm)
            center_y: Array center Y coordinate (mm)

        Returns:
            List of (x, y) via positions in mm
        """
        positions = []

        # Calculate array dimensions
        array_width = (self.cols - 1) * self.pitch_mm
        array_height = (self.rows - 1) * self.pitch_mm

        # Starting position (top-left of array)
        start_x = center_x - array_width / 2.0
        start_y = center_y - array_height / 2.0

        # Generate grid positions
        for row in range(self.rows):
            for col in range(self.cols):
                x = start_x + col * self.pitch_mm
                y = start_y + row * self.pitch_mm
                positions.append((x, y))

        return positions


class NetClassRules(BaseModel):
    """Routing rules for a net class.

    Defines the physical parameters for traces in a given net class,
    including width, clearance, and via specifications.

    Attributes:
        name: Net class name (e.g., 'Power', 'Signal', 'HighSpeed')
        trace_width: Trace width in mm
        clearance: Minimum clearance to other traces in mm
        via_diameter: Via pad diameter in mm (for single vias)
        via_drill: Via drill diameter in mm (for single vias)
        via_template: Via array template name (e.g., 'Via2x2' for high-current)
        creepage_mm: Creepage distance for high-voltage nets
        target_impedance: Target impedance in ohms (for controlled impedance)
        dru_priority: Lower value emits earlier in DRU trace-width section
        required_layer: KiCad layer name or None for no constraint
        safety_category: Safety classification for HV/LV/isolation checks
    """

    model_config = ConfigDict(frozen=True)

    name: str
    trace_width: float  # mm
    clearance: float  # mm
    via_diameter: float = 0.6  # mm
    via_drill: float = 0.3  # mm
    via_template: str | None = None  # Via array template name
    creepage_mm: float = 0.0  # Creepage distance for high-voltage nets
    target_impedance: float | None = None  # Target impedance in ohms

    def __init__(self, name: str = "", **data: object) -> None:
        # Accept a positional name for ergonomics so callers can write
        # ``NetClassRules("HighVoltage", trace_width=0.5)`` instead of
        # ``NetClassRules(name="HighVoltage", trace_width=0.5)``.
        if name and "name" not in data:
            data["name"] = name
        super().__init__(**data)
    voltage_v: float = 0.0  # Voltage rating for safety distance calculation
    routing_strategy: str | None = (
        None  # Routing strategy: "plane_required", "plane_preferred", "wide_trace", "standard"
    )
    via_cost_multiplier: float = 1.0  # Multiplier for via cost (higher = fewer vias)
    layer_costs: dict[str, float] | None = (
        None  # Layer-specific cost multipliers {"F.Cu": 10.0, "In1.Cu": 0.1, ...}
    )
    dru_priority: int = 0  # lower emits earlier in DRU trace-width section (required)
    required_layer: str | None = None  # KiCad layer name or None for no constraint
    safety_category: Literal["HV", "LV", "AC", "iso"] | None = None


@dataclass
class DesignRules:
    print("DEBUG: Loading design_rules.py")
    """PCB Design Rules Module.with net class support.

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
    net_class_assignments: dict[str, str] = field(default_factory=dict)
    differential_pairs: list[DifferentialPairConstraint] = field(default_factory=list)
    bus_cohorts: list[BusCohortConstraint] = field(default_factory=list)
    net_topologies: dict[str, NetGraph] = field(default_factory=dict)
    via_templates: dict[str, ViaTemplate] = field(
        default_factory=lambda: {
            "Via1x1": ViaTemplate("Via1x1", 1, 1, 0.6, 0.3, 1.0),
            "Via2x2": ViaTemplate("Via2x2", 2, 2, 0.6, 0.3, 1.2),
            "Via3x3": ViaTemplate("Via3x3", 3, 3, 0.6, 0.3, 1.2),
            "Via4x4": ViaTemplate("Via4x4", 4, 4, 0.6, 0.3, 1.2),
        }
    )

    def get_via_template(self, net_name: str) -> ViaTemplate:
        """Get via template for a specific net.

        Args:
            net_name: Net name

        Returns:
            ViaTemplate to use for this net
        """
        rules = self.get_rules_for_net(net_name)
        template_name = rules.via_template

        if template_name in self.via_templates:
            return self.via_templates[template_name]

        # Fallback to 1x1 if template not found
        return self.via_templates["Via1x1"]

    def get_rules_for_net(self, net_name: str, net_class: str | None = None) -> NetClassRules:
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

        # Check explicit net class assignment
        if not net_class and net_name in self.net_class_assignments:
            net_class = self.net_class_assignments[net_name]

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
            dru_priority=999,
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
            "VCC",
            "VDD",
            "V+",
            "V-",
            "VBAT",
            "VIN",
            "VOUT",
            "+5V",
            "+3.3V",
            "+12V",
            "-12V",
            "+3V3",
            "+5V0",
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

    def get_diff_pair_for_net(self, net_name: str) -> DifferentialPairConstraint | None:
        """Get differential pair constraint if net is part of a pair.

        Args:
            net_name: Net name to check

        Returns:
            DifferentialPairConstraint if net is part of a differential pair, None otherwise
        """
        for pair in self.differential_pairs:
            if pair.net_pos == net_name or pair.net_neg == net_name:
                return pair
        return None

    def get_bus_cohort_for_net(self, net_name: str) -> BusCohortConstraint | None:
        """Get bus cohort constraint if net is part of a bus.

        Args:
            net_name: Net name to check

        Returns:
            BusCohortConstraint if net is part of a bus, None otherwise
        """
        for bus in self.bus_cohorts:
            if net_name in bus.nets:
                return bus
        return None


# =============================================================================
# Standard Net Classes for Temper Project
# =============================================================================

TEMPER_NET_CLASSES = {
    "ACMains": NetClassRules(
        name="ACMains",
        trace_width=2.5,
        clearance=6.0,
        via_diameter=1.2,
        via_drill=0.6,
        via_template="Via2x2",
        voltage_v=240.0,
        creepage_mm=6.0,
        routing_strategy="plane_required",
        dru_priority=10,
        required_layer=None,
        safety_category="AC",
    ),
    "HighVoltage": NetClassRules(
        name="HighVoltage",
        trace_width=3.0,
        clearance=2.0,
        via_diameter=1.2,
        via_drill=0.6,
        via_template="Via3x3",
        voltage_v=400.0,
        creepage_mm=2.0,
        routing_strategy="plane_required",
        dru_priority=20,
        required_layer="B.Cu",
        safety_category="HV",
    ),
    "FinePitch": NetClassRules(
        name="FinePitch",
        trace_width=0.127,
        clearance=0.1,
        via_diameter=0.4,
        via_drill=0.2,
        via_template="Via1x1",
        dru_priority=30,
        required_layer=None,
        safety_category="LV",
    ),
    "Power": NetClassRules(
        name="Power",
        trace_width=0.5,
        clearance=0.25,
        via_diameter=0.8,
        via_drill=0.4,
        via_template="Via2x2",
        dru_priority=40,
        required_layer=None,
        safety_category="LV",
    ),
    "GateDrive": NetClassRules(
        name="GateDrive",
        trace_width=0.4,
        clearance=0.25,
        via_diameter=0.8,
        via_drill=0.4,
        via_template="Via1x1",
        dru_priority=50,
        required_layer="F.Cu",
        safety_category="LV",
    ),
    "GND": NetClassRules(
        name="GND",
        trace_width=1.0,
        clearance=0.3,
        via_diameter=1.0,
        via_drill=0.5,
        via_template="Via3x3",
        dru_priority=60,
        required_layer=None,
        safety_category="LV",
    ),
    "HighSpeed": NetClassRules(
        name="HighSpeed",
        trace_width=0.15,
        clearance=0.2,
        via_diameter=0.6,
        via_drill=0.3,
        target_impedance=50.0,
        via_template="Via1x1",
        dru_priority=70,
        required_layer=None,
        safety_category="LV",
    ),
    "Signal": NetClassRules(
        name="Signal",
        trace_width=0.2,
        clearance=0.15,
        via_diameter=0.6,
        via_drill=0.3,
        via_template="Via1x1",
        dru_priority=80,
        required_layer=None,
        safety_category="LV",
    ),
    "HighCurrent": NetClassRules(
        name="HighCurrent",
        trace_width=0.5,
        clearance=0.25,
        via_diameter=0.8,
        via_drill=0.4,
        via_template="Via4x4",
        dru_priority=90,
        required_layer=None,
        safety_category="HV",
    ),
}



# Net class assignments matching KiCad project (temper.kicad_pro)
TEMPER_NET_ASSIGNMENTS = {
    # ACMains - Mains voltage (240V AC)
    "AC_L": "ACMains",
    "AC_N": "ACMains",
    "PE": "ACMains",
    # HighVoltage - DC bus (300-400V DC)
    "DC_BUS+": "HighVoltage",
    "DC_BUS-": "HighVoltage",
    "SW_NODE": "HighVoltage",
    # FinePitch - Dense IC connections
    "PWM_H": "FinePitch",
    "PWM_L": "FinePitch",
}


# -----------------------------------------------------------------------------
# Safety constant single source of truth (SSOT).
# Every consumer needing a safety clearance MUST reference TEMPER_NET_CLASSES
# (or SAFETY_CONSTANT_AUTHORITY derived from it) instead of repeating the float.
# Duplicating a bare float that appears here outside this module is blocked by
# the AST linter at packages/temper-drc/tests/test_safety_constant_lint.py.
# -----------------------------------------------------------------------------
SAFETY_CONSTANT_AUTHORITY_NET_CLASSES: frozenset[str] = frozenset({"ACMains", "HighVoltage"})
SAFETY_CONSTANT_AUTHORITY_FIELDS: frozenset[str] = frozenset({"clearance", "creepage_mm"})

SAFETY_CONSTANT_AUTHORITY: tuple[tuple[str, str, float], ...] = tuple(
    (nc_name, field_name, float(getattr(nc, field_name)))
    for nc_name, nc in TEMPER_NET_CLASSES.items()
    if nc_name in SAFETY_CONSTANT_AUTHORITY_NET_CLASSES
    for field_name in SAFETY_CONSTANT_AUTHORITY_FIELDS
)


def create_temper_design_rules() -> DesignRules:
    """Create design rules with Temper-specific net classes.

    Returns:
        DesignRules configured for Temper project requirements
    """
    return DesignRules(
        default_trace_width=0.2,
        default_clearance=0.15,  # Relaxed from 0.2mm to allow signal density (Targeted Reduction)
        default_via_diameter=0.6,
        default_via_drill=0.3,
        net_classes=deepcopy(TEMPER_NET_CLASSES),
        net_class_assignments=deepcopy(TEMPER_NET_ASSIGNMENTS),
    )

