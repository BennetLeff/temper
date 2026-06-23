"""
Type-safe net classification and connectivity semantics.

This module encodes PCB design rules into the type system, making it impossible
to misconfigure critical nets like ground (which MUST connect via planes) or
high-voltage nets (which MUST have creepage clearances).

Key Design Principles:
1. Ground nets connect via planes, NEVER via trace routing
2. Power rails use planes or wide pours with via arrays
3. High-voltage nets require specific clearances per IEC 60335
4. Signal nets can be trace-routed with appropriate widths

Usage in YAML:
    net_classes:
      GND:
        type: ground
        connectivity: plane
        target_layer: In1.Cu

      "+15V":
        type: power
        connectivity: plane
        target_layer: In2.Cu
        max_current_a: 2.0

      AC_L:
        type: high_voltage
        connectivity: copper_pour
        voltage_class: mains_240v
        creepage_mm: 6.0

      SPI_CLK:
        type: signal
        connectivity: trace
        impedance_ohm: 50
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import FrozenSet, List, Optional, Set
from .board import LayerIndex


class NetType(Enum):
    """
    Fundamental classification of net function.

    Each type has inherent routing requirements that cannot be overridden.
    """

    GROUND = auto()  # Return current path - MUST use planes
    POWER = auto()  # Power distribution - planes or wide traces
    HIGH_VOLTAGE = auto()  # Safety-critical - requires creepage/clearance
    SIGNAL = auto()  # General signals - trace routing
    DIFFERENTIAL = auto()  # Paired signals - coupled routing
    HIGH_CURRENT = auto()  # >5A - requires copper pours or via arrays


class ConnectivityStrategy(Enum):
    """
    How a net achieves electrical connectivity.

    Some strategies are REQUIRED for certain net types:
    - GROUND → PLANE (enforced)
    - HIGH_VOLTAGE → COPPER_POUR (enforced)
    - SIGNAL → TRACE (default)
    """

    PLANE = auto()  # Connect via inner layer plane (GND, power)
    COPPER_POUR = auto()  # Connect via filled zone on outer layer (HV)
    TRACE = auto()  # Connect via routed traces
    VIA_ARRAY = auto()  # High-current via stitching
    DIRECT = auto()  # PTH pins directly connect (no routing needed)


class VoltageClass(Enum):
    """
    IEC 60335 voltage classifications for creepage/clearance.

    Reference: IEC 60335-1:2020 Table 16
    """

    SELV = auto()  # Safety Extra Low Voltage (<60V DC, <25V AC)
    LOW_VOLTAGE = auto()  # <50V DC, basic insulation
    MAINS_120V = auto()  # 120V AC (North America)
    MAINS_240V = auto()  # 240V AC (Europe, Asia)
    HIGH_VOLTAGE = auto()  # >1000V DC or >600V AC

    def get_clearance_mm(self, pollution_degree: int = 2) -> float:
        """
        Get minimum clearance (through air) per IEC 60335.

        Args:
            pollution_degree: 1=sealed, 2=normal, 3=conductive pollution

        Returns:
            Minimum clearance in mm
        """
        # IEC 60335-1 Table 16 (basic insulation, pollution degree 2)
        clearances = {
            VoltageClass.SELV: 0.5,
            VoltageClass.LOW_VOLTAGE: 1.0,
            VoltageClass.MAINS_120V: 1.5,
            VoltageClass.MAINS_240V: 3.0,
            VoltageClass.HIGH_VOLTAGE: 8.0,
        }
        base = clearances.get(self, 3.0)

        # Adjust for pollution degree
        if pollution_degree == 3:
            return base * 1.5
        elif pollution_degree == 1:
            return base * 0.8
        return base

    def get_creepage_mm(self, material_group: int = 2) -> float:
        """
        Get minimum creepage (along surface) per IEC 60335.

        Args:
            material_group: 1=best, 2=typical FR4, 3=worst CTI

        Returns:
            Minimum creepage in mm
        """
        # IEC 60335-1 Table 17 (basic insulation, material group II)
        creepages = {
            VoltageClass.SELV: 0.5,
            VoltageClass.LOW_VOLTAGE: 1.6,
            VoltageClass.MAINS_120V: 2.5,
            VoltageClass.MAINS_240V: 5.0,  # 6.3mm for reinforced
            VoltageClass.HIGH_VOLTAGE: 14.0,
        }
        base = creepages.get(self, 5.0)

        # Adjust for material group
        if material_group == 3:
            return base * 1.4
        elif material_group == 1:
            return base * 0.8
        return base


@dataclass(frozen=True)
class NetTypeSpec:
    """
    Complete specification for a net's electrical characteristics.

    This is immutable to prevent accidental modification after validation.
    """

    net_type: NetType
    connectivity: ConnectivityStrategy
    target_layer: str = "F.Cu"  # Default layer for connectivity

    # Electrical properties
    voltage_class: VoltageClass = VoltageClass.SELV
    max_current_a: float = 0.5  # Maximum current in Amps
    impedance_ohm: Optional[float] = None  # Target impedance

    # Physical requirements
    trace_width_mm: float = 0.2
    clearance_mm: float = 0.2
    creepage_mm: float = 0.0  # Additional creepage beyond clearance
    via_template: str = "Via1x1"

    # Routing hints
    allow_layer_change: bool = True
    prefer_short_stubs: bool = False  # For power integrity

    def validate(self) -> List[str]:
        """
        Validate that the spec is internally consistent.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Ground MUST use plane connectivity
        if self.net_type == NetType.GROUND:
            if self.connectivity not in (ConnectivityStrategy.PLANE, ConnectivityStrategy.DIRECT):
                errors.append(
                    f"Ground nets MUST use PLANE or DIRECT connectivity, not {self.connectivity.name}. "
                    "Ground planes provide low-impedance return paths essential for EMI control."
                )

        # High voltage MUST have creepage
        if self.net_type == NetType.HIGH_VOLTAGE:
            min_creepage = self.voltage_class.get_creepage_mm()
            if self.creepage_mm < min_creepage:
                errors.append(
                    f"High voltage net ({self.voltage_class.name}) requires creepage >= {min_creepage}mm, "
                    f"got {self.creepage_mm}mm. Reference: IEC 60335-1 Table 17"
                )
            if self.clearance_mm < self.voltage_class.get_clearance_mm():
                errors.append(
                    f"High voltage net ({self.voltage_class.name}) requires clearance >= "
                    f"{self.voltage_class.get_clearance_mm()}mm, got {self.clearance_mm}mm. "
                    "Reference: IEC 60335-1 Table 16"
                )

        # High current needs appropriate via arrays
        if self.net_type == NetType.HIGH_CURRENT or self.max_current_a > 5.0:
            if self.via_template == "Via1x1":
                errors.append(
                    f"High current net ({self.max_current_a}A) should use Via2x2 or larger, "
                    "not single vias. Single 0.3mm vias rated ~3-5A max."
                )

        # Differential pairs need matched impedance
        if self.net_type == NetType.DIFFERENTIAL:
            if self.impedance_ohm is None:
                errors.append(
                    "Differential pairs should specify target impedance for controlled routing."
                )

        return errors

    def is_valid(self) -> bool:
        """Check if spec passes all validations."""
        return len(self.validate()) == 0


