from dataclasses import replace, dataclass
from typing import List, Tuple, Optional, Set
from ..state import BoardState
from .base import Stage
from .astar import DeterministicAStar
from .multilayer_astar import MultiLayerAStar
from ...core.board import Trace, Via
from ...core.design_rules import DesignRules
from ...routing.constraints.spatial_index import Track as OracleTrack, Via as OracleVia
from ...routing.constraints.geometry import Point as OraclePoint
from ..geometry.via_placement import PadInfo, place_via_with_clearance
from ..geometry.grid_utils import snap_to_grid, add_endpoint_nudge
from ...routing.layer_assignment import Layer as LayerEnum
from ...routing.diff_pair_router import DiffPairRouter, DiffPairPath
from ...routing.adaptive_congestion import (
    GridBasedCongestionDetector,
    ComponentBasedCongestionDetector,
    CompositeDetector,
)


@dataclass
class DiffPairConfig:
    """Configuration for a differential pair."""

    net_pos: str  # Positive net name (e.g., "USB_D+")
    net_neg: str  # Negative net name (e.g., "USB_D-")
    spacing_mm: float = 0.15  # Target spacing between traces
    coupling_tolerance_mm: float = 0.5  # Max allowed divergence
    max_skew_mm: float = 0.5  # Max length mismatch


# Layer name mappings
LAYER_IDX_TO_NAME = {0: "F.Cu", 1: "In1.Cu", 2: "In2.Cu", 3: "B.Cu"}
LAYER_NAME_TO_IDX = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}

# Layer enum to index mapping
LAYER_ENUM_TO_IDX = {
    LayerEnum.L1_TOP: 0,
    LayerEnum.L2_GND: 1,
    LayerEnum.L3_PWR: 2,
    LayerEnum.L4_BOT: 3,
}


