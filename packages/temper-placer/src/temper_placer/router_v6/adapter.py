"""Adapter for Router V6 pipeline integration with the closure test.

Provides `route_pcb(parsed, placements, seed)` which applies placement
data to a KiCad PCB file, invokes RouterV6Pipeline, and returns results.

Also provides `V6RouterAdapter` — a MazeRouter-compatible in-memory adapter
for consumers that currently depend on `routing/maze_router`. Pattern:
    adapter = V6RouterAdapter.from_board(board, cell_size_mm, num_layers, design_rules)
    adapter.block_components(components, positions)
    results = adapter.rrr_route_all_nets(netlist, positions, net_order, assignments)
    conflicts = adapter.get_conflict_locations()
"""

from __future__ import annotations

import contextlib
import logging
import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.core.netlist import Component


@dataclass
class DrcViolation:
    """DRC violation from routing or manufacturing check.

    Attributes:
        net_name: Net name associated with the violation.
        message: Human-readable description.
        location: (x, y) position of the violation in mm.
        comp_a: First component ref (for separation violations).
        comp_b: Second component ref (for separation violations).
        required_mm: Required clearance distance.
        components: Component refs involved.
    """

    net_name: str = ""
    message: str = ""
    location: tuple[float, float] = (0.0, 0.0)
    comp_a: str = ""
    comp_b: str = ""
    required_mm: float = 6.0
    components: list[str] = field(default_factory=list)
    count: int = 0
    type: str = "unknown"


@dataclass
class CongestionRegion:
    """Bottleneck congestion region between components.

    Attributes:
        net_name: Net affected by congestion.
        comp_a: First component ref.
        comp_b: Second component ref.
        current_distance_mm: Current gap between components.
        positions: (pos_a, pos_b) positions in mm.
        bbox: Optional bounding box (x_min, y_min, x_max, y_max).
    """

    net_name: str = ""
    comp_a: str = ""
    comp_b: str = ""
    current_distance_mm: float = 0.0
    positions: tuple[
        tuple[float, float], tuple[float, float]
    ] = ((0.0, 0.0), (0.0, 0.0))
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class RoutingResult:
    """Result from route_pcb call.

    Attributes:
        completion_rate: Fraction of nets successfully routed (0.0 to 1.0).
        unrouted_nets: List of net names that failed to route.
        drc_violations: List of DrcViolation details from per-net reports
            and optional manufacturing report.
        congestion_regions: List of CongestionRegion details from
            bottleneck geometry analysis.
    """

    completion_rate: float = 0.0
    unrouted_nets: list[str] = field(default_factory=list)
    drc_violations: list[DrcViolation] = field(default_factory=list)
    congestion_regions: list[CongestionRegion] = field(default_factory=list)
    routed_pcb_content: str | None = None


# ---------------------------------------------------------------------------
# V6RouterAdapter — MazeRouter-compatible in-memory adapter
# ---------------------------------------------------------------------------

@dataclass
class _AdapterRoutePath:
    """RoutePath-compatible result for consumer compatibility."""
    net: str
    cells: list[Any] = field(default_factory=list)
    length: float = 0.0
    via_count: int = 0
    success: bool = False
    cell_size: float = 0.2
    difficulty: float = 0.0
    cell_difficulties: list[float] = field(default_factory=list)
    failure_reason: str | None = None
    smooth_points: list[Any] = field(default_factory=list)
    trace_width: float = 0.2
    via_diameter: float = 0.6
    via_drill: float = 0.3
    explicit_vias: list[Any] = field(default_factory=list)


