"""Via validation and cleanup stage.

This stage removes dangling vias - vias that are not connected to traces
on at least two layers. Dangling vias cause DRC errors and indicate
routing failures.

Special handling for plane connections:
- Vias connecting to inner plane layers (In1.Cu for GND, In2.Cu for power)
  are considered valid even without traces, as they connect via copper pour.

Wave 4, **Phase 5, final leaves**: the via-connectivity counting kernel
(``_count_connected_layers``) and the via-position dedup kernel
(``ViaDeduplicationStage.run``'s sweep) are implemented in Rust in the
``temper-drc-rs`` crate (``temper_drc_rs.count_connected_layers_py`` /
``temper_drc_rs.dedup_via_positions_py``). This module keeps the pre-migration
public API unchanged and delegates; the endpoint-index building, the plane-net
predicate and the ``frozenset`` wraps stay Python.

Bit-exactness: the kernels replicate the oracle's ``tol_sq = tol * tol``
(plain multiply) vs ``tol_sq = tolerance ** 2`` (libm ``pow``) split, the
``** 2`` distance terms, the ``<=`` boundaries, and the plane-layer
short-circuit. Verified by
``tests/deterministic/stages/test_via_validation_rust_differential.py``
(oracle: ``tests/deterministic/stages/_via_validation_py_oracle.py``); the
structural proof lives in ``packages/temper-drc-rs/VERIFICATION.md``.
"""

from dataclasses import replace

import temper_drc_rs as _drc

from temper_placer.core.net_classification import is_ground_net, is_power_net

from ...core.board import (
    PLANE_LAYER_INDICES,
    STANDARD_LAYER_ORDER,
    Trace,
    Via,
)
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
        index: dict[str, set[tuple[float, float]]] = {}

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
        index: dict[str, set[tuple[float, float]]] = {}

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
        is_plane = _is_plane_net(via.net) if via.net else False
        plane_layers = [str(idx) for idx in PLANE_LAYER_INDICES]
        return _drc.count_connected_layers_py(
            via.position,
            list(via.layers),
            self.tolerance_mm,
            trace_index,
            pin_index,
            is_plane,
            plane_layers,
        )


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

        vias_list = list(state.vias)
        positions = [via.position for via in vias_list]
        kept_indices, duplicates = _drc.dedup_via_positions_py(
            positions, self.tolerance_mm
        )
        unique_vias = [vias_list[i] for i in kept_indices]

        if duplicates > 0:
            print(f"ViaDeduplication: Removed {duplicates} duplicate vias")

        return replace(state, vias=frozenset(unique_vias))