# Pre-defined specs for common net types
GROUND_PLANE_SPEC = NetTypeSpec(
    net_type=NetType.GROUND,
    connectivity=ConnectivityStrategy.PLANE,
    target_layer="In1.Cu",
    max_current_a=10.0,
    trace_width_mm=0.5,
    clearance_mm=0.25,
    via_template="Via2x2",
)

POWER_PLANE_SPEC = NetTypeSpec(
    net_type=NetType.POWER,
    connectivity=ConnectivityStrategy.PLANE,
    target_layer="In2.Cu",
    max_current_a=2.0,
    trace_width_mm=0.5,
    clearance_mm=0.3,
    via_template="Via2x2",
)

MAINS_HV_SPEC = NetTypeSpec(
    net_type=NetType.HIGH_VOLTAGE,
    connectivity=ConnectivityStrategy.COPPER_POUR,
    target_layer="F.Cu",
    voltage_class=VoltageClass.MAINS_240V,
    max_current_a=20.0,
    trace_width_mm=2.0,
    clearance_mm=6.0,
    creepage_mm=6.0,
    via_template="Via3x3",
    allow_layer_change=False,  # Keep HV on single layer
)

SIGNAL_SPEC = NetTypeSpec(
    net_type=NetType.SIGNAL,
    connectivity=ConnectivityStrategy.TRACE,
    target_layer="F.Cu",
    max_current_a=0.5,
    trace_width_mm=0.15,
    clearance_mm=0.15,
    via_template="Via1x1",
)


