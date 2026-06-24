from dataclasses import replace
from typing import List, Tuple, Optional, Set
import logging
import numpy as np
from ..state import BoardState
from .base import Stage
from .multilayer_astar import MultiLayerAStar
from .sequential_routing_dataclasses import DiffPairConfig
from .sequential_routing_helpers import (
    LAYER_ENUM_TO_IDX,
    _compute_endpoint_tolerance,
    _compute_mst,
)
from ...core.board import LAYER_IDX_TO_NAME, LayerIndex, Trace, Via, layer_name_to_index
from ...core.design_rules import DesignRules
from ...core.pin_geometry import pin_world_position
from ...routing.constraints.spatial_index import Track as OracleTrack, Via as OracleVia
from ...routing.constraints.geometry import Point as OraclePoint
from ..geometry.via_placement import PadInfo
from ..geometry.grid_utils import snap_to_grid
from ...routing.layer_assignment import Layer as LayerEnum
from ...routing.diff_pair_router import DiffPairRouter, DiffPairPath
from ...router_v6 import (
    BottleneckGeometry,
    FailureReason,
    NetRoutingReport,
    RoutingStatus,
    analyze_bottleneck,
)


logger = logging.getLogger(__name__)

# EXP-6: Import coupled diff pair router for USB pairs
# The experiments folder is at package root, not in src/
import sys
from pathlib import Path

_package_root = Path(
    __file__
).parent.parent.parent.parent.parent  # src/temper_placer/deterministic/stages -> temper-placer
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))
try:
    from experiments.diff_pair.coupled_router import CoupledDiffPairRouter, CoupledRouterResult

    COUPLED_ROUTER_AVAILABLE = True
except ImportError as e:
    COUPLED_ROUTER_AVAILABLE = False
    _coupled_router_import_error = str(e)
from ...routing.adaptive_congestion import (
    GridBasedCongestionDetector,
    ComponentBasedCongestionDetector,
    CompositeDetector,
)