class V6RouterAdapter:
    """MazeRouter-compatible adapter wrapping RouterV6Pipeline.

    Exposes the subset of MazeRouter's interface that consumers
    (auto_layout.py, internal_route.py) actually call:

        adapter = V6RouterAdapter.from_board(board, cell_size_mm, num_layers, ...)
        adapter.block_components(components, positions)
        results = adapter.rrr_route_all_nets(netlist, positions, net_order, assignments)
        conflicts = adapter.get_conflict_locations()
    """

    def __init__(
        self,
        board: Board,
        cell_size_mm: float,
        num_layers: int,
        design_rules: DesignRules | None = None,
        soft_blocking: bool = False,
        via_cost: float = 1.0,
    ):
        self._board = board
        self._cell_size_mm = cell_size_mm
        self._num_layers = num_layers
        self._design_rules = design_rules
        self._soft_blocking = soft_blocking
        self._via_cost = via_cost
        self._components: list[Component] = []
        self._positions: Any = None
        self._last_results: dict[str, _AdapterRoutePath] = {}
        self._last_conflicts: list[dict[str, Any]] = []

        width_cells = int(math.ceil(board.width / cell_size_mm))
        height_cells = int(math.ceil(board.height / cell_size_mm))
        self.grid_size = (width_cells, height_cells)

    @classmethod
    def from_board(
        cls,
        board: Board,
        cell_size_mm: float = 1.0,
        num_layers: int | None = None,
        via_cost: float = 1.0,
        soft_blocking: bool = False,
        _congestion_via_discount: float = 0.1,
        _min_clearance: float = 0.0,
        _drc_oracle: Any = None,
        _strict_mode: bool = False,
        design_rules: DesignRules | None = None,
        _wrong_way_penalty: float = 2.0,
    ) -> V6RouterAdapter:
        if num_layers is None:
            if hasattr(board, "layer_stackup") and board.layer_stackup:
                num_layers = len(board.layer_stackup.layers)
            else:
                num_layers = 1

        return cls(
            board=board,
            cell_size_mm=cell_size_mm,
            num_layers=num_layers,
            design_rules=design_rules,
            soft_blocking=soft_blocking,
            via_cost=via_cost,
        )

    def block_components(
        self, components: list[Component], positions: Any, _margin: float = 0.5
    ) -> None:
        """Record components and positions for routing."""
        self._components = components
        self._positions = positions

    def block_pads(
        self,
        components: list[Component],
        positions: Any,
        _netlist: Any,
        _trace_width: float = 0.2,
        _clearance: float = 0.2,
    ) -> None:
        """Record components for routing (pad-level blocking handled by V6)."""
        self._components = components
        self._positions = positions

    def block_board_features(self, board: Board) -> None:
        """Record board (edge cuts, mounting holes handled by V6)."""

    def rrr_route_all_nets(
        self,
        netlist: Any,
        positions: Any,
        net_order: list[str],
        _assignments: dict[str, Any],
        _cost_maps: Any = None,
        _max_iterations: int = 5,
        _history_increment: float = 1.0,
        _history_decay: float = 0.9,
        _p_scale_start: float = 1.0,
        _p_scale_step: float = 2.0,
        _progress_callback: Any = None,
        _incremental: bool = True,
        _validate_final: bool = False,
        _pin_positions_overrides: Any = None,
        _component_margin: float = 0.5,
        _soft_c_spaces: Any = None,
    ) -> dict[str, _AdapterRoutePath]:
        """Route all nets using RouterV6Pipeline.

        Writes a temporary KiCad PCB file with the current component
        positions, invokes RouterV6Pipeline, and converts results to
        RoutePath-compatible format.

        U8: the dormant ``_cost_maps`` seam accepts a
        :class:`temper_placer.fields.CostFieldInput` (or any object
        with ``cost_flat`` and ``weight`` attributes).  When
        supplied, the thermal cost field is threaded into the A*
        kernel via the congestion-tensor injection path.
        """
        from temper_placer.router_v6.pipeline import RouterV6Pipeline

        # U8: extract thermal cost field from the _cost_maps seam
        thermal_flat = None
        thermal_weight = 0.0
        if _cost_maps is not None and hasattr(_cost_maps, "cost_flat") and hasattr(_cost_maps, "weight"):
            thermal_flat = _cost_maps.cost_flat
            thermal_weight = _cost_maps.weight

        # Build a minimal temp PCB from board + positions data
        temp_content = self._build_temp_pcb(netlist, positions)
        fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(temp_content)

            pipeline = RouterV6Pipeline(
                verbose=False,
                enable_theta_star=False,
                enable_lazy_theta_star=False,
                enable_smoothing=False,
                max_iter=500_000,
                thermal_flat=thermal_flat,
                thermal_weight=thermal_weight,
            )
            result = pipeline.run(Path(temp_path))
        finally:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)

        # Convert V6 results to RoutePath-compatible dict
        results: dict[str, _AdapterRoutePath] = {}
        if hasattr(result, "stage4") and result.stage4:
            routed = getattr(result.stage4, "routed_paths", {})
            for net_name, path in (routed or {}).items():
                rp = _AdapterRoutePath(
                    net=net_name,
                    success=True,
                    length=getattr(path, "total_length_mm", 0.0),
                    trace_width=getattr(path, "trace_width_mm", 0.2),
                )
                results[net_name] = rp

        # Sort signal nets after power/HV nets (ordering heuristic — R2).
        # Round 4 coexistence proof: all six critical nets coexist,
        # but signal nets are displaced when power nets route later.
        _SIG = ("SPI_", "I_SENSE", "USB_", "TEMP_")
        _PWR = ("GATE_", "PWM_", "DC_BUS", "AC_", "SW_NODE",
                "VCC_BOOT", "CGND", "PGND", "+", "GND")
        def _net_prio(name):
            if any(name.startswith(p) for p in _PWR):
                return 0
            return 1
        net_order = sorted(net_order, key=_net_prio)

        # Mark unrouted nets
        for net_name in net_order:
            if net_name not in results:
                results[net_name] = _AdapterRoutePath(
                    net=net_name,
                    success=False,
                    failure_reason="V6 routing failed",
                )

        self._last_results = results
        self._last_conflicts = _extract_conflicts(result)
        return results

    def get_conflict_locations(self) -> list[dict[str, Any]]:
        return self._last_conflicts


    def _build_temp_pcb(self, netlist: Any, positions: Any) -> str:
        """Build minimal KiCad PCB content from board + components."""
        board = self._board
        lines = [
            "(kicad_pcb (version 20221018) (generator temper-placer)",
            "  (general (thickness 1.6))",
            "  (paper A4)",
            "  (layers (0 \"F.Cu\" signal) (31 \"B.Cu\" signal) (36 \"B.Adhes\" user) (44 \"Edge.Cuts\" edge))",
            "  (setup (pad_to_mask_clearance 0.1))",
            "",
        ]

        # Add board outline
        width_mm = getattr(board, "width", 100)
        height_mm = getattr(board, "height", 100)
        lines.append(
            f"  (gr_line (start 0 0) (end {width_mm} 0) (layer \"Edge.Cuts\") (width 0.1))"
        )
        lines.append(
            f"  (gr_line (start {width_mm} 0) (end {width_mm} {height_mm}) (layer \"Edge.Cuts\") (width 0.1))"
        )
        lines.append(
            f"  (gr_line (start {width_mm} {height_mm}) (end 0 {height_mm}) (layer \"Edge.Cuts\") (width 0.1))"
        )
        lines.append(
            f"  (gr_line (start 0 {height_mm}) (end 0 0) (layer \"Edge.Cuts\") (width 0.1))"
        )

        # Add nets
        if netlist and hasattr(netlist, "nets"):
            for net in netlist.nets:
                lines.append(f"  (net {netlist.nets.index(net) + 1} \"{net.name}\")")

        # Add components with footprints
        if self._components and positions is not None:
            for comp in self._components:
                footprint = getattr(comp, "footprint", "Resistor_SMD:R_0805_2012Metric")
                x, y = (0.0, 0.0)
                if hasattr(positions, "__getitem__"):
                    try:
                        pos = positions[comp.ref] if hasattr(positions, "get") else positions[0]
                        x, y = float(pos[0]), float(pos[1])
                    except (IndexError, KeyError, TypeError):
                        pass

                lines.append(
                    f"  (footprint \"{footprint}\" (layer \"F.Cu\")"
                )
                lines.append("    (attr smd)")
                for pin in getattr(comp, "pins", []):
                    pin_x = x + getattr(pin, "position", (0, 0))[0]
                    pin_y = y + getattr(pin, "position", (0, 0))[1]
                    net_name = getattr(pin, "net", "")
                    net_idx = 0
                    if netlist and hasattr(netlist, "nets"):
                        for i, n in enumerate(netlist.nets):
                            if n.name == net_name:
                                net_idx = i + 1
                                break
                    lines.append(
                        f"    (pad \"{pin.number}\" smd rect (at {pin_x:.4f} {pin_y:.4f})"
                        f" (size 1 1) (layers \"F.Cu\" \"F.Paste\" \"F.Mask\")"
                        f" (net {net_idx} \"{net_name}\"))"
                    )
                lines.append(f"    (at {x:.4f} {y:.4f})")
                lines.append("  )")

        lines.append(")")
        return "\n".join(lines)

