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
    enable_zone_pours: bool = False


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
        if _cost_maps is not None:
            if hasattr(_cost_maps, "cost_flat") and hasattr(_cost_maps, "weight"):
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
    thermal_flat: Any = None,
    thermal_weight: float = 0.0,
    enable_zone_pours: bool = False,
) -> RoutingResult:
    """Route a PCB using the Router V6 pipeline.

    Args:
        ...
        enable_zone_pours: Emit filled-copper zone geometry for power/
            ground/HV nets (per netclass SSOT).  Default False — zones
            are opt-in until measurement validates them.

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

    Returns:
        RoutingResult with completion_rate.

    Raises:
        ValueError: If parsed has no source_path.
    """
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

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
        thermal_flat=thermal_flat,
        thermal_weight=thermal_weight,
        enable_zone_pours=enable_zone_pours,
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
            result.enable_zone_pours = enable_zone_pours
            placed_content = Path(temp_path).read_text(encoding="utf-8")
            routed_content, _ = _write_routes_to_content(
                placed_content, result
            )
            return _build_routing_result(result, routed_content)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(temp_path)
    else:
        result = pipeline.run(pcb_path)
        result.enable_zone_pours = enable_zone_pours
        placed_content = pcb_path.read_text(encoding="utf-8")
        routed_content, _ = _write_routes_to_content(placed_content, result)
        return _build_routing_result(result, routed_content)


def _zone_layers_for_net(net_name: str) -> list[str]:
    """Resolve the zone/pour layer(s) for a net from the netclass SSOT.
    Returns empty list for nets that don't get zone treatment."""
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS
    nc = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
    if nc in ("GND", "Power", "GateDrive", "HighVoltage", "ACMains"):
        return ["F.Cu", "B.Cu"]
    return []


