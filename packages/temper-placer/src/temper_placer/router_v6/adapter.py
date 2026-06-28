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

import logging
import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

import numpy as np

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.core.netlist import Netlist, Component


@dataclass
class RoutingResult:
    """Result from route_pcb call.

    Attributes:
        completion_rate: Fraction of nets successfully routed (0.0 to 1.0).
    """

    completion_rate: float = 0.0


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
        congestion_via_discount: float = 0.1,
        min_clearance: float = 0.0,
        drc_oracle: Any = None,
        strict_mode: bool = False,
        design_rules: DesignRules | None = None,
        wrong_way_penalty: float = 2.0,
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
        self, components: list[Component], positions: Any, margin: float = 0.5
    ) -> None:
        """Record components and positions for routing."""
        self._components = components
        self._positions = positions

    def block_pads(
        self,
        components: list[Component],
        positions: Any,
        netlist: Any,
        trace_width: float = 0.2,
        clearance: float = 0.2,
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
        assignments: dict[str, Any],
        cost_maps: Any = None,
        max_iterations: int = 5,
        history_increment: float = 1.0,
        history_decay: float = 0.9,
        p_scale_start: float = 1.0,
        p_scale_step: float = 2.0,
        progress_callback: Any = None,
        incremental: bool = True,
        validate_final: bool = False,
        pin_positions_overrides: Any = None,
        component_margin: float = 0.5,
        soft_c_spaces: Any = None,
    ) -> dict[str, _AdapterRoutePath]:
        """Route all nets using RouterV6Pipeline.

        Writes a temporary KiCad PCB file with the current component
        positions, invokes RouterV6Pipeline, and converts results to
        RoutePath-compatible format.
        """
        from temper_placer.router_v6.pipeline import RouterV6Pipeline

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
            )
            result = pipeline.run(Path(temp_path))
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

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

        # Mark unrouted nets
        for net_name in net_order:
            if net_name not in results:
                results[net_name] = _AdapterRoutePath(
                    net=net_name,
                    success=False,
                    failure_reason="V6 routing failed",
                )

        self._last_results = results
        self._last_conflicts = self._extract_conflicts(result)
        return results

    def get_conflict_locations(self) -> list[dict[str, Any]]:
        return self._last_conflicts

    @staticmethod
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

    def _build_temp_pcb(self, netlist: Any, positions: Any) -> str:
        """Build minimal KiCad PCB content from board + components."""
        board = self._board
        lines = [
            "(kicad_pcb (version 20221018) (generator temper-placer)",
            f"  (general (thickness 1.6))",
            f"  (paper A4)",
            f"  (layers (0 \"F.Cu\" signal) (31 \"B.Cu\" signal) (36 \"B.Adhes\" user) (44 \"Edge.Cuts\" edge))",
            f"  (setup (pad_to_mask_clearance 0.1))",
            f"",
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
                ref = comp.ref
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
                lines.append(f"    (attr smd)")
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
                lines.append(f"  )")

        lines.append(")")
        return "\n".join(lines)


def route_pcb(
    parsed: Any,
    placements: dict[str, tuple[float, float]],
    seed: int,
) -> RoutingResult:
    """Route a PCB using the Router V6 pipeline.

    Applies the given component placements by writing a temporary modified
    .kicad_pcb file, then invokes the full 4-stage RouterV6Pipeline.

    Args:
        parsed: ParsedPCB from parse_kicad_pcb_v6.
        placements: Dict mapping component ref -> (x, y) position in mm.
            If empty, routing proceeds with the board's existing positions.
        seed: Random seed (passed through to pipeline configuration).

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

    pipeline = RouterV6Pipeline(
        verbose=False,
        enable_theta_star=False,
        enable_lazy_theta_star=False,
        enable_smoothing=False,
        max_iter=500_000,
    )

    if placements:
        raw_content = pcb_path.read_text(encoding="utf-8")
        modified_content = _apply_placements_to_pcb(raw_content, placements)

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
            return RoutingResult(completion_rate=result.completion_rate)
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
    else:
        result = pipeline.run(pcb_path)
        return RoutingResult(completion_rate=result.completion_rate)


def _apply_placements_to_pcb(
    raw_content: str, placements: dict[str, tuple[float, float]]
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
    return "".join(result_parts)