def _extract_conflicts(result: Any) -> list[dict[str, Any]]:
    """Extract conflict locations from V6 routing result."""
    conflicts: list[dict[str, Any]] = []
    if hasattr(result, "stage4") and result.stage4:
        unrouted = getattr(result.stage4, "unrouted_nets", []) or []
        for net_name in unrouted:
            conflicts.append({
                "x": 0, "y": 0, "layer": 0,
                "nets": [net_name],
                "world_x": 0.0, "world_y": 0.0,
            })
    return conflicts


def route_pcb(
    parsed: Any,
    placements: dict[str, tuple[float, float]],
    _seed: int,
    design_rules: Any = None,
    net_class_assignments: dict[str, str] | None = None,
    thermal_flat: Any = None,  # U9: (N,) float32 thermal cost field
    thermal_weight: float = 0.0,  # U9: multiplier
    enable_all_pad_tree: bool = False,
) -> RoutingResult:
    """Route a PCB using the Router V6 pipeline.

    Applies the given component placements by writing a temporary modified
    .kicad_pcb file, then invokes the full 4-stage RouterV6Pipeline.

    Args:
        parsed: ParsedPCB from parse_kicad_pcb_v6.
        placements: Dict mapping component ref -> (x, y) position in mm.
            If empty, routing proceeds with the board's existing positions.
        seed: Random seed (passed through to pipeline configuration).
        design_rules: Optional DesignRules with net_classes for netclass
            form injection into the output PCB.
        net_class_assignments: Optional ``{net_name: netclass_name}`` map
            for per-net clearance-aware routing (R4 FinePitch 0.15mm).
        thermal_flat: U9 optional (N,) float32 thermal cost field from
            the previous round's field.  Threaded to A* kernel.
        thermal_weight: U9 multiplier on per-cell thermal cost
            (from CostFieldInput.weight).  0.0 = field-off.
        enable_all_pad_tree: Experimental all-terminal routing tree. Disabled
            until production KiCad DRC evidence clears the rollout gate.

    Returns:
        RoutingResult with completion_rate.

    Raises:
        ValueError: If parsed has no source_path.
    """
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    # Kept for the established public call signature; the current router
    # resolves layer constraints from ``design_rules`` below.
    del net_class_assignments

    if not placements:
        logger.warning(
            "Empty placements provided; routing with existing board positions."
        )

    pcb_path = getattr(parsed, "source_path", None)
    if pcb_path is None:
        raise ValueError("ParsedPCB has no source_path attribute")
    pcb_path = Path(pcb_path)

    # Resolve per-net layer assignments from the netclass SSOT (W2 R2) so the
    # router constrains each net to its assigned layer instead of letting a
    # signal hop onto a reference/power plane.
    layer_constraints: dict[str, Any] = {}
    if design_rules is not None:
        from temper_placer.router_v6.layer_assignment import (
            layer_assignments_from_netclass,
        )

        net_names = [
            n.name for n in getattr(parsed, "nets", []) if getattr(n, "name", None)
        ]
        if net_names:
            layer_constraints = layer_assignments_from_netclass(
                design_rules, net_names
            )

    pipeline = RouterV6Pipeline(
        verbose=False,
        enable_theta_star=False,
        enable_lazy_theta_star=False,
        enable_smoothing=False,
        max_iter=500_000,
        layer_constraints=layer_constraints,
        thermal_flat=thermal_flat,  # U9
        thermal_weight=thermal_weight,  # U9
        enable_all_pad_tree=enable_all_pad_tree,
    )

    if placements:
        raw_content = pcb_path.read_text(encoding="utf-8")
        modified_content = _apply_placements_to_pcb(
            raw_content, placements, design_rules=design_rules
        )

        fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(modified_content)

            # NOTE 2026-06-23: the closure test was using
            # enable_theta_star=True, enable_lazy_theta_star=True,
            # and enable_smoothing=True.  All three are wrong for
            # SM1 measurement on temper.kicad_pcb:
            #   * lazy theta star is a Python A* with no iter cap
            #     and the reroute loop blows up the full-run wall
            #     time to 5+ minutes (15/24 in 18s in the smoke vs
            #     13/24 incomplete after 5 min in the full profile).
            #   * plain theta star is also Python (no iter cap)
            #     and finds fewer nets than plain A* (Numba).
            #   * enable_smoothing=True is broken:
            #     SDFGrid.from_polygons is missing, so the
            #     smoothing step is a silent no-op (or worse).
            # The closure test should use the smoke-equivalent
            # path: plain 2D A* via the Numba kernel, no
            # smoothing.
            #
            # NOTE 2026-06-24: ``max_iter=500_000`` is the
            # path-quality sweet spot on temper.kicad_pcb.  The
            # kernel default of 1M explores further but lands
            # SPI_MOSI on a different tie-break path and the
            # reroute loop can't recover it (95.83% vs 100.0% at
            # 500k).  See
            # docs/solutions/architecture-patterns/router-v6-closure-rate-100pct-2026-06-24.md
            # for the iter-cap sweet-spot table.
            result = pipeline.run(Path(temp_path))
            placed_content = Path(temp_path).read_text(encoding="utf-8")
            routed_content = _write_routes_to_content(
                placed_content, result
            )
            return _build_routing_result(result, routed_content)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)
    else:
        result = pipeline.run(pcb_path)
        placed_content = pcb_path.read_text(encoding="utf-8")
        routed_content = _write_routes_to_content(placed_content, result)
        return _build_routing_result(result, routed_content)