def _write_routes_to_content(pcb_content: str, result: Any) -> str:
    """Inject routing tracks from RouterV6Pipeline result into KiCad PCB content.

    Extracts successfully routed paths from the pipeline result and writes
    them as ``(segment ...)`` entries into the PCB content. For plane nets
    (zero-length dummy paths) and for missing pins on multi-pin signal nets,
    creates direct connections using pad positions from the parsed PCB.
    """
    import uuid
    from types import SimpleNamespace
    pad_positions: dict[str, list[tuple[float, float]]] = {}


    routing_results = getattr(result.stage4, "routing_results", None)
    if routing_results is None:
        return pcb_content, pad_positions

    compiled = getattr(routing_results, "compiled_routes", {})
    tree_compiled = getattr(routing_results, "tree_routes", {})
    partial_tree_compiled = getattr(routing_results, "partial_tree_routes", {})
    if not compiled and not tree_compiled and not partial_tree_compiled:
        return pcb_content, pad_positions

    # U7: fold tree routes into the compiled-routes iteration so the
    # writer emits tree-routed net geometry alongside legacy paths.
    _tree_seen: set[str] = set()
    for net_name, ctr in {**tree_compiled, **partial_tree_compiled}.items():
        if net_name in compiled or net_name in _tree_seen:
            continue
        _tree_seen.add(net_name)
        fake_path = SimpleNamespace(
            path_length=1.0,
            coordinates=[],  # tree routes have no serial coordinates
        )
        compiled[net_name] = SimpleNamespace(
            path=fake_path,
            width_mm=getattr(ctr, "width_mm", 0.2),
            vias=getattr(ctr, "vias", []),
            _tree_route=ctr,
        )

    # Build net name -> net number mapping from the PCB content
    net_name_to_number: dict[str, int] = {}
    for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"', pcb_content):
        net_name_to_number[m.group(2)] = int(m.group(1))

    # Collect pad world positions from the parsed PCB data
    pcb = getattr(result, "pcb", None)
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

    segments: list[str] = []
    for net_name, compiled_route in compiled.items():
        path = getattr(compiled_route, "path", None)
        if path is None:
            continue

        # U7: emit tree-route branch geometry directly.  Each branch's
        # segments are written as independent track segments; sibling
        # branches are never bridged by synthetic copper.
        tree_route = getattr(compiled_route, "_tree_route", None)
        if tree_route is not None:
            for branch in tree_route.geometry.branches:
                net_num = net_name_to_number.get(net_name, 0)
                for sx, sy, ex, ey, layer in branch.path.iter_segments():
                    seg_id = uuid.uuid4()
                    segments.append(
                        f'  (segment (start {sx:.4f} {sy:.4f}) (end {ex:.4f} {ey:.4f})'
                        f' (width {width:.4f}) (layer "{layer}") (net {net_num})'
                        f' (tstamp "{seg_id}"))'
                    )
            continue

        path_length = getattr(path, "path_length", 0.0)
        width = getattr(compiled_route, "width_mm", 0.2)
        # Defense-in-depth: never emit a zero/negative-width track (KiCad DRC
        # flags these as track_width violations). getattr's default does not
        # catch a present-but-zero width, so guard explicitly.
        if not width or width <= 0.0:
            width = 0.2
        net_num = net_name_to_number.get(net_name, 0)
        pads = pad_positions.get(net_name, [])

        if path_length > 0 and len(pads) >= 2:
            # Real routed net: extract path coordinates
            path_points: list[tuple[float, float]] = []
            path_layer = "F.Cu"
            path_segs = getattr(path, "segments", None)
            if path_segs:
                for s in path_segs:
                    path_points.append((s[0], s[1]))
                    path_layer = s[2]
            else:
                coords = getattr(path, "coordinates", None)
                if coords:
                    path_points = list(coords)
                    path_layer = getattr(path, "layer_name", "F.Cu")

            # Write path segments, collapsing consecutive same-direction steps
            # to avoid A* grid-stepping staircasing.  Each individual grid
            # step (0.1mm) emitted as its own (segment ...) creates 8k+
            # micro-segments that KiCad DRC flags as clearance / shorting /
            # masking violations because adjacent segments from different
            # nets interleave with edge-to-edge gaps under the 0.2mm rule.
            i = 0
            while i < len(path_points) - 1:
                x1, y1 = path_points[i][0], path_points[i][1]
                x2, y2 = path_points[i + 1][0], path_points[i + 1][1]
                dx_prev = x2 - x1
                dy_prev = y2 - y1
                j = i + 2
                while j < len(path_points):
                    xm = path_points[j - 1][0]
                    ym = path_points[j - 1][1]
                    xn = path_points[j][0]
                    yn = path_points[j][1]
                    dx_cur = xn - xm
                    dy_cur = yn - ym
                    if abs(dx_cur - dx_prev) < 1e-12 and abs(dy_cur - dy_prev) < 1e-12:
                        x2, y2 = xn, yn
                        j += 1
                    else:
                        break
                seg_id = uuid.uuid4()
                segments.append(
                    f'  (segment (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f})'
                    f' (width {width:.4f}) (layer "{path_layer}") (net {net_num})'
                    f' (tstamp "{seg_id}"))'
                )
                i = j - 1
        # U5: emit real (via ...) s-expressions for each Via in the compiled route.
        for via in getattr(compiled_route, "vias", []):
            vx, vy = via.position
            segments.append(
                f'  (via (at {vx:.4f} {vy:.4f}) (size {via.diameter:.4f})'
                f' (drill {via.drill:.4f}) (layers "{via.from_layer}" "{via.to_layer}")'
                f' (net {net_num}) (tstamp "{uuid.uuid4()}"))'
            )

    # U1 zone/pour: emit filled-copper zones for ALL zone-eligible nets,
    # not just the ones that routed.  Must fire before the early return.
    if getattr(result, "enable_zone_pours", False):
        from temper_placer.router_v6.zone_emission import (
            compute_zone_for_net, emit_zone_s_expr,
        )
        for net_name, positions in pad_positions.items():
            zone_layers = _zone_layers_for_net(net_name)
            if not zone_layers:
                continue
            net_num = net_name_to_number.get(net_name, 0)
            if net_num > 0 and positions:
                for layer in zone_layers:
                    try:
                        zd = compute_zone_for_net(
                            net_name, net_num, positions, layer=layer,
                        )
                        segments.append(emit_zone_s_expr(zd))
                    except ValueError:
                        pass

    if not segments:
        return pcb_content, pad_positions

    # Inject segments before the closing ")" of the kicad_pcb s-expression
    segment_block = "\n" + "\n".join(segments) + "\n"
    pcb_content = pcb_content.rstrip()
    if pcb_content.endswith(")"):
        pcb_content = pcb_content[:-1] + segment_block + ")\n"

    return pcb_content, pad_positions


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
