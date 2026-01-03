"""
Design rules parsing and clearance matrix for DRC.

Extends core.design_rules with KiCad PCB parsing and clearance matrix
for net-class-aware constraint checking.

Part of temper-lueu.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from temper_placer.core.design_rules import (
    NetClassRules,
    create_temper_design_rules,
)

if TYPE_CHECKING:
    from kiutils.board import Board


@dataclass
class ClearanceMatrix:
    """Net-class-aware clearance lookup table.

    Provides O(1) clearance lookups between any two net classes.
    Falls back to default clearance for unknown net classes.
    """

    # Clearance between net classes: (class_a, class_b) -> clearance_mm
    _clearances: dict[tuple[str, str], float] = field(default_factory=dict)
    default_clearance: float = 0.2  # mm
    default_track_width: float = 0.2  # mm
    default_via_diameter: float = 0.6  # mm
    default_via_drill: float = 0.3  # mm

    # Per-net-class rules
    _net_class_rules: dict[str, NetClassRules] = field(default_factory=dict)

    # Net to net-class mapping
    _net_to_class: dict[str, str] = field(default_factory=dict)

    def get_clearance(self, net_a: str, net_b: str) -> float:
        """Get required clearance between two nets.

        Args:
            net_a: First net name
            net_b: Second net name

        Returns:
            Required clearance in mm
        """
        class_a = self._net_to_class.get(net_a, "Default")
        class_b = self._net_to_class.get(net_b, "Default")

        # Try both orderings (matrix is symmetric)
        key1 = (class_a, class_b)
        key2 = (class_b, class_a)

        if key1 in self._clearances:
            return self._clearances[key1]
        if key2 in self._clearances:
            return self._clearances[key2]

        # Fall back to max of individual class clearances
        clear_a = self._get_class_clearance(class_a)
        clear_b = self._get_class_clearance(class_b)
        return max(clear_a, clear_b)

    def get_track_width(self, net: str) -> float:
        """Get required track width for a net.

        Args:
            net: Net name

        Returns:
            Track width in mm
        """
        net_class = self._net_to_class.get(net, "Default")
        if net_class in self._net_class_rules:
            return self._net_class_rules[net_class].trace_width
        return self.default_track_width

    def get_via_diameter(self, net: str) -> float:
        """Get via diameter for a net.

        Args:
            net: Net name

        Returns:
            Via pad diameter in mm
        """
        net_class = self._net_to_class.get(net, "Default")
        if net_class in self._net_class_rules:
            return self._net_class_rules[net_class].via_diameter
        return self.default_via_diameter

    def get_via_drill(self, net: str) -> float:
        """Get via drill diameter for a net.

        Args:
            net: Net name

        Returns:
            Via drill diameter in mm
        """
        net_class = self._net_to_class.get(net, "Default")
        if net_class in self._net_class_rules:
            return self._net_class_rules[net_class].via_drill
        return self.default_via_drill

    def _get_class_clearance(self, net_class: str) -> float:
        """Get clearance for a specific net class."""
        if net_class in self._net_class_rules:
            return self._net_class_rules[net_class].clearance
        return self.default_clearance

    def set_net_class(self, net: str, net_class: str) -> None:
        """Assign a net to a net class.

        Args:
            net: Net name
            net_class: Net class name
        """
        self._net_to_class[net] = net_class

    def add_net_class_rules(self, rules: NetClassRules) -> None:
        """Add rules for a net class.

        Args:
            rules: Net class rules
        """
        self._net_class_rules[rules.name] = rules

    def set_class_to_class_clearance(
        self, class_a: str, class_b: str, clearance: float
    ) -> None:
        """Set clearance between two net classes.

        Args:
            class_a: First net class
            class_b: Second net class
            clearance: Required clearance in mm
        """
        self._clearances[(class_a, class_b)] = clearance
        self._clearances[(class_b, class_a)] = clearance


class DesignRulesParser:
    """Extract design rules from KiCad PCB file.

    Uses kiutils to parse .kicad_pcb files and extract:
    - Net class definitions
    - Clearance rules
    - Track width constraints
    - Via specifications
    """

    @staticmethod
    def parse(pcb: Board) -> ClearanceMatrix:
        """Parse design rules from a KiCad board.

        Args:
            pcb: kiutils Board object

        Returns:
            ClearanceMatrix with parsed rules
        """
        matrix = ClearanceMatrix()

        # Start with Temper defaults
        temper_rules = create_temper_design_rules()
        for _name, rules in temper_rules.net_classes.items():
            matrix.add_net_class_rules(rules)

        # Extract setup rules from board
        if pcb.setup is not None:
            # Default clearance from board setup
            # kiutils stores this in stackup or design rules section
            pass

        # Parse net classes from board
        if hasattr(pcb, "netClasses") and pcb.netClasses:
            for nc in pcb.netClasses:
                rules = NetClassRules(
                    name=nc.name,
                    trace_width=nc.traceWidth if hasattr(nc, "traceWidth") else 0.2,
                    clearance=nc.clearance if hasattr(nc, "clearance") else 0.2,
                    via_diameter=nc.viaDia if hasattr(nc, "viaDia") else 0.6,
                    via_drill=nc.viaDrill if hasattr(nc, "viaDrill") else 0.3,
                )
                matrix.add_net_class_rules(rules)

                # Map nets to this class
                if hasattr(nc, "nets"):
                    for net_name in nc.nets:
                        matrix.set_net_class(net_name, nc.name)

        # Parse nets from board to auto-classify
        if hasattr(pcb, "nets") and pcb.nets:
            for net in pcb.nets:
                net_name = net.name if hasattr(net, "name") else str(net)
                if net_name not in matrix._net_to_class:
                    # Auto-classify based on name patterns
                    class_name = DesignRulesParser._classify_net(net_name)
                    matrix.set_net_class(net_name, class_name)

        return matrix

    @staticmethod
    def parse_from_file(pcb_path: str) -> ClearanceMatrix:
        """Parse design rules from a KiCad PCB file path.

        Args:
            pcb_path: Path to .kicad_pcb file

        Returns:
            ClearanceMatrix with parsed rules
        """
        from kiutils.board import Board

        pcb = Board.from_file(pcb_path)
        return DesignRulesParser.parse(pcb)

    @staticmethod
    def _classify_net(net_name: str) -> str:
        """Auto-classify net based on name patterns.

        Args:
            net_name: Net name to classify

        Returns:
            Net class name
        """
        upper = net_name.upper()

        # Ground patterns
        ground_patterns = ["GND", "GROUND", "VSS", "AGND", "DGND", "PGND"]
        for pattern in ground_patterns:
            if pattern in upper:
                return "GND"

        # Power patterns
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
            if pattern in upper:
                return "Power"

        # High-speed patterns
        high_speed_patterns = ["CLK", "CLOCK", "SPI_", "I2C_", "USB", "JTAG"]
        for pattern in high_speed_patterns:
            if pattern in upper:
                return "HighSpeed"

        return "Signal"

    @staticmethod
    def create_default() -> ClearanceMatrix:
        """Create a ClearanceMatrix with Temper default rules.

        Returns:
            ClearanceMatrix with standard Temper project rules
        """
        matrix = ClearanceMatrix()
        temper_rules = create_temper_design_rules()

        for _name, rules in temper_rules.net_classes.items():
            matrix.add_net_class_rules(rules)

        # Set default cross-class clearances
        matrix.set_class_to_class_clearance("Power", "Power", 0.5)
        matrix.set_class_to_class_clearance("Power", "Signal", 0.3)
        matrix.set_class_to_class_clearance("GND", "Power", 0.3)
        matrix.set_class_to_class_clearance("HighSpeed", "HighSpeed", 0.2)

        return matrix
