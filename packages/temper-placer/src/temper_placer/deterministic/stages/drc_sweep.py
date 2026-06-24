"""Post-routing DRC sweep to remove violating geometry.

This stage runs after routing to identify and remove tracks/vias that
cause DRC violations. It's a cleanup pass that prevents bad geometry
from being exported.
"""

from dataclasses import replace
from typing import Set, Tuple, List
from ...core.board import LAYER_NAME_TO_IDX, STANDARD_LAYER_ORDER
from ..state import BoardState
from .base import Stage
from ...core.board import Trace, Via
from ...core.pin_geometry import pin_world_position


class DRCSweepStage(Stage):
    """Post-routing DRC sweep that removes violating geometry.

    This stage:
    1. Uses the DRC oracle to check all tracks and vias
    2. Removes geometry that causes clearance violations
    3. Removes tracks that short to other nets
    4. Reports what was removed for debugging

    Should run after ViaValidationStage but before final DRC validation.
    """

    def __init__(self, tolerance: float = 0.01):
        """Initialize DRC sweep.

        Args:
            tolerance: Position tolerance in mm for matching geometry
        """
        self.tolerance = tolerance

    @property
    def name(self) -> str:
        return "drc_sweep"

    def run(self, state: BoardState) -> BoardState:
        if not state.drc_oracle:
            # Can't sweep without oracle
            return state

        oracle = state.drc_oracle
        removed_tracks = 0
        removed_vias = 0
        removed_nets = set()

        # Check all traces
        valid_traces = []
        for trace in state.routes:
            if not isinstance(trace, Trace):
                valid_traces.append(trace)
                continue

            layer_idx = LAYER_NAME_TO_IDX.get(trace.layer, 0)
            valid, reason = oracle.can_place_track_segment(
                start=trace.start,
                end=trace.end,
                layer=layer_idx,
                net=trace.net or "",
                width=trace.width,
                check_existing=False,  # Don't check against already-placed (self)
            )

            # Also check for shorts to other nets
            if valid:
                valid_traces.append(trace)
            else:
                removed_tracks += 1
                if trace.net:
                    removed_nets.add(trace.net)

        # Check all vias
        valid_vias = []
        for via in state.vias:
            if not isinstance(via, Via):
                valid_vias.append(via)
                continue

            # Check via placement
            sites = oracle.get_valid_via_sites(
                via.position,
                search_radius=0.1,  # Very small - just checking current position
                net=via.net or "",
            )

            if sites:
                # Via position is valid
                valid_vias.append(via)
            else:
                removed_vias += 1
                if via.net:
                    removed_nets.add(via.net)

        if removed_tracks > 0 or removed_vias > 0:
            print(f"DRCSweep: Removed {removed_tracks} tracks, {removed_vias} vias")
            if removed_nets:
                nets_preview = ", ".join(sorted(removed_nets)[:10])
                print(
                    f"  Affected nets: {nets_preview}"
                    + (f" (+{len(removed_nets) - 10} more)" if len(removed_nets) > 10 else "")
                )

        return replace(state, routes=frozenset(valid_traces), vias=frozenset(valid_vias))


class TrackDeduplicationStage(Stage):
    """Remove duplicate track segments.

    Multiple routing attempts may create redundant traces at the same
    position. This stage removes duplicates.
    """

    def __init__(self, tolerance_mm: float = 0.05):
        self.tolerance_mm = tolerance_mm

    @property
    def name(self) -> str:
        return "track_deduplication"

    def run(self, state: BoardState) -> BoardState:
        if not state.routes:
            return state

        unique_traces = []
        seen = set()  # Set of (start, end, layer, net) tuples
        duplicates = 0
        tol = self.tolerance_mm

        for trace in state.routes:
            if not isinstance(trace, Trace):
                unique_traces.append(trace)
                continue

            # Normalize segment direction for comparison
            start, end = trace.start, trace.end
            if (start[0], start[1]) > (end[0], end[1]):
                start, end = end, start

            # Round to tolerance for comparison
            # Include net in key to avoid deduplicating different nets at same position
            key = (
                round(start[0] / tol) * tol,
                round(start[1] / tol) * tol,
                round(end[0] / tol) * tol,
                round(end[1] / tol) * tol,
                trace.layer,
                trace.net,  # Include net in key
            )

            if key in seen:
                duplicates += 1
                continue

            seen.add(key)
            unique_traces.append(trace)

        if duplicates > 0:
            print(f"TrackDeduplication: Removed {duplicates} duplicate segments")

        return replace(state, routes=frozenset(unique_traces))


class ShortCircuitDetectionStage(Stage):
    """Detect and remove tracks that short to other nets.

    This stage analyzes track connectivity and removes segments
    that connect to pads of different nets (shorts).
    """

    def __init__(self, tolerance_mm: float = 0.1):
        self.tolerance_mm = tolerance_mm

    @property
    def name(self) -> str:
        return "short_circuit_detection"

    def run(self, state: BoardState) -> BoardState:
        if not state.netlist or not state.routes:
            return state

        # Build map of pin positions to nets
        pin_net_map = {}  # (x, y, layer) -> net_name
        comp_positions = {}
        if state.placements:
            for ref, pos in state.placements:
                comp_positions[ref] = pos

        for comp in state.netlist.components:
            comp_pos = comp_positions.get(comp.ref, comp.initial_position or (0, 0))
            for pin in comp.pins:
                pin_pos = pin_world_position(pin, comp)
                # Find net for this pin
                for net in state.netlist.nets:
                    if (comp.ref, pin.name) in net.pins or (comp.ref, pin.number) in net.pins:
                        # Register on appropriate layers
                        if pin.is_pth:
                            for layer in (str(idx) for idx in STANDARD_LAYER_ORDER):
                                pin_net_map[(round(pin_pos[0], 2), round(pin_pos[1], 2), layer)] = (
                                    net.name
                                )
                        else:
                            layer = getattr(pin, "layer", "F.Cu")
                            pin_net_map[(round(pin_pos[0], 2), round(pin_pos[1], 2), layer)] = (
                                net.name
                            )
                        break

        # Check each track for shorts
        valid_traces = []
        removed = 0
        tol = self.tolerance_mm

        for trace in state.routes:
            if not isinstance(trace, Trace):
                valid_traces.append(trace)
                continue

            track_net = trace.net or ""
            is_short = False

            # Check if endpoints connect to wrong net
            for point in [trace.start, trace.end]:
                px, py = round(point[0], 2), round(point[1], 2)
                for (key_x, key_y, key_layer), net in pin_net_map.items():
                    if key_layer != trace.layer:
                        continue
                    if abs(px - key_x) <= tol and abs(py - key_y) <= tol:
                        if net != track_net and track_net:
                            print(
                                f"  SHORT: {trace.net} track near {net} pin at ({px:.1f}, {py:.1f})"
                            )
                            is_short = True
                            break
                if is_short:
                    break

            if not is_short:
                valid_traces.append(trace)
            else:
                removed += 1

        if removed > 0:
            print(f"ShortCircuitDetection: Removed {removed} shorting tracks")

        return replace(state, routes=frozenset(valid_traces))