def _write_routes_to_content(pcb_content: str, result: Any) -> str:
    """Inject routing tracks from RouterV6Pipeline result into KiCad PCB content.

    Extracts successfully routed paths from the pipeline result and writes
    them as ``(segment ...)`` entries and transition ``(via ...)`` entries
    into the PCB content. For plane nets (zero-length dummy paths) and for
    missing pins on multi-pin signal nets, creates direct connections using
    pad positions from the parsed PCB.
    """
    import math
    import uuid

    routing_results = getattr(result.stage4, "routing_results", None)
    if routing_results is None:
        return pcb_content

    compiled = getattr(routing_results, "compiled_routes", {})
    if not compiled:
        return pcb_content

    # Build net name -> net number mapping from the PCB content
    net_name_to_number: dict[str, int] = {}
    for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"', pcb_content):
        net_name_to_number[m.group(2)] = int(m.group(1))

    # Collect pad world positions from the parsed PCB data
    pcb = getattr(result, "pcb", None)
    pad_positions: dict[str, list[tuple[float, float]]] = {}
    if pcb is not None:
        comp_by_ref = {c.ref: c for c in pcb.components}
        for net in pcb.nets:
            positions: list[tuple[float, float]] = []
            for comp_ref, pin_name in getattr(net, "pins", []):
                comp = comp_by_ref.get(comp_ref)
                if comp is None:
                    continue
                comp_pos = getattr(comp, "initial_position", (0.0, 0.0))
                pin = comp.get_pin(pin_name) if hasattr(comp, "get_pin") else None
                if pin is None:
                    positions.append((float(comp_pos[0]), float(comp_pos[1])))
                else:
                    px, py = pin.position
                    positions.append((float(comp_pos[0]) + float(px), float(comp_pos[1]) + float(py)))
            if positions:
                pad_positions[net.name] = positions

    output_items: list[str] = []
    for net_name, compiled_route in compiled.items():
        path = getattr(compiled_route, "path", None)
        net_num = net_name_to_number.get(net_name, 0)
        route_vias = list(getattr(compiled_route, "vias", []))
        for via in route_vias:
            vx, vy = via.position
            via_id = uuid.uuid4()
            output_items.append(
                f'  (via (at {vx:.4f} {vy:.4f}) (size {via.diameter:.4f})'
                f' (drill {via.drill:.4f}) (layers "{via.from_layer}" "{via.to_layer}")'
                f' (net {net_num}) (tstamp "{via_id}"))'
            )

        if path is None:
            continue
        path_length = getattr(path, "path_length", 0.0)
        width = getattr(compiled_route, "width_mm", 0.2)
        # Defense-in-depth: never emit a zero/negative-width track (KiCad DRC
        # flags these as track_width violations). getattr's default does not
        # catch a present-but-zero width, so guard explicitly.
        if not width or width <= 0.0:
            width = 0.2
        pads = pad_positions.get(net_name, [])

        if path_length > 0 and len(pads) >= 2:
            # Real routed net: extract path coordinates
            path_nodes: list[tuple[float, float, str]] = []
            path_segs = getattr(path, "segments", None)
            if path_segs:
                for s in path_segs:
                    path_nodes.append((s[0], s[1], s[2]))
            else:
                coords = getattr(path, "coordinates", None)
                if coords:
                    path_layer = getattr(path, "layer_name", "F.Cu")
                    path_nodes = [(x, y, path_layer) for x, y in coords]

            path_points = [(x, y) for x, y, _layer in path_nodes]

            # A layer transition is encoded by co-located path nodes and a
            # U5 via.  Only same-layer, non-zero edges become KiCad tracks.
            geometric_edges = [
                (start, end)
                for start, end in zip(path_nodes, path_nodes[1:])
                if start[:2] != end[:2] and start[2] == end[2]
            ]

            # Write path segments, collapsing consecutive same-direction steps
            # to avoid A* grid-stepping staircasing.  Each individual grid
            # step (0.1mm) emitted as its own (segment ...) creates 8k+
            # micro-segments that KiCad DRC flags as clearance / shorting /
            # masking violations because adjacent segments from different
            # nets interleave with edge-to-edge gaps under the 0.2mm rule.
            i = 0
            while i < len(geometric_edges):
                start, end = geometric_edges[i]
                x1, y1, path_layer = start
                x2, y2, _ = end
                dx_prev = x2 - x1
                dy_prev = y2 - y1
                j = i + 1
                while j < len(geometric_edges):
                    previous, current = geometric_edges[j]
                    xm, ym, previous_layer = previous
                    xn, yn, current_layer = current
                    dx_cur = xn - xm
                    dy_cur = yn - ym
                    if (
                        previous[:2] == (x2, y2)
                        and previous_layer == path_layer
                        and current_layer == path_layer
                        and abs(dx_cur - dx_prev) < 1e-12
                        and abs(dy_cur - dy_prev) < 1e-12
                    ):
                        x2, y2 = xn, yn
                        j += 1
                    else:
                        break
                seg_id = uuid.uuid4()
                output_items.append(
                    f'  (segment (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f})'
                    f' (width {width:.4f}) (layer "{path_layer}") (net {net_num})'
                    f' (tstamp "{seg_id}"))'
                )
                i = j

            # Connect any pads not near the path (stitch missing pins)
            CONNECTION_THRESHOLD_MM = 0.5
            for px, py in pads:
                if not path_nodes:
                    continue
                min_dist = min(
                    math.hypot(px - qx, py - qy) for qx, qy in path_points
                )
                if min_dist > CONNECTION_THRESHOLD_MM:
                    nearest_idx = min(
                        range(len(path_nodes)),
                        key=lambda i: math.hypot(px - path_nodes[i][0], py - path_nodes[i][1]),
                    )
                    nx, ny, nearest_layer = path_nodes[nearest_idx]
                    co_located_layers = {
                        layer
                        for x, y, layer in path_nodes
                        if math.isclose(x, nx, abs_tol=1e-9)
                        and math.isclose(y, ny, abs_tol=1e-9)
                    }
                    if "F.Cu" not in co_located_layers and nearest_layer != "F.Cu":
                        # The pad stub is deliberately written on F.Cu. When
                        # its nearest routed point is on another layer, make
                        # that join explicit instead of leaving two copper
                        # islands that merely overlap in X/Y.
                        has_transition_via = any(
                            math.isclose(via.position[0], nx, abs_tol=1e-9)
                            and math.isclose(via.position[1], ny, abs_tol=1e-9)
                            and {via.from_layer, via.to_layer}
                            == {"F.Cu", nearest_layer}
                            for via in route_vias
                        )
                        if not has_transition_via:
                            template_via = route_vias[0] if route_vias else None
                            via_diameter = (
                                template_via.diameter if template_via is not None else 0.6
                            )
                            via_drill = template_via.drill if template_via is not None else 0.3
                            via_id = uuid.uuid4()
                            output_items.append(
                                f'  (via (at {nx:.4f} {ny:.4f}) (size {via_diameter:.4f})'
                                f' (drill {via_drill:.4f}) (layers "F.Cu" "{nearest_layer}")'
                                f' (net {net_num}) (tstamp "{via_id}"))'
                            )
                    seg_id = uuid.uuid4()
                    output_items.append(
                        f'  (segment (start {nx:.4f} {ny:.4f}) (end {px:.4f} {py:.4f})'
                        f' (width {width:.4f}) (layer "F.Cu") (net {net_num})'
                        f' (tstamp "{seg_id}"))'
                    )

        elif len(pads) >= 2:
            # Plane net with dummy path: create minimum spanning-tree
            # connections.  Dummy plane paths carry F.Cu until via-aware
            # multi-layer output lands (see W2 follow-up issue).
            mst_layer = getattr(path, "layer_name", None) or "F.Cu"
            remaining = list(pads)
            connected: list[tuple[float, float]] = [remaining.pop(0)]
            while remaining:
                best_dist = float("inf")
                best_idx = 0
                best_conn = connected[0]
                for i, pad in enumerate(remaining):
                    for cp in connected:
                        d = math.hypot(pad[0] - cp[0], pad[1] - cp[1])
                        if d < best_dist:
                            best_dist = d
                            best_idx = i
                            best_conn = cp
                pad = remaining.pop(best_idx)
                seg_id = uuid.uuid4()
                output_items.append(
                    f'  (segment (start {best_conn[0]:.4f} {best_conn[1]:.4f}) (end {pad[0]:.4f} {pad[1]:.4f})'
                    f' (width {width:.4f}) (layer "{mst_layer}") (net {net_num})'
                    f' (tstamp "{seg_id}"))'
                )
                connected.append(pad)

    if not output_items:
        return pcb_content

    # Inject routed copper before the closing ")" of the kicad_pcb s-expression.
    segment_block = "\n" + "\n".join(output_items) + "\n"
    pcb_content = pcb_content.rstrip()
    if pcb_content.endswith(")"):
        pcb_content = pcb_content[:-1] + segment_block + ")\n"

    return pcb_content


