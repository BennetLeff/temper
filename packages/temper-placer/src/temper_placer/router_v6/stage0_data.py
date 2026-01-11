"""
Router V6 Stage 0: Design Intent Data Structures

Defines ParsedPCB and DesignIntent for Router V6 topological architecture.
See docs/architecture/ROUTER_V6_TOPOLOGICAL_ARCHITECTURE.md

Part of temper-y7j2 (Stage 0.1: Load KiCad PCB File)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net


@dataclass
class LayerInfo:
    """PCB copper layer definition."""

    index: int  # 0=F.Cu, 1=In1.Cu, 2=In2.Cu, 3=B.Cu
    name: str  # "F.Cu", "In1.Cu", etc.
    layer_type: str  # "signal", "plane", "mixed"
    thickness_um: float  # Copper thickness in micrometers (35µm = 1oz)
    plane_net: str | None = None  # "GND", "+15V" for plane layers


@dataclass
class StackupInfo:
    """PCB layer stackup definition."""

    layers: list[LayerInfo]
    total_thickness_mm: float
    layer_count: int

    @property
    def signal_layers(self) -> list[int]:
        """Return indices of signal routing layers."""
        return [layer.index for layer in self.layers if layer.layer_type == "signal"]

    @property
    def plane_layers(self) -> dict[int, str]:
        """Return mapping of plane layer index to net name."""
        return {
            layer.index: layer.plane_net
            for layer in self.layers
            if layer.layer_type == "plane" and layer.plane_net
        }

    def get_reference_plane(self, signal_layer: int) -> int | None:
        """Return adjacent plane layer for return current reference."""
        # Simple heuristic: nearest plane layer
        plane_indices = list(self.plane_layers.keys())
        if not plane_indices:
            return None

        # Find closest plane layer
        closest = min(plane_indices, key=lambda p: abs(p - signal_layer))
        return closest


@dataclass
class NetClassRules:
    """Design rules for a net class."""

    name: str
    clearance_mm: float
    trace_width_mm: float
    via_diameter_mm: float
    via_drill_mm: float
    diff_pair_gap_mm: float | None = None
    diff_pair_width_mm: float | None = None
    current_rating_amps: float | None = None


@dataclass
class DesignRules:
    """KiCad design rules extracted from board setup."""

    net_classes: dict[str, NetClassRules]  # class_name -> rules
    net_class_assignments: dict[str, str]  # net_name -> class_name
    default_clearance_mm: float
    default_trace_width_mm: float
    default_via_diameter_mm: float
    default_via_drill_mm: float
    min_hole_to_hole_mm: float = 0.25
    min_annular_ring_mm: float = 0.1

    def get_rules_for_net(self, net_name: str) -> NetClassRules:
        """Get design rules for a specific net."""
        class_name = self.net_class_assignments.get(net_name, "Signal")
        if class_name in self.net_classes:
            return self.net_classes[class_name]

        #  Fallback: default rules
        return NetClassRules(
            name="Default",
            clearance_mm=self.default_clearance_mm,
            trace_width_mm=self.default_trace_width_mm,
            via_diameter_mm=self.default_via_diameter_mm,
            via_drill_mm=self.default_via_drill_mm,
        )


@dataclass
class ParsedPCB:
    """
    Complete parsed PCB data from KiCad file.

    Output of Router V6 Stage 0.1.

    Attributes:
        components: List of Component instances with positions and pins
        nets: List of Net instances with connectivity
        zones: List of Zone instances (copper pours, keepouts)
        board: Board geometry (width, height, origin, mounting holes)
        design_rules: Extracted design rules and net class assignments
        stackup: Layer stackup information
        source_path: Path to source .kicad_pcb file
    """

    components: list[Component]
    nets: list[Net]
    zones: list
    board: Board
    design_rules: DesignRules
    stackup: StackupInfo
    source_path: Path
    warnings: list[str] = field(default_factory=list)

    def validate_placement(self) -> list[str]:
        """
        Validate that all components are placed (precondition for Router V6).

        Returns:
            List of validation errors (empty if all OK)
        """
        errors = []

        if len(self.components) == 0:
            errors.append("No components found in PCB")

        for comp in self.components:
            if comp.initial_position == (0.0, 0.0):
                errors.append(f"Component {comp.ref} at origin (0,0) - possibly unplaced")

        if len(self.nets) == 0:
            errors.append("No nets found in PCB")

        if self.design_rules.default_clearance_mm <= 0:
            errors.append(f"Invalid default clearance: {self.design_rules.default_clearance_mm}mm")

        if self.stackup.layer_count == 0:
            errors.append("No layers defined in stackup")

        return errors