@dataclass
class NetClassification:
    """
    Container for all net classifications in a design.

    Provides type-safe lookup and validation of net connectivity requirements.
    """

    specs: dict[str, NetTypeSpec] = field(default_factory=dict)

    # Auto-classification patterns
    ground_patterns: FrozenSet[str] = frozenset({"GND", "PGND", "CGND", "AGND", "DGND", "VSS"})
    power_patterns: FrozenSet[str] = frozenset(
        {"+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"}
    )
    hv_patterns: FrozenSet[str] = frozenset({"AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"})

    def classify_net(self, net_name: str) -> NetTypeSpec:
        """
        Get or auto-classify a net's type specification.

        Args:
            net_name: Name of the net

        Returns:
            NetTypeSpec for this net (auto-generated if not explicitly defined)
        """
        # Check explicit specs first
        if net_name in self.specs:
            return self.specs[net_name]

        upper = net_name.upper()

        # Ground nets
        if any(pattern in upper for pattern in self.ground_patterns):
            return GROUND_PLANE_SPEC

        # Power rails
        if any(pattern in upper for pattern in self.power_patterns):
            return POWER_PLANE_SPEC

        # High voltage
        if any(pattern in upper for pattern in self.hv_patterns):
            return MAINS_HV_SPEC

        # Default to signal
        return SIGNAL_SPEC

    def get_plane_nets(self) -> Set[str]:
        """Get all nets that should connect via planes."""
        plane_nets = set()
        for name, spec in self.specs.items():
            if spec.connectivity == ConnectivityStrategy.PLANE:
                plane_nets.add(name)
        return plane_nets

    def get_pour_nets(self) -> Set[str]:
        """Get all nets that should connect via copper pours."""
        pour_nets = set()
        for name, spec in self.specs.items():
            if spec.connectivity == ConnectivityStrategy.COPPER_POUR:
                pour_nets.add(name)
        return pour_nets

    def validate_all(self) -> dict[str, List[str]]:
        """
        Validate all net specifications.

        Returns:
            Dict of net_name -> list of validation errors
        """
        errors = {}
        for name, spec in self.specs.items():
            spec_errors = spec.validate()
            if spec_errors:
                errors[name] = spec_errors
        return errors

    @classmethod
    def from_yaml_config(cls, net_classes: dict, net_class_rules: dict) -> "NetClassification":
        """
        Create NetClassification from YAML config dictionaries.

        Args:
            net_classes: Dict of net_name -> class_name
            net_class_rules: Dict of class_name -> rule config

        Returns:
            Populated NetClassification
        """
        classification = cls()

        for net_name, class_name in net_classes.items():
            rule = net_class_rules.get(class_name, {})

            # Determine net type from class name or explicit config
            net_type_str = rule.get("type", class_name.lower())
            net_type = _parse_net_type(net_type_str, class_name)

            # Determine connectivity strategy
            connectivity_str = rule.get("connectivity", _default_connectivity(net_type))
            connectivity = _parse_connectivity(connectivity_str)

            # Parse voltage class for HV nets
            voltage_class = VoltageClass.SELV
            if net_type == NetType.HIGH_VOLTAGE:
                vc_str = rule.get("voltage_class", "mains_240v")
                voltage_class = _parse_voltage_class(vc_str)

            spec = NetTypeSpec(
                net_type=net_type,
                connectivity=connectivity,
                target_layer=rule.get("target_layer", _default_layer(net_type)),
                voltage_class=voltage_class,
                max_current_a=rule.get("max_current_a", rule.get("max_current_rating", 0.5)),
                impedance_ohm=rule.get("target_impedance"),
                trace_width_mm=rule.get("trace_width_mm", 0.2),
                clearance_mm=rule.get("clearance_mm", 0.2),
                creepage_mm=rule.get("creepage_mm", 0.0),
                via_template=rule.get("via_template", "Via1x1"),
                allow_layer_change=rule.get("allow_layer_change", True),
            )

            classification.specs[net_name] = spec

        return classification


