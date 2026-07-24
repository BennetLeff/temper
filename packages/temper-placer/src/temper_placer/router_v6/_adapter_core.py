"""V6RouterAdapter — MazeRouter-compatible in-memory adapter for router_v6."""

from __future__ import annotations

import contextlib
import logging
import math
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from temper_placer.router_v6._adapter_types import _AdapterRoutePath

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.design_rules import DesignRules
    from temper_placer.core.netlist import Component

__all__ = [
    "V6RouterAdapter",
    "_extract_conflicts",
]


def _extract_conflicts(result: Any) -> list[dict[str, Any]]:
    """Extract conflict locations from V6 routing result."""
    conflicts: list[dict[str, Any]] = []
    if hasattr(result, "stage4") and result.stage4:
        unrouted = getattr(result.stage4, "unrouted_nets", []) or []
        for net_name in unrouted:
            conflicts.append(
                {
                    "x": 0,
                    "y": 0,
                    "layer": 0,
                    "nets": [net_name],
                    "world_x": 0.0,
                    "world_y": 0.0,
                }
            )
    return conflicts


class V6RouterAdapter:
    """MazeRouter-compatible adapter wrapping RouterV6Pipeline.

    Exposes the subset of MazeRouter's interface that consumers
    (auto_layout.py, internal_route.py) actually call:

        adapter = V6RouterAdapter.from_board(board, cell_size_mm, num_layers, ...)
        adapter.block_components(components, positions)
        results = adapter.rrr_route_all_nets(netlist, positions, net_order)
        conflicts = adapter.get_conflict_locations()

    .. note::
       This adapter is at the project's 30-day sunset threshold (last used
       via ``make route``, 31 days from last manifest ``last_run``). It may
       be formally sunset in a follow-up.
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
        _cost_maps: Any = None,
    ) -> dict[str, _AdapterRoutePath]:
        """Route all nets using RouterV6Pipeline.

        Writes a temporary KiCad PCB file with the current component
        positions, invokes RouterV6Pipeline, and converts results to
        RoutePath-compatible format.

        U8: the ``_cost_maps`` seam accepts a
        :class:`temper_placer.fields.CostFieldInput` (or any object
        with ``cost_flat`` and ``weight`` attributes).  When
        supplied, the thermal cost field is threaded into the A*
        kernel via the congestion-tensor injection path.
        """
        from temper_placer.router_v6.pipeline import RouterV6Pipeline

        # U8: extract thermal cost field from the _cost_maps seam
        thermal_flat = None
        thermal_weight = 0.0
        if (
            _cost_maps is not None
            and hasattr(_cost_maps, "cost_flat")
            and hasattr(_cost_maps, "weight")
        ):
            thermal_flat = _cost_maps.cost_flat
            thermal_weight = _cost_maps.weight

        # Build a minimal temp PCB from board + positions data
        temp_content = self._build_temp_pcb(netlist, positions)
        fd, temp_path = tempfile.mkstemp(suffix=".kicad_pcb")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(temp_content)

            # Resolve per-net layer assignments from the netclass SSOT,
            # matching route_pcb()'s corrected call shape so that netclass
            # rules reach the A* engine (R1 fix).
            layer_constraints: dict[str, Any] = {}
            if self._design_rules is not None:
                from temper_placer.router_v6.layer_assignment import (
                    layer_assignments_from_netclass,
                )

                net_names = list(net_order)
                if net_names:
                    layer_constraints = layer_assignments_from_netclass(
                        self._design_rules,
                        net_names,
                    )

            pipeline = RouterV6Pipeline(
                verbose=False,
                enable_theta_star=False,
                enable_lazy_theta_star=False,
                enable_smoothing=False,
                max_iter=500_000,
                thermal_flat=thermal_flat,
                thermal_weight=thermal_weight,
                layer_constraints=layer_constraints,
                enable_all_pad_tree=True,
                enable_zone_pours=True,
                enable_connectivity_verifier=False,
            )
            net_class_assignments = None
            if self._design_rules is not None:
                nc_assign = getattr(self._design_rules, "net_class_assignments", None)
                if nc_assign and isinstance(nc_assign, dict):
                    net_class_assignments = dict(nc_assign)
            result = pipeline.run(Path(temp_path), net_class_assignments=net_class_assignments)
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

        # Sort signal nets after power/HV nets (ordering heuristic -- R2).
        # Round 4 coexistence proof: all six critical nets coexist,
        # but signal nets are displaced when power nets route later.
        _SIG = ("SPI_", "I_SENSE", "USB_", "TEMP_")
        _PWR = ("GATE_", "PWM_", "DC_BUS", "AC_", "SW_NODE", "VCC_BOOT", "CGND", "PGND", "+", "GND")

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
            '  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (36 "B.Adhes" user) (44 "Edge.Cuts" edge))',
            "  (setup (pad_to_mask_clearance 0.1))",
            "",
        ]

        # Add board outline
        width_mm = getattr(board, "width", 100)
        height_mm = getattr(board, "height", 100)
        lines.append(f'  (gr_line (start 0 0) (end {width_mm} 0) (layer "Edge.Cuts") (width 0.1))')
        lines.append(
            f'  (gr_line (start {width_mm} 0) (end {width_mm} {height_mm}) (layer "Edge.Cuts") (width 0.1))'
        )
        lines.append(
            f'  (gr_line (start {width_mm} {height_mm}) (end 0 {height_mm}) (layer "Edge.Cuts") (width 0.1))'
        )
        lines.append(f'  (gr_line (start 0 {height_mm}) (end 0 0) (layer "Edge.Cuts") (width 0.1))')

        # Add nets
        if netlist and hasattr(netlist, "nets"):
            for net in netlist.nets:
                lines.append(f'  (net {netlist.nets.index(net) + 1} "{net.name}")')

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

                lines.append(f'  (footprint "{footprint}" (layer "F.Cu")')
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
                        f'    (pad "{pin.number}" smd rect (at {pin_x:.4f} {pin_y:.4f})'
                        f' (size 1 1) (layers "F.Cu" "F.Paste" "F.Mask")'
                        f' (net {net_idx} "{net_name}"))'
                    )
                lines.append(f"    (at {x:.4f} {y:.4f})")
                lines.append("  )")

        lines.append(")")
        return "\n".join(lines)