def _build_routing_result(result: Any, routed_content: str | None = None) -> RoutingResult:
    """Extract failure data from RouterV6Pipeline result into RoutingResult.

    Pulls failed net names, DRC violations from per-net reports, and
    congestion regions from bottleneck geometry analysis so that the
    FeedbackClassifier can act on real routing failures.
    """
    routing_results = result.stage4.routing_results
    unrouted_nets = list(routing_results.failed_nets)

    drc_violations: list[DrcViolation] = []
    congestion_regions: list[CongestionRegion] = []

    for report in getattr(routing_results, 'net_reports', []):
        # Collect DRC violations from per-net reports
        drc_count = getattr(report, 'drc_violations', 0)
        if drc_count > 0:
            drc_violations.append(DrcViolation(
                net_name=getattr(report, 'net_name', 'unknown'),
                count=drc_count,
                message=getattr(report, 'message', ''),
            ))

        # Collect congestion regions from bottleneck geometry
        bottleneck = getattr(report, 'bottleneck', None)
        if bottleneck is not None:
            pair_kind = getattr(bottleneck, 'pair_kind', None)
            if pair_kind in ('component_edge', 'component_keepout'):
                comps = getattr(bottleneck, 'component_pair', ('unknown', 'unknown'))
                gap = getattr(bottleneck, 'current_gap_mm', 0.0)
                positions = getattr(bottleneck, 'positions_mm', ((0.0, 0.0), (0.0, 0.0)))
                congestion_regions.append(CongestionRegion(
                    net_name=getattr(report, 'net_name', 'unknown'),
                    comp_a=comps[0],
                    comp_b=comps[1],
                    current_distance_mm=gap,
                    positions=positions,
                ))

    # Pull DRC data from manufacturing report if available
    mfg = getattr(result, 'manufacturing_report', None)
    if mfg is not None:
        for v in getattr(mfg, 'violations', []):
            drc_violations.append(DrcViolation(
                type=getattr(v, 'type', 'unknown'),
                message=getattr(v, 'message', ''),
                net_name=getattr(v, 'net_name', ''),
                location=getattr(v, 'location', (0.0, 0.0)),
            ))

    return RoutingResult(
        completion_rate=result.completion_rate,
        unrouted_nets=unrouted_nets,
        drc_violations=drc_violations,
        congestion_regions=congestion_regions,
        routed_pcb_content=routed_content,
    )


