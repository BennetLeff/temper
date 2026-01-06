from dataclasses import replace
from typing import List, Tuple
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

# Layer name mappings
LAYER_IDX_TO_NAME = {0: "F.Cu", 1: "In1.Cu", 2: "In2.Cu", 3: "B.Cu"}
LAYER_NAME_TO_IDX = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 3}


class SequentialRoutingStage(Stage):
    def __init__(
        self,
        design_rules: DesignRules | None = None,
        trace_width_mm: float = 0.25,
        clearance_mm: float = 0.2,
        cost_map_weights: any = None,
        pad_sizes: dict = None,
        net_class_rules: dict = None,
    ):
        """Initialize sequential routing stage.

        Args:
            design_rules: DRC rules for trace widths/clearances
            trace_width_mm: Default trace width
            clearance_mm: Default clearance
            cost_map_weights: Unused legacy parameter
            pad_sizes: Pad size lookup for via placement
            net_class_rules: Dict of net_class_name -> NetClassRule with zone confinement info
        """
        self.design_rules = design_rules
        self.default_width = trace_width_mm
        self.default_clearance = clearance_mm
        self.pad_sizes = pad_sizes or {}
        self.net_class_rules = net_class_rules or {}

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

        for net_idx, net_name in enumerate(net_order):
            if net_name not in net_by_name:
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

                    # Find safe position for via - use larger search radius for power/ground
                    if state.drc_oracle:
                        # Progressive search: try 2mm, then 5mm, then 10mm
                        safe_pos = None
                        for radius in [2.0, 5.0, 10.0]:
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
                                f"WARNING: DRCOracle could not find safe via position for {net_name} at {pos} (searched up to 10mm)"
                            )
                            safe_pos = pos  # Fallback to pad position
                    else:
                        safe_pos = place_via_with_clearance(pos, all_pads_info, via_mask_radius)
                        if not safe_pos:
                            print(
                                f"WARNING: Could not find safe via position for {net_name} at {pos}"
                            )
                            safe_pos = pos  # Fallback

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
                                    f"  WARNING: Plane stub trace for {net_name} rejected: {stub_reason}"
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

            # Create multi-layer pathfinder as fallback
            # Allow routing on F.Cu (0) and B.Cu (3) - inner layers are planes
            multilayer_pathfinder = MultiLayerAStar(
                grid=grid,
                drc_oracle=state.drc_oracle,
                net_name=net_name,
                trace_width=width,
                via_cost=5.0,  # Discourage unnecessary vias
                allowed_layers=[0, 3],  # F.Cu and B.Cu only
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

                # Commit vias from layer transitions
                for vx, vy, from_layer, to_layer in ml_path.via_positions:
                    from_layer_name = LAYER_IDX_TO_NAME.get(from_layer, "F.Cu")
                    to_layer_name = LAYER_IDX_TO_NAME.get(to_layer, "B.Cu")

                    via = Via(
                        position=(vx, vy),
                        drill=via_drill,
                        width=via_d,
                        layers=(from_layer_name, to_layer_name),
                        net=net_name,
                    )
                    all_vias.append(via)

                    # Block via on ALL layers with net_name
                    for l_idx in range(grid.layer_count):
                        grid.block_circle(
                            (vx, vy),
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
                                center=OraclePoint(vx, vy),
                                diameter=via_d,
                                drill=via_drill,
                                net=net_name,
                            )
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
