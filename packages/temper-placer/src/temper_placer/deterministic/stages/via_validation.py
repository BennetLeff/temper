"""Via validation and cleanup stage.

This stage removes dangling vias - vias that are not connected to traces
on at least two layers. Dangling vias cause DRC errors and indicate
routing failures.

Special handling for plane connections:
- Vias connecting to inner plane layers (In1.Cu for GND, In2.Cu for power)
  are considered valid even without traces, as they connect via copper pour.
"""

from dataclasses import replace

from temper_placer.core.net_classification import is_ground_net, is_power_net

from ...core.board import STANDARD_LAYER_ORDER, Trace, Via, is_plane_layer
from ...core.pin_geometry import pin_world_position
from ..state import BoardState
from .base import Stage


def _is_plane_net(net_name: str) -> bool:
    """Check if a net typically connects via copper plane."""
    if not net_name:
        return False
    return is_ground_net(net_name) or is_power_net(net_name)


class ViaValidationStage(Stage):
    """Validates and cleans up vias after routing.

    Removes vias that are not properly connected, which happens when:
    - Routing failed to complete a connection
    - Via was placed optimistically but target layer route failed
    - Layer transition was abandoned mid-route

    Parameters:
        tolerance_mm: Distance tolerance for considering a trace connected to a via.
                     Default 0.1mm accounts for grid snapping and floating point errors.
        require_both_layers: If True (default), removes vias not connected on both layers.
                            If False, keeps vias connected on at least one layer.
    """

    def __init__(self, tolerance_mm: float = 0.1, require_both_layers: bool = True):
        self.tolerance_mm = tolerance_mm
        self.require_both_layers = require_both_layers

    @property
    def name(self) -> str:
        return "via_validation"

    def run(self, state: BoardState) -> BoardState:
        if not state.vias or not state.routes:
            return state

        # Build index of trace endpoints by layer
        # Key: layer name, Value: set of (x, y) positions within tolerance
        trace_endpoints_by_layer = self._build_trace_endpoint_index(state.routes)

        # Also build index of pin positions (vias connected to pads count as connected)
        pin_positions_by_layer = self._build_pin_position_index(state)

        valid_vias = []
        removed_count = 0
        removed_nets = set()

        # Debug: Count plane vias
        plane_vias_total = 0
        plane_vias_kept = 0
        plane_vias_removed = []

        for via in state.vias:
            # Skip protected differential pair vias
            if getattr(via, "is_diff_pair", False):
                valid_vias.append(via)
                continue

            is_plane = _is_plane_net(via.net) if via.net else False
            if is_plane:
                plane_vias_total += 1

            layers_connected = self._count_connected_layers(
                via, trace_endpoints_by_layer, pin_positions_by_layer
            )

            is_valid = layers_connected >= 2 if self.require_both_layers else layers_connected >= 1

            if is_valid:
                valid_vias.append(via)
                if is_plane:
                    plane_vias_kept += 1
            else:
                # Special case: plane vias with 1 connection on F.Cu are valid
                # because they connect to the plane on the inner layer
                if is_plane and layers_connected >= 1:
                    valid_vias.append(via)
                    plane_vias_kept += 1
                else:
                    removed_count += 1
                    if via.net:
                        removed_nets.add(via.net)
                    if is_plane:
                        plane_vias_removed.append(
                            (via.net, via.position, via.layers, layers_connected)
                        )

        if removed_count > 0:
            print(f"ViaValidation: Removed {removed_count} dangling vias")
            if removed_nets:
                print(
                    f"  Affected nets: {', '.join(sorted(removed_nets)[:10])}"
                    + (f" (+{len(removed_nets) - 10} more)" if len(removed_nets) > 10 else "")
                )

        # Debug output
        if plane_vias_total > 0:
            print(f"ViaValidation: Plane vias: {plane_vias_kept}/{plane_vias_total} kept")
            if plane_vias_removed:
                print("  Removed plane vias (first 5):")
                for net, pos, layers, conn in plane_vias_removed[:5]:
                    print(f"    {net} at {pos} layers={layers} connected={conn}")

        return replace(state, vias=frozenset(valid_vias))

    def _build_trace_endpoint_index(self, routes: frozenset) -> dict:
        """Build index of trace endpoints by layer for fast lookup."""
        index = {}

        for trace in routes:
            if not isinstance(trace, Trace):
                continue

            layer = trace.layer
            if layer not in index:
                index[layer] = set()

            # Add both endpoints
            index[layer].add(trace.start)
            index[layer].add(trace.end)

            # Also add points along the trace for mid-trace via connections
            # Sample every 0.5mm along trace
            length = (
                (trace.end[0] - trace.start[0]) ** 2 + (trace.end[1] - trace.start[1]) ** 2
            ) ** 0.5
            if length > 0:
                steps = max(1, int(length / 0.5))
                for i in range(1, steps):
                    t = i / steps
                    x = trace.start[0] + t * (trace.end[0] - trace.start[0])
                    y = trace.start[1] + t * (trace.end[1] - trace.start[1])
                    index[layer].add((x, y))

        return index

    def _build_pin_position_index(self, state: BoardState) -> dict:
        """Build index of pin positions by layer."""
        index = {}

        if not state.netlist:
            return index

        # Build component position lookup
        comp_positions = {}
        if state.placements:
            for ref, pos in state.placements:
                comp_positions[ref] = pos

        # Add pin positions - assume F.Cu for SMD, all layers for PTH
        for comp in state.netlist.components:
            comp_positions.get(comp.ref, comp.initial_position or (0, 0))

            for pin in comp.pins:
                pin_pos = pin_world_position(pin, comp)

                if pin.is_pth:
                    # PTH pins are on all layers
                    for layer in (str(idx) for idx in STANDARD_LAYER_ORDER):
                        if layer not in index:
                            index[layer] = set()
                        index[layer].add(pin_pos)
                else:
                    # SMD pins are on F.Cu (or their specified layer)
                    layer = getattr(pin, "layer", "F.Cu")
                    if layer not in index:
                        index[layer] = set()
                    index[layer].add(pin_pos)

        return index

    def _count_connected_layers(self, via: Via, trace_index: dict, pin_index: dict) -> int:
        """Count how many layers the via is connected to.

        For plane nets (GND, power), inner layers (In1.Cu, In2.Cu) are considered
        connected automatically since they connect via copper pour, not traces.
        """
        connected_layers = set()
        tol = self.tolerance_mm
        tol_sq = tol * tol
        vx, vy = via.position

        # Check if this is a plane net (GND or power)
        is_plane = _is_plane_net(via.net) if via.net else False

        for layer in via.layers:
            # For plane nets, inner layers count as connected (copper pour)
            if is_plane and is_plane_layer(layer):
                connected_layers.add(layer)
                continue

            # Check trace endpoints
            if layer in trace_index:
                for tx, ty in trace_index[layer]:
                    dist_sq = (vx - tx) ** 2 + (vy - ty) ** 2
                    if dist_sq <= tol_sq:
                        connected_layers.add(layer)
                        break

            # If not connected to trace, check pin positions
            if layer not in connected_layers and layer in pin_index:
                for px, py in pin_index[layer]:
                    dist_sq = (vx - px) ** 2 + (vy - py) ** 2
                    if dist_sq <= tol_sq:
                        connected_layers.add(layer)
                        break

        return len(connected_layers)


class ViaDeduplicationStage(Stage):
    """Remove duplicate vias at the same position.

    Multiple routing attempts may create redundant vias at the same location.
    This stage keeps only one via per unique position.
    """

    def __init__(self, tolerance_mm: float = 0.05):
        self.tolerance_mm = tolerance_mm

    @property
    def name(self) -> str:
        return "via_deduplication"

    def run(self, state: BoardState) -> BoardState:
        if not state.vias:
            return state

        unique_vias = []
        seen_positions = []  # List of (x, y) already added
        tol_sq = self.tolerance_mm**2
        duplicates = 0

        for via in state.vias:
            vx, vy = via.position
            is_duplicate = False

            for sx, sy in seen_positions:
                if (vx - sx) ** 2 + (vy - sy) ** 2 <= tol_sq:
                    is_duplicate = True
                    duplicates += 1
                    break

            if not is_duplicate:
                unique_vias.append(via)
                seen_positions.append(via.position)

        if duplicates > 0:
            print(f"ViaDeduplication: Removed {duplicates} duplicate vias")

        return replace(state, vias=frozenset(unique_vias))