class SequentialRoutingStage(Stage):
    def __init__(
        self,
        design_rules: DesignRules | None = None,
        trace_width_mm: float = 0.25,
        clearance_mm: float = 0.2,
        cost_map_weights: any = None,
        pad_sizes: dict = None,
        net_class_rules: dict = None,
        differential_pairs: List[DiffPairConfig] = None,
    ):
        """Initialize sequential routing stage.

        Args:
            design_rules: DRC rules for trace widths/clearances
            trace_width_mm: Default trace width
            clearance_mm: Default clearance
            cost_map_weights: Unused legacy parameter
            pad_sizes: Pad size lookup for via placement
            net_class_rules: Dict of net_class_name -> NetClassRule with zone confinement info
            differential_pairs: List of differential pair configs for coupled routing
        """
        self.design_rules = design_rules
        self.default_width = trace_width_mm
        self.default_clearance = clearance_mm
        self.pad_sizes = pad_sizes or {}
        self.net_class_rules = net_class_rules or {}
        self.differential_pairs = differential_pairs or []

    @property
    def name(self) -> str:
        return "sequential_routing"

    def _get_allowed_zones(self, net_class_name: str, state: BoardState):
        """Get the list of Zone objects where this net class can route.

        Args:
            net_class_name: Name of the net class (e.g., 'HighVoltage', 'Signal')
            state: BoardState with zone definitions

        Returns:
            List of Zone objects, or None if no restriction
        """
        # TEMPORARILY DISABLED: Zone confinement causes routing timeouts
        # TODO: Re-enable after optimizing A* for zone-aware routing
        # The domain-driven placement should be enough for now
        return None

        if not net_class_name or not self.net_class_rules:
            return None

        rule = self.net_class_rules.get(net_class_name)
        if not rule or not hasattr(rule, "confined_to_zones") or not rule.confined_to_zones:
            return None

        # Convert zone names to Zone objects
        zone_by_name = {z.name: z for z in state.zones}
        allowed_zones = []
        for zone_name in rule.confined_to_zones:
            if zone_name in zone_by_name:
                allowed_zones.append(zone_by_name[zone_name])
            else:
                print(f"WARNING: Zone '{zone_name}' in confined_to_zones not found in board zones")

        return allowed_zones if allowed_zones else None

    def _create_via_array(
        self,
        center: Tuple[float, float],
        net_name: str,
        from_layer_name: str,
        to_layer_name: str,
        via_d: float,
        via_drill: float,
        clearance: float,
        grid,
        state: BoardState,
        all_vias: List,
    ) -> List:
        """Create a via array at the specified position for high-current nets.

        Uses ViaTemplate from design_rules if available, otherwise single via.

        Args:
            center: (x, y) center position in mm
            net_name: Name of the net
            from_layer_name: Source layer name (e.g., 'F.Cu')
            to_layer_name: Target layer name (e.g., 'In1.Cu')
            via_d: Via diameter in mm
            via_drill: Via drill diameter in mm
            clearance: Clearance in mm
            grid: ClearanceGrid for blocking
            state: BoardState with DRC oracle
            all_vias: List to append vias to

        Returns:
            List of Via objects created
        """
        created_vias = []

        # Get via template from design rules
        via_template = None
        if self.design_rules:
            via_template = self.design_rules.get_via_template(net_name)

        # If template is 1x1 or not found, create single via
        if not via_template or via_template.via_count <= 1:
            via = Via(
                position=center,
                drill=via_drill,
                width=via_d,
                layers=(from_layer_name, to_layer_name),
                net=net_name,
            )
            all_vias.append(via)
            created_vias.append(via)

            # Block via on ALL layers
            for l_idx in range(grid.layer_count):
                grid.block_circle(
                    center,
                    radius_mm=via_d / 2,
                    clearance_mm=clearance,
                    layer=l_idx,
                    net_name=net_name,
                    is_pad=False,
                )

            # Register in DRCOracle
            if state.drc_oracle:
                state.drc_oracle.register_via(
                    OracleVia(
                        center=OraclePoint(center[0], center[1]),
                        diameter=via_d,
                        drill=via_drill,
                        net=net_name,
                    )
                )
            return created_vias

        # Create via array
        print(
            f"  [ViaArray] Creating {via_template.name} ({via_template.via_count} vias) for {net_name}"
        )
        positions = via_template.get_via_positions(center[0], center[1])

        for vx, vy in positions:
            via = Via(
                position=(vx, vy),
                drill=via_template.via_drill_mm,
                width=via_template.via_diameter_mm,
                layers=(from_layer_name, to_layer_name),
                net=net_name,
            )
            all_vias.append(via)
            created_vias.append(via)

            # Block via on ALL layers
            for l_idx in range(grid.layer_count):
                grid.block_circle(
                    (vx, vy),
                    radius_mm=via_template.via_diameter_mm / 2,
                    clearance_mm=clearance,
                    layer=l_idx,
                    net_name=net_name,
                    is_pad=False,
                )

            # Register in DRCOracle
            if state.drc_oracle:
                state.drc_oracle.register_via(
                    OracleVia(
                        center=OraclePoint(vx, vy),
                        diameter=via_template.via_diameter_mm,
                        drill=via_template.via_drill_mm,
                        net=net_name,
                    )
                )

        return created_vias

    def _get_allowed_layers_for_net(
        self, net_name: str, net_class_name: str | None, state: BoardState
    ) -> List[int]:
        """Get allowed layer indices for routing a specific net.

        Uses layer assignments from BoardState if available, otherwise falls back
        to net class-based heuristics. This enables multi-layer routing on inner
        layers when outer layers are congested.

        Args:
            net_name: Name of the net being routed
            net_class_name: Net class (e.g., 'HighVoltage', 'Signal', 'SPI')
            state: BoardState containing layer assignments

        Returns:
            List of layer indices (0=F.Cu, 1=In1.Cu, 2=In2.Cu, 3=B.Cu)
        """
        # Check for explicit layer assignment in BoardState
        if state.layer_assignments:
            for assignment in state.layer_assignments:
                if assignment.net_name == net_name and hasattr(assignment, "allowed_layers"):
                    # Convert Layer enum set to indices
                    allowed = []
                    for layer_enum in assignment.allowed_layers:
                        if layer_enum in LAYER_ENUM_TO_IDX:
                            allowed.append(LAYER_ENUM_TO_IDX[layer_enum])
                    if allowed:
                        return sorted(allowed)

        # Net class-based layer assignment strategy
        # Priority: Keep HV on outer layers, allow digital signals on all 4 layers
        net_upper = net_name.upper()
        net_class_upper = (net_class_name or "").upper()

        # High-voltage nets: Outer layers only (L1, L4) for clearance
        if any(
            pattern in net_upper
            for pattern in ["DC_BUS", "HV_", "SW_NODE", "AC_L", "AC_N", "RECT_"]
        ):
            return [0, 3]  # F.Cu and B.Cu only

        # Gate drive: Prefer outer layers but allow inner for escape routing
        if any(pattern in net_upper for pattern in ["GATE_", "DRV_", "PWM_H", "PWM_L", "VCC_BOOT"]):
            return [0, 3]  # F.Cu and B.Cu - keep close to ground plane

        # SPI bus: All 4 layers - these are the most congested nets
        if "SPI_" in net_upper:
            return [0, 1, 2, 3]  # All layers for maximum routing flexibility

        # USB: All 4 layers for differential pair routing
        if "USB_" in net_upper:
            return [0, 1, 2, 3]

        # Analog/sensing: Outer layers preferred but allow inner
        if any(
            pattern in net_upper for pattern in ["SENSE_", "ADC_", "TEMP_", "ANALOG_", "I_SENSE"]
        ):
            return [0, 3]  # Outer layers for noise isolation

        # Power nets that are NOT plane nets (individual connections)
        if any(pattern in net_upper for pattern in ["+15V", "+5V", "+3V3", "VCC_"]):
            return [0, 2, 3]  # Allow In2.Cu (power plane layer) for power routing

        # Ground connections that are NOT plane nets
        if any(pattern in net_upper for pattern in ["GND", "PGND", "CGND"]):
            return [0, 1, 3]  # Allow In1.Cu (ground plane layer)

        # Default: All 4 layers for general signals
        return [0, 1, 2, 3]

    def run(self, state: BoardState) -> BoardState:
        if not state.board or not state.netlist or not state.net_order or not state.grid:
            return state

        grid = state.grid
        net_order = state.net_order
        net_by_name = {n.name: n for n in state.netlist.nets}
        comp_by_ref = {c.ref: c for c in state.netlist.components}

        # Build layer assignment lookup from BoardState
        layer_by_net = {}
        is_plane_by_net = {}
        if state.layer_assignments:
            for assignment in state.layer_assignments:
                layer_by_net[assignment.net_name] = assignment.layer
                if hasattr(assignment, "is_plane"):
                    is_plane_by_net[assignment.net_name] = assignment.is_plane

        all_traces = list(state.routes)
        all_vias = list(state.vias)

        # Gather all pads for via clearance checking
        all_pads_info = []
        for component in state.netlist.components:
            comp_pos = comp_by_ref[component.ref].initial_position or (0, 0)
            for pin in component.pins:
                # Approximate pad radius (assuming circular for clearance)
                pad_r = 0.5
                if self.pad_sizes:
                    real_pad = self.pad_sizes.get((component.ref, pin.name))
                    if real_pad:
                        pad_r = max(real_pad.size.X, real_pad.size.Y) / 2.0

                all_pads_info.append(
                    PadInfo(
                        position=(comp_pos[0] + pin.position[0], comp_pos[1] + pin.position[1]),
                        radius=pad_r,
                        mask_expansion=getattr(pin, "mask_expansion", 0.1),
                    )
                )

        import time

        # ========== CONGESTION-AWARE ROUTING SETUP ==========
        # Create composite congestion detector for adaptive A* iteration budgeting
        # This prevents timeouts in highly congested areas (near fine-pitch ICs)
        grid_detector = GridBasedCongestionDetector(grid=grid)

        # Identify fine-pitch components (QFN-56 and similar packages)
        fine_pitch_refs = set()
        for component in state.netlist.components:
            pin_count = len(component.pins)
            # Heuristic 1: Components with >40 pins are likely fine-pitch
            # Heuristic 2: MCU/TEMP components are typically fine-pitch
            is_fine_pitch = pin_count > 40 or component.ref in {"U_MCU", "U_TEMP", "U_GATE"}
            if is_fine_pitch:
                fine_pitch_refs.add(component.ref)
                print(f"  DEBUG: Detected fine-pitch component {component.ref} ({pin_count} pins)")

        component_detector = ComponentBasedCongestionDetector(
            netlist=state.netlist,
            fine_pitch_components=frozenset(fine_pitch_refs),
        )

        congestion_detector = CompositeDetector(detectors=(grid_detector, component_detector))

        print(
            f"  INFO: Adaptive congestion detection enabled ({len(fine_pitch_refs)} fine-pitch components)"
        )

        # ========== DIFFERENTIAL PAIR ROUTING (before main loop) ==========
        # Route diff pairs first to ensure both traces can be routed together
        # This prevents the common failure where one trace blocks the other
        diff_pair_nets: Set[str] = set()  # Track nets routed as diff pairs

        if self.differential_pairs:
            print(
                f"  [DiffPair] Routing {len(self.differential_pairs)} differential pairs first..."
            )

            for dp_config in self.differential_pairs:
                net_pos_name = dp_config.net_pos
                net_neg_name = dp_config.net_neg

                # Skip if nets don't exist
                if net_pos_name not in net_by_name or net_neg_name not in net_by_name:
                    print(
                        f"  [DiffPair] WARNING: {net_pos_name}/{net_neg_name} not found in netlist, skipping"
                    )
                    continue

                net_pos = net_by_name[net_pos_name]
                net_neg = net_by_name[net_neg_name]

                # Get pin positions for both nets
                def get_pin_positions(net, comp_by_ref):
                    positions = []
                    for comp_ref, pin_name in net.pins:
                        if comp_ref not in comp_by_ref:
                            continue
                        comp = comp_by_ref[comp_ref]
                        pin = next(
                            (p for p in comp.pins if p.name == pin_name or p.number == pin_name),
                            None,
                        )
                        if not pin:
                            continue
                        pos = comp.initial_position or (0, 0)
                        positions.append((pos[0] + pin.position[0], pos[1] + pin.position[1]))
                    return positions

                pos_pins = get_pin_positions(net_pos, comp_by_ref)
                neg_pins = get_pin_positions(net_neg, comp_by_ref)

                if len(pos_pins) != 2 or len(neg_pins) != 2:
                    print(
                        f"  [DiffPair] WARNING: {net_pos_name} has {len(pos_pins)} pins, {net_neg_name} has {len(neg_pins)} pins (expected 2 each)"
                    )
                    continue

                # Determine start/goal pins by matching closest pairs
                # USB typically: MCU pins on one side, connector on other
                # Match P to P and N to N by proximity
                def dist_sq(a, b):
                    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2

                # Find which pos_pins[i] is closer to neg_pins[j]
                # Typically pins at same connector/chip are paired
                if dist_sq(pos_pins[0], neg_pins[0]) < dist_sq(pos_pins[0], neg_pins[1]):
                    # pos_pins[0] pairs with neg_pins[0] (start), [1] pairs with [1] (end)
                    start_pins = (pos_pins[0], neg_pins[0])
                    goal_pins = (pos_pins[1], neg_pins[1])
                else:
                    # pos_pins[0] pairs with neg_pins[1]
                    start_pins = (pos_pins[0], neg_pins[1])
                    goal_pins = (pos_pins[1], neg_pins[0])

                # Get design rules for diff pair
                width = self.default_width
                clearance = self.default_clearance
                if self.design_rules:
                    rules = self.design_rules.get_rules_for_net(
                        net_pos_name, net_class="Differential"
                    )
                    width = rules.trace_width
                    clearance = rules.clearance

                # Build obstacle set from current grid blocked cells
                obstacles: Set[Tuple[int, int, int]] = set()
                for layer_idx in range(grid.layer_count):
                    for x in range(grid.cols):
                        for y in range(grid.rows):
                            if not grid.is_available(
                                x * grid.cell_size_mm, y * grid.cell_size_mm, layer_idx
                            ):
                                obstacles.add((x, y, layer_idx))

                # Create diff pair router
                dp_router = DiffPairRouter(
                    grid_size=(grid.cols, grid.rows, grid.layer_count),
                    cell_size_mm=grid.cell_size_mm,
                    target_separation_mm=dp_config.spacing_mm,
                    max_divergence_mm=dp_config.coupling_tolerance_mm,
                    max_skew_mm=dp_config.max_skew_mm,
                )

                print(f"  [DiffPair] Routing {net_pos_name}/{net_neg_name}...")
                dp_start = time.time()

                result = dp_router.route_pair(
                    start_pins=start_pins,
                    goal_pins=goal_pins,
                    obstacles=obstacles,
                )

                dp_elapsed = time.time() - dp_start

                if not result.success:
                    print(
                        f"  [DiffPair] FAILED: {net_pos_name}/{net_neg_name} - {result.failure_reason}"
                    )
                    continue

                print(
                    f"  [DiffPair] SUCCESS: {net_pos_name}/{net_neg_name} in {dp_elapsed:.2f}s "
                    f"(coupling={result.coupling_ratio:.1%}, skew={result.max_skew_mm:.3f}mm)"
                )

                # Mark these nets as routed via diff pair
                diff_pair_nets.add(net_pos_name)
                diff_pair_nets.add(net_neg_name)

                # Convert grid cells to mm positions
                def cells_to_mm(
                    cells: List[Tuple[int, int, int]],
                ) -> List[Tuple[float, float, int]]:
                    return [
                        (x * grid.cell_size_mm, y * grid.cell_size_mm, layer)
                        for x, y, layer in cells
                    ]

                pos_path_mm = cells_to_mm(result.pos_cells)
                neg_path_mm = cells_to_mm(result.neg_cells)

                # Create Trace objects for P trace
                for i in range(len(pos_path_mm) - 1):
                    p1, p2 = pos_path_mm[i], pos_path_mm[i + 1]
                    layer_name = LAYER_IDX_TO_NAME.get(p1[2], "F.Cu")

                    # Check for layer change -> add via
                    if p1[2] != p2[2]:
                        via_pos = (p1[0], p1[1])
                        from_layer = LAYER_IDX_TO_NAME.get(p1[2], "F.Cu")
                        to_layer = LAYER_IDX_TO_NAME.get(p2[2], "B.Cu")
                        via = Via(
                            position=via_pos,
                            drill=0.3,
                            width=0.6,
                            layers=(from_layer, to_layer),
                            net=net_pos_name,
                        )
                        all_vias.append(via)
                        # Block via on all layers
                        for l_idx in range(grid.layer_count):
                            grid.block_circle(
                                via_pos,
                                radius_mm=0.3,
                                clearance_mm=clearance,
                                layer=l_idx,
                                net_name=net_pos_name,
                            )
                    else:
                        # Same layer -> create trace
                        trace = Trace(
                            start=(p1[0], p1[1]),
                            end=(p2[0], p2[1]),
                            width=width,
                            layer=layer_name,
                            net=net_pos_name,
                        )
                        all_traces.append(trace)
                        # Block trace on grid
                        grid.block_trace(
                            [(p1[0], p1[1]), (p2[0], p2[1])],
                            width_mm=width,
                            clearance_mm=clearance,
                            layer=p1[2],
                            net_name=net_pos_name,
                        )
                        # Register in DRCOracle
                        if state.drc_oracle:
                            state.drc_oracle.register_track(
                                OracleTrack(
                                    start=OraclePoint(p1[0], p1[1]),
                                    end=OraclePoint(p2[0], p2[1]),
                                    width=width,
                                    net=net_pos_name,
                                    layer=p1[2],
                                )
                            )

                # Create Trace objects for N trace
                for i in range(len(neg_path_mm) - 1):
                    p1, p2 = neg_path_mm[i], neg_path_mm[i + 1]
                    layer_name = LAYER_IDX_TO_NAME.get(p1[2], "F.Cu")

                    # Check for layer change -> add via
                    if p1[2] != p2[2]:
                        via_pos = (p1[0], p1[1])
                        from_layer = LAYER_IDX_TO_NAME.get(p1[2], "F.Cu")
                        to_layer = LAYER_IDX_TO_NAME.get(p2[2], "B.Cu")
                        via = Via(
                            position=via_pos,
                            drill=0.3,
                            width=0.6,
                            layers=(from_layer, to_layer),
                            net=net_neg_name,
                        )
                        all_vias.append(via)
                        # Block via on all layers
                        for l_idx in range(grid.layer_count):
                            grid.block_circle(
                                via_pos,
                                radius_mm=0.3,
                                clearance_mm=clearance,
                                layer=l_idx,
                                net_name=net_neg_name,
                            )
                    else:
                        # Same layer -> create trace
                        trace = Trace(
                            start=(p1[0], p1[1]),
                            end=(p2[0], p2[1]),
                            width=width,
                            layer=layer_name,
                            net=net_neg_name,
                        )
                        all_traces.append(trace)
                        # Block trace on grid
                        grid.block_trace(
                            [(p1[0], p1[1]), (p2[0], p2[1])],
                            width_mm=width,
                            clearance_mm=clearance,
                            layer=p1[2],
                            net_name=net_neg_name,
                        )
                        # Register in DRCOracle
                        if state.drc_oracle:
                            state.drc_oracle.register_track(
                                OracleTrack(
                                    start=OraclePoint(p1[0], p1[1]),
                                    end=OraclePoint(p2[0], p2[1]),
                                    width=width,
                                    net=net_neg_name,
                                    layer=p1[2],
                                )
                            )

                print(f"      ✓ {net_pos_name}/{net_neg_name} diff pair routed")

        # ========== END DIFFERENTIAL PAIR ROUTING ==========

        for net_idx, net_name in enumerate(net_order):
            if net_name not in net_by_name:
                continue

            # Skip nets already routed as differential pairs
            if net_name in diff_pair_nets:
                print(
                    f"    Skipping net {net_idx + 1}/{len(net_order)}: {net_name} (routed as diff pair)"
                )
                continue

            net = net_by_name[net_name]
            print(f"    Routing net {net_idx + 1}/{len(net_order)}: {net_name}...", flush=True)
            net_start = time.time()

            # Determine layer for this net
            layer_idx = layer_by_net.get(net_name, 0)  # Default to layer 0
            layer_name = LAYER_IDX_TO_NAME.get(layer_idx, "F.Cu")

            # Get net class for zone confinement and design rules lookup
            net_class_name = getattr(net, "net_class", None)

            # Determine width and clearance
            width = self.default_width
            clearance = self.default_clearance

            if self.design_rules:
                rules = self.design_rules.get_rules_for_net(net_name, net_class=net_class_name)
                width = rules.trace_width
                clearance = rules.clearance

            # Find pin positions and refs
            pin_positions = []
            pin_info = []  # Store (ref, name) for lookup
            pins = []  # Store actual Pin objects
            for comp_ref, pin_name in net.pins:
                if comp_ref not in comp_by_ref:
                    continue
                comp = comp_by_ref[comp_ref]
                pin = next(
                    (p for p in comp.pins if p.name == pin_name or p.number == pin_name), None
                )
                if not pin:
                    continue
                pos = comp.initial_position or (0, 0)
                pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
                pin_positions.append(pin_pos)
                pin_info.append((comp_ref, pin.name))
                pins.append(pin)

            if len(pin_positions) < 2 and not is_plane_by_net.get(net_name, False):
                continue

            # Check if this is a plane net (GND/Power on inner layers)
            is_plane = is_plane_by_net.get(net_name, False)

            if is_plane:
                # For plane nets, we don't route traces.
                # We just generate a via at each pin to connect to the plane.
                via_d = 0.6
                via_drill = 0.3
                mask_expansion = 0.1
                if self.design_rules and rules:
                    via_d = rules.via_diameter
                    via_drill = rules.via_drill

                via_mask_radius = via_d / 2.0 + mask_expansion

                for i, pos in enumerate(pin_positions):
                    pin = pins[i]

                    # PTH pads don't need vias - their barrel already connects all layers
                    if pin.is_pth or pin.layer == "all":
                        print(
                            f"  INFO: {net_name} pin {pin.name} at {pos} is PTH - barrel connects to {layer_name}, skipping via"
                        )
                        continue

                    # Find safe position for via
                    # Strategy: Try pad position first (no stub needed), then search outward
                    if state.drc_oracle:
                        # First, try via directly at pad position (best for connectivity)
                        sites = state.drc_oracle.get_valid_via_sites(
                            pos,
                            search_radius=0.01,
                            net=net_name,  # Essentially at pad
                        )
                        safe_pos = sites[0] if sites else None

                        # If pad position doesn't work, search progressively outward
                        if not safe_pos:
                            for radius in [0.5, 1.0, 2.0, 5.0]:
                                sites = state.drc_oracle.get_valid_via_sites(
                                    pos, search_radius=radius, net=net_name
                                )
                                if sites:
                                    safe_pos = sites[0]
                                    print(
                                        f"INFO: Found via site for {net_name} at {radius}mm from pad (offset {((sites[0][0] - pos[0]) ** 2 + (sites[0][1] - pos[1]) ** 2) ** 0.5:.2f}mm)"
                                    )
                                    break

                        if not safe_pos:
                            print(
                                f"WARNING: DRCOracle could not find safe via position for {net_name} at {pos} (searched up to 5mm)"
                            )
                            safe_pos = pos  # Fallback to pad position
                    else:
                        # Without DRC oracle, place via at pad position (no clearance check)
                        safe_pos = pos

                    # Create Via connecting Top to Plane Layer
                    via = Via(
                        position=safe_pos,
                        drill=via_drill,
                        width=via_d,
                        layers=("F.Cu", layer_name),
                        net=net_name,
                    )
                    all_vias.append(via)

                    # Register in DRCOracle
                    if state.drc_oracle:
                        state.drc_oracle.register_via(
                            OracleVia(
                                center=OraclePoint(safe_pos[0], safe_pos[1]),
                                diameter=via_d,
                                drill=via_drill,
                                net=net_name,
                            )
                        )

                    # Add stub trace from SMD pad to via on F.Cu
                    # CRITICAL: SMD pads are only on F.Cu, so they NEED a F.Cu trace
                    # to reach the via, even if the via is at the pad position.
                    # The via then connects F.Cu to the inner plane layer.

                    # Always add stub for SMD pads, even if via is at pad position
                    # For PTH pads, the barrel provides connectivity, so no stub needed
                    if safe_pos != pos or not pin.is_pth:
                        # If via is exactly at pad, create very short stub (0.1mm) for connectivity
                        if safe_pos == pos:
                            # Create minimal stub in direction away from pad center
                            # Just enough for KiCad to recognize connectivity
                            dx = 0.1 if pos[0] < 50 else -0.1
                            stub_end = (pos[0] + dx, pos[1])
                        else:
                            stub_end = safe_pos

                        stub_valid = True
                        if state.drc_oracle and stub_end != pos:
                            stub_valid, stub_reason = state.drc_oracle.can_place_track_segment(
                                start=pos,
                                end=stub_end,
                                layer=0,
                                net=net_name,
                                width=width,
                                neckdown=True,  # Use relaxed clearance for plane stubs
                            )
                            if not stub_valid:
                                print(
                                    f"  INFO: Plane stub trace for {net_name} skipped: {stub_reason}"
                                )

                        if stub_valid and stub_end != pos:
                            all_traces.append(
                                Trace(
                                    start=pos, end=stub_end, width=width, layer="F.Cu", net=net_name
                                )
                            )
                            # Register stub in DRCOracle
                            if state.drc_oracle:
                                state.drc_oracle.register_track(
                                    OracleTrack(
                                        start=OraclePoint(pos[0], pos[1]),
                                        end=OraclePoint(stub_end[0], stub_end[1]),
                                        width=width,
                                        net=net_name,
                                        layer=0,  # F.Cu
                                    )
                                )

                    # Block Via on ALL layers
                    for l_idx in range(grid.layer_count):
                        grid.block_circle(
                            safe_pos,
                            radius_mm=via_d / 2,
                            clearance_mm=clearance,
                            layer=l_idx,
                            net_name=net_name,
                            is_pad=False,
                        )

                # Skip trace routing for plane nets
                continue

            # Get zone confinement for this net class (net_class_name set above)
            allowed_zones = self._get_allowed_zones(net_class_name, state)

            if allowed_zones:
                zone_names = [z.name for z in allowed_zones]
                print(f"  INFO: {net_name} ({net_class_name}) confined to zones: {zone_names}")

            # Get allowed layers for this net (enables inner layer routing for congested nets)
            allowed_layers = self._get_allowed_layers_for_net(net_name, net_class_name, state)

            pathfinder = DeterministicAStar(
                grid=grid,
                drc_oracle=state.drc_oracle,
                net_name=net_name,
                trace_width=width,
                # Note: allowed_zones not supported by DeterministicAStar
            )
            mst_edges = self._compute_mst(pin_positions)

            # Snap pin positions to grid for A* pathfinding
            snapped_positions = [snap_to_grid(p, grid.cell_size_mm) for p in pin_positions]

            net_paths = []  # List of (path_points, layer_idx) tuples
            net_multilayer_paths = []  # Results from multi-layer routing

            # Create multi-layer pathfinder with net-specific allowed layers
            # This enables routing on inner layers for congested signal nets
            multilayer_pathfinder = MultiLayerAStar(
                grid=grid,
                drc_oracle=state.drc_oracle,
                net_name=net_name,
                net_class=net_class_name or "Default",  # For adaptive budget calculation
                trace_width=width,
                via_cost=3.0,  # Reduced from 5.0 to encourage layer changes when needed
                allowed_layers=allowed_layers,  # Dynamic per-net layer assignment
                congestion_detector=congestion_detector,  # Adaptive iteration budgeting
                use_adaptive_budget=True,  # Enable congestion-aware routing
            )

            # Route all edges in the MST
            for idx1, idx2 in mst_edges:
                # Use snapped positions for grid-based pathfinding
                p1_snapped = snapped_positions[idx1]
                p2_snapped = snapped_positions[idx2]

                # Try single-layer routing first (faster, simpler)
                path = pathfinder.find_path(start=p1_snapped, end=p2_snapped, layer=layer_idx)
                if path:
                    # Add nudge segments to connect snapped path back to actual centers
                    nudged_path = add_endpoint_nudge(path, pin_positions[idx1], pin_positions[idx2])

                    # Validate path with DRCOracle before accepting
                    path_valid = True
                    if state.drc_oracle:
                        for i in range(len(nudged_path) - 1):
                            valid, reason = state.drc_oracle.can_place_track_segment(
                                nudged_path[i], nudged_path[i + 1], layer_idx, net_name, width
                            )
                            if not valid:
                                print(f"  Path rejected for {net_name}: {reason}")
                                path_valid = False
                                break

                    if path_valid:
                        net_paths.append((nudged_path, layer_idx))
                        continue  # Success, move to next edge

                # Single-layer failed - try multi-layer routing as fallback
                multilayer_result = multilayer_pathfinder.find_path(
                    start=p1_snapped,
                    end=p2_snapped,
                    start_layer=layer_idx,
                    end_layer=-1,  # Any layer OK
                )

                if multilayer_result:
                    # Show congestion-aware routing diagnostics
                    if (
                        hasattr(multilayer_pathfinder, "last_iterations")
                        and multilayer_pathfinder.last_iterations > 0
                    ):
                        congestion_level = getattr(
                            multilayer_pathfinder, "last_congestion_level", None
                        )
                        congestion_str = (
                            f" [congestion: {congestion_level.value}]" if congestion_level else ""
                        )
                        print(
                            f"  INFO: Multi-layer route found for {net_name} "
                            f"({multilayer_pathfinder.last_iterations}/{multilayer_pathfinder.last_iteration_limit} iters, "
                            f"{len(multilayer_result.via_positions)} vias{congestion_str})"
                        )
                    else:
                        print(
                            f"  INFO: Multi-layer route found for {net_name} ({len(multilayer_result.via_positions)} vias)"
                        )
                    net_multilayer_paths.append(multilayer_result)
                else:
                    print(
                        f"  WARNING: Could not find any path for {net_name} segment {idx1}->{idx2}"
                    )

            # Commit all single-layer paths for this net
            for path, path_layer_idx in net_paths:
                path_layer_name = LAYER_IDX_TO_NAME.get(path_layer_idx, "F.Cu")
                # Block the routed trace on the same layer with net_name
                grid.block_trace(
                    path,
                    width_mm=width,
                    clearance_mm=clearance,
                    layer=path_layer_idx,
                    net_name=net_name,
                )

                # Create Trace objects for state with correct layer
                # FINAL VALIDATION: Check each trace segment before adding
                for i in range(len(path) - 1):
                    # Validate final trace with Oracle
                    trace_valid = True
                    if state.drc_oracle:
                        trace_valid, reject_reason = state.drc_oracle.can_place_track_segment(
                            start=path[i],
                            end=path[i + 1],
                            layer=path_layer_idx,
                            net=net_name,
                            width=width,
                        )
                        if not trace_valid:
                            print(f"  REJECTED final trace for {net_name}: {reject_reason}")
                            continue  # Skip this invalid segment

                    all_traces.append(
                        Trace(
                            start=path[i],
                            end=path[i + 1],
                            width=width,
                            layer=path_layer_name,
                            net=net_name,
                        )
                    )
                    # Register in DRCOracle
                    if state.drc_oracle:
                        state.drc_oracle.register_track(
                            OracleTrack(
                                start=OraclePoint(path[i][0], path[i][1]),
                                end=OraclePoint(path[i + 1][0], path[i + 1][1]),
                                width=width,
                                net=net_name,
                                layer=path_layer_idx,
                            )
                        )

            # Commit multi-layer paths (with vias)
            via_d = 0.6
            via_drill = 0.3
            if self.design_rules:
                rules = self.design_rules.get_rules_for_net(net_name)
                via_d = rules.via_diameter
                via_drill = rules.via_drill

            for ml_path in net_multilayer_paths:
                # Commit trace segments
                for segment in ml_path.segments:
                    seg_layer_name = LAYER_IDX_TO_NAME.get(segment.layer, "F.Cu")

                    # Block on grid with net_name
                    grid.block_trace(
                        [segment.start, segment.end],
                        width_mm=width,
                        clearance_mm=clearance,
                        layer=segment.layer,
                        net_name=net_name,
                    )

                    # FINAL VALIDATION: Validate multi-layer trace segment
                    trace_valid = True
                    if state.drc_oracle:
                        trace_valid, reject_reason = state.drc_oracle.can_place_track_segment(
                            start=segment.start,
                            end=segment.end,
                            layer=segment.layer,
                            net=net_name,
                            width=width,
                        )
                        if not trace_valid:
                            print(f"  REJECTED multi-layer trace for {net_name}: {reject_reason}")
                            continue  # Skip this invalid segment

                    # Create Trace object
                    all_traces.append(
                        Trace(
                            start=segment.start,
                            end=segment.end,
                            width=width,
                            layer=seg_layer_name,
                            net=net_name,
                        )
                    )

                    # Register in DRCOracle
                    if state.drc_oracle:
                        state.drc_oracle.register_track(
                            OracleTrack(
                                start=OraclePoint(segment.start[0], segment.start[1]),
                                end=OraclePoint(segment.end[0], segment.end[1]),
                                width=width,
                                net=net_name,
                                layer=segment.layer,
                            )
                        )

                # Commit vias from layer transitions - use via arrays for high-current nets
                for vx, vy, from_layer, to_layer in ml_path.via_positions:
                    from_layer_name = LAYER_IDX_TO_NAME.get(from_layer, "F.Cu")
                    to_layer_name = LAYER_IDX_TO_NAME.get(to_layer, "B.Cu")

                    # Use via array helper (creates single or array based on net class)
                    self._create_via_array(
                        center=(vx, vy),
                        net_name=net_name,
                        from_layer_name=from_layer_name,
                        to_layer_name=to_layer_name,
                        via_d=via_d,
                        via_drill=via_drill,
                        clearance=clearance,
                        grid=grid,
                        state=state,
                        all_vias=all_vias,
                    )

            # Generate Vias for pins if routed on inner layer
            if net_paths and layer_name != "F.Cu":
                via_d = 0.6
                via_drill = 0.3
                mask_expansion = 0.1
                if self.design_rules and rules:
                    via_d = rules.via_diameter
                    via_drill = rules.via_drill

                via_mask_radius = via_d / 2.0 + mask_expansion

                # Assume all pins are on Top/Bottom and need Via to connect to Inner
                # Ideally check pin layer, but for MVP assuming Top SMD/THT
                for pos in pin_positions:
                    # Find safe position for via - use progressive search
                    if state.drc_oracle:
                        # Progressive search: try 2mm, then 5mm
                        safe_pos = None
                        for radius in [2.0, 5.0]:
                            sites = state.drc_oracle.get_valid_via_sites(
                                pos, search_radius=radius, net=net_name
                            )
                            if sites:
                                safe_pos = sites[0]
                                if radius > 2.0:
                                    print(
                                        f"INFO: Found via site for {net_name} at {radius}mm radius (offset {((sites[0][0] - pos[0]) ** 2 + (sites[0][1] - pos[1]) ** 2) ** 0.5:.2f}mm)"
                                    )
                                break

                        if not safe_pos:
                            print(
                                f"WARNING: DRCOracle could not find safe via position for {net_name} at {pos} (searched up to 5mm)"
                            )
                            safe_pos = pos  # Fallback to pad position
                    else:
                        safe_pos = place_via_with_clearance(pos, all_pads_info, via_mask_radius)
                        if not safe_pos:
                            print(
                                f"WARNING: Could not find safe via position for {net_name} at {pos}"
                            )
                            safe_pos = pos  # Fallback

                    # Create Via
                    via = Via(
                        position=safe_pos,
                        drill=via_drill,
                        width=via_d,
                        layers=("F.Cu", layer_name),
                        net=net_name,
                    )
                    all_vias.append(via)

                    # Register in DRCOracle
                    if state.drc_oracle:
                        state.drc_oracle.register_via(
                            OracleVia(
                                center=OraclePoint(safe_pos[0], safe_pos[1]),
                                diameter=via_d,
                                drill=via_drill,
                                net=net_name,
                            )
                        )

                    # If via shifted, add a short stub trace from pin to via
                    # VALIDATE stub trace before adding to prevent DRC violations
                    if safe_pos != pos:
                        stub_valid = True
                        if state.drc_oracle:
                            stub_valid, stub_reason = state.drc_oracle.can_place_track_segment(
                                start=pos, end=safe_pos, layer=0, net=net_name, width=width
                            )
                            if not stub_valid:
                                print(
                                    f"  WARNING: Signal stub trace for {net_name} rejected: {stub_reason}"
                                )

                        if stub_valid:
                            all_traces.append(
                                Trace(
                                    start=pos, end=safe_pos, width=width, layer="F.Cu", net=net_name
                                )
                            )
                            # Register stub in DRCOracle
                            if state.drc_oracle:
                                state.drc_oracle.register_track(
                                    OracleTrack(
                                        start=OraclePoint(pos[0], pos[1]),
                                        end=OraclePoint(safe_pos[0], safe_pos[1]),
                                        width=width,
                                        net=net_name,
                                        layer=0,  # F.Cu
                                    )
                                )

                    # Block Via on ALL layers
                    # Iterate all grid layers
                    for l_idx in range(grid.layer_count):
                        grid.block_circle(
                            safe_pos,
                            radius_mm=via_d / 2,
                            clearance_mm=clearance,
                            layer=l_idx,
                            net_name=net_name,
                            is_pad=False,
                        )

            net_elapsed = time.time() - net_start
            print(f"      ✓ {net_name} routed in {net_elapsed:.2f}s", flush=True)

        return replace(state, routes=frozenset(all_traces), vias=frozenset(all_vias))

    def _compute_mst(self, points: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
        """Compute Minimum Spanning Tree using Prim's algorithm."""
        n = len(points)
        if n < 2:
            return []

        visited = {0}
        edges = []

        while len(visited) < n:
            min_dist_sq = float("inf")
            u_min, v_min = -1, -1

            # Find shortest edge from visited to unvisited
            for u in visited:
                for v in range(n):
                    if v in visited:
                        continue

                    # Squared Euclidean distance
                    dist_sq = (points[u][0] - points[v][0]) ** 2 + (
                        points[u][1] - points[v][1]
                    ) ** 2

                    if dist_sq < min_dist_sq:
                        min_dist_sq = dist_sq
                        u_min = u
                        v_min = v

            if u_min != -1 and v_min != -1:
                visited.add(v_min)
                edges.append((u_min, v_min))
            else:
                break

        return edges
