from typing import Any

from temper_placer.core.pin_geometry import pin_world_position

from ..state import BoardState
from . import _grid_fence, _grid_hv
from ._grid_core import ClearanceGrid
from .base import Stage


class ClearanceGridStage(Stage):
    def __init__(
        self,
        cell_size_mm: float = 0.5,
        layer_count: int = 2,
        pad_sizes: dict | None = None,
        max_clearance_mm: float = 2.5,
        net_class_clearances: dict[str, float] | None = None,
        net_classes: dict[str, str] | None = None,
        pth_mask_expansion_mm: float = 0.15,
        smd_mask_expansion_mm: float = 0.10,
        inner_layer_clearance_mm: float = 0.5,
        hv_exclusion_zones: list | None = None,
        default_trace_width_mm: float = 0.25,
    ):
        """Initialize clearance grid stage.

        Args:
            cell_size_mm: Grid cell size in mm
            layer_count: Number of copper layers
            pad_sizes: Optional dict of pad sizes
            max_clearance_mm: Maximum clearance to use for blocking (fallback if net class not found)
            net_class_clearances: Optional mapping of net class name to clearance in mm
            net_classes: Optional mapping of net name to net class name (for per-net clearance lookup)
            pth_mask_expansion_mm: Mask expansion for PTH pads (default: 0.15mm)
            smd_mask_expansion_mm: Mask expansion for SMD pads (default: 0.10mm)
            inner_layer_clearance_mm: Max clearance for inner layers (default: 0.5mm).
                Inner layers don't need creepage clearance since they're encapsulated
                in FR4. This prevents high-voltage PTH pads from blocking escape routes on
                inner layers with their full surface clearance (e.g., 6mm -> 0.5mm).
            hv_exclusion_zones: List of HVExclusionZone configs for signal avoidance.
                EXP-13: Zones where specified nets must not route (blocked on all layers).
            default_trace_width_mm: Default trace width to account for in blocking (Minkowski sum).
                Since A* treats the agent as a point, we must expand obstacles by the agent's radius.
        """
        self.cell_size_mm = cell_size_mm
        self.layer_count = layer_count
        self.pad_sizes = pad_sizes or {}
        self.max_clearance_mm = max_clearance_mm
        self.net_class_clearances = net_class_clearances or {}
        self.net_classes = net_classes or {}
        self.pth_mask_expansion_mm = pth_mask_expansion_mm
        self.smd_mask_expansion_mm = smd_mask_expansion_mm
        self.inner_layer_clearance_mm = inner_layer_clearance_mm
        self.hv_exclusion_zones = hv_exclusion_zones or []
        self.default_trace_width_mm = default_trace_width_mm

    def _get_clearance_for_net(self, net_name: str, state: "BoardState", layer: int = 0) -> float:
        """Get the clearance for a specific net based on its net class and layer.

        This uses per-net-class clearances instead of a global max_clearance,
        which dramatically reduces grid congestion on boards with mixed clearances
        (e.g., HighVoltage at 6mm vs Signal at 0.2mm).

        For inner layers (not F.Cu or B.Cu), clearances are capped at
        inner_layer_clearance_mm since creepage requirements only apply to
        exposed surface layers. This is critical for routing near high-voltage
        PTH pads - their 6mm surface clearance would otherwise block all
        inner layers, making escape routing impossible.

        Args:
            net_name: Name of the net
            state: Current board state with netlist info
            layer: Layer index (0=F.Cu, 1=In1.Cu, 2=In2.Cu, 3=B.Cu for 4-layer)

        Returns:
            Clearance in mm for this net on this layer
        """
        if not net_name:
            return self.max_clearance_mm

        # Try to find net class from config mapping first
        net_class = self.net_classes.get(net_name)

        # Fall back to netlist if not in config
        if not net_class and state.netlist:
            for net in state.netlist.nets:
                if net.name == net_name:
                    net_class = getattr(net, "net_class", None)
                    break

        # Look up clearance for this net class
        if net_class and net_class in self.net_class_clearances:
            clearance = self.net_class_clearances[net_class]
        else:
            # Default clearance for unknown nets (use conservative Signal clearance, not max)
            clearance = self.net_class_clearances.get("Signal", 0.2)

        # Cap clearance on inner layers - they don't need creepage clearance
        # Inner layers are encapsulated in FR4, so air gap requirements don't apply
        is_inner_layer = 0 < layer < (self.layer_count - 1)
        if is_inner_layer and clearance > self.inner_layer_clearance_mm:
            return self.inner_layer_clearance_mm

        return clearance

    @property
    def name(self) -> str:
        return "clearance_grid"

    def run(self, state: BoardState) -> BoardState:
        if not state.board:
            return state

        grid = ClearanceGrid(
            width_mm=state.board.width,
            height_mm=state.board.height,
            cell_size_mm=self.cell_size_mm,
            layer_count=self.layer_count,
        )

        # Block pads from OTHER nets with net-class aware clearance buffer.
        # This allows routing TO target pads while avoiding shorts.
        # Pads are blocked with inflated radius = pad_r + clearance + trace_width/2 + mask

        if state.netlist:
            placements_dict = dict(state.placements) if state.placements else {}

            # Build net->pads mapping for selective unblocking
            net_pads: dict[str, list[dict[str, Any]]] = {}
            all_pads_for_expansion = []
            for component in state.netlist.components:
                pos = placements_dict.get(component.ref, component.initial_position)
                if pos is None:
                    continue

                for pin in component.pins:
                    pin_pos = pin_world_position(pin, component)

                    pad_radius = 0.5
                    pad_width = 1.0
                    pad_height = 1.0
                    pad_key = (component.ref, pin.name)
                    if pad_key in self.pad_sizes:
                        real_pad = self.pad_sizes[pad_key]
                        pad_radius = max(real_pad.size.X, real_pad.size.Y) / 2.0
                        pad_width = real_pad.size.X
                        pad_height = real_pad.size.Y

                    # Store pad info
                    net = pin.net or ""
                    if net not in net_pads:
                        net_pads[net] = []

                    # Determine target layers
                    if pin.is_pth or pin.layer == "all":
                        target_layers = list(range(grid.layer_count))
                    elif pin.layer == "F.Cu":
                        target_layers = [0]
                    elif pin.layer == "B.Cu":
                        target_layers = [grid.layer_count - 1]
                    elif pin.layer == "In1.Cu" and grid.layer_count > 1:
                        target_layers = [1]
                    elif pin.layer == "In2.Cu" and grid.layer_count > 2:
                        target_layers = [2]
                    else:
                        target_layers = list(range(grid.layer_count))

                    pad_dict = {
                        "pos": pin_pos,
                        "size": (pad_width, pad_height),  # Store full size
                        "radius": pad_radius,  # Keep radius for circle fallback
                        "shape": pin.shape,  # Store shape
                        "rotation": getattr(pin, "rotation", 0.0),  # Store rotation if available
                        "layers": target_layers,
                        "is_pth": pin.is_pth,
                        "ref": component.ref,  # Store ref for lookup
                        "name": pin.name,  # Store pin name for lookup
                    }
                    net_pads[net].append(pad_dict)
                    all_pads_for_expansion.append(pad_dict)

            # Block all pads with clearance based on the pad's net class.
            for net_name, pads in net_pads.items():
                for pad in pads:
                    # Calculate clearance with PTH/SMD-aware mask expansion
                    mask_expansion = (
                        self.pth_mask_expansion_mm if pad["is_pth"] else self.smd_mask_expansion_mm
                    )

                    # Try to get precise geometry from pad_sizes
                    pad_key = (pad["ref"], pad["name"])
                    real_pad = self.pad_sizes.get(pad_key)

                    use_rect_blocking = False
                    rect_size = (0.0, 0.0)

                    if real_pad:
                        # Use shape and rotation from real pad data
                        shape = real_pad.shape
                        rotation = getattr(real_pad, "rotation", 0.0)
                        size_x = real_pad.size.X
                        size_y = real_pad.size.Y

                        if shape in ["rect", "roundrect", "oval"]:
                            # Handle 0/90/180/270 rotations
                            norm_rot = int(round(rotation)) % 180
                            if norm_rot == 0:
                                rect_size = (size_x, size_y)
                                use_rect_blocking = True
                            elif norm_rot == 90:
                                rect_size = (size_y, size_x)
                                use_rect_blocking = True
                            # For arbitrary rotations, we fall back to circle for now

                    # Fallback to netlist-derived data if pad_sizes missing (shouldn't happen with full parser)
                    if not use_rect_blocking and pad.get("shape") in ["rect", "roundrect", "oval"]:
                        # Assuming axis-aligned if we don't know rotation
                        # This is risky, so we stick to circle if uncertain
                        pass

                    for layer_idx in pad["layers"]:
                        if layer_idx < grid.layer_count:
                            # Get layer-specific clearance (inner layers have reduced clearance)
                            net_clearance = self._get_clearance_for_net(
                                net_name, state, layer=layer_idx
                            )

                            # EXP-24: Mechanical pads (no net) use zero clearance to avoid self-blocking
                            # but still block routing through the physical hole/pad.
                            current_mask = mask_expansion if net_name else 0.0
                            current_clearance = net_clearance if net_name else 0.0

                            # Add trace radius to obstacle clearance (Minkowski sum)
                            total_clearance = (
                                current_clearance
                                + current_mask
                                + (self.default_trace_width_mm / 2.0)
                            )

                            if use_rect_blocking:
                                grid.block_rect(
                                    center=pad["pos"],
                                    size=rect_size,
                                    clearance_mm=total_clearance,
                                    layer=layer_idx,
                                    net_name=net_name,
                                    is_obstacle=False,  # Mark as net, not obstacle
                                )
                            else:
                                grid.block_circle(
                                    pad["pos"],
                                    radius_mm=pad["radius"],
                                    clearance_mm=total_clearance,
                                    layer=layer_idx,
                                    net_name=net_name,
                                )

            # @req(2026-06-23-005, U2, R1, R2, R3): Pre-route creepage expansion
            # pass. After the per-net blocking above, walk the HV-pad set
            # (resolved by U1's `hv_pad_set`) and re-block each HV pad with its
            # per-layer effective creepage distance applied. Non-HV pads are
            # left at their current blocking radius.
            component_positions = {
                component.ref: positions
                for positions, component in (
                    (placements_dict.get(component.ref, component.initial_position), component)
                    for component in state.netlist.components
                )
                if positions is not None
            }
            hv_pads = _grid_hv.hv_pad_set(
                all_pads_for_expansion, self.hv_exclusion_zones, component_positions
            )
            _grid_fence._EXPANSION_LOG.clear()
            for pad in all_pads_for_expansion:
                if (pad["ref"], pad["name"]) not in hv_pads:
                    continue

                for layer_idx in pad["layers"]:
                    if layer_idx >= grid.layer_count:
                        continue

                    layer_name = _grid_hv._layer_index_to_name(layer_idx, grid.layer_count)
                    eff_creep = _grid_hv.effective_creepage(
                        layer_name, 6.0
                    )  # allow-safety-constant: HV clearance default

                    pre_count = grid.blocked_count_on_layer(layer_idx)

                    pad_key = (pad["ref"], pad["name"])
                    real_pad = self.pad_sizes.get(pad_key)
                    use_rect = False
                    rect_size = (0.0, 0.0)
                    if real_pad and real_pad.shape in ("rect", "roundrect", "oval"):
                        rot = int(round(getattr(real_pad, "rotation", 0.0))) % 180
                        if rot == 0:
                            rect_size = (real_pad.size.X, real_pad.size.Y)
                            use_rect = True
                        elif rot == 90:
                            rect_size = (real_pad.size.Y, real_pad.size.X)
                            use_rect = True

                    if use_rect:
                        # Minkowski sum with a disc: each side grows by eff_creep.
                        w, h = rect_size
                        grid.block_rect(
                            center=pad["pos"],
                            size=(w + 2.0 * eff_creep, h + 2.0 * eff_creep),
                            clearance_mm=0.0,
                            layer=layer_idx,
                            net_name=None,
                            is_obstacle=True,
                        )
                    else:
                        # Circular Minkowski sum: radius grows by eff_creep.
                        grid.block_circle(
                            pad["pos"],
                            radius_mm=pad["radius"] + eff_creep,
                            clearance_mm=0.0,
                            layer=layer_idx,
                            net_name=None,
                            is_pad=False,
                        )

                    _grid_fence._EXPANSION_LOG.append(
                        (
                            pad["ref"],
                            pad["name"],
                            layer_idx,
                            pad["pos"],
                            pad["shape"],
                            pad["radius"],
                            (real_pad.size.X, real_pad.size.Y) if real_pad else (0.0, 0.0),
                            eff_creep,
                            grid.blocked_count_on_layer(layer_idx) - pre_count,
                        )
                    )

        # @req(2026-06-23-005, U3, R4, R8): After the U2 expansion pass,
        # invoke the grid-validity fence. A non-empty violation list means
        # the expansion under-blocked somewhere: a downstream A* would
        # route through an unsafe cell, violating creepage. Raise
        # FenceViolation with the first named pad/layer so the failure
        # is actionable from CI logs. The 20% perf-budget check is a
        # soft warning (R4) and is logged but does not fail the stage.
        if _grid_fence._EXPANSION_LOG:
            import time as _fence_time

            _fence_t0 = _fence_time.perf_counter()
            violations = _grid_fence.check_clearance_grid_conservatism(
                grid, _grid_fence._EXPANSION_LOG
            )
            _fence_elapsed_ms = (_fence_time.perf_counter() - _fence_t0) * 1000.0
            if violations:
                first = violations[0]
                raise _grid_fence.FenceViolation(
                    f"U3 fence failed on expansion: {first['reason']} "
                    f"(additional violations: {len(violations) - 1})"
                )
            # Soft perf-budget warning (R4). We approximate stage elapsed
            # time by the fence's own wall-time on its first run; this
            # keeps the budget comparison local to the fence call so
            # callers don't need to instrument the whole stage.
            _stage_elapsed_ms = max(_fence_elapsed_ms, 1.0)
            over_budget, warning = _grid_fence.check_clearance_grid_perf_budget(
                fence_elapsed_ms=_fence_elapsed_ms,
                stage_elapsed_ms=_stage_elapsed_ms,
            )
            if over_budget and warning is not None:
                print(f"  [clearance_grid fence] {warning}")

        # EXP-13: Block HV exclusion zones for specified nets
        # These zones force signals (like GATE_H, PWM_H) to route around HV areas
        # instead of taking the direct path that would violate creepage requirements.
        # Exclusion is per-net: only nets in excluded_nets are blocked.
        if self.hv_exclusion_zones:
            print(f"  HV exclusion zones: {len(self.hv_exclusion_zones)}")
            for hvz in self.hv_exclusion_zones:
                # For each excluded net, block the zone on all layers
                for excluded_net in hvz.excluded_nets:
                    net_id = grid.get_net_id(excluded_net)
                    # Block on all layers to ensure no path through zone
                    for layer_idx in range(grid.layer_count):
                        # Use block_rect with net marking
                        # By marking with a different net ID, we prevent the excluded
                        # net from routing through this zone
                        cx, cy = hvz.center
                        half_w = hvz.size[0] / 2.0
                        half_h = hvz.size[1] / 2.0

                        # Calculate bounding box in grid coordinates
                        min_col = max(0, int((cx - half_w) / grid.cell_size_mm))
                        max_col = min(grid.cols, int((cx + half_w) / grid.cell_size_mm) + 1)
                        min_row = max(0, int((cy - half_h) / grid.cell_size_mm))
                        max_row = min(grid.rows, int((cy + half_h) / grid.cell_size_mm) + 1)

                        # Mark zone as blocked for this net
                        # Using net_id = -2 (obstacle) prevents the net from routing here
                        target_grid = grid._trace_net_ids[layer_idx]
                        for row in range(min_row, max_row):
                            for col in range(min_col, max_col):
                                curr = target_grid[row, col]
                                # Only block if cell is free or belongs to a different net
                                # (allows HV nets to route through their own exclusion zone)
                                if curr == 0 or curr == net_id:
                                    target_grid[row, col] = -2  # Obstacle for this net

                print(
                    f"    {hvz.name}: blocking {hvz.excluded_nets} in "
                    f"{hvz.size[0]}x{hvz.size[1]}mm zone at {hvz.center}"
                )

        from dataclasses import replace

        return replace(state, grid=grid)