def _parse_net_type(type_str: str, class_name: str) -> NetType:
    """Parse net type from string."""
    type_str = type_str.lower()

    if "ground" in type_str or "gnd" in type_str:
        return NetType.GROUND
    elif "power" in type_str or "vcc" in type_str or "vdd" in type_str:
        return NetType.POWER
    elif "high_voltage" in type_str or "hv" in type_str or "highvoltage" in type_str:
        return NetType.HIGH_VOLTAGE
    elif "differential" in type_str or "diff" in type_str:
        return NetType.DIFFERENTIAL
    elif "high_current" in type_str:
        return NetType.HIGH_CURRENT
    else:
        return NetType.SIGNAL


def _parse_connectivity(conn_str: str) -> ConnectivityStrategy:
    """Parse connectivity strategy from string."""
    conn_str = conn_str.lower()

    if "plane" in conn_str:
        return ConnectivityStrategy.PLANE
    elif "pour" in conn_str or "copper" in conn_str:
        return ConnectivityStrategy.COPPER_POUR
    elif "via_array" in conn_str or "viaarray" in conn_str:
        return ConnectivityStrategy.VIA_ARRAY
    elif "direct" in conn_str:
        return ConnectivityStrategy.DIRECT
    else:
        return ConnectivityStrategy.TRACE


def _parse_voltage_class(vc_str: str) -> VoltageClass:
    """Parse voltage class from string."""
    vc_str = vc_str.lower()

    if "selv" in vc_str:
        return VoltageClass.SELV
    elif "240" in vc_str or "euro" in vc_str:
        return VoltageClass.MAINS_240V
    elif "120" in vc_str or "us" in vc_str:
        return VoltageClass.MAINS_120V
    elif "high" in vc_str or "1000" in vc_str:
        return VoltageClass.HIGH_VOLTAGE
    elif "low" in vc_str:
        return VoltageClass.LOW_VOLTAGE
    else:
        return VoltageClass.MAINS_240V  # Conservative default


def _default_connectivity(net_type: NetType) -> str:
    """Get default connectivity strategy for net type."""
    defaults = {
        NetType.GROUND: "plane",
        NetType.POWER: "plane",
        NetType.HIGH_VOLTAGE: "copper_pour",
        NetType.HIGH_CURRENT: "via_array",
        NetType.SIGNAL: "trace",
        NetType.DIFFERENTIAL: "trace",
    }
    return defaults.get(net_type, "trace")


def _default_layer(net_type: NetType) -> LayerIndex:
    """Get default target layer for net type."""
    defaults: dict[NetType, LayerIndex] = {
        NetType.GROUND: LayerIndex.IN1_CU,  # Inner ground plane
        NetType.POWER: LayerIndex.IN2_CU,  # Inner power plane
        NetType.HIGH_VOLTAGE: LayerIndex.F_CU,  # Top copper pour
        NetType.HIGH_CURRENT: LayerIndex.F_CU,
        NetType.SIGNAL: LayerIndex.F_CU,
        NetType.DIFFERENTIAL: LayerIndex.F_CU,
    }
    return defaults.get(net_type, LayerIndex.F_CU)