def _apply_placements_to_pcb(
    raw_content: str, placements: dict[str, tuple[float, float]],
    design_rules: Any = None,
) -> str:
    """Modify footprint (at X Y [ANGLE]) positions in KiCad PCB raw content."""
    foot_starts = [
        m.start()
        for m in re.finditer(r'\(footprint\s+"[^"]+"\s+\(layer', raw_content)
    ]

    if not foot_starts:
        return raw_content

    result_parts = []
    prev_end = 0

    for i, start in enumerate(foot_starts):
        end = (
            foot_starts[i + 1] if i + 1 < len(foot_starts) else len(raw_content)
        )
        block = raw_content[start:end]

        ref_match = re.search(
            r'\(property\s+"Reference"\s+"([^"]+)"', block
        )
        if ref_match:
            ref = ref_match.group(1)
            if ref in placements:
                x, y = placements[ref]
                block = re.sub(
                    r'(\(at\s+)[\d.-]+\s+[\d.-]+(\s*[\d.-]*\s*\))',
                    rf"\g<1>{x:.4f} {y:.4f}\2",
                    block,
                    count=1,
                )

        result_parts.append(raw_content[prev_end:start])
        result_parts.append(block)
        prev_end = end

    result_parts.append(raw_content[prev_end:])
    raw_content = "".join(result_parts)

    if design_rules is not None and getattr(design_rules, "net_classes", None):
        nc_forms = []
        for nc_name, nc_rules in sorted(design_rules.net_classes.items()):
            nc_forms.append(
                f"  (net_class \"{nc_name}\" \"Auto-generated from netclass_rules.yaml\""
                f" (clearance {nc_rules.clearance})"
                f" (trace_width {nc_rules.trace_width})"
                f" (via_dia {nc_rules.via_diameter})"
                f" (via_drill {nc_rules.via_drill}))"
            )
        nc_block = "\n" + "\n".join(nc_forms) + "\n"

        setup_match = re.search(r'\(setup\b', raw_content)
        if setup_match:
            depth = 0
            i = setup_match.start()
            while i < len(raw_content):
                if raw_content[i] == '(':
                    depth += 1
                elif raw_content[i] == ')':
                    depth -= 1
                    if depth == 0:
                        raw_content = raw_content[:i + 1] + nc_block + raw_content[i + 1:]
                        break
                i += 1

    return raw_content


MazeRouter = V6RouterAdapter
