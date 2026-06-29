import math
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix, DesignRulesParser
from temper_placer.router_v6.constraints_drc_oracle import DRCOracle
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.constraints_spatial_index import Pad

from ..state import BoardState
from .base import Stage

if TYPE_CHECKING:
    from temper_placer.core.design_rules import DesignRules


@dataclass
class DRCOracleSetupStage(Stage):
    """Setup stage for initializing DRCOracle and other common utilities.

    Args:
        design_rules: Design rules configuration
        parsed_pads: Optional list of PadData from kicad_parser. If provided,
            these are used for DRC oracle instead of computing from placements.
            This ensures DRC uses the actual KiCad positions, not optimized placements.
    """

    design_rules: "DesignRules | None" = None
    parsed_pads: "list | None" = None  # List of PadData from kicad_parser

    @property
    def name(self) -> str:
        return "drc_oracle_setup"

    def _rotate_point(
        self, point: tuple[float, float], angle_degrees: float
    ) -> tuple[float, float]:
        """Rotate a point by angle_degrees around (0,0)."""
        angle_rad = math.radians(angle_degrees)
        x, y = point
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)

    def run(self, state: BoardState) -> BoardState:
        # Initialize ClearanceMatrix
        if self.design_rules:
            # Use provided design rules if available
            matrix = ClearanceMatrix()

            # Handle both DesignRules and PlacementConstraints (config)
            # DesignRules has: .net_classes (dict of NetClassRules), .net_class_assignments
            # PlacementConstraints has: .net_class_rules (dict of NetClassRule), .net_classes

            if hasattr(self.design_rules, "net_class_rules"):
                # This is a PlacementConstraints object (config)
                for _name, rules in self.design_rules.net_class_rules.items():
                    # Convert NetClassRule to NetClassRules format
                    from temper_placer.core.design_rules import NetClassRules

                    net_class_rules = NetClassRules(
                        name=rules.name,
                        trace_width=rules.trace_width_mm,
                        clearance=rules.clearance_mm,
                        via_diameter=rules.via_size_mm,
                        via_drill=rules.via_drill_mm,
                        via_template=rules.via_template,
                        creepage_mm=rules.creepage_mm,
                        dru_priority=getattr(rules, "dru_priority", 0),
                    )
                    matrix.add_net_class_rules(net_class_rules)

                # net_classes is {net_name: class_name}
                for net, class_name in self.design_rules.net_classes.items():
                    matrix.set_net_class(net, class_name)
            else:
                # This is a DesignRules object
                for _name, rules in self.design_rules.net_classes.items():
                    matrix.add_net_class_rules(rules)
                for net, class_name in self.design_rules.net_class_assignments.items():
                    matrix.set_net_class(net, class_name)

            # Register differential pairs with their configured spacing
            # This allows the DRC system to use relaxed clearance for diff pairs
            if (
                hasattr(self.design_rules, "differential_pairs")
                and self.design_rules.differential_pairs
            ):
                for pair in self.design_rules.differential_pairs:
                    matrix.add_differential_pair(pair.net_pos, pair.net_neg, pair.spacing_mm)
                    print(
                        f"  Clearance matrix now returns: {matrix.get_clearance(pair.net_pos, pair.net_neg)}mm"
                    )
        elif state.board:
            # Try to parse from board (handles zones)
            matrix = ClearanceMatrix.parse(state.board)
        else:
            matrix = DesignRulesParser.create_default()

        # Create DRCOracle
        oracle = DRCOracle(rules=matrix)

        # Register pads - prefer parsed_pads (actual KiCad positions) over computed from placements
        if self.parsed_pads:
            # Use parsed pads directly from KiCad file - these have correct absolute positions
            for pad_data in self.parsed_pads:
                # Map layer name to index
                layer_idx = 0
                pad_layer = getattr(pad_data, "layer", "F.Cu")

                # Check if PTH: layer is "all" or "*.Cu", or has a drill hole
                drill = getattr(pad_data, "drill", None)
                has_drill = drill is not None and (
                    (isinstance(drill, (int, float)) and drill > 0)
                    or (hasattr(drill, "diameter") and drill.diameter and drill.diameter > 0)
                )
                is_pth = pad_layer in ["all", "*.Cu"] or has_drill

                if pad_layer == "B.Cu":
                    layer_idx = 3
                elif pad_layer == "In1.Cu":
                    layer_idx = 1
                elif pad_layer == "In2.Cu":
                    layer_idx = 2
                else:
                    layer_idx = 0

                # Use sentinel net for unconnected pads
                pad_net = pad_data.net if pad_data.net else "__UNCONNECTED__"

                # Determine shape
                shape = getattr(pad_data, "shape", "rect")
                if shape not in ["circle", "rect", "oval"]:
                    shape = "rect"

                oracle.register_pad(
                    Pad(
                        center=Point(pad_data.position[0], pad_data.position[1]),
                        shape=shape,
                        size=pad_data.size,
                        net=pad_net,
                        layer=layer_idx,
                        id=f"{pad_data.component_ref}.{pad_data.number}",
                        rotation=getattr(pad_data, "rotation", 0.0),
                        mask_expansion=0.1,
                        is_pth=is_pth,
                    )
                )

            oracle.geometry.rebuild_index()

        elif state.board and state.netlist:
            # Fallback: compute from component placements (may not match KiCad positions)
            placements_dict = dict(state.placements) if state.placements else {}

            for component in state.netlist.components:
                # Use placement from BoardState if available, otherwise initial
                pos = placements_dict.get(component.ref, component.initial_position)
                if pos is None:
                    continue

                # Component rotation: index to degrees (0=0, 1=90, 2=180, 3=270)
                rot_idx = component.initial_rotation or 0
                rotation = rot_idx * 90.0

                for pin in component.pins:
                    # Pad position with rotation and side awareness
                    pin_pos = pin_world_position(pin, component)

                    # Map layer name to index
                    layer_idx = 0
                    pin_layer = getattr(pin, "layer", "F.Cu")
                    is_pth = pin_layer == "all" or pin.is_pth

                    if pin_layer == "B.Cu":
                        layer_idx = 3
                    elif pin_layer == "In1.Cu":
                        layer_idx = 1
                    elif pin_layer == "In2.Cu":
                        layer_idx = 2
                    else:
                        layer_idx = 0

                    # Create Pad object for DRCOracle
                    # Use sentinel net for unconnected pads so Oracle still validates
                    # against them (fixes J_DEBUG pin 6 vs DC_BUS+ shorting)
                    pad_net = pin.net if pin.net else "__UNCONNECTED__"
                    oracle.register_pad(
                        Pad(
                            center=Point(pin_pos[0], pin_pos[1]),
                            shape=getattr(pin, "shape", "rect")
                            if getattr(pin, "shape", "rect") in ["circle", "rect", "oval"]
                            else "rect",
                            size=(getattr(pin, "width", 1.0), getattr(pin, "height", 1.0)),
                            net=pad_net,
                            layer=layer_idx,
                            id=f"{component.ref}.{pin.number}",
                            rotation=rotation,  # Pad rotation follows component rotation
                            mask_expansion=getattr(pin, "mask_expansion", 0.1),
                            is_pth=is_pth,
                        )
                    )

            oracle.geometry.rebuild_index()

        return replace(state, drc_oracle=oracle)


@dataclass
class NetClassSetupStage(Stage):
    """Setup stage to apply net class mapping from config to netlist.

    This stage should run early in the pipeline to ensure net classes
    are properly assigned before routing decisions are made.
    """

    net_classes: "dict[str, str] | None" = None

    @property
    def name(self) -> str:
        return "net_class_setup"

    def run(self, state: BoardState) -> BoardState:
        if not state.netlist or not self.net_classes:
            return state

        # Apply net class mapping to netlist
        updated = state.netlist.apply_net_class_mapping(self.net_classes)
        if updated > 0:
            print(f"  Applied net class mapping to {updated} nets")

        return state  # Netlist is mutated in place


# Alias for backward compatibility
SetupStage = DRCOracleSetupStage