class SequentialRoutingStage(Stage):
    def __init__(
        self,
        design_rules: DesignRules | None = None,
        trace_width_mm: float = 0.25,
        clearance_mm: float = 0.2,
        pad_sizes: dict = None,
        net_class_rules: dict = None,
        differential_pairs: List[DiffPairConfig] = None,
    ):
        """Initialize sequential routing stage.

        Args:
            design_rules: DRC rules for trace widths/clearances
            trace_width_mm: Default trace width
            clearance_mm: Default clearance
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

        Note:
            Zone confinement is currently disabled. Reintroduce the
            body below when A* is optimized for zone-aware routing;
            git history preserves the original implementation.

        Args:
            net_class_name: Name of the net class (e.g., 'HighVoltage', 'Signal')
            state: BoardState with zone definitions

        Returns:
            Always ``None`` while zone confinement is disabled.
        """
        # TEMPORARILY DISABLED: Zone confinement causes routing timeouts.
        # TODO: Re-enable after optimizing A* for zone-aware routing.
        # The domain-driven placement should be enough for now.
        return None

    def _get_escape_via_for_pin(
        self,
        pin_pos: Tuple[float, float],
        net_name: str,
        state: BoardState,
    ) -> Tuple[Optional[int], Tuple[float, float]]:
        """Check if an escape via exists at this pin position.

        Escape vias are placed by FinePitchEscapeStage to route from dense
        pin fields on F.Cu to inner layers where clearances don't conflict.

        Args:
            pin_pos: (x, y) position of pin on component
            net_name: Net name to match
            state: Current board state with vias

        Returns:
            (escape_layer_idx, via_position) if escape via found
            (None, pin_pos) if no escape via at this position
        """
        if not state.vias:
            return (None, pin_pos)

        for via in state.vias:
            if via.net != net_name:
                continue

            # Check if via is at pin position (within 0.01mm tolerance for floating point)
            dx = via.position[0] - pin_pos[0]
            dy = via.position[1] - pin_pos[1]
            dist = (dx * dx + dy * dy) ** 0.5

            if dist < 0.01:  # Via is at pin
                # Determine escape layer from via.layers tuple
                # Escape vias connect F.Cu (0) -> In1.Cu (1)
                if "In1.Cu" in via.layers:
                    return (1, via.position)  # Escape to Layer 1
                elif "In2.Cu" in via.layers:
                    return (2, via.position)  # Escape to Layer 2
                elif "B.Cu" in via.layers:
                    return (3, via.position)  # Escape to Layer 3

        return (None, pin_pos)  # No escape via found

    def _get_pin_positions_from_oracle(
        self,
        comp_ref: str,
        pin_name: str,
        state: BoardState,
    ) -> List[Tuple[Tuple[float, float], bool, Optional[Tuple[float, float]]]]:
        """Get all pin positions from DRC oracle (has correct KiCad positions).

        The DRC oracle loads pad positions directly from the KiCad PCB file,
        which are correct even after placement optimization. Using netlist
        component.initial_position may give wrong positions.
        
        Returns:
            List of (position, is_pth, size) tuples for all matching pads.
        """
        results = []
        if not state.drc_oracle or not hasattr(state.drc_oracle, "geometry"):
            return results

        # Try exact pad ID match
        pad_id = f"{comp_ref}.{pin_name}"
        
        # Try alternate formats (some KiCad versions use different naming)
        alt_ids = [
            f"{comp_ref}-{pin_name}",
            f"{comp_ref}_{pin_name}",
        ]
        
        for pad in state.drc_oracle.geometry.pads:
            if pad.id == pad_id or pad.id in alt_ids:
                results.append(((pad.center.x, pad.center.y), pad.is_pth, pad.size))

        return results

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
            # Check DRC before placing via
            if state.drc_oracle:
                valid, reason = state.drc_oracle.can_place_via(
                    position=center,
                    diameter=via_d,
                    net=net_name,
                )
                if not valid:
                    print(f"  WARNING: Skipping via for {net_name} at {center} - {reason}")
                    return created_vias  # Return empty list

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
            # Check DRC before placing via
            if state.drc_oracle:
                valid, reason = state.drc_oracle.can_place_via(
                    position=(vx, vy),
                    diameter=via_template.via_diameter_mm,
                    net=net_name,
                )
                if not valid:
                    print(
                        f"  WARNING: Skipping via array element for {net_name} at ({vx}, {vy}) - {reason}"
                    )
                    continue  # Skip this via in the array

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

        # Gate drive: All layers - these need escape routing through inner layers
        # EXP-6b: Changed from [0, 3] to all layers for escape via compatibility
        if any(pattern in net_upper for pattern in ["GATE_", "DRV_", "PWM_H", "PWM_L", "VCC_BOOT"]):
            return [0, 1, 2, 3]  # All layers - escape vias may go to In2.Cu

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

    def _get_via_params_for_net(self, net_name: str) -> dict:
        """Get via parameters (diameter, drill) for a specific net.

        Args:
            net_name: Name of the net

        Returns:
            Dict with 'diameter' and 'drill' keys
        """
        via_d = 0.6
        via_drill = 0.3
        
        # Check design rules if available
        if self.design_rules:
            via_d = getattr(self.design_rules, "default_via_diameter", 0.6)
            via_drill = getattr(self.design_rules, "default_via_drill", 0.3)
            
        return {"diameter": via_d, "drill": via_drill}

    def run(self, state: BoardState) -> BoardState:
        if not state.board or not state.netlist or not state.net_order or not state.grid:
            return state

        grid = state.grid
        net_order = state.net_order
        net_by_name = {n.name: n for n in state.netlist.nets}
        comp_by_ref = {c.ref: c for c in state.netlist.components}

        import time
        total_start = time.time()

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
        # U3: per-net routing reports. The post-mortem ``_attach_bottlenecks``
        # pass iterates over reports whose status is FAILED / PARTIAL /
        # BLOCKED and calls ``analyze_bottleneck`` for each. Successful
        # nets do not need a bottleneck diagnostic and are skipped.
        all_net_reports: list[NetRoutingReport] = []

        # Gather all pads for via clearance checking
        all_pads_info = []
        for component in state.netlist.components:
            comp_for_pin = comp_by_ref[component.ref]
            for pin in component.pins:
                # Approximate pad radius (assuming circular for clearance)
                pad_r = 0.5
                if self.pad_sizes:
                    real_pad = self.pad_sizes.get((component.ref, pin.name))
                    if real_pad:
                        pad_r = max(real_pad.size.X, real_pad.size.Y) / 2.0

                all_pads_info.append(
                    PadInfo(
                        position=pin_world_position(pin, comp_for_pin),
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

                # Build pad position lookup from DRC oracle (has correct KiCad positions)
                # This avoids using component.initial_position which may be modified by placement optimizer
                pad_positions_from_oracle = {}
                if state.drc_oracle:
                    for pad in state.drc_oracle.geometry.pads:
                        pad_positions_from_oracle[pad.id] = (pad.center.x, pad.center.y)

                # Get pin positions for both nets - prefer DRC oracle positions
                def get_pin_positions_from_oracle(net, pad_lookup, comp_by_ref):
                    """Get pin positions, preferring DRC oracle positions over component positions."""
                    positions = []
                    for comp_ref, pin_name in net.pins:
                        # Try DRC oracle first (has correct KiCad positions)
                        pad_id = f"{comp_ref}.{pin_name}"
                        if pad_id in pad_lookup:
                            positions.append(pad_lookup[pad_id])
                            continue

                        # Fallback to component position (may be wrong if placement optimizer ran)
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

                pos_pins = get_pin_positions_from_oracle(
                    net_pos, pad_positions_from_oracle, comp_by_ref
                )
                neg_pins = get_pin_positions_from_oracle(
                    net_neg, pad_positions_from_oracle, comp_by_ref
                )

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

                # DEBUG: Log computed pin positions
                print(
                    f"  [DiffPair] {net_pos_name}/{net_neg_name} pos_pins={pos_pins}, neg_pins={neg_pins}"
                )
                print(f"  [DiffPair] start_pins={start_pins}, goal_pins={goal_pins}")

                # Get design rules for diff pair
                width = self.default_width
                clearance = self.default_clearance
                if self.design_rules:
                    rules = self.design_rules.get_rules_for_net(
                        net_pos_name, net_class="Differential"
                    )
                    width = rules.trace_width
                    clearance = rules.clearance

                # FIX: Build minimal obstacle set for diff pair routing
                # The main grid uses max_clearance_mm (e.g., 6.3mm for HV boards) which blocks
                # nearly everything. For diff pairs, we only need to avoid actual physical
                # obstacles (other pads/traces), not the inflated clearance zones.
                #
                # Strategy: Build obstacles from DRC oracle pads (has correct KiCad positions)
                obstacles: Set[Tuple[int, int, int]] = set()

                # FIX: Use effective clearance that matches DRC oracle calculation
                # The DRC oracle computes: effective_clearance = required + (width / 2) + mask_expansion
                # We need to account for:
                # - USB-to-GND clearance: 0.25mm (max of 0.10 Differential and 0.25 Ground)
                # - Half trace width: 0.127 / 2 = 0.0635mm
                # - Mask expansion: 0.1mm (default in spatial_index.py)
                # Total: ~0.414mm
                mask_expansion_mm = 0.1  # Match default in spatial_index.py
                gnd_clearance_mm = 0.25  # Ground net class clearance
                effective_obstacle_clearance = gnd_clearance_mm + (width / 2) + mask_expansion_mm

                # FIX: Build obstacles from DRC oracle's pad geometry instead of netlist components
                # The DRC oracle has correct pad positions from KiCad PCB, while netlist.components
                # may have positions from the placement optimizer
                if state.drc_oracle and hasattr(state.drc_oracle, "geometry"):
                    for pad in state.drc_oracle.geometry.pads:
                        # Skip pads belonging to the diff pair nets we're routing
                        if pad.net in (net_pos_name, net_neg_name):
                            continue

                        # Get pad position and size
                        pad_center = (pad.center.x, pad.center.y)
                        # pad.size is a tuple (width, height) in mm
                        pad_radius_mm = max(pad.size[0], pad.size[1]) / 2.0

                        # Extra clearance for large thermal pads (>2mm diameter)
                        # These often have exposed copper that requires additional margin
                        thermal_pad_margin = 0.5 if pad_radius_mm > 1.0 else 0.0

                        pin_gx = int(pad_center[0] / grid.cell_size_mm)
                        pin_gy = int(pad_center[1] / grid.cell_size_mm)

                        total_radius = pad_radius_mm + effective_obstacle_clearance + thermal_pad_margin
                        radius_cells = int(total_radius / grid.cell_size_mm) + 1

                        for dx in range(-radius_cells, radius_cells + 1):
                            for dy in range(-radius_cells, radius_cells + 1):
                                if dx * dx + dy * dy <= radius_cells * radius_cells:
                                    gx, gy = pin_gx + dx, pin_gy + dy
                                    if 0 <= gx < grid.cols and 0 <= gy < grid.rows:
                                        # Block on all layers for through-hole, layer 0 for SMD
                                        if pad.is_pth:
                                            for layer in range(grid.layer_count):
                                                obstacles.add((gx, gy, layer))
                                        else:
                                            obstacles.add((gx, gy, 0))
                else:
                    # Fallback to netlist components (old behavior)
                    for comp in state.netlist.components:
                        for pin in comp.pins:
                            # Skip pins belonging to the diff pair nets we're routing
                            if pin.net in (net_pos_name, net_neg_name):
                                continue

                            pin_pos = pin_world_position(pin, comp)
                            pin_gx = int(pin_pos[0] / grid.cell_size_mm)
                            pin_gy = int(pin_pos[1] / grid.cell_size_mm)

                            # Block cells within clearance radius
                            # FIX: Use actual pad size from pad_sizes lookup instead of hardcoded 0.5mm
                            # This is critical for large pads like ESP32 thermal/ground pads (5.6mm x 5.6mm)
                            pad_key = (comp.ref, pin.name)
                            if pad_key in self.pad_sizes:
                                pad_info = self.pad_sizes[pad_key]
                                # pad_info.size.X and .Y contain width/height
                                # Use the larger dimension for circular obstacle (conservative)
                                pad_radius_mm = max(pad_info.size.X, pad_info.size.Y) / 2.0
                            else:
                                # Fallback to reasonable default
                                pad_radius_mm = 0.5

                            total_radius = pad_radius_mm + effective_obstacle_clearance
                            radius_cells = int(total_radius / grid.cell_size_mm) + 1

                            for dx in range(-radius_cells, radius_cells + 1):
                                for dy in range(-radius_cells, radius_cells + 1):
                                    if dx * dx + dy * dy <= radius_cells * radius_cells:
                                        gx, gy = pin_gx + dx, pin_gy + dy
                                        if 0 <= gx < grid.cols and 0 <= gy < grid.rows:
                                            # Block on layer 0 (F.Cu) for SMD, all layers for PTH
                                            if pin.is_pth:
                                                for layer in range(grid.layer_count):
                                                    obstacles.add((gx, gy, layer))
                                            else:
                                                obstacles.add((gx, gy, 0))

                # Also add any already-routed traces as obstacles
                for layer_idx in range(grid.layer_count):
                    trace_blocked = grid._trace_net_ids[layer_idx] != 0
                    blocked_indices = np.argwhere(trace_blocked)
                    for row, col in blocked_indices:
                        obstacles.add((int(col), int(row), layer_idx))

                print(
                    f"  [DiffPair] Built {len(obstacles)} obstacles with {effective_obstacle_clearance:.2f}mm clearance"
                )

                # EXP-6: Use CoupledDiffPairRouter for USB differential pairs
                # The coupled router routes P and N simultaneously, checking DRC at each step,
                # which prevents the post-processing offset problem that causes violations.
                is_usb_pair = "USB" in net_pos_name.upper() or "USB" in net_neg_name.upper()
                use_coupled_router = COUPLED_ROUTER_AVAILABLE and is_usb_pair

                if use_coupled_router:
                    # CoupledDiffPairRouter: routes both traces together with DRC validation
                    coupled_router = CoupledDiffPairRouter(
                        grid_resolution_mm=0.1,  # Fine grid for diff pairs
                        trace_width_mm=width,
                        target_spacing_mm=dp_config.spacing_mm,
                        max_divergence_mm=dp_config.coupling_tolerance_mm,
                        max_skew_mm=dp_config.max_skew_mm,
                        drc_oracle=state.drc_oracle,  # Pass DRC oracle for live validation
                    )

                    print(
                        f"  [DiffPair] Using CoupledDiffPairRouter for {net_pos_name}/{net_neg_name}..."
                    )
                    dp_start = time.time()

                    # Use hierarchical routing (coarse A* + fine segments)
                    # IMPORTANT: Pass the grid cell size so obstacle coordinates are correctly converted
                    coupled_result = coupled_router.route_hierarchical(
                        start_pins=start_pins,
                        goal_pins=goal_pins,
                        obstacles=obstacles,
                        board_size=(
                            grid.cols * grid.cell_size_mm,
                            grid.rows * grid.cell_size_mm,
                            grid.layer_count,
                        ),
                        net_pos=net_pos_name,
                        net_neg=net_neg_name,
                        obstacle_grid_resolution_mm=grid.cell_size_mm,  # FIX: Pass grid cell size
                    )

                    dp_elapsed = time.time() - dp_start

                    if not coupled_result.success:
                        print(
                            f"  [DiffPair] CoupledRouter FAILED: {net_pos_name}/{net_neg_name} - {coupled_result.error_message}"
                        )
                        print(f"  [DiffPair] Falling back to legacy router...")
                        use_coupled_router = False  # Fall back to legacy
                    else:
                        print(
                            f"  [DiffPair] CoupledRouter SUCCESS: {net_pos_name}/{net_neg_name} in {dp_elapsed:.2f}s "
                            f"(coupling={coupled_result.coupling_ratio:.1f}%, skew={coupled_result.max_skew_mm:.3f}mm)"
                        )
                        # Paths are already in mm - no post-processing needed!
                        pos_path_mm = coupled_result.pos_path
                        neg_path_mm = coupled_result.neg_path

                        # Mark nets as routed
                        diff_pair_nets.add(net_pos_name)
                        diff_pair_nets.add(net_neg_name)

                # Legacy router path (for non-USB pairs or as fallback)
                if not use_coupled_router:
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
                        f"(coupling={result.coupling_ratio:.1f}%, skew={result.max_skew_mm:.3f}mm)"
                    )

                    # Mark these nets as routed via diff pair
                    diff_pair_nets.add(net_pos_name)
                    diff_pair_nets.add(net_neg_name)

                    # Convert grid cells to mm positions with perpendicular offset
                    # to ensure P and N traces don't share endpoints.
                    #
                    # Problem: The diff pair router keeps P and N in different cells at each
                    # timestep, but when navigating corners, BOTH paths may pass through the
                    # same cell at different timesteps. This creates trace segments that share
                    # endpoints, causing DRC violations.
                    #
                    # Solution: Find cells that appear in both paths and apply perpendicular
                    # offsets to ensure they don't share exact coordinates.
                    def cells_to_mm_with_offset(
                        pos_cells: List[Tuple[int, int, int]],
                        neg_cells: List[Tuple[int, int, int]],
                        target_spacing_mm: float,
                    ) -> Tuple[List[Tuple[float, float, int]], List[Tuple[float, float, int]]]:
                        """Convert grid cells to mm with perpendicular offset for true parallel traces.

                        For cells that appear in both paths, applies a perpendicular offset based on
                        the trace direction to ensure P and N traces don't share exact endpoints.
                        """
                        import math

                        half_spacing = target_spacing_mm / 2.0

                        # Find cells that appear in both paths (these need offset)
                        pos_cell_set = set((c[0], c[1], c[2]) for c in pos_cells)
                        neg_cell_set = set((c[0], c[1], c[2]) for c in neg_cells)
                        shared_cells = pos_cell_set & neg_cell_set

                        def get_offset_for_cell(cells, idx, is_pos_trace):
                            """Compute perpendicular offset for a cell based on trace direction."""
                            cell = cells[idx]

                            # Determine trace direction at this point
                            if idx > 0:
                                prev = cells[idx - 1]
                                trace_dx = cell[0] - prev[0]
                                trace_dy = cell[1] - prev[1]
                            elif idx < len(cells) - 1:
                                next_cell = cells[idx + 1]
                                trace_dx = next_cell[0] - cell[0]
                                trace_dy = next_cell[1] - cell[1]
                            else:
                                trace_dx, trace_dy = 1, 0

                            trace_len = math.sqrt(trace_dx * trace_dx + trace_dy * trace_dy)
                            if trace_len > 0:
                                # Perpendicular to trace direction (rotate 90 degrees)
                                perp_x = -trace_dy / trace_len
                                perp_y = trace_dx / trace_len
                            else:
                                perp_x, perp_y = 0, 1

                            # P gets positive offset, N gets negative offset
                            sign = 1.0 if is_pos_trace else -1.0
                            return (perp_x * half_spacing * sign, perp_y * half_spacing * sign)

                        pos_path = []
                        neg_path = []

                        for i, (px, py, p_layer) in enumerate(pos_cells):
                            px_mm = px * grid.cell_size_mm
                            py_mm = py * grid.cell_size_mm

                            if (px, py, p_layer) in shared_cells:
                                # This cell is shared - apply offset
                                offset_x, offset_y = get_offset_for_cell(pos_cells, i, True)
                                pos_path.append((px_mm + offset_x, py_mm + offset_y, p_layer))
                            else:
                                pos_path.append((px_mm, py_mm, p_layer))

                        for i, (nx, ny, n_layer) in enumerate(neg_cells):
                            nx_mm = nx * grid.cell_size_mm
                            ny_mm = ny * grid.cell_size_mm

                            if (nx, ny, n_layer) in shared_cells:
                                # This cell is shared - apply offset
                                offset_x, offset_y = get_offset_for_cell(neg_cells, i, False)
                                neg_path.append((nx_mm + offset_x, ny_mm + offset_y, n_layer))
                            else:
                                neg_path.append((nx_mm, ny_mm, n_layer))

                        return pos_path, neg_path

                    pos_path_mm, neg_path_mm = cells_to_mm_with_offset(
                        result.pos_cells, result.neg_cells, dp_config.spacing_mm
                    )

                # Create Trace objects for P trace
                for i in range(len(pos_path_mm) - 1):
                    p1, p2 = pos_path_mm[i], pos_path_mm[i + 1]
                    layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(p1[2])])

                    # Check for layer change -> add via
                    if p1[2] != p2[2]:
                        via_pos = (p1[0], p1[1])
                        from_layer = str(LAYER_IDX_TO_NAME[LayerIndex(p1[2])])
                        to_layer = str(LAYER_IDX_TO_NAME[LayerIndex(p2[2])])
                        via = Via(
                            position=via_pos,
                            drill=0.3,
                            width=0.6,
                            layers=(from_layer, to_layer),
                            net=net_pos_name,
                            is_diff_pair=True,  # NEW: Protect diff pair vias from validation removal
                        )
                        all_vias.append(via)

                        # NEW: Add bridge trace from via to next point on new layer
                        # This ensures via is connected on both layers (fixes validation issue)
                        if (p2[0], p2[1]) != via_pos:
                            to_layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(p2[2])])
                            bridge_trace = Trace(
                                start=via_pos,
                                end=(p2[0], p2[1]),
                                width=width,
                                layer=to_layer_name,
                                net=net_pos_name,
                            )
                            all_traces.append(bridge_trace)
                            # Block bridge trace on grid
                            grid.block_trace(
                                [via_pos, (p2[0], p2[1])],
                                width_mm=width,
                                clearance_mm=clearance,
                                layer=p2[2],
                                net_name=net_pos_name,
                            )
                            # Register in DRCOracle
                            if state.drc_oracle:
                                state.drc_oracle.register_track(
                                    OracleTrack(
                                        start=OraclePoint(via_pos[0], via_pos[1]),
                                        end=OraclePoint(p2[0], p2[1]),
                                        width=width,
                                        net=net_pos_name,
                                        layer=p2[2],
                                        diff_pair_companion=net_neg_name,
                                    )
                                )

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
                                    diff_pair_companion=net_neg_name,
                                )
                            )

                # Create Trace objects for N trace
                for i in range(len(neg_path_mm) - 1):
                    p1, p2 = neg_path_mm[i], neg_path_mm[i + 1]
                    layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(p1[2])])

                    # Check for layer change -> add via
                    if p1[2] != p2[2]:
                        via_pos = (p1[0], p1[1])
                        from_layer = str(LAYER_IDX_TO_NAME[LayerIndex(p1[2])])
                        to_layer = str(LAYER_IDX_TO_NAME[LayerIndex(p2[2])])
                        via = Via(
                            position=via_pos,
                            drill=0.3,
                            width=0.6,
                            layers=(from_layer, to_layer),
                            net=net_neg_name,
                            is_diff_pair=True,  # NEW: Protect diff pair vias from validation removal
                        )
                        all_vias.append(via)

                        # NEW: Add bridge trace from via to next point on new layer
                        # This ensures via is connected on both layers (fixes validation issue)
                        if (p2[0], p2[1]) != via_pos:
                            to_layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(p2[2])])
                            bridge_trace = Trace(
                                start=via_pos,
                                end=(p2[0], p2[1]),
                                width=width,
                                layer=to_layer_name,
                                net=net_neg_name,
                            )
                            all_traces.append(bridge_trace)
                            # Block bridge trace on grid
                            grid.block_trace(
                                [via_pos, (p2[0], p2[1])],
                                width_mm=width,
                                clearance_mm=clearance,
                                layer=p2[2],
                                net_name=net_neg_name,
                            )
                            # Register in DRCOracle
                            if state.drc_oracle:
                                state.drc_oracle.register_track(
                                    OracleTrack(
                                        start=OraclePoint(via_pos[0], via_pos[1]),
                                        end=OraclePoint(p2[0], p2[1]),
                                        width=width,
                                        net=net_neg_name,
                                        layer=p2[2],
                                        diff_pair_companion=net_pos_name,
                                    )
                                )

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
                                    diff_pair_companion=net_pos_name,
                                )
                            )

                print(f"      ✓ {net_pos_name}/{net_neg_name} diff pair routed")

        # ========== END DIFFERENTIAL PAIR ROUTING ==========

        # ========== WARN ABOUT UNCONFIGURED DIFFERENTIAL PAIRS ==========
        # Detect nets that look like differential pairs but aren't configured
        # This helps users catch configuration issues before routing fails
        DIFF_PAIR_SUFFIXES = [
            ("+", "-"),  # USB_D+/USB_D-, etc.
            ("_P", "_N"),  # LVDS_P/LVDS_N, etc.
            ("P", "N"),  # DP/DN patterns
            ("_DP", "_DM"),  # USB_DP/USB_DM patterns
        ]
        DIFF_PAIR_KEYWORDS = ["USB", "LVDS", "ETH", "HDMI", "PCIE", "SATA", "DIFF"]

        # Find potential differential pair nets not configured
        unconfigured_diff_candidates = []
        for net_name in net_order:
            if net_name in diff_pair_nets:
                continue  # Already configured

            net_upper = net_name.upper()
            # Check if net name contains differential pair keywords
            has_keyword = any(kw in net_upper for kw in DIFF_PAIR_KEYWORDS)
            # Check if net name ends with differential suffix
            has_suffix = any(
                net_upper.endswith(pos) or net_upper.endswith(neg)
                for pos, neg in DIFF_PAIR_SUFFIXES
            )

            if has_keyword and has_suffix:
                unconfigured_diff_candidates.append(net_name)

        if unconfigured_diff_candidates:
            print(
                f"\n  ⚠️  WARNING: Found {len(unconfigured_diff_candidates)} nets that look like differential pairs but are NOT configured:"
            )
            for net_name in unconfigured_diff_candidates[:10]:  # Limit to first 10
                print(f"      - {net_name}")
            if len(unconfigured_diff_candidates) > 10:
                print(f"      ... and {len(unconfigured_diff_candidates) - 10} more")
            print(
                f"      Add to 'differential_pairs' in config for proper routing with length matching."
            )
            print(
                f"      Without config, these will route as single-ended and may fail or have gaps.\n"
            )

        # ========== END DIFFERENTIAL PAIR WARNING ==========

        # EXP-5: Track nets that were successfully routed this iteration for locking
        newly_locked_nets: set[str] = set()

        for net_idx, net_name in enumerate(net_order):
            if net_name not in net_by_name:
                continue

            # EXP-5: Skip nets that are already locked (successfully routed in previous iteration)
            if state.is_route_locked(net_name):
                print(
                    f"    Skipping net {net_idx + 1}/{len(net_order)}: {net_name} (locked - preserved from previous iteration)"
                )
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
            layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(layer_idx)])

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
            # Phase 3 enhancement: Use DRC oracle positions (correct KiCad positions)
            # and track PTH pad tolerances for endpoint flexibility
            pin_positions = []
            pin_info = []  # Store (ref, name) for lookup
            pins = []  # Store actual Pin objects
            pin_escape_layers = []  # Track which layer each pin escapes to (None = F.Cu)
            pin_tolerances = []  # Track endpoint tolerances for PTH pads
            pin_is_pth = []  # Track PTH status for each pin
            for comp_ref, pin_name in net.pins:
                if comp_ref not in comp_by_ref:
                    continue
                comp = comp_by_ref[comp_ref]
                pin = next(
                    (p for p in comp.pins if p.name == pin_name or p.number == pin_name), None
                )
                if not pin:
                    continue

                # Phase 3: Try DRC oracle first (has correct KiCad positions)
                oracle_results = self._get_pin_positions_from_oracle(
                    comp_ref, pin_name, state
                )

                if oracle_results:
                    # Found pads in oracle - use them (could be multiple for one logical pin)
                    for oracle_pos, is_pth, pad_size in oracle_results:
                        endpoint_tolerance = _compute_endpoint_tolerance(
                            is_pth, pad_size, grid.cell_size_mm
                        )
                        
                        # Check for escape via at this pin position
                        escape_layer, final_pos = self._get_escape_via_for_pin(oracle_pos, net_name, state)

                        pin_positions.append(final_pos)
                        pin_info.append((comp_ref, pin.name))
                        pins.append(pin)
                        pin_escape_layers.append(escape_layer)
                        pin_tolerances.append(endpoint_tolerance)
                        pin_is_pth.append(is_pth)
                        
                        # Debug output for PTH pads and escape vias
                        if is_pth and pad_size:
                            print(
                                f"    PTH pad {net_name}.{comp_ref}.{pin_name} tolerance={endpoint_tolerance:.2f}mm"
                            )
                        if escape_layer is not None:
                            print(
                                f"    Using escape via for {net_name}.{comp_ref}.{pin.name} -> Layer {escape_layer}"
                            )
                else:
                    # Fallback to netlist position (may be wrong after placement optimizer)
                    pos = comp.initial_position or (0, 0)
                    pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
                    endpoint_tolerance = grid.cell_size_mm
                    is_pth = getattr(pin, "is_pth", False)
                    pad_size = None

                    # Check for escape via at this pin position
                    escape_layer, final_pos = self._get_escape_via_for_pin(pin_pos, net_name, state)

                    pin_positions.append(final_pos)
                    pin_info.append((comp_ref, pin.name))
                    pins.append(pin)
                    pin_escape_layers.append(escape_layer)
                    pin_tolerances.append(endpoint_tolerance)
                    pin_is_pth.append(is_pth)
                    
                    if escape_layer is not None:
                        print(
                            f"    Using escape via for {net_name}.{comp_ref}.{pin.name} -> Layer {escape_layer}"
                        )

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

                    # Skip via and stub if pin is already on the target plane layer
                    is_on_layer = False
                    if pin.is_pth or pin.layer == "all":
                        is_on_layer = True
                    elif isinstance(pin.layer, str) and pin.layer == layer_name:
                        is_on_layer = True
                    elif isinstance(pin.layer, (list, tuple)) and layer_name in pin.layer:
                        is_on_layer = True
                        
                    if is_on_layer:
                        continue

                    # Determine via parameters from net class
                    rules = self.net_class_rules.get(net_name)
                    via_params = self._get_via_params_for_net(net_name)
                    via_d = via_params["diameter"]
                    via_drill = via_params["drill"]

                    safe_pos = None
                    if state.drc_oracle:
                        # First, try via directly at pad position
                        sites = state.drc_oracle.get_valid_via_sites(
                            pos, search_radius=0.01, net=net_name
                        )
                        safe_pos = sites[0] if sites else None

                        if not safe_pos:
                            for radius in [0.5, 1.0, 2.0, 5.0]:
                                sites = state.drc_oracle.get_valid_via_sites(
                                    pos, search_radius=radius, net=net_name
                                )
                                if sites:
                                    safe_pos = sites[0]
                                    break

                        if not safe_pos:
                            print(f"WARNING: No safe via site for {net_name} at {pos}")
                            continue
                    else:
                        safe_pos = pos

                    # Prepare via layers
                    via_layers = ("F.Cu", layer_name)
                    if via_layers[0] == via_layers[1]:
                        if pin.layer == "B.Cu" or "B.Cu" in str(pin.layer):
                            via_layers = ("B.Cu", "F.Cu")
                        else:
                            # Already on the correct layer, skip via
                            continue

                    # Create Via
                    via = Via(
                        position=safe_pos,
                        drill=via_drill,
                        width=via_d,
                        layers=via_layers,
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

                    # Add stub trace
                    if (safe_pos != pos or not pin.is_pth) and not is_on_layer:
                        stub_valid = False
                        stub_end = None
                        
                        if safe_pos == pos:
                            # 0.1mm stub for connectivity
                            stub_candidates = [
                                (pos[0] + 0.1, pos[1]),
                                (pos[0] - 0.1, pos[1]),
                                (pos[0], pos[1] + 0.1),
                                (pos[0], pos[1] - 0.1),
                            ]
                            for candidate in stub_candidates:
                                if state.drc_oracle:
                                    s_width = rules.trace_width if rules else self.default_width
                                    valid, _ = state.drc_oracle.can_place_track_segment(
                                        start=pos, end=candidate,
                                        layer=0 if "F.Cu" in str(pin.layer) or "F.Cu" == layer_name else 3,
                                        net=net_name, width=s_width, neckdown=True,
                                    )
                                    if valid:
                                        stub_end = candidate
                                        stub_valid = True
                                        break
                                else:
                                    stub_end = stub_candidates[0]
                                    stub_valid = True
                                    break
                        else:
                            stub_end = safe_pos
                            stub_valid = True

                        if stub_valid and stub_end and stub_end != pos:
                            stub_layer_name = "F.Cu" if "F.Cu" in str(pin.layer) or "F.Cu" == layer_name else layer_name
                            stub_layer_idx = layer_name_to_index(stub_layer_name).value
                            stub_width = s_width if 's_width' in locals() else self.default_width
                            all_traces.append(
                                Trace(
                                    start=pos,
                                    end=stub_end,
                                    width=stub_width,
                                    layer=stub_layer_name,
                                    net=net_name
                                )
                            )
                            if state.drc_oracle:
                                state.drc_oracle.register_track(
                                    OracleTrack(
                                        start=OraclePoint(pos[0], pos[1]),
                                        end=OraclePoint(stub_end[0], stub_end[1]),
                                        width=stub_width,
                                        net=net_name,
                                        layer=stub_layer_idx,
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

                # ========== PHASE 4: POWER NET COMPLETION ==========
                # For plane nets with remaining unconnected pads, route stub
                # traces to the nearest via to ensure full connectivity.

                # Check if any pads are still unconnected
                via_positions_for_net = set(
                    v.position for v in all_vias if v.net == net_name
                )

                unconnected_pads = []
                for i, pos in enumerate(pin_positions):
                    pin = pins[i]
                    # Skip PTH pads (barrel connects all layers)
                    if pin.is_pth:
                        continue

                    # Check if pad has a via within connection distance
                    is_connected = any(
                        ((pos[0] - vp[0]) ** 2 + (pos[1] - vp[1]) ** 2) ** 0.5 < 0.5
                        for vp in via_positions_for_net
                    )

                    if not is_connected:
                        unconnected_pads.append((pos, pin))

                if unconnected_pads:
                    print(f"  [PowerComplete] {net_name}: {len(unconnected_pads)} pads need stub traces")

                    for pad_pos, pin in unconnected_pads:
                        # Find nearest via on same net
                        nearest_via = None
                        nearest_dist = float("inf")

                        for via in all_vias:
                            if via.net != net_name:
                                continue
                            dist = ((pad_pos[0] - via.position[0]) ** 2 +
                                    (pad_pos[1] - via.position[1]) ** 2) ** 0.5
                            if dist < nearest_dist:
                                nearest_dist = dist
                                nearest_via = via

                        if not nearest_via or nearest_dist > 10.0:  # Max 10mm stub
                            print(f"    No suitable via for {net_name} pad at {pad_pos}")
                            continue

                        # Validate stub trace with DRC oracle
                        stub_valid = True
                        if state.drc_oracle:
                            stub_valid, reason = state.drc_oracle.can_place_track_segment(
                                start=pad_pos,
                                end=nearest_via.position,
                                layer=0,  # F.Cu
                                net=net_name,
                                width=width,
                            )
                            if not stub_valid:
                                print(f"      REJECTED plane stub for {net_name}: {reason}")
                        
                        if stub_valid:
                            # Create stub trace from pad to via
                            all_traces.append(
                                Trace(
                                    start=pad_pos,
                                    end=nearest_via.position,
                                    width=width,
                                    layer=layer_name,
                                    net=net_name,
                                )
                            )

                            # Block on grid
                            grid.block_trace(
                                [pad_pos, nearest_via.position],
                                width_mm=width,
                                clearance_mm=clearance,
                                layer=layer_idx,
                                net_name=net_name,
                            )

                            # Register in DRC oracle
                            if state.drc_oracle:
                                state.drc_oracle.register_track(
                                    OracleTrack(
                                        start=OraclePoint(pad_pos[0], pad_pos[1]),
                                        end=OraclePoint(nearest_via.position[0], nearest_via.position[1]),
                                        width=width,
                                        net=net_name,
                                        layer=layer_idx,
                                    )
                                )

                        print(f"    Added {nearest_dist:.1f}mm stub for {net_name} pad at {pad_pos}")

                # ========== END PHASE 4 ==========

                # Add a marker trace on the plane layer so the net
                # appears in state.routes. Plane nets with all pins
                # already on the plane layer produce no physical
                # trace segments, but downstream consumers (e.g. SM3
                # in the HV/LV partition integration test) need to
                # confirm the net was not dropped. A zero-length
                # trace at the first pin's position serves as a
                # visible "routed" marker without affecting DRC.
                if pin_positions:
                    first_pos = pin_positions[0]
                    all_traces.append(
                        Trace(
                            start=first_pos,
                            end=first_pos,
                            width=width,
                            layer=layer_name,
                            net=net_name,
                        )
                    )
                    if state.drc_oracle:
                        state.drc_oracle.register_track(
                            OracleTrack(
                                start=OraclePoint(first_pos[0], first_pos[1]),
                                end=OraclePoint(first_pos[0], first_pos[1]),
                                width=width,
                                net=net_name,
                                layer=layer_idx,
                            )
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

            mst_edges = _compute_mst(pin_positions)

            # Snap pin positions to grid for A* pathfinding
            snapped_positions = [snap_to_grid(p, grid.cell_size_mm) for p in pin_positions]

            net_multilayer_paths = []  # Results from multi-layer routing

            # Create multi-layer pathfinder with net-specific allowed layers
            # This enables routing on inner layers for congested signal nets
            # NOTE: Always use MultiLayerAStar (has Cython support) - removed old Python-only DeterministicAStar
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
                base_iterations_per_cell=200,  # EXP-2: Increased from 100 to help congested routes
            )

            # EXP-5: Track if any segment fails to route for this net
            net_routing_failed = False

            # Route all edges in the MST
            for idx1, idx2 in mst_edges:
                # Use original pin positions (MM) for pathfinding
                # The pathfinders will snap to grid cells internally but use these exact
                # endpoints for final segment reconstruction to avoid dangling tracks.
                p1 = pin_positions[idx1]
                p2 = pin_positions[idx2]

                p1_snapped = snapped_positions[idx1]
                p2_snapped = snapped_positions[idx2]

                # Determine start/end layers based on escape vias
                # If escape via exists, use escape layer; otherwise use default layer
                start_layer_for_route = (
                    pin_escape_layers[idx1] if pin_escape_layers[idx1] is not None else layer_idx
                )
                end_layer_for_route = (
                    pin_escape_layers[idx2] if pin_escape_layers[idx2] is not None else layer_idx
                )

                # Calculate Manhattan distance in cells to decide routing strategy
                distance_cells = (
                    abs(int(p1_snapped[0] / grid.cell_size_mm) - int(p2_snapped[0] / grid.cell_size_mm))
                    + abs(int(p1_snapped[1] / grid.cell_size_mm) - int(p2_snapped[1] / grid.cell_size_mm))
                )
                
                # Use bidirectional A* for long routes on HV/Power nets
                # Threshold: >30 cells empirically determined (10-100x speedup above this)
                # Use bidirectional A* for long routes
                # - HV/Power nets >30 cells (IEC safety routes need best paths)
                # - FinePitch nets >30 cells (long MCU signal routes)
                # - ANY net >60 cells (very long routes benefit regardless of class)
                use_bidirectional = (
                    distance_cells > 60  # Very long routes always use bidirectional
                    or (
                        distance_cells > 30
                        and net_class_name in ["HighVoltage", "Power", "PowerTrace", "FinePitch", "Signal"]
                    )
                )
                
                if use_bidirectional:
                    # Import bidirectional A* (lazy import to avoid circular deps)
                    from .bidirectional_astar import BidirectionalAStar
                    
                    bidirectional = BidirectionalAStar(
                        grid=grid,
                        drc_oracle=state.drc_oracle,
                        net_name=net_name,
                        trace_width=width,
                        via_cost=3.0,
                        via_diameter=0.6,
                        via_drill=0.3,
                        allowed_layers=allowed_layers,
                        max_iterations=200000,  # Experiment B: Increased from 10000
                    )
                    
                    print(f"  Using bidirectional A* for {net_name} ({distance_cells} cells)")
                    
                    multilayer_result = bidirectional.find_path(
                        start=p1,
                        end=p2,
                        start_layer=start_layer_for_route,
                        end_layer=end_layer_for_route,
                    )
                    
                    if multilayer_result:
                        print(f"  ✓ Bidirectional found path: {bidirectional.last_fwd_iterations}fwd + {bidirectional.last_bwd_iterations}bwd iterations")
                    else:
                        if bidirectional.last_timeout:
                            print(f"  ✗ Bidirectional timeout after {bidirectional.last_fwd_iterations+bidirectional.last_bwd_iterations} iterations")
                        else:
                            print(f"  ✗ Bidirectional found no path")
                else:
                    # Use standard unidirectional multi-layer A* routing
                    
                    # For PTH pins, we can end on any layer. For SMD, we MUST end on pad layer.
                    # end_layer_for_route already contains the pin's layer or escape layer.
                    pin2 = pins[idx2]
                    final_end_layer = end_layer_for_route if not pin2.is_pth else -1
                    
                    multilayer_result = multilayer_pathfinder.find_path(
                        start=p1,
                        end=p2,
                        start_layer=start_layer_for_route,
                        end_layer=final_end_layer,
                    start_tolerance=pin_tolerances[idx1],
                    end_tolerance=pin_tolerances[idx2],
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
                    net_routing_failed = True  # EXP-5: Mark this net as having a failed segment

            # Commit multi-layer paths (with vias and traces)
            via_d = 0.6
            via_drill = 0.3
            if self.design_rules:
                rules = self.design_rules.get_rules_for_net(net_name)
                via_d = rules.via_diameter
                via_drill = rules.via_drill

            for ml_path in net_multilayer_paths:
                # Commit trace segments
                for segment in ml_path.segments:
                    seg_layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(segment.layer)])

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
                    from_layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(from_layer)])
                    to_layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(to_layer)])

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

            # MultiLayerAStar handles vias automatically - no need for manual via generation

            net_elapsed = time.time() - net_start
            # EXP-5: Lock net if all segments routed successfully
            if not net_routing_failed and not is_plane:
                newly_locked_nets.add(net_name)
                print(f"      ✓ {net_name} routed in {net_elapsed:.2f}s [LOCKED]", flush=True)
            elif is_plane:
                # Plane nets are always "successful" since they just add vias
                newly_locked_nets.add(net_name)
                print(f"      ✓ {net_name} routed in {net_elapsed:.2f}s (plane)", flush=True)
            else:
                print(
                    f"      ⚠ {net_name} routed in {net_elapsed:.2f}s (partial - not locked)",
                    flush=True,
                )

            # U3: build a per-net report. The bottleneck is attached
            # later by ``_attach_bottlenecks``. Plane nets and
            # successfully routed nets still get a report (status
            # SUCCESS) so the post-mortem pass can skip them
            # unambiguously; failed/partial/blocked nets drive the
            # min-cut analysis.
            if not is_plane:
                routed_count = len(net_multilayer_paths)
                total_segments = max(1, len(mst_edges))
                status = (
                    RoutingStatus.FAILED
                    if net_routing_failed
                    else RoutingStatus.SUCCESS
                )
                failure_reason = (
                    FailureReason.CHANNEL_CAPACITY if net_routing_failed else None
                )
                report = NetRoutingReport(
                    net_name=net_name,
                    status=status,
                    score=1.0 if status == RoutingStatus.SUCCESS else 0.0,
                    pins=len(net.pins),
                    routed_segments=routed_count,
                    total_segments=total_segments,
                    failure_reason=failure_reason,
                )
                all_net_reports.append(report)

        # EXP-5: Update state with newly locked routes
        if newly_locked_nets:
            print(f"\n  EXP-5: Locking {len(newly_locked_nets)} successfully routed nets")
            state = state.with_locked_routes(newly_locked_nets)

        # ========== PHASE 2: ROUTING RETRY LOGIC ==========
        # Retry failed nets with increased iteration budgets.
        # This handles cases where initial routing failed due to congestion.
        # perf: Reduced from 5→3 retries and 10000→3000 base to avoid timeout
        # on fundamentally unroutable nets. Added per-retry time cap.
        MAX_RETRIES = 3
        BASE_ITERATIONS = 3000
        ITERATION_MULTIPLIER = 2.0
        RETRY_TIME_LIMIT_S = 15.0  # Cap per-retry wall time

        # Collect nets that failed to route completely
        failed_nets = []
        for net_name in net_order:
            if net_name in diff_pair_nets:
                continue  # Diff pairs handled separately
            if state.is_route_locked(net_name):
                continue  # Already successfully routed
            if net_name in newly_locked_nets:
                continue  # Just locked this iteration

            # Check if net has 2+ pins (should have been routed)
            net = net_by_name.get(net_name)
            if net and len(net.pins) >= 2:
                # Check if it's a plane net (those don't need retry)
                if not is_plane_by_net.get(net_name, False):
                    failed_nets.append(net_name)

        if failed_nets:
            print(f"\n  [Retry] Found {len(failed_nets)} failed nets to retry...")

            retry_queue = [(net_name, 1) for net_name in failed_nets]
            retry_successes = 0
            retry_total_start = time.time()

            while retry_queue:
                # perf: Cap total retry time to prevent runaway on unroutable nets
                retry_elapsed = time.time() - retry_total_start
                if retry_elapsed > 120.0:  # Total retry budget: 2 minutes
                    print(f"  [Retry] Total retry time {retry_elapsed:.1f}s exceeded 120s limit, stopping")
                    break

                net_name, retry_count = retry_queue.pop(0)

                if retry_count > MAX_RETRIES:
                    print(f"    {net_name}: Exceeded max retries ({MAX_RETRIES})")
                    continue

                # Calculate increased iteration budget
                iteration_budget = int(BASE_ITERATIONS * (ITERATION_MULTIPLIER ** retry_count))

                net = net_by_name[net_name]
                net_class_name = getattr(net, "net_class", None)

                # Get rules
                width = self.default_width
                clearance = self.default_clearance
                if self.design_rules:
                    rules = self.design_rules.get_rules_for_net(net_name, net_class=net_class_name)
                    width = rules.trace_width
                    clearance = rules.clearance

                # Get allowed layers - on retry, allow ALL layers for maximum flexibility
                allowed_layers = [0, 1, 2, 3]  # All 4 layers

                # Rebuild pin positions using DRC oracle
                pin_positions = []
                pin_escape_layers = []
                pin_tolerances = []
                for comp_ref, pin_name in net.pins:
                    if comp_ref not in comp_by_ref:
                        continue
                    comp = comp_by_ref[comp_ref]
                    pin = next(
                        (p for p in comp.pins if p.name == pin_name or p.number == pin_name), None
                    )
                    if not pin:
                        continue

                    # Use DRC oracle position if available
                    oracle_results = self._get_pin_positions_from_oracle(
                        comp_ref, pin_name, state
                    )
                    
                    if oracle_results:
                        for oracle_pos, is_pth, pad_size in oracle_results:
                            endpoint_tolerance = _compute_endpoint_tolerance(
                                is_pth, pad_size, grid.cell_size_mm
                            )
                            escape_layer, final_pos = self._get_escape_via_for_pin(oracle_pos, net_name, state)
                            pin_positions.append(final_pos)
                            pin_escape_layers.append(escape_layer)
                            pin_tolerances.append(endpoint_tolerance)
                    else:
                        endpoint_tolerance = grid.cell_size_mm
                        pos = comp.initial_position or (0, 0)
                        pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
                        is_pth = getattr(pin, "is_pth", False)

                        escape_layer, final_pos = self._get_escape_via_for_pin(pin_pos, net_name, state)
                        pin_positions.append(final_pos)
                        pin_escape_layers.append(escape_layer)
                        pin_tolerances.append(endpoint_tolerance)

                if len(pin_positions) < 2:
                    continue

                print(
                    f"    Retry {retry_count}/{MAX_RETRIES}: {net_name} (budget: {iteration_budget} iters)"
                )

                # Create pathfinder with increased budget
                retry_pathfinder = MultiLayerAStar(
                    grid=grid,
                    drc_oracle=state.drc_oracle,
                    net_name=net_name,
                    net_class=net_class_name or "Default",
                    trace_width=width,
                    via_cost=2.0,  # Lower via cost on retry to encourage layer changes
                    allowed_layers=allowed_layers,
                    congestion_detector=congestion_detector,
                    use_adaptive_budget=True,
                    base_iterations_per_cell=iteration_budget,  # Increased budget
                )

                # Compute MST and route
                snapped_positions = [snap_to_grid(p, grid.cell_size_mm) for p in pin_positions]
                mst_edges = _compute_mst(pin_positions)

                retry_success = True
                retry_paths = []

                for idx1, idx2 in mst_edges:
                    p1_snapped = snapped_positions[idx1]
                    p2_snapped = snapped_positions[idx2]

                    start_layer = pin_escape_layers[idx1] if pin_escape_layers[idx1] else 0
                    end_layer = pin_escape_layers[idx2] if pin_escape_layers[idx2] else 0

                    result = retry_pathfinder.find_path(
                        start=p1_snapped,
                        end=p2_snapped,
                        start_layer=start_layer,
                        end_layer=end_layer if end_layer != 0 else -1,
                        start_tolerance=pin_tolerances[idx1],
                        end_tolerance=pin_tolerances[idx2],
                    )

                    if result:
                        retry_paths.append(result)
                    else:
                        retry_success = False
                        break

                if retry_success and retry_paths:
                    # Commit all retry paths
                    via_d = 0.6
                    via_drill = 0.3
                    if self.design_rules:
                        rules = self.design_rules.get_rules_for_net(net_name)
                        via_d = rules.via_diameter
                        via_drill = rules.via_drill

                    for ml_path in retry_paths:
                        # Commit trace segments
                        for segment in ml_path.segments:
                            seg_layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(segment.layer)])

                            # Block on grid
                            grid.block_trace(
                                [segment.start, segment.end],
                                width_mm=width,
                                clearance_mm=clearance,
                                layer=segment.layer,
                                net_name=net_name,
                            )

                            # Validate and create trace
                            trace_valid = True
                            if state.drc_oracle:
                                trace_valid, _ = state.drc_oracle.can_place_track_segment(
                                    start=segment.start,
                                    end=segment.end,
                                    layer=segment.layer,
                                    net=net_name,
                                    width=width,
                                )

                            if trace_valid:
                                all_traces.append(
                                    Trace(
                                        start=segment.start,
                                        end=segment.end,
                                        width=width,
                                        layer=seg_layer_name,
                                        net=net_name,
                                    )
                                )

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

                        # Commit vias
                        for vx, vy, from_layer, to_layer in ml_path.via_positions:
                            from_layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(from_layer)])
                            to_layer_name = str(LAYER_IDX_TO_NAME[LayerIndex(to_layer)])

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

                    newly_locked_nets.add(net_name)
                    retry_successes += 1
                    print(f"      ✓ {net_name} routed on retry {retry_count}")
                else:
                    # Requeue with higher retry count
                    retry_queue.append((net_name, retry_count + 1))
                    print(f"      ✗ {net_name} retry {retry_count} failed, requeuing")

                # U3: build a per-net report after each retry attempt.
                # A successful retry overwrites the prior FAILED report
                # so the post-mortem pass sees the net as SUCCESS.
                retry_status = (
                    RoutingStatus.SUCCESS if retry_success else RoutingStatus.FAILED
                )
                retry_report = NetRoutingReport(
                    net_name=net_name,
                    status=retry_status,
                    score=1.0 if retry_status == RoutingStatus.SUCCESS else 0.0,
                    pins=len(net.pins),
                    routed_segments=len(retry_paths) if retry_success else 0,
                    total_segments=max(1, len(mst_edges)),
                    failure_reason=(
                        None
                        if retry_status == RoutingStatus.SUCCESS
                        else FailureReason.CHANNEL_CAPACITY
                    ),
                )
                # Replace any prior report for this net (e.g. an earlier
                # failed attempt or a successful first-pass attempt).
                all_net_reports[:] = [
                    r for r in all_net_reports if r.net_name != net_name
                ]
                all_net_reports.append(retry_report)

            if retry_successes > 0:
                print(f"\n  [Retry] Successfully routed {retry_successes} nets on retry")
                # Update locked routes with retry successes
                state = state.with_locked_routes(newly_locked_nets)

        # ========== END PHASE 2 ==========

        # ========== POST-MORTEM: MIN-CUT BOTTLENECK ANALYSIS (U3) ==========
        # For every net that the routing pass could not complete, attach a
        # BottleneckGeometry via ``analyze_bottleneck`` so the closure test
        # JSON surfaces an actionable signal. The pass/fail result of the
        # routing loop is the source of truth; this is informational only
        # and is wrapped in a broad try/except so it never crashes the
        # routing pass.
        self._attach_bottlenecks(state, all_net_reports, net_by_name, grid)

        return replace(state, routes=frozenset(all_traces), vias=frozenset(all_vias))

    def _attach_bottlenecks(
        self,
        state: BoardState,
        all_net_reports: list[NetRoutingReport],
        net_by_name: dict,
        grid: "ClearanceGrid",
    ) -> None:
        """Attach ``BottleneckGeometry`` to every failed/partial report.

        For each report whose status is FAILED, PARTIAL, or BLOCKED, this
        method calls ``analyze_bottleneck`` (U2) and, on a non-None
        return, mutates the report in place to record the geometry. The
        analysis is wrapped in a broad try/except so any failure inside
        ``analyze_bottleneck`` (e.g. networkx import error, exception
        inside the graph builder) cannot crash the routing pass.

        Successful nets are intentionally skipped — the routing
        pass/fail result is the source of truth, and bottleneck
        analysis for completed nets is wasted work.

        The closure test's WARNING capture picks up the
        ``logger.warning("routing_bottleneck: %s", result.message)``
        call so the human-readable message surfaces in the JSON
        output.
        """
        net_class_rules: dict = {}
        design_rules = getattr(state, "design_rules", None)
        if design_rules and getattr(design_rules, "net_classes", None):
            net_class_rules = {
                name: rule
                for name, rule in design_rules.net_classes.items()
            }

        for idx, report in enumerate(all_net_reports):
            if report.status in (RoutingStatus.SUCCESS, RoutingStatus.FLAGGED):
                continue
            net = net_by_name.get(report.net_name)
            if net is None:
                continue
            try:
                result = analyze_bottleneck(
                    grid=grid,
                    net=net,
                    board_state=state,
                    report=report,
                    net_class_rules=net_class_rules or None,
                )
            except Exception as exc:  # noqa: BLE001 — never crash the pass
                logger.debug(
                    "analyze_bottleneck raised for %s: %s",
                    report.net_name,
                    exc,
                )
                continue

            if result is None:
                # The failure reason is not a capacity/clearance one;
                # ``analyze_bottleneck`` correctly returned None and the
                # routing pass already classifies this net as a
                # different failure mode.
                continue

            # NetRoutingReport is a frozen dataclass; replace with a
            # new instance that carries the bottleneck, and write it
            # back into ``all_net_reports`` so the caller can observe
            # the change.
            all_net_reports[idx] = replace(report, bottleneck=result)
            if result.message:
                logger.warning("routing_bottleneck: %s", result.message)
